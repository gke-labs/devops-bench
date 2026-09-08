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

"""Tests for ChecklistMetric's per-item retry and error-reporting behavior."""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

from devops_bench.metrics.base import MetricContext, MetricScore
from devops_bench.metrics.checklist import ChecklistMetric


@pytest.fixture(autouse=True)
def _stub_geval(mocker):
    """Stand in for GEval so construction skips DeepEval's judge-type validation.

    ``run_geval`` is patched per-test, so the only thing the metric needs off a
    built GEval is its ``name`` — which the per-item run_geval stub reads back.
    """
    mocker.patch(
        "devops_bench.metrics.checklist.GEval",
        side_effect=lambda **kwargs: SimpleNamespace(name=kwargs["name"]),
    )


@pytest.fixture(autouse=True)
def _no_sleep(mocker):
    """Skip real backoff delays so retry tests stay fast."""
    return mocker.patch("devops_bench.metrics.checklist.time.sleep")


def _ctx(items: list[str], **result_fields) -> MetricContext:
    """Build a MetricContext whose checklist items resolve to ``items``."""
    return MetricContext(
        result={"name": "t", "expected_output": "unused, extraction is bypassed", **result_fields},
        judge=MagicMock(),
        use_mcp=True,
        outcome_case=MagicMock(),
        tool_case=MagicMock(),
        all_case=MagicMock(),
    )


def _patch_items(mocker, items: list[str]) -> None:
    """Bypass expected-output parsing; extraction itself is covered elsewhere."""
    mocker.patch("devops_bench.metrics.checklist.extract_checklist_items", return_value=items)


# --- happy path ---------------------------------------------------------------


def test_all_items_pass_on_first_try(mocker):
    _patch_items(mocker, ["a", "b"])

    def _run(case, metrics):
        return [MetricScore(name=metrics[0].name, score=1.0, success=True)]

    mocker.patch("devops_bench.metrics.checklist.run_geval", side_effect=_run)

    scores = {ms.name: ms for ms in ChecklistMetric().evaluate(_ctx(["a", "b"]))}

    assert scores["ChecklistScore"].score == pytest.approx(1.0)
    assert scores["ChecklistScore"].success is True
    assert scores["Check: a"].success is True
    assert scores["Check: b"].success is True


# --- retry recovers a transient failure ---------------------------------------


def test_transient_failure_recovers_on_retry_with_no_error_entry(mocker):
    _patch_items(mocker, ["flaky"])
    calls = {"n": 0}

    def _run(case, metrics):
        calls["n"] += 1
        if calls["n"] == 1:
            raise RuntimeError("transient judge error")
        return [MetricScore(name=metrics[0].name, score=1.0, success=True)]

    mocker.patch("devops_bench.metrics.checklist.run_geval", side_effect=_run)

    out = list(ChecklistMetric().evaluate(_ctx(["flaky"])))
    scores = {ms.name: ms for ms in out}

    assert calls["n"] == 2
    assert scores["Check: flaky"].success is True
    assert scores["ChecklistScore"].score == pytest.approx(1.0)
    assert scores["ChecklistScore"].success is True
    # No stray error-only entry for the item that ultimately succeeded.
    assert len(out) == 2


# --- persistent failure is reported honestly, not silently dropped -----------


def test_persistent_failure_is_excluded_from_denominator_not_silently_dropped(mocker):
    _patch_items(mocker, ["good", "always_broken"])

    def _run(case, metrics):
        item = metrics[0].name.split(": ", 1)[1]
        if item == "always_broken":
            raise RuntimeError("judge blew up")
        return [MetricScore(name=metrics[0].name, score=1.0, success=True)]

    mocker.patch("devops_bench.metrics.checklist.run_geval", side_effect=_run)

    out = list(ChecklistMetric().evaluate(_ctx(["good", "always_broken"])))
    scores = {ms.name: ms for ms in out}

    # The broken item gets an explicit, visible entry rather than vanishing.
    broken = scores["Check: always_broken"]
    assert broken.score is None
    assert broken.success is None
    assert "Could not be judged" in broken.reason

    # Denominator is the evaluated count (1), not the declared total (2), so a
    # single stuck item can't drag the ratio down to a spurious 0.5.
    checklist = scores["ChecklistScore"]
    assert checklist.score == pytest.approx(1.0)
    assert checklist.success is True
    assert "1 of 2 could not be judged" in checklist.reason


def test_all_items_persistently_fail_yields_zero_score_not_success(mocker):
    _patch_items(mocker, ["always_broken"])
    mocker.patch(
        "devops_bench.metrics.checklist.run_geval",
        side_effect=RuntimeError("judge blew up"),
    )

    out = list(ChecklistMetric().evaluate(_ctx(["always_broken"])))
    scores = {ms.name: ms for ms in out}

    checklist = scores["ChecklistScore"]
    # Nothing was ever evaluated: score falls back to 0.0 and is marked failed,
    # not silently reported as a passing empty checklist.
    assert checklist.score == 0.0
    assert checklist.success is False


def test_retries_up_to_max_attempts_before_giving_up(mocker, _no_sleep):
    _patch_items(mocker, ["flaky"])
    calls = {"n": 0}

    def _run(case, metrics):
        calls["n"] += 1
        raise RuntimeError(f"attempt {calls['n']}")

    mocker.patch("devops_bench.metrics.checklist.run_geval", side_effect=_run)

    list(ChecklistMetric().evaluate(_ctx(["flaky"])))

    assert calls["n"] == 3  # _MAX_ATTEMPTS
    assert _no_sleep.call_count == 2  # slept between attempts 1->2 and 2->3, not after the last
