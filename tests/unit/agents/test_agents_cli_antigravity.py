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

"""Unit tests for devops_bench.agents.cli.antigravity."""

from __future__ import annotations

import json
import pathlib
from types import SimpleNamespace
from unittest import mock

from devops_bench.agents import base as agents_base
from devops_bench.agents import config as agents_config
from devops_bench.agents import result as agents_result
from devops_bench.agents import capabilities
from devops_bench.agents.cli.antigravity import agent as agy_mod
from devops_bench.agents.cli.antigravity import parsing
from devops_bench.core import subprocess as devops_subprocess


def _jsonl(*records: dict) -> str:
    """Render a list of records as a JSONL blob."""
    return "\n".join(json.dumps(record) for record in records) + "\n"


SAMPLE_SESSION = _jsonl(
    {"sessionId": "session-123"},
    {
        "id": "msg-1",
        "type": "user",
        "content": "List GKE clusters and get details of cluster-a",
    },
    {
        "id": "msg-2",
        "type": "gemini",
        "content": "",
        "toolCalls": [
            {
                "name": "mcp_gke_list_clusters",
                "args": {"project": "p1"},
                "result": [
                    {
                        "functionResponse": {
                            "name": "mcp_gke_list_clusters",
                            "response": {"output": "cluster-a, cluster-b"},
                        }
                    }
                ],
            }
        ],
        "tokens": {"input": 10, "output": 5},
    },
    {
        "id": "msg-3",
        "type": "gemini",
        "content": "I found cluster-a. Let me get its details.",
        "toolCalls": [
            {
                "name": "mcp_gke_get_cluster",
                "args": {"cluster": "cluster-a"},
                "result": [
                    {
                        "functionResponse": {
                            "name": "mcp_gke_get_cluster",
                            "response": {"output": "v1.30", "is_error": False},
                        }
                    }
                ],
            }
        ],
        "tokens": {"input": 15, "output": 8},
    },
    {
        "id": "msg-4",
        "type": "gemini",
        "content": "Done. Cluster-a is running v1.30.",
        "tokens": {"input": 20, "output": 10},
    },
)

SAMPLE_TRANSCRIPT = _jsonl(
    {
        "step_index": 0,
        "source": "USER_EXPLICIT",
        "type": "USER_INPUT",
        "status": "DONE",
        "content": "Configure redirect",
    },
    {
        "step_index": 2,
        "source": "MODEL",
        "type": "PLANNER_RESPONSE",
        "status": "DONE",
        "tool_calls": [
            {
                "name": "run_command",
                "args": {"CommandLine": "pwd"},
            }
        ],
    },
    {
        "step_index": 3,
        "source": "MODEL",
        "type": "RUN_COMMAND",
        "status": "DONE",
        "content": "/workspace",
    },
    {
        "step_index": 5,
        "source": "MODEL",
        "type": "PLANNER_RESPONSE",
        "status": "DONE",
        "content": "Done configuring redirect",
    },
)


def test_parse_session_jsonl_emits_canonical_trajectory():
    output, trajectory, tokens, errors = parsing.parse_session_jsonl(SAMPLE_SESSION)
    assert output == "I found cluster-a. Let me get its details.Done. Cluster-a is running v1.30."
    assert tokens == {"input": 45, "output": 23, "total": 68, "cached": 0}
    assert errors == []
    assert trajectory == [
        {
            "name": "mcp_gke_list_clusters",
            "args": {"project": "p1"},
            "result": "cluster-a, cluster-b",
            "status": "completed",
        },
        {
            "name": "mcp_gke_get_cluster",
            "args": {"cluster": "cluster-a"},
            "result": "v1.30",
            "status": "completed",
        },
    ]


def test_parse_session_jsonl_handles_rewinds():
    session_with_rewind = _jsonl(
        {"sessionId": "session-123"},
        {"id": "msg-1", "type": "user", "content": "hello"},
        {
            "id": "msg-2",
            "type": "gemini",
            "content": "thought 1",
            "toolCalls": [{"name": "tool1", "args": {}}],
        },
        # Rewind back to msg-1 (effectively discarding msg-2)
        {"$rewindTo": "msg-1"},
        {
            "id": "msg-3",
            "type": "gemini",
            "content": "thought 2",
            "toolCalls": [{"name": "tool2", "args": {}, "result": "ok"}],
        },
    )
    output, trajectory, _tokens, errors = parsing.parse_session_jsonl(session_with_rewind)
    assert output == "thought 2"
    assert errors == []
    assert len(trajectory) == 1
    assert trajectory[0]["name"] == "tool2"


def test_parse_session_jsonl_handles_tool_errors():
    session_with_error = _jsonl(
        {
            "id": "msg-1",
            "type": "gemini",
            "toolCalls": [
                {
                    "name": "fail_tool",
                    "args": {},
                    "result": [
                        {
                            "functionResponse": {
                                "name": "fail_tool",
                                "response": {"output": "permission denied", "is_error": True},
                            }
                        }
                    ],
                }
            ],
        }
    )
    _, trajectory, _, _ = parsing.parse_session_jsonl(session_with_error)
    assert trajectory[0]["status"] == "error"
    assert trajectory[0]["result"] == "permission denied"


def test_parse_transcript_jsonl():
    output, trajectory, tokens, errors = parsing.parse_session_jsonl(SAMPLE_TRANSCRIPT)
    assert output == "Done configuring redirect"
    assert errors == []
    assert trajectory == [
        {
            "name": "run_command",
            "args": {"CommandLine": "pwd"},
            "result": "/workspace",
            "status": "completed",
        }
    ]


def test_build_settings_renders_mcp_and_model():
    mcp = capabilities.McpBinding(name="gke", command=("gke-mcp", "run"))
    settings = agy_mod._build_settings(
        (mcp,), "google/gemini-3.5-flash", "my-project", "us-east1"
    )
    
    assert settings["experimental"]["skills"] is True
    assert settings["modelConfigs"]["defaultModel"] == "gemini-3.5-flash"
    assert settings["mcpServers"]["gke"] == {
        "command": "gke-mcp",
        "args": ["run"],
    }
    assert settings["gcp"] == {
        "project": "my-project",
        "location": "us-east1",
    }


def test_build_env_sets_auth_and_presets():
    config = agents_config.AgentConfig(
        model="gemini-3.5-flash",
        api_key="secret-key",
    )
    with mock.patch.dict("os.environ", {"GOOGLE_CLOUD_PROJECT": "my-project"}):
        env = agy_mod._build_env(config)
        
    assert "HOME" not in env  # HOME must not be overridden
    assert env["GEMINI_CLI_TRUST_WORKSPACE"] == "true"
    assert env["GEMINI_API_KEY"] == "secret-key"
    assert env["GOOGLE_API_KEY"] == "secret-key"
    assert env["GOOGLE_CLOUD_PROJECT"] == "my-project"
    assert env["OTEL_SDK_DISABLED"] == "true"


@mock.patch.object(pathlib.Path, "home")
@mock.patch.object(devops_subprocess, "run")
def test_agy_cli_agent_execute_flow(mock_run, mock_home, tmp_path):
    # Mock Path.home() to return a temp directory to avoid polluting real HOME
    mock_home.return_value = tmp_path
    
    mock_run.return_value = SimpleNamespace(
        args=["agy"],
        returncode=0,
        stdout="Success",
        stderr="",
    )
    
    # Mock the session file writing that agy would do in the mocked HOME
    def side_effect(*args, **kwargs):
        cwd = kwargs.get("cwd") or tmp_path
        root_dir = cwd / ".gemini" / "antigravity-cli"
        conv_dir = root_dir / "conversations"
        conv_dir.mkdir(parents=True, exist_ok=True)
        uuid = "test-uuid-123"
        (conv_dir / f"{uuid}.db").write_text("", encoding="utf-8")
        
        transcript_dir = root_dir / "brain" / uuid / ".system_generated" / "logs"
        transcript_dir.mkdir(parents=True, exist_ok=True)
        (transcript_dir / "transcript.jsonl").write_text(SAMPLE_SESSION, encoding="utf-8")
        return mock_run.return_value
    mock_run.side_effect = side_effect

    config = agents_config.AgentConfig(
        target="/bin/agy",
        model="gemini-3.5-flash",
        capabilities=capabilities.AllCapabilities(),
    )
    agent = agy_mod.AgyCliAgent(config)
    
    result = agent._execute("run task")
    
    assert result.output == "I found cluster-a. Let me get its details.Done. Cluster-a is running v1.30."
    assert len(result.trajectory) == 2
    assert result.errors == []
    assert mock_run.called
    
    # Verify argv
    args = mock_run.call_args[0][0]
    assert args[0] == "/bin/agy"
    assert "--dangerously-skip-permissions" in args
    assert "--prompt=run task" in args
    assert any(a.startswith("--gemini_dir=") for a in args)
