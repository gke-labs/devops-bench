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

"""Unit tests for devops_bench.agents.cli.hermes.parsing."""

from __future__ import annotations

import json
import sqlite3
from pathlib import Path

import pytest

from devops_bench.agents.cli.hermes.parsing import (
    empty_tokens,
    extract_tokens_from_db,
    extract_trajectory_from_db,
)


@pytest.fixture
def test_db_path(tmp_path: Path) -> Path:
    """Fixture creating a temporary SQLite database path."""
    return tmp_path / "test_state.db"


def init_db_schema(db_path: Path) -> None:
    """Initialize the schema for the test state database."""
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    cursor.execute(
        """
        CREATE TABLE sessions (
            id TEXT PRIMARY KEY,
            started_at TIMESTAMP
        )
    """
    )
    cursor.execute(
        """
        CREATE TABLE messages (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            session_id TEXT,
            role TEXT,
            content TEXT,
            tool_calls TEXT,
            tool_call_id TEXT,
            tool_name TEXT
        )
    """
    )
    conn.commit()
    conn.close()


def test_parsing_no_db_file(test_db_path: Path):
    """Test behavior when the database file does not exist."""
    trajectory, errors = extract_trajectory_from_db(test_db_path)
    assert trajectory == []
    assert len(errors) == 1
    assert "State database not found" in errors[0]


def test_parsing_empty_db_no_tables(test_db_path: Path):
    """Test behavior when the database file exists but has no tables."""
    test_db_path.touch()
    trajectory, errors = extract_trajectory_from_db(test_db_path)
    assert trajectory == []
    assert len(errors) == 1
    assert "Database error: no such table: sessions" in errors[0]


def test_parsing_no_sessions(test_db_path: Path):
    """Test behavior when tables exist but no sessions are recorded."""
    init_db_schema(test_db_path)
    trajectory, errors = extract_trajectory_from_db(test_db_path)
    assert trajectory == []
    assert len(errors) == 1
    assert "No session found in state database" in errors[0]


def test_parsing_happy_path(test_db_path: Path):
    """Test successful trajectory extraction with valid data."""
    init_db_schema(test_db_path)

    conn = sqlite3.connect(test_db_path)
    cursor = conn.cursor()

    cursor.execute(
        "INSERT INTO sessions (id, started_at) VALUES ('session_1', '2026-07-09 12:00:00')"
    )

    cursor.execute(
        "INSERT INTO messages (session_id, role, content) VALUES ('session_1', 'user', 'Deploy app')"
    )

    tool_calls_json = json.dumps(
        [
            {
                "id": "call_1",
                "type": "function",
                "function": {
                    "name": "kubectl_apply",
                    "arguments": json.dumps({"manifest": "nginx.yaml"}),
                },
            }
        ]
    )
    cursor.execute(
        "INSERT INTO messages (session_id, role, tool_calls) VALUES ('session_1', 'assistant', ?)",
        (tool_calls_json,),
    )

    cursor.execute(
        "INSERT INTO messages (session_id, role, content, tool_call_id, tool_name) "
        "VALUES ('session_1', 'tool', 'Successfully applied', 'call_1', 'kubectl_apply')"
    )

    conn.commit()
    conn.close()

    trajectory, errors = extract_trajectory_from_db(test_db_path)
    assert errors == []
    assert len(trajectory) == 1

    tc = trajectory[0]
    assert tc["name"] == "kubectl_apply"
    assert tc["args"] == {"manifest": "nginx.yaml"}
    assert tc["status"] == "completed"
    assert tc["result"] == "Successfully applied"


def test_parsing_malformed_tool_calls_json(test_db_path: Path):
    """Test behavior when tool_calls column contains invalid JSON."""
    init_db_schema(test_db_path)
    conn = sqlite3.connect(test_db_path)
    cursor = conn.cursor()
    cursor.execute(
        "INSERT INTO sessions (id, started_at) VALUES ('session_1', '2026-07-09 12:00:00')"
    )
    cursor.execute(
        "INSERT INTO messages (session_id, role, tool_calls) VALUES ('session_1', 'assistant', '[invalid json')"
    )
    conn.commit()
    conn.close()

    trajectory, errors = extract_trajectory_from_db(test_db_path)
    assert trajectory == []
    assert len(errors) == 1
    assert "Failed to parse tool calls JSON" in errors[0]


def test_parsing_unknown_tool_call_id(test_db_path: Path):
    """Test behavior when a tool response arrives for an untracked call ID."""
    init_db_schema(test_db_path)
    conn = sqlite3.connect(test_db_path)
    cursor = conn.cursor()
    cursor.execute(
        "INSERT INTO sessions (id, started_at) VALUES ('session_1', '2026-07-09 12:00:00')"
    )

    cursor.execute(
        "INSERT INTO messages (session_id, role, content, tool_call_id, tool_name) "
        "VALUES ('session_1', 'tool', 'Some result', 'call_unknown', 'kubectl_delete')"
    )
    conn.commit()
    conn.close()

    trajectory, errors = extract_trajectory_from_db(test_db_path)
    assert len(errors) == 1
    assert "Found tool response for unknown tool_call_id: call_unknown" in errors[0]
    assert len(trajectory) == 1

    tc = trajectory[0]
    assert tc["name"] == "kubectl_delete"
    assert tc["args"] == {}
    assert tc["status"] == "completed"
    assert tc["result"] == "Some result"


def test_parsing_missing_tool_name(test_db_path: Path):
    """Test behavior when tool call name is completely missing from assistant message."""
    init_db_schema(test_db_path)
    conn = sqlite3.connect(test_db_path)
    cursor = conn.cursor()
    cursor.execute(
        "INSERT INTO sessions (id, started_at) VALUES ('session_1', '2026-07-09 12:00:00')"
    )

    # Insert assistant call without a function name
    tool_calls_json = json.dumps(
        [
            {
                "id": "call_1",
                "type": "function",
                "function": {"arguments": json.dumps({"manifest": "nginx.yaml"})},
            }
        ]
    )
    cursor.execute(
        "INSERT INTO messages (session_id, role, tool_calls) VALUES ('session_1', 'assistant', ?)",
        (tool_calls_json,),
    )
    conn.commit()
    conn.close()

    trajectory, errors = extract_trajectory_from_db(test_db_path)
    assert errors == []
    assert len(trajectory) == 1
    assert trajectory[0]["name"] == "unknown"


# -- extract_tokens_from_db ---------------------------------------------------


_TOKEN_COLUMNS = (
    "input_tokens",
    "output_tokens",
    "reasoning_tokens",
    "cache_read_tokens",
    "cache_write_tokens",
)


def init_db_schema_with_tokens(db_path: Path) -> None:
    """Extend the base schema with the token columns current Hermes writes."""
    init_db_schema(db_path)
    conn = sqlite3.connect(db_path)
    for column in _TOKEN_COLUMNS:
        conn.execute(f"ALTER TABLE sessions ADD COLUMN {column} INTEGER")
    conn.commit()
    conn.close()


def insert_session(db_path: Path, session_id: str, *counts) -> None:
    conn = sqlite3.connect(db_path)
    conn.execute(
        "INSERT INTO sessions (id, started_at, input_tokens, output_tokens,"
        " reasoning_tokens, cache_read_tokens, cache_write_tokens)"
        " VALUES (?, NULL, ?, ?, ?, ?, ?)",
        (session_id, *counts),
    )
    conn.commit()
    conn.close()


def test_empty_tokens_all_none():
    assert empty_tokens() == {
        "input": None,
        "cached": None,
        "cache_write": None,
        "reasoning": None,
        "output": None,
        "total": None,
    }


def test_extract_tokens_reads_session_counts(test_db_path: Path):
    init_db_schema_with_tokens(test_db_path)
    insert_session(test_db_path, "s1", 2748, 11267, 152, 334987, 12000)

    assert extract_tokens_from_db(test_db_path) == {
        "input": 2748,
        "cached": 334987,
        "cache_write": 12000,
        "reasoning": 152,
        "output": 11267,
        "total": 2748 + 334987 + 12000 + 152 + 11267,
    }


def test_extract_tokens_sums_across_sessions(test_db_path: Path):
    # The DB is per-run; a run may write several session rows (compaction,
    # sub-sessions), and session ids need not sort chronologically.
    init_db_schema_with_tokens(test_db_path)
    insert_session(test_db_path, "f3a9-uuid", 1, 1, 0, 0, 0)
    insert_session(test_db_path, "0b21-uuid", 500, 40, 5, 900, 30)

    tokens = extract_tokens_from_db(test_db_path)
    assert tokens["input"] == 501
    assert tokens["output"] == 41
    assert tokens["cached"] == 900


def test_extract_tokens_coerces_real_values(test_db_path: Path):
    # SQLite columns are dynamically typed; a REAL count must not be dropped.
    init_db_schema_with_tokens(test_db_path)
    insert_session(test_db_path, "s1", 100, 7, 0, 0, 12000.0)

    tokens = extract_tokens_from_db(test_db_path)
    assert tokens["cache_write"] == 12000
    assert tokens["input"] == 100


def test_extract_tokens_null_columns_stay_none(test_db_path: Path):
    # NULL counts (e.g. a crashed run) must surface as None, not 0.
    init_db_schema_with_tokens(test_db_path)
    insert_session(test_db_path, "s1", 100, 7, None, None, None)

    tokens = extract_tokens_from_db(test_db_path)
    assert tokens["input"] == 100
    assert tokens["output"] == 7
    assert tokens["reasoning"] is None
    assert tokens["cached"] is None
    assert tokens["cache_write"] is None
    assert tokens["total"] == 107


def test_extract_tokens_old_schema_without_token_columns(test_db_path: Path):
    # Older Hermes schemas lack the token columns entirely -> all-None.
    init_db_schema(test_db_path)
    assert extract_tokens_from_db(test_db_path) == empty_tokens()


def test_extract_tokens_missing_or_invalid_db(test_db_path: Path):
    assert extract_tokens_from_db(test_db_path) == empty_tokens()  # no file
    test_db_path.write_text("not a database")
    assert extract_tokens_from_db(test_db_path) == empty_tokens()
