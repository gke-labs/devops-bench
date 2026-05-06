#!/bin/bash
set -e

# Verify required environment variables are set
if [ -z "$CLOUD_PROVIDER" ] || [ -z "$BENCH_TASK_FILE" ]; then
    echo "Error: CLOUD_PROVIDER and BENCH_TASK_FILE environment variables must be set."
    echo "Usage: docker run -e CLOUD_PROVIDER=<gcp> -e BENCH_TASK_FILE=<file> ..."
    exit 1
fi

# Step 1: Set up environment (auth) by calling provider-specific script
AUTH_SCRIPT="./scripts/setup_auth_${CLOUD_PROVIDER}.sh"
if [ -f "$AUTH_SCRIPT" ]; then
    echo "Running auth setup for $CLOUD_PROVIDER..."
    source "$AUTH_SCRIPT"
else
    echo "Warning: No auth setup script found at $AUTH_SCRIPT"
fi

export KUBECONFIG=/tmp/kubeconfig

# Step 2: Call the deployer script to bring up the cluster
# We assume infra.py reads necessary env vars (like GCP_PROJECT_ID, GKE_CLUSTER_NAME) directly.
echo "Step 2: Bringing up cluster for $CLOUD_PROVIDER..."
python3 scripts/infra.py "$CLOUD_PROVIDER" up

# Step 2.5: Create Hello World App
echo "Step 2.5: Creating Hello World Go App..."
mkdir -p hello-app
cat <<EOF > hello-app/main.go
package main
import "fmt"
func main() {
    fmt.Println("Hello, World! This is a simple Go application.")
}
EOF

# Step 3: Call the eval script with the task to eval
echo "Step 3: Running evaluation..."
if [ -f "$HOME/deepeval_env/bin/activate" ]; then
    echo "Activating virtual environment..."
    source "$HOME/deepeval_env/bin/activate"
fi

python3 pkg/evaluator/evaluate.py "$BENCH_TASK_FILE"

# Step 3.5: Display results
echo "Step 3.5: Displaying results..."
LATEST_RESULTS=$(ls -t results/run_*/results.json 2>/dev/null | head -n 1)
if [ -n "$LATEST_RESULTS" ] && [ -f "$LATEST_RESULTS" ]; then
    echo "Latest results file: $LATEST_RESULTS"
    cat "$LATEST_RESULTS"
else
    echo "Warning: No results file found."
fi

# Step 4: Call the deployer script to shut the environment down
echo "Step 4: Tearing down cluster..."
python3 scripts/infra.py "$CLOUD_PROVIDER" down
