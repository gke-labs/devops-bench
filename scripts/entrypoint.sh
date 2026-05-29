#!/bin/bash
set -e

if [ -z "$CLOUD_PROVIDER" ] || [ -z "$BENCH_TASK_FILE" ]; then
    echo "Error: CLOUD_PROVIDER and BENCH_TASK_FILE environment variables must be set."
    exit 1
fi

AUTH_SCRIPT="./scripts/setup_auth_${CLOUD_PROVIDER}.sh"
if [ -f "$AUTH_SCRIPT" ]; then
    source "$AUTH_SCRIPT"
fi

# Bypass any host-level GKE API endpoint overrides mounted via gcloud config
export CLOUDSDK_API_ENDPOINT_OVERRIDES_CONTAINER="https://container.googleapis.com/"

export KUBECONFIG=/tmp/kubeconfig

mkdir -p hello-app
cat <<EOF > hello-app/main.go
package main
import "fmt"
func main() { fmt.Println("Hello, World!") }
EOF

if [ -f "$HOME/deepeval_env/bin/activate" ]; then
    source "$HOME/deepeval_env/bin/activate"
fi

echo "Starting Evaluation Engine..."
python3 pkg/evaluator/evaluate.py "$BENCH_TASK_FILE"

LATEST_RESULTS=$(ls -t results/run_*/results.json 2>/dev/null | head -n 1)
if [ -n "$LATEST_RESULTS" ]; then
    cat "$LATEST_RESULTS"
fi
