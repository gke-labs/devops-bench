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

"""Per-requirement checklist metric and its expected-output parser.

Scores each ``-`` bulleted "Critical Requirements" item from a task's expected
output with its own GEval and emits the aggregate ``ChecklistScore``. Registered
under the ``checklist`` key; the batch pipeline picks it up via :data:`METRICS`.
"""

from __future__ import annotations

import random
import re
import time
from collections.abc import Iterable

from deepeval.metrics import GEval
from deepeval.test_case import SingleTurnParams

from devops_bench.core import get_logger
from devops_bench.metrics.base import (
    GEVAL_PASS_THRESHOLD,
    METRICS,
    MetricContext,
    MetricScore,
    run_geval,
)

__all__ = [
    "CHECKLIST_THRESHOLD",
    "ChecklistMetric",
    "extract_checklist_items",
]

_log = get_logger("metrics.checklist")

# Per-task checklist pass cutoff.
CHECKLIST_THRESHOLD = 0.8

# Each checklist item is its own judge API call and fails independently and
# transiently (a malformed judge response, a rate limit) at a real, non-trivial
# rate — confirmed live: a 10-item checklist re-scored from the same saved
# trajectory emitted 6/10 on one attempt and 3/10 on the next, with no retry at
# all. A bounded retry absorbs that without masking a persistently-broken item.
_MAX_ATTEMPTS = 3
_BASE_DELAY_SEC = 1.0
_MAX_DELAY_SEC = 10.0


def _backoff_delay(attempt: int) -> float:
    """Full-jitter exponential backoff delay for ``attempt`` (0-based)."""
    ceiling = min(_MAX_DELAY_SEC, _BASE_DELAY_SEC * (2**attempt))
    return random.uniform(0.0, ceiling)


def extract_checklist_items(expected_output: str, use_mcp: bool) -> list[str]:
    """Parse per-requirement checklist items from an expected-output string.

    Items are the ``-`` bulleted lines inside the "Critical Requirements" section
    (everything before an "Expected Manifest Generated" marker). When MCP is
    disabled, "expected tool call" requirements are dropped since the agent has
    no tools to invoke.

    Args:
        expected_output: The task's expected-output text.
        use_mcp: Whether the run used MCP tools.

    Returns:
        The cleaned list of requirement strings (bullet markers stripped).
    """
    reqs_section = expected_output
    if "critical requirements:" in reqs_section.lower():
        parts = re.split(r"(?i)critical requirements\s*:", reqs_section, maxsplit=1)
        if len(parts) > 1:
            reqs_section = parts[1]

    if "expected manifest generated:" in reqs_section.lower():
        parts = re.split(r"(?i)expected manifest generated\s*:", reqs_section, maxsplit=1)
        reqs_section = parts[0]

    # Strip a single leading "-" bullet marker (and the spaces after it). A
    # character-class strip like ``lstrip("- ")`` would also eat a leading flag
    # ("- --dry-run" -> "dry-run") or a trailing hyphen ("...staging-").
    raw_checklist_items = [
        re.sub(r"^-\s*", "", stripped)
        for line in reqs_section.split("\n")
        if (stripped := line.strip()).startswith("-")
    ]
    checklist_items = []
    for item in raw_checklist_items:
        if not use_mcp and "expected tool call" in item.lower():
            _log.info("Skipping Expected Tool Call criteria: '%s'", item)
            continue
        checklist_items.append(item)
    return checklist_items


@METRICS.register("checklist")
class ChecklistMetric:
    """Registered evaluator scoring per-requirement checklist items.

    For each parsed checklist item the evaluator builds a per-item ``Check: …``
    GEval, scores it, and emits the aggregate ``ChecklistScore`` using
    :data:`CHECKLIST_THRESHOLD` as the pass cutoff.

    Attributes:
        name: Identifier for logging; per-score keys come from each yielded
            :class:`MetricScore`.
    """

    name = "checklist"

    def applies(self, ctx: MetricContext) -> bool:
        """Run only when the result's ``expected_output`` carries bullets."""
        return bool(extract_checklist_items(ctx.result.get("expected_output", ""), ctx.use_mcp))

    def evaluate(self, ctx: MetricContext) -> Iterable[MetricScore]:
        """Score each requirement and emit the aggregate ChecklistScore."""
        items = extract_checklist_items(ctx.result.get("expected_output", ""), ctx.use_mcp)
        dynamic_metrics = [
            GEval(
                name=f"Check: {item}",
                criteria=(
                    f"Verify that the actual output fulfills this specific requirement: {item}"
                ),
                threshold=GEVAL_PASS_THRESHOLD,
                evaluation_params=[SingleTurnParams.ACTUAL_OUTPUT],
                model=ctx.judge,
            )
            for item in items
        ]

        out: list[MetricScore] = []
        passed = 0
        evaluated = 0
        total = len(dynamic_metrics)
        for m in dynamic_metrics:
            last_error: Exception | None = None
            for attempt in range(_MAX_ATTEMPTS):
                try:
                    _log.info(
                        "Evaluating metric: %s (attempt %d/%d)...",
                        m.name,
                        attempt + 1,
                        _MAX_ATTEMPTS,
                    )
                    for ms in run_geval(ctx.all_case, [m]):
                        out.append(ms)
                        evaluated += 1
                        if ms.success:
                            passed += 1
                    last_error = None
                    break
                except Exception as e:  # noqa: BLE001 - keep scoring the rest
                    last_error = e
                    if attempt < _MAX_ATTEMPTS - 1:
                        delay = _backoff_delay(attempt)
                        _log.warning(
                            "Attempt %d/%d failed for metric %s (%s); retrying in %.1fs",
                            attempt + 1,
                            _MAX_ATTEMPTS,
                            m.name,
                            e,
                            delay,
                        )
                        time.sleep(delay)
            if last_error is not None:
                _log.error(
                    "Giving up on metric %s after %d attempts: %s",
                    m.name,
                    _MAX_ATTEMPTS,
                    last_error,
                )
                # success=None (neither pass nor fail) distinguishes "the judge
                # never rendered a verdict" from a genuine 0.0 failure, so a
                # reader of scores[...] can tell the two apart instead of the
                # item silently vanishing from the record.
                out.append(
                    MetricScore(
                        name=m.name,
                        score=None,
                        success=None,
                        reason=f"Could not be judged after {_MAX_ATTEMPTS} attempts: {last_error}",
                    )
                )

        errored = total - evaluated
        ratio = passed / evaluated if evaluated > 0 else 0.0
        reason = f"Passed {passed} out of {evaluated} evaluated checks"
        if errored:
            reason += (
                f" ({errored} of {total} could not be judged and are excluded from this ratio)"
            )
        reason += "."
        out.append(
            MetricScore(
                name="ChecklistScore",
                score=ratio,
                success=ratio >= CHECKLIST_THRESHOLD if evaluated > 0 else False,
                reason=reason,
            )
        )
        return out
