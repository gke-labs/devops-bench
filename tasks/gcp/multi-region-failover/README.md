# Multi-Region Disaster-Recovery Failover Task

This task evaluates an agent's ability to run a **regional outage incident** end-to-end on real
GCP infrastructure: detect that a user-facing service is failing in its primary region, confirm
the standby region is safe to cut over to (capacity **and** data consistency), redirect global
traffic, scale the standby, reconcile configuration drift from GitOps, validate the recovery, and
write a post-mortem.

Unlike the other tasks in this suite, this one genuinely needs managed-cloud features, so it runs
on **GKE** (not kind): a global external HTTP load balancer with a URL map, **two** regional GKE
clusters, and a **cross-region Cloud SQL** primary/replica pair.

## How it works

- **Infrastructure** (`tf/prebuilt/multi-region-failover`) is provisioned by OpenTofu when you run
  the evaluator. It creates:
  - two zonal GKE clusters — `<name>-east` (**primary**, `us-east1-b`) and `<name>-west`
    (**standby**, `us-west1-b`, deliberately small);
  - reserved external IPs + a **global external HTTP LB**: two `INTERNET_IP_PORT` NEGs → two
    backend services (`be-east`/`be-west`) → a **URL map whose default route is pinned to east**
    → target proxy → global forwarding rule on a global anycast IP;
  - **Cloud SQL** MySQL **primary** in `us-east1` + a **cross-region read replica** in `us-west1`
    (the datastore whose replication health the agent checks before failover). The instance names
    are surfaced in `app-config` (`DB_PRIMARY_INSTANCE`/`DB_REPLICA_INSTANCE`) so the app's
    dependency on a cross-region DB is discoverable from the desired state.
- **The outage is injected outside the cluster.** During `tofu apply`, `scripts/setup.sh` deploys
  the `storefront` app (nginx `frontend` → `backend`) to both regions, then **deletes the east
  node pool** — a regional capacity loss. Because the URL map still defaults to the east backend,
  the global endpoint returns **5xx**. There is no automatic cross-backend failover, and — since
  there is no node pool to scale back — the outage **cannot be repaired in place** by re-applying
  manifests; the only path to restore users is to fail traffic over to the healthy **west** region.
  The cluster control plane stays up, so `kubectl`/credentials to east still work for diagnosis.
  Nothing in either cluster describes the outage or the fix.
- **Config drift is pre-seeded.** West is deployed **without** the `app-config` ConfigMap and
  `app-secret` Secret that east has (they are marked `optional`, so west still runs). Post-failover
  validation is expected to surface this drift; the agent reconciles it from the GitOps repo.
- **GitOps source of truth** is a per-run local **bare git repo** at `~/app-repo-<cluster_name>.git`
  (run-unique so concurrent runs don't collide; the prompt uses `{{GKE_CLUSTER_NAME}}`), seeded with
  the app's desired state (including `app-config`/`app-secret`).
- Both clusters' credentials are merged into the kubeconfig as stable contexts **`east`** and
  **`west`** (the harness only credentials the primary; the setup script adds the standby).

## IAM Prerequisites (GKE)

The agent/provisioner runs as the OpenClaw VM service account
(`openclaw-vm-sa@<PROJECT_ID>.iam.gserviceaccount.com`). It needs broad project roles to create
GKE clusters, the global LB, Cloud SQL, and the supporting IAM/service-accounts.

> [!IMPORTANT]
> These grants must be run by a **project admin in Cloud Shell** — the VM SA **cannot grant roles
> to itself**. Run once before the first eval.

```bash
PROJECT_ID="jessieliu-gke-dev"                       # <-- your project
VM_SA="openclaw-vm-sa@${PROJECT_ID}.iam.gserviceaccount.com"

# Enable the required APIs
gcloud services enable \
  container.googleapis.com compute.googleapis.com sqladmin.googleapis.com iam.googleapis.com \
  --project "$PROJECT_ID"

# Grant the VM SA the roles the stack needs
for role in \
  roles/container.admin \
  roles/compute.admin \
  roles/cloudsql.admin \
  roles/iam.serviceAccountAdmin \
  roles/iam.serviceAccountUser \
  roles/resourcemanager.projectIamAdmin \
  roles/serviceusage.serviceUsageAdmin ; do
  gcloud projects add-iam-policy-binding "$PROJECT_ID" \
    --member="serviceAccount:${VM_SA}" --role="$role" --condition=None
done
```

| Role | Why it's needed |
| --- | --- |
| `roles/container.admin` | Create/manage the two GKE clusters; resize node pools; `kubectl` access. |
| `roles/compute.admin` | Reserved IPs, global address, internet NEGs, backend services, URL map, proxy, forwarding rule, node-pool resize. |
| `roles/cloudsql.admin` | Create/manage the Cloud SQL primary **and** the cross-region read replica. |
| `roles/iam.serviceAccountAdmin` | The GKE module creates per-cluster node service accounts (`gke-nodes-*`). |
| `roles/iam.serviceAccountUser` | Attach those node SAs to the node pools (actAs). |
| `roles/resourcemanager.projectIamAdmin` | The module binds project roles to the node SAs and the agent SA. |
| `roles/serviceusage.serviceUsageAdmin` | Enable/verify APIs from within the provisioner. |

> [!WARNING]
> **`container.admin` teardown-clobber — grant `roles/owner` on a dev project.** The GKE module
> manages the agent SA's project `roles/container.admin` binding, so **every** `tofu destroy`
> removes it (it's the same IAM entry the grant loop adds). Worse, destroy can remove it *before*
> the cluster/node-pool deletions finish, leaving them stuck on `container.operations.get` 403s and
> requiring a re-grant + re-destroy. The clean fix on a dev project is to grant the VM SA a durable
> role the module never touches — `roles/owner` supersets all the roles above, so you can skip the
> grant loop entirely and no teardown will ever clobber it:
> ```bash
> gcloud projects add-iam-policy-binding "$PROJECT_ID" \
>   --member="serviceAccount:${VM_SA}" --role=roles/owner --condition=None
> ```

## Setup & Running the Benchmark

Run everything on the OpenClaw GCE VM (the agent runs locally via `OPENCLAW_LOCAL=true`; the GKE
clusters are remote and reached with `gcloud`/`kubectl`).

### Host requirements

- `gcloud` authenticated as / running on the VM SA, `kubectl`, OpenTofu (`tofu`), and the OpenClaw
  `oc` binary at `~/bin/oc` (override with `OPENCLAW_BIN`).
- **Python ≥ 3.10** (the `deepeval` dependency requires it).
- No Docker/kind/inotify needed (this task does not use kind).

### 1. Install prerequisites (one-time)

```bash
sudo apt-get update && sudo apt-get install -y unzip python3-venv google-cloud-cli-gke-gcloud-auth-plugin
curl -LO "https://dl.k8s.io/release/$(curl -L -s https://dl.k8s.io/release/stable.txt)/bin/linux/amd64/kubectl" && chmod +x kubectl && sudo mv kubectl /usr/local/bin/
curl -fsSL https://get.opentofu.org/install-opentofu.sh -o /tmp/it.sh && sudo bash /tmp/it.sh --install-method deb
for t in gcloud kubectl tofu; do command -v $t >/dev/null && echo "have $t" || echo "MISSING $t"; done
```

### 2. IAM bootstrap

Run the grant loop in [IAM Prerequisites](#iam-prerequisites-gke) (once, from Cloud Shell).

### 3. Python environment

```bash
cd ~/devops-bench
python3 -m venv .venv && source .venv/bin/activate
pip install --upgrade pip && pip install -r requirements.txt
```

### 4. Configure environment variables

```bash
export GKE_CLUSTER_NAME="storefront"          # base name; clusters become storefront-east / -west
export NAMESPACE="storefront"                  # MUST match the stack's namespace
export GCP_PROJECT_ID="jessieliu-gke-dev"
export GCP_LOCATION="us-east1-b"               # accepted by the harness; the stack pins its own regions

export OPENCLAW_LOCAL="true"                    # run the oc agent locally on the VM

# Agent config
export BENCH_AGENT_TYPE="cli"
export AGENT_TARGET="oc"
export AGENT_PROVIDER="google"
export AGENT_MODEL="gemini-3.1-pro-preview"
export AGENT_API_KEY="<your-gemini-key>"

# Judge config
export JUDGE_PROVIDER="google"
export JUDGE_MODEL="gemini-3.1-pro-preview"
export JUDGE_API_KEY="<your-gemini-key>"
```

> Tip: drop the `export`s into a git-ignored `env.sh` (it holds API keys) so future runs are just
> `source .venv/bin/activate && source env.sh`.

### 5. Run the evaluator

```bash
python pkg/evaluator/evaluate.py tasks/gcp/multi-region-failover/task.yaml
```

The harness provisions the infra (+ injects the outage), runs the local `oc` agent against it,
judges the result, and tears everything down. Results land in `results/run_<timestamp>/`:
- `results.json` — per-check scores + the agent's full trajectory.
- `generated_files/incident-report.md` — the post-mortem the agent wrote.

> [!CAUTION]
> **This task is slow and costly.** Provisioning two GKE clusters + a Cloud SQL primary **and**
> cross-region replica + a global LB takes **~25–40 minutes**, and these are billed resources.
> While iterating, `export BENCH_NO_TEARDOWN="true"` to reuse the stack, and **destroy it manually
> when done** so you stop paying for it:
> ```bash
> tofu -chdir=tf/prebuilt/multi-region-failover destroy -auto-approve \
>   -var project_id="$GCP_PROJECT_ID" -var cluster_name="$GKE_CLUSTER_NAME"
> ```

## Verifying the environment manually

```bash
cd tf/prebuilt/multi-region-failover
tofu init && tofu apply -auto-approve -var project_id="$GCP_PROJECT_ID" -var cluster_name=storefront
LB_IP=$(tofu output -raw lb_ip)

curl -s -o /dev/null -w '%{http_code}\n' "http://$LB_IP/"   # 5xx — primary region is down
kubectl --context east get nodes                            # no nodes (node pool deleted)
kubectl --context west get pods -n storefront               # frontend + backend Running
kubectl --context east get cm,secret -n storefront          # app-config + app-secret present
kubectl --context west get cm,secret -n storefront          # app-config + app-secret MISSING (drift)
gcloud sql instances list                                   # primary + replica, RUNNABLE
git clone "$HOME/app-repo.git" /tmp/app-repo && ls /tmp/app-repo/manifests   # desired state incl. app-config/secret

# manual solve (proves solvability):
URLMAP=$(gcloud compute url-maps list --format='value(name)' --filter="name~storefront-urlmap")
BE_WEST=$(gcloud compute backend-services list --global --format='value(name)' --filter="name~be-west")
gcloud compute url-maps set-default-service "$URLMAP" --global --default-service "$BE_WEST"
gcloud container clusters resize storefront-west --node-pool primary-node-pool --num-nodes 3 --zone us-west1-b -q
kubectl --context west apply -n storefront -f /tmp/app-repo/manifests/app-config.yaml
kubectl --context west apply -n storefront -f /tmp/app-repo/manifests/app-secret.yaml
curl -s -o /dev/null -w '%{http_code}\n' "http://$LB_IP/"   # now 200 — served from west

tofu destroy -auto-approve -var project_id="$GCP_PROJECT_ID" -var cluster_name=storefront
```

## Troubleshooting

| Symptom | Cause / Fix |
| --- | --- |
| `403 ... Permission denied` during apply | VM SA missing a role — run the IAM grant loop (Cloud Shell). |
| `container.admin` lost after a run | Teardown clobbers it — re-run the grant loop or use a durable role. |
| `instance name ... cannot be reused` (Cloud SQL) | A prior instance was deleted <1 week ago; the random suffix should avoid this — re-apply for a fresh name. |
| Global endpoint still 5xx right after failover | Global LB / URL-map changes take a few minutes to propagate — retry the `curl`. |
| `TypeError: unsupported operand type(s) for \|: …` on import | Python < 3.10 — use a 3.10+ venv. |
| `No such file or directory: 'tofu'` / `kubectl` | Missing prerequisite — install step 1. |
| `getcredentials ... gke-gcloud-auth-plugin` error | Install `google-cloud-cli-gke-gcloud-auth-plugin` (step 1). |

## Out of scope / deliberate simplifications (for reviewers)

- **Scale** is representative, not literal (2 regions, small clusters) — same spirit as cp-recovery
  scaling etcd. Clusters are **zonal** (cheaper) rather than the SOT's "regional".
- **Replication lag is kept low**, so the data-safe path is "verify-then-proceed"; the SOT's
  `lag > 500ms → soft-drain` branch is not exercised (kept deterministic).
- **No real Slack** — the post-mortem is written to `incident-report.md` only.
- **Golden signals** = global-endpoint health + error checks (no full dashboards).
- **Forcing the DR path.** The primary outage is injected by *deleting* the east node pool (not
  scaling it to 0). An earlier scale-to-0 version let agents sidestep failover by simply resizing
  the pool back; deleting it means there is nothing to resize, so failover to west is the only
  in-budget recovery. (A determined agent could still recreate a node pool, but that is a far less
  natural move than re-pointing the URL map.)

The faithful 5-step DR core is exercised: detect → verify-safe (capacity + replication) → redirect
(URL map) → scale standby → validate + reconcile config drift → post-mortem.
