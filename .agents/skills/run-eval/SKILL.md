---
name: run-eval
description: Run ONE evaluation — a single Task × Model × AgentConfig — end to end, local or on the bastion; invoke when the user wants to run, evaluate, or "kick off" a single eval combo (e.g. "run secret-rotation on gemini-3.1-pro-preview", "evaluate this task once and watch it").
---

# Run a single eval

The easy entrypoint for **one** eval run: one Task × one Model × one AgentConfig.
A single run is just a 1×1×1 matrix, driven through the same wrapper everything
else uses. This skill keeps the front-end lean — no concurrency, no combo math,
no cross-combo safety. For those, use a different skill (see *Wrong tool?*).

The run mechanics are shared and live in the references — **read them, don't
re-derive them here:**

- Local vs bastion, auth, clean pre-flight, launch, knobs, results layout →
  [`../../references/running-evals.md`](../../references/running-evals.md)
- Capability → tool mapping for your harness →
  [`../../references/harness-capabilities.md`](../../references/harness-capabilities.md)

---

## Flow

### 1. Choose where + how, then pin the one combo

- **Local or bastion?** Local is the default; remote sets `BENCH_REMOTE=1` + the
  `BASTION_*` connection env. **Auth:** prefer Vertex/ADC (`BENCH_VERTEX=1`, no
  keys). Both covered in [running-evals.md](../../references/running-evals.md).
- Pin exactly one **Task** (`task.yaml` path), one **Model**, one **AgentConfig**
  (`oc|gcli` `[+mcp][+skills]`, refactored arm only), and the **arm** (refactored
  `run_matrix.sh` or legacy `run_matrix_legacy.sh`, oc-only).
- Ask the operator for anything not given — don't guess on the dimensions that
  cost a cluster + time (≈25–40 min for an infra-bearing task).

### 2. Preview with `DRY_RUN=1`

Show the expanded (single) combo + per-combo env before spending a cluster:

```bash
DRY_RUN=1 \
MATRIX_TASKS="tasks/gcp/secret-rotation/task.yaml" \
MATRIX_MODELS="gemini-3.1-pro-preview" \
MATRIX_AGENT_CONFIGS="gcli+mcp+skills" \
  scripts/bastion/run_matrix.sh
```

### 3. Clean pre-flight

Work the **"Before any retry" checklist** in
[`../../../docs/appendix/known_issues.md`](../../../docs/appendix/known_issues.md)
before launching — stale per-run state and orphaned cloud resources are the top
cause of a "fresh" run failing instantly. For leaked clusters / `gke-nodes-*`
SAs / secrets, use the `cleanup-orphaned-resources` skill.

### 4. Launch the one combo (detached)

Drive the wrapper with single-value `MATRIX_*`. It runs detached under `nohup`
and prints a `STAMP` — record `RESUME_STAMP=<stamp>` in durable state; it is your
handle for monitoring, retry, and re-attach. Example (Vertex, refactored arm;
prefix `BENCH_REMOTE=1` + `BASTION_*` for remote):

```bash
BENCH_VERTEX=1 AGENT_PROVIDER=google-vertex \
JUDGE_PROVIDER=google JUDGE_MODEL=gemini-3.1-pro-preview \
MATRIX_TASKS="tasks/gcp/secret-rotation/task.yaml" \
MATRIX_MODELS="gemini-3.1-pro-preview" \
MATRIX_AGENT_CONFIGS="gcli+mcp+skills" \
RESULTS_DIR="results/<label>" \
  scripts/bastion/run_matrix.sh
```

(Legacy arm: `run_matrix_legacy.sh`, oc-only, no `MATRIX_AGENT_CONFIGS`.
`MAX_PARALLEL` is irrelevant for one combo.) Full launch details, including
running both arms, are in [running-evals.md](../../references/running-evals.md).

### 5. Watch it

Basic loop: poll the combo's `status` + `run.log` tail on an interval (~3–5 min
for an infra-bearing task — **don't busy-poll**). If your poller dies the
detached run continues; re-attach with `RESUME_STAMP=<stamp>` and the same
command. For a resilient, hands-off watch that survives quiet stretches and dead
watchers, follow
[`../../references/monitoring-and-recovery.md`](../../references/monitoring-and-recovery.md)
(for one combo it degenerates to one watcher + the keepalive loop).

Classify a flake vs a real failure against the router in
[known_issues.md](../../../docs/appendix/known_issues.md): infra flake → clean +
retry (cap 2); real failure (auth/config, low score, task-logic) → do not retry,
analyze.

### 6. Summarize + where to read scores

When the combo has a terminal `status` (or `.done`), report:
**task · model · agent-config · arm · auth-mode · exit · score · pass/fail
checks.** Results land per the layout in
[running-evals.md](../../references/running-evals.md); for how scoring works and
how to interpret it, see
[`../../../docs/components/metrics.md`](../../../docs/components/metrics.md). If
it didn't pass, give the decisive log line (redact secrets), the root cause, and
the concrete fix. Then confirm teardown is clean.

---

## Wrong tool?

- **Validating a NEW eval** (iterate in a loop until the task is correct and
  runnable, hands-off or self-healing) → use the
  [`validate-eval`](../validate-eval/SKILL.md) skill. No loop logic lives here.
- **More than one combo** (a matrix, a comparison) → use the
  [`run-parallel-evals`](../run-parallel-evals/SKILL.md) skill — it adds combo
  math, `MAX_PARALLEL`, and cross-combo parallel-safety.

## Guardrails

- One run still costs a real GKE cluster + ~25–40 min — confirm scale and
  `DRY_RUN=1` first.
- Never print or commit API keys; redact secrets in summaries.
- Never launch a second run of the **same** task+model+config concurrently
  (run-id-derived cluster names are reused).
- Always confirm clean teardown — orphaned `gke-nodes-*` SAs silently `409` the
  next run.
- Prefer leaving the run detached + re-attaching via `RESUME_STAMP` over a
  fragile foreground session.
