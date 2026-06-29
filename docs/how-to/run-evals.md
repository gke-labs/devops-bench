# Running evals

This is the practical guide to running DevOps-bench evaluations — one task on one
model, or a whole matrix of tasks across models and agent configs.

There are two layers, and it helps to keep them straight:

- **The CLI** (`python -m devops_bench` / the `devops-bench` console script) runs
  **one task source in one process**: it loads tasks, optionally provisions a
  cluster, runs the agent, judges the result, and writes artifacts. This is the
  primitive.
- **The matrix wrapper** (`scripts/bastion/run_matrix.sh`) expands a
  **Task × Model × AgentConfig** matrix and launches **many isolated CLI
  processes** concurrently — each in its own cluster, with its own results.

A single eval is just a 1×1×1 matrix. Learn the CLI first; the matrix is the same
thing, fanned out.

---

## Prerequisites

Install the package with all optional providers:

```bash
uv sync --extra all
```

For **no-infra** runs (no real cluster) that's all you need. For **real GKE / kind**
runs you also need the co-located toolchain (`gcloud`, `kubectl`, `tofu`, `kind`,
the agent binaries) and authenticated GCP credentials. The eval **bastion** provides
all of this out of the box — see [bastion](../components/bastion.md). Running real
infra runs from a laptop means reproducing that toolchain yourself.

### Authentication

Pick one of two auth modes:

| Mode | How | Notes |
|---|---|---|
| **Vertex / ADC** | `BENCH_VERTEX=1`, **no API keys** | Agents and judges use the VM service account's ADC. **Recommended** — no key handling. |
| **API keys** | Provider env vars (`AGENT_API_KEY`, `GEMINI_API_KEY`, `GOOGLE_API_KEY`) + `JUDGE_API_KEY` | The runner sources these from `~/secrets.env` on the bastion. Never print or commit key values. |

> [!TIP]
> Prefer Vertex/ADC. It removes per-key plumbing and is the only mode that stays
> portable across the isolated per-run state dirs that parallel runs create.

---

## Run a single eval (the CLI)

The CLI is the primitive everything else builds on. The shape is:

```bash
python -m devops_bench [flags] <source>
```

- **`source`** (positional, required) is either a **tasks directory** or a single
  **`task.yaml`** / `.yml` / `.json` spec file. A directory runs every task it
  finds; a single file runs just that task.
- **`--project` and `--cluster` are required** unless you pass `--no-infra` (or set
  `BENCH_NO_INFRA=true`). With infra disabled, no GCP project or cluster is needed.
- **The agent and model are chosen by environment variables**, not flags. There is
  no `--model` flag — set `AGENT_PROVIDER`, `AGENT_MODEL`, and the agent type
  (`BENCH_AGENT_TYPE` / `AGENT_TARGET`) in the environment.

### Example: quick no-infra run

No cluster, fast feedback — good for smoke-testing a task spec or an agent config:

```bash
BENCH_NO_INFRA=true \
AGENT_PROVIDER=gemini AGENT_MODEL=gemini-3.1-pro-preview AGENT_API_KEY=$GEMINI_KEY \
JUDGE_PROVIDER=gemini JUDGE_MODEL=gemini-3.1-pro-preview JUDGE_API_KEY=$GEMINI_KEY \
python -m devops_bench --no-infra tasks/noop/create-deployment/task.yaml
```

### Example: a real GKE task

Provisions a cluster, runs the agent against it, then tears it down. Note
`--parallel`, which isolates this run's kubeconfig / gcloud config / tofu data dir
and gives it a run-unique cluster name so it can coexist with other runs:

```bash
export GCP_PROJECT_ID=my-proj GKE_CLUSTER_NAME=eval GCP_LOCATION=us-central1-a
AGENT_PROVIDER=google-vertex AGENT_MODEL=gemini-2.5-pro BENCH_AGENT_TYPE=gemini AGENT_TARGET=gemini \
JUDGE_PROVIDER=google JUDGE_MODEL=gemini-3.1-pro-preview \
python -m devops_bench --parallel --run-id myrun \
  --project my-proj --cluster eval --results-root results/myrun \
  tasks/gcp/secret-rotation/task.yaml
```

---

## CLI flags

Flags override the environment; anything you don't pass falls back to its env var.

| Flag | Meaning |
|---|---|
| `source` (positional) | Tasks directory or a single `task.yaml` / `.yml` / `.json` spec. |
| `--project` | GCP project id (required unless `--no-infra`). |
| `--cluster` | GKE cluster name (required unless `--no-infra`). |
| `--limit N` | Run only the first N tasks from the source. |
| `--results-root DIR` | Root directory for run artifacts (default `results`). |
| `--agent-type` | Override `BENCH_AGENT_TYPE`. |
| `--judge-provider` | Override `JUDGE_PROVIDER`. |
| `--judge-model` | Override `JUDGE_MODEL`. |
| `--no-infra` / `--infra` | Skip / force infrastructure provisioning. |
| `--no-teardown` / `--teardown` | Skip / force teardown of provisioned infra. |
| `--parallel` | Isolate this run (own kubeconfig / gcloud config / tofu data dir + run-unique cluster name) so it can run concurrently with others. |
| `--run-id` | Explicit run id for isolation and artifact naming (default: `RUN_ID` env or a generated id). |

**Exit codes:**

| Code | Meaning |
|---|---|
| `0` | No task failed. |
| `1` | At least one task failed. |
| `2` | Configuration error (e.g. infra enabled but project/cluster missing). |

**Environment variables that affect a run.** Each maps to a flag or config field;
flags win when both are set:

| Variable | Effect |
|---|---|
| `PROJECT_ID` / `GCP_PROJECT_ID` | GCP project id (either name works). |
| `CLUSTER_NAME` / `GKE_CLUSTER_NAME` | GKE cluster name (either name works). |
| `EVAL_LIMIT` | Cap the number of tasks run. |
| `RESULTS_ROOT` | Root directory for artifacts. |
| `BENCH_AGENT_TYPE` | Agent type to run. |
| `JUDGE_PROVIDER` / `JUDGE_MODEL` | Judge model used to grade results. |
| `BENCH_NO_INFRA` | Skip provisioning when truthy. |
| `BENCH_NO_TEARDOWN` | Skip teardown when truthy. |
| `BENCH_PARALLEL` | Enable per-run isolation when truthy. |
| `RUN_ID` | Explicit run id for isolation / artifact naming. |

---

## Use the `run-eval` skill

If you'd rather not assemble the command and babysit it yourself, the **`run-eval`**
skill orchestrates a single eval end to end: it gathers the spec and credentials,
ensures a clean runner, launches the run detached, monitors it with recovery (it can
re-attach if your session drops), then summarizes and diagnoses the result. It runs
**locally by default**; set `BENCH_REMOTE=1` to drive it on the bastion. Always
preview with `DRY_RUN=1` first to confirm exactly what will run before you spend a
cluster.

---

## Run a matrix (parallel evals)

This is where the wrapper earns its keep. A **combo** is one
`(task, model, agent-config)` triple. The matrix is the Cartesian product:

```
MATRIX_TASKS × MATRIX_MODELS × MATRIX_AGENT_CONFIGS
```

capped at `MAX_PARALLEL` running at once.

> [!IMPORTANT]
> **Each combo provisions and tears down its own cluster** and writes its own
> results. Combos share no mutable state — that's what makes the matrix safe to run
> wide.

The launcher runs detached under `nohup`, polls for a `.done` marker, and pulls
results back. If your laptop sleeps or your SSH connection drops, **the run keeps
going** — re-attach with `RESUME_STAMP`.

### Command (Vertex, remote on the bastion)

```bash
export BENCH_REMOTE=1
export BASTION_USE_GCPNODE=1 BASTION_VM=bench-bastion BASTION_ZONE=us-central1-a \
       BASTION_PROJECT=<proj> GCP_PROJECT_ID=<proj>
BENCH_VERTEX=1 AGENT_PROVIDER=google-vertex \
JUDGE_PROVIDER=google JUDGE_MODEL=gemini-3.1-pro-preview \
MAX_PARALLEL=3 \
MATRIX_TASKS="tasks/gcp/secret-rotation/task.yaml" \
MATRIX_MODELS="gemini-3.1-pro-preview gemini-3.5-flash" \
MATRIX_AGENT_CONFIGS="gcli+mcp+skills oc+mcp+skills" \
  scripts/bastion/run_matrix.sh
# re-attach after a dropped connection:
RESUME_STAMP=<stamp> scripts/bastion/run_matrix.sh
```

The wrapper prints a `STAMP` on launch (`RESUME_STAMP=<stamp>`). Hold on to it — it's
your handle for monitoring and re-attaching. Outputs land on the runner host under
`~/matrix-runs/<stamp>/`.

### Matrix knobs

| Variable | Meaning |
|---|---|
| `MATRIX_TASKS` | Space-separated `task.yaml` paths, or `ALL` to enumerate every task. |
| `MATRIX_MODELS` | Space-separated model ids. |
| `MATRIX_AGENT_CONFIGS` | Agent-config presets, each `oc\|gcli` `[+mcp][+skills]` (e.g. `gcli+mcp+skills`). |
| `MAX_PARALLEL` | Max combos running at once (default 3). **Each combo is its own cluster — mind your quota.** |
| `AGENT_TIMEOUT_SEC` | Per-agent timeout (default 1200 in the matrix; the bare harness default is lower). |
| `BENCH_VERTEX` | Run agents + judges against Vertex via VM-SA ADC (no API keys). |
| `BENCH_REMOTE` | Run on the bastion over SSH; unset runs every combo locally on this host. |
| `SKIP_SYNC` | Skip the working-tree sync to the bastion (after you've already synced once). |
| `DRY_RUN` | Print the expanded matrix + per-combo env without provisioning anything. |
| `RESUME_STAMP` | Skip launching; re-poll and pull an existing run by its stamp. |
| `RESULTS_DIR` | Where pulled results land (default `results/matrix`). |

> [!TIP]
> Always `DRY_RUN=1` first. It confirms the combo count before you commit clusters —
> at roughly **25–40 minutes per combo** for an infra-bearing task, a typo in
> `MATRIX_MODELS` is an expensive mistake.

For long or hands-off matrices, the **`run-parallel-evals`** skill drives this whole
lifecycle with monitoring and infra-flake retry built in, plus opt-in
resilient-monitoring and self-healing modes.

**Related skills.** To vet a *new* task in a self-healing loop, use **`validate-eval`**. To clear
leaked cloud resources after aborted runs, use **`cleanup-orphaned-resources`**. To understand *why*
a model scored low on a run, use **`diagnose-eval-failure`**.

---

## Where results go & how to read them

**A matrix run** writes one directory per combo under the results root:

```
<results-root>/<stamp>/<combo>/
├── status              # "exit=<rc>" once the combo finishes
├── run.log             # full stdout/stderr for the combo
└── run_<ts>_<rid>/
    └── results.json    # the judged, per-criterion scores
```

**A bare CLI run** writes a single run directory:

```
results/run_<ts>[_<rid>]/
├── results.json        # list of per-criterion results {name, score, success, reason}
├── rows.json           # flattened, ingest-ready rows
└── manifest.json       # run-level metadata
```

`results.json` is a **list** of per-criterion objects, each with `name`, `score`,
`success`, and `reason`. For how scoring works and how to interpret it, see
[metrics](../components/metrics.md).

---

## Aggregating + publishing

The matrix runs **one task per process**, so each combo emits its own `rows.json`
with a unique run id. The leaderboard models a *run* as a batch of tasks sharing one
run id, so combine the per-task rows into a single batch before ingesting:

```bash
python -m devops_bench.results.aggregate <results-root> -o <results-root>
```

This scans the tree for per-task `rows.json` files, stamps a single shared batch run
id and timestamp across every row, and writes a combined `rows.json` plus per-setup
`manifests.json`. Pass `--run-id <id>` to reuse the matrix's own id instead of a
generated one.

Then ingest the combined rows through the leaderboard pipeline — see
[the leaderboard guide](./leaderboard.md).

---

## When something fails

Most failures during parallel runs are **infra flakes** — a transient API error, a
node-pool timeout, a leftover resource that `409`s — and the right response is simply
to clean up and retry. A router of concrete symptoms mapped to fixes lives in the
[known issues appendix](../appendix/known_issues.md). **Start there** when a run
misbehaves; it covers the failures you're most likely to hit.

> [!WARNING]
> Before re-running anything, clean up stale per-run state and orphaned cloud
> resources (clusters, `gke-nodes-*` service accounts, leftover secrets). A skipped
> cleanup is the single most common cause of a re-run failing the same way the first
> one did.

---

See also: [bastion](../components/bastion.md) · [metrics](../components/metrics.md) ·
[leaderboard](./leaderboard.md) · [project README](../../README.md).
