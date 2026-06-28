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

"""Regression test: the real ``optimize-scale`` verification spec parses.

The legacy schema rejected the only real compound spec in the repo because the
``name`` *value* (a bare string) was treated as a structural key. The new
discriminated union encodes the same intent as an explicit ``parallel`` node
with a ``checks`` list. This test pins the migrated literal so the regression
cannot return.
"""

from __future__ import annotations

from unittest.mock import patch

from devops_bench.verification import (
    ParallelSpec,
    VerificationResult,
    VerificationSpec,
    VerifierAgent,
)
from devops_bench.verification.verifiers import (
    PodHealthyVerifier,
    ScalingCompleteVerifier,
)

# The migrated optimize-scale verification spec — what ``tasks/common/optimize-scale``
# would author in native YAML once §7b lands. The structural change vs. the legacy
# spec: the ``name`` string becomes metadata on a ``type: parallel`` node, and the
# member checks live in a ``checks`` list.
_OPTIMIZE_SCALE_SPEC: dict = {
    "type": "parallel",
    "name": "Planned Load Spike Verification",
    "checks": [
        {
            "type": "pod_healthy",
            "name": "pod_spec",
            "selector": "app=test-deployment",
            "namespace": "default",
        },
        {
            "type": "scaling_complete",
            "name": "scaling_spec",
            "deployment": "test-deployment",
            "min_replicas": 2,
            "namespace": "default",
        },
    ],
}


def test_optimize_scale_spec_parses_and_discriminates():
    spec = VerificationSpec(_OPTIMIZE_SCALE_SPEC)

    node = spec.root
    assert isinstance(node, ParallelSpec)
    assert node.name == "Planned Load Spike Verification"
    assert len(node.checks) == 2

    pod, scale = node.checks
    assert isinstance(pod, PodHealthyVerifier)
    assert pod.selector == "app=test-deployment"
    assert pod.namespace == "default"

    assert isinstance(scale, ScalingCompleteVerifier)
    assert scale.deployment == "test-deployment"
    assert scale.min_replicas == 2
    assert scale.namespace == "default"


def test_optimize_scale_spec_dispatches_end_to_end_with_stubbed_leaves():
    spec = VerificationSpec(_OPTIMIZE_SCALE_SPEC)

    def fake_pod(self: PodHealthyVerifier, timeout_sec: float) -> VerificationResult:
        return VerificationResult(
            success=True, elapsed_time=0.0, reason="pods ready", name=self.name
        )

    def fake_scale(
        self: ScalingCompleteVerifier, timeout_sec: float
    ) -> VerificationResult:
        return VerificationResult(
            success=True, elapsed_time=0.0, reason="scaled", name=self.name
        )

    with (
        patch.object(PodHealthyVerifier, "verify", fake_pod),
        patch.object(ScalingCompleteVerifier, "verify", fake_scale),
    ):
        result = VerifierAgent().wait_for_condition(spec, timeout_sec=30)

    assert result.success is True
    assert result.name == "Planned Load Spike Verification"
    assert len(result.children) == 2
    # Leaf names propagated through the result tree.
    assert {c.name for c in result.children} == {"pod_spec", "scaling_spec"}
