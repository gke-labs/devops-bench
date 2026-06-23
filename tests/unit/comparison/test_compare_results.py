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

"""Unit tests for the comparison bucket classifier and normalizers."""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import pytest

_SCRIPT = Path(__file__).resolve().parents[3] / "scripts" / "compare_results.py"
_spec = importlib.util.spec_from_file_location("compare_results", _SCRIPT)
assert _spec is not None and _spec.loader is not None
cr = importlib.util.module_from_spec(_spec)
sys.modules["compare_results"] = cr
_spec.loader.exec_module(cr)


def _record(scores: dict, **overrides) -> dict:
    """Build a minimal result record with matching status/output/trajectory."""
    base = {
        "name": "t",
        "status": "success",
        "output": "same output",
        "trajectory": [{"name": "x"}],
        "scores": scores,
    }
    base.update(overrides)
    return base


def _buckets(comp) -> dict[str, list]:
    out: dict[str, list] = {cr.MATCHED: [], cr.INTENDED: [], cr.REGRESSION: []}
    for d in comp.differences:
        out[d.bucket].append(d)
    return out


def test_geval_suffix_normalizes_to_matched():
    legacy = _record({"OutcomeValidity [GEval]": {"score": 0.1, "success": False}})
    refactor = _record({"OutcomeValidity": {"score": 0.1, "success": False}})
    comp = cr.compare_records(legacy, refactor, "t")
    b = _buckets(comp)
    assert not b[cr.REGRESSION]
    assert any("OutcomeValidity" in d.field for d in b[cr.MATCHED])


def test_normalize_score_key_strips_suffix():
    assert cr.normalize_score_key("ToolInvocation [GEval]") == "ToolInvocation"
    assert cr.normalize_score_key("ChecklistScore") == "ChecklistScore"


def test_grounding_value_diff_is_intended():
    legacy = _record({"GroundingAccuracy": 3.0})
    refactor = _record({"GroundingAccuracy": 5.0})
    comp = cr.compare_records(legacy, refactor, "t")
    b = _buckets(comp)
    assert not b[cr.REGRESSION]
    assert any("GroundingAccuracy" in d.field for d in b[cr.INTENDED])


def test_status_flip_is_regression():
    legacy = _record({}, status="success")
    refactor = _record({}, status="failed")
    comp = cr.compare_records(legacy, refactor, "t")
    b = _buckets(comp)
    assert any(d.field == "status" for d in b[cr.REGRESSION])


def test_legacy_null_status_is_intended():
    legacy = _record({}, status=None)
    refactor = _record({}, status="success")
    comp = cr.compare_records(legacy, refactor, "t")
    b = _buckets(comp)
    assert not b[cr.REGRESSION]
    assert any(d.field == "status" for d in b[cr.INTENDED])


def test_dropped_non_allowlisted_metric_is_regression():
    legacy = _record({"OutcomeValidity": {"score": 0.1, "success": False}})
    refactor = _record({})
    comp = cr.compare_records(legacy, refactor, "t")
    b = _buckets(comp)
    assert any("OutcomeValidity" in d.field for d in b[cr.REGRESSION])


def test_dropped_checklist_metric_is_intended():
    legacy = _record({"Check: do a thing-": {"score": 0.1, "success": False}})
    refactor = _record({"Check: do a thing": {"score": 0.1, "success": False}})
    comp = cr.compare_records(legacy, refactor, "t")
    b = _buckets(comp)
    assert not b[cr.REGRESSION]
    assert len(b[cr.INTENDED]) >= 2  # one missing on each side


def test_mcp_gated_metric_missing_is_intended():
    legacy = _record({"ToolInvocation": {"score": 0.5, "success": True}})
    refactor = _record({})
    comp = cr.compare_records(legacy, refactor, "t")
    b = _buckets(comp)
    assert not b[cr.REGRESSION]
    assert any("ToolInvocation" in d.field for d in b[cr.INTENDED])


def test_non_allowlisted_value_diff_is_regression():
    legacy = _record({"OutcomeValidity": {"score": 0.1, "success": False}})
    refactor = _record({"OutcomeValidity": {"score": 0.9, "success": True}})
    comp = cr.compare_records(legacy, refactor, "t")
    b = _buckets(comp)
    assert any("OutcomeValidity" in d.field for d in b[cr.REGRESSION])


def test_output_whitespace_normalized_matches():
    legacy = _record({}, output="hello   world\n")
    refactor = _record({}, output="hello world")
    comp = cr.compare_records(legacy, refactor, "t")
    b = _buckets(comp)
    assert not any(d.field == "output" for d in b[cr.REGRESSION])


def test_output_material_diff_is_regression():
    legacy = _record({}, output="apply manifest A")
    refactor = _record({}, output="apply manifest B")
    comp = cr.compare_records(legacy, refactor, "t")
    b = _buckets(comp)
    assert any(d.field == "output" for d in b[cr.REGRESSION])


def test_trajectory_presence_delta_is_intended():
    legacy = _record({}, trajectory=[{"type": "user_input"}])
    refactor = _record({}, trajectory=[])
    comp = cr.compare_records(legacy, refactor, "t")
    b = _buckets(comp)
    assert not b[cr.REGRESSION]
    assert any(d.field == "trajectory" for d in b[cr.INTENDED])


def test_identical_records_all_matched():
    rec = _record({"OutcomeValidity": {"score": 0.1, "success": False}})
    comp = cr.compare_records(rec, dict(rec), "t")
    b = _buckets(comp)
    assert not b[cr.REGRESSION]
    assert not b[cr.INTENDED]


def test_align_by_name():
    legacy = [{"name": "b"}, {"name": "a"}]
    refactor = [{"name": "a"}, {"name": "b"}]
    aligned = cr.align_records(legacy, refactor)
    pairs = {nm: (lr["name"], rr["name"]) for nm, lr, rr in aligned}
    assert pairs["a"] == ("a", "a")
    assert pairs["b"] == ("b", "b")


def test_missing_task_is_regression():
    legacy = [_record({}, name="only_legacy")]
    refactor = []
    comps = cr.compare(legacy, refactor)
    assert cr.has_regression(comps)


def test_non_list_input_raises():
    with pytest.raises(cr.CompareError):
        cr.align_records({"not": "a list"}, [])


def test_has_regression_and_exit_semantics():
    clean = cr.compare([_record({})], [_record({})])
    assert not cr.has_regression(clean)
    flipped = cr.compare(
        [_record({}, status="success")], [_record({}, status="failed")]
    )
    assert cr.has_regression(flipped)
