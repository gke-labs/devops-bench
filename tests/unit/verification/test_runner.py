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

"""Unit tests for ``VerifierAgent`` deadline semantics and dispatch.

Leaf ``verify`` methods are stubbed throughout so the runner can be exercised
without a real cluster. The runner shares a single ``time.monotonic`` clock
with its leaves; tests patch it in-place when they need deterministic
deadline behavior.
"""

from __future__ import annotations

from typing import Any
from unittest.mock import patch

from devops_bench.verification import (
    ParallelSpec,
    SequenceSpec,
    VerificationResult,
    VerificationSpec,
    VerifierAgent,
)
from devops_bench.verification.verifiers import (
    PodHealthyVerifier,
    ScalingCompleteVerifier,
)


def _stub_result(success: bool = True, reason: str = "ok") -> VerificationResult:
    return VerificationResult(success=success, elapsed_time=0.0, reason=reason)


def test_leaf_spec_dispatches_to_verify():
    calls: list[float] = []

    def fake_verify(self: Any, timeout_sec: float) -> VerificationResult:
        calls.append(timeout_sec)
        return _stub_result()

    spec = VerificationSpec({"type": "pod_healthy", "selector": "app=web"})
    with patch.object(PodHealthyVerifier, "verify", fake_verify):
        result = VerifierAgent().wait_for_condition(spec, timeout_sec=30)

    assert result.success is True
    assert len(calls) == 1
    # Leaf saw approximately the full budget.
    assert 25.0 < calls[0] <= 30.0


def test_sequence_runs_children_in_order_and_aggregates():
    order: list[str] = []
    verify_calls: dict[str, float] = {}

    def fake_pod(self: PodHealthyVerifier, timeout_sec: float) -> VerificationResult:
        order.append("pod")
        verify_calls["pod"] = timeout_sec
        return _stub_result(reason="pod ok")

    def fake_scale(self: ScalingCompleteVerifier, timeout_sec: float) -> VerificationResult:
        order.append("scale")
        verify_calls["scale"] = timeout_sec
        return _stub_result(reason="scale ok")

    spec = VerificationSpec(
        {
            "type": "sequence",
            "name": "ordered",
            "checks": [
                {"type": "pod_healthy", "selector": "app=web"},
                {"type": "scaling_complete", "deployment": "web"},
            ],
        }
    )
    with (
        patch.object(PodHealthyVerifier, "verify", fake_pod),
        patch.object(ScalingCompleteVerifier, "verify", fake_scale),
    ):
        result = VerifierAgent().wait_for_condition(spec, timeout_sec=60)

    assert result.success is True
    assert result.name == "ordered"
    assert order == ["pod", "scale"]
    assert len(result.children) == 2
    assert result.children[0].reason == "pod ok"


def test_sequence_fail_fast_skips_remaining_children():
    calls: list[str] = []

    def fake_pod(self: PodHealthyVerifier, timeout_sec: float) -> VerificationResult:
        calls.append("pod")
        return _stub_result(success=False, reason="pod failed")

    def fake_scale(self: ScalingCompleteVerifier, timeout_sec: float) -> VerificationResult:
        calls.append("scale")
        return _stub_result(success=True)

    spec = VerificationSpec(
        {
            "type": "sequence",
            "checks": [
                {"type": "pod_healthy", "selector": "app=web"},
                {"type": "scaling_complete", "deployment": "web"},
            ],
        }
    )
    with (
        patch.object(PodHealthyVerifier, "verify", fake_pod),
        patch.object(ScalingCompleteVerifier, "verify", fake_scale),
    ):
        result = VerifierAgent().wait_for_condition(spec, timeout_sec=30)

    assert result.success is False
    assert calls == ["pod"]  # later child never called
    assert len(result.children) == 2
    assert result.children[0].success is False
    assert result.children[1].success is False
    assert "earlier step failed" in result.children[1].reason


def test_parallel_runs_children_concurrently_and_ands():
    timeouts: list[float] = []

    def fake_pod(self: PodHealthyVerifier, timeout_sec: float) -> VerificationResult:
        timeouts.append(timeout_sec)
        return _stub_result(success=True)

    spec = VerificationSpec(
        {
            "type": "parallel",
            "checks": [
                {"type": "pod_healthy", "selector": "app=web"},
                {"type": "pod_healthy", "selector": "app=db"},
                {"type": "pod_healthy", "selector": "app=cache"},
            ],
        }
    )
    with patch.object(PodHealthyVerifier, "verify", fake_pod):
        result = VerifierAgent().wait_for_condition(spec, timeout_sec=45)

    assert result.success is True
    assert len(timeouts) == 3
    # Every child saw approximately the full remaining deadline — no draw-down.
    for t in timeouts:
        assert 40.0 < t <= 45.0


def test_parallel_one_failure_fails_the_group():
    def fake_pod(self: PodHealthyVerifier, timeout_sec: float) -> VerificationResult:
        # Fail when targeting db; succeed otherwise.
        if "db" in self.selector:
            return _stub_result(success=False, reason="db pods not ready")
        return _stub_result(success=True)

    spec = VerificationSpec(
        {
            "type": "parallel",
            "checks": [
                {"type": "pod_healthy", "selector": "app=web"},
                {"type": "pod_healthy", "selector": "app=db"},
            ],
        }
    )
    with patch.object(PodHealthyVerifier, "verify", fake_pod):
        result = VerifierAgent().wait_for_condition(spec, timeout_sec=20)

    assert result.success is False
    assert any(not c.success for c in result.children)
    assert any(c.success for c in result.children)


def test_nested_sequence_of_parallels_dispatches_both_levels():
    call_log: list[str] = []

    def fake_pod(self: PodHealthyVerifier, timeout_sec: float) -> VerificationResult:
        call_log.append(f"pod:{self.selector}")
        return _stub_result(success=True)

    def fake_scale(self: ScalingCompleteVerifier, timeout_sec: float) -> VerificationResult:
        call_log.append(f"scale:{self.deployment}")
        return _stub_result(success=True)

    spec = VerificationSpec(
        {
            "type": "sequence",
            "checks": [
                {"type": "pod_healthy", "selector": "app=web"},
                {
                    "type": "parallel",
                    "checks": [
                        {"type": "scaling_complete", "deployment": "web"},
                        {"type": "scaling_complete", "deployment": "db"},
                    ],
                },
            ],
        }
    )
    with (
        patch.object(PodHealthyVerifier, "verify", fake_pod),
        patch.object(ScalingCompleteVerifier, "verify", fake_scale),
    ):
        result = VerifierAgent().wait_for_condition(spec, timeout_sec=60)

    assert result.success is True
    assert call_log[0] == "pod:app=web"
    assert {"scale:web", "scale:db"} <= set(call_log)
    assert isinstance(result.children[1].children[0], VerificationResult)


def test_sequence_skips_remaining_when_deadline_exhausted_at_iteration_boundary():
    # Drive ``time.monotonic`` so the deadline is *exactly* exhausted at the
    # boundary check between the two children: the first child still runs, but
    # the per-iteration ``if time.monotonic() >= deadline`` short-circuits
    # before the second child can dispatch.
    #
    # Sequence of monotonic() calls:
    #   1. wait_for_condition: deadline = monotonic() + 10 = 0.0 + 10 = 10
    #   2. _run_sequence start = monotonic() -> 0.1
    #   3. iter 0 deadline check -> 0.2 (< 10, ok)
    #   4. _run_leaf remaining = 10 - monotonic() = 10 - 0.3 = 9.7 (ok)
    #   5. iter 1 deadline check -> 1000.0 (>= 10, skip rest)
    #   6. elapsed_time computation -> 1000.1
    times = iter([0.0, 0.1, 0.2, 0.3, 1000.0, 1000.1])

    def fake_monotonic() -> float:
        return next(times)

    pod_calls = []

    def fake_pod(self: PodHealthyVerifier, timeout_sec: float) -> VerificationResult:
        pod_calls.append(timeout_sec)
        return _stub_result(success=True, reason="pod ok")

    def fake_scale(self: ScalingCompleteVerifier, timeout_sec: float) -> VerificationResult:
        raise AssertionError("scale verify should not have been called past deadline")

    spec = VerificationSpec(
        {
            "type": "sequence",
            "checks": [
                {"type": "pod_healthy", "selector": "app=web"},
                {"type": "scaling_complete", "deployment": "web"},
            ],
        }
    )

    with (
        patch("devops_bench.verification.runner.time.monotonic", fake_monotonic),
        patch.object(PodHealthyVerifier, "verify", fake_pod),
        patch.object(ScalingCompleteVerifier, "verify", fake_scale),
    ):
        result = VerifierAgent().wait_for_condition(spec, timeout_sec=10)

    assert result.success is False
    assert len(pod_calls) == 1  # first child ran
    assert len(result.children) == 2
    assert result.children[0].success is True
    assert result.children[1].success is False
    assert result.children[1].reason == "deadline exhausted"


def test_leaf_past_deadline_returns_timed_out_without_calling_verify():
    times = iter([0.0, 100.0, 200.0])

    def fake_monotonic() -> float:
        return next(times)

    def fake_pod(self: PodHealthyVerifier, timeout_sec: float) -> VerificationResult:
        raise AssertionError("verify should not be called past deadline")

    spec = VerificationSpec({"type": "pod_healthy", "selector": "app=web"})

    with (
        patch("devops_bench.verification.runner.time.monotonic", fake_monotonic),
        patch.object(PodHealthyVerifier, "verify", fake_pod),
    ):
        result = VerifierAgent().wait_for_condition(spec, timeout_sec=10)

    assert result.success is False
    assert "deadline exhausted" in result.reason


def test_single_clock_source_only_monotonic():
    # The runner module must not import or call ``time.time`` — all timing is
    # ``time.monotonic`` so verifier and runner share one clock.
    from pathlib import Path

    from devops_bench.verification import runner

    source = Path(runner.__file__).read_text()
    assert "time.time(" not in source


def test_wait_for_condition_accepts_already_parsed_node():
    def fake_pod(self: PodHealthyVerifier, timeout_sec: float) -> VerificationResult:
        return _stub_result(success=True, reason="ok")

    node = VerificationSpec({"type": "pod_healthy", "selector": "app=web"}).root
    with patch.object(PodHealthyVerifier, "verify", fake_pod):
        result = VerifierAgent().wait_for_condition(node, timeout_sec=5)

    assert result.success is True


def test_wait_for_condition_accepts_sequence_node_directly():
    def fake_pod(self: PodHealthyVerifier, timeout_sec: float) -> VerificationResult:
        return _stub_result(success=True, reason="ok")

    node = VerificationSpec(
        {
            "type": "sequence",
            "checks": [{"type": "pod_healthy", "selector": "app=web"}],
        }
    ).root
    assert isinstance(node, SequenceSpec)
    with patch.object(PodHealthyVerifier, "verify", fake_pod):
        result = VerifierAgent().wait_for_condition(node, timeout_sec=5)

    assert result.success is True


def test_parallel_with_no_checks_passes_trivially():
    spec = VerificationSpec({"type": "parallel", "checks": []})

    result = VerifierAgent().wait_for_condition(spec, timeout_sec=5)

    assert result.success is True
    assert result.children == []


def test_sequence_records_reason_for_each_child():
    def fake_pod(self: PodHealthyVerifier, timeout_sec: float) -> VerificationResult:
        return _stub_result(success=True)

    spec = VerificationSpec(
        {
            "type": "sequence",
            "checks": [
                {"type": "pod_healthy", "selector": "app=a"},
                {"type": "pod_healthy", "selector": "app=b"},
            ],
        }
    )
    with patch.object(PodHealthyVerifier, "verify", fake_pod):
        result = VerifierAgent().wait_for_condition(spec, timeout_sec=10)

    assert result.success is True
    assert "[0] succeeded" in result.reason
    assert "[1] succeeded" in result.reason


def test_parallel_node_isinstance_check_is_independent_of_leaf_construction():
    # The runner dispatches on the compound spec types only; leaf identity does
    # not affect dispatch. This protects the Phase-4 swap (registry-driven leaf
    # parsing) from breaking the runner.
    parallel = ParallelSpec(type="parallel", checks=[])
    sequence = SequenceSpec(type="sequence", checks=[])

    result_p = VerifierAgent().wait_for_condition(parallel, timeout_sec=1)
    result_s = VerifierAgent().wait_for_condition(sequence, timeout_sec=1)

    assert result_p.success is True
    assert result_s.success is True


def test_parallel_with_exhausted_deadline_times_out_all_children_using_real_verifiers():
    # Top-level parallel with timeout_sec=0 — the deadline is exhausted before
    # any child can dispatch. Uses the REAL ``PodHealthyVerifier`` /
    # ``ScalingCompleteVerifier`` classes (no ``verify`` stub) and patches the
    # kubectl primitives to raise: if either were ever invoked the test fails.
    spec = VerificationSpec(
        {
            "type": "parallel",
            "name": "exhausted-group",
            "checks": [
                {"type": "pod_healthy", "name": "pods", "selector": "app=web"},
                {
                    "type": "scaling_complete",
                    "name": "scale",
                    "deployment": "web",
                    "min_replicas": 1,
                },
            ],
        }
    )

    def _fail(*_args: Any, **_kwargs: Any) -> Any:
        raise AssertionError("kubectl primitive should not be called past deadline")

    with (
        patch("devops_bench.verification.verifiers.pod_healthy.wait", _fail),
        patch("devops_bench.verification.verifiers.pod_healthy.get_resource", _fail),
        patch("devops_bench.verification.verifiers.scaling_complete.get_resource", _fail),
    ):
        result = VerifierAgent().wait_for_condition(spec, timeout_sec=0)

    assert result.success is False
    assert result.name == "exhausted-group"
    assert len(result.children) == 2
    # Both children must be timed-out failures; their elapsed_time is the
    # documented 0.0 since they never ran. The reason is either
    # "deadline exhausted before evaluation" (leaf short-circuit on the
    # worker thread) or "deadline reached" (parallel-level pre-fill when the
    # worker never started).
    for child in result.children:
        assert child.success is False
        assert child.elapsed_time == 0.0
        assert "deadline" in child.reason
    # Names propagate from the leaf nodes onto the timed-out child results.
    assert {c.name for c in result.children} == {"pods", "scale"}


def test_parallel_leaf_unhandled_exception_becomes_failed_child_not_group_abort():
    # A leaf that raises unexpectedly must not abort the whole parallel group;
    # the other children should still run and report normally.
    def bad_pod(self: PodHealthyVerifier, timeout_sec: float) -> VerificationResult:
        raise RuntimeError("boom")

    def ok_scale(
        self: ScalingCompleteVerifier, timeout_sec: float
    ) -> VerificationResult:
        return _stub_result(success=True, reason="scaled")

    spec = VerificationSpec(
        {
            "type": "parallel",
            "checks": [
                {"type": "pod_healthy", "selector": "app=web"},
                {"type": "scaling_complete", "deployment": "web"},
            ],
        }
    )
    with (
        patch.object(PodHealthyVerifier, "verify", bad_pod),
        patch.object(ScalingCompleteVerifier, "verify", ok_scale),
    ):
        result = VerifierAgent().wait_for_condition(spec, timeout_sec=10)

    assert result.success is False
    assert len(result.children) == 2
    pod_child = result.children[0]
    scale_child = result.children[1]
    assert pod_child.success is False
    assert "unhandled error" in pod_child.reason
    assert "boom" in pod_child.reason
    # Sibling still completed normally.
    assert scale_child.success is True
    assert scale_child.reason == "scaled"
