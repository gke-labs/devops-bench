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

"""End-to-end smoke test (e2e plan §8 / harness handoff §10).

Drives the real ``complextasks/optimize-scale`` task through
:meth:`DefaultHarness.run` against the :class:`NoOpDeployer`, with the agent
and the deepeval judge stubbed (no network, no provider SDK, no real
``kubectl``), but exercising the **real** wiring: deployer → chaos
trigger/action seam → verification mapping lookup → metrics registry loop →
result reporter.

Assertions pin:

* exactly one ``results.json`` was written under the run directory,
* the on-disk schema matches the preserved legacy shape (Decision D3),
* a populated trajectory rode the typed :class:`AgentResult` boundary, and
* both ``chaos_report`` and ``perf_report`` carry the typed values.
"""

from __future__ import annotations

import json
import os
import threading
from pathlib import Path
from typing import Any
from unittest.mock import patch

import pytest

from devops_bench.agents import AGENTS, AgentHarness, AgentResult, ToolCall
from devops_bench.chaos import ChaosResult
from devops_bench.chaos.faults.generate_load import GenerateLoadFault
from devops_bench.chaos.triggers.time_delay import TimeTrigger
from devops_bench.harness import default as harness_default
from devops_bench.harness.default import DefaultHarness
from devops_bench.tasks import FileSystemTaskLoader
from devops_bench.verification import VerificationResult, VerifierAgent

_REPO_ROOT = Path(__file__).resolve().parents[3]
_OPTIMIZE_SCALE_DIR = _REPO_ROOT / "complextasks" / "optimize-scale"


class _StubAgent(AgentHarness):
    """In-memory agent that records its prompt and returns a canned trajectory."""

    last_prompt: str | None = None

    def _execute(self, prompt: str) -> AgentResult:
        _StubAgent.last_prompt = prompt
        return AgentResult(
            output="Tuned HPA, added requests/limits, observed load handled.",
            trajectory=[
                ToolCall(
                    name="run_command",
                    args={"command": "kubectl apply -f deploy.yaml"},
                    result="deployment.apps/web-app configured",
                    status="completed",
                ).to_dict(),
            ],
            tokens={"input": 42, "output": 21},
        )


def _fake_inject(
    self: GenerateLoadFault,
    ctx: Any,
    event: threading.Event | None,
) -> ChaosResult:
    """Fake fault that signals 'active' and returns a clean :class:`ChaosResult`."""
    if event is not None:
        event.set()
    return ChaosResult(
        success=True,
        injected_fault=self.type,
        output="fortio load completed at 300qps for 30s",
        elapsed_time=30.5,
    )


def _fake_verification_result(
    self: VerifierAgent,
    spec: Any,
    timeout_sec: float = 120,
) -> VerificationResult:
    """Fake verifier that mimics a successful end-to-end check."""
    del spec, timeout_sec
    return VerificationResult(
        success=True,
        elapsed_time=12.0,
        reason="pods ready; scaling complete",
        name="Planned Load Spike Verification",
        children=[
            VerificationResult(
                success=True, elapsed_time=4.0, reason="pods ready", name="pod_spec"
            ),
            VerificationResult(
                success=True, elapsed_time=8.0, reason="scaled", name="scaling_spec"
            ),
        ],
    )


def _fake_evaluate_metrics(
    detailed_results: list[dict[str, Any]],
    judge: Any,
    *,
    use_mcp: bool,
) -> None:
    """Score in place — mimics ``evaluate_metrics_batch`` without ``deepeval``."""
    for res in detailed_results:
        res["scores"] = {
            "OutcomeValidity": {
                "score": 0.85,
                "success": True,
                "reason": "captured the optimization intent",
            },
            "ChecklistScore": {
                "score": 1.0,
                "success": True,
                "reason": "Passed 3 out of 3 checks.",
            },
            "DocRetrievalRate": 1.0,
        }


@pytest.fixture
def stub_agent_registered():
    """Register ``_StubAgent`` under the ``cli`` alias for the smoke run."""
    AGENTS.register("gemini-stub")(_StubAgent)
    try:
        yield
    finally:
        AGENTS._items.pop("gemini-stub", None)  # noqa: SLF001 - test-only teardown
        _StubAgent.last_prompt = None


@pytest.fixture
def smoke_env(monkeypatch: pytest.MonkeyPatch) -> None:
    """Configure the env so the harness picks NoOpDeployer + the stub agent."""
    # Strip env vars that would otherwise leak from the dev shell and skew
    # capabilities / agent selection.
    for var in (
        "BENCH_USE_MCP",
        "BENCH_AGENT_TYPE",
        "AGENT_MCP_SERVER",
        "AGENT_ALLOWED_TOOLS",
        "AGENT_SKILLS_PATHS",
        "AGENT_RULES_TEXT",
        "AGENT_MODEL",
        "AGENT_PROVIDER",
        "AGENT_TARGET",
    ):
        monkeypatch.delenv(var, raising=False)
    monkeypatch.setenv("BENCH_USE_MCP", "true")
    monkeypatch.setenv("BENCH_AGENT_TYPE", "gemini-stub")
    monkeypatch.setenv("BENCH_NO_INFRA", "true")
    # Pin placeholder targets so chaos / verification URLs are stable.
    monkeypatch.setenv("TARGET_DEPLOYMENT_NAME", "web-app")
    monkeypatch.setenv("NAMESPACE", "default")


def test_optimize_scale_smoke_end_to_end(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    smoke_env: None,
    stub_agent_registered: None,
) -> None:
    """A real ``optimize-scale`` task flows end-to-end through the harness."""
    tasks = FileSystemTaskLoader().load_tasks(str(_OPTIMIZE_SCALE_DIR))
    assert len(tasks) == 1

    # Re-route results into the tmp dir so we leave no artifacts behind.
    harness = DefaultHarness(
        project_id="proj",
        cluster_name="cluster",
        judge_model=object(),
        results_root=str(tmp_path),
    )

    # Shrink the chaos-active wait so the smoke completes quickly when the
    # fake fault already signalled the event before the scenario thread
    # started running. (The real harness uses 45s; tests don't need to.)
    # The module global is what ``_run_one`` reads at call time, so we
    # patch the live attribute on the module object — and assert against
    # the same attribute, not a frozen ``from ... import`` alias (which
    # would be a no-op assertion).
    monkeypatch.setattr(harness_default, "_CHAOS_ACTIVE_WAIT_SEC", 1)
    assert harness_default._CHAOS_ACTIVE_WAIT_SEC == 1

    # The smoke run NEVER opens a kubectl port-forward — NoOpDeployer is the
    # deployer, and the start_scenario call routes skip_port_forward=True.
    real_start_scenario = harness.start_scenario

    def patched_start_scenario(chaos_specs, mapping, ctx):
        return real_start_scenario(
            chaos_specs, mapping, ctx, skip_port_forward=True
        )

    monkeypatch.setattr(harness, "start_scenario", patched_start_scenario)

    with (
        # No real time-trigger sleep; the fake returns immediately.
        patch.object(TimeTrigger, "wait", lambda self, ctx: None),
        # Inject without driving a real LLM / fortio binary.
        patch.object(GenerateLoadFault, "inject", _fake_inject),
        # Verification: typed result returned without touching k8s.
        patch.object(
            VerifierAgent, "wait_for_condition", _fake_verification_result
        ),
        # Metrics: registry-driven loop replaced with the fake scorer so the
        # smoke does not pull deepeval / a real judge.
        patch(
            "devops_bench.metrics.evaluate_metrics_batch",
            _fake_evaluate_metrics,
            create=True,
        ),
        patch(
            "devops_bench.metrics.get_judge_model", lambda: object(), create=True
        ),
    ):
        results = harness.run(tasks)

    # ----- run shape -----------------------------------------------------
    run_dirs = [p for p in tmp_path.iterdir() if p.is_dir() and p.name.startswith("run_")]
    assert len(run_dirs) == 1, f"expected one run dir, got {run_dirs}"
    results_file = run_dirs[0] / "results.json"
    assert results_file.exists()

    on_disk = json.loads(results_file.read_text())
    assert on_disk == results
    assert len(on_disk) == 1
    record = on_disk[0]

    # ----- preserved schema (D3) -----------------------------------------
    expected_keys = {
        "input",
        "output",
        "latency",
        "tokens",
        "tools",
        "trajectory",
        "skills",
        "name",
        "status",
        "expected_output",
        "expected_output_raw",
        "retrieval_context",
        "chaos_spec",
        "verification_spec",
        "chaos_report",
        "perf_report",
        "documentation",
        "capabilities_granted",
        "scores",
    }
    assert expected_keys <= set(record.keys()), (
        f"missing keys: {expected_keys - set(record.keys())}"
    )
    assert record["status"] == "success"
    assert record["name"] == "optimize-scale"

    # ----- trajectory rode the typed AgentResult boundary ---------------
    assert isinstance(record["trajectory"], list) and record["trajectory"]
    assert record["trajectory"][0]["name"] == "run_command"
    assert record["trajectory"][0]["status"] == "completed"

    # ----- chaos + verification reports present (typed flow) -------------
    assert record["chaos_report"]["status"] == "success"
    assert record["chaos_report"]["injected_fault"] == "generate_load"
    assert record["chaos_report"]["verification"]["success"] is True
    assert record["chaos_report"]["verification"]["name"] == (
        "Planned Load Spike Verification"
    )
    assert record["perf_report"]["uptime_percentage"] == 100.0

    # ----- scores wrote in place via the (stubbed) metrics registry ------
    assert record["scores"]["OutcomeValidity"]["score"] == 0.85
    # Bare-value scores keep the legacy raw-value shape (D3).
    assert record["scores"]["DocRetrievalRate"] == 1.0

    # ----- capabilities snapshot lives on the record ---------------------
    assert record["capabilities_granted"] == {"use_mcp": True, "skills": []}

    # ----- placeholder substitution happened on the prompt ---------------
    assert "{{TARGET_DEPLOYMENT_NAME}}" not in record["input"]
    assert "web-app" in record["input"]


def test_smoke_uses_workspace_path_for_artifact_diff(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    smoke_env: None,
    stub_agent_registered: None,
) -> None:
    """Artifact diff is rooted at ``RunContext.workspace_path``, not literal cwd."""
    tasks = FileSystemTaskLoader().load_tasks(str(_OPTIMIZE_SCALE_DIR))
    harness = DefaultHarness(
        project_id="proj",
        cluster_name="cluster",
        judge_model=object(),
        results_root=str(tmp_path),
    )

    # Run the harness from a sandbox so an accidental ``snapshot_dir(".")``
    # call would diff the empty sandbox — not the user's cwd. The smoke
    # assertion is that ``run`` completes without writing into the user's
    # source tree.
    sandbox = tmp_path / "sandbox"
    sandbox.mkdir()
    monkeypatch.chdir(sandbox)

    real_start_scenario = harness.start_scenario

    def patched_start_scenario(chaos_specs, mapping, ctx):
        # Confirm the harness threaded the resolved workspace into the
        # context, so the artifact diff cannot regress to ``"."`` hardcoded.
        assert ctx.workspace_path is not None
        assert os.fspath(ctx.workspace_path) == str(sandbox.resolve())
        return real_start_scenario(
            chaos_specs, mapping, ctx, skip_port_forward=True
        )

    monkeypatch.setattr(harness, "start_scenario", patched_start_scenario)

    with (
        patch.object(TimeTrigger, "wait", lambda self, ctx: None),
        patch.object(GenerateLoadFault, "inject", _fake_inject),
        patch.object(
            VerifierAgent, "wait_for_condition", _fake_verification_result
        ),
        patch(
            "devops_bench.metrics.evaluate_metrics_batch",
            _fake_evaluate_metrics,
            create=True,
        ),
        patch(
            "devops_bench.metrics.get_judge_model", lambda: object(), create=True
        ),
    ):
        results = harness.run(tasks)

    assert len(results) == 1
    # Generated-files dir is only created when a new entry exists; the stub
    # agent writes nothing, so the dir stays absent.
    run_dirs = [p for p in tmp_path.iterdir() if p.is_dir() and p.name.startswith("run_")]
    assert run_dirs
    assert not (run_dirs[0] / "generated_files").exists()
