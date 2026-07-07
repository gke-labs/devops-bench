# Intelligent Workload Re-balancing for GreenOps (Energy Efficiency)

This task evaluates an agent's ability to **cut a cluster's energy/carbon footprint
by consolidating workloads onto fewer nodes** during off-peak hours — packing a
lightly-loaded fleet down, cordoning and draining the freed nodes for
de-provisioning, all **without dropping availability** — then reporting the savings.

The cluster runs an underutilized fleet spread thinly across several worker nodes
(the energy-wasteful "before" state). The agent must recognize the consolidation
opportunity from live node utilization it inspects itself, drain the spare nodes
safely (honoring PodDisruptionBudgets and pod anti-affinity), and avoid
over-consolidating to the point of breaking a workload. A minimal carbon feed
(grid intensity + per-node power) supplies only the external figures the agent
can't derive from the cluster, for the savings estimate in its report.

Runs on **kind** (local, on the runner VM) — no cloud dependency, no GKE quota.

## How it works

- **Infrastructure** (`tf/prebuilt/greenops-consolidation-kind`) provisions a
  **multi-node** kind cluster (1 control-plane + **4 workers**) and runs
  `scripts/setup.sh`, which:
  - deploys the workload fleet. With four empty workers at bring-up the scheduler
    spreads the pods roughly one-per-node, so every worker carries a little load —
    the underutilized state the agent must consolidate,
  - waits for the fleet to become Available so the agent starts healthy.
- A declarative `local_file` resource delivers a minimal carbon feed (off-peak
  window, grid carbon intensity, per-node power draw — no utilization summary, no
  recommendation) to a per-run file `~/carbon-report-<cluster_name>.json` (removed
  automatically on `tofu destroy`).
- The feed's host path derives from `cluster_name` (which the harness
  run-token-prefixes), so concurrent runs on the shared bastion never collide. The
  prompt references it via `{{CLUSTER_NAME}}`.
- **Nothing tells the agent what to do** — the prompt states only the goal (cut
  overnight energy/carbon, keep workloads available); the agent inspects node
  utilization and each workload's scheduling constraints and decides the approach
  (consolidate → drain the spare nodes) and how far it can safely go itself.

### The fleet (namespace `workloads`)

| Workload | Replicas | Constraint | Role in the task |
| --- | --- | --- | --- |
| `web-frontend` | 2 | **required** pod anti-affinity (replicas on distinct nodes) + PDB | Sets the consolidation **floor of 2 nodes** |
| `api-server` | 2 | PDB `minAvailable: 1` | Drain must evict politely |
| `worker-batch` | 4 | none | Spreads one-per-node → makes the fleet span all 4 workers |
| `cache` | 1 | none | Freely reschedulable |
| `cron-runner` | 1 | none | Freely reschedulable |

The agent can safely collapse the cluster from **4 worker nodes to 2** — but not to
1: `web-frontend`'s required anti-affinity needs two distinct nodes, so an
over-aggressive drain-to-one leaves a replica Pending. That, plus the PDBs, makes
"maintain availability" a real constraint (SOT step 2: respect affinity/anti-affinity).

### How it maps to the source-of-truth scenario (Complex Task #9)

| SOT step | Realization in this task |
| --- | --- |
| 1. Carbon-aware load analysis | Read the carbon report (off-peak window, grid intensity, node power, fleet utilization) + live node/pod state; identify the consolidation opportunity. |
| 2. Predictive bin-packing | Determine the minimum safe node count by reasoning about capacity + the PDBs and the `web-frontend` anti-affinity (floor of 2). |
| 3. Evacuation & de-provisioning | Cordon + drain the spare nodes in a PDB-respecting way; drained nodes end SchedulingDisabled and empty (what an autoscaler would then reclaim). |
| 4. Availability monitoring | Keep every workload Running with no Pending pods; don't over-consolidate. |
| 5. GreenOps reporting | Write `greenops-report.md` with node-hours reclaimed and estimated CO2 saved. |

The parts of the SOT that the harness can't score objectively (real node-pool
de-provisioning — kind can't delete a node mid-cluster — and live auto-scale-up
revert on density-induced degradation) are distilled into the cordon/drain +
availability + anti-affinity constraints above, which are fully observable from
cluster state and the agent's trajectory.

## Setup (run on the GCE VM)

Run on the runner VM so kind and the agent are co-located. Prereqs (one-time):

- Docker (running), `kind`, `kubectl`, `tofu`, and the agent binary.
- Python ≥ 3.10 venv with the repo requirements installed.
- `fs.inotify` bump (kind) + ≥ 20 GB free disk (a 5-node cluster is heavier than a
  single-node one):
  ```bash
  echo -e "fs.inotify.max_user_watches=524288\nfs.inotify.max_user_instances=512" | sudo tee /etc/sysctl.d/99-kind.conf
  sudo sysctl --system
  ```

## Run

```bash
export GKE_CLUSTER_NAME="greenops-kind"   # used as the kind cluster name
export NAMESPACE="default"                # unused by this task; just needs to be set
export GCP_PROJECT_ID="local-kind"        # placeholder; only used for prompt/Vertex judge
export OPENCLAW_LOCAL="true"

export BENCH_AGENT_TYPE="cli"
export AGENT_TARGET="oc"
export AGENT_PROVIDER="google"
export AGENT_MODEL="gemini-3.1-pro-preview"
export AGENT_API_KEY="<your-gemini-key>"
export JUDGE_PROVIDER="google"
export JUDGE_MODEL="gemini-3.1-pro-preview"
export JUDGE_API_KEY="<your-gemini-key>"

python -m devops_bench tasks/common/greenops-consolidation/task.yaml
```

## Verify the environment manually (optional smoke test)

```bash
cd tf/prebuilt/greenops-consolidation-kind
tofu init && tofu apply -auto-approve -var cluster_name=greenops-kind
export KUBECONFIG=~/.kube/config && kubectl config use-context kind-greenops-kind

kubectl get nodes                                  # 1 control-plane + 4 workers
kubectl -n workloads get pods -o wide              # spread across the workers
cat ~/carbon-report-greenops-kind.json             # the delivered report

tofu destroy -auto-approve -var cluster_name=greenops-kind
```
You should see four worker nodes each carrying a couple of pods, the `web-frontend`
replicas on two distinct nodes, and the carbon report on disk. `tofu destroy`
removes the cluster and the host-side report.

## Results

`results/run_<timestamp>/`:
- `results.json` — per-check scores + the agent's full trajectory (analysis +
  cordon/drain + consolidation).
- `generated_files/greenops-report.md` — the report the agent wrote.

## Troubleshooting

| Symptom | Cause / Fix |
| --- | --- |
| `failed to join node with kubeadm … exit status 1` | inotify limits — apply the sysctl bump above (a 5-node cluster needs more watches). |
| `Error: … no space left on device` | Disk too small — grow to ≥ 20 GB. |
| Fleet never becomes Available during setup | Image pull from Docker Hub slow/failed; re-run `tofu apply`. `setup.sh` waits on `rollout`/`wait` and fails loudly rather than handing the agent a broken fixture. |
| A `web-frontend` pod is Pending after the agent's drain | Over-consolidation — fewer than two schedulable nodes remain, so the required anti-affinity can't be satisfied. At least two worker nodes must stay schedulable. |
