---
name: run-eval
description: >
  Use when the user wants to run a single evaluation — one Task on one Model with
  one AgentConfig — on the GKE eval bastion or this host, e.g. "run secret-rotation
  on gemini-3.1-pro-preview", "run one eval", "evaluate <task> with <model>", "kick
  off a single eval run", "run this task once and watch it". Drives the whole
  lifecycle for that one run: gather the spec + credentials, ensure a clean runner,
  launch it detached, monitor with recovery, then summarize and diagnose. For more
  than one Task/Model/AgentConfig combo, use `run-parallel-evals` instead. Inherits
  the same recovery (RESUME_STAMP re-attach) and opt-in hands-off / self-healing
  modes, which it reuses from the parallel skill's reference files.
---

# Run a single eval

Orchestrate **one** eval run (one Task × one Model × one AgentConfig) end to end:
set up env + credentials, ensure a clean runner, launch the run detached, babysit it
with recovery, then deliver a result summary with failure analysis.

## Relationship to `run-parallel-evals`

A single run **is a 1×1×1 matrix** — it uses the exact same wrappers
(`scripts/bastion/run_matrix.sh`, `run_matrix_legacy.sh`, `_matrix_lib.sh`) with one
task, one model, one config. So this skill does **not** add scripts or new recovery
machinery; it reuses the parallel skill's. The only difference is a leaner front-end:
no concurrency (`MAX_PARALLEL`), no combo-count math, and no cross-combo
parallel-safety pre-flight.

**Reused as-is from `run-parallel-evals` (read there, don't duplicate):**
- `.agents/skills/run-parallel-evals/SKILL.md` — *Harness portability*, *Execution
  mode*, **Phase 2** (credentials), **Phase 3** (clean environment), the **Phase 5**
  infra-flake-vs-real-failure classification, and the **Phase 6** scoring mechanics.
- `docs/bastion.md` — bastion architecture, provisioning, per-run isolation. If
  `docs/parallel-evals.md` is present, it is the fuller operational runbook +
  failure-mode table; otherwise the classification inline in the parallel skill's
  Phases 5–6 is the source of truth.

This file states only what is **specific to a single run**. When a phase below says
"same as the parallel skill," go read that phase there.

**If the user actually wants more than one combo** (multiple tasks/models/configs, a
comparison, a matrix), stop and use `run-parallel-evals` instead — it adds the
concurrency, combo math, and cross-combo parallel-safety this skill deliberately omits.

---

## Modes & progressive disclosure

Keep context lean: **this file is the standard single run** (Phases 1–6, you drive
directly). The recovery/hands-off and self-healing capabilities live in the **parallel
skill's** `references/` — read them only when the request calls for them:

| If the user wants… | Read (when you reach it) | Default |
|---|---|---|
| A normal single run | nothing extra — Phases 1–6 below | — |
| A long / hands-off run that "must not stop", "watch it", "stay alive" | `.agents/skills/run-parallel-evals/references/resilient-monitoring.md` — tiered-subagent monitoring + API-error recovery + keepalive. For one combo it degenerates to **one** analyzer + the keepalive loop. Read **before Phase 4** of any real (non-`DRY_RUN`) launch. | **on** for real runs |
| "unlimited", "keep going until it passes", "auto-fix and restart", self-healing | `.agents/skills/run-parallel-evals/references/unlimited-mode.md` — diagnose → fix in a worktree → re-sync → restart the run → repeat (capped). | **off** — explicit opt-in only |

Resolve the mode in Phase 1. If neither special mode applies, ignore the reference files.

---

## Harness portability & execution mode

This skill is **agent/harness-agnostic** and **local by default; remote is opt-in** —
identical to the parallel skill. Rather than duplicate them, see the *Harness
portability* and *Execution mode* sections in
`.agents/skills/run-parallel-evals/SKILL.md`. The essentials:

- It needs only a **shell on the runner host** — *this host* by default (local
  `nohup`, no ssh/sync, outputs in `~/matrix-runs/<stamp>`), or set **`BENCH_REMOTE=1`**
  (+ the `BASTION_*` env) to sync to the bastion and run there over ssh.
- Tool names like `Agent` / `ScheduleWakeup` are **examples** — substitute your
  harness's equivalent (sub-task, scheduler, durable state, ask-the-user).
- The snippets below show the **remote** form `ssh <bastion> '<cmd>'`; in **local
  mode drop the `ssh <bastion>` wrapper** — the paths are the same on this host.
- Durable run state lives on the runner host (`RESUME_STAMP`), so even a bare harness
  (one shell, no sub-tasks) can drive and re-attach to a run.

---

## Phase 1 — Gather the single-run spec

**First, always ask: local or remote?** (local runs on this host, the default; remote
sets `BENCH_REMOTE=1` + the `BASTION_*` connection env.) Then pin down exactly the one
run. Ask the user (your harness's clarify path) for anything not given; don't guess on
the dimensions that cost a cluster + time. You need:

1. **Task** — one `*/task.yaml` path (`MATRIX_TASKS="complextasks/secret-rotation/task.yaml"`).
2. **Model** — one model (`MATRIX_MODELS="gemini-3.1-pro-preview"`).
3. **Agent config** — refactored arm only: one `MATRIX_AGENT_CONFIGS`, e.g.
   `gcli+mcp+skills` or `oc+mcp+skills` (`oc|gcli` `[+mcp][+skills]`).
4. **Arm** — refactored (`run_matrix.sh`) **or** legacy (`run_matrix_legacy.sh`,
   oc-only). One run = one arm.
5. **Auth mode** — API-key vs **Vertex/ADC** (`BENCH_VERTEX=1`). If unsure, recommend
   Vertex (no key handling, VM-SA ADC).

State the **rough wall-clock** (≈25–40 min for an infra-bearing task like
secret-rotation; less for a lightweight task) so the user can confirm before you spend
a cluster. Then run with `DRY_RUN=1` to show the expanded (single) combo before the
real launch.

**Single-run safety (much lighter than the matrix pre-flight):**
- **Never launch a second run of the same task+model+config concurrently** —
  run-id-derived cluster names are reused (safe only because the prior run tore down
  first). Different task/model/config is fine to run alongside.
- If the task is **infra-bearing**, skim its stack/scripts (or run the
  `devops-bench-review` skill on it) for self-collisions that bite even one run — e.g.
  it seeds a fixed `$HOME` repo (`~/<task>-repo.git`) and `rm -rf`s it, or grants the
  shared VM SA a project role it then revokes on teardown. The cross-*combo* hazards
  the parallel skill lists (node-SA prefix collapse, duplicate `task_id`s, host
  capacity across `MAX_PARALLEL`) don't apply to a single run.

Note: **legacy + gemini CLI is not parallel-safe**, but a single run is not parallel,
so either arm is fine here.

---

## Phase 2 — Credentials & environment

**Same as the parallel skill's Phase 2** — see
`.agents/skills/run-parallel-evals/SKILL.md`. In brief:

- **Remote mode only:** export the connection env (`BASTION_USE_GCPNODE=1`,
  `BASTION_VM`, `BASTION_ZONE`, `BASTION_PROJECT`, `GCP_PROJECT_ID`). Skip for local.
- **API-key mode:** the runner sources `~/secrets.env` (must export `AGENT_API_KEY`,
  `GEMINI_API_KEY`, `GOOGLE_API_KEY`, `JUDGE_API_KEY`). Check names only — **never
  print key values**; ask the user for a missing key (or have them paste with `!`).
- **Vertex mode (`BENCH_VERTEX=1`):** no keys. Verify VM-SA roles, gemini
  folder-trust (`security.folderTrust.enabled=false`), and for the **legacy oc** arm
  the `google-vertex` provider (`scripts/bastion/configure-oc.sh --vertex` once). The
  default `JUDGE_MODEL=gemini-3.1-pro` **404s on Vertex** — set
  `JUDGE_MODEL=gemini-3.1-pro-preview` and `AGENT_PROVIDER=google-vertex`.
- For legacy capabilities run `configure-oc.sh --mcp --skills` (or
  `--no-mcp --no-skills`) once before launching.

---

## Phase 3 — Connect and ensure a clean environment

**Same as the parallel skill's Phase 3.** Even for one run this matters — a stale
process or a leftover GCP resource from a prior aborted run will `409` your launch.

1. **Connectivity:** `ssh <bastion> 'echo OK; oc --version; gemini --version'`
   (transient `exit 255` is a gcpnode blip — retry).
2. **No stale processes:**
   `ssh <bastion> 'pgrep -af "matrix-runner|evaluate.py|devops_bench|oc agent" | grep -v pgrep'`.
3. **No leftover GCP resources** for this run's shape (clusters, `gke-nodes-*` SAs,
   `sa-secret-rotation-*`, `db-credentials`) — Phase-3 `gcloud` checks in the parallel
   skill. Delete confirmed orphans, **especially `gke-nodes-*` SAs**.
4. **Prereqs present:** `~/gke-mcp`, `~/oc-skills/` (if skills), `~/devops-bench/.venv`;
   else `scripts/bastion/vm-setup.sh`.

---

## Phase 4 — Launch the single run (detached)

> **Hands-off run? (default for real runs)** Read
> `.agents/skills/run-parallel-evals/references/resilient-monitoring.md` first and run
> the keepalive + recovery loop (for one combo: one monitor tick, one analyzer on
> finish). The inline path below is the direct foreground form.

Drive the wrapper with the **single** task/model/config — a 1×1×1 matrix. By default
it runs locally (detached `nohup`); with `BENCH_REMOTE=1` it syncs to the bastion and
launches detached over ssh, then polls. Run it as a **background job** so you keep
control. Example (Vertex, refactored arm):

```bash
# local by default; prefix BENCH_REMOTE=1 (+ BASTION_* env) to run on the bastion
BENCH_VERTEX=1 AGENT_PROVIDER=google-vertex \
JUDGE_PROVIDER=google JUDGE_MODEL=gemini-3.1-pro-preview \
MATRIX_TASKS="complextasks/secret-rotation/task.yaml" \
MATRIX_MODELS="gemini-3.1-pro-preview" \
MATRIX_AGENT_CONFIGS="gcli+mcp+skills" \
RESULTS_DIR="results/<label>" \
  scripts/bastion/run_matrix.sh
```

(Legacy arm: `run_matrix_legacy.sh`, oc-only, no `MATRIX_AGENT_CONFIGS`. `MAX_PARALLEL`
is irrelevant for one combo — leave it default.)

**Capture the `STAMP`** the wrapper prints (`RESUME_STAMP=<stamp>`) — it's your handle
for monitoring, retry, and re-attach. Record it in durable state (task list or notes
file) so you survive a context reset. Outputs live on the runner host at
`~/matrix-runs/<stamp>/<rid>/` (`run.log`, `status`); `~/matrix-runs/<stamp>/.done`
appears when it finishes. **If your poller dies, the run continues** (detached) —
re-attach with `RESUME_STAMP=<stamp>` and the same command.

---

## Phase 5 — Monitor + recover

Check on an interval (every ~3–5 min for an infra-bearing task); **don't busy-poll**.

```bash
ssh <bastion> 'd=~/matrix-runs/<stamp>/*/; \
  echo "status=$(cat $d/status 2>/dev/null || echo running) \
        last=$(tail -1 $d/run.log 2>/dev/null | cut -c1-80)"; \
  test -f ~/matrix-runs/<stamp>/.done && echo ALL_DONE'
```

Classify the run:
- **Running** — no `status` file, runner process alive. Leave it.
- **Finished** — `status` is `exit=<rc>`. `rc=0` ran to completion (score in Phase 6);
  `rc!=0` the harness errored (diagnose in Phase 6).
- **Aborted / flaked** — no `status` **and** no live process, or an **infra** error in
  `run.log`. Retry case.

**Infra flake vs real failure** — use the parallel skill's Phase-5 classification
(`.agents/skills/run-parallel-evals/SKILL.md`):
- **Infra flake → clean + retry:** tofu/provision failure, `409 already exists`
  (orphaned `gke-nodes-*` SA), GKE quota/transient API error, SSH/relay drop, node-pool
  timeout.
- **Real failure → do NOT retry, analyze:** auth/config errors (`No API key`, `401`,
  Vertex `404`, missing `--approval-mode`), or the agent ran but scored low (model
  capability), or task-logic failure.

**Retry procedure** (cap 2; log every retry):
1. Kill any lingering process for the run on the VM.
2. `rm -rf ~/matrix-runs/<stamp>/<rid>`.
3. Clean its leaked GCP resources: cluster (`c<hash>-eval`), `gke-nodes-<hash>` SA, any
   `sa-secret-rotation-*` / `db-credentials-*` (Phase-3 commands).
4. Re-launch the **same single run** (new `STAMP`, `SKIP_SYNC=1` after a real sync).
   Track the new stamp.

If the detached runner itself died (no `.done`, no live process), re-attach with
`RESUME_STAMP`; if truly dead, relaunch.

> **Unlimited / self-healing mode?** Only if the user opted in: a *real* (non-flake)
> failure from a task/code bug is not the end — read
> `.agents/skills/run-parallel-evals/references/unlimited-mode.md` and follow
> diagnose → fix → re-sync → restart instead of just reporting it.

**Keepalive (hands-off run):** under a harness that may classify the session done,
never emit a completion / `result:` / "done" line until the run is terminal **and**
summarized; each tick emit a one-line `still working: running / done / flaked` status
and schedule the next wake (see `resilient-monitoring.md`).

---

## Phase 6 — Summarize the result + diagnose

When the run has a terminal `status` (or `.done`), pull results (the wrapper does this
on normal exit; else `RESUME_STAMP=<stamp>` re-run to pull) and report:

**task · model · agent-config · arm · auth-mode · exit · score · #MCP-tool-calls ·
pass/fail checks.** Scoring mechanics are the **same as the parallel skill's Phase 6**:

```bash
grep -c 'Pass Rate: 100.0%' <run>/run.log   # passed checks
grep -c 'Pass Rate: 0.0%'   <run>/run.log   # failed checks
grep -oiE 'mcp_[a-z0-9_-]+|run_shell_command|activate_skill' <run>/run.log | sort | uniq -c
```
`results.json` is a **list** of per-criterion objects (`{name, score, success,
reason}`); refactored nests under `run_<ts>_<rid>/results.json`, legacy copies
`results/run_<ts>_<rid>` into the run dir. Beware grep false positives (bare
`401`/`quota` match terraform output) — anchor on `invalid_api_key`,
`ProviderAuthError`, `No API key`, `^OK$`.

**If the run did not pass / errored**, give an analysis: what happened (quote the
decisive log line, redacting secrets), the **root cause** (map to the failure table /
parallel-skill Phase 6 — e.g. `exit -1` = **timeout** not crash; Vertex `404` = wrong
location/model), **model vs harness** (clean trajectory + low score = model; early
abort / auth error = harness/config), and the **concrete fix / next step**.

Then **verify teardown is clean** (Phase-3 GCP checks — zero leftover cluster /
`gke-nodes-*` / `sa-secret-rotation-*` / `db-credentials-*`) and report any residue.

**Record any new failure mode** (same as the parallel skill) — a symptom → root cause →
fix row in the failure-mode table for an operational flake, or a known-issues bullet for
a structural gap, in `docs/bastion.md` (or `docs/parallel-evals.md` if present).
Terse, no duplication, follow the docs conventions (scope + user-guide, GFM, no model
scores).

End with: the run's exit, score, pass/fail checks, and — if it didn't pass — the root
cause + fix.

---

## Guardrails

- One run still costs a real GKE cluster + ~25–40 min. Confirm scale and use
  `DRY_RUN=1` first.
- Never print or commit API keys; redact secrets in summaries.
- Never launch a second run of the **same** task+model+config concurrently (cluster
  name reuse).
- Always confirm clean teardown — orphaned `gke-nodes-*` SAs silently `409` the next run.
- Cap retries (≤2) and surface a persistent failure rather than looping.
- Capture every **new** failure mode in the docs appendix (Phase 6) so learnings accrue.
- Prefer leaving the run detached + re-attaching via `RESUME_STAMP` over a fragile
  foreground SSH session.
- **Hands-off run:** don't let an idle/completion classifier stop the job mid-run —
  emit periodic progress, signal completion only when the run is terminal and summarized.
- **Progressive disclosure:** read a `references/*.md` file only when its mode applies.
- **Wrong tool?** If the request grows to multiple combos, switch to `run-parallel-evals`.
