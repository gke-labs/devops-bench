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

"""Verifier that issues an HTTP request from inside the cluster via an ephemeral pod."""

from __future__ import annotations

import re
import time
import uuid
from typing import Any, Literal

from devops_bench.core import SubprocessError, get_logger
from devops_bench.k8s import run_pod
from devops_bench.verification.base import VERIFIERS, BaseVerifier, VerificationResult

__all__ = ["HttpProbeVerifier"]

_log = get_logger("verification.http_probe")


@VERIFIERS.register("http_probe")
class HttpProbeVerifier(BaseVerifier):
    """Verify HTTP reachability by running a one-shot curl inside the cluster.

    Launches an ephemeral ``curlimages/curl`` pod via ``kubectl run --rm``
    and asserts on status code and, optionally, body content. This verifier
    exists to prove the ephemeral-pod substrate for in-cluster probing; reach
    for it only when the service is not externally accessible. Every use is a
    documentation point that the service cannot be probed from outside the
    cluster.

    Attributes:
        type: Discriminator literal, always ``"http_probe"``.
        url: URL to probe (must be reachable from inside the cluster).
        expect_status: Expected HTTP status code; default 200.
        expect_body_matches: Optional regex applied to the response body; the
            probe fails when the pattern does not match.
        namespace: Namespace the ephemeral pod is launched in; uses the
            active context namespace when ``None``.
        probe_timeout: Seconds the curl command is allowed to run before the
            pod is terminated. The overall kubectl overhead budget is this
            value plus 30 s.
    """

    type: Literal["http_probe"] = "http_probe"
    url: str
    expect_status: int = 200
    expect_body_matches: str | None = None
    namespace: str | None = None
    probe_timeout: int = 10

    def verify(self, timeout_sec: float) -> VerificationResult:
        """Run the curl probe and return the result.

        Args:
            timeout_sec: Maximum seconds the entire check may take. The probe
                itself is bounded by ``probe_timeout``; ``timeout_sec`` is
                accepted here to satisfy the :class:`BaseVerifier` contract but
                the probe is always one-shot.

        Returns:
            The verification result.
        """
        start = time.monotonic()
        try:
            ok, reason, raw = self._run_probe()
        except SubprocessError as exc:
            stderr = (exc.stderr or "").strip()
            _log.warning("http_probe kubectl run failed for %s: %s", self.url, stderr)
            return VerificationResult(
                success=False,
                elapsed_time=time.monotonic() - start,
                reason=f"kubectl run failed: {stderr}",
                name=self.name,
                weight=self.weight,
            )
        except Exception as exc:  # noqa: BLE001 - surface unexpected errors as failures
            _log.warning("http_probe unexpected error for %s: %s", self.url, exc)
            return VerificationResult(
                success=False,
                elapsed_time=time.monotonic() - start,
                reason=f"unexpected error: {exc}",
                name=self.name,
                weight=self.weight,
            )
        return VerificationResult(
            success=ok,
            elapsed_time=time.monotonic() - start,
            reason=reason,
            name=self.name,
            raw=raw,
            weight=self.weight,
        )

    def _run_probe(self) -> tuple[bool, str, dict[str, Any] | None]:
        """Launch an ephemeral curl pod and evaluate its output.

        Returns:
            ``(success, reason, raw)`` triple.

        Raises:
            SubprocessError: If kubectl exits non-zero.
        """
        pod_name = f"http-probe-{uuid.uuid4().hex[:8]}"
        curl_cmd = [
            "curl",
            "-s",
            "-w",
            r"\n%{http_code}",
            f"--max-time={self.probe_timeout}",
            self.url,
        ]
        output = run_pod(
            pod_name,
            "curlimages/curl",
            curl_cmd,
            namespace=self.namespace,
            kubeconfig=self.kubeconfig,
            timeout=self.probe_timeout + 30,
        ).rstrip()

        # curl writes body then ``\n<status_code>`` at the end.
        lines = output.rsplit("\n", 1)
        if len(lines) < 2:
            return False, f"unexpected curl output: {output!r}", None

        body, status_line = lines
        try:
            status_code = int(status_line.strip())
        except ValueError:
            return False, f"could not parse HTTP status from {status_line!r}", None

        raw: dict[str, Any] = {"status_code": status_code, "body_length": len(body)}

        if status_code != self.expect_status:
            return (
                False,
                f"expected HTTP {self.expect_status}, got {status_code} from {self.url}",
                raw,
            )

        if self.expect_body_matches and not re.search(self.expect_body_matches, body):
            return False, f"body did not match pattern {self.expect_body_matches!r}", raw

        return True, f"HTTP {status_code} from {self.url}", raw
