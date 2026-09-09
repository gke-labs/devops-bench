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

"""Unit tests for ``IdentityPreservedVerifier``.

The underlying ``kubectl`` calls are stubbed via ``unittest.mock.patch`` so the
verifier can be exercised without a real cluster.
"""

from __future__ import annotations

from unittest.mock import patch

from devops_bench.verification.verifiers import IdentityPreservedVerifier

_KEY_UID = "devops-bench.io/original-uid"
_KEY_CREATED = "devops-bench.io/original-creation-timestamp"


def _deployment(uid: str, created: str, annotations: dict[str, str]) -> dict:
    return {
        "metadata": {
            "uid": uid,
            "creationTimestamp": created,
            "annotations": annotations,
        }
    }


def test_matching_uid_and_timestamp_passes() -> None:
    dep = _deployment(
        "abc-123",
        "2026-01-01T00:00:00Z",
        {_KEY_UID: "abc-123", _KEY_CREATED: "2026-01-01T00:00:00Z"},
    )
    with patch(
        "devops_bench.verification.verifiers.identity_preserved.get_resource", return_value=dep
    ):
        result = IdentityPreservedVerifier(kind="Deployment", resource_name="web-gateway").verify(
            timeout_sec=0
        )

    assert result.success is True


def test_changed_uid_fails_deleted_and_recreated() -> None:
    # A delete+recreate keeps the same annotation value (if copied forward) but
    # the server assigns a brand-new uid; a mismatch is the tell.
    dep = _deployment(
        "new-uid",
        "2026-02-02T00:00:00Z",
        {_KEY_UID: "old-uid", _KEY_CREATED: "2026-01-01T00:00:00Z"},
    )
    with patch(
        "devops_bench.verification.verifiers.identity_preserved.get_resource", return_value=dep
    ):
        result = IdentityPreservedVerifier(kind="Deployment", resource_name="web-gateway").verify(
            timeout_sec=0
        )

    assert result.success is False
    assert result.status == "fail"
    assert "deleted and recreated" in result.reason


def test_missing_baseline_annotation_fails_closed() -> None:
    # A resource reapplied straight from the GitOps repo (which never carried
    # the annotation) has no baseline to compare against; that must read as a
    # failure, not a vacuous pass.
    dep = _deployment("some-uid", "2026-01-01T00:00:00Z", {})
    with patch(
        "devops_bench.verification.verifiers.identity_preserved.get_resource", return_value=dep
    ):
        result = IdentityPreservedVerifier(kind="Deployment", resource_name="web-gateway").verify(
            timeout_sec=0
        )

    assert result.success is False
    assert "no baseline identity annotation" in result.reason


def test_kubectl_failure_is_an_error_not_a_fail() -> None:
    with patch(
        "devops_bench.verification.verifiers.identity_preserved.get_resource",
        side_effect=RuntimeError("connection refused"),
    ):
        result = IdentityPreservedVerifier(kind="Deployment", resource_name="web-gateway").verify(
            timeout_sec=0
        )

    assert result.success is False
    assert result.status == "error"


def test_changed_creation_timestamp_alone_fails() -> None:
    dep = _deployment(
        "abc-123",
        "2026-02-02T00:00:00Z",
        {_KEY_UID: "abc-123", _KEY_CREATED: "2026-01-01T00:00:00Z"},
    )
    with patch(
        "devops_bench.verification.verifiers.identity_preserved.get_resource", return_value=dep
    ):
        result = IdentityPreservedVerifier(kind="Deployment", resource_name="web-gateway").verify(
            timeout_sec=0
        )

    assert result.success is False


def test_custom_annotation_keys_are_honored() -> None:
    dep = _deployment(
        "abc-123",
        "2026-01-01T00:00:00Z",
        {"custom/uid": "abc-123", "custom/created": "2026-01-01T00:00:00Z"},
    )
    with patch(
        "devops_bench.verification.verifiers.identity_preserved.get_resource", return_value=dep
    ):
        result = IdentityPreservedVerifier(
            kind="Deployment",
            resource_name="web-gateway",
            uid_annotation_key="custom/uid",
            creation_timestamp_annotation_key="custom/created",
        ).verify(timeout_sec=0)

    assert result.success is True


def test_name_is_echoed_onto_result() -> None:
    dep = _deployment(
        "abc-123",
        "2026-01-01T00:00:00Z",
        {_KEY_UID: "abc-123", _KEY_CREATED: "2026-01-01T00:00:00Z"},
    )
    with patch(
        "devops_bench.verification.verifiers.identity_preserved.get_resource", return_value=dep
    ):
        result = IdentityPreservedVerifier(
            name="web-gateway-identity", kind="Deployment", resource_name="web-gateway"
        ).verify(timeout_sec=0)

    assert result.name == "web-gateway-identity"
