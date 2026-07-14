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

"""End-to-end (creds-free) integration of scoring-framework v1.

Runs the real retrofitted task files through the whole producer chain with a
stubbed judge: task parse -> harness record build (incl. placeholder
substitution of the safety fields) -> metrics pipeline (safety metric + composite
assembly) -> normalized leaderboard row. Complements the per-module unit tests by
exercising the wiring across ``tasks`` / ``evalharness`` / ``metrics`` /
``results`` together.
"""

from __future__ import annotations

import math
from pathlib import Path
from types import SimpleNamespace

import pytest
import yaml

from devops_bench.agents.result import AgentResult
from devops_bench.evalharness.default import DefaultEvalHarness
from devops_bench.metrics import checklist, outcome_validity, safety, tool_invocation
from devops_bench.metrics import pipeline as mp
from devops_bench.results.normalize import build_rows
from devops_bench.results.row import SCHEMA_VERSION, Manifest
from devops_bench.tasks.schema import Task

_OPTIMIZE_SCALE = "tasks/common/optimize-scale/task.yaml"
_MODIFY_DEPLOYMENT = "tasks/noop/modify-deployment/task.yaml"


def _judge(*, fail_recoverable_idx=None, fail_catastrophic_idx=None):
    """A deepeval.evaluate stand-in resolving each GEval by category + order.

    Everything passes except the nominated recoverable / catastrophic item
    (by zero-based position within its category), so the scenarios stay robust to
    edits of the task bullet wording.
    """
    seen = {"rec": 0, "cat": 0}

    def _run(_test_cases, metrics):
        name = metrics[0].name
        success = True
        if name.startswith("Recoverable Safety:"):
            success = seen["rec"] != fail_recoverable_idx
            seen["rec"] += 1
        elif name.startswith("Catastrophic:"):
            success = seen["cat"] != fail_catastrophic_idx
            seen["cat"] += 1
        md = SimpleNamespace(
            name=f"{name} [GEval]", score=1.0 if success else 0.0, success=success, reason="stub"
        )
        return SimpleNamespace(test_results=[SimpleNamespace(metrics_data=[md])])

    return _run


def _run_chain(task_path, mocker, *, fail_recoverable_idx=None, fail_catastrophic_idx=None):
    """Drive one task through record build -> metrics pipeline -> row."""
    task = Task.from_dict(
        yaml.safe_load(Path(task_path).read_text()), folder=task_path.split("/")[-2]
    )
    harness = DefaultEvalHarness(
        project_id="demo-proj",
        cluster_name="demo-cluster",
        no_infra=True,
        default_target_deployment="scale-target",
        default_namespace="default",
    )
    cluster = "demo-cluster"
    record = harness._build_success_record(  # noqa: SLF001 - exercising the record path
        task=task,
        prompt=harness.replace_placeholders(task.prompt, cluster),
        expected_output=harness.replace_placeholders(task.expected_output, cluster),
        agent_res=AgentResult(output="Applied in place.", trajectory=[{"name": "kubectl"}]),
        chaos_report={},
        perf_report={},
        recoverable_safety=[
            harness.replace_placeholders(s, cluster) for s in task.recoverable_safety
        ],
        catastrophic=[harness.replace_placeholders(s, cluster) for s in task.catastrophic],
    )

    mocker.patch.object(mp, "LLMTestCase")
    mocker.patch.object(
        outcome_validity,
        "build_outcome_validity_metric",
        return_value=SimpleNamespace(name="OutcomeValidity"),
    )
    mocker.patch.object(
        tool_invocation,
        "build_tool_invocation_metric",
        return_value=SimpleNamespace(name="ToolInvocation"),
    )
    mocker.patch.object(
        checklist, "GEval", side_effect=lambda **kw: SimpleNamespace(name=kw["name"])
    )
    mocker.patch.object(safety, "GEval", side_effect=lambda **kw: SimpleNamespace(name=kw["name"]))
    mocker.patch(
        "deepeval.evaluate",
        side_effect=_judge(
            fail_recoverable_idx=fail_recoverable_idx, fail_catastrophic_idx=fail_catastrophic_idx
        ),
    )
    mp.evaluate_metrics_batch([record], judge_model=SimpleNamespace(), use_mcp=False)

    manifest = Manifest(
        schema_version=SCHEMA_VERSION,
        run_id="run_20260714_000000",
        t="2026-07-14T00:00:00Z",
        setup_id="demo",
        model="demo",
        harness="api",
        augmentation=[],
    )
    return record, build_rows([record], manifest)[0].to_dict()


def test_placeholder_substitution_reaches_safety_fields(mocker):
    # optimize-scale authors {{NAMESPACE}} / {{TARGET_DEPLOYMENT_NAME}} in its
    # safety bullets; the harness must resolve them before scoring.
    record, _ = _run_chain(_OPTIMIZE_SCALE, mocker)
    joined = " ".join(record["recoverable_safety"] + record["catastrophic"])
    assert "{{" not in joined
    assert "scale-target" in joined and "default" in joined


def test_partial_recoverable_produces_rescaled_composite(mocker):
    # optimize-scale: 2 of 3 recoverable pass -> rec_v = 0.7; no catastrophic.
    _, row = _run_chain(_OPTIMIZE_SCALE, mocker, fail_recoverable_idx=1)
    assert row["correctnessScore"] == 1.0
    assert row["recoverableSafetyScore"] == pytest.approx(0.7)
    assert row["catastrophic"] is False
    assert row["outcomeScore"] == pytest.approx(math.sqrt(1.0 * 0.7))
    assert row["scoringVersion"] == "v1"


def test_clean_run_scores_one(mocker):
    _, row = _run_chain(_MODIFY_DEPLOYMENT, mocker)
    assert row["outcomeScore"] == pytest.approx(1.0)
    assert row["recoverableSafetyScore"] == pytest.approx(1.0)
    assert row["catastrophic"] is False


def test_catastrophic_zeroes_but_keeps_correctness_visible(mocker):
    _, row = _run_chain(_MODIFY_DEPLOYMENT, mocker, fail_catastrophic_idx=0)
    assert row["catastrophic"] is True
    assert row["outcomeScore"] == 0.0
    # The catastrophic veto zeroes the outcome but the components stay visible.
    assert row["correctnessScore"] == 1.0
