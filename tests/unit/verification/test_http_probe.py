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

"""Unit tests for the http_probe verifier. ``run_pod`` is patched throughout."""

from __future__ import annotations

from devops_bench.core import SubprocessError
from devops_bench.verification import VerificationSpec
from devops_bench.verification.verifiers.http_probe import HttpProbeVerifier


def _patch_run_pod(mocker, output: str):
    return mocker.patch(
        "devops_bench.verification.verifiers.http_probe.run_pod", return_value=output
    )


def test_registered_via_spec():
    node = VerificationSpec({"type": "http_probe", "url": "http://svc"}).root
    assert isinstance(node, HttpProbeVerifier)
    assert node.expect_status == 200


def test_probe_passes_on_expected_status(mocker):
    _patch_run_pod(mocker, "hello world\n200")
    v = HttpProbeVerifier.model_validate({"type": "http_probe", "url": "http://svc"})
    assert v.verify(30).success is True


def test_probe_fails_on_wrong_status(mocker):
    _patch_run_pod(mocker, "not found\n404")
    v = HttpProbeVerifier.model_validate({"type": "http_probe", "url": "http://svc"})
    result = v.verify(30)
    assert result.success is False
    assert "404" in result.reason


def test_probe_body_match_required(mocker):
    _patch_run_pod(mocker, "unexpected\n200")
    v = HttpProbeVerifier.model_validate(
        {"type": "http_probe", "url": "http://svc", "expect_body_matches": "hello"}
    )
    assert v.verify(30).success is False


def test_probe_body_match_passes(mocker):
    _patch_run_pod(mocker, "hello there\n200")
    v = HttpProbeVerifier.model_validate(
        {"type": "http_probe", "url": "http://svc", "expect_body_matches": "hello"}
    )
    assert v.verify(30).success is True


def test_probe_subprocess_error_is_failure(mocker):
    mocker.patch(
        "devops_bench.verification.verifiers.http_probe.run_pod",
        side_effect=SubprocessError(["kubectl", "run"], returncode=1, stderr="boom"),
    )
    v = HttpProbeVerifier.model_validate({"type": "http_probe", "url": "http://svc"})
    result = v.verify(30)
    assert result.success is False
    assert "kubectl run failed" in result.reason


def test_probe_unparseable_output(mocker):
    _patch_run_pod(mocker, "no-status-line")
    v = HttpProbeVerifier.model_validate({"type": "http_probe", "url": "http://svc"})
    assert v.verify(30).success is False
