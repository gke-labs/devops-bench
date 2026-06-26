---
name: devops-bench-review
description: >
  Use when the user asks for a comprehensive review of devops-bench changes —
  e.g. "review this PR", "review the workspace", "review my changes", "is this
  task parallel-safe", "review this new task/stack/doc", "will this break under
  the parallel matrix". Reviews a PR (number/URL) or the current working tree
  across four lenses — correctness, parallel-safety across the eval matrix axes,
  task/stack conventions, and docs conventions — and returns ranked, actionable
  findings. The parallel-safety lens is the emphasis: it hunts for shared state
  that makes a task fail when many runs execute at once. This skill is
  review-only: it analyzes statically and may run unit tests, linting, and
  formatting checks, but it NEVER runs benchmark evals or provisions infra.
---

# devops-bench comprehensive review

Review either a **GitHub PR** or the **current workspace** for devops-bench, then
return ranked findings a maintainer would act on. The defining lens here — beyond
ordinary correctness — is **parallel-safety**: this repo runs an eval matrix
(Task × Model × AgentConfig) where many evaluations execute concurrently on one
host, and the most common way a new task/stack/script is "correct alone but wrong
in the matrix" is that it touches a resource shared across runs.

**Read these first when the change touches tasks, TF stacks, or run isolation —
they are the source of truth; don't reconstruct them from memory:**
- `docs/parallel-evals.md` — per-run isolation model, the **parallel-safety
  matrix**, the **failure-mode -> fix** table, and the **known-issues** appendix.
- `docs/bastion.md` — bastion architecture, provisioning, per-run isolation.
- The isolation primitive itself: `devops_bench/core/run_env.py` (`RunEnv`) and
  its legacy mirror `pkg/runenv.py`. Confirm what it actually isolates before
  asserting a collision is or isn't covered.
- Governing **agent-instruction files** — whichever your harness uses (`CLAUDE.md`,
  `AGENTS.md`, `GEMINI.md`), at user level and at the repo root, plus any in a
  directory that is an ancestor of a changed file — quote the exact rule when you
  flag a violation.

Work the phases in order. Default to **precision**: every finding should name a
concrete failure (inputs/state -> wrong outcome), not a style preference.

---

## Scope & guardrails — review only, never run evals

This skill **analyzes and reports**. It does **not** execute the benchmark, and it
finds parallel-run hazards by **reading and reasoning** about the task/stack/
scripts — never by launching runs to observe a collision.

**May run** (only to validate the code under review):
- Unit / integration tests for the changed code (`pytest` / the repo's runner).
- Linting (`ruff`) and formatting **checks** (e.g. `ruff format --check`) — report
  violations; do not reformat or modify files as part of a review.

**Must NOT run — out of scope, stop and report instead:**
- Benchmark evaluations or the eval matrix: `pkg/evaluator/evaluate.py`,
  `python -m devops_bench`, `scripts/bastion/run_matrix*.sh`, or any agent/judge
  invocation.
- Infrastructure provisioning or teardown: `tofu`/`terraform apply|destroy|plan|
  init`, `gcloud ... create/delete`, `kind create/delete cluster`, `kubectl
  apply/delete`.
- Anything that spends cloud resources or calls a model/agent API.

If reviewing a change would seem to *require* running it (e.g. "does this task
actually pass?"), do not run it — report what static analysis shows and state that
an actual eval run is out of scope for this skill.

---

## Phase 0 — Scope the target and gather the diff

Determine the target from the user's request:

- **A PR** (number or URL): use `gh`, not local git.
  - `gh pr view <target> --json title,body,author,baseRefName,headRefName,state,additions,deletions,changedFiles,labels`
  - `gh pr diff <target>`
  - When an angle needs surrounding code, Read the file in this checkout if it
    matches the PR branch, else fetch with `git show <ref>:<path>` / `gh`.
- **The current workspace** ("review my changes / the workspace"):
  - `git diff @{upstream}...HEAD` (or `git diff main...HEAD` / `git diff HEAD~1`),
    and also `git diff HEAD` when there are uncommitted changes — review is often
    run pre-commit. Treat the union as scope.

The diff is the review scope. For each touched function, also Read the enclosing
function — bugs on unchanged lines of a touched function are in scope (the change
re-exposes or fails to fix them).

If the change references another PR's mechanism (e.g. "works with the parallel
isolation from PR #N"), fetch that PR's relevant files too, so you review the
**interaction**, not the change in isolation.

---

## Phase 1 — Classify what changed, then route to lenses

Bucket each changed file so you apply the right lens (a PR often spans several):

- **Task spec** — `complextasks/*/task.yaml`, `tasks/**/task.yaml` -> Lens C + B.
- **TF stack / module** — `tf/prebuilt/**`, `tf/modules/**`, `*.tf`, seed/setup
  `scripts/*.sh` -> Lens B (heavily) + C + A.
- **Harness / deployer / agent code** — `devops_bench/**`, `pkg/**`,
  `deployers/**` -> Lens A + B + E + F.
- **Docs** — `*.md`, `README`, `docs/**` -> Lens D.

Always run Lens A (correctness) and Lens B (parallel-safety) on anything
executable; run B on any task/stack because that is where matrix collisions live.

---

## Phase 2 — Review lenses

Run the relevant lenses below. Collect candidate findings with `file`, `line`, a
one-line `summary`, and a concrete `failure_scenario`. Pass through every
candidate with a nameable failure — verification (Phase 3) is where uncertain
ones get cut, not here.

### Lens A — correctness

- **Line-by-line:** inverted/wrong conditions, off-by-one, null/undefined deref,
  missing `await`, falsy-zero checks, wrong-variable copy-paste, swallowed errors,
  unescaped regex/shell metachars, `set -euo pipefail` gaps in bash.
- **Removed behavior:** for each deleted/replaced line, name the invariant it
  enforced and find where it is re-established; a dropped guard/validation/error
  path or deleted test covering a real case is a finding.
- **Cross-file:** for each changed function, Grep its callers and callees — does a
  new precondition, changed return shape, new exception, or timing/ordering
  dependency break a call site?

If the changed code has unit/integration tests, you **may** run them (and `ruff`)
to corroborate a finding — see Scope & guardrails. Do not run anything that
provisions infra or starts an eval.

### Lens B — parallel-safety across the matrix axes (the emphasis)

The eval matrix runs **Task × Model × AgentConfig** concurrently, often N on one
host. `RunEnv` gives each run its own isolation; a change is unsafe when it
introduces state shared *outside* that isolation. Establish this **by static
analysis** — read the stack/scripts/prompt and reason about shared state; do not
run concurrent evals to find out. First ground yourself in what isolation actually
covers (verify against `run_env.py` / `docs/parallel-evals.md`, don't assume):

**Per-run isolation covers:** `KUBECONFIG`, `CLOUDSDK_CONFIG`, `TF_DATA_DIR` (+ TF
state beside it), a run-token-prefixed **cluster name** (short token, prefixed and
clamped to GKE's 40-char limit), per-run **results dir** (run id appended), and
`OPENCLAW_STATE_DIR` (sessions/auth/memory) while sharing `OPENCLAW_CONFIG_PATH`.

**Isolation does NOT cover:** `$HOME` and paths under it, the shared
`tf/prebuilt/<stack>` working dir (`.terraform.lock.hcl`), project-global GCP
resource names that a stack hardcodes, IAM bindings on shared service accounts,
`task_id`, host capacity (disk/inotify/ports), and anything an **agent** creates
at runtime.

**Reason per axis — the same collision can be safe on one axis and fatal on
another.** For each shared-state suspect, ask which axis triggers it:

- **Task axis** (different tasks, same model/config, concurrently): collides only
  if the shared name is **fixed across tasks** or **project-global**. A resource
  whose name is *distinct per task* (e.g. `~/taskA-repo.git` vs `~/taskB-repo.git`)
  is safe here.
- **Model / AgentConfig axis** (same task, different model/config): the **same
  task runs more than once**, so any task-fixed `$HOME`/global name collides — even
  one that was safe on the task axis. `rm -rf` of a shared path becomes a race.
- **Repeated same combo / N-on-one-host:** cluster names derived from run id are
  safe *only because the prior run tore down first* — do not run two of the same
  combo at once; and host resources (kind clusters, disk, inotify, ports) **sum**
  across all concurrent runs.

**Shared-state checklist — flag any of these in changed code:**

1. **`$HOME` / process-global paths.** Bare repos (`~/*-repo.git`), fixed temp
   files, `~/.kube/config`, fixed dirs. `HOME` is **not** isolated. Check: is the
   path task-distinct AND per-run? Is it hardcoded in the **prompt** with no
   template token (prompt only templates `{{CLUSTER_NAME}}`, `{{NAMESPACE}}`,
   `{{PROJECT_ID}}`, etc. — there is no `{{REPO_PATH}}`)? Does a seed/setup script
   `rm -rf` it (a wipe race under the model/config axis)?
2. **Cluster / resource names not flowing through the run token.** Names must
   derive from the harness-supplied (already-prefixed) `cluster_name`. Watch
   **length** (token + base + any stack suffix vs the 40-char GKE limit) and
   **truncations that drop the discriminator** — e.g. a stack that appends
   `-east`/`-west` to a name the gke module then truncates with
   `substr(cluster_name, 0, 15)` collapses both to one node-SA `account_id`.
3. **Project-global GCP names not random-suffixed.** Compare against the
   secret-rotation pattern (appends a `random_id` suffix to `sa-*` /
   `db-credentials-*` so concurrent runs coexist). Known offender: the gke module
   node SA `gke-nodes-<cluster>` is deterministic, not suffixed -> `409 already
   exists` on re-run after a failed teardown (see the known-issues appendix).
4. **IAM bindings on a shared service account.** A stack that grants a project
   role (e.g. `roles/container.admin`) to the shared `openclaw-vm-sa` via
   `google_project_iam_member` in its own TF state: concurrent GKE tasks each
   "own" that binding, and the first `tofu destroy` strips it from the SA while the
   others are still running -> mid-run auth loss.
5. **`task_id` uniqueness.** A new task must not reuse an existing `task_id`
   (`grep -rn '^task_id' complextasks/ tasks/`). Duplicates make per-task scoring
   ambiguous when both run in one matrix.
6. **Agent-created resources & host capacity.** If the task design relies on the
   agent creating clusters/resources at runtime, their names are agent-chosen
   (un-prefixed -> cross-run collision risk) and they multiply host load. Sum the
   per-task disk/inotify/cluster counts across a realistic concurrent batch and
   flag if the single-run README sizing is exceeded.
7. **Provisioner env inheritance.** A `local-exec` seed/setup script is only
   isolated if it inherits the run-scoped `KUBECONFIG`/`CLOUDSDK_CONFIG` — verify
   it doesn't re-point them at `~/.kube/config` or a global gcloud config.
8. **Agent/runner parallel-safety.** Legacy arm + gemini CLI is **not**
   parallel-safe (shared `~/.gemini` trajectory dir); parallel gemini must use the
   refactored arm. Flag changes that reintroduce shared-session assumptions.

For each parallel finding, **state which axis triggers it** and whether it's
already covered by `RunEnv` — that is the distinction maintainers act on.

### Lens C — task & stack conventions

- `task.yaml`: unique `task_id`; `name`; `infrastructure` (`deployer`, `stack`,
  `teardown`); a prompt that uses template tokens rather than hardcoded
  project/cluster/namespace values; `expected_output` as discoverable critical
  requirements (nothing in-cluster should *name* the fix — the agent must discover
  it).
- **Solvability:** there is a real path to success (a manual-solve in the README
  or an equivalent), and the fault is injected from outside the cluster. Assess
  this by reading the stack/scripts — do not provision to check.
- **Substrate parity:** kind stacks declare `kubeconfig_path`/`cluster_name`/
  `location` and emit `cluster_location = "local"`; GKE stacks return
  `cluster_name`/`cluster_location` the deployer expects. New stack variables the
  harness must set (beyond what the kind/gcp variable resolvers inject) are a
  red flag — the resolver won't populate them.
- **Idempotency / teardown:** `teardown: true` actually destroys everything the
  stack and its scripts create; re-apply after a failed run isn't blocked by
  orphans.

### Lens D — docs conventions

Apply the repo's documentation conventions:
- Organize as **scope + user-guide**; GitHub-flavored markdown.
- **Not journal-like** — no migration history, no "why this lives here", no diary
  of what changed.
- No **contradictions or duplication** with existing docs; put caveats in a
  **known-issues appendix** rather than scattering them.
- **No model scores / result tallies** in docs (those are tracked separately);
  results-interpretation and formatting guidance is fine.
- Convert relative dates to absolute; keep examples runnable.

### Lens E — reuse / simplification / efficiency / altitude

- **Reuse:** new code re-implementing an existing helper (Grep shared/utility
  modules and adjacent files; name the helper to call).
- **Simplification:** redundant/derivable state, copy-paste variants, dead code.
- **Efficiency:** redundant I/O, sequential work that could be independent,
  blocking work added to a hot path; closures capturing large scopes.
- **Altitude:** special cases bolted onto shared infrastructure where generalizing
  the underlying mechanism is the deeper fix (e.g. fixing repo-path isolation once
  in `RunEnv` + a prompt token, instead of per-task patches).

### Lens F — code conventions (agent-instruction files)

For Python, enforce the docstring rules from the governing agent-instruction file
(e.g. the user's Google-style rules: purpose; `Args`/
`Returns`/`Attributes`; `Raises`; concise, no implementation narration). Flag a
convention violation only when you can quote the exact rule and the exact line.

---

## Phase 3 — Verify candidates

Dedup candidates that point at the same line/mechanism. For each survivor, decide
one of three states (run an independent verifier pass for non-obvious ones — a
sub-task/subagent if your harness supports one, otherwise re-check it yourself;
for parallel-safety, the verifier should try to *refute* by finding the isolation
that already covers it — by reading code, not by running evals):

- **CONFIRMED** — name the inputs/state and the wrong output/crash; quote the line.
- **PLAUSIBLE** — mechanism is real, trigger depends on env/config/composition
  (common for parallel findings: "fires only if the batch also contains task X").
  State what would confirm it.
- **REFUTED** — guarded elsewhere or factually wrong; quote the proof (e.g. the
  resolver that injects the per-run value, or the `count = ... != "" ? 1 : 0`).

Keep CONFIRMED and PLAUSIBLE. Correctness bugs outrank cleanup/altitude/docs when
trimming.

---

## Phase 4 — Present the review

Do **not** dump raw JSON. Write a readable review:

1. **Overview** — 2–3 sentences on what the change does and how it interacts with
   the parallel-isolation model.
2. **Findings**, most-severe first, each as
   `file:line — summary (failure scenario)`. For parallel findings, state the
   **triggering axis** and whether `RunEnv` already covers it.
3. **Cleared** — a short list of things you checked and found safe (so the author
   knows the coverage), e.g. "cluster name + KUBECONFIG isolation inherited from
   RunEnv ok".
4. **Systemic note** (when applicable) — if several findings share a root cause,
   recommend the seam-level fix once rather than per-site patches.

Scale effort to the ask: a quick "is this parallel-safe?" wants the B-lens
checklist and a verdict; "comprehensive review" wants all lenses and a fuller
findings list. If nothing survives verification, say so plainly. Remember the
scope guardrail: present findings; never run the benchmark to produce them.
