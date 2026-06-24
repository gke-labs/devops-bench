#!/usr/bin/env bash
#
# Shared library for the bastion eval-matrix orchestrators:
#   run_matrix.sh         (refactored arm: Task x Model x AgentConfig)
#   run_matrix_legacy.sh  (legacy arm:     Task x Model)
#
# Not run directly. A wrapper sources this, sets the MATRIX_* / run config, then
# builds the global COMBOS array (each entry "run_id|task|kvs|arm", where kvs is
# a ';'-joined KEY=VALUE list of per-combo env, e.g.
# "AGENT_MODEL=gemini-3.1-pro;BENCH_AGENT_TYPE=openclaw;...") and calls
# `matrix_dispatch "<label>"`. Each combo runs as an isolated --parallel run on
# the bastion (its own cluster); results are copied back to RESULTS_DIR.
#
# Connection env (same as sync-to-bastion.sh): BASTION_VM/ZONE/PROJECT, and
# either default IAP or BASTION_USE_GCPNODE=1 / BASTION_SSH_HOST / BASTION_SSH_USER.
# Run config: GCP_PROJECT_ID (req unless DRY_RUN), GKE_CLUSTER_NAME, GCP_LOCATION,
# AGENT_PROVIDER, JUDGE_PROVIDER, JUDGE_MODEL, MAX_PARALLEL, RESULTS_DIR,
# GKE_MCP_BIN, SKILLS_PATHS, SKIP_SYNC, DRY_RUN, MATRIX_TASKS, MATRIX_MODELS.

BASTION_VM="${BASTION_VM:-bench-bastion}"
BASTION_ZONE="${BASTION_ZONE:-us-central1-a}"
BASTION_PROJECT="${BASTION_PROJECT:-$(gcloud config get-value project 2>/dev/null || true)}"
REMOTE_DIR="${REMOTE_DIR:-devops-bench}"

MATRIX_TASKS="${MATRIX_TASKS:-complextasks/secret-rotation/task.yaml}"
MATRIX_MODELS="${MATRIX_MODELS:-gemini-3.1-pro}"

GKE_CLUSTER_NAME="${GKE_CLUSTER_NAME:-eval}"
GCP_LOCATION="${GCP_LOCATION:-us-central1-a}"
AGENT_PROVIDER="${AGENT_PROVIDER:-google}"
JUDGE_PROVIDER="${JUDGE_PROVIDER:-google}"
JUDGE_MODEL="${JUDGE_MODEL:-gemini-3.1-pro}"
MAX_PARALLEL="${MAX_PARALLEL:-3}"
GKE_MCP_BIN="${GKE_MCP_BIN:-\$HOME/gke-mcp}"     # expanded on the bastion
SKILLS_PATHS="${SKILLS_PATHS:-\$HOME/oc-skills}" # expanded on the bastion
DRY_RUN="${DRY_RUN:-}"

STAMP="$(date +%Y%m%d_%H%M%S)"
# Pulled results land in ${RESULTS_DIR}/${STAMP} (the pull re-creates the
# stamped dir), so the default deliberately omits the stamp.
RESULTS_DIR="${RESULTS_DIR:-results/matrix}"
REMOTE_OUT="matrix-runs/${STAMP}"  # relative to the bastion user's $HOME

_MATRIX_LIB_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${_MATRIX_LIB_DIR}/../.." && pwd)"

# --- SSH transport (mirrors sync-to-bastion.sh) ----------------------------- #
if [ -n "${BASTION_SSH_HOST:-}" ] || [ "${BASTION_USE_GCPNODE:-}" = "1" ]; then
  SSH_HOST="${BASTION_SSH_HOST:-nic0.${BASTION_VM}.${BASTION_ZONE}.c.${BASTION_PROJECT}.internal.gcpnode.com}"
  SSH_USER="${BASTION_SSH_USER:-$(id -un)_google_com}"
  SSH_TARGET="${SSH_USER}@${SSH_HOST}"
  remote_exec() { ssh -o BatchMode=yes "${SSH_TARGET}" "$1"; }
  push_file()   { scp -o BatchMode=yes "$1" "${SSH_TARGET}:$2"; }
  pull_dir()    { scp -o BatchMode=yes -r "${SSH_TARGET}:$1" "$2"; }
else
  remote_exec() { gcloud compute ssh "${BASTION_VM}" --tunnel-through-iap --zone "${BASTION_ZONE}" --project "${BASTION_PROJECT}" --command "$1"; }
  push_file()   { gcloud compute scp --tunnel-through-iap --zone "${BASTION_ZONE}" --project "${BASTION_PROJECT}" "$1" "${BASTION_VM}:$2"; }
  pull_dir()    { gcloud compute scp --tunnel-through-iap --recurse --zone "${BASTION_ZONE}" --project "${BASTION_PROJECT}" "${BASTION_VM}:$1" "$2"; }
fi

sanitize() { echo "$1" | tr '/.+ ' '----' | tr -cd 'A-Za-z0-9_-'; }

# ALL -> enumerate every task.yaml under complextasks/ + tasks/; else the list.
resolve_tasks() {
  if [ "${MATRIX_TASKS}" = "ALL" ]; then
    ( cd "${REPO_ROOT}" && find complextasks tasks -name task.yaml 2>/dev/null | sort )
  else
    printf '%s\n' ${MATRIX_TASKS}
  fi
}

# Run the COMBOS matrix. Arg: a human label for logging.
matrix_dispatch() {
  local label="$1"
  echo "==> ${label} matrix: ${#COMBOS[@]} combo(s), MAX_PARALLEL=${MAX_PARALLEL}"
  printf '    %s\n' "${COMBOS[@]%%|*}"

  if [ -n "${DRY_RUN}" ]; then
    echo "==> DRY_RUN: per-combo env (not executing):"
    local c rid task kvs arm
    for c in "${COMBOS[@]}"; do
      IFS='|' read -r rid task kvs arm <<<"$c"
      echo "  [${rid}] arm=${arm} task=${task}"
      echo "      ${kvs}"
    done
    echo "==> DRY_RUN: results would land in ${RESULTS_DIR}/${STAMP}"
    return 0
  fi

  [ "${#COMBOS[@]}" -gt 0 ] || { echo "ERROR: empty matrix" >&2; exit 2; }
  [ -n "${GCP_PROJECT_ID:-}" ] || { echo "ERROR: set GCP_PROJECT_ID" >&2; exit 2; }

  if [ -z "${SKIP_SYNC:-}" ]; then
    echo "==> syncing working tree to ${BASTION_VM}"
    "${REPO_ROOT}/scripts/bastion/sync-to-bastion.sh"
  fi

  local runner; runner="$(mktemp -t matrix-runner-XXXXXX.sh)"
  trap 'rm -f "${runner}"' RETURN
  {
    echo '#!/usr/bin/env bash'
    echo 'set -uo pipefail'
    echo "cd ~/${REMOTE_DIR}"
    echo 'source .venv/bin/activate'
    echo 'set -a; . ~/secrets.env; set +a'
    echo "OUT=\"\$HOME/${REMOTE_OUT}\"; mkdir -p \"\$OUT\""
    echo "export GCP_PROJECT_ID='${GCP_PROJECT_ID}' GKE_CLUSTER_NAME='${GKE_CLUSTER_NAME}' GCP_LOCATION='${GCP_LOCATION}'"
    echo "export AGENT_PROVIDER='${AGENT_PROVIDER}' JUDGE_PROVIDER='${JUDGE_PROVIDER}' JUDGE_MODEL='${JUDGE_MODEL}'"
    echo "export BENCH_PARALLEL=true"
    echo 'run_one() {'
    echo '  local rid="$1" task="$2" kvs="$3" arm="$4" kv rc rdir'
    echo '  local d="$OUT/$rid"; mkdir -p "$d"'
    echo '  ('
    echo '    export RUN_ID="$rid"'
    echo '    # eval so values like AGENT_MCP_SERVER=$HOME/gke-mcp expand on the bastion'
    echo '    IFS=";"; for kv in $kvs; do eval "export ${kv}"; done'
    echo '    if [ "$arm" = "legacy" ]; then'
    echo '      python3 pkg/evaluator/evaluate.py "$task"; rc=$?'
    echo '      # legacy writes results/run_<ts>_<rid>; copy it into the combo dir'
    echo '      rdir="$(ls -dt results/run_*_"$rid" 2>/dev/null | head -1)"'
    echo '      [ -n "$rdir" ] && cp -a "$rdir/." "$d/" 2>/dev/null || true'
    echo '    else'
    echo '      python3 -m devops_bench --parallel --run-id "$rid" \'
    echo '        --project "$GCP_PROJECT_ID" --cluster "$GKE_CLUSTER_NAME" \'
    echo '        --results-root "$d" "$task"; rc=$?'
    echo '    fi'
    echo '    echo "exit=$rc" >"$d/status"'
    echo '  ) >"$d/run.log" 2>&1'
    echo '}'
    echo "SEM=${MAX_PARALLEL}"
    local c rid task kvs arm
    for c in "${COMBOS[@]}"; do
      IFS='|' read -r rid task kvs arm <<<"$c"
      printf 'run_one %q %q %q %q &\n' "$rid" "$task" "$kvs" "$arm"
      echo 'while [ "$(jobs -r | wc -l)" -ge "$SEM" ]; do wait -n; done'
    done
    echo 'wait'
    echo "echo ALL_DONE >\"\$HOME/${REMOTE_OUT}/.done\""
  } >"${runner}"

  echo "==> uploading + launching remote runner (detached)"
  push_file "${runner}" "/tmp/matrix-runner.sh"
  remote_exec "chmod +x /tmp/matrix-runner.sh; nohup /tmp/matrix-runner.sh >\$HOME/${REMOTE_OUT}.out 2>&1 & echo launched pid=\$!"

  echo "==> waiting for ${#COMBOS[@]} run(s) (poll 60s; runs continue on the bastion if this exits)"
  while true; do
    if remote_exec "test -f \$HOME/${REMOTE_OUT}/.done" 2>/dev/null; then break; fi
    local done_n
    done_n="$(remote_exec "ls \$HOME/${REMOTE_OUT}/*/status 2>/dev/null | wc -l" 2>/dev/null | tr -d '[:space:]' || echo 0)"
    echo "    ${done_n}/${#COMBOS[@]} finished... ($(date +%H:%M:%S))"
    sleep 60
  done

  mkdir -p "${RESULTS_DIR}"
  echo "==> pulling results -> ${RESULTS_DIR}/${STAMP}"
  pull_dir "${REMOTE_OUT}" "${RESULTS_DIR}"
  local LOCAL_OUT="${RESULTS_DIR}/${STAMP}"

  echo "==> summary"
  printf '%-56s %-8s %s\n' "COMBO" "EXIT" "results.json"
  local c rid st rj
  for c in "${COMBOS[@]}"; do
    rid="${c%%|*}"
    st="$(cat "${LOCAL_OUT}/${rid}/status" 2>/dev/null || echo '?')"
    rj="$(find "${LOCAL_OUT}/${rid}" -name results.json 2>/dev/null | head -1)"
    printf '%-56s %-8s %s\n' "${rid}" "${st}" "${rj:-<none>}"
  done
  echo "==> done. results under ${LOCAL_OUT} (each combo provisioned + tore down its own cluster)"
}
