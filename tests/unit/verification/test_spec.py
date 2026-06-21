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

"""Unit tests for the discriminated-union verification spec."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from devops_bench.verification import (
    ParallelSpec,
    SequenceSpec,
    VerificationSpec,
    json_schema,
    parse_node,
)
from devops_bench.verification.verifiers import (
    PodHealthyVerifier,
    ScalingCompleteVerifier,
)


def test_bare_leaf_is_valid_spec():
    spec = VerificationSpec({"type": "pod_healthy", "selector": "app=web"})

    node = spec.root
    assert isinstance(node, PodHealthyVerifier)
    assert node.selector == "app=web"
    assert node.name is None


def test_leaf_with_optional_name():
    spec = VerificationSpec(
        {
            "type": "scaling_complete",
            "name": "scale-to-two",
            "deployment": "web",
            "min_replicas": 2,
        }
    )

    node = spec.root
    assert isinstance(node, ScalingCompleteVerifier)
    assert node.name == "scale-to-two"
    assert node.min_replicas == 2


def test_sequence_node_parses_with_mixed_children():
    spec = VerificationSpec(
        {
            "type": "sequence",
            "name": "ordered",
            "checks": [
                {"type": "pod_healthy", "selector": "app=web"},
                {"type": "scaling_complete", "deployment": "web", "min_replicas": 1},
            ],
        }
    )

    node = spec.root
    assert isinstance(node, SequenceSpec)
    assert node.name == "ordered"
    assert isinstance(node.checks[0], PodHealthyVerifier)
    assert isinstance(node.checks[1], ScalingCompleteVerifier)


def test_parallel_node_parses_and_discriminates():
    spec = VerificationSpec(
        {
            "type": "parallel",
            "checks": [
                {"type": "pod_healthy", "selector": "app=web"},
                {"type": "pod_healthy", "selector": "app=db"},
            ],
        }
    )

    node = spec.root
    assert isinstance(node, ParallelSpec)
    assert len(node.checks) == 2
    assert all(isinstance(c, PodHealthyVerifier) for c in node.checks)


def test_nested_compounds_parse():
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

    outer = spec.root
    assert isinstance(outer, SequenceSpec)
    inner = outer.checks[1]
    assert isinstance(inner, ParallelSpec)
    assert all(isinstance(c, ScalingCompleteVerifier) for c in inner.checks)


def test_bare_list_is_rejected():
    with pytest.raises(ValidationError):
        VerificationSpec(
            [
                {"type": "pod_healthy", "selector": "app=web"},
                {"type": "pod_healthy", "selector": "app=db"},
            ]
        )


def test_bare_dict_without_type_is_rejected():
    # A dict that uses ``name`` as a structural key (the old anti-pattern that
    # kept ``optimize-scale`` from parsing) has no ``type`` discriminator and
    # must be rejected.
    with pytest.raises(ValidationError):
        VerificationSpec(
            {
                "name": "Planned Load Spike Verification",
                "pod_spec": {"type": "pod_healthy", "selector": "app=web"},
            }
        )


def test_unknown_type_is_rejected():
    with pytest.raises(ValidationError):
        VerificationSpec({"type": "definitely_not_a_check"})


def test_parse_node_returns_concrete_node():
    node = parse_node({"type": "pod_healthy", "selector": "app=web"})

    assert isinstance(node, PodHealthyVerifier)


def test_parse_node_propagates_validation_error():
    with pytest.raises(ValidationError):
        parse_node({"type": "pod_healthy"})  # missing selector


def test_json_schema_emits_all_discriminated_types():
    schema = json_schema()

    text = repr(schema)
    # All four union members must appear in the emitted schema.
    for tag in ("pod_healthy", "scaling_complete", "sequence", "parallel"):
        assert tag in text
