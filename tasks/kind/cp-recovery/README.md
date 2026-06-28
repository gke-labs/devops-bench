# Control Plane Recovery Task

This task evaluates the agent's ability to diagnose and recover a corrupted etcd control
plane on a **real Kubernetes cluster**. Unlike a managed control plane (e.g. GKE) which hides
etcd and the API server, this task runs on a multi-node [kind](https://kind.sigs.k8s.io/)
cluster whose **real** 3-member etcd and API server we fully control.

The agent must: diagnose the unhealthy etcd member, verify the integrity of a staged etcd
snapshot, restore the member and re-establish Raft quorum, reconcile the running workloads
against the desired GitOps state, and produce an incident report.

## How it works

- **Infrastructure** (`tf/prebuilt/cp-recovery-kind`) is provisioned by OpenTofu when you run
  the evaluator. It creates a kind cluster with **3 control-plane nodes** (a real 3-member
  stacked etcd) and **1 worker**, deploys the desired-state workloads (`workload-1`,
  `workload-2`), the `gitops-state` ConfigMap, and a backup volume (`etcd-backup-pvc`).
- **Fault injection happens outside the cluster.** During `tofu apply`,
  `scripts/inject-fault.sh` takes a verified etcd snapshot (staging it + its sha256 into the
  backup PVC), then corrupts a **single** etcd member and restarts it. Quorum (2/3) is
  preserved, so the API server stays up and the agent keeps `kubectl` access — but one member
  crash-loops. No Job, ConfigMap, or script describing the corruption is left in the cluster.
- **`workload-3`** is intentionally never created, so after recovery the agent must reconcile
  it from the `gitops-state` desired state.

## Setup & Running the Benchmark

Because kind runs the cluster as local Docker containers, the eval, the kind cluster, and the
agent must all run on the **same host**. The simplest setup is to run everything directly on
the runner VM (e.g. the OpenClaw GCE VM).

### Host requirements

- **≥ 4 vCPU, ≥ 8 GB RAM** (a 4-node kind cluster is heavy; tested on 4 vCPU / 15 GB).
- **≥ 50 GB disk.** The default boot disk is often too small — a running 4-node cluster plus
  the `kindest/node` image needs several GB free. On GCE you can grow the disk live:
  ```bash
  # from Cloud Shell / a machine with working gcloud:
  gcloud compute disks resize <VM_NAME> --size 50GB --zone <ZONE>
  # then on the VM:
  sudo growpart /dev/sda 1 && sudo resize2fs /dev/sda1 && df -h /
  ```
- **Python ≥ 3.10** (the `deepeval` dependency requires it).
- Docker (running), and the OpenClaw `oc` binary at `~/bin/oc` (override with `OPENCLAW_BIN`).

### 1. Install prerequisites (one-time)

```bash
# kind, kubectl, tofu, docker
curl -Lo ./kind https://kind.sigs.k8s.io/dl/latest/kind-linux-amd64 && chmod +x kind && sudo mv kind /usr/local/bin/
curl -LO "https://dl.k8s.io/release/$(curl -L -s https://dl.k8s.io/release/stable.txt)/bin/linux/amd64/kubectl" && chmod +x kubectl && sudo mv kubectl /usr/local/bin/
sudo apt-get update && sudo apt-get install -y unzip python3-venv
curl -fsSL https://get.opentofu.org/install-opentofu.sh -o /tmp/it.sh && sudo bash /tmp/it.sh --install-method deb
curl -fsSL https://get.docker.com | sh && sudo usermod -aG docker "$USER"   # then log out/in so `docker ps` works without sudo

# verify
for t in docker kind kubectl tofu; do command -v $t >/dev/null && echo "have $t" || echo "MISSING $t"; done
```

### 2. Raise inotify limits (one-time, required)

Multi-node kind exhausts the default inotify limits, which makes the **worker node fail to
`kubeadm join`** (`failed to join node with kubeadm … exit status 1`). Bump them:

```bash
echo -e "fs.inotify.max_user_watches=524288\nfs.inotify.max_user_instances=512" | sudo tee /etc/sysctl.d/99-kind.conf
sudo sysctl --system
```

### 3. Python environment

```bash
cd ~/devops-bench
python3 -m venv .venv
source .venv/bin/activate
pip install --upgrade pip
pip install -r requirements.txt
```

### 4. Configure environment variables

```bash
export GKE_CLUSTER_NAME="cp-recovery-kind"   # used as the kind cluster name
export NAMESPACE="cp-recovery"               # MUST match the stack's namespace
export GCP_PROJECT_ID="local-kind"           # placeholder; only used for prompt/Vertex judge

# Run the OpenClaw agent locally (no SSH to a remote VM)
export OPENCLAW_LOCAL="true"

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

> Tip: drop the `export`s into a local `env.sh` (git-ignored — it holds API keys) so future
> runs are just `source .venv/bin/activate && source env.sh`.

### 5. Run the evaluator

```bash
python pkg/evaluator/evaluate.py tasks/kind/cp-recovery/task.yaml
```

The harness provisions the cluster (+ corruption), runs the local `oc` agent against it,
judges the result, and tears everything down. Results land in `results/run_<timestamp>/`:
- `results.json` — per-check scores + the agent's full trajectory.
- `generated_files/incident-report.md` — the report the agent wrote.

> [!TIP]
> To iterate without re-creating the cluster each run, `export BENCH_NO_TEARDOWN="true"`.
> Delete it manually when done: `kind delete cluster --name cp-recovery-kind`.

## Verifying the environment manually

You can provision the stack by hand and inspect the degraded state before handing it to the agent:

```bash
cd tf/prebuilt/cp-recovery-kind
tofu init && tofu apply -auto-approve -var cluster_name=cp-recovery-kind -var namespace=cp-recovery
export KUBECONFIG=~/.kube/config

kubectl get nodes                                    # 3 control-plane + 1 worker, Ready
kubectl -n kube-system get pods -l component=etcd    # one etcd-* CrashLoopBackOff
kubectl get ns                                       # still works -> API server up (quorum held)
kubectl get deploy -n cp-recovery                    # workload-1, workload-2 (no workload-3)
kubectl get pvc -n cp-recovery etcd-backup-pvc       # Bound
docker exec cp-recovery-kind-worker ls -l /backup    # etcd-backup.db + etcd-backup.sha256

tofu destroy -auto-approve -var cluster_name=cp-recovery-kind -var namespace=cp-recovery
```

## Troubleshooting

| Symptom | Cause / Fix |
| --- | --- |
| `failed to join node with kubeadm … exit status 1` | inotify limits — apply step 2. |
| `Error: … no space left on device` (cluster create fails) | Disk too small — grow it (see Host requirements). |
| `TypeError: unsupported operand type(s) for \|: …` on import | Python < 3.10 — use a 3.10+ venv. |
| `No such file or directory: 'tofu'` / `kind` / `docker` | Missing prerequisite — install step 1. |
| `ModuleNotFoundError: No module named 'deepeval'` | venv not active / deps not installed — step 3. |
