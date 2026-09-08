# Cross-Cluster Service Mesh Federation (Istio multi-primary)

This task evaluates an agent's ability to **operate a federated Istio service mesh
spanning two clusters** — diagnose a broken cross-cluster call, reconcile a mutual
TLS misconfiguration across the cluster boundary, and restore secure connectivity.

Two kind clusters are joined as an Istio **multi-primary / multi-network** mesh
(shared root CA, east-west gateways, cross-cluster endpoint discovery). A client in
the first cluster calls a backend in the second. An mTLS mismatch is injected so
the cross-cluster call fails the handshake; the agent must find and fix it.

Runs on **kind** (two local clusters, on the runner VM) — no cloud dependency, no
GKE quota. **It is the heaviest task in the suite** (two clusters + full Istio on
each); run it at a **low `MAX_PARALLEL`**.

## How it works

- **Infrastructure** (`tf/prebuilt/mesh-federation-kind`) provisions **two** kind
  clusters on the shared `kind` Docker network — `{{CLUSTER_NAME}}` (client) and
  `{{CLUSTER_NAME}}-peer` (backend) — then runs `scripts/setup.sh`, which builds a
  real federation:
  - downloads a pinned `istioctl` + samples (the bastion has none),
  - installs **MetalLB** on both clusters with non-overlapping pools carved from the
    kind subnet, so the east-west gateways get mutually-reachable LoadBalancer IPs,
  - installs a **shared root CA** (`cacerts`) in `istio-system` on both (federated
    trust domain),
  - installs **Istio multi-primary** control planes (mesh `mesh1`; per-cluster
    name + network),
  - installs **east-west gateways** + `expose-services` on both,
  - exchanges **remote secrets** both directions (with the kind API-server IP
    patched so the peer kubeconfig is reachable),
  - deploys the `backend` (cluster-2) and a `sleep` client (cluster-1), with the
    `backend` Service present in both clusters.
- **The injected fault:** cluster-2's `sample` namespace enforces
  `PeerAuthentication: STRICT`, while cluster-1 has a `DestinationRule` for the
  backend host with `tls.mode: DISABLE`. The client therefore sends plaintext and
  the server rejects it — the textbook STRICT-vs-DISABLE mTLS handshake failure.
- **The agent** reproduces the failing call, localizes the mTLS mismatch across the
  two clusters, reconciles it to a consistent mutual-TLS posture (without weakening
  security), verifies the cross-cluster call is restored over mTLS, and reports.

### How it maps to the source-of-truth scenario (Complex Task #10)

| SOT step | Realization in this task |
| --- | --- |
| 1. Network/identity analysis | Diagnose across both clusters: reproduce the failing call, inspect the mesh mTLS config and the two trust domains. |
| 2. Mesh expansion & trust federation | The shared root CA, east-west gateways, and remote-secret exchange are pre-established as the substrate (a real multi-primary mesh). |
| 3. Traffic routing & protocol translation | Cross-cluster routing is via Istio endpoint discovery; the client→backend path is the federated route under test. |
| 4. Real-time protocol validation | **The scored core** — detect the mTLS handshake failure and reconcile `PeerAuthentication`/`DestinationRule` to consistent strict mTLS. |
| 5. Governance & connectivity report | Write `mesh-federation-report.md` with root cause, fix, and the restored secure posture. |

Steps 2–3's *plumbing* is pre-built (it's kind-specific and not the skill under
test); the agent's job is the cross-cluster **diagnosis + mTLS reconciliation**
(steps 1, 4, 5), which is fully observable from cluster state and the trajectory.

## Setup (run on the GCE VM)

Run on the runner VM so both kind clusters and the agent are co-located. Prereqs:

- Docker (running), `kind`, `kubectl`, `tofu`, `make`, `curl`, and the agent binary.
- Python ≥ 3.10 venv with the repo requirements installed.
- **Generous host headroom** — two clusters + Istio is heavy. `fs.inotify` bump and
  **≥ 40 GB free disk** recommended:
  ```bash
  echo -e "fs.inotify.max_user_watches=524288\nfs.inotify.max_user_instances=512" | sudo tee /etc/sysctl.d/99-kind.conf
  sudo sysctl --system
  ```

## Run

```bash
export GKE_CLUSTER_NAME="mesh-kind"    # base name; clusters are mesh-kind / mesh-kind-peer
export NAMESPACE="sample"
export GCP_PROJECT_ID="local-kind"     # placeholder; only used for prompt/Vertex judge
export OPENCLAW_LOCAL="true"

export BENCH_AGENT_TYPE="cli"; export AGENT_TARGET="oc"
export AGENT_PROVIDER="google"; export AGENT_MODEL="gemini-3.1-pro-preview"
export AGENT_API_KEY="<your-gemini-key>"
export JUDGE_PROVIDER="google"; export JUDGE_MODEL="gemini-3.1-pro-preview"
export JUDGE_API_KEY="<your-gemini-key>"

python -m devops_bench tasks/common/mesh-federation/task.yaml
```

## Verify the environment manually (optional smoke test)

```bash
cd tf/prebuilt/mesh-federation-kind
tofu init && tofu apply -auto-approve -var cluster_name=mesh-kind
export KUBECONFIG=~/.kube/config

# Both clusters + the federation
kubectl --context kind-mesh-kind get pods -n istio-system
kubectl --context kind-mesh-kind-peer get pods -n sample        # backend pods
# Reproduce the failing cross-cluster call (should fail until fixed):
kubectl --context kind-mesh-kind -n sample exec deploy/sleep -c sleep -- \
  curl -sS -m 5 backend.sample.svc.cluster.local:8080 || echo "FAILS (as injected)"

tofu destroy -auto-approve -var cluster_name=mesh-kind
```

## Results

`results/run_<timestamp>/`:
- `results.json` — per-check scores + the agent's full trajectory (diagnosis + fix).
- `generated_files/mesh-federation-report.md` — the report the agent wrote.

## Troubleshooting

| Symptom | Cause / Fix |
| --- | --- |
| `failed to join node with kubeadm` | inotify limits — apply the sysctl bump (two clusters need more watches). |
| `no space left on device` | Two clusters + Istio images are heavy — grow disk to ≥ 40 GB. |
| east-west gateway stuck `<pending>` external IP | MetalLB pool didn't apply / overlaps — check `kubectl -n metallb-system get ipaddresspool`. |
| cross-cluster call still fails after the agent's fix | Endpoint discovery not converged, or the remote secret's API server isn't reachable — check `istioctl remote-clusters` and that the remote secret server is the node's Docker IP. |
