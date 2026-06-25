# create-deployment task

The agent generates a Kubernetes manifest for a vLLM-served Gemma 3 12B model and
deploys it to the GKE cluster (exercises the `generate_manifest` gke-mcp tool, GPU
toleration, autoscaling). Infra = `prebuilt/minimum` (a bare GKE cluster); the agent
does the deploying.

## Parallel run on the bastion (Vertex)

Full setup + troubleshooting: **[`docs/parallel-evals.md`](../../../docs/parallel-evals.md)**.

```bash
BASTION_USE_GCPNODE=1 BASTION_VM=claw-ubuntu BASTION_ZONE=us-central1-a \
BASTION_PROJECT=jessieliu-gke-dev BASTION_SSH_USER=jssl_google_com \
REMOTE_DIR=devops-bench-eval SKIP_SYNC=1 \
GCP_PROJECT_ID=jessieliu-gke-dev GKE_CLUSTER_NAME=createdep GCP_LOCATION=us-central1-a \
AGENT_PROVIDER=google-vertex JUDGE_PROVIDER=google JUDGE_MODEL=gemini-3.1-pro-preview \
BENCH_VERTEX=1 MAX_PARALLEL=2 \
MATRIX_TASKS="tasks/gcp/create-deployment/task.yaml" \
MATRIX_MODELS="gemini-3.1-pro-preview gemini-3.5-flash" \
RESULTS_DIR=results/matrix \
bash scripts/bastion/run_matrix_legacy.sh
```

Task-specific note:
- **Do NOT set `NAMESPACE`.** `prebuilt/minimum` declares no `namespace` tofu variable,
  so a stray `NAMESPACE` in `secrets.env` makes tofu fail with *"Value for undeclared
  variable namespace"*. Remove it for this task (`sed -i '/export NAMESPACE=/d' ~/secrets.env`).
- `prebuilt/minimum` is parallel-safe (cluster, `gke-nodes-*` SA, IAP firewall are
  per-run-token-unique; the shared `container.admin` grant is harmless while the bastion SA holds `owner`).
