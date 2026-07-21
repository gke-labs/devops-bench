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

Each top-level evaluation races a single monotonic deadline: ``wait_for_condition``
(the chaos path) establishes one, and ``run_entry`` establishes one per entry.
Sequence nodes consume the deadline serially and fail fast (later children are
recorded as skipped); quantifier nodes (``all``/``parallel``, ``any``, ``none``)
hand each child the full remaining deadline and combine the results. Leaf
evaluation is mode-aware: ``converge`` consumes the remaining deadline via
``leaf.verify(remaining)``, ``assert`` evaluates once via ``leaf.verify(0.0)``,
and ``hold`` samples over a window. The mode is threaded down as a ``_ModeCtx``.
"""

from __future__ import annotations

import time
from concurrent.futures import ThreadPoolExecutor
from concurrent.futures import wait as futures_wait
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any, Literal

from devops_bench.verification.base import BaseVerifier, VerificationResult
from devops_bench.verification.rollup import EvaluatedEntry
from devops_bench.verification.spec import (
    AllSpec,
    AnySpec,
    NoneSpec,
    ParallelSpec,
    SequenceSpec,
    VerificationSpec,
)

if TYPE_CHECKING:
    from devops_bench.tasks.schema import VerificationEntry

__all__ = ["VerifierAgent"]

_MAX_PARALLEL_WORKERS = 8

# A leaf invoked with less than this many seconds left on the deadline is
# short-circuited as timed out. Avoids issuing useless ``kubectl wait
# --timeout=0.001s`` calls at the tail of the budget.
_MIN_LEAF_BUDGET_SECONDS = 1.0

# Hold-mode defaults used when an entry does not override the window / interval.
_DEFAULT_HOLD_WINDOW_SEC = 30.0
_DEFAULT_HOLD_INTERVAL_SEC = 5.0

# Default evaluation mode inferred from an entry's role when it sets no explicit
# ``mode``. An explicit mode on the entry always wins.
_DEFAULT_MODE_FOR_ROLE: dict[str, str] = {"objective": "converge", "safeguard": "assert"}


@dataclass(frozen=True)
class _ModeCtx:
    """Per-entry evaluation context threaded through the dispatch tree.

    ``mode`` is ``None`` on the ``wait_for_condition`` (chaos) path, which means
    "converge" at the leaf — preserving that method's original behavior exactly.
    """

    mode: str | None
    hold_window_sec: float
    hold_poll_interval_sec: float


_CONVERGE_CTX = _ModeCtx(
    mode=None,
    hold_window_sec=_DEFAULT_HOLD_WINDOW_SEC,
    hold_poll_interval_sec=_DEFAULT_HOLD_INTERVAL_SEC,
)


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

    Two entry points establish an evaluation: :meth:`wait_for_condition` (the
    chaos path, always ``converge``) and :meth:`run_entry` (a single typed
    entry, evaluated under its own mode). Each establishes one monotonic
    deadline; compound nodes propagate it without rebudgeting, and leaves
    consume it according to the entry's mode. The agent holds no per-run
    mutable state: the ``_ModeCtx`` is threaded as a parameter rather than
    stored on ``self`` (quantifier children run in a thread pool).
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
        return self._run(node, deadline, ctx=_CONVERGE_CTX)

    def run_entry(
        self,
        entry: VerificationEntry,
        node: Any,
        timeout_sec: float = 120,
    ) -> EvaluatedEntry:
        """Evaluate one already-parsed entry check under the entry's mode.

        The caller substitutes placeholders in ``entry.check`` and parses it into
        ``node`` before this call (mirroring how the harness resolves specs). The
        effective mode is the entry's explicit ``mode`` or, if unset, the default
        for its role. Hold window / interval fall back to module defaults.

        Args:
            entry: The typed verification entry (metadata only is read here).
            node: The parsed check tree for ``entry.check``.
            timeout_sec: Total wall-clock budget for this entry's evaluation.

        Returns:
            An :class:`~devops_bench.verification.rollup.EvaluatedEntry` pairing
            the entry's role/severity/weight with its aggregated result, safe to
            collect in any order for :func:`~devops_bench.verification.rollup.rollup`.
        """
        mode = entry.mode or _DEFAULT_MODE_FOR_ROLE[entry.role]
        window = (
            entry.hold_window_sec if entry.hold_window_sec is not None else _DEFAULT_HOLD_WINDOW_SEC
        )
        interval = (
            entry.hold_poll_interval_sec
            if entry.hold_poll_interval_sec is not None
            else _DEFAULT_HOLD_INTERVAL_SEC
        )
        ctx = _ModeCtx(mode=mode, hold_window_sec=window, hold_poll_interval_sec=interval)
        deadline = time.monotonic() + timeout_sec
        result = self._run(node, deadline, ctx=ctx)
        return EvaluatedEntry(
            name=entry.name,
            role=entry.role,
            severity=entry.severity,
            weight=entry.weight,
            result=result,
        )

    def _run(self, node: Any, deadline: float, *, ctx: _ModeCtx) -> VerificationResult:
        """Dispatch a node against the shared deadline under a mode context."""
        if isinstance(node, SequenceSpec):
            return self._run_sequence(node, deadline, ctx=ctx)
        if isinstance(node, ParallelSpec | AllSpec):
            return self._run_quantified(node, deadline, "all", ctx=ctx)
        if isinstance(node, AnySpec):
            return self._run_quantified(node, deadline, "any", ctx=ctx)
        if isinstance(node, NoneSpec):
            return self._run_quantified(node, deadline, "none", ctx=ctx)
        return self._run_leaf(node, deadline, ctx=ctx)

    def _run_leaf(self, node: Any, deadline: float, *, ctx: _ModeCtx) -> VerificationResult:
        """Run a leaf verifier under the entry's evaluation mode.

        Short-circuits when the remaining budget is below
        :data:`_MIN_LEAF_BUDGET_SECONDS` so we never issue a useless
        sub-second ``kubectl wait`` at the tail of the deadline. ``assert``
        evaluates once with a zero budget; ``hold`` samples over a window;
        ``converge`` (and the ``None`` mode used by the chaos path) hands the
        leaf the full remaining budget — the original behavior.
        """
        remaining = deadline - time.monotonic()
        if remaining < _MIN_LEAF_BUDGET_SECONDS:
            return _timed_out(node, "deadline exhausted before evaluation")
        if ctx.mode == "assert":
            return node.verify(0.0)
        if ctx.mode == "hold":
            return self._hold(node, deadline, ctx.hold_window_sec, ctx.hold_poll_interval_sec)
        return node.verify(remaining)

    def _hold(
        self, node: Any, deadline: float, window_sec: float, interval_sec: float
    ) -> VerificationResult:
        """Sample ``node.verify(0)`` repeatedly; every sample must pass.

        Stops at the first failing sample, or once the hold window or the
        overall deadline is reached. Uses ``time.monotonic`` only, so the
        runner and its leaves share a single clock.

        Args:
            node: Leaf verifier to sample.
            deadline: Absolute monotonic deadline; sampling stops at the
                earlier of the hold window or this deadline.
            window_sec: Seconds to keep sampling.
            interval_sec: Seconds to sleep between samples.

        Returns:
            A failed result on the first failing sample; a successful result
            if every sample up to the window/deadline passes.
        """
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
        self, node: SequenceSpec, deadline: float, *, ctx: _ModeCtx
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
            res = self._run(child, deadline, ctx=ctx)
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

    def _run_quantified(
        self,
        node: Any,
        deadline: float,
        quantifier: Literal["all", "any", "none"],
        *,
        ctx: _ModeCtx,
    ) -> VerificationResult:
        """Run children concurrently and combine by ``quantifier``.

        ``all`` requires every child to pass (the old ``parallel`` semantics);
        ``any`` requires at least one; ``none`` requires zero. An empty ``checks``
        list is vacuously true for ``all`` and ``none`` and false for ``any``.

        Each child sees the full remaining deadline. A child still blocked when
        the deadline hits is bounded by the ``remaining`` value handed to its
        ``verify`` call. A leaf that unexpectedly raises becomes a failed child
        result so one bad leaf does not abort the group.
        """
        start = time.monotonic()
        if not node.checks:
            vacuous = quantifier != "any"
            return VerificationResult(
                success=vacuous,
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
                ex.submit(self._run, child, deadline, ctx=ctx): i
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
        ok_count = sum(1 for r in results if r.success)
        if quantifier == "all":
            ok = ok_count == len(results)
        elif quantifier == "any":
            ok = ok_count > 0
        else:  # none
            ok = ok_count == 0
        reasons = [f"[{i}] {'ok' if r.success else 'fail'}" for i, r in enumerate(results)]
        return VerificationResult(
            success=ok,
            elapsed_time=time.monotonic() - start,
            reason=f"{quantifier}: {'; '.join(reasons)}",
            name=node.name,
            children=results,
        )
