# Eval-harness bastion (GCE)

A static Google Compute Engine VM that serves as the **execution environment for
the eval harness**. Use it when you can't run the agent CLI (openclaw / `oc`)
locally: you SSH into the bastion over IAP and run the whole harness there.

The harness drives `oc` as a **local subprocess** (the openclaw agent on the
refactor branch is local-only — the SSH transport was removed), so everything —
infra provisioning (tofu), the agent run (`oc`), and the judge — happens on the
VM.

The bastion is intentionally **generic and reusable**; secret-rotation is just
the first eval it runs.

## Architecture

```
You ──IAP SSH──> bastion VM "bench-bastion" (us-central1-a)
                   runs as openclaw-vm-sa  (ADC via the metadata server)
                   │
                   ├─ devops-bench CLI (the harness)
                   │    ├─ tofu apply  ->  GKE cluster + Secret Manager + ESO + app
                   │    ├─ oc agent --local   (openclaw performs the rotation)
                   │    │     └─ kubectl + gcloud + Secret Manager  (as the VM SA)
                   │    └─ judge (Gemini/Anthropic via API key)
                   └─ openclaw API key for the agent model
   (code pushed from your laptop via gcloud compute scp over IAP, subset only)
```

### Why this service account
The bastion runs as `openclaw-vm-sa@<project>.iam.gserviceaccount.com`. That is
**not arbitrary**: the secret-rotation tofu stack already references that exact
email — `tf/prebuilt/secret-rotation/cluster/main.tf` grants it
`roles/secretmanager.admin`, and `tf/modules/gke` grants the cluster's
`agent_service_account` `roles/container.admin` and opens an IAP-SSH firewall.
Nothing in those stacks *creates* the SA or a VM — this bastion fills that gap.
The SA id is the `sa_account_id` variable, so other harnesses can use a different
one.

The bastion SA also gets broad **provisioning** rights (`roles/editor` +
`roles/resourcemanager.projectIamAdmin` + `roles/iam.serviceAccountAdmin`) so the
harness can run the task's tofu (which creates GKE, secrets, service accounts, and
sets project/SA IAM bindings) *as this SA*. Tighten via `sa_roles` if needed; the
lazy alternative is `["roles/owner"]`.

## Files

| Path | Purpose |
|------|---------|
| `tf/modules/bastion/` | Reusable module: SA + IAM, the VM, the IAP-SSH firewall, `startup.sh`. |
| `tf/prebuilt/bastion/` | Concrete stack you `tofu apply`. |
| `scripts/bastion/sync-to-bastion.sh` | Push your local working tree (subset) to the VM. |
| `scripts/bastion/vm-setup.sh` | One-time per-user setup on the VM (venv + install + env). |

## 1. Provision the bastion

```bash
cd tf/prebuilt/bastion
tofu init
tofu apply -var project_id=<your-project>
```

Useful outputs: `iap_ssh_command`, `sa_email`. The VM's `startup.sh` installs the
toolchain on first boot (OpenTofu, gcloud + gke-gcloud-auth-plugin, kubectl,
Node 22, and `openclaw`, symlinked as `oc`); it touches
`/var/lib/bench-bastion-ready` when finished and logs to
`/var/log/bench-bastion-startup.log`.

Variables you may want: `name` (VM name, default `bench-bastion`), `zone`
(default `us-central1-a`), `machine_type` (default `e2-standard-4`),
`sa_account_id` (default `openclaw-vm-sa`), `assign_external_ip` (default `true`).

## 2. SSH in (over IAP)

```bash
gcloud compute ssh bench-bastion --zone us-central1-a --project <proj> --tunnel-through-iap
```

(the `iap_ssh_command` output prints this exact line). SSH ingress is restricted
to Google's IAP range (`35.235.240.0/20`); the external IP, if any, is for egress
only.

Sanity-check the toolchain:

```bash
cat /var/lib/bench-bastion-ready   # exists once startup finished
oc --version && tofu version && gcloud --version | head -1
kubectl version --client | head -1 && python3 --version && node --version
```

## 3. Ship your code + set up

From your laptop (reflects local, unpushed changes — only the needed subset is
sent):

```bash
scripts/bastion/sync-to-bastion.sh        # tars + scps over IAP into ~/devops-bench
```

By default this uses `gcloud compute ssh/scp --tunnel-through-iap`. In special
environments (e.g. Google corp hosts reachable directly at
`nic0.<vm>.<zone>.c.<project>.internal.gcpnode.com`) you can override the
transport without changing the default:

```bash
# Auto-build the gcpnode host from VM/zone/project, user defaults to <you>_google_com:
BASTION_USE_GCPNODE=1 scripts/bastion/sync-to-bastion.sh
# Or point at an explicit host / user:
BASTION_SSH_HOST=nic0.bench-bastion.us-central1-a.c.my-proj.internal.gcpnode.com \
  BASTION_SSH_USER=me_google_com scripts/bastion/sync-to-bastion.sh
```

Then on the VM, once:

```bash
~/devops-bench/scripts/bastion/vm-setup.sh   # venv + pip install .[all] + ~/bench.env
openclaw onboard                              # persist the agent model API key
```

`vm-setup.sh` writes a `~/bench.env` template. Fill in your project and judge key,
then `source ~/bench.env`.

> The harness does **not** pass an API key to `oc`. openclaw holds the agent
> model's key itself — set it with `openclaw onboard` (or a provider env var your
> openclaw build reads, e.g. `GEMINI_API_KEY`).

## 4. Run the secret-rotation eval

```bash
cd ~/devops-bench && source .venv/bin/activate
source ~/bench.env
devops-bench complextasks/secret-rotation/task.yaml
```

The harness provisions the GKE cluster + Secret Manager + External Secrets
Operator + the `db-secret-viewer` app, runs `oc agent --local` to rotate the
secret, judges the result, then tears the infra down.

Iterating: keep the cluster between runs with `export BENCH_NO_TEARDOWN=true` and
bump `NAMESPACE` per run; or skip provisioning entirely with `--no-infra`.

## Cost & security notes

- **Static VM** — it bills while it exists. `tofu destroy` in `tf/prebuilt/bastion`
  when you're done, or stop the instance between sessions.
- **SSH is IAP-only.** The optional external IP is egress-only; remove it
  (`-var assign_external_ip=false`) if your VPC has Cloud NAT.
- **Broad SA.** `openclaw-vm-sa` holds near-project-admin rights so it can
  provision eval infra. Keep it in a non-production / sandbox project. The agent's
  model key lives in openclaw's config on the VM (per your chosen API-key auth);
  promoting it to Secret Manager is a tracked follow-up.

## Parallel comparison runs (legacy vs refactored)

Both pipeline arms can run **concurrently on the bastion**, each provisioning its
own cluster, via the per-run isolation (`--parallel` / `BENCH_PARALLEL=true`).
Each run gets its own `KUBECONFIG`, `CLOUDSDK_CONFIG`, `TF_DATA_DIR`, OpenTofu
state, and a run-unique cluster name; results go to per-run dirs.

Launch the two arms with **distinct `RUN_ID`** (the `NAMESPACE` can be the same —
the stack random-suffixes its project-global GCP resources; see below). Same key
for the agent model + judge:

```bash
source ~/secrets.env   # GEMINI_API_KEY (mirrored to GOOGLE/AGENT/JUDGE_API_KEY)
# One-time per mode: wire the LEGACY arm's global oc config (MCP + skills + key).
scripts/bastion/configure-oc.sh --mcp --skills

common=( GCP_PROJECT_ID=<proj> GKE_CLUSTER_NAME=secret-rot GCP_LOCATION=us-central1-a
         AGENT_PROVIDER=google AGENT_MODEL=gemini-3.1-pro-preview
         JUDGE_PROVIDER=google JUDGE_MODEL=gemini-3.1-pro-preview
         BENCH_PARALLEL=true BENCH_NO_TEARDOWN=true BENCH_USE_MCP=true
         AGENT_TARGET=oc OPENCLAW_BIN=oc OPENCLAW_AGENT=main )

# Arm A — legacy (MCP+skills from the GLOBAL ~/.openclaw config set above)
env "${common[@]}" RUN_ID=legacy-$(date +%s) \
    BENCH_AGENT_TYPE=cli OPENCLAW_LOCAL=true \
    python3 pkg/evaluator/evaluate.py complextasks/secret-rotation/task.yaml &

# Arm B — refactored (MCP+skills via env -> isolated openclaw.json)
env "${common[@]}" RUN_ID=refac-$(date +%s) \
    BENCH_AGENT_TYPE=openclaw AGENT_MCP_SERVER="$HOME/gke-mcp" AGENT_SKILLS_PATHS="$HOME/oc-skills" \
    python3 -m devops_bench --parallel complextasks/secret-rotation/task.yaml \
      --project <proj> --cluster secret-rot --results-root results/refac &
wait
# then: python3 scripts/compare_results.py --legacy <A>/results.json --refactor <B>/results.json
```

### Matrix runs (Task × Model × AgentConfig)

`scripts/bastion/run_matrix.sh` runs this from your **workstation**: given the
bastion connection env, it expands a `MATRIX_TASKS × MATRIX_MODELS ×
MATRIX_AGENT_CONFIGS` matrix, launches each combo as an isolated `--parallel`
run on the bastion (bounded by `MAX_PARALLEL`, each combo its own cluster),
and copies every run's `results.json` + logs back to `RESULTS_DIR`. Agent-config
presets are `<oc|gcli>[+mcp][+skills]`. The three canonical CUJs:

```bash
# 1) one task, many models, one agent config
MATRIX_TASKS="complextasks/secret-rotation/task.yaml" \
MATRIX_MODELS="gemini-3.1-pro gemini-3.5-flash" \
MATRIX_AGENT_CONFIGS="gcli+mcp+skills" \
GCP_PROJECT_ID=<proj> scripts/bastion/run_matrix.sh

# 2) one task, one model, many agent configs
MATRIX_AGENT_CONFIGS="oc oc+mcp+skills gcli gcli+mcp+skills" ... run_matrix.sh

# 3) all tasks, one model, one agent config
MATRIX_TASKS=ALL MATRIX_MODELS="gemini-3.1-pro" MATRIX_AGENT_CONFIGS="oc+mcp+skills" ... run_matrix.sh
```

`DRY_RUN=1` prints the expanded matrix + per-combo env without provisioning.
It drives the refactored arm (per-run MCP/skills via env), so combos are fully
independent. Both `oc` and `gemini` CLIs are installed by `vm-setup.sh`.

For the **legacy** arm use `scripts/bastion/run_matrix_legacy.sh` — same harness,
but **Task × Model only** (no AgentConfig dimension: the legacy arm reads
MCP/skills from the global `~/.openclaw`, so set them once with
`configure-oc.sh` beforehand). It's a thin throwaway companion (shared logic
lives in `_matrix_lib.sh`); delete it when the legacy arm is retired.

#### Surviving SSH drops / resuming

The matrix runner is launched **detached** (`nohup`) on the bastion, so the runs
themselves complete regardless of your SSH session. The local script only polls
and copies results back, and it's hardened against drops:

- SSH **keepalive** (`ServerAliveInterval`) on every call so brief blips don't
  drop the connection.
- The poll loop treats a failed check as "not finished yet" and retries — a
  transient drop never aborts it.
- The final pull **retries** a few times before giving up (and tells you the
  results remain on the bastion if it still can't copy them).

If the local process itself dies (terminal closed, laptop sleeps), the runs keep
going on the bastion. Re-attach with the stamp the original invocation printed —
this skips launching and just re-polls + pulls:

```bash
RESUME_STAMP=20260623_213512 ./scripts/bastion/run_matrix.sh        # or run_matrix_legacy.sh
```

### Parallel agent support

| Agent | Refactored arm | Legacy arm |
|-------|----------------|------------|
| OpenClaw (`oc`)  | ✅ parallel-safe | ✅ parallel-safe |
| Gemini CLI (`gemini`) | ✅ parallel-safe | ❌ **not** parallel-safe |

The **refactored** arm runs the Gemini CLI in a per-run temporary working
directory (its own `.gemini/settings.json` + skills) and reconstructs the
trajectory from the process **stdout** (`--output-format stream-json`), so it
never touches shared user-level state — concurrent gemini runs are independent.

The **legacy** Gemini runner instead reads the trajectory back from the shared
`~/.gemini/tmp/.../chats` session directory and matches by a short session id,
which can pick the wrong run's trajectory under concurrency. Legacy parallel
support is therefore **OpenClaw-only by design**, which is why
`run_matrix_legacy.sh` is hard-wired to `AGENT_TARGET=oc`. Run legacy gemini only
one-at-a-time; for parallel gemini use the refactored matrix
(`MATRIX_AGENT_CONFIGS="gcli..."`).

### MCP + skills for OpenClaw

- **Refactored arm** reads `AGENT_MCP_SERVER` (the `gke-mcp` binary) and
  `AGENT_SKILLS_PATHS` (a tree of `<name>/SKILL.md` files), writes an *isolated*
  `openclaw.json`, and materializes skills under its per-run state dir.
- **Legacy arm** ignores those vars — it only uses the **global** `~/.openclaw`
  config. Wire it (and the model key) idempotently with
  `scripts/bastion/configure-oc.sh --mcp --skills`; run `--no-mcp --no-skills`
  (or just don't run it) for a clean "no capabilities" legacy run. The script
  reshapes the repo's `skills/*.md` into the `<name>/SKILL.md` layout oc expects.
- The configured agent profile is **`main`** on current openclaw builds; set
  `OPENCLAW_AGENT=main` (both arms default to it).

### Identity model: BYO credentials

The agent runs as the operator-provided **bastion VM SA** (ambient ADC via the
metadata server), assumed to already hold the broad infra permissions a task
needs (e.g. Secret Manager + GKE admin). Infra stacks therefore grant the runner
**nothing** — there is intentionally no per-run runner SA and no project IAM
binding to a shared SA. (A least-privilege per-run runner identity is a tracked
follow-up.) Ensure the bastion SA is broad enough once, out of band, e.g.:

```bash
gcloud projects add-iam-policy-binding <proj> \
  --member="serviceAccount:openclaw-vm-sa@<proj>.iam.gserviceaccount.com" \
  --role="roles/container.admin"   # + roles/secretmanager.admin (or roles/editor/owner)
```

### Per-task isolation: name collisions handled in-stack

The secret-rotation stack derives project-global GCP names from `namespace`
(`sa-${namespace}`, `db-credentials-${namespace}`). To let concurrent runs share
the same namespace, the stack appends a **`random_id` suffix** to those names
(`tf/prebuilt/secret-rotation/cluster/main.tf`) and threads the suffixed secret
id to the ExternalSecret. So **no distinct `NAMESPACE` per run is required** — the
run-unique cluster name + the random suffix keep everything separate. (The k8s
namespace itself is cluster-scoped, so two clusters can reuse the same one.)

Because no run grants a shared project-level IAM binding anymore, the earlier
**teardown hazard is resolved** — one run's `tofu destroy` no longer revokes a
permission another run needs.

### Known limitation: shared OpenTofu working directory

Per-run isolation covers `TF_DATA_DIR` and the state file (written *beside*
`TF_DATA_DIR`, never at the reserved `<TF_DATA_DIR>/terraform.tfstate`), but both
arms still run `tofu` in the **same stack working directory**
(`tf/prebuilt/<stack>`), so `.terraform.lock.hcl` is shared. It is benign in
practice (identical provider locks), but the fully robust fix is a **per-run copy
of the stack directory**; tracked as a follow-up.
