# Metrics

Scoring in devops-bench is two things working together: an **LLM-as-judge** that
reads what the agent actually produced and decides whether it met the task, plus
**deterministic checks** computed straight from the run record (retrieval rates,
performance passthroughs). This page explains how the framework is wired and,
more importantly, how to read the results it writes.

Every metric is a small, self-registering class. The contract lives in
[`devops_bench/metrics/base.py`](../../devops_bench/metrics/base.py): a metric
implements the `MetricEvaluator` protocol with a `name`, an `applies(ctx)` gate
that decides whether it runs for a given result, and an `evaluate(ctx)` that
yields zero or more `MetricScore` entries. Metrics register themselves into the
`METRICS` registry with a decorator, and the registry also discovers
entry-point plugins from other packages — so adding a metric never means editing
the scoring loop.

The judge runs through the provider-agnostic models layer via `ModelLayerJudge`
([`geval.py`](../../devops_bench/metrics/geval.py)). You pick which model judges
with the `JUDGE_PROVIDER` and `JUDGE_MODEL` environment variables; the judge
itself is text-only and provider-neutral. (For how providers are selected, see
[model_providers.md](./model_providers.md).)

## The built-in metrics

Each judged metric is scored with **GEval** (DeepEval's criteria-based grader) on
a 0–1 scale and passes at **≥ 0.8** unless noted. Bare-value metrics are plain
numbers with no pass flag — you read the magnitude. The `<item>` / `<text>`
placeholders below are filled in per task.

| Score key | What it measures | Range / pass rule | When it runs |
| --- | --- | --- | --- |
| `OutcomeValidity` | LLM judge: did the run actually achieve the task outcome — the headline "did it work" signal | 0–1, pass ≥ 0.8 | Always |
| `ToolInvocation` | LLM judge: did the agent call the right tools and follow a sensible trajectory | 0–1, pass ≥ 0.8 | Only when MCP is on |
| `Check: <item>` | LLM judge: one bulleted requirement from `expected_output`, judged on its own | 0–1, pass ≥ 0.8 | When `expected_output` has requirement bullets |
| `ChecklistScore` | Aggregate of the per-requirement checks: passed ÷ total | 0–1, pass ≥ 0.8 | Same as above |
| `Doc Constraint: <text>` | LLM judge: one documented constraint, judged on its own | 0–1, pass ≥ 0.8 | When the task maps `documentation` |
| `GroundingAccuracy` | Banded roll-up of constraint coverage, weighting critical constraints | **5.0 / 2.5 / 0.0**, pass ≥ 4.0 | When the task maps `documentation` |
| `ParameterRecallAccuracy` | Fraction of documented constraints satisfied | 0–1 (bare) | When the task maps `documentation` |
| `DocRetrievalRate` | Fraction of mapped guides the agent actually visited in its trajectory | 0–1 (bare) | When the task maps `documentation` |
| `DiagnosisAccuracy` | LLM judge: did the agent correctly identify the injected fault | 0–1, pass ≥ 0.8 | When the task has a `chaos_spec` |
| `GracefulRecovery` | LLM judge: did the agent recover gracefully (uptime, zero downtime) | 0–1, pass ≥ 0.8 | When the task has a `chaos_spec` |
| `Workload_Deployment_Time_Seconds` | Deployment time, passed through verbatim | seconds (bare) | When the task has a `chaos_spec` |
| `Workload_Uptime_Percentage` | Uptime during the run, passed through verbatim | percentage (bare) | When the task has a `chaos_spec` |
| `Resource_Utilization_Efficiency` | Efficiency figure, passed through verbatim | bare number | When the task has a `chaos_spec` |

A few notes that matter when you read these:

- **`OutcomeValidity` softens for generation-only tasks.** When a task provisions
  no live cluster (`deployer: noop`), the criteria are adjusted so a missing
  cluster-apply or execution confirmation is *not* counted against the agent — a
  correct, complete manifest is full achievement. Semantic correctness and every
  expected-output requirement are still graded normally.
- **`GroundingAccuracy` is banded, not continuous.** 5.0 means every constraint
  was met, 0.0 means none were, and 2.5 is partial. Any unmet **critical**
  constraint caps the band at Partial (2.5) regardless of how many non-critical
  ones passed.
- **Tokens and latency are not scores.** They are top-level fields on the record
  (`tokens`, `latency`), not entries in the `scores` map.

> [!NOTE]
> The fixed order in which the built-in keys appear in `results.json` is pinned
> in [`pipeline.py`](../../devops_bench/metrics/pipeline.py); any third-party
> plugin metrics follow in registry insertion order.

## Output format

A scored run writes three files into `results/<run_…>/`.

### `results.json` — the per-task detail

A list of per-task records. The interesting part of each is its `scores` map.
Two shapes show up there, both produced by the same `MetricScore.to_entry()`:

```json
{
  "scores": {
    "OutcomeValidity": { "score": 0.9, "success": true, "reason": "…" },
    "ChecklistScore":  { "score": 1.0, "success": true, "reason": "Passed 4 out of 4 checks." },
    "DocRetrievalRate": 0.5
  }
}
```

Judged entries are `{"score", "success", "reason"}` objects; computed and rate
entries are bare numbers. Records share a symmetric key set, so parsing is safe
across tasks.

> [!IMPORTANT]
> A record with `status: "failed"` is skipped by scoring and carries no scores.
> An absent score is **not** a bad result — it means the metric did not run (or
> the task failed before it could). Always check `status` before reading a low or
> missing score as a model's fault.

### `rows.json` — the dashboard contract

A flattened view, one row per setup × task × run × iteration, defined in
[`row.py`](../../devops_bench/results/row.py) and produced by
[`normalize.py`](../../devops_bench/results/normalize.py). This is what the
leaderboard ingests. Each row carries fields like `setupId`, `model`, `harness`,
`augmentation`, `outcomeScore`, `toolScore`, `latencySec`, input/output tokens,
`status`, and `validated`.

Two things are deliberate here: scores are kept **continuous** (never
pre-thresholded into pass/fail), so any pass@k formula stays computable
downstream; and a `null` score means the metric **didn't run**, distinct from a
genuine zero.

### `manifest.json` — run-level identity

The shared identity for every row in the run: schema version, `runId`, timestamp,
`setupId`, `model`, `harness`, and `augmentation`.

## How to read a result

Practical guidance, roughly in the order you'd actually look:

1. **Start with `OutcomeValidity`.** It is the headline. When it fails, read its
   `reason` — the judge explains what it thought was missing.
2. **`ChecklistScore.reason` tells you the ratio in words**, e.g. `"Passed 3 out
   of 5 checks."` Drill into the individual `Check: <item>` entries to see which
   requirement slipped.
3. **`GroundingAccuracy.reason` reads `"Applied X out of Y documented
   constraints (Critical: a/b)."`** If the critical count is short, that's why
   the band is capped at Partial even when the raw count looks decent.
4. **Bare rates have no pass flag.** `DocRetrievalRate`,
   `ParameterRecallAccuracy`, and the chaos performance numbers are just
   magnitudes — interpret them directly, don't look for `success`.
5. **Separate a real low score from an infrastructure failure** by checking
   `status`. A `failed` record didn't get a fair shot at scoring.
6. **`validated: true` gates leaderboard eligibility.** A row only counts toward
   the leaderboard once its task is vetted as correct.

## Adding a metric

The short version — for the full leaderboard wiring see
[leaderboard.md](../how-to/leaderboard.md):

1. Create `devops_bench/metrics/<name>.py` with a class decorated
   `@METRICS.register("<key>")` that implements `name`, `applies`, and
   `evaluate`. Use `run_geval(...)` for a judge-based metric, or build
   `MetricScore` instances directly for a computed one.
2. Add the new module to the side-effect import block in
   [`pipeline.py`](../../devops_bench/metrics/pipeline.py) so its registration
   fires (and optionally pin its position in the built-in order).
3. GEval criteria text lives in `devops_bench/skills/` and is loaded via
   `_skills.load_skill_text`.
4. To surface the metric on the leaderboard, extend
   [`row.py`](../../devops_bench/results/row.py) and
   [`normalize.py`](../../devops_bench/results/normalize.py) with the new field.

> [!NOTE]
> A failing metric is caught per-result and logged; it never aborts the batch.
