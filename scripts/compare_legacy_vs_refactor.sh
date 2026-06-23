#!/usr/bin/env bash
# Temporary legacy-vs-refactor regression gate (droppable scaffolding).
#
# Runs the SAME reference task through both the legacy entrypoint
# (pkg/evaluator/evaluate.py) and the refactor entrypoint
# (python -m devops_bench) against a deterministic mock Ollama server, then
# diffs the two results.json files via scripts/compare_results.py.
#
# Usage: scripts/compare_legacy_vs_refactor.sh [TASK_FILE]
# Env:   MOCK_PORT (default 11439)
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$REPO_ROOT"

MOCK_PORT="${MOCK_PORT:-11439}"
TASK_FILE="${1:-tasks/generic/gateway-https-redirect/task.yaml}"
TMP_DIR="$(mktemp -d)"

cleanup() {
  if [[ -n "${MOCK_PID:-}" ]]; then
    kill "${MOCK_PID}" 2>/dev/null || true
  fi
  rm -rf "${TMP_DIR}" 2>/dev/null || true
}
# Always clean up the mock + temp dir, even on a failed run (legacy script lacked this).
trap cleanup EXIT

echo "==> Starting mock Ollama server on port ${MOCK_PORT}"
python3 scripts/mock_ollama_server.py "${MOCK_PORT}" >"${TMP_DIR}/mock.log" 2>&1 &
MOCK_PID=$!

# Health-check the mock before running anything.
for _ in $(seq 1 30); do
  if curl -sf "http://127.0.0.1:${MOCK_PORT}/v1/models" >/dev/null 2>&1; then
    break
  fi
  sleep 0.3
done
if ! curl -sf "http://127.0.0.1:${MOCK_PORT}/v1/models" >/dev/null 2>&1; then
  echo "ERROR: mock server failed to start; log follows:" >&2
  cat "${TMP_DIR}/mock.log" >&2
  exit 2
fi
echo "    mock server healthy (pid ${MOCK_PID})"

# Shared env mirroring scripts/run_ollama_e2e_test.sh, pointed at the mock.
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

echo ""
echo "==> Running LEGACY: python3 pkg/evaluator/evaluate.py ${TASK_FILE}"
# Legacy writes results/run_<ts>/results.json relative to CWD and ignores
# RESULTS_ROOT. Record pre-existing run dirs, then pick the newest new one.
BEFORE="$(ls -d results/run_* 2>/dev/null | sort || true)"
uv run python pkg/evaluator/evaluate.py "${TASK_FILE}" >"${TMP_DIR}/legacy.log" 2>&1 || {
  echo "ERROR: legacy run failed; log follows:" >&2
  cat "${TMP_DIR}/legacy.log" >&2
  exit 2
}
AFTER="$(ls -d results/run_* 2>/dev/null | sort || true)"
LEGACY_RUN_DIR="$(comm -13 <(printf '%s\n' "${BEFORE}") <(printf '%s\n' "${AFTER}") | grep -E 'results/run_' | tail -1 || true)"
if [[ -z "${LEGACY_RUN_DIR}" ]]; then
  echo "ERROR: could not locate the legacy run directory" >&2
  exit 2
fi
LEGACY_RESULTS="${REPO_ROOT}/${LEGACY_RUN_DIR}/results.json"
echo "    legacy results: ${LEGACY_RESULTS}"

echo ""
echo "==> Running REFACTOR: uv run python -m devops_bench ${TASK_FILE}"
# Isolate the refactor output under TMP_DIR via RESULTS_ROOT, then parse the
# printed 'results: <path>' line.
REFACTOR_LOG="${TMP_DIR}/refactor.log"
RESULTS_ROOT="${TMP_DIR}/refactor_results" uv run python -m devops_bench "${TASK_FILE}" \
  >"${REFACTOR_LOG}" 2>&1 || {
  echo "ERROR: refactor run failed; log follows:" >&2
  cat "${REFACTOR_LOG}" >&2
  exit 2
}
REFACTOR_RESULTS="$(grep -oE 'results: .*results\.json' "${REFACTOR_LOG}" | tail -1 | sed 's/^results: //')"
if [[ -z "${REFACTOR_RESULTS}" || ! -f "${REFACTOR_RESULTS}" ]]; then
  echo "ERROR: could not parse refactor results path; log follows:" >&2
  cat "${REFACTOR_LOG}" >&2
  exit 2
fi
echo "    refactor results: ${REFACTOR_RESULTS}"

echo ""
echo "==> Comparing results"
set +e
uv run python scripts/compare_results.py \
  --legacy "${LEGACY_RESULTS}" \
  --refactor "${REFACTOR_RESULTS}"
VERDICT=$?
set -e

echo ""
echo "==> Result paths"
echo "    legacy:   ${LEGACY_RESULTS}"
echo "    refactor: ${REFACTOR_RESULTS}"
if [[ "${VERDICT}" -eq 0 ]]; then
  echo "==> VERDICT: PASS (no regressions); exit ${VERDICT}"
else
  echo "==> VERDICT: FAIL or error; exit ${VERDICT}"
fi
exit "${VERDICT}"
