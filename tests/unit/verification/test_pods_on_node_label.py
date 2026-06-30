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

"""Unit tests for ``PodsOnNodeWithLabelVerifier``.

The two ``kubectl get`` calls (nodes, then pods) are stubbed via
``unittest.mock.patch`` with a ``side_effect`` so the verifier can be exercised
without a real cluster.
"""

from __future__ import annotations

from unittest.mock import patch

from devops_bench.core import SubprocessError
from devops_bench.verification.verifiers import PodsOnNodeWithLabelVerifier


def _nodes(*names):
    return {"items": [{"metadata": {"name": n}} for n in names]}


def _pods(*pairs):
    # pairs of (pod_name, node_name, phase)
    return {
        "items": [
            {
                "metadata": {"name": name},
                "spec": {"nodeName": node},
                "status": {"phase": phase},
            }
            for name, node, phase in pairs
        ]
    }


def test_success_when_all_running_pods_on_labeled_nodes():
    labeled = _nodes("spot-a", "spot-b")
    pods = _pods(("web-1", "spot-a", "Running"), ("web-2", "spot-b", "Running"))
    with patch(
        "devops_bench.verification.verifiers.pods_on_node_label.get_resource",
        side_effect=[labeled, pods],
    ):
        result = PodsOnNodeWithLabelVerifier(
            selector="app=web", node_label="cloud.google.com/gke-spot=true"
        ).verify(timeout_sec=5)

    assert result.success is True
    assert "are on nodes" in result.reason
    assert result.raw["labeled_nodes"] == ["spot-a", "spot-b"]


def test_failure_when_a_pod_is_on_an_unlabeled_node():
    labeled = _nodes("spot-a", "spot-b")
    # web-2 landed on the on-demand node.
    pods = _pods(("web-1", "spot-a", "Running"), ("web-2", "on-demand", "Running"))
    with patch(
        "devops_bench.verification.verifiers.pods_on_node_label.get_resource",
        side_effect=[labeled, pods],
    ):
        result = PodsOnNodeWithLabelVerifier(
            selector="app=web", node_label="cloud.google.com/gke-spot=true"
        ).verify(timeout_sec=0)

    assert result.success is False
    assert "not on a node matching" in result.reason
    assert "web-2" in result.reason


def test_failure_when_no_running_pods_match():
    labeled = _nodes("spot-a")
    pods = _pods(("web-1", "", "Pending"))
    with patch(
        "devops_bench.verification.verifiers.pods_on_node_label.get_resource",
        side_effect=[labeled, pods],
    ):
        result = PodsOnNodeWithLabelVerifier(
            selector="app=web", node_label="cloud.google.com/gke-spot=true"
        ).verify(timeout_sec=0)

    assert result.success is False
    assert "no Running pods" in result.reason


def test_failure_when_kubectl_errors():
    with patch(
        "devops_bench.verification.verifiers.pods_on_node_label.get_resource",
        side_effect=SubprocessError(["kubectl", "get", "nodes"], 1, stderr="nodes is forbidden"),
    ):
        result = PodsOnNodeWithLabelVerifier(
            selector="app=web", node_label="cloud.google.com/gke-spot=true"
        ).verify(timeout_sec=0)

    assert result.success is False
    assert "kubectl get failed" in result.reason


def test_registered_in_registry():
    from devops_bench.verification.base import VERIFIERS

    assert "pods_on_node_with_label" in VERIFIERS.keys()
