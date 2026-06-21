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

"""Verifier that waits for a deployment to reach a minimum ready replica count."""

from __future__ import annotations

import time
from typing import Any, Literal

from devops_bench.core import SubprocessError, get_logger
from devops_bench.k8s import get_resource, poll_until
from devops_bench.verification.base import VERIFIERS, BaseVerifier, VerificationResult

__all__ = ["ScalingCompleteVerifier"]

_log = get_logger("verification.scaling_complete")


@VERIFIERS.register("scaling_complete")
class ScalingCompleteVerifier(BaseVerifier):
    """Verify that a deployment has converged to a minimum ready replica count.

    The deployment's ``status.readyReplicas`` is polled with exponential backoff
    (via :func:`devops_bench.k8s.poll_until`) until it reaches ``min_replicas``
    or the timeout elapses.

    Attributes:
        type: Discriminator literal, always ``"scaling_complete"``.
        deployment: Name of the deployment to inspect.
        min_replicas: Ready replicas required for success.
        namespace: Optional namespace; defaults to the active one.
    """

    type: Literal["scaling_complete"] = "scaling_complete"
    deployment: str
    min_replicas: int = 1
    namespace: str | None = None

    def verify(self, timeout_sec: float) -> VerificationResult:
        """Poll the deployment until it reaches ``min_replicas`` ready replicas.

        Args:
            timeout_sec: Maximum seconds to keep polling.

        Returns:
            A result reflecting the last observed scaling state; successful once
            ready replicas meet or exceed ``min_replicas``.
        """
        start_time = time.monotonic()
        last: dict[str, dict[str, Any]] = {}

        def predicate() -> bool:
            success, raw = self._check_scaling()
            last["raw"] = raw
            return success

        converged = poll_until(predicate, timeout_sec=timeout_sec)
        raw = last.get("raw", {})
        if converged:
            return VerificationResult(
                success=True,
                elapsed_time=time.monotonic() - start_time,
                reason=f"Scaling complete: {raw.get('reason')}",
                name=self.name,
                raw=raw,
            )

        return VerificationResult(
            success=False,
            elapsed_time=time.monotonic() - start_time,
            reason=f"Timeout reached: {raw.get('reason')}",
            name=self.name,
            raw=raw,
        )

    def _check_scaling(self) -> tuple[bool, dict[str, Any]]:
        """Read the deployment once and compare ready replicas to the minimum.

        Returns:
            A ``(success, raw)`` pair. ``raw`` always carries a ``reason`` and,
            on success paths, the raw deployment document.
        """
        try:
            dep_data = get_resource(
                "deployment",
                self.deployment,
                namespace=self.namespace,
                kubeconfig=self.kubeconfig,
            )
        except SubprocessError as exc:
            stderr = (exc.stderr or "").strip()
            _log.warning("Failed to get deployment %s: %s", self.deployment, stderr)
            return False, {"reason": f"Failed to get deployment: {stderr}"}
        except ValueError:
            _log.warning("Failed to parse deployment JSON for %s", self.deployment)
            return False, {"reason": "Failed to parse deployment JSON"}

        # ``status`` may be explicitly null before the controller populates it.
        ready_replicas = (dep_data.get("status") or {}).get("readyReplicas", 0)
        success = ready_replicas >= self.min_replicas
        if success:
            reason = (
                f"Ready replicas ({ready_replicas}) >= min replicas ({self.min_replicas})"
            )
        else:
            reason = (
                f"Ready replicas ({ready_replicas}) < min replicas ({self.min_replicas})"
            )
        return success, {"reason": reason, "deployment": dep_data}
