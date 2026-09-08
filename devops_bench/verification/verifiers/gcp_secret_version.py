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

"""Assert a property of a GCP Secret Manager secret version.

``resource_property`` and ``pod_exec`` answer what the cluster itself says or
serves; this verifier answers what Secret Manager itself says about a secret
version's ``state`` (``ENABLED`` / ``DISABLED`` / ``DESTROYED``) or
``payload`` — the one fact a task's own report, or even a healthy-looking
``ExternalSecret`` sync, cannot substitute for. A "the old version is
revoked" claim is only real if Secret Manager agrees; a "new secure value"
claim is only real if the payload it actually stored differs from the
compromised one.

The secret id is resolved from a live Kubernetes object rather than declared
as a literal, because a parallel-safe stack names its Secret Manager secret
with a run-scoped suffix (see the ``random_id`` comment in this task's
``main.tf``) that isn't known at task-authoring time. Any object already on
the cluster that carries the resolved id (an ``ExternalSecret``'s
``remoteRef.key`` is the common case) works as the source.
"""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, model_validator

from devops_bench.gcp import access_secret_version, describe_secret_version
from devops_bench.k8s import get_resource
from devops_bench.verification.base import (
    VERIFIERS,
    BaseVerifier,
    VerificationResult,
    VerificationStatus,
    single_call_timeout,
)
from devops_bench.verification.verifiers.resource_property import _apply_op, _compile

__all__ = ["GcpSecretVersionVerifier", "SecretIdSource"]

_VALUE_OPS = ("eq", "ne", "contains", "matches")


class SecretIdSource(BaseModel):
    """Locate a Secret Manager secret id via a field on a live Kubernetes object.

    Attributes:
        kind: Resource kind to fetch, e.g. ``"ExternalSecret"``.
        resource_name: Exact object name. Mutually exclusive with ``selector``.
        selector: Label selector resolving to one or more objects; the first
            match (as returned by the API) is used.
        namespace: Optional namespace; defaults to the active one.
        path: JSONPath resolving to the secret id, e.g.
            ``'spec.data[0].remoteRef.key'``.
    """

    model_config = ConfigDict(extra="forbid")

    kind: str
    resource_name: str | None = None
    selector: str | None = None
    namespace: str | None = None
    path: str

    @model_validator(mode="after")
    def _check_shape(self) -> SecretIdSource:
        """Reject combinations that cannot mean anything at evaluation time."""
        if bool(self.resource_name) == bool(self.selector):
            msg = "secret_id_source takes exactly one of 'resource_name' or 'selector'"
            raise ValueError(msg)
        return self


@VERIFIERS.register("gcp_secret_version")
class GcpSecretVersionVerifier(BaseVerifier):
    """Compare a GCP Secret Manager secret version's state or payload.

    Attributes:
        type: Discriminator literal, always ``"gcp_secret_version"``.
        project_id: GCP project the secret lives in.
        secret_id_source: How to resolve the secret id from the live cluster.
        version: Version number to inspect, or ``"latest"`` (the newest
            ``ENABLED`` version). ``field: "state"`` requires a concrete
            version — ``"latest"`` is by definition always enabled, so
            asserting its state would be vacuous.
        field: ``"state"`` compares the version's lifecycle state
            (``ENABLED`` / ``DISABLED`` / ``DESTROYED``); ``"payload"``
            compares its decoded secret data.
        op: Comparison applied to the resolved value.
        value: Right-hand side of the comparison.
    """

    type: Literal["gcp_secret_version"] = "gcp_secret_version"
    project_id: str
    secret_id_source: SecretIdSource
    version: str
    field: Literal["state", "payload"]
    op: Literal["eq", "ne", "contains", "matches"]
    value: Any = None

    @model_validator(mode="after")
    def _check_shape(self) -> GcpSecretVersionVerifier:
        """Reject combinations that cannot mean anything at evaluation time."""
        if self.field == "state" and self.version == "latest":
            msg = "field 'state' needs a concrete version number, not 'latest'"
            raise ValueError(msg)
        if self.op in _VALUE_OPS and self.value is None:
            raise ValueError(f"op {self.op!r} requires 'value'")
        return self

    def verify(self, timeout_sec: float) -> VerificationResult:
        """Poll the property until it holds or the timeout runs out."""
        return self._poll_to_result(lambda: self._check(timeout_sec), timeout_sec)

    def _resolve_secret_id(
        self, timeout_sec: float
    ) -> tuple[str | None, VerificationStatus | None, str | None]:
        """Return ``(secret_id, status, reason)``; ``status`` is set iff ``secret_id`` is ``None``.

        Mirrors ``resource_property``'s own fail-closed convention: a
        ``selector`` that matches nothing is a real, observable absence (the
        source object was deleted) and fails closed rather than erroring out
        of the rollup's correctness denominator — a deleted
        ``secret_id_source`` must not silently exempt this check from
        counting. A genuine ``kubectl`` failure, or a matched object that
        doesn't carry the expected field, stays an environmental ``error``.
        """
        src = self.secret_id_source
        try:
            payload = get_resource(
                src.kind,
                src.resource_name,
                selector=src.selector,
                namespace=src.namespace,
                kubeconfig=self.kubeconfig,
                context=self.context,
                timeout=single_call_timeout(timeout_sec),
            )
        except Exception as exc:  # noqa: BLE001 - a kubectl failure is a check error
            return None, "error", f"kubectl get {src.kind} failed: {exc}"

        items = payload.get("items")
        objects = items if isinstance(items, list) else [payload]
        if not objects:
            return None, "fail", f"no {src.kind} matched"

        matches = _compile(src.path).find(objects[0])
        if not matches:
            return None, "error", f"path {src.path!r} did not resolve on the matched {src.kind}"
        return str(matches[0].value), None, None

    def _check(self, timeout_sec: float) -> tuple[VerificationStatus, str, dict[str, Any] | None]:
        """One evaluation pass: resolve the secret id, read gcloud, apply the operator."""
        secret_id, resolve_status, resolve_reason = self._resolve_secret_id(timeout_sec)
        if secret_id is None:
            assert resolve_status is not None  # guaranteed whenever secret_id is None
            return resolve_status, resolve_reason or "could not resolve a secret id", None

        gcloud_timeout = single_call_timeout(timeout_sec)
        try:
            if self.field == "state":
                info = describe_secret_version(
                    self.project_id, secret_id, self.version, timeout=gcloud_timeout
                )
                actual: Any = info.get("state")
            else:
                actual = access_secret_version(
                    self.project_id, secret_id, self.version, timeout=gcloud_timeout
                )
        except Exception as exc:  # noqa: BLE001 - a gcloud failure is a check error
            return "error", f"gcloud secrets versions {self.field!r} failed: {exc}", None

        raw = {"secret_id": secret_id, "version": self.version, "field": self.field}
        ok, reason = _apply_op(self.op, actual, self.value)
        return ("pass" if ok else "fail"), f"{secret_id}@{self.version}: {reason}", raw
