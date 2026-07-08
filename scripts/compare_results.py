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

"""Compare two ``results.json`` files and classify each difference."""

from __future__ import annotations

import argparse
import json
import sys
from dataclasses import dataclass, field
from typing import Any

__all__ = [
    "INTENDED",
    "MATCHED",
    "REGRESSION",
    "CompareError",
    "Difference",
    "TaskComparison",
    "align_records",
    "build_json_report",
    "compare",
    "compare_records",
    "has_regression",
    "main",
    "normalize_score_key",
    "normalize_scores",
    "normalize_whitespace",
    "render_report",
    "score_entry_success",
    "score_entry_value",
]

# --------------------------------------------------------------------------- #
# Intended-delta allowlist. Differences NOT covered here are regressions.
# --------------------------------------------------------------------------- #

#: Score keys whose numeric value may legitimately differ between the two
#: implementations.
INTENDED_METRIC_VALUE_DELTAS: frozenset[str] = frozenset(
    {
        "GroundingAccuracy",  # constraint dedup
        "ParameterRecallAccuracy",  # constraint dedup
        "DocRetrievalRate",  # missing-key guard
    }
)

#: When True, a ``Check:`` key present on one side but not the other is INTENDED:
#: only the checklist item text changed.
INTENDED_CHECKLIST_TEXT_DELTAS: bool = True

#: When True, a legacy ``status`` of ``None`` paired with any refactor status is
#: intended. A success<->failed flip (both sides non-None) is still a REGRESSION.
INTENDED_LEGACY_NULL_STATUS: bool = True

#: When True, a trajectory presence mismatch is intended; trajectory is never
#: diffed structurally.
INTENDED_TRAJECTORY_PRESENCE_DELTA: bool = True

#: Metrics whose presence/absence depends on the ``BENCH_USE_MCP`` read.
INTENDED_MCP_READ_METRICS: frozenset[str] = frozenset({"ToolInvocation"})

#: Top-level keys that are volatile or refactor-only schema additions and kept
#: out of the diff entirely.
VOLATILE_TOP_LEVEL_KEYS: frozenset[str] = frozenset(
    {
        "latency",
        "tokens",
        "trajectory",  # handled separately via presence-only check
        "error",
        "errors",
        "score",
        "capabilities_granted",
        "verification_parse_errors",
    }
)

_GEVAL_SUFFIX = " [GEval]"

# Buckets.
MATCHED = "MATCHED"
INTENDED = "INTENDED"
REGRESSION = "REGRESSION"


class CompareError(Exception):
    """Raised on usage or IO errors (mapped to exit code 2)."""


@dataclass
class Difference:
    """A single classified difference between two aligned records.

    Attributes:
        bucket: One of MATCHED / INTENDED / REGRESSION.
        field: Dotted field path the difference applies to.
        detail: Human-readable explanation of the difference.
        legacy: Legacy-side value (for display).
        refactor: Refactor-side value (for display).
    """

    bucket: str
    field: str
    detail: str
    legacy: Any = None
    refactor: Any = None

    def to_dict(self) -> dict[str, Any]:
        """Serialize for the JSON report."""
        return {
            "bucket": self.bucket,
            "field": self.field,
            "detail": self.detail,
            "legacy": self.legacy,
            "refactor": self.refactor,
        }


@dataclass
class TaskComparison:
    """Per-task comparison outcome.

    Attributes:
        name: Aligned task name (or index fallback).
        differences: All classified differences for this task.
    """

    name: str
    differences: list[Difference] = field(default_factory=list)

    @property
    def regressions(self) -> list[Difference]:
        """Differences in this task classified as regressions."""
        return [d for d in self.differences if d.bucket == REGRESSION]

    @property
    def intended(self) -> list[Difference]:
        """Differences in this task classified as intended deltas."""
        return [d for d in self.differences if d.bucket == INTENDED]

    def to_dict(self) -> dict[str, Any]:
        """Serialize for the JSON report."""
        return {
            "name": self.name,
            "differences": [d.to_dict() for d in self.differences],
        }


# --------------------------------------------------------------------------- #
# Normalization helpers.
# --------------------------------------------------------------------------- #


def normalize_score_key(key: str) -> str:
    """Strip a trailing ``" [GEval]"`` suffix from a score key.

    >>> normalize_score_key("OutcomeValidity [GEval]")
    'OutcomeValidity'
    """
    if key.endswith(_GEVAL_SUFFIX):
        return key[: -len(_GEVAL_SUFFIX)]
    return key


def normalize_whitespace(text: Any) -> str:
    """Collapse runs of whitespace and trim, for stable text comparison.

    Args:
        text: Any value; non-strings are stringified (None becomes "").

    Returns:
        Whitespace-normalized string.
    """
    if text is None:
        return ""
    return " ".join(str(text).split())


def score_entry_value(entry: Any) -> float | None:
    """Extract the numeric score from a score entry (dict or bare float).

    >>> score_entry_value({"score": 0.5})
    0.5
    >>> score_entry_value(0.5)
    0.5
    >>> score_entry_value({}) is None
    True
    """
    if isinstance(entry, dict):
        val = entry.get("score")
        return float(val) if isinstance(val, (int, float)) else None
    if isinstance(entry, (int, float)):
        return float(entry)
    return None


def score_entry_success(entry: Any) -> bool | None:
    """Extract the success flag from a score entry, if any.

    Args:
        entry: Either ``{"score": ..., "success": ...}`` or a bare value.

    Returns:
        The success flag, or None for bare-value entries.
    """
    if isinstance(entry, dict):
        val = entry.get("success")
        return val if isinstance(val, bool) else None
    return None


def normalize_scores(scores: dict[str, Any]) -> dict[str, Any]:
    """Re-key a scores dict by normalized (GEval-stripped) name.

    Later keys win on collision.

    >>> normalize_scores({"OutcomeValidity [GEval]": 0.5})
    {'OutcomeValidity': 0.5}
    """
    out: dict[str, Any] = {}
    for key, value in (scores or {}).items():
        out[normalize_score_key(key)] = value
    return out


def _is_checklist_key(key: str) -> bool:
    return key.startswith("Check:")


def _trajectory_nonempty(record: dict[str, Any]) -> bool:
    return bool(record.get("trajectory"))


# --------------------------------------------------------------------------- #
# Classification.
# --------------------------------------------------------------------------- #


def _classify_status(legacy: dict[str, Any], refactor: dict[str, Any]) -> Difference | None:
    """Classify a ``status`` difference, or return None if equal."""
    ls, rs = legacy.get("status"), refactor.get("status")
    if ls == rs:
        return None
    if ls is None and INTENDED_LEGACY_NULL_STATUS:
        return Difference(
            INTENDED,
            "status",
            "legacy non-infra path leaves status=None; refactor sets explicit status",
            ls,
            rs,
        )
    return Difference(
        REGRESSION,
        "status",
        "status flip between implementations",
        ls,
        rs,
    )


def _classify_output(legacy: dict[str, Any], refactor: dict[str, Any]) -> Difference | None:
    """Classify an ``output`` difference (whitespace-normalized)."""
    lo = normalize_whitespace(legacy.get("output"))
    ro = normalize_whitespace(refactor.get("output"))
    if lo == ro:
        return None
    return Difference(
        REGRESSION,
        "output",
        "materially different output after whitespace normalization",
        legacy.get("output"),
        refactor.get("output"),
    )


def _classify_trajectory(legacy: dict[str, Any], refactor: dict[str, Any]) -> Difference | None:
    """Classify a trajectory presence-only difference."""
    ln, rn = _trajectory_nonempty(legacy), _trajectory_nonempty(refactor)
    if ln == rn:
        return None
    if INTENDED_TRAJECTORY_PRESENCE_DELTA:
        return Difference(
            INTENDED,
            "trajectory",
            "trajectory presence differs by design (legacy: conversation turns; "
            "refactor: tool-call entries only)",
            f"non-empty={ln}",
            f"non-empty={rn}",
        )
    return Difference(
        REGRESSION,
        "trajectory",
        "trajectory presence mismatch",
        f"non-empty={ln}",
        f"non-empty={rn}",
    )


def _classify_metric_set(
    legacy_scores: dict[str, Any], refactor_scores: dict[str, Any]
) -> list[Difference]:
    """Classify metric keys present on one side but not the other."""
    diffs: list[Difference] = []
    lkeys, rkeys = set(legacy_scores), set(refactor_scores)

    for key in sorted(lkeys - rkeys):
        diffs.append(_classify_missing_metric(key, side="refactor"))
    for key in sorted(rkeys - lkeys):
        diffs.append(_classify_missing_metric(key, side="legacy"))
    return diffs


def _classify_missing_metric(key: str, *, side: str) -> Difference:
    """Classify a metric key missing on ``side``.

    Args:
        key: Normalized score key.
        side: The implementation MISSING the key ("legacy" or "refactor").

    Returns:
        An INTENDED Difference when the gap is allowlisted, else REGRESSION.
    """
    field_path = f"scores[{key!r}]"
    if _is_checklist_key(key) and INTENDED_CHECKLIST_TEXT_DELTAS:
        return Difference(
            INTENDED,
            field_path,
            f"checklist item text changed (trailing-hyphen fix); missing on {side}",
            None if side == "legacy" else key,
            None if side == "refactor" else key,
        )
    if key in INTENDED_MCP_READ_METRICS:
        return Difference(
            INTENDED,
            field_path,
            f"MCP-gated metric ({key}); presence depends on BENCH_USE_MCP read",
        )
    return Difference(
        REGRESSION,
        field_path,
        f"metric {key!r} present on the other side but missing on {side}",
    )


def _classify_metric_values(
    legacy_scores: dict[str, Any], refactor_scores: dict[str, Any]
) -> list[Difference]:
    """Classify per-metric value/success diffs for shared metric keys."""
    diffs: list[Difference] = []
    for key in sorted(set(legacy_scores) & set(refactor_scores)):
        legacy_entry, refactor_entry = legacy_scores[key], refactor_scores[key]
        lv, rv = score_entry_value(legacy_entry), score_entry_value(refactor_entry)
        ls, rs = score_entry_success(legacy_entry), score_entry_success(refactor_entry)
        field_path = f"scores[{key!r}]"

        if lv == rv and ls == rs:
            diffs.append(Difference(MATCHED, field_path, "score value and success match", lv, rv))
            continue

        if key in INTENDED_METRIC_VALUE_DELTAS:
            diffs.append(
                Difference(
                    INTENDED,
                    field_path,
                    f"value/success delta allowed for {key} (constraint dedup / robustness)",
                    {"score": lv, "success": ls},
                    {"score": rv, "success": rs},
                )
            )
            continue

        diffs.append(
            Difference(
                REGRESSION,
                field_path,
                f"score value/success diff for non-allowlisted metric {key!r}",
                {"score": lv, "success": ls},
                {"score": rv, "success": rs},
            )
        )
    return diffs


def compare_records(
    legacy: dict[str, Any], refactor: dict[str, Any], name: str
) -> TaskComparison:
    """Compare one aligned (legacy, refactor) record pair.

    Args:
        legacy: Legacy result record.
        refactor: Refactor result record.
        name: Aligned task name for reporting.

    Returns:
        A TaskComparison holding all classified differences.
    """
    comp = TaskComparison(name=name)

    for classifier in (_classify_status, _classify_output, _classify_trajectory):
        diff = classifier(legacy, refactor)
        if diff is not None:
            comp.differences.append(diff)

    lscores = normalize_scores(legacy.get("scores", {}))
    rscores = normalize_scores(refactor.get("scores", {}))
    comp.differences.extend(_classify_metric_set(lscores, rscores))
    comp.differences.extend(_classify_metric_values(lscores, rscores))

    if not comp.differences:
        comp.differences.append(Difference(MATCHED, "<record>", "no differences"))
    return comp


def align_records(
    legacy: list[dict[str, Any]], refactor: list[dict[str, Any]]
) -> list[tuple[str, dict[str, Any], dict[str, Any]]]:
    """Align legacy and refactor records by task name, falling back to index.

    Args:
        legacy: Legacy result list.
        refactor: Refactor result list.

    Returns:
        Triples of (name, legacy_record, refactor_record) for every aligned
        pair. Unmatched records on either side are paired with ``{}``.

    Raises:
        CompareError: If either input is not a list.
    """
    if not isinstance(legacy, list) or not isinstance(refactor, list):
        raise CompareError("both result files must contain a JSON list of records")

    refactor_by_name = {r.get("name"): r for r in refactor if r.get("name")}
    aligned: list[tuple[str, dict[str, Any], dict[str, Any]]] = []
    used: set[str] = set()

    name_match = all(r.get("name") for r in legacy) and all(r.get("name") for r in refactor)
    if name_match:
        for lr in legacy:
            nm = lr.get("name")
            rr = refactor_by_name.get(nm, {})
            if rr:
                used.add(nm)
            aligned.append((nm, lr, rr))
        for rr in refactor:
            nm = rr.get("name")
            if nm not in used:
                aligned.append((nm, {}, rr))
        return aligned

    # Positional fallback.
    for idx in range(max(len(legacy), len(refactor))):
        lr = legacy[idx] if idx < len(legacy) else {}
        rr = refactor[idx] if idx < len(refactor) else {}
        nm = (lr.get("name") if lr else None) or (rr.get("name") if rr else None) or f"#{idx}"
        aligned.append((nm, lr, rr))
    return aligned


def compare(
    legacy: list[dict[str, Any]], refactor: list[dict[str, Any]]
) -> list[TaskComparison]:
    """Align and compare two full result lists.

    Args:
        legacy: Legacy result list.
        refactor: Refactor result list.

    Returns:
        One TaskComparison per aligned task.
    """
    results: list[TaskComparison] = []
    for name, lr, rr in align_records(legacy, refactor):
        if not lr or not rr:
            comp = TaskComparison(name=name)
            missing = "legacy" if not lr else "refactor"
            comp.differences.append(
                Difference(REGRESSION, "<record>", f"task missing on {missing} side")
            )
            results.append(comp)
            continue
        results.append(compare_records(lr, rr, name))
    return results


# --------------------------------------------------------------------------- #
# Reporting / CLI.
# --------------------------------------------------------------------------- #


def _load(path: str) -> list[dict[str, Any]]:
    try:
        with open(path, encoding="utf-8") as fh:
            return json.load(fh)
    except OSError as exc:
        raise CompareError(f"cannot read {path}: {exc}") from exc
    except json.JSONDecodeError as exc:
        raise CompareError(f"invalid JSON in {path}: {exc}") from exc


def render_report(comparisons: list[TaskComparison]) -> str:
    """Render a human-readable, bucket-grouped report.

    Args:
        comparisons: Per-task comparison outcomes.

    Returns:
        The full report text (no trailing newline).
    """
    lines: list[str] = []
    total = {MATCHED: 0, INTENDED: 0, REGRESSION: 0}

    for comp in comparisons:
        lines.append(f"== task: {comp.name} ==")
        for bucket in (REGRESSION, INTENDED, MATCHED):
            items = [d for d in comp.differences if d.bucket == bucket]
            for _ in items:
                total[bucket] += 1
            if not items:
                continue
            lines.append(f"  [{bucket}]")
            for d in items:
                lines.append(f"    - {d.field}: {d.detail}")
                if d.legacy is not None or d.refactor is not None:
                    lines.append(f"        legacy:   {d.legacy!r}")
                    lines.append(f"        refactor: {d.refactor!r}")
        lines.append("")

    verdict = "PASS (no regressions)" if total[REGRESSION] == 0 else "FAIL (regressions found)"
    lines.append(
        f"SUMMARY: {total[MATCHED]} matched, {total[INTENDED]} intended, "
        f"{total[REGRESSION]} regression(s) -> {verdict}"
    )
    return "\n".join(lines)


def build_json_report(comparisons: list[TaskComparison]) -> dict[str, Any]:
    """Build the machine-readable report payload.

    Args:
        comparisons: Per-task comparison outcomes.

    Returns:
        A JSON-serializable dict with per-task differences and totals.
    """
    totals = {MATCHED: 0, INTENDED: 0, REGRESSION: 0}
    for comp in comparisons:
        for d in comp.differences:
            totals[d.bucket] += 1
    return {
        "tasks": [c.to_dict() for c in comparisons],
        "totals": totals,
        "regressions": totals[REGRESSION],
    }


def has_regression(comparisons: list[TaskComparison]) -> bool:
    """Whether any task has at least one regression."""
    return any(c.regressions for c in comparisons)


def main(argv: list[str] | None = None) -> int:
    """CLI entrypoint.

    Args:
        argv: Argument vector (defaults to ``sys.argv[1:]``).

    Returns:
        0 if no regressions, 1 if any regression, 2 on usage/IO error.
    """
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--legacy", required=True, help="legacy results.json path")
    parser.add_argument("--refactor", required=True, help="refactor results.json path")
    parser.add_argument("--json-report", help="optional path to write a JSON report")
    try:
        args = parser.parse_args(argv)
        legacy = _load(args.legacy)
        refactor = _load(args.refactor)
        comparisons = compare(legacy, refactor)
    except CompareError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2

    print(render_report(comparisons))

    if args.json_report:
        try:
            with open(args.json_report, "w", encoding="utf-8") as fh:
                json.dump(build_json_report(comparisons), fh, indent=2)
        except OSError as exc:
            print(f"error: cannot write report: {exc}", file=sys.stderr)
            return 2

    return 1 if has_regression(comparisons) else 0


if __name__ == "__main__":
    sys.exit(main())
