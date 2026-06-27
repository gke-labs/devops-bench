#!/usr/bin/env bash
#
# Legacy-vs-refactored comparison for ANY task, ANY CLI agent, on real infra.
#
#   Arm A (LEGACY):     python3 pkg/evaluator/evaluate.py  <task>
#   Arm B (REFACTORED): python3 -m devops_bench           <task>
#
# Runs the same task through both entrypoints with the same agent/judge config,
# then diffs the two results.json via scripts/compare_results.py. The agent is
# selected entirely by env, so this works for gemini, openclaw, or any other
# registered CLI agent — nothing here is task- or agent-specific.
#
# (This is the real-infra comparison. scripts/compare_legacy_vs_refactor.sh is a
# separate, mock-Ollama regression gate.)
#
# Usage:
#   scripts/run_compare.sh <task.yaml>
#
# Required env:
#   AGENT_API_KEY, JUDGE_API_KEY
#   GCP_PROJECT_ID, GKE_CLUSTER_NAME   (unless BENCH_NO_INFRA=true)
# Optional env:
#   RESULTS_ROOT (default results), NAMESPACE, GCP_LOCATION (us-central1-a),
#   AGENT_MODEL / JUDGE_MODEL (default gemini-3.1-pro-preview),
#   RULES_FILE   (operator brief; delivered to refactored via AGENT_RULES_TEXT
#                 and to the legacy gemini arm via a repo-root GEMINI.md shadow),
#   BENCH_NO_INFRA=true  (plumbing smoke; skips GKE).
#   ...plus any agent-specific vars you export, e.g.:
#     gemini   : AGENT_TARGET=gemini   BENCH_AGENT_TYPE stays default (cli->gemini)
#     openclaw : AGENT_TARGET=oc  OPENCLAW_LOCAL=true  OPENCLAW_BIN=oc
#                refactored arm: BENCH_AGENT_TYPE=openclaw  AGENT_MCP_SERVER=gke-mcp
#                                AGENT_SKILLS_PATHS=skills
set -euo pipefail

TASK_FILE="${1:?usage: scripts/run_compare.sh <task.yaml>}"
[[ -f "$TASK_FILE" ]] || { echo "ERROR: task file not found: $TASK_FILE" >&2; exit 2; }

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$REPO_ROOT"

STAMP="${STAMP:-$(date +%Y%m%d_%H%M%S)}"
RUN_DIR="${RESULTS_ROOT:-results}/compare_${STAMP}"
mkdir -p "${RUN_DIR}/legacy" "${RUN_DIR}/refactored"

: "${AGENT_API_KEY:?set AGENT_API_KEY}"
: "${JUDGE_API_KEY:?set JUDGE_API_KEY}"
BENCH_NO_INFRA="${BENCH_NO_INFRA:-false}"
if [[ "$BENCH_NO_INFRA" != "true" ]]; then
  : "${GCP_PROJECT_ID:?set GCP_PROJECT_ID (or BENCH_NO_INFRA=true)}"
  : "${GKE_CLUSTER_NAME:?set GKE_CLUSTER_NAME (or BENCH_NO_INFRA=true)}"
fi

# Shared agent/judge config (both arms identical where it matters). Anything the
# caller already exported (AGENT_TARGET, BENCH_AGENT_TYPE, OPENCLAW_*, MCP, etc.)
# is passed through to both arms.
export BENCH_AGENT_TYPE="${BENCH_AGENT_TYPE:-cli}"
export AGENT_PROVIDER="${AGENT_PROVIDER:-google}"
export AGENT_MODEL="${AGENT_MODEL:-gemini-3.1-pro-preview}"
export JUDGE_PROVIDER="${JUDGE_PROVIDER:-google}"
export JUDGE_MODEL="${JUDGE_MODEL:-gemini-3.1-pro-preview}"
export AGENT_API_KEY JUDGE_API_KEY
# google-provider CLIs read the key from these; harmless for other providers.
export GEMINI_API_KEY="${GEMINI_API_KEY:-$AGENT_API_KEY}"
export GOOGLE_API_KEY="${GOOGLE_API_KEY:-$AGENT_API_KEY}"
export GCP_LOCATION="${GCP_LOCATION:-us-central1-a}"
export NAMESPACE="${NAMESPACE:-compare}"
export BENCH_NO_INFRA

RULES_TEXT=""
[[ -n "${RULES_FILE:-}" && -f "${RULES_FILE}" ]] && RULES_TEXT="$(cat "${RULES_FILE}")"

echo "==> compare dir: ${RUN_DIR}  (task: ${TASK_FILE}; mode: $([[ "$BENCH_NO_INFRA" == true ]] && echo NO-INFRA || echo 'REAL INFRA'))"

# ----------------------------- ARM A: LEGACY ------------------------------- #
echo "==> ARM A (LEGACY): pkg/evaluator/evaluate.py"
BEFORE="$(ls -d results/run_* 2>/dev/null || true)"
GEMINI_MD="${REPO_ROOT}/GEMINI.md"; GEMINI_MD_BAK=""
restore_gemini_md() {
  if [[ -n "$RULES_TEXT" ]]; then
    if [[ -n "$GEMINI_MD_BAK" ]]; then mv "$GEMINI_MD_BAK" "$GEMINI_MD"; else rm -f "$GEMINI_MD"; fi
  fi
}
if [[ -n "$RULES_TEXT" ]]; then
  # Legacy gemini auto-loads a repo-root GEMINI.md; shadow it for the run, then
  # restore. (Other legacy agents ignore it — harmless.)
  [[ -f "$GEMINI_MD" ]] && { GEMINI_MD_BAK="$(mktemp)"; cp "$GEMINI_MD" "$GEMINI_MD_BAK"; }
  printf '%s' "$RULES_TEXT" > "$GEMINI_MD"
  # Restore on ANY exit path (a ``set -e`` abort, a later arm failure, or a
  # clean finish) so a tracked GEMINI.md is never left clobbered.
  trap restore_gemini_md EXIT
fi
if ! python3 pkg/evaluator/evaluate.py "${TASK_FILE}" >"${RUN_DIR}/legacy/run.log" 2>&1; then
  echo "ERROR: legacy arm failed"; tail -30 "${RUN_DIR}/legacy/run.log"; exit 2
fi
AFTER="$(ls -d results/run_* 2>/dev/null || true)"
LEGACY_RUN_DIR="$(comm -13 <(printf '%s\n' "${BEFORE}") <(printf '%s\n' "${AFTER}") | grep -E 'results/run_' | tail -1 || true)"
if [[ -z "${LEGACY_RUN_DIR}" || ! -f "${LEGACY_RUN_DIR}/results.json" ]]; then
  echo "ERROR: legacy results.json not found"; tail -30 "${RUN_DIR}/legacy/run.log"; exit 2
fi
cp -R "${LEGACY_RUN_DIR}/." "${RUN_DIR}/legacy/"
LEGACY_RESULTS="${RUN_DIR}/legacy/results.json"
echo "    legacy results: ${LEGACY_RESULTS}"

# --------------------------- ARM B: REFACTORED ----------------------------- #
echo "==> ARM B (REFACTORED): python3 -m devops_bench"
REFACTOR_LOG="${RUN_DIR}/refactored/run.log"
(
  [[ -n "$RULES_TEXT" ]] && export AGENT_RULES_TEXT="$RULES_TEXT"
  if [[ "$BENCH_NO_INFRA" == "true" ]]; then
    python3 -m devops_bench --results-root "${RUN_DIR}/refactored" "${TASK_FILE}"
  else
    python3 -m devops_bench --project "${GCP_PROJECT_ID}" --cluster "${GKE_CLUSTER_NAME}" \
      --results-root "${RUN_DIR}/refactored" "${TASK_FILE}"
  fi
) >"${REFACTOR_LOG}" 2>&1 || { echo "ERROR: refactored arm failed"; tail -30 "${REFACTOR_LOG}"; exit 2; }
REFACTOR_RESULTS="$(grep -oE 'results: .*results\.json' "${REFACTOR_LOG}" | tail -1 | sed 's/^results: //')"
[[ -z "${REFACTOR_RESULTS}" || ! -f "${REFACTOR_RESULTS}" ]] && REFACTOR_RESULTS="$(find "${RUN_DIR}/refactored" -name results.json | head -1)"
if [[ -z "${REFACTOR_RESULTS}" || ! -f "${REFACTOR_RESULTS}" ]]; then
  echo "ERROR: refactored results.json not found"; tail -30 "${REFACTOR_LOG}"; exit 2
fi
echo "    refactored results: ${REFACTOR_RESULTS}"

# -------------------------------- DIFF ------------------------------------- #
echo "==> compare_results.py"
set +e
python3 scripts/compare_results.py \
  --legacy "${LEGACY_RESULTS}" \
  --refactor "${REFACTOR_RESULTS}" \
  --json-report "${RUN_DIR}/comparison-report.json" | tee "${RUN_DIR}/comparison-report.md"
echo "==> done. RUN_DIR=${RUN_DIR}"
