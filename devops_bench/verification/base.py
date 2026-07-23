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

"""Result model, abstract base, and registry for verification checks.

Each leaf verifier and each compound spec (``sequence`` / ``parallel``)
registers itself in the :data:`VERIFIERS` registry by its ``type`` literal.
"""

from __future__ import annotations

import time
from abc import ABC, abstractmethod
from collections.abc import Callable
from typing import Any, Literal

from pydantic import BaseModel, Field

from devops_bench.core import Registry
from devops_bench.k8s import poll_until

__all__ = ["Mode", "VERIFIERS", "VerificationResult", "BaseVerifier"]

# Execution mode for a leaf verifier.
#
# converge  -- verify(timeout_sec=N): keep polling until success or deadline.
# assert    -- verify(timeout_sec=0): evaluate exactly once, never sleep.
# hold      -- sample verify(0) repeatedly; every sample must pass.
# unchanged -- NOT IMPLEMENTED: requires a pre-agent snapshot protocol.
#              The first consumer (unchanged_outside) is not in this PR.
Mode = Literal["converge", "assert", "unchanged", "hold"]

# Registry keyed by the ``type`` discriminator literal. Entry-point discovery
# lets external packages register a verifier without touching this tree.
VERIFIERS: Registry[type[BaseModel]] = Registry(
    "verifiers", entry_point_group="devops_bench.verifiers"
)


class VerificationResult(BaseModel):
    """Structured outcome of a verification check.

    Compound nodes (sequence/parallel) populate ``children`` with one entry per
    member; leaf checks populate ``raw`` with kubectl diagnostics. ``name`` is
    echoed from the originating spec node's optional label.

    Attributes:
        success: True when every condition the check covers was met.
        elapsed_time: Wall-clock seconds spent evaluating the check.
        reason: Human-readable summary of the outcome or failure.
        name: Optional label echoed from the spec node, for result rendering.
        children: Per-member results from compound (sequence/parallel) nodes.
        raw: Leaf-only kubectl diagnostics or supporting data.
        weight: Contribution weight used by the rollup; default 1.0. Echoed
            from the originating leaf's :attr:`BaseVerifier.weight` so the
            result tree is self-describing for downstream scoring. The runner
            (:meth:`~devops_bench.verification.runner.VerifierAgent._run_leaf`)
            stamps the leaf's configured weight onto the result after
            evaluation, so a custom verifier that builds this result directly
            (bypassing :meth:`BaseVerifier._poll_to_result`) does not need to
            forward ``weight`` itself — the runner is authoritative.
    """

    success: bool
    elapsed_time: float
    reason: str
    name: str | None = None
    children: list[VerificationResult] = Field(default_factory=list)
    raw: dict | None = None
    weight: float = 1.0


VerificationResult.model_rebuild()


class BaseVerifier(BaseModel, ABC):
    """Abstract base for a single leaf verification check.

    Concrete verifiers carry a ``type`` literal, an optional ``name`` for result
    labeling, and implement :meth:`verify`.

    Attributes:
        name: Optional label echoed onto the result; metadata, never structural.
        kubeconfig: Optional path to a kubeconfig file, forwarded to the
            ``devops_bench.k8s`` wrappers so a check can target a specific
            cluster. When ``None`` the wrappers use the ambient kubeconfig.
        weight: Contribution weight used by the rollup when summing pass/fail
            fractions across leaves. Default 1.0 (all leaves equal). Echoed
            onto the :class:`VerificationResult` so the tree is self-describing.
        mode: Explicit execution mode. When ``None`` the runner derives the
            mode from the parent :class:`~devops_bench.verification.entry.Role`:
            ``"objective"`` -> ``"converge"``;
            ``"safeguard"`` -> ``"assert"``. An explicit ``mode`` always wins
            over the role-derived default.
        hold_window_sec: Duration of the hold-mode sampling window; meaningful
            only when ``mode="hold"``. Defaults to 30 s.
        hold_interval_sec: Pause between hold-mode samples; meaningful only
            when ``mode="hold"``. Defaults to 5 s.
    """

    name: str | None = None
    kubeconfig: str | None = None
    weight: float = 1.0
    mode: Mode | None = None
    hold_window_sec: float = 30.0
    hold_interval_sec: float = 5.0

    @abstractmethod
    def verify(self, timeout_sec: float) -> VerificationResult:
        """Run the check and report the outcome.

        Args:
            timeout_sec: Maximum seconds the check may spend before giving up.

        Returns:
            The structured verification result.
        """
        raise NotImplementedError

    def _poll_to_result(
        self,
        check: Callable[[], tuple[bool, str, dict[str, Any] | None]],
        timeout_sec: float,
    ) -> VerificationResult:
        """Poll ``check`` to a :class:`VerificationResult`.

        Shared scaffolding for predicate-style verifiers: times the run, polls
        ``check`` via :func:`devops_bench.k8s.poll_until`, and folds the last
        observation into a result. Verifiers backed by a server-side watch
        (e.g. ``kubectl wait``) build their result directly instead.

        Args:
            check: Evaluated once per poll, returning ``(success, reason, raw)``
                where ``reason`` describes the latest observation and ``raw``
                carries optional diagnostics.
            timeout_sec: Maximum seconds to keep polling.

        Returns:
            A result whose ``success`` reflects whether the predicate held
            before the timeout, carrying the last observed ``reason`` and
            ``raw``.
        """
        start_time = time.monotonic()
        last: dict[str, Any] = {"reason": "", "raw": None}

        def predicate() -> bool:
            success, reason, raw = check()
            last["reason"] = reason
            last["raw"] = raw
            return success

        converged = poll_until(predicate, timeout_sec=timeout_sec)
        return VerificationResult(
            success=converged,
            elapsed_time=time.monotonic() - start_time,
            reason=last["reason"],
            name=self.name,
            raw=last["raw"],
            weight=self.weight,
        )
