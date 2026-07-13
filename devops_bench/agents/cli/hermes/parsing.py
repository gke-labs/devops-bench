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

"""Trajectory parsing and extraction utilities for Hermes Agent."""

from __future__ import annotations

import json
import sqlite3
from pathlib import Path

from devops_bench.agents.result import ToolCall


def extract_trajectory_from_db(db_path: Path) -> tuple[list[dict], list[str]]:
    """Extract trajectory (tool calls and results) from Hermes state.db."""
    errors: list[str] = []
    trajectory: list[dict] = []

    if not db_path.exists():
        errors.append(f"State database not found at {db_path}")
        return [], errors

    try:
        conn = sqlite3.connect(db_path)
        try:
            cursor = conn.cursor()

            cursor.execute("SELECT id FROM sessions ORDER BY id DESC LIMIT 1")
            row = cursor.fetchone()
            if not row:
                errors.append("No session found in state database")
                return [], errors
            session_id = row[0]

            cursor.execute(
                "SELECT role, content, tool_calls, tool_call_id, tool_name FROM messages WHERE session_id = ? ORDER BY id",
                (session_id,),
            )
            messages = cursor.fetchall()
        finally:
            conn.close()
    except sqlite3.Error as exc:
        errors.append(f"Database error: {exc}")
        return [], errors

    tool_calls_map = {}  # map tool_call_id to ToolCall object

    for role, content, tool_calls_json, tool_call_id, tool_name in messages:
        if role == "assistant" and tool_calls_json:
            try:
                tool_calls_list = json.loads(tool_calls_json)
                for tc_data in tool_calls_list:
                    tc_id = tc_data.get("id")
                    func_data = tc_data.get("function", {})
                    name = func_data.get("name") or "unknown"
                    args_str = func_data.get("arguments", "{}")
                    try:
                        args = json.loads(args_str)
                    except json.JSONDecodeError:
                        args = {"raw_args": args_str}

                    tc = ToolCall(name=name, args=args, status="called")
                    trajectory.append(tc.to_dict())
                    if tc_id:
                        tool_calls_map[tc_id] = trajectory[-1]
            except json.JSONDecodeError as exc:
                errors.append(f"Failed to parse tool calls JSON: {exc}")
        elif role == "tool" and tool_call_id:
            if tool_call_id in tool_calls_map:
                tc_dict = tool_calls_map[tool_call_id]
                tc_dict["result"] = content
                tc_dict["status"] = "completed"
            else:
                name = tool_name or "unknown"
                tc = ToolCall(name=name, args={}, result=content, status="completed")
                trajectory.append(tc.to_dict())
                errors.append(f"Found tool response for unknown tool_call_id: {tool_call_id}")

    return trajectory, errors
