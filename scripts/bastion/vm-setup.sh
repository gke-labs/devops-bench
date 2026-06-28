#!/usr/bin/env bash
#
# Per-user setup, run ONCE on the bastion after the first sync-to-bastion.sh.
#
# The system toolchain (tofu, gcloud, kubectl, node, oc) is already installed by
# the VM startup script. This finishes the user-scoped pieces: a Python venv with
# the harness installed, an openclaw API key, and a ~/bench.env template.
#
# Usage (on the VM):
#   ~/devops-bench/scripts/bastion/vm-setup.sh
set -euo pipefail

REPO_DIR="${REPO_DIR:-${HOME}/devops-bench}"
ENV_FILE="${HOME}/bench.env"

if [ ! -f "${REPO_DIR}/pyproject.toml" ]; then
  echo "ERROR: ${REPO_DIR}/pyproject.toml not found. Run sync-to-bastion.sh from your laptop first." >&2
  exit 1
fi

# Wait for the startup-script toolchain in case the VM only just booted.
if [ ! -f /var/lib/bench-bastion-ready ]; then
  echo "==> waiting for VM startup toolchain (/var/lib/bench-bastion-ready)..."
  for _ in $(seq 1 60); do
    [ -f /var/lib/bench-bastion-ready ] && break
    sleep 5
  done
  # The loop falls through on timeout; fail loudly instead of proceeding
  # against a half-provisioned VM (toolchain not yet installed).
  if [ ! -f /var/lib/bench-bastion-ready ]; then
    echo "ERROR: VM startup toolchain not ready after ~5m; aborting." >&2
    exit 1
  fi
fi

cd "${REPO_DIR}"

echo "==> creating venv + installing the harness (.[all])"
python3 -m venv .venv
# shellcheck disable=SC1091
source .venv/bin/activate
pip install --upgrade pip
pip install ".[all]"

echo "==> openclaw key check"
# The harness does NOT pass an API key to oc; openclaw must hold the agent
# model's key itself. Persist it once with the interactive wizard:
#     openclaw onboard
# or export the provider key (e.g. GEMINI_API_KEY / ANTHROPIC_API_KEY) before
# running the harness. We don't store the key here to keep it off disk in plain
# text beyond openclaw's own config.
if oc models list >/dev/null 2>&1; then
  echo "    oc reachable."
else
  echo "    NOTE: run 'openclaw onboard' to configure the agent model API key."
fi

# Gemini CLI (the 'gemini' agent target for gcli runs). oc is installed
# system-wide by startup.sh; this finishes the other agent CLI. Node's global
# prefix is root-owned, so install with sudo. Idempotent.
echo "==> gemini CLI check"
if command -v gemini >/dev/null 2>&1; then
  echo "    gemini present: $(gemini --version 2>/dev/null | head -1)"
else
  echo "    installing @google/gemini-cli (sudo npm -g)..."
  sudo npm install -g @google/gemini-cli \
    && echo "    gemini installed: $(gemini --version 2>/dev/null | head -1)" \
    || echo "    WARN: gemini CLI install failed; gcli agent runs will not work until it's installed."
fi

# fortio — the load generator the chaos agent shells out to for `generate_load`
# faults (e.g. the optimize-scale load spike). The chaos system instruction tells
# the agent to use the `fortio` binary; without it on PATH the spike is a silent
# no-op (the run can still "pass" via the agent's HPA minReplicas, but the load is
# never actually applied). Install to ~/bin (idempotent).
echo "==> fortio check (chaos load generator)"
if command -v fortio >/dev/null 2>&1; then
  echo "    fortio present: $(fortio version 2>/dev/null | head -1)"
else
  echo "    installing fortio to ~/bin..."
  FORTIO_VERSION="${FORTIO_VERSION:-1.66.4}"
  mkdir -p "${HOME}/bin"
  if curl -fsSL -o /tmp/fortio.tgz \
       "https://github.com/fortio/fortio/releases/download/v${FORTIO_VERSION}/fortio-linux_amd64-${FORTIO_VERSION}.tgz" \
     && tar -xzf /tmp/fortio.tgz -C /tmp 2>/dev/null \
     && cp "$(find /tmp -maxdepth 4 -name fortio -type f 2>/dev/null | head -1)" "${HOME}/bin/fortio" \
     && chmod +x "${HOME}/bin/fortio"; then
    echo "    fortio installed: $("${HOME}/bin/fortio" version 2>/dev/null | head -1)"
    echo "    (ensure ~/bin is on PATH — secrets.env / bench.env exports it for runs)"
  else
    echo "    WARN: fortio install failed; chaos generate_load faults (optimize-scale) will no-op."
  fi
fi

# Disable Gemini CLI folder-trust gating at the USER level. The gcli agent runs
# in a fresh, untrusted per-run temp cwd; untrusted folders have their MCP
# servers (e.g. gke-mcp) suppressed, and a workspace-level setting can't lift it
# (untrusted folders ignore their own settings.json) — nor does the --skip-trust
# flag. Setting it here lets gke-mcp connect for every run. Merge-preserving +
# idempotent.
echo "==> gemini folder-trust (~/.gemini/settings.json: security.folderTrust.enabled=false)"
mkdir -p "${HOME}/.gemini"
python3 - "${HOME}/.gemini/settings.json" <<'PY'
import json, sys
path = sys.argv[1]
try:
    with open(path) as f:
        cfg = json.load(f)
    if not isinstance(cfg, dict):
        cfg = {}
except (FileNotFoundError, ValueError):
    cfg = {}
cfg.setdefault("security", {}).setdefault("folderTrust", {})["enabled"] = False
with open(path, "w") as f:
    json.dump(cfg, f, indent=2)
print(f"    wrote {path}")
PY

if [ ! -f "${ENV_FILE}" ]; then
  echo "==> writing ${ENV_FILE} template (fill in values, then 'source ~/bench.env')"
  cat > "${ENV_FILE}" <<'EOF'
# DevOps Bench harness environment. Fill in, then: source ~/bench.env
# --- GCP target ---
export GCP_PROJECT_ID=""
export GKE_CLUSTER_NAME="secret-rotation-cluster"
export GCP_LOCATION="us-central1-a"
export NAMESPACE="secret-rotation-run-1"

# --- Agent (openclaw / oc) ---
export BENCH_AGENT_TYPE="cli"
export AGENT_TARGET="oc"
export AGENT_PROVIDER="google"
export AGENT_MODEL="gemini-3.1-pro-preview"
# Agent model key: prefer 'openclaw onboard'. If your provider reads an env key,
# set it here too (e.g. GEMINI_API_KEY / ANTHROPIC_API_KEY).
# export GEMINI_API_KEY=""

# --- Judge ---
export JUDGE_PROVIDER="google"
export JUDGE_MODEL="gemini-3.1-pro-preview"
export JUDGE_API_KEY=""
EOF
else
  echo "==> ${ENV_FILE} already exists; leaving it untouched"
fi

echo ""
echo "==> setup complete. To run the secret-rotation eval:"
echo "    source ~/bench.env   # after filling in project + keys"
echo "    cd ${REPO_DIR} && source .venv/bin/activate"
echo "    devops-bench complextasks/secret-rotation/task.yaml"
