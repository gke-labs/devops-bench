# Eval-harness bastion (GCE)

A static Google Compute Engine VM that serves as the **execution environment for
the eval harness**. Use it when you can't run the agent CLI (openclaw / `oc`)
locally: you SSH into the bastion over IAP and run the whole harness there.

The harness drives `oc` as a **local subprocess** (the openclaw agent is
local-only), so everything — infra provisioning (tofu), the agent run (`oc`), and
the judge — happens on the VM.

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
sets project/SA IAM bindings) *as this SA*. These rights are owner-equivalent, so
**run this only in a non-production / sandbox project**. Scope them down for your
task with the `sa_roles` variable, granting only the roles the task's tofu needs.

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

> Agent model key: when `AGENT_API_KEY` is unset, the harness passes no key to
> `oc` and openclaw uses the key from `openclaw onboard`. When `AGENT_API_KEY` is
> set, the harness threads it into the provider env var (`GEMINI_API_KEY` /
> `ANTHROPIC_API_KEY` / …) for the run. Either way, provide the key once — via
> `openclaw onboard` or that provider env var.

## 4. Run the secret-rotation eval

```bash
cd ~/devops-bench && source .venv/bin/activate
source ~/bench.env
devops-bench complextasks/secret-rotation/task.yaml
```

The harness provisions the GKE cluster + Secret Manager + External Secrets
Operator + the `db-secret-viewer` app, runs `oc agent --local` to rotate the
secret, judges the result, then tears the infra down.

Iterating: keep the cluster between runs with `export BENCH_NO_TEARDOWN=true`,
bumping `NAMESPACE` per run so each run's resources don't collide in the shared
cluster; or skip provisioning entirely with `--no-infra`. This per-run `NAMESPACE`
bump applies only when reusing one cluster — parallel runs on separate clusters
don't need it (see [`docs/parallel-evals.md`](./parallel-evals.md)).

## Cost & security notes

- **Static VM** — it bills while it exists. `tofu destroy` in `tf/prebuilt/bastion`
  when you're done, or stop the instance between sessions.
- **SSH is IAP-only.** The optional external IP is egress-only; remove it
  (`-var assign_external_ip=false`) if your VPC has Cloud NAT.
- **Broad SA.** `openclaw-vm-sa` holds near-project-admin rights so it can
  provision eval infra. Keep it in a non-production / sandbox project. The agent's
  model key lives in openclaw's config on the VM (per your chosen API-key auth);
  promoting it to Secret Manager is a tracked follow-up.

## Parallel & matrix runs (legacy vs refactored)

Both pipeline arms can run **concurrently on the bastion**, each provisioning its
own cluster, via per-run isolation (`--parallel` / `BENCH_PARALLEL=true`): each run
gets its own `KUBECONFIG`, `CLOUDSDK_CONFIG`, `TF_DATA_DIR`, OpenTofu state, and a
run-unique cluster name. The secret-rotation stack also random-suffixes its
project-global GCP names, so parallel runs may share a `NAMESPACE` — the per-run
bump above is only needed when several runs reuse one cluster.

> **[`docs/parallel-evals.md`](./parallel-evals.md) is the canonical parallel-eval
> runbook** — Vertex/ADC mode, gemini-CLI MCP setup, `run_matrix.sh` /
> `run_matrix_legacy.sh` matrix orchestration, MCP + skills wiring, the
> parallel-safety matrix, and a failure-mode → fix table. The rest of this section
> is just the bastion quickstart; use that doc for everything else.

Launch the two arms manually with **distinct `RUN_ID`** and the same agent/judge key:

```bash
source ~/secrets.env   # GEMINI_API_KEY (mirrored to GOOGLE/AGENT/JUDGE_API_KEY)
scripts/bastion/configure-oc.sh --mcp --skills   # one-time: wire the LEGACY arm's global oc config

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

For the full matrix (Task × Model × AgentConfig) use `scripts/bastion/run_matrix.sh`
(refactored) or `scripts/bastion/run_matrix_legacy.sh` (legacy, oc-only) — local by
default, `BENCH_REMOTE=1` to sync + run on the bastion. See
`docs/parallel-evals.md` for the matrix CUJs, the parallel-safety rules (legacy +
gemini CLI is not parallel-safe), resume-after-drop, and Vertex setup.

**kind-based tasks (run on the bastion host, not GKE).** A few tasks need
node-level access that GKE's managed control plane doesn't allow, so they run on
real **kind** clusters on the bastion:

- `complextasks/cp-recovery` — control-plane surgery (restore a corrupted etcd
  member to quorum); impossible on GKE's node-inaccessible control plane.
- `complextasks/opa-remediation` — Kyverno policy remediation on a kind cluster.
- `complextasks/migration-and-upgrade` — kind-based cluster upgrade; the agent
  also spins a throwaway target-version kind cluster to validate manifests.
- `tasks/generic/debug-crashloop` — investigation task on a small kind cluster.

All are parallel-safe (kind cluster name derives from the run-token-prefixed
cluster name → per-run-unique Docker containers/nodes; per-run `$KUBECONFIG`; and
their GitOps repos are per-run paths). **Caveat:** these clusters all share one
bastion host, so several concurrent kind tasks (cp-recovery is 4-node; migration
runs two clusters) sum on the host's CPU/RAM/disk — keep `MAX_PARALLEL` modest.

## Known issues (appendix)

Record issues found while using the bastion here, so they live in one place.

| Issue | Impact | Workaround / status |
|-------|--------|---------------------|
| Bastion SA is owner-equivalent (`editor` + `projectIamAdmin` + `serviceAccountAdmin`). | Anything running as the SA can grant itself any role and impersonate any SA. | Sandbox/non-prod projects only; scope down with `sa_roles`. Follow-up: ship a least-privilege default. |
| Agent model key stored in openclaw's on-VM config. | Key sits in plaintext on the VM. | Keep the VM IAP-only. Follow-up: promote to Secret Manager. |
| Static VM bills continuously. | Cost accrues while the VM exists. | `tofu destroy` (or stop the instance) when idle. |
| Shared OpenTofu working directory. | Per-run isolation covers `TF_DATA_DIR` + state, but both arms ran `tofu` in the same `tf/prebuilt/<stack>` dir, so `.terraform.lock.hcl` was shared. | **Resolved** — under `--parallel` both arms now copy the whole `tf/` tree into the per-run scratch dir and run `tofu` there (`devops_bench/deployers/tofu.py`, `deployers/tf/tf_deployer.py`); single runs unchanged. |
| Shared VM-SA project IAM bindings clobber under concurrent GKE tasks. | A per-task GKE stack that grants a project role (e.g. `roles/container.admin`) to the shared VM SA via `google_project_iam_member` "owns" that binding in its own TF state; the first `tofu destroy` strips it while sibling runs still need it → mid-run `container.*` 403. | Don't manage shared-SA project bindings from per-task stacks; grant out-of-band (or use a role the stacks don't manage). Affects any concurrent GKE-task batch. |
| Host capacity sums across concurrent runs (kind tasks). | Per-task READMEs size disk/inotify/clusters for **one** run; N concurrent kind runs use ~N×, and tasks where the agent spins up extra clusters use more (those get agent-chosen, **un-prefixed** names → docker-daemon collision risk). | Size the bastion for the concurrent batch, not a single run; avoid agent-side cluster creation in large matrices. See `docs/parallel-evals.md` for the per-run isolation gaps. |
| Bastion toolchain gaps for kind tasks: no Docker, low `inotify`, no `fortio`. | kind tasks fail at provision (`docker: not found`; multi-node `kubeadm join` fails on default `inotify`), and `optimize-scale` chaos `generate_load` silently no-ops without `fortio`. | One-time bastion setup: install `docker.io` (+ runner socket access), `sudo sysctl fs.inotify.max_user_instances=1280 max_user_watches=1048576` (persist in `/etc/sysctl.d/`), and install `fortio` to `~/bin` (`vm-setup.sh`). |
| kind teardown leaves orphaned node containers. | A kind task's `tofu destroy` can leave `<hash>-eval-*` Docker containers running (not tracked by `kind get clusters`), accreting host load/disk across runs. | After a kind run, sweep: `docker rm -f $(docker ps -aq --filter name=<hash>-eval)`; periodically `docker container prune` on an idle bastion. |
