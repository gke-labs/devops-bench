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

"""Parser for Antigravity CLI session JSONL logs.

Reconstructs the final message history by respecting ``$rewindTo`` and ``$set``
control records, then extracts the canonical tool call trajectory, final output,
and aggregated token usage.
"""

from __future__ import annotations

import json
from devops_bench import core
from devops_bench.agents import result as agents_result

__all__ = ["parse_session_jsonl"]

_log = core.get_logger("agents.cli.antigravity.parsing")


def _extract_text(content: object) -> str:
    """Extract plain text from a message content field."""
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts = []
        for part in content:
            if isinstance(part, dict) and isinstance(part.get("text"), str):
                parts.append(part["text"])
            elif isinstance(part, str):
                parts.append(part)
        return "".join(parts)
    return ""


def _parse_tool_result(result_list: list) -> tuple[str, str]:
    """Parse a tool result list into a (result_text, status) tuple."""
    text_parts = []
    status = "completed"
    
    for item in result_list:
        if not isinstance(item, dict):
            continue
        
        # Check for functionResponse structure
        func_resp = item.get("functionResponse")
        if isinstance(func_resp, dict):
            response = func_resp.get("response")
            if isinstance(response, dict):
                # Look for explicit output
                output = response.get("output")
                if output is not None:
                    text_parts.append(output if isinstance(output, str) else json.dumps(output))
                
                # Check for error indicators
                if response.get("error") or response.get("is_error") or response.get("failed"):
                    status = "error"
            else:
                text_parts.append(json.dumps(func_resp))
        else:
            # Fallback for other result shapes
            text_parts.append(json.dumps(item))
            
    return "\n".join(text_parts), status


def parse_transcript_jsonl(jsonl_text: str) -> tuple[str, list[dict], dict, list[str]]:
    """Parse Antigravity CLI transcript.jsonl into the canonical shape."""
    errors: list[str] = []
    trajectory: list[dict] = []
    output_parts: list[str] = []
    aggregated_tokens = {"input": 0, "output": 0, "total": 0, "cached": 0}
    
    pending_tool_calls: list[dict] = []
    
    for lineno, raw in enumerate(jsonl_text.splitlines(), start=1):
        line = raw.strip()
        if not line:
            continue
        try:
            record = json.loads(line)
        except json.JSONDecodeError as exc:
            errors.append(f"transcript line {lineno} parse error: {exc}")
            continue
        if not isinstance(record, dict):
            continue
            
        stype = record.get("type")
        source = record.get("source")
        
        # Aggregate tokens if present
        if "tokens" in record and isinstance(record["tokens"], dict):
            t = record["tokens"]
            aggregated_tokens["input"] += t.get("input", 0)
            aggregated_tokens["output"] += t.get("output", 0)
            aggregated_tokens["cached"] += t.get("cached", 0)
            
        if source == "MODEL":
            if stype == "PLANNER_RESPONSE":
                # If it has content, it's a text response
                if "content" in record and record["content"]:
                    output_parts.append(record["content"])
                
                # If it has tool calls, queue them
                if "tool_calls" in record and isinstance(record["tool_calls"], list):
                    for tc in record["tool_calls"]:
                        if isinstance(tc, dict):
                            pending_tool_calls.append({
                                "name": tc.get("name", ""),
                                "args": tc.get("args") or {},
                                "result": None,
                                "status": "called"
                            })
            else:
                # This is a tool execution result!
                # Match it with the first pending tool call
                if pending_tool_calls:
                    tc = pending_tool_calls.pop(0)
                    tc["result"] = record.get("content") or record.get("error") or ""
                    tc["status"] = "completed" if record.get("status") == "DONE" else "error"
                    trajectory.append(tc)
                else:
                    # Ignore tool results that don't match any pending call
                    pass
        elif stype == "ERROR_MESSAGE":
            if record.get("content"):
                errors.append(f"System error: {record['content']}")
                
    # If there are still pending tool calls at the end, they were probably interrupted
    for tc in pending_tool_calls:
        tc["status"] = "interrupted"
        trajectory.append(tc)
        
    aggregated_tokens["total"] = aggregated_tokens["input"] + aggregated_tokens["output"]
    output = "".join(output_parts)
    return output, trajectory, aggregated_tokens, errors


def parse_session_jsonl(jsonl_text: str) -> tuple[str, list[dict], dict, list[str]]:
    """Parse Antigravity CLI session JSONL into the canonical shape.

    Automatically detects if the format is the old session log or the new
    transcript log and delegates accordingly.
    """
    if not jsonl_text:
        return "", [], {"input": 0, "output": 0, "total": 0, "cached": 0}, ["Empty session log"]

    # Detect format by looking at the first non-empty line
    first_line = ""
    for line in jsonl_text.splitlines():
        if line.strip():
            first_line = line.strip()
            break

    if "step_index" in first_line:
        return parse_transcript_jsonl(jsonl_text)

    # Fallback to old parser
    return _parse_old_session_jsonl(jsonl_text)


def _parse_old_session_jsonl(jsonl_text: str) -> tuple[str, list[dict], dict, list[str]]:
    """Old parser for Antigravity CLI session JSONL logs."""
    errors: list[str] = []
    message_ids: list[str] = []
    messages_by_id: dict[str, dict] = {}
    metadata: dict = {}

    # 1. Reconstruct final history by applying rewinds
    for lineno, raw in enumerate(jsonl_text.splitlines(), start=1):
        line = raw.strip()
        if not line:
            continue
        try:
            record = json.loads(line)
        except json.JSONDecodeError as exc:
            errors.append(f"session line {lineno} parse error: {exc}")
            continue
        if not isinstance(record, dict):
            continue

        if "$rewindTo" in record:
            rewind_id = str(record["$rewindTo"])
            if rewind_id in message_ids:
                idx = message_ids.index(rewind_id)
                # Keep everything up to the rewind target, discard the rest
                for removed in message_ids[idx + 1:]:
                    messages_by_id.pop(removed, None)
                del message_ids[idx + 1:]
            else:
                # If target not found, clear everything (defensive)
                message_ids.clear()
                messages_by_id.clear()
        elif "$set" in record and isinstance(record["$set"], dict):
            metadata.update(record["$set"])
        elif "id" in record and "type" in record:
            mid = str(record["id"])
            if mid not in messages_by_id:
                message_ids.append(mid)
            messages_by_id[mid] = record
        elif "sessionId" in record:
            for k, v in record.items():
                if k != "messages":
                    metadata[k] = v

    # 2. Extract trajectory, output, and tokens from the reconstructed messages
    trajectory: list[core.ToolCall] = []
    output_parts: list[str] = []
    aggregated_tokens = {"input": 0, "output": 0, "total": 0, "cached": 0}

    for mid in message_ids:
        msg = messages_by_id[mid]
        mtype = msg.get("type")
        
        if mtype in ("gemini", "agent", "assistant"):
            # Extract text output
            content_text = _extract_text(msg.get("content", ""))
            if content_text:
                output_parts.append(content_text)
                
            # Extract tool calls
            tool_calls_data = msg.get("toolCalls")
            if isinstance(tool_calls_data, list):
                for tc in tool_calls_data:
                    if not isinstance(tc, dict):
                        continue
                    
                    name = tc.get("name", "")
                    args = tc.get("args") or tc.get("arguments") or {}
                    
                    # Parse result and status
                    result_text = None
                    status = "called"
                    result_data = tc.get("result")
                    
                    if isinstance(result_data, list):
                        result_text, status = _parse_tool_result(result_data)
                    elif result_data is not None:
                        result_text = result_data if isinstance(result_data, str) else json.dumps(result_data)
                        status = "completed"
                        
                    call = agents_result.ToolCall(
                        name=name,
                        args=args if isinstance(args, dict) else {},
                        result=result_text,
                        status=status,
                    )
                    trajectory.append(call)
            
            # Aggregate tokens
            msg_tokens = msg.get("tokens")
            if isinstance(msg_tokens, dict):
                aggregated_tokens["input"] += msg_tokens.get("input", 0)
                output_cnt = msg_tokens.get("output", 0)
                thoughts_cnt = msg_tokens.get("thoughts", 0)
                tool_cnt = msg_tokens.get("tool", 0)
                aggregated_tokens["output"] += (output_cnt + thoughts_cnt + tool_cnt)
                aggregated_tokens["cached"] += msg_tokens.get("cached", 0)

    aggregated_tokens["total"] = aggregated_tokens["input"] + aggregated_tokens["output"]
    
    output = "".join(output_parts)
    return output, [call.to_dict() for call in trajectory], aggregated_tokens, errors
