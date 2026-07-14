---
name: run-parallel-evals
description: Run a Task × Model × AgentConfig MATRIX of evals in parallel — local or on the bastion, with opt-in hands-off and unlimited/self-healing modes; invoke when the user wants a matrix, a comparison across models/configs, or to "run these evals in parallel" / "compare legacy vs refactored".
---

# Run a parallel eval matrix

Orchestrate a **Task × Model × AgentConfig** matrix end to end: expand the combos,
launch them detached, monitor and retry flakes, then summarize and diagnose.

This file keeps only what's **unique to running many combos at once**. Everything
shared is in the references — read them, don't restate them:

- Local vs bastion, auth, clean pre-flight, launch, knobs, results →
  [`../../references/running-evals.md`](../../references/running-evals.md)
- Monitoring / keepalive / recovery →
  [`../../references/monitoring-and-recovery.md`](../../references/monitoring-and-recovery.md)
- Unlimited / self-healing loop →
  [`../../references/unlimited-mode.md`](../../references/unlimited-mode.md)
- Capability → tool mapping (sub-agents, background runs, timers, durable state,
  worktrees) → [`../../references/harness-capabilities.md`](../../references/harness-capabilities.md)
- Failure router →
  [`../../../docs/appendix/known_issues.md`](../../../docs/appendix/known_issues.md)
- Reading scores →
  [`../../../docs/components/metrics.md`](../../../docs/components/metrics.md)

**Single combo?** Use [`run-eval`](../run-eval/SKILL.md). **Validating a new
task?** Use [`validate-eval`](../validate-eval/SKILL.md).

---

## Modes (opt-in)

| Mode | When | What it adds |
|---|---|---|
| **Standard** | default | You drive Phases 1–5 directly. |
| **Hands-off** | "must not stop", "monitor with subagents", long runs | Tiered-subagent monitoring + keepalive — [monitoring-and-recovery.md](../../references/monitoring-and-recovery.md). |
| **Unlimited / self-healing** | "keep going until it finishes", "auto-fix and restart" | Diagnose → fix → re-sync → restart failed combos, capped — [unlimited-mode.md](../../references/unlimited-mode.md). |

Resolve the mode in Phase 1; hands-off and unlimited are **explicit opt-in**.

---

## Phase 1 — Spec the matrix + combo math

Choose **local vs bastion** and **auth** ([running-evals.md](../../references/running-evals.md)),
then pin the matrix axes — ask the operator for anything not given:

1. **`MATRIX_TASKS`** — space-separated `task.yaml` paths, or `ALL`.
2. **`MATRIX_MODELS`** — space-separated model ids.
3. **`MATRIX_AGENT_CONFIGS`** — refactored arm only; each `oc|gcli` `[+mcp][+skills]`.
4. **Arm(s)** — refactored (`run_matrix.sh`), legacy (`run_matrix_legacy.sh`,
   oc-only), or both in parallel.
5. **`MAX_PARALLEL`** — combos running at once (default 3).

**Combo count = tasks × models × configs.** State it plus the rough wall-clock
(≈25–40 min/combo for infra-bearing tasks) so the operator can confirm scale
before you spend clusters. Then `DRY_RUN=1` to print the expanded matrix.

---

## Phase 2 — Cross-combo parallel-safety pre-flight

The one thing a matrix must get right that a single run needn't: combos run
**concurrently**, so shared state across combos is a hazard. Each combo provisions
and tears down **its own** cluster and writes its own results — the matrix is safe
only as long as that isolation holds.

- **Never run two of the *same* combo at once** — run-id-derived cluster names are
  reused (safe only because the prior identical run tore down first). Distinct
  combos are fine alongside each other.
- **Legacy + gemini CLI is not parallel-safe** — for parallel gemini, use the
  refactored arm.
- Pre-flight each selected task against the per-run isolation gaps in
  [known_issues.md](../../../docs/appendix/known_issues.md) (run the
  [`devops-bench-review`](../devops-bench-review/SKILL.md) skill for a thorough
  pass). The ones that bite a *matrix* specifically:
  - a task that seeds a fixed `$HOME` repo (`~/<task>-repo.git`) and `rm -rf`s it
    — unsafe once the matrix repeats it across models/configs;
  - a multi-cluster stack whose node-SA name collapses under the run-token prefix;
  - a per-task stack that grants a project role to the **shared VM SA** (teardown
    clobber across concurrent GKE combos);
  - duplicate `task_id`s among the selected tasks (ambiguous reporting);
  - host capacity: sum kind clusters / disk / inotify across `MAX_PARALLEL`.

A doomed combo wastes a cluster + ~30 min, so catch these before launch.

---

## Phase 3 — Clean pre-flight + launch (detached)

Work the **"Before any retry" checklist** in
[known_issues.md](../../../docs/appendix/known_issues.md) before **every** launch —
stale per-run state and orphaned cloud resources are the top cause of a "fresh"
matrix failing instantly. For leaked clusters / `gke-nodes-*` SAs / secrets, use
the `cleanup-orphaned-resources` skill.

**Smoke-gate before the full matrix.** Launch **one cheap combo first** (a `noop`
or `kind` task is fastest — no GKE provision) and verify its `results.json` has a
**non-empty `trajectory`** (and `tools` populated for tool-using tasks), not just
`exit=0`. An empty trajectory on a task the agent clearly acted on is a *silent*
capture failure that scores still "succeed" through — it deflates every
tool/checklist score (e.g. the `oc sessions` Node-not-on-PATH bug in
[known_issues.md](../../../docs/appendix/known_issues.md)). **Abort and fix before
spending the full matrix** rather than discovering it across N invalid runs.

Then launch per [running-evals.md](../../references/running-evals.md): build the
env from Phase 1, run the wrapper as a background job, and **capture each
`STAMP`** (`RESUME_STAMP=<stamp>`) plus the combo list in durable state. To run
both arms in parallel, sync once then start each wrapper `SKIP_SYNC=1`, staggered
a few seconds. If your poller dies the detached run continues — re-attach with
`RESUME_STAMP`.

---

## Phase 4 — Monitor + retry flakes

Follow [monitoring-and-recovery.md](../../references/monitoring-and-recovery.md):
poll each combo's `status` + `run.log` on an interval (~3–5 min for infra-bearing
tasks — **don't busy-poll**); under hands-off mode delegate polling to a cheap
watcher and per-finish analysis to a mid tier.

Classify each combo against the router in
[known_issues.md](../../../docs/appendix/known_issues.md): **infra flake** → clean
+ retry that one combo (cap 2 per combo; log every retry — never silently drop a
combo); **real failure** (auth/config, low score, task-logic) → do not retry,
analyze in Phase 5. If the whole runner died, re-attach with `RESUME_STAMP` then
relaunch only the unfinished combos. For unlimited mode, a real task/code bug is
not the end — follow [unlimited-mode.md](../../references/unlimited-mode.md).

---

## Phase 5 — Summarize + diagnose

When every combo is terminal (or `.done` is present), pull results and report per
combo: **task · model · agent-config · arm · auth-mode · exit · score ·
#MCP-tool-calls · pass/fail checks.** Read and interpret scores per
[metrics.md](../../../docs/components/metrics.md); results layout is in
[running-evals.md](../../references/running-evals.md).

**Aggregate for the dashboard:** the matrix runs one task per process, so combine
the per-task `rows.json` into one batch run before ingest:

```bash
python -m devops_bench.results.aggregate <results-root> -o <results-root>
```

Then ingest the combined `rows.json` (see `site/ingest/`). For every
non-passing combo, give: the decisive log line (redact secrets), the **root
cause** mapped to the router, whether it's **model vs harness** (clean trajectory
+ low score = model; early abort / auth error = harness/config), and the concrete
fix. Then **verify teardown is clean** and report any residue.

End with: total combos, passed/failed counts, best performer, the headline score
table, and each failure's root cause + fix.

---

## Living known-issues

When a combo fails in a way **not** already in
[known_issues.md](../../../docs/appendix/known_issues.md), append a router row —
**symptom → root cause → fix → class** — so the next run benefits. Terse, no
duplication, follow the docs conventions (scope + user-guide, GFM, not
journal-like, no model scores). This capture step is part of the run, not
optional.

---

## Guardrails

- Each combo costs a real GKE cluster + ~25–40 min — confirm the combo count and
  `DRY_RUN=1` first; mind project quota across `MAX_PARALLEL`.
- Never print or commit API keys; redact secrets in summaries.
- Always confirm clean teardown — orphaned `gke-nodes-*` SAs silently `409` the
  next run.
- Cap retries (≤2/combo) and surface anything still failing rather than looping.
- Prefer leaving the run detached + re-attaching via `RESUME_STAMP` over a fragile
  foreground session.
- **Hands-off run:** never emit a completion signal until *every* combo is
  terminal **and** summarized; emit a periodic heartbeat instead.
- **Cluster-mutation blast radius (with-mcp + owner SA).** The bench SA needs
  broad rights, so gke-mcp exposes every real cluster in the project as a writable
  target. On manifest-generation tasks (computeclass-*, gateway-*, hpa-*) the
  agent sometimes runs `gcloud container clusters update/upgrade` against an
  unrelated cluster — a long-running op with no agent timeout, so the run **hangs**
  (no score) and may mutate a cluster the eval never provisioned. Mitigate: run
  such tasks in a project with **no other clusters**, or watch the logs for
  `clusters update|upgrade|delete` and kill the offending `gcloud`. Don't
  auto-revert a change to a cluster you don't own.
