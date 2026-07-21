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

"""Unit tests for the resource_property verifier.

``get_resource`` is patched throughout so no real ``kubectl`` runs. The verifier
polls via ``_poll_to_result``; a single immediate success needs no sleep.
"""

from __future__ import annotations

from typing import Any

import pytest
from pydantic import ValidationError

from devops_bench.core import SubprocessError
from devops_bench.verification import VerificationSpec
from devops_bench.verification.verifiers.resource_property import ResourcePropertyVerifier

_DEPLOY = {
    "metadata": {"labels": {"pod-security.kubernetes.io/enforce": "restricted"}},
    "status": {"readyReplicas": 3},
    "spec": {
        "template": {
            "spec": {
                "serviceAccountName": "hello-sa",
                "containers": [
                    {
                        "name": "web",
                        "image": "us-docker.pkg.dev/p/hello-app-c1/web:latest",
                        "livenessProbe": {"httpGet": {"path": "/healthz"}},
                        "securityContext": {"readOnlyRootFilesystem": True},
                    }
                ],
            }
        }
    },
}


def _patch_get(mocker, payload: Any):
    return mocker.patch(
        "devops_bench.verification.verifiers.resource_property.get_resource",
        return_value=payload,
    )


def test_registered_via_spec():
    node = VerificationSpec(
        {"type": "resource_property", "kind": "deployment", "name": "web", "op": "exists"}
    ).root
    assert isinstance(node, ResourcePropertyVerifier)


def test_name_and_selector_mutually_exclusive():
    with pytest.raises(ValidationError):
        ResourcePropertyVerifier.model_validate(
            {
                "type": "resource_property",
                "kind": "deployment",
                "name": "web",
                "selector": "app=web",
                "op": "exists",
            }
        )


def test_scalar_op_requires_path():
    with pytest.raises(ValidationError):
        ResourcePropertyVerifier.model_validate(
            {
                "type": "resource_property",
                "kind": "deployment",
                "name": "web",
                "op": "eq",
                "value": 1,
            }
        )


def test_gte_on_named_object(mocker):
    _patch_get(mocker, _DEPLOY)
    v = ResourcePropertyVerifier.model_validate(
        {
            "type": "resource_property",
            "kind": "deployment",
            "name": "web",
            "path": "status.readyReplicas",
            "op": "gte",
            "value": 2,
        }
    )
    assert v.verify(1).success is True


def test_gte_fails_when_below(mocker):
    _patch_get(mocker, {**_DEPLOY, "status": {"readyReplicas": 1}})
    v = ResourcePropertyVerifier.model_validate(
        {
            "type": "resource_property",
            "kind": "deployment",
            "name": "web",
            "path": "status.readyReplicas",
            "op": "gte",
            "value": 2,
        }
    )
    assert v.verify(1).success is False


def test_eq_on_special_char_label_path(mocker):
    _patch_get(mocker, _DEPLOY)
    v = ResourcePropertyVerifier.model_validate(
        {
            "type": "resource_property",
            "kind": "namespace",
            "name": "hello-app",
            "path": 'metadata.labels."pod-security.kubernetes.io/enforce"',
            "op": "eq",
            "value": "restricted",
        }
    )
    assert v.verify(1).success is True


def test_exists_on_nested_probe_path(mocker):
    _patch_get(mocker, _DEPLOY)
    v = ResourcePropertyVerifier.model_validate(
        {
            "type": "resource_property",
            "kind": "deployment",
            "name": "web",
            "path": "spec.template.spec.containers[0].livenessProbe",
            "op": "exists",
        }
    )
    assert v.verify(1).success is True


def test_exists_fails_on_missing_path(mocker):
    _patch_get(mocker, _DEPLOY)
    v = ResourcePropertyVerifier.model_validate(
        {
            "type": "resource_property",
            "kind": "deployment",
            "name": "web",
            "path": "spec.template.spec.containers[0].readinessProbe",
            "op": "exists",
        }
    )
    assert v.verify(1).success is False


def test_contains_image_path(mocker):
    _patch_get(mocker, _DEPLOY)
    v = ResourcePropertyVerifier.model_validate(
        {
            "type": "resource_property",
            "kind": "deployment",
            "name": "web",
            "path": "spec.template.spec.containers[0].image",
            "op": "contains",
            "value": "hello-app-c1",
        }
    )
    assert v.verify(1).success is True


def test_object_level_exists_over_selector_list(mocker):
    _patch_get(mocker, {"items": [{"metadata": {"name": "pdb-1"}}]})
    v = ResourcePropertyVerifier.model_validate(
        {
            "type": "resource_property",
            "kind": "poddisruptionbudget",
            "namespace": "hello-app",
            "op": "exists",
        }
    )
    assert v.verify(1).success is True


def test_object_level_exists_fails_when_empty(mocker):
    _patch_get(mocker, {"items": []})
    v = ResourcePropertyVerifier.model_validate(
        {
            "type": "resource_property",
            "kind": "networkpolicy",
            "namespace": "hello-app",
            "op": "exists",
        }
    )
    assert v.verify(1).success is False


def test_object_level_absent_passes_when_empty(mocker):
    _patch_get(mocker, {"items": []})
    v = ResourcePropertyVerifier.model_validate(
        {
            "type": "resource_property",
            "kind": "deployment",
            "selector": "app=hello-app",
            "namespace": "default",
            "op": "absent",
        }
    )
    assert v.verify(1).success is True


def test_quantifier_all_over_selector(mocker):
    _patch_get(
        mocker,
        {
            "items": [
                {
                    "spec": {
                        "template": {
                            "spec": {"containers": [{"securityContext": {"runAsNonRoot": True}}]}
                        }
                    }
                },
                {
                    "spec": {
                        "template": {
                            "spec": {"containers": [{"securityContext": {"runAsNonRoot": False}}]}
                        }
                    }
                },
            ]
        },
    )
    v = ResourcePropertyVerifier.model_validate(
        {
            "type": "resource_property",
            "kind": "deployment",
            "selector": "app=x",
            "path": "spec.template.spec.containers[0].securityContext.runAsNonRoot",
            "op": "eq",
            "value": True,
            "quantifier": "all",
        }
    )
    assert v.verify(1).success is False  # one object fails -> "all" fails


def test_named_absent_on_404(mocker):
    mocker.patch(
        "devops_bench.verification.verifiers.resource_property.get_resource",
        side_effect=SubprocessError(
            ["kubectl", "get"], returncode=1, stderr='deployments.apps "web" not found'
        ),
    )
    v = ResourcePropertyVerifier.model_validate(
        {
            "type": "resource_property",
            "kind": "deployment",
            "name": "web",
            "namespace": "default",
            "op": "absent",
        }
    )
    assert v.verify(1).success is True
