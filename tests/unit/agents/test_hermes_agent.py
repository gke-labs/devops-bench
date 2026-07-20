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

"""Unit tests for devops_bench.agents.cli.hermes.agent."""

from __future__ import annotations

import os
from pathlib import Path
from unittest.mock import patch

import yaml

from devops_bench.agents.cli.hermes.agent import HermesAgent, _build_env
from devops_bench.agents.config import AgentConfig


def test_build_env():
    config = AgentConfig(
        provider="google",
        api_key="test-key",
        extra_env={"FOO": "BAR"},
    )
    env = _build_env(config)

    assert env.get("FOO") == "BAR"
    assert env.get("GEMINI_API_KEY") == "test-key"


@patch("os.path.exists")
def test_resolve_hermes_bin(mock_exists):
    # If target is provided, it should be used
    agent = HermesAgent(AgentConfig(target="/custom/bin/hermes"))
    assert agent._resolve_hermes_bin() == "/custom/bin/hermes"

    agent_no_target = HermesAgent(AgentConfig(target=None))

    # If candidate path exists, it should be used
    mock_exists.return_value = True
    assert agent_no_target._resolve_hermes_bin() == os.path.expanduser("~/.local/bin/hermes")

    # If candidate path doesn't exist, fall back to "hermes"
    mock_exists.return_value = False
    assert agent_no_target._resolve_hermes_bin() == "hermes"


def test_prepare_config(tmp_path: Path):
    agent = HermesAgent(AgentConfig())
    run_dir = tmp_path / "run"
    run_dir.mkdir()

    # We will patch build_mcp_servers and see if the dict is written correctly
    with patch("devops_bench.agents.cli.hermes.agent.build_mcp_servers") as mock_build_mcp:
        mock_build_mcp.return_value = {"test_server": {"command": "echo", "args": ["hello"]}}

        agent._prepare_config(run_dir, ())

        config_path = run_dir / "config.yaml"
        assert config_path.exists()

        with open(config_path) as f:
            data = yaml.safe_load(f)

        assert "mcp_servers" in data
        assert "test_server" in data["mcp_servers"]


def test_prepare_config_null_mcp_servers(tmp_path: Path):
    agent = HermesAgent(AgentConfig())
    run_dir = tmp_path / "run"
    run_dir.mkdir()

    config_path = run_dir / "config.yaml"
    with open(config_path, "w") as f:
        f.write("mcp_servers: null\n")

    with patch("devops_bench.agents.cli.hermes.agent.build_mcp_servers") as mock_build_mcp:
        mock_build_mcp.return_value = {"new_server": {"command": "echo"}}

        # Test safe dictionary unpacking handles the None value safely
        agent._prepare_config(run_dir, ())

        with open(config_path) as f:
            data = yaml.safe_load(f)

        assert data["mcp_servers"]["new_server"]["command"] == "echo"


def test_execute_reports_tokens_from_state_db(tmp_path: Path):
    """End-to-end wiring: _execute must surface state.db token counts on
    AgentResult.tokens (regression guard for the tokens= kwarg)."""
    import sqlite3
    from types import SimpleNamespace

    from devops_bench.agents.cli.hermes import agent as agent_mod

    def fake_run(cmd, check, timeout, extra_env):
        home = Path(extra_env["HERMES_HOME"])
        conn = sqlite3.connect(home / "state.db")
        conn.execute(
            "CREATE TABLE sessions (id TEXT PRIMARY KEY, started_at TIMESTAMP,"
            " input_tokens INTEGER, output_tokens INTEGER, reasoning_tokens INTEGER,"
            " cache_read_tokens INTEGER, cache_write_tokens INTEGER)"
        )
        conn.execute(
            "CREATE TABLE messages (id INTEGER PRIMARY KEY AUTOINCREMENT, session_id TEXT,"
            " role TEXT, content TEXT, tool_calls TEXT, tool_call_id TEXT, tool_name TEXT)"
        )
        conn.execute("INSERT INTO sessions VALUES ('s1', NULL, 2748, 11267, 152, 334987, 12000)")
        conn.commit()
        conn.close()
        return SimpleNamespace(returncode=0, stdout="done", stderr="")

    with patch.object(agent_mod, "devops_run", side_effect=fake_run):
        result = HermesAgent(AgentConfig(target="/bin/hermes")).run("hello")

    assert result.output == "done"
    assert result.tokens == {
        "input": 2748,
        "cached": 334987,
        "cache_write": 12000,
        "reasoning": 152,
        "output": 11267,
        "total": 2748 + 334987 + 12000 + 152 + 11267,
    }


def test_execute_binary_unavailable_reports_canonical_none_tokens(tmp_path: Path):
    from devops_bench.agents.cli.hermes import agent as agent_mod
    from devops_bench.agents.cli.hermes.parsing import empty_tokens

    with patch.object(agent_mod, "devops_run", side_effect=OSError("no such file")):
        result = HermesAgent(AgentConfig(target="/bin/hermes")).run("hello")

    assert result.has_errors()
    assert result.tokens == empty_tokens()
