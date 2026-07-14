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
terminal ``result`` event.
"""

from __future__ import annotations

import json

from devops_bench.agents.result import ToolCall

__all__ = ["parse_stream_json"]


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
    | ``assistant`` | ``tool_use`` blocks → pending ToolCalls; ``text`` → output|
    | ``user``      | ``tool_result`` blocks matched to pending ToolCalls       |
    | ``result``    | terminal: authoritative answer, token usage, error subtype|

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
    tokens: dict = {}
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
        if etype == "assistant":
            content = (event.get("message") or {}).get("content")
            if not isinstance(content, list):
                continue
            for block in content:
                if not isinstance(block, dict):
                    continue
                btype = block.get("type")
                if btype == "text":
                    if isinstance(block.get("text"), str):
                        text_parts.append(block["text"])
                elif btype == "tool_use":
                    args = block.get("input")
                    call = ToolCall(
                        name=block.get("name", ""),
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
    return output, [call.to_dict() for call in trajectory], tokens, errors


def _usage_tokens(usage: dict) -> dict:
    """Normalize an Anthropic ``usage`` block to the row-normalizer shape.

    ``total`` is the sum of input/output when both are present; ``cached`` folds
    the cache-read and cache-creation counts together (either may be absent).
    """
    inp = usage.get("input_tokens")
    out = usage.get("output_tokens")
    total = inp + out if isinstance(inp, int) and isinstance(out, int) else None
    cache_read = usage.get("cache_read_input_tokens")
    cache_creation = usage.get("cache_creation_input_tokens")
    cached: int | None = None
    if isinstance(cache_read, int) or isinstance(cache_creation, int):
        cached = (cache_read or 0) + (cache_creation or 0)
    return {"input": inp, "output": out, "total": total, "cached": cached}
