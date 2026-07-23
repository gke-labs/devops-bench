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

"""Verifier that selected pods are scheduled on nodes carrying a given label."""

from __future__ import annotations

from typing import Any, Literal

from devops_bench.core import SubprocessError, get_logger
from devops_bench.k8s import get_resource
from devops_bench.verification.base import VERIFIERS, BaseVerifier, VerificationResult

__all__ = ["PodsOnNodeWithLabelVerifier"]

_log = get_logger("verification.pods_on_node_with_label")


@VERIFIERS.register("pods_on_node_with_label")
class PodsOnNodeWithLabelVerifier(BaseVerifier):
    """Verify every pod matched by ``selector`` runs on a node with ``node_label``.

    Resolves the set of nodes whose labels match ``node_label`` (a ``key=value``
    or bare ``key`` selector), then confirms each Running pod matched by
    ``selector`` is scheduled onto one of them. Polls until the placement holds
    or the timeout elapses, so it tolerates pods still rescheduling. Useful for
    asserting placement outcomes such as "the Spot-eligible workloads landed on
    Spot-labeled nodes".

    Attributes:
        type: Discriminator literal, always ``"pods_on_node_with_label"``.
        selector: Pod label selector (``-l``) identifying the pods to check.
        node_label: Node label selector the pods' nodes must match (e.g.
            ``"cloud.google.com/gke-spot=true"``).
        namespace: Optional namespace for the pods; defaults to the active one.
        min_pods: Minimum number of correctly-placed Running pods required to
            pass (default ``1``). Guards against a partial rollout passing while
            replicas are still Pending and may yet land on the wrong nodes.
    """

    type: Literal["pods_on_node_with_label"] = "pods_on_node_with_label"
    selector: str
    node_label: str
    namespace: str | None = None
    min_pods: int = 1

    def verify(self, timeout_sec: float) -> VerificationResult:
        """Poll until every matched, Running pod sits on a labeled node.

        Args:
            timeout_sec: Maximum seconds to keep polling.

        Returns:
            A result that is successful once at least one pod matches the
            selector and all such Running pods are scheduled on nodes carrying
            ``node_label``.
        """
        return self._poll_to_result(self._check_placement, timeout_sec)

    def _check_placement(self) -> tuple[bool, str, dict[str, Any] | None]:
        """Read pods + labeled nodes once and compare placement.

        Returns:
            A ``(success, reason, raw)`` triple. ``raw`` carries the labeled
            node set and the observed pod-to-node placement once both could be
            read, else ``None``.
        """
        try:
            labeled = get_resource("nodes", selector=self.node_label, kubeconfig=self.kubeconfig)
            pods = get_resource(
                "pods",
                selector=self.selector,
                namespace=self.namespace,
                kubeconfig=self.kubeconfig,
            )
        except SubprocessError as exc:
            return False, f"kubectl get failed: {(exc.stderr or '').strip()}", None

        labeled_nodes = {
            (node.get("metadata") or {}).get("name") for node in labeled.get("items", [])
        }
        labeled_nodes.discard(None)
        # Only Running pods have a settled node; Pending/terminating pods are not
        # yet placed and would spuriously fail (or pass) a placement check.
        running = [
            pod
            for pod in pods.get("items", [])
            if (pod.get("status") or {}).get("phase") == "Running"
        ]
        placement = {
            (pod.get("metadata") or {}).get("name"): (pod.get("spec") or {}).get("nodeName")
            for pod in running
        }
        raw: dict[str, Any] = {
            "labeled_nodes": sorted(labeled_nodes),
            "placement": placement,
        }
        # No labeled nodes at all means the label selector is wrong or the node
        # pool never came up — surface that instead of blaming every pod.
        if not labeled_nodes:
            return (
                False,
                f"no nodes match node_label {self.node_label!r} "
                "(check the selector or whether the node pool came up)",
                raw,
            )
        if not running:
            return False, f"no Running pods matched selector {self.selector!r}", raw
        misplaced = {name: node for name, node in placement.items() if node not in labeled_nodes}
        if misplaced:
            return (
                False,
                f"{len(misplaced)}/{len(running)} pod(s) not on a node matching "
                f"{self.node_label!r}: {misplaced}",
                raw,
            )
        # Every Running pod here is correctly placed; require enough of them so a
        # partial rollout (replicas still Pending) does not pass prematurely.
        if len(running) < self.min_pods:
            return (
                False,
                f"only {len(running)} correctly-placed Running pod(s) matching "
                f"{self.selector!r}; need >= {self.min_pods} (others may still be scheduling)",
                raw,
            )
        return (
            True,
            f"all {len(running)} pod(s) matching {self.selector!r} are on nodes "
            f"matching {self.node_label!r}",
            raw,
        )
