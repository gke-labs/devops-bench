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

"""Verifier that asserts a property of one or more Kubernetes resources."""

from __future__ import annotations

import re
from typing import Any, Literal

from pydantic import model_validator

from devops_bench.core import SubprocessError, get_logger
from devops_bench.k8s import get_resource
from devops_bench.verification.base import VERIFIERS, BaseVerifier, VerificationResult

__all__ = ["ResourcePropertyVerifier"]

_log = get_logger("verification.resource_property")

_Op = Literal["eq", "ne", "gt", "gte", "lt", "lte", "exists", "absent", "contains", "matches"]
_Quantifier = Literal["all", "any", "none"]


def _split_path(path: str) -> list[str]:
    """Split a dotted/JSONPath-ish accessor into traversal segments.

    Handles ``$.`` prefix (JSONPath), dotted keys, and ``[n]`` array indices.

    Args:
        path: Path string, e.g. ``"spec.replicas"`` or ``"$.spec.containers[0].name"``.

    Returns:
        Ordered list of key/index strings.
    """
    if path.startswith("$."):
        path = path[2:]
    segments: list[str] = []
    for token in re.split(r"\.|(?=\[)", path):
        clean = token.strip("[]")
        if clean:
            segments.append(clean)
    return segments


def _resolve_path(obj: Any, path: str) -> tuple[bool, Any]:
    """Walk ``path`` through ``obj`` and return ``(found, value)``.

    Args:
        obj: Root object (dict, list, or scalar).
        path: Dotted/JSONPath-ish accessor.

    Returns:
        ``(True, value)`` when the path resolves; ``(False, None)`` when any
        segment is missing.
    """
    current = obj
    for segment in _split_path(path):
        if isinstance(current, dict):
            if segment not in current:
                return False, None
            current = current[segment]
        elif isinstance(current, list):
            try:
                current = current[int(segment)]
            except (ValueError, IndexError):
                return False, None
        else:
            return False, None
    return True, current


def _eval_op(value: Any, op: _Op, expected: Any) -> bool:
    """Evaluate a comparison operation between ``value`` and ``expected``.

    Args:
        value: The resolved value from the resource.
        op: The comparison operator.
        expected: The expected value from the spec.

    Returns:
        True when the comparison holds.
    """
    if op == "eq":
        return value == expected
    if op == "ne":
        return value != expected
    if op in ("gt", "gte", "lt", "lte"):
        try:
            fv, fe = float(value), float(expected)
        except (TypeError, ValueError):
            fv, fe = None, None
        if op == "gt":
            return fv is not None and fv > fe
        if op == "gte":
            return fv is not None and fv >= fe
        if op == "lt":
            return fv is not None and fv < fe
        if op == "lte":
            return fv is not None and fv <= fe
    if op == "contains":
        if isinstance(value, str):
            return str(expected) in value
        if isinstance(value, (list, tuple)):
            return expected in value
        return False
    if op == "matches":
        if value is None:
            return False
        return bool(re.search(str(expected), str(value)))
    return False


@VERIFIERS.register("resource_property")
class ResourcePropertyVerifier(BaseVerifier):
    """Verify a property on one or more Kubernetes resources.

    Uses :func:`devops_bench.k8s.get_resource` to fetch the target(s), walks
    the ``path`` accessor, and evaluates ``op`` against ``value``. Polling is
    via :meth:`~devops_bench.verification.base.BaseVerifier._poll_to_result`
    so this verifier composes cleanly with the ``converge`` and ``assert``
    execution modes.

    Attributes:
        type: Discriminator literal, always ``"resource_property"``.
        kind: Kubernetes resource kind (e.g. ``"deployment"``, ``"pod"``).
        name: Specific resource name. Exactly one of ``name`` or ``selector``
            must be provided.
        selector: Label selector (``-l``) matching multiple resources. Exactly
            one of ``name`` or ``selector`` must be provided.
        namespace: Optional namespace; defaults to the active context.
        path: Dotted or JSONPath-ish accessor into the resource object
            (e.g. ``"spec.replicas"`` or ``"$.status.readyReplicas"``).
        op: Comparison operator. ``"exists"`` / ``"absent"`` do not use
            ``value``; all others do.
        value: Expected value for comparison operators.
        quantifier: How to evaluate when a selector matches multiple objects.
            ``"all"`` (default) requires every object to pass; ``"any"``
            requires at least one; ``"none"`` requires none to pass.
    """

    type: Literal["resource_property"] = "resource_property"
    kind: str
    name: str | None = None
    selector: str | None = None
    namespace: str | None = None
    path: str
    op: _Op
    value: Any = None
    quantifier: _Quantifier = "all"

    @model_validator(mode="after")
    def _require_name_or_selector(self) -> ResourcePropertyVerifier:
        """Ensure exactly one of ``name`` or ``selector`` is provided."""
        if (self.name is None) == (self.selector is None):
            raise ValueError("exactly one of 'name' or 'selector' is required")
        return self

    def verify(self, timeout_sec: float) -> VerificationResult:
        """Poll until the resource property satisfies the condition.

        Args:
            timeout_sec: Maximum seconds to keep polling.

        Returns:
            A result reflecting the last observed property value.
        """
        return self._poll_to_result(self._check, timeout_sec)

    def _get_objects(self) -> list[dict[str, Any]]:
        """Fetch the target resource(s) as a list of raw dicts.

        Returns:
            A list with a single item for a named resource; the ``items``
            list for a selector-based query.

        Raises:
            SubprocessError: If kubectl exits non-zero.
            ValueError: If the JSON response cannot be parsed.
        """
        if self.name:
            obj = get_resource(
                self.kind,
                self.name,
                namespace=self.namespace,
                kubeconfig=self.kubeconfig,
            )
            return [obj]
        result = get_resource(
            self.kind,
            selector=self.selector,
            namespace=self.namespace,
            kubeconfig=self.kubeconfig,
        )
        return result.get("items", [])

    def _check_one(self, obj: dict[str, Any]) -> tuple[bool, str]:
        """Evaluate the path/op/value condition against a single object.

        Args:
            obj: Raw resource dict.

        Returns:
            ``(success, reason)`` pair.
        """
        found, val = _resolve_path(obj, self.path)
        if self.op == "exists":
            ok = found
            return ok, f"path {self.path!r} {'exists' if ok else 'not found'}"
        if self.op == "absent":
            ok = not found
            return ok, f"path {self.path!r} {'absent' if ok else 'present (expected absent)'}"
        if not found:
            return False, f"path {self.path!r} not found"
        ok = _eval_op(val, self.op, self.value)
        return ok, f"{self.path}={val!r} {self.op} {self.value!r} -> {ok}"

    def _check(self) -> tuple[bool, str, dict[str, Any] | None]:
        """Fetch resources and evaluate the quantified condition.

        Returns:
            ``(success, reason, raw)`` triple compatible with
            :meth:`~devops_bench.verification.base.BaseVerifier._poll_to_result`.
        """
        try:
            objects = self._get_objects()
        except SubprocessError as exc:
            stderr = (exc.stderr or "").strip()
            _log.warning("failed to get %s: %s", self.kind, stderr)
            return False, f"failed to get {self.kind}: {stderr}", None
        except ValueError:
            _log.warning("failed to parse JSON for %s", self.kind)
            return False, f"failed to parse JSON for {self.kind}", None

        if not objects:
            if self.quantifier == "none":
                return True, f"no {self.kind} objects matched (none requirement satisfied)", None
            return False, f"no {self.kind} objects matched", None

        check_results = [self._check_one(obj) for obj in objects]
        passed = sum(1 for ok, _ in check_results if ok)
        total = len(check_results)
        raw: dict[str, Any] = {"objects_checked": total, "passed": passed}

        if self.quantifier == "all":
            ok = passed == total
        elif self.quantifier == "any":
            ok = passed > 0
        else:  # none
            ok = passed == 0

        reason = f"{self.kind} {self.quantifier}: {passed}/{total} passed"
        if not ok:
            first_fail = next((msg for success, msg in check_results if not success), None)
            if first_fail:
                reason += f"; {first_fail}"

        return ok, reason, raw
