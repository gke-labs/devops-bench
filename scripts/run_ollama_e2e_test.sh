#!/usr/bin/env bash
# End-to-end test for the Ollama provider integration.
# Uses a mock Ollama server so no model weights or live cluster are required.
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$REPO_ROOT"

MOCK_PORT="${MOCK_PORT:-11435}"
TASK_FILE="tasks/noop/gateway-https-redirect/task.yaml"

echo "==> Starting mock Ollama server on port ${MOCK_PORT}"
python3 scripts/mock_ollama_server.py "${MOCK_PORT}" &
MOCK_PID=$!
sleep 1
curl -sf "http://127.0.0.1:${MOCK_PORT}/v1/models" | python3 -m json.tool || {
  echo "ERROR: mock server failed to start"; kill "${MOCK_PID}" 2>/dev/null; exit 1
}

echo ""
echo "==> Running benchmark task: ${TASK_FILE}"
echo "    AGENT_PROVIDER=ollama  JUDGE_PROVIDER=ollama  MODEL=gemma4:2b"
echo ""

export BENCH_AGENT_TYPE=api
export BENCH_USE_MCP=false
export BENCH_NO_INFRA=true
export AGENT_PROVIDER=ollama
export JUDGE_PROVIDER=ollama
export AGENT_MODEL=gemma4:2b
export JUDGE_MODEL=gemma4:2b
export OLLAMA_BASE_URL="http://127.0.0.1:${MOCK_PORT}/v1"
export GCP_PROJECT_ID=test-project
export CLUSTER_NAME=test-cluster

python3 pkg/evaluator/evaluate.py "${TASK_FILE}"
EXIT_CODE=$?

echo ""
echo "==> Stopping mock server (PID ${MOCK_PID})"
kill "${MOCK_PID}" 2>/dev/null || true

exit ${EXIT_CODE}
