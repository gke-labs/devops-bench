---
name: run-parallel-evals
description: >
  Use when the user wants to run a parallel evaluation matrix (Task × Model ×
  AgentConfig) on the GKE eval bastion — e.g. "run a parallel eval matrix",
  "run these evals on the bastion", "run the matrix for <tasks/models>",
  "kick off a Vertex eval run", "compare legacy vs refactored on the bastion".
  Drives the whole lifecycle: gather the matrix spec + credentials, set up the
  bastion cleanly, launch the detached run, monitor and retry infra flakes, then
  summarize results and diagnose failures. Supports delegated tiered-subagent monitoring and an opt-in unlimited/self-healing mode, loaded from reference files only when requested.
---

# Run parallel evals on the bastion

Orchestrate a parallel eval-matrix run on the GCE bastion end to end. You set up
env + credentials, ensure a clean VM, launch the matrix detached, babysit it
(retrying infra flakes), then deliver a results summary with failure analysis.

**Read these first — they are the source of truth; do not duplicate their content
from memory:**
- `docs/parallel-evals.md` — the runbook: env vars, Vertex/ADC setup, MCP setup,
  isolation, the **operational runbook**, and the **failure-mode → fix table**.
- `docs/bastion.md` — bastion architecture, provisioning, per-run isolation.

The scripts you drive: `scripts/bastion/run_matrix.sh` (refactored arm),
`scripts/bastion/run_matrix_legacy.sh` (legacy/oc arm), and the shared
`scripts/bastion/_matrix_lib.sh`. `DRY_RUN=1` previews any matrix without
provisioning — use it to validate the expansion before a real run.

Work through the phases in order. Don't skip the clean-environment or
credentials phases — they are the most common cause of wasted multi-hour runs.


---

## Modes & progressive disclosure

Keep context lean: **this file is the standard run** (Phases 1–6, you drive
directly). Two heavier capabilities live in `references/` — read them **only** when
the request calls for them, and don't pull both in for a plain run.

| If the user wants… | Read (when you reach it) | Default |
|---|---|---|
| A normal matrix run | nothing extra — Phases 1–6 below | — |
| A long / hands-off run that "must not stop", "monitor with subagents", "stay alive" | `references/resilient-monitoring.md` — tiered-subagent monitoring + API-error recovery + background-classifier keepalive. Read **before Phase 5** of any real (non-`DRY_RUN`) launch. | **on** for real runs |
| "unlimited", "keep going until it finishes", "auto-fix and restart", self-healing | `references/unlimited-mode.md` — diagnose → fix in a worktree → re-sync → restart failed combos → repeat. | **off** — explicit opt-in only |

Resolve the mode in Phase 1 (ask if it's ambiguous for a long/expensive matrix). If
neither special mode applies, ignore the reference files entirely.


---

## Harness portability

This skill is **agent/harness-agnostic** — it runs under any coding agent (Claude
Code, Antigravity/Gemini, Codex, …). It needs only a **shell on the runner host** — local by default, or `ssh` to the
bastion in remote mode (Antigravity: the `run_command` tool); everything else is an optimization. Map each capability used below to
whatever your harness provides, and degrade gracefully if it lacks one:

| Capability | Claude Code | Antigravity | Other / fallback |
|---|---|---|---|
| Sub-task | `Agent` | `invoke_subagent` | subagent/`task`; else inline |
| Model tiers | Haiku / Sonnet / Opus | `/models` (Flash / Pro) | mini / standard |
| Background run | `run_in_background` | `manage_task` | async; else poll |
| Timer / wake | `ScheduleWakeup` | `schedule` | scheduler; else `sleep` |
| Durable state | task list | Artifacts / `write_to_file` | notes file |
| Isolated worktree | `EnterWorktree` | `run_command` | `git worktree add` |
| Ask the user | `AskUserQuestion` | `ask_question` | ask in chat |
| Keepalive | progress, no early "done" | same | same |

Each cell names **one primitive** — assume your harness chains the supporting
calls (args, follow-ups, file reads) from it; the full Antigravity set is in the
footnote below.

Throughout this skill and its `references/`, tool names like `Agent` or
`ScheduleWakeup` are **examples**, not requirements — substitute your harness's
equivalent. Durable run state lives on the **bastion** (`RESUME_STAMP`), so even a
bare harness (one shell, no sub-tasks, no scheduler) can drive a run by polling.

**Antigravity tools** (the actual agent tool set, confirmed from a live Antigravity instance — the public [hooks docs](https://antigravity.google/docs/hooks) render client-side): files `view_file` · `list_dir` · `grep_search` · `write_to_file` · `replace_file_content` · `multi_replace_file_content`; exec `run_command` · `ask_permission` · `list_permissions`; web `search_web` · `read_url_content`; subagents/background `invoke_subagent` · `define_subagent` · `manage_subagents` · `send_message` · `manage_task` · `schedule`; interaction `ask_question` · `generate_image`. Hooks match these by tool name on `PreToolUse` / `PostToolUse` (config in `.agents/hooks.json`).

---

## Execution mode

**Local by default; remote is opt-in.** The matrix runs on the **runner host** —
the machine where you invoke the wrapper. By default that's *this host* (local
`nohup`, no ssh/sync, outputs in `~/matrix-runs/<stamp>`). Set **`BENCH_REMOTE=1`**
(plus the `BASTION_*` connection env) to sync the tree to the bastion and run
there over ssh, pulling results back.

**Command convention:** the snippets below show the **remote** form,
`ssh <bastion> '<cmd>'`. In **local mode, drop the `ssh <bastion>` wrapper** and
run `<cmd>` directly — the paths (`~/secrets.env`, `~/.kube`,
`~/matrix-runs/<stamp>`) are the same, just on this host. `RESUME_STAMP` and
`DRY_RUN` behave identically in both modes.

---

## Phase 1 — Gather the matrix spec

**First, always ask: local or remote?** (see *Execution mode*) — local runs on
this host (default); remote sets `BENCH_REMOTE=1` + the `BASTION_*` connection
env. Then determine exactly what to run. Ask the user (your harness's clarify path — see *Harness portability*) for
anything not given;
do not guess on dimensions that cost clusters/time. You need:

1. **Tasks** — `MATRIX_TASKS` (space-separated `*/task.yaml` paths, or `ALL`).
2. **Models** — `MATRIX_MODELS` (e.g. `gemini-3.1-pro-preview gemini-3.5-flash`).
3. **Agent configs** — refactored arm only: `MATRIX_AGENT_CONFIGS`, each
   `oc|gcli` `[+mcp][+skills]` (e.g. `gcli+mcp+skills oc+mcp+skills`).
4. **Arm(s)** — refactored (`run_matrix.sh`), legacy (`run_matrix_legacy.sh`,
   oc-only), or both in parallel.
5. **Auth mode** — API-key vs **Vertex/ADC** (`BENCH_VERTEX=1`). If unsure,
   recommend Vertex (no key handling, VM-SA ADC).
6. **Concurrency** — `MAX_PARALLEL` (default 3). Each combo provisions its own
   cluster; mind project quota. Count combos = tasks × models × configs.

Compute and **state the combo count and rough wall-clock** (≈25–40 min/combo for
infra-bearing tasks like secret-rotation) before launching, so the user can
confirm scale. Then run with `DRY_RUN=1` and show the expanded matrix.

Note the parallel-safety rule (see `docs/parallel-evals.md`): **legacy + gemini
CLI is not parallel-safe** — for parallel gemini, use the refactored arm.

**Pre-flight the matrix tasks for parallel hazards** before a real run — a doomed
combo wastes a cluster + ~30 min. Skim each selected task's stack/scripts (or run
the `devops-bench-review` skill on it) against the per-run isolation gaps in
`docs/parallel-evals.md` (known-issues appendix). The ones that bite a matrix:
- a task that seeds a fixed `$HOME` repo (`~/<task>-repo.git`) and `rm -rf`s it —
  unsafe once the matrix repeats that task across models/configs;
- a multi-cluster stack whose node-SA name collapses under the run-token prefix;
- a per-task stack that grants a project role to the shared VM SA (teardown
  clobber across concurrent GKE combos);
- duplicate `task_id`s among the selected tasks (ambiguous reporting);
- host capacity: sum kind clusters / disk / inotify across `MAX_PARALLEL`.

Never run two of the **same** combo at once — run-id-derived cluster names are
reused (safe only because the prior run tore down first).

---

## Phase 2 — Credentials & environment

Set the **connection env** (**remote mode only** — same as `sync-to-bastion.sh`;
skip it entirely for a local run):

```bash
export BASTION_USE_GCPNODE=1 BASTION_VM=bench-bastion \
       BASTION_ZONE=us-central1-a BASTION_PROJECT=<proj> GCP_PROJECT_ID=<proj>
```

**API-key mode:** the remote runner sources `~/secrets.env` on the VM, which must
export `AGENT_API_KEY`, `GEMINI_API_KEY`, `GOOGLE_API_KEY`, `JUDGE_API_KEY`.
Check it exists and has the needed keys (names only — **never print key values**):

```bash
ssh <bastion> 'grep -oE "^[A-Z_]+=" ~/secrets.env | sort -u'
```

If a required key is missing, **ask the user for it** (your harness's clarify path) (or have
them paste it with the `!` prefix so it isn't echoed), then append it to
`~/secrets.env` on the VM. Treat keys as secrets: don't log them, don't commit
them, redact in any summary.

**Vertex mode (`BENCH_VERTEX=1`):** no API keys needed. Verify prereqs instead:
- VM SA has `roles/aiplatform.user` (+ `container.admin`, `secretmanager.admin`).
- gemini folder-trust: `~/.gemini/settings.json` has
  `security.folderTrust.enabled=false` (else MCP won't load). `vm-setup.sh` sets
  it; if absent, run `vm-setup.sh` or write it.
- For the **legacy oc** arm on Vertex: the `google-vertex` provider must be
  registered — run `scripts/bastion/configure-oc.sh --vertex` once.
- `_matrix_lib.sh` defaults `JUDGE_MODEL=gemini-3.1-pro`, which **404s on
  Vertex** — always set `JUDGE_MODEL=gemini-3.1-pro-preview` and
  `AGENT_PROVIDER=google-vertex`. Location is `global` (handled by `BENCH_VERTEX`).

If the legacy arm needs capabilities, run `configure-oc.sh --mcp --skills`
(or `--no-mcp --no-skills` for a clean no-capability run) once before launching.

---

## Phase 3 — Connect and ensure a clean environment

1. **Connectivity:** `ssh <bastion> 'echo OK; oc --version; gemini --version'`.
   Transient `exit 255` is a gcpnode/cert blip — retry a couple times.
2. **No stale processes:** check for and kill leftover runners/agents from prior
   aborted runs:
   ```bash
   ssh <bastion> 'pgrep -af "matrix-runner|evaluate.py|devops_bench|oc agent" | grep -v pgrep'
   ```
3. **No leftover GCP resources** (a prior failed teardown can `409` your run):
   ```bash
   gcloud container clusters list --project <proj>
   gcloud iam service-accounts list --project <proj> | grep -E 'gke-nodes-|sa-secret-rotation-'
   gcloud secrets list --project <proj> | grep db-credentials
   ```
   If anything is left over, confirm it isn't from another active run, then delete
   it — **especially the easy-to-miss `gke-nodes-*` SAs** (their orphaning is a
   known bug; see `docs/parallel-evals.md`).
4. **Prereqs present:** `~/gke-mcp` (executable), `~/oc-skills/` (if using skills),
   `~/devops-bench/.venv`, and — for **chaos tasks** (e.g. `optimize-scale`) — the
   `fortio` binary on PATH (the chaos agent shells out to it for `generate_load`;
   without it the load spike silently no-ops). If anything is missing, run
   `scripts/bastion/vm-setup.sh`.
5. **Clear stale per-run state before EVERY run** (not just a single-task rerun).
   On a persistent bastion the per-run state dir is keyed by `task__model__arm`,
   so state from ANY prior run is reused — even a fresh full-matrix launch then
   fails at `tofu plan` with *"could not locate any control plane nodes for cluster
   …"* (against an already-deleted cluster), or a GitOps seed `rm -rf` trips on a
   leftover repo. Wipe ALL of it (not just one task) up front:
   ```bash
   ssh <bastion> 'rm -rf /tmp/devops-bench-runs/* ; \
                  for c in $(kind get clusters); do kind delete cluster --name "$c"; done'
   ```
   Also clear stale GitOps bare repos the seeds recreate
   (`~/app-repo.git`, `~/opa-repo.git`, `~/migration-repo.git`) if a prior run left
   them — if one is **root-owned** (e.g. from an old Docker-based run), the seed's
   `rm -rf` fails under `set -e`; remove it with `sudo rm -rf`.

---

## Phase 4 — Launch the matrix (detached)

By default the wrappers run the matrix **locally** (detached `nohup` on this
host). With `BENCH_REMOTE=1` they sync the working tree to the bastion, upload a
runner, and launch it detached over ssh, then poll. To run **both arms in parallel**: sync
once, then start each wrapper with `SKIP_SYNC=1`, staggered ~5s so their
second-resolution `STAMP`s differ.

Run each wrapper as a **background job** so you keep control to monitor. Build the
env from Phase 1–2, e.g. Vertex refactored:

```bash
# local by default; prefix BENCH_REMOTE=1 (+ BASTION_* env) to run on the bastion
BENCH_VERTEX=1 AGENT_PROVIDER=google-vertex \
JUDGE_PROVIDER=google JUDGE_MODEL=gemini-3.1-pro-preview \
MAX_PARALLEL=<n> MATRIX_TASKS="..." MATRIX_MODELS="..." \
MATRIX_AGENT_CONFIGS="..." RESULTS_DIR="results/<label>" \
  scripts/bastion/run_matrix.sh
```

**Capture the `STAMP`** each wrapper prints (`RESUME_STAMP=<stamp>`). It is your
handle for monitoring, retry, and re-attach. Record it (and the combo list) in durable state (a
task list or a notes file) so you survive a context reset. Outputs live on the runner host at
`~/matrix-runs/<stamp>/<rid>/` (`run.log`, `status`); a `~/matrix-runs/<stamp>/.done`
marker appears when all combos finish.

If your poller dies, the run continues (detached on the runner host) — re-attach
with `RESUME_STAMP=<stamp>` and the same command.

---

## Phase 5 — Monitor periodically + retry infra flakes

> **Long or hands-off run? (default for real runs)** Read
> `references/resilient-monitoring.md` and delegate polling/analysis to tiered
> subagents — a cheap model (Haiku / Flash-low) polls, a mid model (Sonnet /
> Flash-medium) analyzes finished combos, you supervise and re-spawn on API errors.
> It also covers keeping the background job from being classified as finished
> mid-run. The inline steps below are the direct (small-matrix / foreground) path.

Check progress on an interval (every ~3–5 min for infra-bearing tasks). **Don't
busy-poll**; sleep between checks. Per tick, inspect each combo:

```bash
ssh <bastion> 'for d in ~/matrix-runs/<stamp>/*/; do
  echo "$(basename $d): status=$(cat $d/status 2>/dev/null || echo running) \
        last=$(tail -1 $d/run.log 2>/dev/null | cut -c1-80)"; done
ssh <bastion> 'test -f ~/matrix-runs/<stamp>/.done && echo ALL_DONE'
```

Classify each combo:
- **Running** — no `status` file, runner process alive. Leave it.
- **Finished** — `status` is `exit=<rc>`. `rc=0` = ran to completion (score
  separately); `rc!=0` = the harness errored (diagnose in Phase 6).
- **Aborted / flaked** — no `status` **and** no live process, or `run.log` shows
  an **infra** error. This is the retry case.

**Distinguish infra flake from real failure** (consult the failure-mode table in
`docs/parallel-evals.md`):
- **Infra flake → clean + retry:** tofu apply/provision failure, `409 already
  exists` (orphaned `gke-nodes-*` SA), GKE quota/transient API error, SSH/relay
  drop that killed the runner, node pool creation timeout.
- **Real failure → do NOT retry, analyze:** auth/config errors (`No API key`,
  `401`, Vertex `404`, missing `--approval-mode`), agent ran but scored low
  (model capability), task-logic failures. Retrying won't help; fix config or
  report.

**Retry procedure** for a flaked combo (cap at 2 retries; log every retry —
never silently drop a combo):
1. Kill any lingering process for that combo on the VM.
2. Delete its remote run dir: `rm -rf ~/matrix-runs/<stamp>/<rid>`.
3. Clean leaked GCP resources for it: its cluster (`c<hash>-eval`), the matching
   `gke-nodes-<hash>` SA, and any `sa-secret-rotation-*` / `db-credentials-*`
   left behind (Phase 3 commands).
4. Re-launch **just that combo** as a fresh single-combo matrix (same task/model/
   config, new `STAMP`, `SKIP_SYNC=1`). Track the new stamp.

If the **whole** detached runner died (no `.done`, no live process, partial
combos), re-attach with `RESUME_STAMP`; if that shows it's truly dead, relaunch
the unfinished combos.

> **Unlimited / self-healing mode?** If (and only if) the user opted in, a *real*
> (non-flake) failure caused by a task/code bug is not the end — read
> `references/unlimited-mode.md` and follow diagnose → fix → re-sync → restart
> instead of just reporting it.

---

## Phase 6 — Summarize results + diagnose failures

When every combo has a terminal `status` (or `.done` is present), pull results
(the wrapper does this on its normal exit; otherwise `RESUME_STAMP=<stamp>` re-run
to pull) and produce a **comprehensive summary**.

For each combo report: **task · model · agent-config · arm · auth-mode · exit ·
score · #MCP-tool-calls · pass/fail checks**. Read scores from the pulled
results:

```bash
# per-check pass/fail
grep -c 'Pass Rate: 100.0%' <combo>/run.log   # passed
grep -c 'Pass Rate: 0.0%'   <combo>/run.log   # failed
# tool usage (MCP shows as mcp_<server>_<tool>)
grep -oiE 'mcp_[a-z0-9_-]+|run_shell_command|activate_skill' <combo>/run.log | sort | uniq -c
```
`results.json` is a **list** of per-criterion objects (`{name, score, success,
reason}`). Refactored results nest under `run_<ts>_<rid>/results.json`; legacy
writes `results/run_<ts>_<rid>` copied into the combo dir.

### Aggregate per-task runs for the dashboard

The matrix runs **one task per process**, so each combo emits its own
`run_<ts>_<rid>/rows.json` with a unique runId and its own `t`. The leaderboard
models a *run* as a batch of tasks sharing one `runId`/`t` (tasks told apart by
`taskFolder`), so combine the per-task runs into one batch run before ingest:

```bash
# Scans the pulled tree for per-task rows.json, stamps one shared batch runId
# (run_<ts>_<pid>) + t across every row, and writes a combined rows.json +
# per-setup manifests.json under the output dir. Pass --run-id "$RUN_ID" to
# reuse the matrix id instead of the generated one.
python -m devops_bench.results.aggregate <results-root> -o <results-root>
```

Then ingest the combined `rows.json` (see `site_new/ingest/`). Each setup shows
as one run with all its tasks; re-running the matrix adds a new history point
(the batch runId's suffix keeps separate matrix runs distinct).

Beware grep false positives: bare `401`/`quota` match terraform output
(`92401222`, `cpu_cfs_quota`). Anchor on `invalid_api_key`, `ProviderAuthError`,
`No API key`, `^OK$`.

**For every non-passing / errored combo, give an analysis:**
- What happened (quote the decisive log line, redacting secrets).
- **Root cause** — map it to an entry in the `docs/parallel-evals.md` failure
  table where possible (e.g. `exit -1` = a **timeout**, not a crash;
  `No API key` under isolation = the sqlite-store vs `GOOGLE_CLOUD_API_KEY`
  marker issue; Vertex `404` = wrong location/model).
- **Whether it's the model or the harness** — a clean trajectory with a low score
  is the model; an early abort/auth error is the harness/config.
- **Concrete fix or next step**, and whether a retry would help.

Then **verify teardown is clean** (Phase 3 GCP checks — zero leftover clusters /
`gke-nodes-*` / `sa-secret-rotation-*` / `db-credentials-*`) and report any
residue you couldn't remove.

**Record any new failure mode** — this capture step is part of the run, not
optional. If a combo failed in a way **not** already in the
`docs/parallel-evals.md` failure-mode table or known-issues appendix (or the
`docs/bastion.md` appendix for bastion-host / VM-SA issues), append it so the next
run benefits:
- a **symptom → root cause → fix** row in the failure-mode table for an
  operational flake;
- a known-issues bullet/row for a **structural** gap (isolation, naming, capacity).

Keep it terse, don't duplicate an existing entry, and follow the docs conventions
(scope + user-guide, GFM, not journal-like, no model scores).

End with: total combos, passed/failed counts, best performer, the headline score
table, and the list of failures with their root cause + fix.

---

## Guardrails

- Each combo costs a real GKE cluster + ~25–40 min. Confirm the combo count with
  the user before launching a large matrix; use `DRY_RUN=1` first.
- Never print or commit API keys; redact secrets in summaries.
- Always confirm clean teardown — orphaned `gke-nodes-*` SAs silently break the
  next run with `409`.
- Cap retries (≤2/combo) and surface anything still failing rather than looping.
- Capture every **new** failure mode in the `docs/parallel-evals.md` /
  `docs/bastion.md` appendices (see Phase 6) so learnings accrue across runs.
- Prefer leaving the run detached + re-attaching via `RESUME_STAMP` over holding a
  fragile foreground SSH session.
- **Don't let an idle timeout / completion classifier stop the job mid-run** (if
  your harness has one). A long detached
  matrix has quiet stretches; never emit a completion / `result:` / "done" /
  "failed" line until *every* combo is terminal and summarized. Each check-in, emit
  a one-line "still working: N running / M done / K flaked" status and schedule the
  next wake (see `references/resilient-monitoring.md`) rather than going silent.
- **Progressive disclosure:** read a `references/*.md` file only when its mode
  applies; don't load both for a plain run.
- **Cluster-mutation blast radius (with-mcp + owner SA).** The bench SA needs broad
  rights (`owner`/`container.admin`), so gke-mcp exposes *every* real cluster in the
  project as a writable target. On manifest-generation tasks (computeclass-*,
  gateway-*, hpa-*) — which should just emit YAML — the agent sometimes runs
  `gcloud container clusters update/upgrade` against an unrelated cluster it
  discovers. These ops are long-running with no agent timeout, so the run **hangs**
  (no score) and may mutate a cluster the eval never provisioned (teardown won't
  clean it). Mitigations: run such tasks in a project with **no other clusters**,
  or watch the logs for `clusters update|upgrade|delete` and kill the offending
  `gcloud` (the agent then falls back to `generate_manifest`). Don't auto-revert a
  change to a cluster you don't own.
