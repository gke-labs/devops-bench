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

"""Targeted unit tests for ``DefaultHarness`` internals not covered elsewhere.

Tests in this file exercise the harness-level wiring beyond the agent /
scenario / metrics seams (those have their own files): the scenario-drain
timed-out path, the constructor-arg-driven deployment / namespace defaults,
the cached granted-skill-paths snapshot, and the narrowed builtin-agent
import behavior.
"""

from __future__ import annotations

import importlib
import threading
from pathlib import Path
from typing import Any

import pytest

from devops_bench.agents.result import AgentResult
from devops_bench.core import MissingDependencyError
from devops_bench.harness import default as harness_default
from devops_bench.harness.default import DefaultHarness
from devops_bench.tasks import Task


@pytest.fixture
def isolated_env(monkeypatch: pytest.MonkeyPatch) -> None:
    """Strip BENCH_* / AGENT_* env so the harness reads predictable defaults."""
    for var in (
        "BENCH_USE_MCP",
        "BENCH_AGENT_TYPE",
        "AGENT_MCP_SERVER",
        "AGENT_ALLOWED_TOOLS",
        "AGENT_SKILLS_PATHS",
        "AGENT_RULES_TEXT",
        "AGENT_TARGET",
        "AGENT_MODEL",
        "AGENT_PROVIDER",
        "TARGET_DEPLOYMENT_NAME",
        "NAMESPACE",
    ):
        monkeypatch.delenv(var, raising=False)


def test_drain_scenario_stamps_timed_out_when_thread_still_alive(
    isolated_env: None,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A scenario thread that outlives the join budget is flagged on the report."""
    harness = DefaultHarness(project_id="p", cluster_name="c")

    # Drive the join budget to ~0 so the thread is "still alive" on return
    # without sleeping in the test. The harness reads the module global at
    # call time, so patching the attribute on the module flexes the path.
    monkeypatch.setattr(harness_default, "_SCENARIO_JOIN_SEC", 0.01)

    class _StuckScenario:
        """Stand-in scenario manager whose reports stay partial."""

        def get_reports(self) -> tuple[dict[str, Any], dict[str, Any]]:
            return ({"status": "initiated", "injected_fault": "x"}, {})

    stop_event = threading.Event()

    def _hang() -> None:
        # Hold the thread alive past the join budget so ``is_alive`` is True
        # on return; the event lets the test release the thread on cleanup.
        stop_event.wait(timeout=2.0)

    scenario_thread = threading.Thread(target=_hang, daemon=True)
    scenario_thread.start()
    try:
        chaos_report, perf_report = harness._drain_scenario(  # noqa: SLF001
            _StuckScenario(), scenario_thread
        )
        assert chaos_report["status"] == "timed_out"
        # Partial fields from the underlying scenario carry through so the
        # operator sees how far it got before the cutoff.
        assert chaos_report["injected_fault"] == "x"
        assert perf_report == {}
    finally:
        stop_event.set()
        scenario_thread.join(timeout=2.0)


def test_drain_scenario_returns_empty_when_no_scenario_scheduled(
    isolated_env: None,
) -> None:
    """No chaos for the task → both reports are empty dicts (legacy contract)."""
    harness = DefaultHarness(project_id="p", cluster_name="c")
    chaos_report, perf_report = harness._drain_scenario(None, None)  # noqa: SLF001
    assert chaos_report == {} and perf_report == {}


def test_default_target_deployment_and_namespace_are_ctor_args(
    isolated_env: None,
) -> None:
    """A non-Hypercompute embedder can override the legacy defaults at ctor.

    No env vars set; the harness's overrides flow through to
    ``replace_placeholders`` so a task with
    ``{{TARGET_DEPLOYMENT_NAME}}``/``{{NAMESPACE}}`` resolves to the
    embedder's values rather than the legacy literals.
    """
    harness = DefaultHarness(
        project_id="p",
        cluster_name="c",
        default_target_deployment="my-app",
        default_namespace="custom-ns",
    )
    resolved = harness.replace_placeholders(
        "deploy={{TARGET_DEPLOYMENT_NAME}} ns={{NAMESPACE}}",
        cluster_name="cl",
    )
    assert resolved == "deploy=my-app ns=custom-ns"


def test_granted_skill_paths_snapshot_captured_once(
    isolated_env: None, monkeypatch: pytest.MonkeyPatch
) -> None:
    """``_granted_skill_paths`` snapshots once at __init__, not per record.

    Removes the env-drift surface: a mid-run change to
    ``AGENT_SKILLS_PATHS`` must NOT show up in record records, because
    the harness is the single source of truth for what was granted.
    """
    monkeypatch.setenv("AGENT_SKILLS_PATHS", "/skills/a,/skills/b")
    harness = DefaultHarness(project_id="p", cluster_name="c")
    assert harness._granted_skill_paths == ("/skills/a", "/skills/b")  # noqa: SLF001

    # A later env mutation must not move the snapshot — the captured
    # tuple is the authority for the rest of the run.
    monkeypatch.setenv("AGENT_SKILLS_PATHS", "/skills/x")
    assert harness._granted_skill_paths == ("/skills/a", "/skills/b")  # noqa: SLF001


def test_build_agent_config_returns_identical_snapshot_across_calls(
    isolated_env: None, monkeypatch: pytest.MonkeyPatch
) -> None:
    """``build_agent_config`` is a pure accessor over the __init__ snapshot.

    Two back-to-back calls must return the **same object identity** so the
    agent the harness constructs cannot differ from the config the
    record's ``capabilities_granted`` was derived from. A previous version
    re-read ``AgentConfig.from_env()`` per call, opening a desync window
    that mid-batch env mutation could exploit.
    """
    monkeypatch.setenv("AGENT_SKILLS_PATHS", "/skills/a")
    monkeypatch.setenv("BENCH_USE_MCP", "true")
    harness = DefaultHarness(project_id="p", cluster_name="c")

    a = harness.build_agent_config()
    b = harness.build_agent_config()
    # Identity — not just equality — pins the no-rebuild invariant.
    assert a is b
    assert a.capabilities.skills.paths == ("/skills/a",)


def test_capabilities_granted_matches_agent_config_even_after_env_mutation(
    isolated_env: None, monkeypatch: pytest.MonkeyPatch
) -> None:
    """``capabilities_granted`` exactly mirrors the agent's actual config.

    This is the consistency invariant the senior reviewer flagged: env
    mutated AFTER ``DefaultHarness(...)`` construction must not desync
    what the agent was built with from what the record claims it was
    built with. Both come from the single ``__init__`` snapshot.
    """
    monkeypatch.setenv("AGENT_SKILLS_PATHS", "/skills/granted")
    monkeypatch.setenv("AGENT_MCP_SERVER", "/path/to/mcp")
    monkeypatch.setenv("AGENT_ALLOWED_TOOLS", "tool_a")
    monkeypatch.setenv("BENCH_USE_MCP", "true")
    harness = DefaultHarness(project_id="p", cluster_name="c")

    # Drift the env AFTER construction. The harness must still report
    # what was granted at construction, not what the env now says.
    monkeypatch.setenv("AGENT_SKILLS_PATHS", "/skills/leaked-after-init")
    monkeypatch.setenv("BENCH_USE_MCP", "false")
    monkeypatch.delenv("AGENT_MCP_SERVER", raising=False)

    config = harness.build_agent_config()
    task = Task.from_dict({"task_id": "t", "name": "demo", "prompt": "p"})
    success = harness._build_success_record(  # noqa: SLF001
        task=task,
        prompt="p",
        expected_output="e",
        agent_res=AgentResult(output="ok", trajectory=[]),
        chaos_report={},
        perf_report={},
    )
    failed = harness._build_failed_record(  # noqa: SLF001
        task, RuntimeError("boom")
    )

    # The record's ``skills`` and ``capabilities_granted.skills`` come
    # from the same snapshot the agent was built from. The post-init env
    # mutation must NOT leak through.
    expected_skills = list(config.capabilities.skills.paths)
    assert expected_skills == ["/skills/granted"]
    for record in (success, failed):
        assert record["skills"] == expected_skills
        assert record["capabilities_granted"]["skills"] == expected_skills
        # ``use_mcp`` was snapshotted True at __init__; the post-init
        # mutation to "false" must not flip it on the record.
        assert record["capabilities_granted"]["use_mcp"] is True
    # And the agent's actual MCP binding agrees — the post-init delenv
    # of AGENT_MCP_SERVER did NOT drop the binding the agent runs with.
    assert config.capabilities.mcp is not None


def test_run_one_returns_failed_record_when_get_deployer_raises(
    isolated_env: None, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """A deployer-factory failure becomes a failed record, not a batch crash.

    ``get_deployer`` runs inside ``_run_one``'s try, so an unknown deployer
    type fails just this task (status ``failed``) instead of aborting the whole
    batch evaluation.
    """
    harness = DefaultHarness(project_id="p", cluster_name="c")

    def _boom(*_args: Any, **_kwargs: Any) -> Any:
        raise ValueError("unknown deployer type")

    monkeypatch.setattr(harness_default, "get_deployer", _boom)
    task = Task.from_dict({"task_id": "t", "name": "demo", "prompt": "p"})

    record = harness._run_one(task, tmp_path)  # noqa: SLF001

    assert record["status"] == "failed"
    assert "unknown deployer type" in record["error"]
    assert record["name"] == "demo"


def test_ensure_builtin_agents_swallows_only_import_errors(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Optional-SDK absence is swallowed; real bugs re-raise.

    ``ImportError`` / ``MissingDependencyError`` are the narrow-catch
    classes — anything else (``SyntaxError``, ``RuntimeError`` at module
    top, etc.) must bubble out so the operator sees the real failure
    instead of a silent ``debug`` log.
    """
    # Case 1: ImportError is swallowed — function returns normally.
    def fake_import_missing_sdk(name: str) -> Any:
        raise ImportError("anthropic SDK not installed")

    monkeypatch.setattr(importlib, "import_module", fake_import_missing_sdk)
    harness_default._ensure_builtin_agents_registered()  # noqa: SLF001

    # Case 2: a non-import bug must NOT be silently swallowed.
    def fake_import_buggy_module(name: str) -> Any:
        raise SyntaxError("agent module is broken")

    monkeypatch.setattr(importlib, "import_module", fake_import_buggy_module)
    with pytest.raises(SyntaxError):
        harness_default._ensure_builtin_agents_registered()  # noqa: SLF001

    # Case 3: MissingDependencyError is also swallowed (its semantic class).
    def fake_missing_dep(name: str) -> Any:
        raise MissingDependencyError("optional-feature", "extras-marker")

    monkeypatch.setattr(importlib, "import_module", fake_missing_dep)
    harness_default._ensure_builtin_agents_registered()  # noqa: SLF001
