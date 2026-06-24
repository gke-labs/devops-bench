#!/usr/bin/env bash
#
# Parallel eval matrix on the bastion — LEGACY arm (pkg/evaluator/evaluate.py).
# Dimensions: Task x Model ONLY (no AgentConfig — the legacy arm reads MCP/skills
# from the GLOBAL ~/.openclaw config, so capabilities are fixed for the whole
# matrix; set them once with scripts/bastion/configure-oc.sh).
#
# This is a thin, throwaway companion to run_matrix.sh (the refactored matrix);
# delete it when the legacy arm is retired — the shared _matrix_lib.sh stays.
#
# CUJs supported: one task x many models, and all tasks x one model. E.g.:
#   MATRIX_TASKS="complextasks/secret-rotation/task.yaml" \
#   MATRIX_MODELS="gemini-3.1-pro gemini-3.5-flash" \
#   GCP_PROJECT_ID=<proj> run_matrix_legacy.sh
#
#   MATRIX_TASKS=ALL MATRIX_MODELS="gemini-3.1-pro" GCP_PROJECT_ID=<proj> run_matrix_legacy.sh
#
# Prereq: run `scripts/bastion/configure-oc.sh --mcp --skills` (or --no-*) once
# to set the global oc config the legacy arm uses. DRY_RUN=1 previews the matrix.
set -euo pipefail

# shellcheck source=scripts/bastion/_matrix_lib.sh
source "$(dirname "${BASH_SOURCE[0]}")/_matrix_lib.sh"

# Legacy openclaw (local) env — fixed; capabilities come from the global oc config.
LEGACY_KVS="BENCH_AGENT_TYPE=cli;AGENT_TARGET=oc;OPENCLAW_BIN=oc;OPENCLAW_LOCAL=true;OPENCLAW_AGENT=main"

COMBOS=()
while IFS= read -r task; do
  [ -n "${task}" ] || continue
  tname="$(basename "$(dirname "${task}")")"
  for model in ${MATRIX_MODELS}; do
    kvs="AGENT_MODEL=${model};AGENT_PROVIDER=${AGENT_PROVIDER};${LEGACY_KVS}"
    rid="$(sanitize "${tname}")__$(sanitize "${model}")__legacy"
    COMBOS+=("${rid}|${task}|${kvs}|legacy")
  done
done < <(resolve_tasks)

matrix_dispatch "legacy (Task x Model)"
