# Legacy vs. refactor comparison harness (temporary)

**Status: droppable scaffolding.** This harness is a regression gate used *during*
the `pkg/evaluator/evaluate.py` -> `devops_bench` refactor. Both implementations
currently coexist on this branch. Once the refactor is validated and the legacy
evaluator is removed, delete `scripts/compare_legacy_vs_refactor.sh`,
`scripts/compare_results.py`, and `tests/unit/comparison/`.

## Purpose

Run the same reference task through both entrypoints against a deterministic mock
model and prove that the refactor changed *only* what it intended to change. The
mock (`scripts/mock_ollama_server.py`) returns identical canned agent + judge
output to both runs, so any difference in `results.json` is attributable to the
code, not the model.

## How to run

```bash
# default reference task: tasks/noop/gateway-https-redirect/task.yaml
scripts/compare_legacy_vs_refactor.sh

# a different task / a different mock port
MOCK_PORT=11500 scripts/compare_legacy_vs_refactor.sh tasks/<...>/task.yaml
```

The orchestrator:

1. Starts the mock Ollama server and health-checks `/v1/models` (killed via an
   `EXIT` trap so a failed run still cleans up).
2. Runs LEGACY (`python pkg/evaluator/evaluate.py <task>`), which writes
   `results/run_<ts>/results.json` relative to CWD; the script picks the newest
   run dir that did not exist before the run.
3. Runs REFACTOR (`RESULTS_ROOT=<tmp> uv run python -m devops_bench <task>`) into
   an isolated temp dir and parses the printed `results: <path>` line.
4. Diffs the two files with `scripts/compare_results.py` and propagates its exit
   code: **0** = no regressions, **1** = a regression, **2** = usage/IO error.

You can also diff two existing files directly:

```bash
uv run python scripts/compare_results.py \
  --legacy <legacy results.json> --refactor <refactor results.json> \
  [--json-report report.json]
```

## The three buckets

Every observed difference (after normalization that drops volatile fields:
`latency`, `tokens`, timestamps, run-dir/absolute paths, and trajectory
structure) is partitioned into:

- **MATCHED** — identical after normalization.
- **INTENDED** — explained by the allowlist below (a documented, deliberate
  refactor change).
- **REGRESSION** — any remaining unexplained difference (a dropped/added
  non-allowlisted metric, a real status flip, materially different `output`, or a
  value/success diff on a metric not on the value-delta allowlist). A single
  regression fails the gate (exit 1).

## Current intended-delta allowlist

Defined as clearly-labeled module-level constants at the top of
`scripts/compare_results.py`; edit there to extend. Rationale traces to
`docs/refactor/metrics-extensibility-handoff.md` (section 3 reviewer note) plus
two schema/trajectory deltas observed empirically on the reference task.

| Allowlist constant | What it tolerates | Rationale |
|---|---|---|
| (always) score-key normalization | strips a trailing ` [GEval]` before aligning | Legacy wrote `OutcomeValidity [GEval]` / `ToolInvocation [GEval]`; refactor strips uniformly (handoff section 3). |
| `INTENDED_METRIC_VALUE_DELTAS` = {GroundingAccuracy, ParameterRecallAccuracy, DocRetrievalRate} | numeric value/success diffs on these metrics | Constraint dedup (legacy double-counted) and missing-key robustness guard (handoff section 3). |
| `INTENDED_CHECKLIST_TEXT_DELTAS` | a `Check: ...` key present on only one side | Trailing-hyphen fix changed some checklist item names (handoff section 3); only the *text* changed. |
| `INTENDED_LEGACY_NULL_STATUS` | legacy `status=None` paired with any refactor status | Legacy non-infra path never set `status`; refactor sets an explicit terminal status. A real success<->failed flip (both non-None) is still a regression. |
| `INTENDED_TRAJECTORY_PRESENCE_DELTA` | trajectory non-empty on one side, empty on the other | By design the two trajectories track different things: legacy stores conversation turns, refactor stores only canonical `ToolCall` entries (empty for a no-tool task). Trajectory is never diffed structurally. |
| `INTENDED_MCP_READ_METRICS` = {ToolInvocation} | the `ToolInvocation` metric present on only one side | MCP-gated; `BENCH_USE_MCP` is read once by the refactor harness (handoff section 4.3). |

## Reading the gate output

`compare_results.py` prints each difference under its bucket, then exits `0` (no
regressions) or `1` (one or more). A clean refactor on a no-infra,
`BENCH_USE_MCP=false` task typically shows only **INTENDED** deltas (e.g. legacy
`status=None` → refactor `success`; trajectory presence by design) plus
**MATCHED** scores. Treat any **REGRESSION** row as a real change to investigate.
(Per-run counts and scores are not recorded here — they're tracked separately.)

> **Blind spots.** The allowlist deliberately tolerates value/success diffs on the
> three grounding metrics (`INTENDED_METRIC_VALUE_DELTAS`) and `Check:` key-text
> changes, so a value regression *on those* will not fail the gate. The gate is a
> coarse guard, not a full equivalence proof.
