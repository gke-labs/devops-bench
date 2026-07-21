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

"""Verifier that asserts a property of one or more Kubernetes resources via JSONPath."""

from __future__ import annotations

import re
from typing import Any, Literal

from jsonpath_ng.exceptions import JSONPathError
from jsonpath_ng.ext import parse as jsonpath_parse
from pydantic import PrivateAttr, model_validator

from devops_bench.core import SubprocessError, get_logger
from devops_bench.k8s import get_resource
from devops_bench.verification.base import VERIFIERS, BaseVerifier, VerificationResult

__all__ = ["ResourcePropertyVerifier"]

_log = get_logger("verification.resource_property")

_Op = Literal["eq", "ne", "gt", "gte", "lt", "lte", "exists", "absent", "contains", "matches"]
_Quantifier = Literal["all", "any", "none"]

# Ops that read and compare a value at ``path``; each requires ``path`` to be set.
_SCALAR_OPS: frozenset[str] = frozenset(
    {"eq", "ne", "gt", "gte", "lt", "lte", "contains", "matches"}
)


def _eval_op(value: Any, op: str, expected: Any) -> bool:
    """Evaluate a scalar comparison between a resolved value and the expected value."""
    if op == "eq":
        return value == expected
    if op == "ne":
        return value != expected
    if op in ("gt", "gte", "lt", "lte"):
        try:
            fv, fe = float(value), float(expected)
        except (TypeError, ValueError):
            return False
        if op == "gt":
            return fv > fe
        if op == "gte":
            return fv >= fe
        if op == "lt":
            return fv < fe
        return fv <= fe
    if op == "contains":
        if isinstance(value, str):
            return str(expected) in value
        if isinstance(value, list | tuple):
            return expected in value
        return False
    if op == "matches":
        return value is not None and bool(re.search(str(expected), str(value)))
    return False


@VERIFIERS.register("resource_property")
class ResourcePropertyVerifier(BaseVerifier):
    """Verify a property of one or more live Kubernetes objects.

    Fetches the target(s) via :func:`devops_bench.k8s.get_resource`, resolves
    ``path`` with real JSONPath (``jsonpath-ng``, extended parser for filter
    predicates), and evaluates ``op`` against ``value``. Polls via
    :meth:`~devops_bench.verification.base.BaseVerifier._poll_to_result` so it
    composes with converge/assert/hold modes.

    Match-count resolution: 0 matches means "not found"; exactly 1 match compares
    that value; more than 1 passes ``exists``/``absent`` (by count) but fails a
    scalar op with "ambiguous match".

    Attributes:
        type: Discriminator literal, always ``"resource_property"``.
        kind: Kubernetes resource kind (e.g. ``"deployment"``, ``"namespace"``).
        name: Specific resource name. At most one of ``name`` / ``selector``;
            omitting both lists every object of the kind in the namespace.
        selector: Label selector (``-l``). At most one of ``name`` / ``selector``.
        namespace: Optional namespace; defaults to the active context.
        path: Optional JSONPath accessor. Omit for object-level ``exists`` /
            ``absent`` (does any matching object exist?).
        op: Comparison operator. ``exists`` / ``absent`` ignore ``value``.
        value: Expected value for comparison operators.
        quantifier: How to combine when a selector matches multiple objects and a
            ``path`` is given. ``all`` (default) / ``any`` / ``none``.
    """

    type: Literal["resource_property"] = "resource_property"
    kind: str
    name: str | None = None
    selector: str | None = None
    namespace: str | None = None
    path: str | None = None
    op: _Op
    value: Any = None
    quantifier: _Quantifier = "all"

    _compiled: Any = PrivateAttr(default=None)

    @model_validator(mode="after")
    def _validate(self) -> ResourcePropertyVerifier:
        """Enforce at-most-one target, require ``path`` for scalar ops, compile JSONPath."""
        if self.name is not None and self.selector is not None:
            raise ValueError("provide at most one of 'name' or 'selector', not both")
        if self.op in _SCALAR_OPS and self.path is None:
            raise ValueError(f"op {self.op!r} requires a 'path'")
        if self.path is not None:
            try:
                self._compiled = jsonpath_parse(self.path)
            except JSONPathError as exc:
                raise ValueError(f"invalid JSONPath {self.path!r}: {exc}") from exc
        return self

    def verify(self, timeout_sec: float) -> VerificationResult:
        """Poll until the resource property satisfies the condition."""
        return self._poll_to_result(self._check, timeout_sec)

    def _get_objects(self) -> list[dict[str, Any]]:
        """Fetch the target object(s) as a list of raw dicts."""
        if self.name is not None:
            obj = get_resource(
                self.kind, self.name, namespace=self.namespace, kubeconfig=self.kubeconfig
            )
            return [obj]
        result = get_resource(
            self.kind, selector=self.selector, namespace=self.namespace, kubeconfig=self.kubeconfig
        )
        return result.get("items", [])

    def _check_one(self, obj: dict[str, Any]) -> tuple[bool, str]:
        """Evaluate the path/op/value condition against a single object."""
        matches = self._compiled.find(obj)
        if self.op == "exists":
            return (len(matches) > 0), f"path {self.path!r} {'exists' if matches else 'not found'}"
        if self.op == "absent":
            return (
                len(matches) == 0
            ), f"path {self.path!r} {'absent' if not matches else 'present'}"
        if not matches:
            return False, f"path {self.path!r} not found"
        if len(matches) > 1:
            return False, f"ambiguous match: {len(matches)} results for path {self.path!r}"
        val = matches[0].value
        ok = _eval_op(val, self.op, self.value)
        return ok, f"{self.path}={val!r} {self.op} {self.value!r} -> {ok}"

    def _check(self) -> tuple[bool, str, dict[str, Any] | None]:
        """Fetch resources and evaluate the (possibly quantified) condition."""
        try:
            objects = self._get_objects()
        except SubprocessError as exc:
            stderr = (exc.stderr or "").strip()
            if self.name is not None and self.path is None and "not found" in stderr.lower():
                # A named-object 404 is a definite object-level signal.
                if self.op == "absent":
                    return True, f"{self.kind}/{self.name} not found (absent satisfied)", None
                if self.op == "exists":
                    return False, f"{self.kind}/{self.name} not found", None
            _log.warning("failed to get %s: %s", self.kind, stderr)
            return False, f"failed to get {self.kind}: {stderr}", None
        except ValueError:
            return False, f"failed to parse JSON for {self.kind}", None

        # Object-level existence (no path): the object COUNT is what matters.
        if self.path is None:
            count = len(objects)
            if self.op == "exists":
                return (count > 0), f"{self.kind}: {count} object(s) present", None
            return (count == 0), f"{self.kind}: {count} object(s) present (expected none)", None

        # Property checks (path set), quantified across the matched objects.
        if not objects:
            if self.quantifier == "none":
                return True, f"no {self.kind} objects matched (none satisfied)", None
            return False, f"no {self.kind} objects matched", None

        results = [self._check_one(obj) for obj in objects]
        passed = sum(1 for ok, _ in results if ok)
        total = len(results)
        raw: dict[str, Any] = {"objects_checked": total, "passed": passed}
        if self.quantifier == "all":
            ok = passed == total
        elif self.quantifier == "any":
            ok = passed > 0
        else:  # none
            ok = passed == 0
        reason = f"{self.kind} {self.quantifier}: {passed}/{total} passed"
        if not ok:
            first_fail = next((msg for success, msg in results if not success), None)
            if first_fail:
                reason += f"; {first_fail}"
        return ok, reason, raw
