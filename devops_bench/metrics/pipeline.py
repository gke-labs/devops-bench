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

"""Batch scoring loop that turns execution results into per-task scores."""

from __future__ import annotations

import json
from typing import Any

from deepeval.test_case import LLMTestCase

from devops_bench.core import get_bool, get_logger

# Imported for their @METRICS.register side effects.
from devops_bench.metrics import (
    chaos_metrics,  # noqa: F401
    grounding,  # noqa: F401
    outcome_validity,  # noqa: F401
    tool_invocation,  # noqa: F401
)
from devops_bench.metrics.base import (
    METRICS,
    MetricContext,
)

# Re-exported for callers importing from this module.
from devops_bench.metrics.checklist import (
    CHECKLIST_THRESHOLD,
    ChecklistMetric,
    extract_checklist_items,
)

__all__ = [
    "CHECKLIST_THRESHOLD",
    "ChecklistMetric",
    "evaluate_metrics_batch",
    "extract_checklist_items",
]

_log = get_logger("metrics.pipeline")

# Order in which builtin metric keys appear in results.json.
_BUILTIN_METRIC_KEYS: tuple[str, ...] = (
    "outcome_validity",
    "tool_invocation",
    "checklist",
    "grounding",
    "chaos",
)


def _build_context(
    res: dict[str, Any], judge_model: Any, use_mcp: bool
) -> MetricContext:
    """Build the per-result :class:`MetricContext`, sharing test cases.

    Args:
        res: One execution result dict.
        judge_model: A ``DeepEvalBaseLLM`` judge.
        use_mcp: Whether the run was granted MCP capabilities.

    Returns:
        A populated :class:`MetricContext` with the three test cases built once.
    """
    # ``input`` / ``output`` / ``expected_output`` are the minimum a judge needs
    # and are always written by the harness. The trajectory / latency /
    # retrieval-context fields default to empty so a slimmer external result dict
    # degrades to an unscored case rather than raising an uncaught ``KeyError``
    # here (before the per-metric ``try`` in the batch loop).
    prompt = res["input"]
    actual_output = res["output"]
    expected_output = res["expected_output"]
    trajectory = res.get("trajectory", [])
    latency = res.get("latency")
    retrieval_context = res.get("retrieval_context")

    outcome_case = LLMTestCase(
        input=prompt,
        actual_output=actual_output if actual_output else "No response generated",
        expected_output=expected_output,
        retrieval_context=retrieval_context,
        latency=latency,
    )

    combined_actual = {
        "tools_used": res.get("tools", []),
        "execution_trace": trajectory,
    }
    tool_case = LLMTestCase(
        input=prompt,
        actual_output=json.dumps(combined_actual, indent=2),
        expected_output=expected_output,
        latency=latency,
    )

    all_context = {
        "tools_used": res.get("tools", []),
        "execution_trace": trajectory,
        "text_output": actual_output if actual_output else "No response generated",
    }
    all_case = LLMTestCase(
        input=prompt,
        actual_output=json.dumps(all_context, indent=2),
        expected_output=expected_output,
        latency=latency,
    )

    return MetricContext(
        result=res,
        judge=judge_model,
        use_mcp=use_mcp,
        outcome_case=outcome_case,
        tool_case=tool_case,
        all_case=all_case,
    )


def evaluate_metrics_batch(
    detailed_results: list[dict[str, Any]],
    judge_model: Any,
    *,
    use_mcp: bool | None = None,
) -> None:
    """Score a batch of execution results in place via the metrics registry.

    Adding a metric is a new ``@METRICS.register(...)`` class in any metric
    module — there is no orchestration surgery required here. Each registered
    evaluator's :meth:`MetricEvaluator.applies` gates whether it runs for a
    given result, and one failing metric never aborts the rest.

    Args:
        detailed_results: Execution result dicts. ``input``, ``output``, and
            ``expected_output`` are required; ``trajectory``, ``latency``,
            ``retrieval_context``, ``name``, ``documentation``, ``chaos_spec`` /
            ``chaos_report`` / ``perf_report``, and ``tools`` are optional and
            default to empty when absent.
        judge_model: A ``DeepEvalBaseLLM`` judge model.
        use_mcp: Whether the harness granted MCP tool capabilities. ``None``
            falls back to the ``BENCH_USE_MCP`` env var.
    """
    _log.info("Starting batch post-processing evaluation metrics...")
    if use_mcp is None:
        use_mcp = get_bool("BENCH_USE_MCP", True)

    builtin_keys = list(_BUILTIN_METRIC_KEYS)
    builtin_set = set(builtin_keys)
    # Builtin metrics in the pinned (results.json) order, then any third-party
    # registrations in registry insertion order.
    ordered_keys = builtin_keys + [k for k in METRICS if k not in builtin_set]
    evaluators = [METRICS[k]() for k in ordered_keys]

    for res in detailed_results:
        ctx = _build_context(res, judge_model, use_mcp)
        scores: dict[str, Any] = {}
        _log.info("Evaluating metrics for: %s...", res.get("name"))
        for ev in evaluators:
            try:
                if not ev.applies(ctx):
                    continue
                for ms in ev.evaluate(ctx):
                    scores[ms.name] = ms.to_entry()
            except Exception:  # noqa: BLE001 - one metric must not abort the rest
                _log.exception(
                    "metric %r failed for %s",
                    getattr(ev, "name", ev),
                    res.get("name"),
                )
        res["scores"] = scores
