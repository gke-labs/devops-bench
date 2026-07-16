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

"""Unit tests for ResourcePropertyVerifier.

All kubernetes calls are mocked; no real cluster required.
"""

from __future__ import annotations

from unittest.mock import patch

import pytest
from pydantic import ValidationError

from devops_bench.core import SubprocessError
from devops_bench.verification.verifiers.resource_property import (
    ResourcePropertyVerifier,
    _eval_op,
    _resolve_path,
    _split_path,
)

# -- path helpers -------------------------------------------------------------


def test_split_path_simple_dotted():
    assert _split_path("spec.replicas") == ["spec", "replicas"]


def test_split_path_jsonpath_prefix():
    assert _split_path("$.spec.replicas") == ["spec", "replicas"]


def test_split_path_array_index():
    assert _split_path("spec.containers[0].name") == ["spec", "containers", "0", "name"]


def test_resolve_path_hit():
    obj = {"spec": {"replicas": 3}}
    found, val = _resolve_path(obj, "spec.replicas")
    assert found is True
    assert val == 3


def test_resolve_path_miss():
    obj = {"spec": {}}
    found, val = _resolve_path(obj, "spec.replicas")
    assert found is False
    assert val is None


def test_resolve_path_array_index():
    obj = {"spec": {"containers": [{"name": "web"}, {"name": "sidecar"}]}}
    found, val = _resolve_path(obj, "spec.containers[1].name")
    assert found is True
    assert val == "sidecar"


def test_resolve_path_out_of_range_index():
    obj = {"spec": {"containers": [{"name": "web"}]}}
    found, val = _resolve_path(obj, "spec.containers[5].name")
    assert found is False


def test_resolve_path_jsonpath_prefix():
    obj = {"status": {"readyReplicas": 2}}
    found, val = _resolve_path(obj, "$.status.readyReplicas")
    assert found is True
    assert val == 2


# -- eval_op ------------------------------------------------------------------


def test_eval_op_eq():
    assert _eval_op(3, "eq", 3) is True
    assert _eval_op(3, "eq", 4) is False


def test_eval_op_ne():
    assert _eval_op(3, "ne", 4) is True
    assert _eval_op(3, "ne", 3) is False


def test_eval_op_numeric_comparisons():
    assert _eval_op(5, "gt", 3) is True
    assert _eval_op(3, "gt", 5) is False
    assert _eval_op(3, "gte", 3) is True
    assert _eval_op(2, "lt", 5) is True
    assert _eval_op(5, "lte", 5) is True


def test_eval_op_contains_string():
    assert _eval_op("hello world", "contains", "world") is True
    assert _eval_op("hello", "contains", "xyz") is False


def test_eval_op_contains_list():
    assert _eval_op(["a", "b", "c"], "contains", "b") is True
    assert _eval_op(["a", "b"], "contains", "z") is False


def test_eval_op_matches_regex():
    assert _eval_op("nginx/1.23", "matches", r"nginx/\d+") is True
    assert _eval_op("apache/2.4", "matches", r"nginx") is False


def test_eval_op_matches_none_value_returns_false():
    # str(None) == "None" which would match "on" without the guard.
    assert _eval_op(None, "matches", "on") is False


def test_eval_op_matches_none_value_never_matches_any_pattern():
    assert _eval_op(None, "matches", "None") is False
    assert _eval_op(None, "matches", ".*") is False


def test_eval_op_numeric_comparison_with_non_numeric_returns_false():
    assert _eval_op("abc", "gt", 3) is False


# -- model validation ---------------------------------------------------------


def test_requires_name_or_selector():
    with pytest.raises(ValidationError, match="exactly one of"):
        ResourcePropertyVerifier(kind="deployment", path="spec.replicas", op="eq", value=2)


def test_rejects_both_name_and_selector():
    with pytest.raises(ValidationError, match="exactly one of"):
        ResourcePropertyVerifier(
            kind="deployment",
            name="web",
            selector="app=web",
            path="spec.replicas",
            op="eq",
            value=2,
        )


def test_accepts_name():
    v = ResourcePropertyVerifier(
        kind="deployment", name="web", path="spec.replicas", op="eq", value=2
    )
    assert v.name == "web"


def test_accepts_selector():
    v = ResourcePropertyVerifier(
        kind="pod", selector="app=web", path="status.phase", op="eq", value="Running"
    )
    assert v.selector == "app=web"


# -- verify with named resource -----------------------------------------------


_DEPLOYMENT = {
    "kind": "Deployment",
    "metadata": {"name": "web"},
    "spec": {"replicas": 3},
    "status": {"readyReplicas": 3},
}


def test_verify_eq_success():
    with patch(
        "devops_bench.verification.verifiers.resource_property.get_resource",
        return_value=_DEPLOYMENT,
    ):
        v = ResourcePropertyVerifier(
            kind="deployment", name="web", path="spec.replicas", op="eq", value=3
        )
        result = v.verify(timeout_sec=0)

    assert result.success is True
    assert "1/1 passed" in result.reason


def test_verify_eq_failure():
    dep = {**_DEPLOYMENT, "spec": {"replicas": 1}}
    with patch(
        "devops_bench.verification.verifiers.resource_property.get_resource",
        return_value=dep,
    ):
        v = ResourcePropertyVerifier(
            kind="deployment", name="web", path="spec.replicas", op="eq", value=3
        )
        result = v.verify(timeout_sec=0)

    assert result.success is False


def test_verify_exists_op():
    with patch(
        "devops_bench.verification.verifiers.resource_property.get_resource",
        return_value=_DEPLOYMENT,
    ):
        v = ResourcePropertyVerifier(
            kind="deployment", name="web", path="spec.replicas", op="exists"
        )
        result = v.verify(timeout_sec=0)

    assert result.success is True


def test_verify_absent_op_on_missing_path():
    with patch(
        "devops_bench.verification.verifiers.resource_property.get_resource",
        return_value=_DEPLOYMENT,
    ):
        v = ResourcePropertyVerifier(
            kind="deployment", name="web", path="spec.nonexistent", op="absent"
        )
        result = v.verify(timeout_sec=0)

    assert result.success is True


def test_verify_absent_op_on_present_path():
    with patch(
        "devops_bench.verification.verifiers.resource_property.get_resource",
        return_value=_DEPLOYMENT,
    ):
        v = ResourcePropertyVerifier(
            kind="deployment", name="web", path="spec.replicas", op="absent"
        )
        result = v.verify(timeout_sec=0)

    assert result.success is False


# -- quantifiers with selector ------------------------------------------------


_POD_LIST = {
    "kind": "List",
    "items": [
        {"status": {"phase": "Running"}},
        {"status": {"phase": "Running"}},
        {"status": {"phase": "Pending"}},
    ],
}


def test_quantifier_all_fails_when_any_fails():
    with patch(
        "devops_bench.verification.verifiers.resource_property.get_resource",
        return_value=_POD_LIST,
    ):
        v = ResourcePropertyVerifier(
            kind="pod",
            selector="app=web",
            path="status.phase",
            op="eq",
            value="Running",
            quantifier="all",
        )
        result = v.verify(timeout_sec=0)

    assert result.success is False
    assert "2/3" in result.reason


def test_quantifier_any_passes_when_some_pass():
    with patch(
        "devops_bench.verification.verifiers.resource_property.get_resource",
        return_value=_POD_LIST,
    ):
        v = ResourcePropertyVerifier(
            kind="pod",
            selector="app=web",
            path="status.phase",
            op="eq",
            value="Running",
            quantifier="any",
        )
        result = v.verify(timeout_sec=0)

    assert result.success is True


def test_quantifier_none_fails_when_any_pass():
    with patch(
        "devops_bench.verification.verifiers.resource_property.get_resource",
        return_value=_POD_LIST,
    ):
        v = ResourcePropertyVerifier(
            kind="pod",
            selector="app=web",
            path="status.phase",
            op="eq",
            value="Running",
            quantifier="none",
        )
        result = v.verify(timeout_sec=0)

    assert result.success is False


def test_quantifier_none_passes_when_none_match():
    pod_list = {"items": [{"status": {"phase": "Pending"}}]}
    with patch(
        "devops_bench.verification.verifiers.resource_property.get_resource",
        return_value=pod_list,
    ):
        v = ResourcePropertyVerifier(
            kind="pod",
            selector="app=web",
            path="status.phase",
            op="eq",
            value="Running",
            quantifier="none",
        )
        result = v.verify(timeout_sec=0)

    assert result.success is True


# -- empty result set ---------------------------------------------------------


def test_empty_object_list_fails_default_quantifier():
    with patch(
        "devops_bench.verification.verifiers.resource_property.get_resource",
        return_value={"items": []},
    ):
        v = ResourcePropertyVerifier(
            kind="pod",
            selector="app=missing",
            path="status.phase",
            op="eq",
            value="Running",
        )
        result = v.verify(timeout_sec=0)

    assert result.success is False
    assert "no pod objects matched" in result.reason


def test_empty_object_list_passes_none_quantifier():
    with patch(
        "devops_bench.verification.verifiers.resource_property.get_resource",
        return_value={"items": []},
    ):
        v = ResourcePropertyVerifier(
            kind="pod",
            selector="app=missing",
            path="status.phase",
            op="eq",
            value="Running",
            quantifier="none",
        )
        result = v.verify(timeout_sec=0)

    assert result.success is True


# -- error handling -----------------------------------------------------------


def test_subprocess_error_yields_failed_result():
    exc = SubprocessError(["kubectl"], returncode=1, stdout="", stderr="not found")
    with patch(
        "devops_bench.verification.verifiers.resource_property.get_resource",
        side_effect=exc,
    ):
        v = ResourcePropertyVerifier(
            kind="deployment", name="web", path="spec.replicas", op="eq", value=1
        )
        result = v.verify(timeout_sec=0)

    assert result.success is False
    assert "not found" in result.reason


# -- registry registration ----------------------------------------------------


def test_resource_property_is_registered():
    from devops_bench.verification.base import VERIFIERS

    assert "resource_property" in VERIFIERS
