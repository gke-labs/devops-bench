# Secret Rotation Task

This task evaluates the agent's ability to rotate a compromised Google Secret Manager secret consumed by a deployment in a GKE cluster with zero downtime, and then cleanly revoke/destroy the old version of the secret.

## Task Scenario & Evaluation Criteria

### Infrastructure Harness
When the evaluator runs, it automatically provisions a comprehensive testing environment:
- **GCP Secret Manager:** A compromised version of `db-credentials` is pre-provisioned.
- **GKE Cluster:** A cluster configured with Workload Identity.
- **ExternalSecrets Operator:** Installed and configured to authenticate natively to GCP via Workload Identity.
- **Application Workload:** A Python HTTP server (`db-secret-viewer`) exposing port `8080` that actively serves the decoded secret from a mounted volume.

### Evaluation Requirements
The agent is tasked with rotating the secret without causing downtime. The GEval framework automatically scores the agent out of 5 based on whether it successfully executed the following steps:
1. Inspects the `ExternalSecret` resource to determine the exact GCP Secret Manager object.
2. Generates a strong, cryptographically secure password and creates a new version of the secret in GCP Secret Manager.
3. Updates the `ExternalSecret` manifest in the cluster to point to the new version.
4. Executes a zero-downtime rolling restart of the application deployment.
5. Verifies the application is healthy and actively consuming the new secret (e.g., by checking pod logs or querying the application endpoint).
6. Maintains continuous service availability throughout the process.
7. Explicitly revokes (destroys) the compromised version of the secret in GCP.

## Setup & Running the Benchmark

The infrastructure for this task (including GKE setup, workload identity, external-secrets operator, permissions for the runner VM service account, and deploying the target application) is automatically provisioned and managed via OpenTofu (tofu) when you run the evaluator.

### 1. Export Environment Variables
Export the target GCP environment, agent, and judge configurations:

```bash
# GCP Environment
export GCP_PROJECT_ID="your-project-id"
export GKE_CLUSTER_NAME="your-cluster-name"
export GCP_LOCATION="us-central1"
export NAMESPACE="secret-rotation-run-1"

# Agent Config
export BENCH_AGENT_TYPE="cli"       # 'cli' or 'api'
export AGENT_TARGET="oc"            # The agent target binary/orchestrator
export AGENT_PROVIDER="google"      # LLM provider for the agent
export AGENT_MODEL="gemini-3.1-pro-preview"
export AGENT_API_KEY="your-gemini-api-key"

# Judge Config
export JUDGE_PROVIDER="google"
export JUDGE_MODEL="gemini-3.1-pro-preview"
export JUDGE_API_KEY="your-gemini-api-key"

# SSH Config (required by openclaw for VM interactions)
export OPENCLAW_SSH_USER="your_ssh_username"

# Credentials config (ADC path)
export GOOGLE_APPLICATION_CREDENTIALS="/path/to/your/application_default_credentials.json"
```

### 2. Run the Evaluator

#### Option A: Running Locally (via Python)
Run the evaluator script directly:
```bash
python3 pkg/evaluator/evaluate.py tasks/gcp/secret-rotation/task.yaml
```

> [!TIP]
> **Saving time on subsequent runs:**
> Export `export BENCH_NO_TEARDOWN="true"` to prevent tearing down the GKE cluster at the end of the run. On your next runs, simply change the namespace environment variable (e.g. `export NAMESPACE="secret-rotation-run-2"`) and run the evaluator again. It will skip cluster provisioning and run in under 30 seconds.


#### Option B: Running inside Docker
To run within the container (after building it via `docker build -t devops-bench:latest .`):
```bash
docker run -it \
  -v ~/.config/gcloud:/root/.config/gcloud \
  -v ~/.ssh:/root/.ssh \
  -v $(pwd)/results:/app/results \
  -e CLOUD_PROVIDER="gcp" \
  -e GCP_PROJECT_ID="${GCP_PROJECT_ID}" \
  -e GKE_CLUSTER_NAME="${GKE_CLUSTER_NAME}" \
  -e GCP_LOCATION="${GCP_LOCATION}" \
  -e NAMESPACE="${NAMESPACE}" \
  -e BENCH_TASK_FILE="tasks/gcp/secret-rotation/task.yaml" \
  -e BENCH_AGENT_TYPE="${BENCH_AGENT_TYPE}" \
  -e AGENT_TARGET="${AGENT_TARGET}" \
  -e AGENT_PROVIDER="${AGENT_PROVIDER}" \
  -e AGENT_MODEL="${AGENT_MODEL}" \
  -e AGENT_API_KEY="${AGENT_API_KEY}" \
  -e JUDGE_PROVIDER="${JUDGE_PROVIDER}" \
  -e JUDGE_MODEL="${JUDGE_MODEL}" \
  -e JUDGE_API_KEY="${JUDGE_API_KEY}" \
  -e OPENCLAW_SSH_USER="${OPENCLAW_SSH_USER}" \
  -e GOOGLE_APPLICATION_CREDENTIALS=/root/.config/gcloud/application_default_credentials.json \
  devops-bench:latest
```
