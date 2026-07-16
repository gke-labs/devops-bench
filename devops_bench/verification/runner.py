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

"""Deadline-based dispatcher that evaluates a verification specification.

The whole verification races a single monotonic deadline computed once at the
top of :meth:`VerifierAgent.wait_for_condition`. Sequence nodes consume the
deadline serially and fail fast (later children are recorded as skipped);
parallel nodes hand each child the full remaining deadline and AND the results.
Leaves consume the deadline directly via ``leaf.verify(remaining)``.

Mode dispatch is additive over this existing machinery: three of the four modes
(``converge``, ``assert``, ``hold``) are simply different ways to call the
existing ``verify()`` contract. ``unchanged`` is designed but not built; it
requires a pre-agent snapshot protocol that is not in this PR.
"""

from __future__ import annotations

import time
from concurrent.futures import ThreadPoolExecutor
from concurrent.futures import wait as futures_wait
from typing import Any

from pydantic import BaseModel

from devops_bench.verification.base import BaseVerifier, VerificationResult
from devops_bench.verification.entry import VerificationEntry
from devops_bench.verification.rollup import EvaluatedEntry
from devops_bench.verification.spec import (
    ParallelSpec,
    SequenceSpec,
    VerificationSpec,
    parse_node,
)

__all__ = ["VerifierAgent"]

_MAX_PARALLEL_WORKERS = 8

# A leaf invoked with less than this many seconds left on the deadline is
# short-circuited as timed out. Avoids issuing useless ``kubectl wait
# --timeout=0.001s`` calls at the tail of the budget.
_MIN_LEAF_BUDGET_SECONDS = 1.0

# Hold-mode defaults used when the leaf does not override window/interval.
_DEFAULT_HOLD_WINDOW_SEC = 30.0
_DEFAULT_HOLD_INTERVAL_SEC = 5.0

# Default mode inferred from a VerificationEntry's role when the leaf carries
# no explicit ``mode``. Explicit mode on the leaf always wins.
_ROLE_DEFAULT_MODE: dict[str, str] = {
    "correctness": "converge",
    "safety": "assert",
    "catastrophic": "assert",
}


def _node_name(node: Any) -> str | None:
    """Echo the optional ``name`` label from a spec node, if any."""
    return getattr(node, "name", None)


def _timed_out(node: Any, reason: str) -> VerificationResult:
    """Build a failed result for a node that ran into the deadline."""
    return VerificationResult(
        success=False,
        elapsed_time=0.0,
        reason=reason,
        name=_node_name(node),
    )


def _skipped(node: Any, reason: str) -> VerificationResult:
    """Build a failed result for a node skipped by sequence fail-fast / deadline."""
    return VerificationResult(
        success=False,
        elapsed_time=0.0,
        reason=reason,
        name=_node_name(node),
    )


class VerifierAgent:
    """Evaluate single or compound verification specs against cluster state.

    All evaluations share a single monotonic deadline established by
    :meth:`wait_for_condition`. Compound nodes propagate the deadline without
    rebudgeting; leaves consume it directly via their ``verify`` method.

    The mode dispatch layer is additive: ``converge`` is the existing behavior;
    ``assert`` calls ``verify(0)``, evaluated exactly once; ``hold`` repeatedly
    calls ``verify(0)`` across a window and requires every sample to pass.
    ``unchanged`` is intentionally not implemented (see :meth:`_run_leaf`).
    """

    def wait_for_condition(
        self,
        spec: VerificationSpec | Any,
        timeout_sec: float = 120,
    ) -> VerificationResult:
        """Wait for a spec to hold within ``timeout_sec``.

        Args:
            spec: A :class:`VerificationSpec`, an already-parsed node, or a raw
                mapping the spec validator can parse.
            timeout_sec: Total wall-clock budget shared across the (possibly
                nested) checks. A single monotonic deadline is computed from
                this once at the top.

        Returns:
            The aggregated verification result.
        """
        if isinstance(spec, VerificationSpec):
            node: Any = spec.root
        elif isinstance(spec, SequenceSpec | ParallelSpec | BaseVerifier):
            node = spec  # already-parsed node (compound or leaf)
        else:
            node = VerificationSpec(spec).root  # raw mapping -> parse

        deadline = time.monotonic() + timeout_sec
        return self._run(node, deadline, default_mode=None)

    def run_entry(
        self,
        entry: VerificationEntry,
        timeout_sec: float = 120,
    ) -> EvaluatedEntry:
        """Evaluate a typed entry with its role-derived default mode.

        ``entry.spec`` must already have placeholders substituted before this
        call; ``parse_node`` is applied here to produce the concrete spec tree.

        Args:
            entry: Typed entry. ``entry.spec`` is the (already substituted) raw
                spec dict, or an already-parsed :class:`pydantic.BaseModel` node.
            timeout_sec: Total wall-clock budget for the entry's spec tree.

        Returns:
            An :class:`~devops_bench.verification.rollup.EvaluatedEntry` pairing
            the entry's role and name with its aggregated result tree. Bundling
            the role with the result means the returned objects can be collected
            in any order and passed to :func:`~devops_bench.verification.rollup.rollup`
            without risk of pairing the wrong role to the wrong result.
        """
        node: Any = entry.spec if isinstance(entry.spec, BaseModel) else parse_node(entry.spec)
        default_mode = _ROLE_DEFAULT_MODE.get(entry.role, "converge")
        deadline = time.monotonic() + timeout_sec
        result = self._run(node, deadline, default_mode=default_mode)
        return EvaluatedEntry(name=entry.name, role=entry.role, result=result)

    def _run(self, node: Any, deadline: float, *, default_mode: str | None) -> VerificationResult:
        """Dispatch a node against the shared deadline."""
        if isinstance(node, SequenceSpec):
            return self._run_sequence(node, deadline, default_mode=default_mode)
        if isinstance(node, ParallelSpec):
            return self._run_parallel(node, deadline, default_mode=default_mode)
        return self._run_leaf(node, deadline, default_mode=default_mode)

    def _run_leaf(
        self, node: Any, deadline: float, *, default_mode: str | None
    ) -> VerificationResult:
        """Run a leaf verifier with mode dispatch.

        Determines the effective mode from (in priority order):
        1. An explicit ``mode`` field on the leaf verifier.
        2. The ``default_mode`` derived from the parent entry's role.
        3. ``"converge"`` (the original behavior) when both are absent.

        Short-circuits when the remaining budget is below
        :data:`_MIN_LEAF_BUDGET_SECONDS` so we never issue a useless
        sub-second ``kubectl wait`` at the tail of the deadline.

        Raises:
            NotImplementedError: When the effective mode is ``"unchanged"``.
                That mode requires a pre-agent snapshot protocol; the first
                consumer (``unchanged_outside``) is not in this PR.
        """
        remaining = deadline - time.monotonic()
        if remaining < _MIN_LEAF_BUDGET_SECONDS:
            return _timed_out(node, "deadline exhausted before evaluation")

        explicit_mode: str | None = getattr(node, "mode", None)
        effective_mode: str = explicit_mode or default_mode or "converge"

        if effective_mode == "unchanged":
            raise NotImplementedError(
                "Mode 'unchanged' is not implemented: it requires a pre-agent snapshot "
                "protocol. The first consumer (unchanged_outside) is not in this PR."
            )
        if effective_mode == "assert":
            return node.verify(0.0)
        if effective_mode == "hold":
            return self._hold(node, deadline)
        # Default / converge: hand the leaf the full remaining budget.
        return node.verify(remaining)

    def _hold(self, node: Any, deadline: float) -> VerificationResult:
        """Sample ``node.verify(0)`` repeatedly; every sample must pass.

        The sampling window and interval come from the node's
        ``hold_window_sec`` / ``hold_interval_sec`` fields (if present) or the
        module-level defaults. The loop exits early when the deadline is hit.

        Args:
            node: Leaf verifier to sample.
            deadline: Absolute monotonic deadline; sampling stops at the earlier
                of the hold window or this deadline.

        Returns:
            A failed result on the first failing sample; a successful result if
            every sample up to the window/deadline passes.
        """
        _window = getattr(node, "hold_window_sec", None)
        window_sec: float = _window if _window is not None else _DEFAULT_HOLD_WINDOW_SEC
        _interval = getattr(node, "hold_interval_sec", None)
        interval_sec: float = _interval if _interval is not None else _DEFAULT_HOLD_INTERVAL_SEC

        start = time.monotonic()
        window_end = start + window_sec
        samples = 0

        while True:
            result = node.verify(0.0)
            samples += 1
            if not result.success:
                return VerificationResult(
                    success=False,
                    elapsed_time=time.monotonic() - start,
                    reason=f"hold failed at sample {samples}: {result.reason}",
                    name=_node_name(node),
                    raw=result.raw,
                )
            now = time.monotonic()
            if now >= window_end or now >= deadline:
                break
            sleep_time = min(interval_sec, window_end - now, deadline - now)
            if sleep_time > 0:
                time.sleep(sleep_time)

        elapsed = time.monotonic() - start
        return VerificationResult(
            success=True,
            elapsed_time=elapsed,
            reason=f"hold passed: {samples} sample(s) over {elapsed:.1f}s",
            name=_node_name(node),
        )

    def _run_sequence(
        self, node: SequenceSpec, deadline: float, *, default_mode: str | None
    ) -> VerificationResult:
        """Run children in order; stop and skip the rest on the first failure."""
        start = time.monotonic()
        children: list[VerificationResult] = []
        reasons: list[str] = []
        ok = True
        for i, child in enumerate(node.checks):
            if time.monotonic() >= deadline:
                children.append(_skipped(child, "deadline exhausted"))
                reasons.append(f"[{i}] skipped")
                ok = False
                continue
            res = self._run(child, deadline, default_mode=default_mode)
            children.append(res)
            if not res.success:
                ok = False
                reasons.append(f"[{i}] failed: {res.reason}")
                for j, rest in enumerate(node.checks[i + 1 :], start=i + 1):
                    children.append(_skipped(rest, "earlier step failed"))
                    reasons.append(f"[{j}] skipped")
                break  # fail-fast
            reasons.append(f"[{i}] succeeded")
        return VerificationResult(
            success=ok,
            elapsed_time=time.monotonic() - start,
            reason="; ".join(reasons),
            name=node.name,
            children=children,
        )

    def _run_parallel(
        self, node: ParallelSpec, deadline: float, *, default_mode: str | None
    ) -> VerificationResult:
        """Run children concurrently; each sees the full remaining deadline.

        A parallel child still blocked in ``kubectl wait`` / ``poll_until`` when
        the deadline hits is bounded by the ``remaining`` value handed to its
        ``verify`` call, so worker threads do not linger long past the deadline.
        A leaf that unexpectedly raises is converted to a failed child result so
        one bad leaf does not abort the rest of the group.
        """
        start = time.monotonic()
        if not node.checks:
            return VerificationResult(
                success=True,
                elapsed_time=time.monotonic() - start,
                reason="no checks",
                name=node.name,
                children=[],
            )
        results: list[VerificationResult] = [
            _timed_out(child, "deadline reached") for child in node.checks
        ]
        workers = min(_MAX_PARALLEL_WORKERS, len(node.checks))
        # ``cancel_futures=True`` (3.9+) drops queued-but-not-started futures so
        # an exhausted deadline does not block on workers we never want to wait
        # for. In-flight workers are still bounded by the deadline-aware
        # ``verify(remaining)`` call, so they cannot linger long.
        ex = ThreadPoolExecutor(max_workers=workers)
        try:
            futs = {
                ex.submit(self._run, child, deadline, default_mode=default_mode): i
                for i, child in enumerate(node.checks)
            }
            done, _ = futures_wait(futs, timeout=max(0.0, deadline - time.monotonic()))
            for f, i in futs.items():
                if f not in done:
                    continue
                try:
                    results[i] = f.result()
                except Exception as exc:  # noqa: BLE001 - convert to a failed child
                    results[i] = VerificationResult(
                        success=False,
                        elapsed_time=0.0,
                        reason=f"unhandled error: {exc}",
                        name=_node_name(node.checks[i]),
                    )
        finally:
            ex.shutdown(wait=False, cancel_futures=True)
        ok = all(r.success for r in results)
        reasons = [f"[{i}] {'ok' if r.success else 'fail'}" for i, r in enumerate(results)]
        return VerificationResult(
            success=ok,
            elapsed_time=time.monotonic() - start,
            reason="; ".join(reasons),
            name=node.name,
            children=results,
        )
