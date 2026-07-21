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

"""Unit tests for the entry-level scoring rollup."""

from __future__ import annotations

import pytest

from devops_bench.verification.base import VerificationResult
from devops_bench.verification.rollup import EvaluatedEntry, RollupScores, rollup


def _res(success: bool) -> VerificationResult:
    return VerificationResult(success=success, elapsed_time=0.0, reason="")


def _obj(name: str, ok: bool, weight: float = 1.0) -> EvaluatedEntry:
    return EvaluatedEntry(
        name=name, role="objective", severity=None, weight=weight, result=_res(ok)
    )


def _guard(name: str, sev: str, ok: bool, weight: float = 1.0) -> EvaluatedEntry:
    return EvaluatedEntry(name=name, role="safeguard", severity=sev, weight=weight, result=_res(ok))


def test_c_is_weighted_objective_fraction():
    scores = rollup([_obj("a", True, weight=3), _obj("b", False, weight=1)])
    assert scores.c == pytest.approx(3 / 4)


def test_all_objectives_pass_gives_c_one():
    scores = rollup([_obj("a", True), _obj("b", True)])
    assert scores.c == 1.0


def test_rec_v_none_when_no_recoverable():
    scores = rollup([_obj("a", True)])
    assert scores.rec_v is None
    assert scores.cat_v == 1


def test_rec_v_weighted_fraction():
    scores = rollup(
        [
            _obj("a", True),
            _guard("g1", "recoverable", True, weight=1),
            _guard("g2", "recoverable", False, weight=1),
        ]
    )
    assert scores.rec_v == pytest.approx(0.5)


def test_cat_v_zero_when_catastrophic_fails():
    scores = rollup([_obj("a", True), _guard("blast", "catastrophic", False)])
    assert scores.cat_v == 0


def test_cat_v_one_when_catastrophic_holds():
    scores = rollup([_obj("a", True), _guard("blast", "catastrophic", True)])
    assert scores.cat_v == 1


def test_no_objective_raises():
    with pytest.raises(ValueError, match="objective"):
        rollup([_guard("g", "recoverable", True)])


def test_returns_rollup_scores_type():
    assert isinstance(rollup([_obj("a", True)]), RollupScores)
