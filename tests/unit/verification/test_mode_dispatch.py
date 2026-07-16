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

"""Unit tests for mode dispatch in VerifierAgent.

Verifies:
- assert mode calls verify(0) and never sleeps
- hold mode samples multiple times and fails on any failing sample
- default mode derives from entry role (correctness -> converge, safety/catastrophic -> assert)
- explicit mode on a leaf overrides the role-derived default
- unchanged mode raises NotImplementedError
"""

from __future__ import annotations

from typing import Any
from unittest.mock import patch

import pytest
from pydantic import ValidationError

from devops_bench.verification.base import VerificationResult
from devops_bench.verification.entry import VerificationEntry
from devops_bench.verification.runner import VerifierAgent
from devops_bench.verification.verifiers import ScalingCompleteVerifier


def _ok(reason: str = "ok") -> VerificationResult:
    return VerificationResult(success=True, elapsed_time=0.0, reason=reason)


def _fail(reason: str = "fail") -> VerificationResult:
    return VerificationResult(success=False, elapsed_time=0.0, reason=reason)


# -- assert mode --------------------------------------------------------------


def test_assert_mode_calls_verify_with_zero_timeout():
    timeouts: list[float] = []

    def fake_verify(self: Any, timeout_sec: float) -> VerificationResult:
        timeouts.append(timeout_sec)
        return _ok()

    with patch.object(ScalingCompleteVerifier, "verify", fake_verify):
        entry = VerificationEntry(
            name="check",
            role="safety",
            spec={"type": "scaling_complete", "deployment": "web"},
        )
        VerifierAgent().run_entry(entry, timeout_sec=30)

    assert len(timeouts) == 1
    assert timeouts[0] == 0.0


def test_assert_mode_via_explicit_leaf_mode():
    timeouts: list[float] = []

    def fake_verify(self: Any, timeout_sec: float) -> VerificationResult:
        timeouts.append(timeout_sec)
        return _ok()

    with patch.object(ScalingCompleteVerifier, "verify", fake_verify):
        entry = VerificationEntry(
            name="check",
            role="correctness",
            spec={"type": "scaling_complete", "deployment": "web", "mode": "assert"},
        )
        VerifierAgent().run_entry(entry, timeout_sec=30)

    assert timeouts[0] == 0.0


# -- converge mode ------------------------------------------------------------


def test_converge_mode_passes_remaining_timeout():
    timeouts: list[float] = []

    def fake_verify(self: Any, timeout_sec: float) -> VerificationResult:
        timeouts.append(timeout_sec)
        return _ok()

    with patch.object(ScalingCompleteVerifier, "verify", fake_verify):
        entry = VerificationEntry(
            name="check",
            role="correctness",
            spec={"type": "scaling_complete", "deployment": "web"},
        )
        VerifierAgent().run_entry(entry, timeout_sec=30)

    assert len(timeouts) == 1
    assert timeouts[0] > 20.0  # close to the full 30s budget


# -- default mode from role ---------------------------------------------------


def test_correctness_role_defaults_to_converge():
    timeouts: list[float] = []

    def fake_verify(self: Any, timeout_sec: float) -> VerificationResult:
        timeouts.append(timeout_sec)
        return _ok()

    with patch.object(ScalingCompleteVerifier, "verify", fake_verify):
        entry = VerificationEntry(
            name="check",
            role="correctness",
            spec={"type": "scaling_complete", "deployment": "web"},
        )
        VerifierAgent().run_entry(entry, timeout_sec=60)

    # converge: leaf receives approximately the full remaining timeout
    assert timeouts[0] > 50.0


def test_safety_role_defaults_to_assert():
    timeouts: list[float] = []

    def fake_verify(self: Any, timeout_sec: float) -> VerificationResult:
        timeouts.append(timeout_sec)
        return _ok()

    with patch.object(ScalingCompleteVerifier, "verify", fake_verify):
        entry = VerificationEntry(
            name="check",
            role="safety",
            spec={"type": "scaling_complete", "deployment": "web"},
        )
        VerifierAgent().run_entry(entry, timeout_sec=30)

    assert timeouts[0] == 0.0


def test_catastrophic_role_defaults_to_assert():
    timeouts: list[float] = []

    def fake_verify(self: Any, timeout_sec: float) -> VerificationResult:
        timeouts.append(timeout_sec)
        return _ok()

    with patch.object(ScalingCompleteVerifier, "verify", fake_verify):
        entry = VerificationEntry(
            name="check",
            role="catastrophic",
            spec={"type": "scaling_complete", "deployment": "web"},
        )
        VerifierAgent().run_entry(entry, timeout_sec=30)

    assert timeouts[0] == 0.0


# -- hold mode ----------------------------------------------------------------


def test_hold_mode_samples_multiple_times():
    call_count = 0

    def fake_verify(self: Any, timeout_sec: float) -> VerificationResult:
        nonlocal call_count
        call_count += 1
        assert timeout_sec == 0.0
        return _ok()

    with (
        patch.object(ScalingCompleteVerifier, "verify", fake_verify),
        patch("devops_bench.verification.runner.time.sleep"),
    ):
        entry = VerificationEntry(
            name="check",
            role="correctness",
            spec={
                "type": "scaling_complete",
                "deployment": "web",
                "mode": "hold",
                "hold_window_sec": 15.0,
                "hold_interval_sec": 5.0,
            },
        )
        pair = VerifierAgent().run_entry(entry, timeout_sec=60)

    assert pair.result.success is True
    assert call_count >= 2


def test_hold_mode_fails_on_first_failing_sample():
    call_count = 0

    def fake_verify(self: Any, timeout_sec: float) -> VerificationResult:
        nonlocal call_count
        call_count += 1
        if call_count == 2:
            return _fail("condition broke")
        return _ok()

    with (
        patch.object(ScalingCompleteVerifier, "verify", fake_verify),
        patch("devops_bench.verification.runner.time.sleep"),
    ):
        entry = VerificationEntry(
            name="check",
            role="correctness",
            spec={
                "type": "scaling_complete",
                "deployment": "web",
                "mode": "hold",
                "hold_window_sec": 30.0,
                "hold_interval_sec": 5.0,
            },
        )
        pair = VerifierAgent().run_entry(entry, timeout_sec=60)

    assert pair.result.success is False
    assert "sample 2" in pair.result.reason
    assert "condition broke" in pair.result.reason
    # Exactly 2 samples: first passed, second failed (loop stopped immediately)
    assert call_count == 2


def test_hold_mode_does_not_sleep_between_window_end_and_deadline():
    """When the hold window is shorter than the budget, the loop exits at window_end."""
    sleep_calls: list[float] = []

    def fake_verify(self: Any, timeout_sec: float) -> VerificationResult:
        return _ok()

    times = [0.0, 0.0, 0.1, 0.1, 5.1, 5.1]
    time_iter = iter(times)

    def fake_monotonic() -> float:
        try:
            return next(time_iter)
        except StopIteration:
            return 1000.0  # far future

    with (
        patch.object(ScalingCompleteVerifier, "verify", fake_verify),
        patch("devops_bench.verification.runner.time.sleep", side_effect=sleep_calls.append),
        patch("devops_bench.verification.runner.time.monotonic", fake_monotonic),
    ):
        entry = VerificationEntry(
            name="check",
            role="correctness",
            spec={
                "type": "scaling_complete",
                "deployment": "web",
                "mode": "hold",
                "hold_window_sec": 5.0,
                "hold_interval_sec": 5.0,
            },
        )
        pair = VerifierAgent().run_entry(entry, timeout_sec=60)

    assert pair.result.success is True


# -- unchanged mode -----------------------------------------------------------


def test_unchanged_mode_fails_at_entry_construction():
    """mode='unchanged' is rejected at task-load time, not mid-eval.

    The validator on VerificationEntry raises ValidationError when the raw spec
    dict contains mode='unchanged', so the failure surfaces at schema validation
    rather than deep inside VerifierAgent._run_leaf.
    """
    with pytest.raises(ValidationError, match="unchanged"):
        VerificationEntry(
            name="check",
            role="correctness",
            spec={
                "type": "scaling_complete",
                "deployment": "web",
                "mode": "unchanged",
            },
        )


# -- explicit mode overrides role default -------------------------------------


def test_explicit_converge_overrides_safety_role_default():
    timeouts: list[float] = []

    def fake_verify(self: Any, timeout_sec: float) -> VerificationResult:
        timeouts.append(timeout_sec)
        return _ok()

    with patch.object(ScalingCompleteVerifier, "verify", fake_verify):
        entry = VerificationEntry(
            name="check",
            role="safety",
            spec={"type": "scaling_complete", "deployment": "web", "mode": "converge"},
        )
        VerifierAgent().run_entry(entry, timeout_sec=30)

    # converge: leaf receives close to the full remaining timeout, not 0
    assert timeouts[0] > 20.0


def test_explicit_assert_overrides_correctness_role_default():
    timeouts: list[float] = []

    def fake_verify(self: Any, timeout_sec: float) -> VerificationResult:
        timeouts.append(timeout_sec)
        return _ok()

    with patch.object(ScalingCompleteVerifier, "verify", fake_verify):
        entry = VerificationEntry(
            name="check",
            role="correctness",
            spec={"type": "scaling_complete", "deployment": "web", "mode": "assert"},
        )
        VerifierAgent().run_entry(entry, timeout_sec=30)

    assert timeouts[0] == 0.0


# -- wait_for_condition retains existing behavior (default_mode=None) ---------


def test_wait_for_condition_default_is_converge():
    """wait_for_condition with no entry context still behaves like converge."""
    timeouts: list[float] = []

    def fake_verify(self: Any, timeout_sec: float) -> VerificationResult:
        timeouts.append(timeout_sec)
        return _ok()

    with patch.object(ScalingCompleteVerifier, "verify", fake_verify):
        from devops_bench.verification import VerificationSpec

        spec = VerificationSpec({"type": "scaling_complete", "deployment": "web"})
        VerifierAgent().wait_for_condition(spec, timeout_sec=30)

    assert timeouts[0] > 20.0
