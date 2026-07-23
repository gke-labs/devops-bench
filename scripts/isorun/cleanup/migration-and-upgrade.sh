#!/usr/bin/env bash
# Pre-run reset for tasks/common/migration-and-upgrade. Idempotent: safe to
# run when nothing exists.
set -euo pipefail

: "${CLUSTER:=autopilot-cluster-1}"
: "${PROJECT:=}"
: "${REGION:=us-central1}"

NS="${NAMESPACE:-migration}"

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=scripts/isorun/_guards.sh
source "$SCRIPT_DIR/../_guards.sh"
iso_refuse_protected_namespace "$NS"

echo "==> migration-and-upgrade cleanup: deleting namespace '$NS' (cluster: $CLUSTER)"
kubectl delete namespace "$NS" --ignore-not-found --wait=true --timeout=120s

# ~/migration-repo-$CLUSTER.git is NOT tofu-cleaned, so it must be removed
# here for a clean reseed.
echo "==> migration-and-upgrade cleanup: removing $HOME/migration-repo-$CLUSTER.git"
rm -rf "${HOME:?}/migration-repo-$CLUSTER.git"

# Sweep stray temp validation kind clusters left over from a prior run
# (the task spins up a target-version cluster named off $CLUSTER).
if command -v kind >/dev/null 2>&1; then
  while IFS= read -r c; do
    [[ -z "$c" ]] && continue
    echo "==> migration-and-upgrade cleanup: deleting stray validation kind cluster '$c'"
    kind delete cluster --name "$c"
  done < <(kind get clusters 2>/dev/null | grep -F "$CLUSTER" | grep -v -x "$CLUSTER" || true)
else
  echo "==> migration-and-upgrade cleanup: kind not installed; skipping stray-cluster sweep"
fi
