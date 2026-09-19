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

"""Unit tests for ``GcpSecretVersionVerifier``.

The underlying ``kubectl``/``gcloud`` calls are stubbed via
``unittest.mock.patch`` so the verifier can be exercised without a real
cluster or GCP project.
"""

from __future__ import annotations

from unittest.mock import patch

import pytest
from pydantic import ValidationError

from devops_bench.verification.verifiers import GcpSecretVersionVerifier

_EXTERNAL_SECRET = {
    "metadata": {"name": "db-credentials"},
    "spec": {"data": [{"remoteRef": {"key": "db-credentials-ns-abcd1234"}}]},
}

_SOURCE = {
    "kind": "ExternalSecret",
    "resource_name": "db-credentials",
    "namespace": "secret-rotation",
    "path": "spec.data[0].remoteRef.key",
}


def test_state_check_resolves_secret_id_and_compares_state() -> None:
    with (
        patch(
            "devops_bench.verification.verifiers.gcp_secret_version.get_resource",
            return_value=_EXTERNAL_SECRET,
        ),
        patch(
            "devops_bench.verification.verifiers.gcp_secret_version.describe_secret_version",
            return_value={"state": "DISABLED"},
        ) as mock_describe,
    ):
        result = GcpSecretVersionVerifier(
            project_id="my-project",
            secret_id_source=_SOURCE,
            version="1",
            field="state",
            op="matches",
            value="^(DISABLED|DESTROYED)$",
        ).verify(timeout_sec=5)

    assert result.success is True
    mock_describe.assert_called_once_with(
        "my-project", "db-credentials-ns-abcd1234", "1", timeout=5
    )


def test_get_resource_is_called_with_the_declared_context() -> None:
    with (
        patch(
            "devops_bench.verification.verifiers.gcp_secret_version.get_resource",
            return_value=_EXTERNAL_SECRET,
        ) as mock_get,
        patch(
            "devops_bench.verification.verifiers.gcp_secret_version.describe_secret_version",
            return_value={"state": "DISABLED"},
        ),
    ):
        GcpSecretVersionVerifier(
            project_id="my-project",
            secret_id_source=_SOURCE,
            version="1",
            field="state",
            op="matches",
            value="^(DISABLED|DESTROYED)$",
            context="west",
        ).verify(timeout_sec=5)

    assert mock_get.call_args.kwargs["context"] == "west"


def test_state_check_fails_when_version_still_enabled() -> None:
    with (
        patch(
            "devops_bench.verification.verifiers.gcp_secret_version.get_resource",
            return_value=_EXTERNAL_SECRET,
        ),
        patch(
            "devops_bench.verification.verifiers.gcp_secret_version.describe_secret_version",
            return_value={"state": "ENABLED"},
        ),
    ):
        result = GcpSecretVersionVerifier(
            project_id="my-project",
            secret_id_source=_SOURCE,
            version="1",
            field="state",
            op="matches",
            value="^(DISABLED|DESTROYED)$",
        ).verify(timeout_sec=0)

    assert result.success is False
    assert result.status == "fail"


def test_payload_check_reads_latest_version() -> None:
    with (
        patch(
            "devops_bench.verification.verifiers.gcp_secret_version.get_resource",
            return_value=_EXTERNAL_SECRET,
        ),
        patch(
            "devops_bench.verification.verifiers.gcp_secret_version.access_secret_version",
            return_value="a-new-strong-value",
        ) as mock_access,
    ):
        result = GcpSecretVersionVerifier(
            project_id="my-project",
            secret_id_source=_SOURCE,
            version="latest",
            field="payload",
            op="ne",
            value="compromised-password-v1",
        ).verify(timeout_sec=5)

    assert result.success is True
    mock_access.assert_called_once_with(
        "my-project", "db-credentials-ns-abcd1234", "latest", timeout=5
    )


def test_deleted_secret_id_source_fails_closed_not_errors() -> None:
    """A selector matching nothing (e.g. the ExternalSecret was deleted) must FAIL, not
    error — an error is excluded from rollup's correctness denominator, which would let
    dismantling the source object silently exempt this objective instead of failing it.
    """
    with patch(
        "devops_bench.verification.verifiers.gcp_secret_version.get_resource",
        return_value={"items": []},
    ):
        result = GcpSecretVersionVerifier(
            project_id="my-project",
            secret_id_source={**_SOURCE, "resource_name": None, "selector": "app=ghost"},
            version="latest",
            field="payload",
            op="ne",
            value="x",
        ).verify(timeout_sec=0)

    assert result.success is False
    assert result.status == "fail"


def test_kubectl_failure_resolving_secret_id_is_an_error_not_a_fail() -> None:
    with patch(
        "devops_bench.verification.verifiers.gcp_secret_version.get_resource",
        side_effect=RuntimeError("connection refused"),
    ):
        result = GcpSecretVersionVerifier(
            project_id="my-project",
            secret_id_source=_SOURCE,
            version="latest",
            field="payload",
            op="ne",
            value="x",
        ).verify(timeout_sec=0)

    assert result.success is False
    assert result.status == "error"


def test_gcloud_failure_is_an_error_not_a_fail() -> None:
    with (
        patch(
            "devops_bench.verification.verifiers.gcp_secret_version.get_resource",
            return_value=_EXTERNAL_SECRET,
        ),
        patch(
            "devops_bench.verification.verifiers.gcp_secret_version.access_secret_version",
            side_effect=RuntimeError("permission denied"),
        ),
    ):
        result = GcpSecretVersionVerifier(
            project_id="my-project",
            secret_id_source=_SOURCE,
            version="latest",
            field="payload",
            op="ne",
            value="x",
        ).verify(timeout_sec=0)

    assert result.success is False
    assert result.status == "error"


def test_state_field_rejects_latest_version() -> None:
    with pytest.raises(ValidationError, match="not 'latest'"):
        GcpSecretVersionVerifier(
            project_id="my-project",
            secret_id_source=_SOURCE,
            version="latest",
            field="state",
            op="eq",
            value="DISABLED",
        )


def test_secret_id_source_rejects_both_resource_name_and_selector() -> None:
    with pytest.raises(ValidationError, match="exactly one of"):
        GcpSecretVersionVerifier(
            project_id="my-project",
            secret_id_source={**_SOURCE, "selector": "app=db-credentials"},
            version="1",
            field="state",
            op="eq",
            value="DISABLED",
        )
