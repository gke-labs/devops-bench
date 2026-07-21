# Copyright 2026 The Kubernetes Authors.
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

"""Parser for the Claude Code ``--output-format stream-json`` event stream.

Folds the ``tool_use`` / ``tool_result`` content blocks into the canonical
:class:`ToolCall` list and pulls the final answer and token usage from the
terminal ``result`` event. ``thinking`` / ``redacted_thinking`` blocks are
dropped so the trajectory matches the tool-calls-only shape the other CLI
harnesses emit.
"""

from __future__ import annotations

import json

from devops_bench.agents.result import ToolCall

__all__ = ["parse_stream_json", "empty_tokens"]

# Canonical token buckets, harness-local until the shared schema lands
# (gke-labs/devops-bench#212). ``input`` is non-cached; ``total`` sums all buckets.
_TOKEN_BUCKETS = ("input", "cached", "cache_write", "reasoning", "output", "total")


def empty_tokens() -> dict:
    """Return the canonical token dict with every bucket ``None`` (unavailable)."""
    return dict.fromkeys(_TOKEN_BUCKETS, None)


def _block_text(content: object) -> str | None:
    """Render a tool_result ``content`` payload to a string, or ``None``.

    Claude Code emits tool results either as a bare string or as a list of
    content blocks (``[{"type": "text", "text": ...}]``). Both are flattened to
    text; any other shape is JSON-encoded so nothing is dropped silently.
    """
    if content is None:
        return None
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts = [
            block["text"]
            for block in content
            if isinstance(block, dict) and isinstance(block.get("text"), str)
        ]
        if parts:
            return "".join(parts)
    return json.dumps(content, default=str)


# Claude Code namespaces MCP tools as ``mcp__<server>__<tool>``. The rest of the
# pipeline uses the ``<server>__<tool>`` convention (the metrics canonicalizer
# strips exactly one ``<server>__`` segment to recover the bare tool name), so
# drop the literal ``mcp__`` client prefix to stay consistent with the other
# harnesses. Built-in tools (``Bash``, ``Read``, ...) carry no prefix.
_MCP_TOOL_PREFIX = "mcp__"


def _normalize_tool_name(name: str) -> str:
    """Strip Claude Code's ``mcp__`` client prefix from an MCP tool name."""
    if name.startswith(_MCP_TOOL_PREFIX):
        return name[len(_MCP_TOOL_PREFIX) :]
    return name


# Terminal-failure MCP statuses in the ``init`` event. Transient ``pending`` /
# ``connecting`` states are excluded: a stdio server (e.g. gke-mcp) often reports
# them at init yet connects moments later, so flagging them would false-positive
# on a working run.
_MCP_FAILED_STATUSES = frozenset({"failed", "error", "disconnected", "needs-auth", "needs_auth"})


def parse_stream_json(stdout: str) -> tuple[str, list[dict], dict, list[str]]:
    """Parse a Claude Code ``--output-format stream-json`` stdout stream.

    The stream is newline-delimited JSON in the wrapped SDK form: each line is
    an envelope with a top-level ``type`` (``system`` / ``assistant`` / ``user``
    / ``result``) carrying a nested Anthropic ``message`` object. The parser is
    intentionally lenient (unknown event types are skipped) and surfaces both
    per-line JSON decode errors and unmatched ``tool_result`` blocks on the
    ``errors`` list rather than dropping them.

    | Event type    | Handling                                                  |
    |---------------|-----------------------------------------------------------|
    | ``system``    | ``init`` metadata, ignored                                |
    | ``assistant`` | ``tool_use`` → pending ToolCalls; ``text`` → output;      |
    |               | ``thinking`` / ``redacted_thinking`` dropped              |
    | ``user``      | ``tool_result`` blocks matched to pending ToolCalls       |
    | ``result``    | terminal: authoritative answer, token usage, error subtype|

    ``trajectory`` is a list of tool calls (``ToolCall.to_dict()``) in emission
    order, matching the tool-calls-only shape the other CLI harnesses emit;
    ``thinking`` / ``redacted_thinking`` blocks are dropped rather than recorded
    as steps.

    The accumulated assistant ``text`` doubles as a fallback answer for the rare
    case where no terminal ``result`` event arrives (e.g. a truncated pipe on
    older ``claude`` builds); when the ``result`` event is present its ``result``
    string is authoritative.

    Args:
        stdout: Raw process stdout, possibly empty.

    Returns:
        A ``(output, trajectory, tokens, errors)`` tuple. ``trajectory`` is a
        list of ``ToolCall.to_dict()`` mappings ordered as emitted.
    """
    text_parts: list[str] = []
    result_output: str | None = None
    tokens: dict = empty_tokens()
    acc_usage: dict = {}
    errors: list[str] = []
    pending: dict[str, ToolCall] = {}
    trajectory: list[ToolCall] = []

    for lineno, raw in enumerate(stdout.splitlines(), start=1):
        line = raw.strip()
        if not line:
            continue
        try:
            event = json.loads(line)
        except json.JSONDecodeError as exc:
            errors.append(f"stream-json line {lineno} parse error: {exc}")
            continue
        if not isinstance(event, dict):
            continue

        etype = event.get("type")
        if etype == "system":
            # A failed MCP server leaves the run tool-less but still exits 0, so
            # surface terminal-failure statuses (see ``_MCP_FAILED_STATUSES``)
            # rather than scoring a silently-degraded run clean.
            if event.get("subtype") == "init":
                for server in event.get("mcp_servers") or []:
                    if not isinstance(server, dict):
                        continue
                    status = str(server.get("status", "")).lower()
                    if status in _MCP_FAILED_STATUSES:
                        name = server.get("name") or "<unknown>"
                        errors.append(f"mcp server {name!r} failed to connect at init: {status}")
        elif etype == "assistant":
            message = event.get("message") or {}
            # Accumulate per-turn usage so a truncated stream (no terminal
            # ``result`` event) still yields token counts, not ``{}``.
            _add_usage(acc_usage, message.get("usage"))
            content = message.get("content")
            if not isinstance(content, list):
                continue
            for block in content:
                if not isinstance(block, dict):
                    continue
                btype = block.get("type")
                if btype == "text":
                    if isinstance(block.get("text"), str):
                        text_parts.append(block["text"])
                elif btype in ("thinking", "redacted_thinking"):
                    continue  # not part of the tool-calls-only trajectory
                elif btype == "tool_use":
                    args = block.get("input")
                    call = ToolCall(
                        name=_normalize_tool_name(block.get("name", "")),
                        args=args if isinstance(args, dict) else {},
                        status="called",
                    )
                    trajectory.append(call)
                    call_id = block.get("id")
                    if call_id:
                        pending[str(call_id)] = call
        elif etype == "user":
            content = (event.get("message") or {}).get("content")
            if not isinstance(content, list):
                # A user message with a bare-string content echoes the prompt.
                continue
            for block in content:
                if not isinstance(block, dict) or block.get("type") != "tool_result":
                    continue
                call_id = block.get("tool_use_id") or ""
                target = pending.pop(str(call_id), None) if call_id else None
                if target is None:
                    errors.append(
                        f"stream-json tool_result without matching tool_use (id={call_id!r})"
                    )
                    continue
                target.result = _block_text(block.get("content"))
                target.status = "error" if block.get("is_error") else "completed"
        elif etype == "result":
            # Terminal event: ``result`` is the authoritative answer, ``usage``
            # holds token accounting, and an ``error_*`` subtype flags failure.
            tail = event.get("result")
            if isinstance(tail, str):
                result_output = tail
            usage = event.get("usage")
            if isinstance(usage, dict):
                tokens = _usage_tokens(usage)
            subtype = event.get("subtype")
            if isinstance(subtype, str) and subtype.startswith("error_"):
                errors.append(f"stream-json result error: {subtype}")

    output = result_output if result_output is not None else "".join(text_parts)
    # Fall back to the summed per-turn usage when the terminal ``result`` usage
    # is absent or degenerate. The canonical dict is truthy even when all-None,
    # so test the values, not the dict.
    if not any(tokens.values()) and acc_usage:
        tokens = _usage_tokens(acc_usage)
    return output, [call.to_dict() for call in trajectory], tokens, errors


_USAGE_KEYS = (
    "input_tokens",
    "output_tokens",
    "cache_read_input_tokens",
    "cache_creation_input_tokens",
)


def _add_usage(acc: dict, usage: object) -> None:
    """Fold an Anthropic per-turn ``usage`` block into a running accumulator.

    Summing each turn's counts matches the cumulative accounting Claude Code
    reports in the terminal ``result`` event (every API call bills its full
    input), so the accumulator is a faithful stand-in when that event is lost.
    """
    if not isinstance(usage, dict):
        return
    for key in _USAGE_KEYS:
        val = usage.get(key)
        if isinstance(val, int):
            acc[key] = acc.get(key, 0) + val


def _usage_tokens(usage: dict) -> dict:
    """Normalize an Anthropic ``usage`` block to the canonical token buckets.

    ``input_tokens`` is already the uncached prompt; cache reads and writes stay
    separate buckets (writes bill at a premium). ``reasoning`` stays ``None`` —
    Anthropic bills thinking inside ``output_tokens``.
    """
    tokens = empty_tokens()
    inp = usage.get("input_tokens")
    out = usage.get("output_tokens")
    cache_read = usage.get("cache_read_input_tokens")
    cache_write = usage.get("cache_creation_input_tokens")
    tokens.update(
        input=inp if isinstance(inp, int) else None,
        cached=cache_read if isinstance(cache_read, int) else None,
        cache_write=cache_write if isinstance(cache_write, int) else None,
        output=out if isinstance(out, int) else None,
    )
    reported = [v for k, v in tokens.items() if k != "total" and v is not None]
    if reported:
        tokens["total"] = sum(reported)
    return tokens
