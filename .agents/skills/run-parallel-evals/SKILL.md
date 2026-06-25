---
name: run-parallel-evals
description: >
  Use when the user wants to run a parallel evaluation matrix (Task × Model ×
  AgentConfig) on the GKE eval bastion — e.g. "run a parallel eval matrix",
  "run these evals on the bastion", "run the matrix for <tasks/models>",
  "kick off a Vertex eval run", "compare legacy vs refactored on the bastion".
  Drives the whole lifecycle: gather the matrix spec + credentials, set up the
  bastion cleanly, launch the detached run, monitor and retry infra flakes, then
  summarize results and diagnose failures.
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

## Phase 1 — Gather the matrix spec

Determine exactly what to run. Use **AskUserQuestion** for anything not given;
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

---

## Phase 2 — Credentials & environment

Set the **connection env** (same as `sync-to-bastion.sh`):

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

If a required key is missing, **ask the user for it via AskUserQuestion** (or have
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
   `~/devops-bench/.venv`. If missing, run `scripts/bastion/vm-setup.sh`.

---

## Phase 4 — Launch the matrix (detached)

The wrappers sync the working tree, generate a runner, upload it, and launch it
**detached under `nohup`**, then poll. To run **both arms in parallel**: sync
once, then start each wrapper with `SKIP_SYNC=1`, staggered ~5s so their
second-resolution `STAMP`s differ.

Run each wrapper as a **background job** so you keep control to monitor. Build the
env from Phase 1–2, e.g. Vertex refactored:

```bash
BENCH_VERTEX=1 AGENT_PROVIDER=google-vertex \
JUDGE_PROVIDER=google JUDGE_MODEL=gemini-3.1-pro-preview \
MAX_PARALLEL=<n> MATRIX_TASKS="..." MATRIX_MODELS="..." \
MATRIX_AGENT_CONFIGS="..." RESULTS_DIR="results/<label>" \
  scripts/bastion/run_matrix.sh
```

**Capture the `STAMP`** each wrapper prints (`RESUME_STAMP=<stamp>`). It is your
handle for monitoring, retry, and re-attach. Record it (and the combo list) in a
TaskList so you survive a context reset. Remote outputs live at
`~/matrix-runs/<stamp>/<rid>/` (`run.log`, `status`); a `~/matrix-runs/<stamp>/.done`
marker appears when all combos finish.

If your local poller dies, the run continues on the VM — re-attach with
`RESUME_STAMP=<stamp>` and the same command.

---

## Phase 5 — Monitor periodically + retry infra flakes

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
- Prefer leaving the run detached + re-attaching via `RESUME_STAMP` over holding a
  fragile foreground SSH session.
