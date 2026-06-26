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

"""Extension-axis acceptance: a dummy metric appears with no orchestrator edit."""

from __future__ import annotations

from collections.abc import Iterable
from unittest.mock import MagicMock

from devops_bench.metrics import pipeline
from devops_bench.metrics.base import (
    METRICS,
    MetricContext,
    MetricScore,
)
from devops_bench.metrics.pipeline import evaluate_metrics_batch


def _base_result(**overrides):
    res = {
        "input": "ping",
        "output": "pong",
        "trajectory": [],
        "expected_output": "Expected pong",
        "latency": 0.1,
        "name": "case-dummy",
        "retrieval_context": [],
        "tools": [],
    }
    res.update(overrides)
    return res


def test_dummy_metric_appears_in_scores_with_no_orchestrator_edit(mocker):
    # Stub out judge construction so the built-in metrics don't reach for
    # ``deepeval.evaluate`` during the loop (they would normally call it via
    # ``run_geval``); a no-op return means they record nothing while our dummy
    # still emits its score, which is what we want to assert on.
    from devops_bench.metrics import outcome_validity, tool_invocation

    mocker.patch.object(outcome_validity, "build_outcome_validity_metric")
    mocker.patch.object(tool_invocation, "build_tool_invocation_metric")
    mocker.patch.object(pipeline, "LLMTestCase")
    mocker.patch("deepeval.evaluate", return_value=MagicMock(test_results=[]))

    @METRICS.register("acceptance_dummy")
    class _DummyAcceptanceMetric:
        name = "DummyAcceptanceMetric"

        def applies(self, ctx: MetricContext) -> bool:
            return True

        def evaluate(self, ctx: MetricContext) -> Iterable[MetricScore]:
            yield MetricScore(name="DummyAcceptanceMetric", score=0.99)

    try:
        results = [_base_result()]
        evaluate_metrics_batch(results, MagicMock(), use_mcp=True)

        # The dummy metric appears in ``res["scores"]`` without touching
        # ``evaluate_metrics_batch`` — that is the whole point of the registry.
        assert "DummyAcceptanceMetric" in results[0]["scores"]
        # Bare-value entry round-trips through ``MetricScore.to_entry()`` (D3).
        assert results[0]["scores"]["DummyAcceptanceMetric"] == 0.99
    finally:
        METRICS._items.pop("acceptance_dummy", None)
