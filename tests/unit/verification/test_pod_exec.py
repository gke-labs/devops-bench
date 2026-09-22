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

"""Unit tests for ``PodExecVerifier``.

The underlying ``kubectl`` calls are stubbed via ``unittest.mock.patch`` so the
verifier can be exercised without a real cluster.
"""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import patch

import pytest
from pydantic import ValidationError

from devops_bench.verification.verifiers import PodExecVerifier


def test_resource_name_target_execs_directly() -> None:
    completed = SimpleNamespace(stdout="nginx/1.27.4\n")
    with patch(
        "devops_bench.verification.verifiers.pod_exec.exec_pod", return_value=completed
    ) as mock_exec:
        result = PodExecVerifier(
            resource_name="prober",
            command=["nginx", "-v"],
            op="contains",
            value="1.27.4",
        ).verify(timeout_sec=5)

    assert result.success is True
    assert mock_exec.call_args.args[0] == "prober"


def test_exec_pod_is_called_with_the_declared_context() -> None:
    completed = SimpleNamespace(stdout="nginx/1.27.4\n")
    with patch(
        "devops_bench.verification.verifiers.pod_exec.exec_pod", return_value=completed
    ) as mock_exec:
        PodExecVerifier(
            resource_name="prober",
            command=["nginx", "-v"],
            op="contains",
            value="1.27.4",
            context="west",
        ).verify(timeout_sec=5)

    assert mock_exec.call_args.kwargs["context"] == "west"


def test_get_resource_for_selector_resolution_is_called_with_the_declared_context() -> None:
    pods = {"items": [{"metadata": {"name": "a-pod"}}]}
    completed = SimpleNamespace(stdout="OK\n")
    with (
        patch(
            "devops_bench.verification.verifiers.pod_exec.get_resource", return_value=pods
        ) as mock_get,
        patch("devops_bench.verification.verifiers.pod_exec.exec_pod", return_value=completed),
    ):
        PodExecVerifier(
            selector="app=probe", command=["cat", "status"], op="eq", value="OK", context="west"
        ).verify(timeout_sec=5)

    assert mock_get.call_args.kwargs["context"] == "west"


def test_selector_resolves_to_first_pod_by_name() -> None:
    pods = {"items": [{"metadata": {"name": "b-pod"}}, {"metadata": {"name": "a-pod"}}]}
    completed = SimpleNamespace(stdout="OK\n")
    with (
        patch("devops_bench.verification.verifiers.pod_exec.get_resource", return_value=pods),
        patch(
            "devops_bench.verification.verifiers.pod_exec.exec_pod", return_value=completed
        ) as mock_exec,
    ):
        result = PodExecVerifier(
            selector="app=probe", command=["cat", "status"], op="eq", value="OK"
        ).verify(timeout_sec=5)

    assert result.success is True
    assert mock_exec.call_args.args[0] == "a-pod"


def test_no_matching_pod_is_an_error_not_a_fail() -> None:
    with patch(
        "devops_bench.verification.verifiers.pod_exec.get_resource",
        return_value={"items": []},
    ):
        result = PodExecVerifier(selector="app=ghost", command=["true"], op="eq", value="x").verify(
            timeout_sec=0
        )

    assert result.success is False
    assert result.status == "error"


def test_exec_failure_is_an_error_not_a_fail() -> None:
    with patch(
        "devops_bench.verification.verifiers.pod_exec.exec_pod",
        side_effect=RuntimeError("connection refused"),
    ):
        result = PodExecVerifier(
            resource_name="prober", command=["true"], op="eq", value="x"
        ).verify(timeout_sec=0)

    assert result.success is False
    assert result.status == "error"


def test_stdout_is_stripped_before_comparison() -> None:
    completed = SimpleNamespace(stdout="  OK  \n")
    with patch("devops_bench.verification.verifiers.pod_exec.exec_pod", return_value=completed):
        result = PodExecVerifier(
            resource_name="prober", command=["tail", "-n", "1", "probe.log"], op="eq", value="OK"
        ).verify(timeout_sec=5)

    assert result.success is True


def test_mismatched_output_fails() -> None:
    completed = SimpleNamespace(stdout="FAIL\n")
    with patch("devops_bench.verification.verifiers.pod_exec.exec_pod", return_value=completed):
        result = PodExecVerifier(
            resource_name="prober", command=["tail", "-n", "1", "probe.log"], op="eq", value="OK"
        ).verify(timeout_sec=0)

    assert result.success is False
    assert result.status == "fail"


def test_both_resource_name_and_selector_rejected() -> None:
    with pytest.raises(ValidationError, match="exactly one of"):
        PodExecVerifier(resource_name="a", selector="app=b", command=["true"], op="eq", value="x")


def test_neither_resource_name_nor_selector_rejected() -> None:
    with pytest.raises(ValidationError, match="exactly one of"):
        PodExecVerifier(command=["true"], op="eq", value="x")


def test_value_op_without_value_rejected() -> None:
    with pytest.raises(ValidationError, match="requires 'value'"):
        PodExecVerifier(resource_name="a", command=["true"], op="contains")


def test_empty_command_rejected() -> None:
    with pytest.raises(ValidationError):
        PodExecVerifier(resource_name="a", command=[], op="eq", value="x")


@pytest.mark.parametrize(("timeout_sec", "expected_timeout"), [(0.0, 30.0), (5.0, 5.0)])
def test_exec_is_called_with_a_floored_timeout(timeout_sec: float, expected_timeout: float) -> None:
    completed = SimpleNamespace(stdout="OK")
    with patch(
        "devops_bench.verification.verifiers.pod_exec.exec_pod", return_value=completed
    ) as mock_exec:
        PodExecVerifier(resource_name="prober", command=["true"], op="eq", value="OK").verify(
            timeout_sec=timeout_sec
        )

    assert mock_exec.call_args.kwargs["timeout"] == expected_timeout


def test_name_is_echoed_onto_result() -> None:
    completed = SimpleNamespace(stdout="OK")
    with patch("devops_bench.verification.verifiers.pod_exec.exec_pod", return_value=completed):
        result = PodExecVerifier(
            name="probe-ok", resource_name="prober", command=["true"], op="eq", value="OK"
        ).verify(timeout_sec=5)

    assert result.name == "probe-ok"
