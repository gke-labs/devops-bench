#!/bin/bash
set -e

# Verify required environment variables are set
if [ -z "$CLOUD_PROVIDER" ] || [ -z "$TASK_FILE" ]; then
    echo "Error: CLOUD_PROVIDER and TASK_FILE environment variables must be set."
    echo "Usage: docker run -e CLOUD_PROVIDER=<gcp> -e TASK_FILE=<file> ..."
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
# We assume infra.py reads necessary env vars (like PROJECT_ID, CLUSTER_NAME) directly.
echo "Step 2: Bringing up cluster for $CLOUD_PROVIDER..."
python3 scripts/infra.py "$CLOUD_PROVIDER" up

# Step 3: Call the eval script with the task to eval
echo "Step 3: Running evaluation..."
# TODO: This needs to be replaced by the actual eval run
echo "Displaying task file content:"
cat "$TASK_FILE"

# Simulate writing results to host
TIMESTAMP=$(date +%Y%m%d_%H%M%S)
echo "{\"task\": \"$TASK_FILE\", \"status\": \"mock_success\"}" > "/app/results/results_$TIMESTAMP.json"

# Step 4: Call the deployer script to shut the environment down
echo "Step 4: Tearing down cluster..."
python3 scripts/infra.py "$CLOUD_PROVIDER" down
