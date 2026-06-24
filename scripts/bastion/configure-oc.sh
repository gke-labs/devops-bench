#!/usr/bin/env bash
#
# Configure the GLOBAL ~/.openclaw config for a run mode, on the bastion.
#
# Why this is separate from vm-setup.sh: only the LEGACY arm reads the global oc
# config — the refactored arm wires MCP/skills per-run via env
# (AGENT_MCP_SERVER / AGENT_SKILLS_PATHS / BENCH_USE_MCP). Keeping this out of
# the one-time setup means MCP/skills are a per-run-mode choice: run this with
# --mcp/--skills before a legacy "with capabilities" run, or with --no-mcp /
# --no-skills (or just don't run it) for a clean "no capabilities" run.
#
# Idempotent. Also stores the agent model API key in oc (from ~/secrets.env), so
# both arms authenticate without baking the key into oc during provisioning.
#
# Usage:
#   scripts/bastion/configure-oc.sh [--mcp|--no-mcp] [--skills|--no-skills]
#
# Env overrides:
#   GKE_MCP_BIN   path to the gke-mcp binary   (default: ~/gke-mcp)
#   SECRETS_ENV   file exporting GEMINI_API_KEY (default: ~/secrets.env)
#   SKILLS_SRC    dir of skill markdowns        (default: ~/devops-bench/skills)
#   OC_SKILLS_DIR staging dir for <name>/SKILL.md (default: ~/oc-skills)
set -euo pipefail

WANT_MCP=1
WANT_SKILLS=1
GKE_MCP_BIN="${GKE_MCP_BIN:-${HOME}/gke-mcp}"
SECRETS_ENV="${SECRETS_ENV:-${HOME}/secrets.env}"
SKILLS_SRC="${SKILLS_SRC:-${HOME}/devops-bench/skills}"
OC_SKILLS_DIR="${OC_SKILLS_DIR:-${HOME}/oc-skills}"

while [ $# -gt 0 ]; do
  case "$1" in
    --mcp) WANT_MCP=1 ;;
    --no-mcp) WANT_MCP=0 ;;
    --skills) WANT_SKILLS=1 ;;
    --no-skills) WANT_SKILLS=0 ;;
    -h|--help) grep '^#' "$0" | sed 's/^# \{0,1\}//'; exit 0 ;;
    *) echo "unknown arg: $1" >&2; exit 2 ;;
  esac
  shift
done

command -v oc >/dev/null 2>&1 || { echo "ERROR: oc not on PATH" >&2; exit 1; }

# --- 1. Agent model API key -> oc auth (idempotent) ------------------------- #
if [ -f "${SECRETS_ENV}" ]; then
  # shellcheck disable=SC1090
  . "${SECRETS_ENV}"
  KEY="${GEMINI_API_KEY:-${GOOGLE_API_KEY:-}}"
  if [ -n "${KEY}" ]; then
    printf '%s\n' "${KEY}" | oc models auth paste-api-key --provider google >/dev/null \
      && echo "==> oc model auth set (google)"
  else
    echo "==> WARN: no GEMINI_API_KEY/GOOGLE_API_KEY in ${SECRETS_ENV}; skipping oc auth"
  fi
else
  echo "==> WARN: ${SECRETS_ENV} not found; skipping oc auth"
fi

# --- 2. GKE MCP server ------------------------------------------------------ #
oc mcp unset gke-mcp >/dev/null 2>&1 || true   # idempotent: clear any prior entry
if [ "${WANT_MCP}" = "1" ]; then
  [ -x "${GKE_MCP_BIN}" ] || { echo "ERROR: gke-mcp not executable at ${GKE_MCP_BIN}" >&2; exit 1; }
  oc mcp add gke-mcp --command "${GKE_MCP_BIN}" --no-probe >/dev/null
  echo "==> gke-mcp registered (global oc config)"
else
  echo "==> gke-mcp NOT registered (--no-mcp)"
fi

# --- 3. Skills (reshape *.md -> <name>/SKILL.md, install --global) ---------- #
managed_skills_dir="${HOME}/.openclaw/skills"
if [ "${WANT_SKILLS}" = "1" ]; then
  [ -d "${SKILLS_SRC}" ] || { echo "ERROR: skills source ${SKILLS_SRC} not found" >&2; exit 1; }
  mkdir -p "${OC_SKILLS_DIR}"
  for f in "${SKILLS_SRC}"/*.md; do
    [ -f "$f" ] || continue
    name="$(awk -F': ' '/^name:/{print $2; exit}' "$f" | tr -d '\r')"
    [ -n "${name}" ] || name="$(basename "$f" .md)"
    mkdir -p "${OC_SKILLS_DIR}/${name}"
    cp "$f" "${OC_SKILLS_DIR}/${name}/SKILL.md"
    oc skills install "${OC_SKILLS_DIR}/${name}" --global --force >/dev/null
    echo "==> skill installed: ${name}"
  done
else
  # Remove any skills this script previously installed, leaving oc's bundled ones.
  if [ -d "${OC_SKILLS_DIR}" ]; then
    for d in "${OC_SKILLS_DIR}"/*/; do
      [ -d "$d" ] || continue
      rm -rf "${managed_skills_dir}/$(basename "$d")"
    done
  fi
  echo "==> skills NOT installed (--no-skills)"
fi

echo "==> oc configured (mcp=${WANT_MCP} skills=${WANT_SKILLS}). 'oc mcp list' / 'oc skills list' to verify."
