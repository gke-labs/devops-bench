# Parallel evals on the bastion — runbook & lessons learned

How to run the eval matrix (Task × Model × AgentConfig) **in parallel** on the
GCE bastion, against either the **API-key** endpoints or **Vertex AI** (the VM
service account's ADC), for both the **legacy** (`pkg/evaluator`) and
**refactored** (`devops_bench`) arms — plus every non-obvious failure mode and
fix discovered while getting it working.

This is the operational companion to [`docs/bastion.md`](./bastion.md), which
covers the bastion's architecture, provisioning, and the per-run isolation
design. Read that first for the *why*; read this for the *how* and the *gotchas*.

---

## TL;DR

```bash
# Connection (gcpnode/IAP) — same env as sync-to-bastion.sh
export BASTION_USE_GCPNODE=1 BASTION_VM=bench-bastion \
       BASTION_ZONE=us-central1-a BASTION_PROJECT=<proj> GCP_PROJECT_ID=<proj>

# --- API-key mode (secrets.env supplies GEMINI_API_KEY etc.) ---
MATRIX_TASKS="complextasks/secret-rotation/task.yaml" \
MATRIX_MODELS="gemini-3.1-pro-preview" \
MATRIX_AGENT_CONFIGS="gcli+mcp+skills" \
  scripts/bastion/run_matrix.sh                       # refactored arm
MATRIX_MODELS="gemini-3.1-pro-preview" \
  scripts/bastion/run_matrix_legacy.sh                # legacy arm (oc only)

# --- Vertex mode (VM-SA ADC, no API keys) ---
# one-time per bastion: vm-setup.sh (gemini folder-trust) + configure-oc.sh --vertex
BENCH_VERTEX=1 AGENT_PROVIDER=google-vertex \
JUDGE_PROVIDER=google JUDGE_MODEL=gemini-3.1-pro-preview \
MATRIX_TASKS="complextasks/secret-rotation/task.yaml" \
MATRIX_MODELS="gemini-3.5-flash" \
MATRIX_AGENT_CONFIGS="gcli+mcp+skills" \
  scripts/bastion/run_matrix.sh

# Re-attach after a dropped laptop / SSH (the run continues detached on the VM):
RESUME_STAMP=<stamp-printed-at-launch> scripts/bastion/run_matrix.sh
```

`DRY_RUN=1` prints the expanded matrix + per-combo env without provisioning.

---

## Mental model

A **combo** is one `(task, model, agent-config, arm)` tuple. The matrix expands
`MATRIX_TASKS × MATRIX_MODELS × MATRIX_AGENT_CONFIGS` into combos, then runs them
concurrently (capped by `MAX_PARALLEL`). **Each combo provisions and tears down
its own GKE cluster** and writes to its own results dir, so combos never share
mutable infra or agent state.

- `scripts/bastion/run_matrix.sh` — **refactored** arm (`python -m devops_bench`).
  Capabilities (MCP/skills) are wired **per-run via env**, so each combo is fully
  independent. Agent configs: `oc | gcli` `[+mcp][+skills]`.
- `scripts/bastion/run_matrix_legacy.sh` — **legacy** arm (`pkg/evaluator/evaluate.py`).
  Hard-wired to `AGENT_TARGET=oc`; capabilities come from the **global**
  `~/.openclaw` config (set once with `configure-oc.sh`).
- `scripts/bastion/_matrix_lib.sh` — shared library both wrappers source. It
  builds the remote runner, uploads it, launches it **detached under `nohup`**,
  polls for a `.done` marker, and pulls results back. Not run directly.

The local process only **orchestrates**: it generates a runner script, `scp`s it
to the VM, starts it with `nohup`, then polls. If your laptop sleeps or SSH
drops, the run keeps going on the VM — re-attach with `RESUME_STAMP`.

---

## Identity & auth

The agent and judge run **as the bastion VM service account** via ambient ADC
(metadata server). Infra stacks grant the runner *nothing* (no per-run runner SA,
no project IAM binding) — see `docs/bastion.md` "Identity model: BYO credentials".
Ensure the VM SA is broad enough **once, out of band**:

```bash
gcloud projects add-iam-policy-binding <proj> \
  --member="serviceAccount:<vm-sa>@<proj>.iam.gserviceaccount.com" \
  --role="roles/container.admin"      # + roles/secretmanager.admin, roles/aiplatform.user (Vertex)
```

`roles/container.admin` is required for the ExternalSecrets operator's cluster
RBAC; `roles/aiplatform.user` is required for Vertex.

### API-key mode (default)

The remote runner sources `~/secrets.env`, which exports `AGENT_API_KEY`,
`GEMINI_API_KEY`, `GOOGLE_API_KEY`, `JUDGE_API_KEY`. Agents and judges use the
generativelanguage / Anthropic API-key endpoints.

### Vertex mode (`BENCH_VERTEX=1`)

Runs agents **and** judges against Vertex AI via the VM-SA's ADC instead of API
keys. `_matrix_lib.sh` does this when `BENCH_VERTEX` is set: it **unsets every API
key** sourced from `secrets.env` and exports the Vertex env.

| Variable | Value | Why |
|---|---|---|
| `GOOGLE_GENAI_USE_VERTEXAI` | `true` | gemini CLI + google-genai pick Vertex |
| `GOOGLE_CLOUD_PROJECT` | `<GCP_PROJECT_ID>` | Vertex project |
| `GOOGLE_CLOUD_LOCATION` | `global` | gemini CLI / oc transport location |
| `GCP_VERTEX_LOCATION` | `global` | the judges' location (`models/gemini.py`, `evaluate.py`) |
| `GOOGLE_CLOUD_API_KEY` | `gcp-vertex-credentials` | the **oc** ADC marker (see below) |

Plus set `AGENT_PROVIDER=google-vertex` at the wrapper so the legacy oc model id
becomes `google-vertex/<model>`.

**Location must be `global`.** The `gemini-3.x *-preview` models **404 on regional
endpoints** (e.g. `us-central1`). The refactored judge already defaults to
`global`; the **legacy judge defaults to `us-central1`**, so `GCP_VERTEX_LOCATION=global`
is mandatory in Vertex mode.

**Judge model must exist on Vertex.** `gemini-3.1-pro` **404s** on Vertex; use
`JUDGE_MODEL=gemini-3.1-pro-preview`. (The `_matrix_lib.sh` default is
`gemini-3.1-pro`, so always override it for Vertex.)

#### oc → Vertex auth (the tricky one)

OpenClaw (`oc`) has a built-in `google-vertex` provider, but two config steps are
required — a *missing token* is **not** the blocker:

1. The provider entry in `~/.openclaw/openclaw.json` must include
   `"api": "google-vertex"` (and `"baseUrl": "https://{location}-aiplatform.googleapis.com"`).
   **Without `api`, oc routes the provider through the OpenAI transport** and
   sends the credential marker to `platform.openai.com` → `401 Incorrect API key`.
2. The provider needs the literal ADC marker `gcp-vertex-credentials` as its api
   key. oc's `google-vertex` transport treats that marker as "use ADC" and reads
   the real token from `google-auth-library` → **metadata-server ADC** at request
   time (auto-refresh; no ~1h token-paste expiry).

`scripts/bastion/configure-oc.sh --vertex` does both idempotently (registers the
provider + models, allowlists `google-vertex/<model>` for the agent, pastes the
marker).

**Marker portability under isolation.** `oc models auth paste-api-key` stores the
marker only in the **global** agent sqlite auth store
(`~/.openclaw/agents/main/agent/openclaw-agent.sqlite`). Parallel runs set their
own empty `OPENCLAW_STATE_DIR`, so they **don't see it** and fail with
`No API key found for provider "google-vertex"`. The portable fix (what
`BENCH_VERTEX` does) is to export `GOOGLE_CLOUD_API_KEY=gcp-vertex-credentials` —
oc's env-based auth resolver picks up the marker with no per-agent store. The
gemini CLI and the google-genai judge **ignore** `GOOGLE_CLOUD_API_KEY` when ADC
is configured, so it's safe to set globally.

#### gemini CLI → Vertex

Just the env above (`GOOGLE_GENAI_USE_VERTEXAI=true`, project, `GOOGLE_CLOUD_LOCATION=global`,
API keys unset). No marker needed. Confirmed working against `gemini-3.5-flash`
and the `-preview` models.

---

## Agent capabilities (MCP + skills)

### OpenClaw (legacy + refactored `oc` config)

- **Refactored arm**: reads `AGENT_MCP_SERVER` (the `gke-mcp` binary) and
  `AGENT_SKILLS_PATHS`, writes an *isolated* `openclaw.json`, materializes skills
  per-run. Fully independent across combos.
- **Legacy arm**: uses only the **global** `~/.openclaw` config. Wire it with
  `scripts/bastion/configure-oc.sh --mcp --skills` (or `--no-mcp --no-skills` for
  a clean "no capabilities" run). The agent profile is `main`.

### Gemini CLI (refactored `gcli` config) — headless MCP requirements

Making the gemini CLI actually **load and execute** MCP tools (e.g. gke-mcp) in
headless runs needs **two** things — `--skip-trust` alone is **not** enough:

1. **User-level** `~/.gemini/settings.json` with `security.folderTrust.enabled=false`.
   MCP servers are suppressed in *untrusted* folders; the agent's per-run temp cwd
   is untrusted, and a workspace-level setting is **ignored when the folder is
   untrusted** (chicken-and-egg). `--skip-trust` ("trust this session") does **not**
   lift the MCP gate. Set once — `scripts/bastion/vm-setup.sh` does this.
2. **`--approval-mode yolo`** in the argv (in `_build_argv`). Without an approval
   mode, MCP tool calls block on interactive confirmation and the run hangs until
   timeout. It's the modern replacement for the deprecated `--allowed-tools`.

Notes:
- MCP servers come from the workspace `.gemini/settings.json` `mcpServers` and
  stay available even with `--extensions=` — that flag only disables gemini
  *extensions*, which are distinct from MCP servers.
- Disable extensions with `--extensions=` (long form). `-e=` / `-e=""` **print
  help and exit non-zero** on gemini ≥ 0.47 (argv bypasses the shell, so the
  literal quotes reach the parser), and `-e none` loads an extension named "none".
- MCP tools surface in the trajectory as `mcp_<server>_<tool>`
  (e.g. `mcp_default_list_clusters`).
- `gke-mcp` runs as a stdio MCP server by default (no subcommand needed) and
  exposed 34 tools in testing (`list_clusters`, `get_k8s_resource`,
  `patch_k8s_resource`, `get_k8s_logs`, `get_kubeconfig`, …).

---

## Parallel-safety matrix

| Agent | Refactored arm | Legacy arm |
|---|---|---|
| OpenClaw (`oc`) | ✅ parallel-safe | ✅ parallel-safe |
| Gemini CLI (`gemini`) | ✅ parallel-safe | ❌ **not** parallel-safe |

The **refactored** gemini agent runs in a per-run temp cwd with its own
`.gemini/settings.json` + skills and reconstructs the trajectory from process
**stdout** (`--output-format stream-json`), so concurrent runs are independent.
The **legacy** gemini runner reads the trajectory from the shared
`~/.gemini/tmp/.../chats` dir keyed by a short session id, which can pick the
wrong run's trajectory under concurrency — hence `run_matrix_legacy.sh` is
hard-wired to `oc`. For parallel gemini, use the refactored matrix.

---

## Per-run isolation (what keeps combos apart)

- **OpenTofu**: per-run `TF_DATA_DIR`; state file written *beside* it (never at the
  reserved `<TF_DATA_DIR>/terraform.tfstate`).
- **Cluster name**: derived deterministically from the run id (e.g.
  `<hash>-eval`), so re-running the *same* combo reuses the name — safe **only
  because** the prior run tore down first. Don't run two of the *same* combo at once.
- **OpenClaw state**: each run gets its own `OPENCLAW_STATE_DIR` (isolated
  sessions/auth store) while sharing the global `OPENCLAW_CONFIG_PATH`.
- **Gemini CLI**: per-run temp cwd holds `.gemini/settings.json`, `skills/`,
  `GEMINI.md`; the user-level `~/.gemini` is untouched.
- **Secret-rotation stack**: appends a `random_id` suffix to project-global GCP
  names (`sa-<ns>-<rand>`, `db-credentials-<ns>-<rand>`), so concurrent runs can
  share a namespace. **No distinct `NAMESPACE` per run is required.**

---

## Operational runbook

### Launch

Run a wrapper with the matrix env. It syncs your working tree to the VM (unless
`SKIP_SYNC=1`), generates + uploads the runner, launches it detached, and prints
a `RESUME_STAMP`. To launch **both arms truly in parallel**, sync once then start
each wrapper with `SKIP_SYNC=1` (staggered by a couple seconds so their
second-resolution `STAMP`s differ).

### Monitor (without blocking the run)

The run is detached; polling is read-only. Useful checks against the remote
`~/matrix-runs/<stamp>/<rid>/run.log`:

```bash
# progress
ssh <bastion> 'ls ~/matrix-runs/<stamp>/*/status 2>/dev/null | wc -l'
# auth failures during the agent phase
grep -icE 'No API key|ProviderAuthError|invalid_api_key' run.log
# MCP / tool usage
grep -oiE 'mcp_[a-z0-9_-]+|run_shell_command|activate_skill' run.log | sort | uniq -c
# deepeval outcome
grep -c 'Pass Rate: 100.0%' run.log    # passed checks
```

⚠️ **Grep false positives.** Naive `grep -E '401|quota'` matches terraform output
like `92401222` and `cpu_cfs_quota`. Anchor patterns (`invalid_api_key`,
`ProviderAuthError`, `^OK$`) instead of bare numbers.

### Verify isolation

Each combo should have a **distinct** cluster, node SA, secret-rotation SA, and
secret. Cross-check the `c<hash>-eval` cluster names + `gke-nodes-<hash>` SAs in
the logs are unique per combo.

### Teardown checklist

Each combo tears down its own cluster. After a run (especially a *failed* one),
confirm nothing leaked — the node SAs are the easy-to-miss part:

```bash
gcloud container clusters list --project <proj>
gcloud iam service-accounts list --project <proj> | grep -E 'gke-nodes-|sa-secret-rotation-'
gcloud secrets list --project <proj> | grep db-credentials
```

---

## Failure modes & fixes (the hard-won table)

| Symptom | Root cause | Fix |
|---|---|---|
| Detached runner never starts; empty `<stamp>.out` | `nohup ... > ~/matrix-runs/<stamp>.out` redirect target dir didn't exist | `mkdir -p` the output dir **before** the redirect (done in `_matrix_lib.sh`) |
| Two parallel matrices clobber each other's runner | shared `/tmp/matrix-runner.sh` | per-stamp runner path `/tmp/matrix-runner-<stamp>.sh` (done) |
| `gemini subprocess error: ... exit code -1` | **timeout**, not a crash — `core.subprocess.run` returns `-1` on `TimeoutExpired` | find what's hanging (usually MCP approval); raise `AGENT_TIMEOUT_SEC` only after |
| gemini exits -1 immediately, prints help | argv had literal `-e=""` (quotes reach parser; argv bypasses shell) | use `--extensions=` long form |
| gemini run hangs to timeout with MCP configured | no approval mode → MCP tool calls block on confirmation | `--approval-mode yolo` |
| gemini `mcp list` shows server `Disabled`; model writes its own MCP client | untrusted per-run cwd suppresses MCP; `--skip-trust` doesn't lift it | user-level `~/.gemini/settings.json` `security.folderTrust.enabled=false` |
| oc `google-vertex` → `401 Incorrect API key` (sent to platform.openai.com) | provider config lacks `"api":"google-vertex"` → OpenAI transport | add `api` + `baseUrl` (or `configure-oc.sh --vertex`) |
| oc `No API key found for provider "google-vertex"` under parallel runs | marker only in global sqlite store; isolated `OPENCLAW_STATE_DIR` can't see it | export `GOOGLE_CLOUD_API_KEY=gcp-vertex-credentials` (portable; `BENCH_VERTEX` does this) |
| Vertex `404 Publisher model ... not found` | regional endpoint, or non-`-preview` model id | `GOOGLE_CLOUD_LOCATION=global` + `GCP_VERTEX_LOCATION=global`; use `gemini-3.1-pro-preview` |
| Judge silently fails / 404 on Vertex | legacy judge defaults to `us-central1`; `JUDGE_MODEL` default `gemini-3.1-pro` invalid on Vertex | set `GCP_VERTEX_LOCATION=global` and `JUDGE_MODEL=gemini-3.1-pro-preview` |
| Standalone test sees stale code (`-e=""` after it was fixed) | bastion venv has an **installed** `devops_bench`; `python3 /tmp/x.py` imports it, not the synced source | run with `PYTHONPATH=$HOME/devops-bench`, or `python -m devops_bench` from the source dir (what the matrix does) |
| Cluster re-create `409 already exists` (node SA) | `gke-nodes-<cluster>` SA is **not** random-suffixed; a failed teardown orphans it | delete orphan `gke-nodes-*` SAs; durable fix tracked (see below) |
| `workloads` helm `context deadline exceeded` (~300s), empty results | each run makes a **fresh** GSA → cold Workload-Identity binding takes minutes to propagate, so ESO can't sync the secret in time | raised helm `timeout` to 900s in `secret-rotation/k8s_config/main.tf` (ESO retries every 10s, so it syncs once WI is live); durable fix = stable/static GSA |
| tofu `Value for undeclared variable "namespace"` | `NAMESPACE` env is passed as a tofu `-var namespace=` to **every** stack, but only some declare it (`secret-rotation` does; `prebuilt/minimum` does not) | only set `NAMESPACE` for tasks whose stack declares it; unset it for `prebuilt/minimum` tasks (e.g. `create-deployment`) |
| SSH `exit 255` mid-run | transient gcpnode/cert blip | retry; the detached run is unaffected, re-attach with `RESUME_STAMP` |

### SSH / environment gotchas

- Bastion over gcpnode: host
  `nic0.<vm>.<zone>.c.<proj>.internal.gcpnode.com`, user `<you>_google_com`; set
  `BASTION_USE_GCPNODE=1`. Don't force SSH `ControlMaster`/`ControlPath=none`
  (breaks the user's ssh config → yubikey re-taps).
- Always pass keepalive (`-o ServerAliveInterval` / `-o ServerAliveCountMax` /
  `-o ConnectTimeout`) so a hung relay fails fast; the matrix scripts already do.
- Run long jobs under `nohup` (the matrix does). macOS has **no `timeout`**
  command — rely on SSH keepalive caps.
- Laptop `gcloud` crashing with `ModuleNotFoundError: No module named 'OpenSSL'`:
  a corp enterprise-cert config (`/etc/certificate_config.json`) makes gcloud need
  `pyOpenSSL`, which its Python lacks. Prefix gcloud with
  `CLOUDSDK_CONTEXT_AWARE_USE_CLIENT_CERTIFICATE=false` to bypass the client-cert path.

---

## Model behavior (interpreting scores)

Scores reflect **model capability on the task**, not infra — once a run reaches
the agent phase with working auth + tools, a low score is the model, not the
harness. Observed on the secret-rotation task via Vertex:

| Arm / agent | Model | Result |
|---|---|---|
| Legacy oc | gemini-3.1-pro-preview | 7/9 checks |
| Legacy oc | gemini-3-flash-preview | 0/9 (ran full trajectory) |
| Refactored gcli | gemini-3.5-flash (bare) | 2/8 |
| Refactored gcli+mcp+skills | gemini-3.5-flash | **8/9** (37-step trajectory, ~20 gke-mcp calls + skill activation) |

`gemini-3.5-flash` can loop/flail when driving MCP; `gemini-3.1-pro-preview` is
more reliable. The strongest result came from the refactored agent **with**
MCP + skills — MCP tool access materially helped.

---

## Results layout

```
results/<RESULTS_DIR-or-matrix>/<stamp>/<rid>/
  status                                   # "exit=<rc>"
  run.log                                  # full combo stdout (tofu + agent + judge)
  run_<ts>_<rid>/results.json              # refactored: nested
  results.json                             # legacy: copied in from results/run_<ts>_<rid>
```

`results.json` is a **list** of per-criterion objects (`{name, score, success,
reason, ...}`). The per-check pass/fail also appears as DeepEval
`Pass Rate: 100.0% / 0.0%` lines in `run.log`.

---

## Known limitations & follow-ups

- **Shared OpenTofu working dir**: per-run isolation covers `TF_DATA_DIR` + state,
  but both arms run `tofu` in the same `tf/prebuilt/<stack>` dir, so
  `.terraform.lock.hcl` is shared (benign in practice; a per-run copy of the stack
  dir is the robust fix).
- **Node-SA orphaning**: `tf/modules/gke` node SA name `gke-nodes-<cluster>` is
  deterministic, **not** random-suffixed, so a failed teardown orphans it and a
  re-run hits `409 already exists`. Durable fix (random suffix /
  `create_ignore_already_exists` / always clean `gke-nodes-*`) is still open.

---

## Reproducing a bastion from scratch

```bash
# 1. provision + ship code (see docs/bastion.md §1–3), then on the VM:
scripts/bastion/vm-setup.sh           # installs gemini CLI; sets ~/.gemini folder-trust=false
# 2. for Vertex/ADC legacy runs, register the oc google-vertex provider:
scripts/bastion/configure-oc.sh --vertex [--mcp --skills | --no-mcp --no-skills]
# 3. ensure the VM SA has container.admin + secretmanager.admin + aiplatform.user
```

After that, the TL;DR commands at the top work with no manual config.
