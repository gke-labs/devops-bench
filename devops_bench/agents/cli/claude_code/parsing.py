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
from collections.abc import Iterator

from devops_bench.agents.result import ToolCall

__all__ = ["parse_stream_json", "empty_tokens"]

# Canonical token buckets, harness-local until the shared schema lands
# (gke-labs/devops-bench#212). ``input`` is non-cached; ``total`` sums all buckets.
_TOKEN_BUCKETS = ("input", "cached", "cache_write", "reasoning", "output", "total")


def empty_tokens() -> dict:
    """Return the canonical token dict with every bucket ``None`` (unavailable)."""
    return dict.fromkeys(_TOKEN_BUCKETS, None)


def _int_or_none(val: object) -> int | None:
    """Return ``val`` if it is a real ``int`` (``bool`` rejected), else ``None``.

    Mirrors ``results/normalize._coerce_int``'s bool rejection so a stray JSON
    ``true`` in a usage field never surfaces as a token count.
    """
    return val if isinstance(val, int) and not isinstance(val, bool) else None


def _block_text(content: object) -> str | None:
    """Render a tool_result ``content`` payload to a string, or ``None``.

    Claude Code emits tool results either as a bare string or as a list of
    content blocks. Text blocks contribute their text; any other block (e.g. an
    ``image``) is JSON-encoded in place so nothing is dropped silently.
    """
    if content is None:
        return None
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        if not content:
            return None
        parts = [
            block["text"]
            if isinstance(block, dict) and isinstance(block.get("text"), str)
            else json.dumps(block, default=str)
            for block in content
        ]
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


def _iter_events(stdout: str) -> Iterator[tuple[object, str | None]]:
    """Yield ``(event, error)`` pairs from the stream, one populated per item.

    The stream is normally newline-delimited JSON, but a rebuffered or truncated
    pipe can concatenate several objects onto one physical line. Each line is
    decoded with ``raw_decode`` in a loop so every object is recovered rather
    than lost to a single ``Extra data`` error. A malformed remainder yields one
    error and the rest of that line is abandoned.
    """
    decoder = json.JSONDecoder()
    for lineno, raw in enumerate(stdout.splitlines(), start=1):
        line = raw.strip()
        if not line:
            continue
        idx = 0
        while idx < len(line):
            while idx < len(line) and line[idx].isspace():
                idx += 1
            if idx >= len(line):
                break
            try:
                event, idx = decoder.raw_decode(line, idx)
            except json.JSONDecodeError as exc:
                yield None, f"stream-json line {lineno} parse error: {exc}"
                break
            yield event, None


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

    The accumulated assistant ``text`` doubles as a fallback answer when no
    terminal ``result`` event arrives (a truncated pipe) or when it carries an
    empty answer (error subtypes emit ``""``). Likewise token usage falls back to
    the per-turn accumulator only when the terminal event reports no usage;
    per-turn usage is deduped by message id, since Claude Code repeats the same
    ``usage`` on every content-block envelope of one API message.

    Args:
        stdout: Raw process stdout, possibly empty.

    Returns:
        A ``(output, trajectory, tokens, errors)`` tuple. ``trajectory`` is a
        list of ``ToolCall.to_dict()`` mappings ordered as emitted.
    """
    text_parts: list[str] = []
    result_output: str | None = None
    tokens: dict = empty_tokens()
    result_usage_seen = False
    acc_usage: dict = {}
    seen_usage_ids: set[str] = set()
    errors: list[str] = []
    # Each id maps to a FIFO queue of pending calls: distinct tool_use blocks can
    # legitimately reuse an id, so results are matched in emission order rather
    # than the second call silently overwriting the first.
    pending: dict[str, list[ToolCall]] = {}
    trajectory: list[ToolCall] = []

    for event, error in _iter_events(stdout):
        if error is not None:
            errors.append(error)
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
            message = event.get("message")
            if not isinstance(message, dict):
                continue
            # Accumulate per-turn usage so a truncated stream (no terminal
            # ``result`` event) still yields token counts. Claude Code emits one
            # envelope per content block of a single API message, each repeating
            # the identical ``usage``, so count each message id only once.
            msg_id = message.get("id")
            if not (isinstance(msg_id, str) and msg_id in seen_usage_ids):
                if isinstance(msg_id, str):
                    seen_usage_ids.add(msg_id)
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
                        pending.setdefault(str(call_id), []).append(call)
        elif etype == "user":
            message = event.get("message")
            content = message.get("content") if isinstance(message, dict) else None
            if not isinstance(content, list):
                # A user message with a bare-string content echoes the prompt.
                continue
            for block in content:
                if not isinstance(block, dict) or block.get("type") != "tool_result":
                    continue
                call_id = block.get("tool_use_id") or ""
                queue = pending.get(str(call_id)) if call_id else None
                target = queue.pop(0) if queue else None
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
            # Guard against a later degenerate ``result`` (empty answer / no
            # usage) clobbering an earlier good one.
            tail = event.get("result")
            if isinstance(tail, str) and not result_output:
                result_output = tail
            usage = event.get("usage")
            if isinstance(usage, dict) and _has_usage(usage):
                tokens = _usage_tokens(usage)
                result_usage_seen = True
            subtype = event.get("subtype")
            if isinstance(subtype, str) and subtype.startswith("error_"):
                errors.append(f"stream-json result error: {subtype}")

    # ``result_output`` may be an empty string (error subtypes emit ``""``); fall
    # back to the accumulated assistant text so a real partial answer survives.
    output = result_output or "".join(text_parts)
    # Only fall back to summed per-turn usage when the terminal event reported no
    # recognized usage — a terminal event that reported genuine zeros is trusted.
    if not result_usage_seen and acc_usage:
        tokens = _usage_tokens(acc_usage)
    return output, [call.to_dict() for call in trajectory], tokens, errors


_USAGE_KEYS = (
    "input_tokens",
    "output_tokens",
    "cache_read_input_tokens",
    "cache_creation_input_tokens",
)


def _has_usage(usage: dict) -> bool:
    """True if ``usage`` carries at least one recognized integer count.

    Distinguishes a terminal ``result`` that reported genuine (possibly zero)
    counts from one that reported nothing, so the accumulator fallback only
    fires in the latter case.
    """
    return any(_int_or_none(usage.get(key)) is not None for key in _USAGE_KEYS)


def _add_usage(acc: dict, usage: object) -> None:
    """Fold an Anthropic per-turn ``usage`` block into a running accumulator.

    Callers dedupe by message id first, so each API message is added once. The
    terminal ``result`` usage is cumulative and authoritative; this accumulator
    is only a best-effort stand-in for a truncated stream that never emits it.
    """
    if not isinstance(usage, dict):
        return
    for key in _USAGE_KEYS:
        val = _int_or_none(usage.get(key))
        if val is not None:
            acc[key] = acc.get(key, 0) + val


def _usage_tokens(usage: dict) -> dict:
    """Normalize an Anthropic ``usage`` block to the canonical token buckets.

    ``input_tokens`` is already the uncached prompt; cache reads and writes stay
    separate buckets (writes bill at a premium). ``reasoning`` stays ``None`` —
    Anthropic bills thinking inside ``output_tokens``.
    """
    tokens = empty_tokens()
    tokens.update(
        input=_int_or_none(usage.get("input_tokens")),
        cached=_int_or_none(usage.get("cache_read_input_tokens")),
        cache_write=_int_or_none(usage.get("cache_creation_input_tokens")),
        output=_int_or_none(usage.get("output_tokens")),
    )
    reported = [v for k, v in tokens.items() if k != "total" and v is not None]
    if reported:
        tokens["total"] = sum(reported)
    return tokens
