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

"""Unit tests for devops_bench.agents.cli.claude_code."""

from __future__ import annotations

import json
import os
import tempfile
from types import SimpleNamespace

import pytest

from devops_bench.agents import AGENTS, AgentConfig
from devops_bench.agents.capabilities import (
    AgentRules,
    AllCapabilities,
    McpBinding,
    SkillBinding,
    SupportsMcp,
    SupportsRules,
    SupportsSkills,
)
from devops_bench.agents.cli.claude_code import ClaudeCodeAgent, parse_stream_json
from devops_bench.agents.cli.claude_code import agent as claude_mod
from devops_bench.agents.cli.claude_code.agent import _build_argv, _build_env
from devops_bench.core.errors import ConfigError, SubprocessError


def _stream(*events: dict) -> str:
    """Render a list of events as a stream-json stdout blob."""
    return "\n".join(json.dumps(event) for event in events) + "\n"


def _assistant(*blocks: dict) -> dict:
    return {"type": "assistant", "message": {"content": list(blocks)}}


def _user(*blocks: dict) -> dict:
    return {"type": "user", "message": {"content": list(blocks)}}


SAMPLE_STREAM = _stream(
    {"type": "system", "subtype": "init", "session_id": "abc-123", "model": "claude-opus-4-8"},
    _assistant(
        {
            "type": "tool_use",
            "id": "call-1",
            "name": "mcp__gke__list_clusters",
            "input": {"project": "p1"},
        }
    ),
    _user({"type": "tool_result", "tool_use_id": "call-1", "content": "cluster-a, cluster-b"}),
    _assistant(
        {"type": "tool_use", "id": "call-2", "name": "mcp__gke__get_cluster", "input": {"c": "a"}}
    ),
    _user(
        {
            "type": "tool_result",
            "tool_use_id": "call-2",
            "content": [{"type": "text", "text": "v1.30"}],
            "is_error": False,
        }
    ),
    _assistant({"type": "text", "text": "Done."}),
    {
        "type": "result",
        "subtype": "success",
        "result": "Done.",
        "usage": {"input_tokens": 10, "output_tokens": 20, "cache_read_input_tokens": 5},
    },
)


# ---------------------------------------------------------------------------
# Parser
# ---------------------------------------------------------------------------


def test_parse_stream_json_emits_canonical_trajectory():
    output, trajectory, tokens, errors = parse_stream_json(SAMPLE_STREAM)
    assert output == "Done."
    assert errors == []
    assert tokens == {"input": 10, "output": 20, "total": 30, "cached": 5}
    assert trajectory == [
        {
            "name": "gke__list_clusters",
            "args": {"project": "p1"},
            "result": "cluster-a, cluster-b",
            "status": "completed",
        },
        {
            "name": "gke__get_cluster",
            "args": {"c": "a"},
            "result": "v1.30",
            "status": "completed",
        },
    ]


def test_parse_stream_json_marks_failed_tool_results_as_error_status():
    blob = _stream(
        _assistant({"type": "tool_use", "id": "c", "name": "x", "input": {}}),
        _user({"type": "tool_result", "tool_use_id": "c", "content": "oops", "is_error": True}),
    )
    _output, trajectory, _tokens, errors = parse_stream_json(blob)
    assert errors == []
    assert trajectory[0]["status"] == "error"


def test_parse_stream_json_records_unmatched_tool_results():
    blob = _stream(_user({"type": "tool_result", "tool_use_id": "ghost", "content": "?"}))
    _output, trajectory, _tokens, errors = parse_stream_json(blob)
    assert trajectory == []
    assert any("without matching tool_use" in msg for msg in errors)


def test_parse_stream_json_records_json_decode_errors_on_errors_list():
    blob = "{not json}\n" + json.dumps({"type": "result", "result": "ok"}) + "\n"
    output, trajectory, _tokens, errors = parse_stream_json(blob)
    assert output == "ok"
    assert trajectory == []
    assert len(errors) == 1
    assert "parse error" in errors[0]


def test_parse_stream_json_records_error_result_subtype():
    blob = _stream({"type": "result", "subtype": "error_max_turns", "result": ""})
    _output, _trajectory, _tokens, errors = parse_stream_json(blob)
    assert errors == ["stream-json result error: error_max_turns"]


def test_parse_stream_json_empty_input_returns_empty():
    assert parse_stream_json("") == ("", [], {}, [])


def test_parse_stream_json_flags_failed_mcp_server_at_init():
    """A failed MCP server in the init event surfaces on ``errors`` — a
    tool-less-but-exit-0 run must not look clean."""
    blob = _stream(
        {
            "type": "system",
            "subtype": "init",
            "mcp_servers": [
                {"name": "gke", "status": "connected"},
                {"name": "broken", "status": "failed"},
            ],
        },
        {"type": "result", "subtype": "success", "result": "ok"},
    )
    output, _trajectory, _tokens, errors = parse_stream_json(blob)
    assert output == "ok"
    assert any("broken" in e and "failed" in e for e in errors)
    assert not any("gke" in e for e in errors)


def test_parse_stream_json_ignores_transient_pending_mcp_status_at_init():
    """A ``pending`` MCP status at the init snapshot is transient — the server
    (e.g. gke-mcp) connects moments later and serves tools normally — so it must
    NOT surface an error, which would otherwise flip the run-level ``validated``
    gate to ``False`` on a fully working MCP run."""
    blob = _stream(
        {
            "type": "system",
            "subtype": "init",
            "mcp_servers": [{"name": "gke", "status": "pending"}],
        },
        _assistant(
            {"type": "tool_use", "id": "t1", "name": "mcp__gke__list_clusters", "input": {}}
        ),
        _user({"type": "tool_result", "tool_use_id": "t1", "content": "cluster-a"}),
        {"type": "result", "subtype": "success", "result": "ok"},
    )
    output, trajectory, _tokens, errors = parse_stream_json(blob)
    assert output == "ok"
    assert errors == []
    assert trajectory[0]["status"] == "completed"


def test_parse_stream_json_strips_mcp_client_prefix_from_tool_names():
    """Claude Code names MCP tools ``mcp__<server>__<tool>``; the parser drops the
    literal ``mcp__`` prefix so names match the pipeline's ``<server>__<tool>``
    convention (which the metrics canonicalizer reduces to the bare tool name).
    Built-in tools keep their names."""
    blob = _stream(
        _assistant(
            {"type": "tool_use", "id": "a", "name": "mcp__default__generate_manifest", "input": {}},
            {"type": "tool_use", "id": "b", "name": "Bash", "input": {"command": "ls"}},
        ),
    )
    _output, trajectory, _tokens, _errors = parse_stream_json(blob)
    assert [t["name"] for t in trajectory] == ["default__generate_manifest", "Bash"]


def test_parse_stream_json_drops_thinking_blocks():
    """``thinking`` / ``redacted_thinking`` blocks are dropped so the trajectory
    is tool-calls-only, matching the shape the other CLI harnesses emit. Only the
    tool call survives; the surrounding reasoning leaves no trajectory step."""
    blob = _stream(
        _assistant(
            {"type": "thinking", "thinking": "let me plan", "signature": "sig"},
            {"type": "tool_use", "id": "c1", "name": "Bash", "input": {"command": "ls"}},
            {"type": "redacted_thinking", "data": "enc"},
        ),
        _user({"type": "tool_result", "tool_use_id": "c1", "content": "ok"}),
    )
    _output, trajectory, _tokens, errors = parse_stream_json(blob)
    assert errors == []
    assert trajectory == [
        {"name": "Bash", "args": {"command": "ls"}, "result": "ok", "status": "completed"},
    ]


def test_parse_stream_json_keeps_pending_tool_use_as_called():
    """A tool_use with no matching tool_result (timeout-truncated stream) stays
    in the trajectory with status ``called`` and a ``None`` result."""
    blob = _stream(_assistant({"type": "tool_use", "id": "c1", "name": "do", "input": {"k": "v"}}))
    _output, trajectory, _tokens, errors = parse_stream_json(blob)
    assert trajectory == [{"name": "do", "args": {"k": "v"}, "result": None, "status": "called"}]
    assert errors == []


def test_parse_stream_json_falls_back_to_assistant_text_without_result_event():
    """A truncated stream (no terminal ``result``) still yields the answer from
    the accumulated assistant ``text`` blocks."""
    blob = _stream(
        _assistant({"type": "text", "text": "partial "}),
        _assistant({"type": "text", "text": "answer"}),
    )
    output, _trajectory, tokens, errors = parse_stream_json(blob)
    assert output == "partial answer"
    assert tokens == {}
    assert errors == []


def test_parse_stream_json_falls_back_to_accumulated_usage_without_result_event():
    """A truncated stream (no terminal ``result``) still yields token counts,
    summed from the per-turn assistant ``usage``."""
    blob = _stream(
        {
            "type": "assistant",
            "message": {
                "content": [{"type": "text", "text": "a"}],
                "usage": {"input_tokens": 10, "output_tokens": 5, "cache_read_input_tokens": 2},
            },
        },
        {
            "type": "assistant",
            "message": {
                "content": [{"type": "text", "text": "b"}],
                "usage": {
                    "input_tokens": 20,
                    "output_tokens": 7,
                    "cache_creation_input_tokens": 3,
                },
            },
        },
    )
    output, _trajectory, tokens, errors = parse_stream_json(blob)
    assert output == "ab"
    assert tokens == {"input": 30, "output": 12, "total": 42, "cached": 5}
    assert errors == []


def test_parse_stream_json_result_usage_wins_over_accumulated():
    """When the terminal ``result`` carries usage it is authoritative — the
    accumulated per-turn usage is not added on top."""
    blob = _stream(
        {
            "type": "assistant",
            "message": {
                "content": [{"type": "text", "text": "x"}],
                "usage": {"input_tokens": 999, "output_tokens": 999},
            },
        },
        {
            "type": "result",
            "subtype": "success",
            "result": "x",
            "usage": {"input_tokens": 10, "output_tokens": 20},
        },
    )
    _output, _trajectory, tokens, _errors = parse_stream_json(blob)
    assert tokens == {"input": 10, "output": 20, "total": 30, "cached": None}


def test_parse_stream_json_falls_back_when_result_usage_degenerate():
    """A terminal ``result`` whose ``usage`` carries no recognized counts must
    not shadow the accumulated per-turn usage — the all-None result is treated
    as absent so the summed per-turn counts survive."""
    blob = _stream(
        {
            "type": "assistant",
            "message": {
                "content": [{"type": "text", "text": "x"}],
                "usage": {"input_tokens": 15, "output_tokens": 4},
            },
        },
        {"type": "result", "subtype": "success", "result": "x", "usage": {}},
    )
    _output, _trajectory, tokens, _errors = parse_stream_json(blob)
    assert tokens == {"input": 15, "output": 4, "total": 19, "cached": None}


def test_parse_stream_json_result_string_is_authoritative_over_text():
    """When a ``result`` event is present its string wins over assistant text
    (which merely duplicates it) — no double-counting."""
    blob = _stream(
        _assistant({"type": "text", "text": "Done."}),
        {"type": "result", "subtype": "success", "result": "Done."},
    )
    output, _trajectory, _tokens, _errors = parse_stream_json(blob)
    assert output == "Done."


# ---------------------------------------------------------------------------
# argv
# ---------------------------------------------------------------------------


def test_build_argv_base_flags_and_prompt_via_argv():
    argv = _build_argv("/bin/claude", "hi", model=None, max_turns=None, mcp_config_path=None)
    assert argv[0] == "/bin/claude"
    # Prompt is an argv value (never a shell string), right after ``-p``.
    assert argv[1:3] == ["-p", "hi"]
    assert "--output-format" in argv and "stream-json" in argv
    assert "--verbose" in argv  # required for stream-json under -p
    assert "--dangerously-skip-permissions" in argv
    # Optional flags absent when unset.
    assert "--model" not in argv
    assert "--max-turns" not in argv
    assert "--mcp-config" not in argv
    assert "--strict-mcp-config" not in argv
    # This harness never emits an allowlist (bare names can't match mcp__ tools).
    assert "--allowedTools" not in argv and "--allowed-tools" not in argv


def test_build_argv_threads_model_and_max_turns_when_set():
    argv = _build_argv(
        "/bin/claude", "hi", model="claude-opus-4-8", max_turns=7, mcp_config_path=None
    )
    assert argv[argv.index("--model") + 1] == "claude-opus-4-8"
    assert argv[argv.index("--max-turns") + 1] == "7"


def test_build_argv_adds_strict_mcp_config_only_when_config_bound():
    argv = _build_argv(
        "/bin/claude", "hi", model=None, max_turns=None, mcp_config_path="/w/.claude/mcp.json"
    )
    assert argv[argv.index("--mcp-config") + 1] == "/w/.claude/mcp.json"
    assert "--strict-mcp-config" in argv


# ---------------------------------------------------------------------------
# env
# ---------------------------------------------------------------------------


def test_build_env_threads_api_key_into_anthropic_var():
    env = _build_env(AgentConfig(api_key="sk-abc"), config_dir=None)
    assert env["ANTHROPIC_API_KEY"] == "sk-abc"
    assert env["CLAUDE_CODE_DISABLE_NONESSENTIAL_TRAFFIC"] == "1"
    assert env["DISABLE_AUTOUPDATER"] == "1"


def test_build_env_keyless_vertex_sets_switch_and_maps_project_region(monkeypatch):
    monkeypatch.setenv("GCP_PROJECT_ID", "proj-42")
    monkeypatch.setenv("GCP_VERTEX_LOCATION", "us-east5")
    env = _build_env(AgentConfig(provider="anthropic-vertex"), config_dir=None)
    assert env["CLAUDE_CODE_USE_VERTEX"] == "1"
    assert env["ANTHROPIC_VERTEX_PROJECT_ID"] == "proj-42"
    assert env["CLOUD_ML_REGION"] == "us-east5"
    # Keyless: no API-key var written even absent an explicit api_key.
    assert "ANTHROPIC_API_KEY" not in env


def test_build_env_vertex_region_defaults_to_global(monkeypatch):
    monkeypatch.delenv("GCP_VERTEX_LOCATION", raising=False)
    monkeypatch.setenv("GCP_PROJECT_ID", "proj-42")
    env = _build_env(AgentConfig(provider="anthropic-vertex"), config_dir=None)
    assert env["CLOUD_ML_REGION"] == "global"


def test_build_env_keyless_bedrock_sets_switch():
    env = _build_env(AgentConfig(provider="anthropic-bedrock"), config_dir=None)
    assert env["CLAUDE_CODE_USE_BEDROCK"] == "1"
    assert "ANTHROPIC_API_KEY" not in env


def test_build_env_unknown_provider_raises_even_when_keyless():
    with pytest.raises(ConfigError):
        _build_env(AgentConfig(provider="anthropi"), config_dir=None)


def test_build_env_extra_env_wins_over_computed_vars():
    cfg = AgentConfig(api_key="sk-abc", extra_env={"ANTHROPIC_API_KEY": "override", "X": "y"})
    env = _build_env(cfg, config_dir=None)
    assert env["ANTHROPIC_API_KEY"] == "override"
    assert env["X"] == "y"


def test_build_env_sets_config_dir_when_provided():
    env = _build_env(AgentConfig(), config_dir="/tmp/cfg")
    assert env["CLAUDE_CONFIG_DIR"] == "/tmp/cfg"


def test_build_env_omits_config_dir_when_none():
    env = _build_env(AgentConfig(), config_dir=None)
    assert "CLAUDE_CONFIG_DIR" not in env


# ---------------------------------------------------------------------------
# Registry + capability protocols
# ---------------------------------------------------------------------------


def test_claude_agent_registered_under_canonical_key():
    assert AGENTS.get("claude") is ClaudeCodeAgent


def test_claude_agent_satisfies_mcp_skills_and_rules_protocols():
    agent = ClaudeCodeAgent(AgentConfig())
    assert isinstance(agent, SupportsMcp)
    assert isinstance(agent, SupportsSkills)
    assert isinstance(agent, SupportsRules)


def test_claude_agent_mirrors_capability_bindings_onto_mixin_attributes():
    binding = McpBinding(name="x", command=(), tools=("t",))
    skills = SkillBinding(paths=("/some/skills",))
    caps = AllCapabilities(
        mcp_servers=(binding,),
        skills=skills,
        rules=AgentRules(text="be a sre"),
    )
    agent = ClaudeCodeAgent(AgentConfig(capabilities=caps))
    assert agent.mcp_servers == (binding,)
    assert agent.skills == skills
    assert agent.rules == AgentRules(text="be a sre")


# ---------------------------------------------------------------------------
# _execute: return shape, wiring, and error paths
# ---------------------------------------------------------------------------


def test_execute_returns_typed_result_with_trajectory(monkeypatch):
    captured: dict = {}

    def fake_run(argv, **kwargs):
        captured["argv"] = argv
        captured["timeout"] = kwargs.get("timeout")
        return SimpleNamespace(stdout=SAMPLE_STREAM, stderr="", returncode=0)

    monkeypatch.setattr(claude_mod, "run", fake_run)
    result = ClaudeCodeAgent(AgentConfig(target="claude-x", timeout_sec=30.0)).run("ping")
    assert result.output == "Done."
    assert len(result.trajectory) == 2
    assert result.errors == []
    assert result.tokens == {"input": 10, "output": 20, "total": 30, "cached": 5}
    assert captured["timeout"] == 30.0
    assert captured["argv"][0].endswith("claude-x")
    assert captured["argv"][1:3] == ["-p", "ping"]


def test_execute_wires_extra_env_into_subprocess_call(monkeypatch):
    captured: dict = {}

    def fake_run(argv, **kwargs):
        captured["extra_env"] = kwargs.get("extra_env")
        return SimpleNamespace(stdout="", stderr="", returncode=0)

    monkeypatch.setattr(claude_mod, "run", fake_run)
    ClaudeCodeAgent(AgentConfig(target="claude", api_key="sk-abc")).run("p")
    env = captured["extra_env"]
    assert env["ANTHROPIC_API_KEY"] == "sk-abc"
    assert env["CLAUDE_CODE_DISABLE_NONESSENTIAL_TRAFFIC"] == "1"


def test_execute_records_non_zero_exit(monkeypatch):
    def fake_run(argv, **kwargs):
        return SimpleNamespace(stdout="", stderr="boom", returncode=2)

    monkeypatch.setattr(claude_mod, "run", fake_run)
    result = ClaudeCodeAgent(AgentConfig(target="claude")).run("p")
    assert result.has_errors()
    assert any("exited 2" in e for e in result.errors)
    assert result.metadata.get("returncode") == 2


def test_execute_parses_stream_on_non_zero_exit(monkeypatch):
    """An ``error_max_turns`` run exits non-zero *after* emitting a full stream;
    output and trajectory must still be parsed, with the exit + subtype recorded."""
    stream = _stream(
        _assistant({"type": "tool_use", "id": "c1", "name": "do", "input": {}}),
        {"type": "result", "subtype": "error_max_turns", "result": "hit the cap"},
    )

    def fake_run(argv, **kwargs):
        return SimpleNamespace(stdout=stream, stderr="turn limit reached", returncode=1)

    monkeypatch.setattr(claude_mod, "run", fake_run)
    result = ClaudeCodeAgent(AgentConfig(target="claude")).run("p")
    assert result.output == "hit the cap"
    assert len(result.trajectory) == 1
    assert result.metadata["returncode"] == 1
    assert result.metadata["stderr"] == "turn limit reached"
    assert any("error_max_turns" in e for e in result.errors)
    assert any("exited 1" in e for e in result.errors)


def test_execute_captures_stderr_on_clean_exit(monkeypatch):
    """stderr is kept for diagnosis even when the process exits 0."""

    def fake_run(argv, **kwargs):
        return SimpleNamespace(stdout=SAMPLE_STREAM, stderr="a warning", returncode=0)

    monkeypatch.setattr(claude_mod, "run", fake_run)
    result = ClaudeCodeAgent(AgentConfig(target="claude")).run("p")
    assert result.metadata["stderr"] == "a warning"
    assert "returncode" not in result.metadata
    assert not any("exited" in e for e in result.errors)


def test_execute_handles_subprocess_error(monkeypatch):
    def fake_run(argv, **kwargs):
        raise SubprocessError(argv, returncode=-1, stdout="", stderr="timeout")

    monkeypatch.setattr(claude_mod, "run", fake_run)
    result = ClaudeCodeAgent(AgentConfig(target="claude")).run("p")
    assert result.has_errors()
    assert "subprocess error" in result.errors[0]
    assert result.trajectory == []


def test_execute_recovers_partial_trajectory_on_timeout(monkeypatch):
    """A timeout carries the partial stream-json captured before the kill; the
    harness recovers the trajectory instead of discarding the run's work, while
    still surfacing the error."""
    partial = _stream(
        _assistant(
            {"type": "tool_use", "id": "c1", "name": "mcp__gke__list_clusters", "input": {}}
        ),
        _user({"type": "tool_result", "tool_use_id": "c1", "content": "ok"}),
    )

    def fake_run(argv, **kwargs):
        raise SubprocessError(argv, returncode=-1, stdout=partial, stderr="killed after timeout")

    monkeypatch.setattr(claude_mod, "run", fake_run)
    result = ClaudeCodeAgent(AgentConfig(target="claude")).run("p")
    assert result.has_errors()
    assert any("subprocess error" in e for e in result.errors)
    assert [step["name"] for step in result.trajectory] == ["gke__list_clusters"]
    assert result.metadata["stderr"] == "killed after timeout"


def test_execute_handles_missing_binary(monkeypatch):
    def fake_run(argv, **kwargs):
        raise OSError("not found")

    monkeypatch.setattr(claude_mod, "run", fake_run)
    result = ClaudeCodeAgent(AgentConfig(target="claude")).run("p")
    assert result.has_errors()
    assert "binary unavailable" in result.errors[0]


def test_execute_passes_timeout_to_subprocess(monkeypatch):
    captured: dict = {}

    def fake_run(argv, **kwargs):
        captured.update(kwargs)
        return SimpleNamespace(stdout="", stderr="", returncode=0)

    monkeypatch.setattr(claude_mod, "run", fake_run)
    ClaudeCodeAgent(AgentConfig(target="claude", timeout_sec=15.5)).run("p")
    assert captured["timeout"] == 15.5


# ---------------------------------------------------------------------------
# _execute side-effects: capabilities land in the cwd before the subprocess.
# Assertions run INSIDE the fake ``run`` because the temp cwd is cleaned up
# once ``_execute`` returns.
# ---------------------------------------------------------------------------


def test_execute_writes_claude_md_with_rules_text_before_subprocess(monkeypatch):
    captured: dict = {}

    def fake_run(argv, **kwargs):
        from pathlib import Path

        cwd = kwargs.get("cwd")
        captured["cwd"] = cwd
        claude_md = Path(cwd) / "CLAUDE.md" if cwd else None
        captured["exists"] = bool(claude_md and claude_md.exists())
        captured["text"] = claude_md.read_text(encoding="utf-8") if captured["exists"] else None
        return SimpleNamespace(stdout="", stderr="", returncode=0)

    monkeypatch.setattr(claude_mod, "run", fake_run)
    caps = AllCapabilities(rules=AgentRules(text="you are a precise SRE"))
    ClaudeCodeAgent(AgentConfig(target="claude", capabilities=caps)).run("p")
    assert captured["exists"], "CLAUDE.md must exist in cwd before subprocess"
    assert captured["text"] == "you are a precise SRE"


def test_execute_skips_writing_claude_md_when_rules_empty(monkeypatch):
    captured: dict = {}

    def fake_run(argv, **kwargs):
        cwd = kwargs.get("cwd")
        captured["exists"] = bool(cwd and os.path.exists(os.path.join(cwd, "CLAUDE.md")))
        return SimpleNamespace(stdout="", stderr="", returncode=0)

    monkeypatch.setattr(claude_mod, "run", fake_run)
    ClaudeCodeAgent(AgentConfig(target="claude")).run("p")
    assert captured["exists"] is False


def test_execute_writes_mcp_config_and_passes_flag(monkeypatch):
    captured: dict = {}

    def fake_run(argv, **kwargs):
        captured["argv"] = argv
        mcp_path = os.path.join(kwargs["cwd"], ".claude", "mcp-config.json")
        captured["exists"] = os.path.exists(mcp_path)
        if captured["exists"]:
            with open(mcp_path) as f:
                captured["payload"] = json.load(f)
        return SimpleNamespace(stdout="", stderr="", returncode=0)

    monkeypatch.setattr(claude_mod, "run", fake_run)
    caps = AllCapabilities(
        mcp_servers=(McpBinding(name="gke", command=("gke-mcp",), tools=("mcp__gke__x",)),),
    )
    ClaudeCodeAgent(AgentConfig(target="claude", capabilities=caps)).run("p")

    assert captured["exists"], "mcp-config.json must exist in cwd before subprocess"
    assert captured["payload"] == {"mcpServers": {"gke": {"command": "gke-mcp"}}}
    argv = captured["argv"]
    assert argv[argv.index("--mcp-config") + 1].endswith(os.path.join(".claude", "mcp-config.json"))
    assert "--strict-mcp-config" in argv


def test_execute_writes_no_mcp_config_when_no_command(monkeypatch):
    captured: dict = {}

    def fake_run(argv, **kwargs):
        captured["argv"] = argv
        mcp_path = os.path.join(kwargs["cwd"], ".claude", "mcp-config.json")
        captured["exists"] = os.path.exists(mcp_path)
        return SimpleNamespace(stdout="", stderr="", returncode=0)

    monkeypatch.setattr(claude_mod, "run", fake_run)
    # Binding carries tools but no launch command → nothing to write.
    caps = AllCapabilities(
        mcp_servers=(McpBinding(name="builtin", command=(), tools=("alpha",)),),
    )
    ClaudeCodeAgent(AgentConfig(target="claude", capabilities=caps)).run("p")
    assert captured["exists"] is False
    assert "--mcp-config" not in captured["argv"]


def test_execute_materializes_skills_into_workspace(monkeypatch, tmp_path):
    src = tmp_path / "skills" / "my-skill"
    src.mkdir(parents=True)
    skill_text = "---\nname: my-skill\ndescription: do things\n---\nbody\n"
    (src / "SKILL.md").write_text(skill_text)

    captured: dict = {}

    def fake_run(argv, **kwargs):
        skill_path = os.path.join(kwargs["cwd"], ".claude", "skills", "my-skill", "SKILL.md")
        captured["exists"] = os.path.exists(skill_path)
        if captured["exists"]:
            with open(skill_path) as f:
                captured["text"] = f.read()
        else:
            captured["text"] = None
        return SimpleNamespace(stdout="", stderr="", returncode=0)

    monkeypatch.setattr(claude_mod, "run", fake_run)
    caps = AllCapabilities(skills=SkillBinding(paths=(str(tmp_path / "skills"),)))
    ClaudeCodeAgent(AgentConfig(target="claude", capabilities=caps)).run("p")
    assert captured["exists"], "skill must be materialized before subprocess"
    assert captured["text"] == skill_text


# ---------------------------------------------------------------------------
# Parallel isolation + CLAUDE_CONFIG_DIR handling.
# ---------------------------------------------------------------------------


def test_execute_injects_per_run_config_dir_when_ambient_unset(monkeypatch):
    monkeypatch.delenv("CLAUDE_CONFIG_DIR", raising=False)
    captured: dict = {}

    def fake_run(argv, **kwargs):
        captured["cwd"] = kwargs.get("cwd")
        captured["config_dir"] = kwargs.get("extra_env", {}).get("CLAUDE_CONFIG_DIR")
        return SimpleNamespace(stdout="", stderr="", returncode=0)

    monkeypatch.setattr(claude_mod, "run", fake_run)
    ClaudeCodeAgent(AgentConfig(target="claude")).run("p")

    cfg_dir = captured["config_dir"]
    assert cfg_dir is not None
    assert os.path.basename(cfg_dir).startswith("claude-config-")
    assert os.path.realpath(cfg_dir).startswith(os.path.realpath(tempfile.gettempdir()))
    assert os.path.expanduser("~/.claude") not in os.path.realpath(cfg_dir)
    # cwd is a fresh throwaway too.
    assert os.path.basename(captured["cwd"]).startswith("claude-run-")


def test_execute_respects_operator_config_dir(monkeypatch):
    monkeypatch.setenv("CLAUDE_CONFIG_DIR", "/operator/claude")
    captured: dict = {}

    def fake_run(argv, **kwargs):
        captured["config_dir"] = kwargs.get("extra_env", {}).get("CLAUDE_CONFIG_DIR")
        return SimpleNamespace(stdout="", stderr="", returncode=0)

    monkeypatch.setattr(claude_mod, "run", fake_run)
    ClaudeCodeAgent(AgentConfig(target="claude")).run("p")
    # The harness does not override an operator-exported value (it flows through
    # os.environ, not the overlay), so no CLAUDE_CONFIG_DIR is added to extra_env.
    assert captured["config_dir"] is None


def test_execute_uses_distinct_cwd_and_config_dir_per_run(monkeypatch):
    monkeypatch.delenv("CLAUDE_CONFIG_DIR", raising=False)
    cwds: list[str] = []
    cfg_dirs: list[str] = []

    def fake_run(argv, **kwargs):
        cwds.append(kwargs.get("cwd"))
        cfg_dirs.append(kwargs.get("extra_env", {}).get("CLAUDE_CONFIG_DIR"))
        return SimpleNamespace(stdout="", stderr="", returncode=0)

    monkeypatch.setattr(claude_mod, "run", fake_run)
    agent = ClaudeCodeAgent(AgentConfig(target="claude"))
    agent.run("p")
    agent.run("p")

    assert len(set(map(str, cwds))) == 2, f"cwds must be unique per run, got {cwds}"
    assert len(set(cfg_dirs)) == 2, f"config dirs must be unique per run, got {cfg_dirs}"
