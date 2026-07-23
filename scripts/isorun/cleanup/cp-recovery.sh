#!/usr/bin/env bash
# Pre-run reset for tasks/kind/cp-recovery. Idempotent: safe to run when the
# namespace doesn't exist.
set -euo pipefail

: "${CLUSTER:=autopilot-cluster-1}"
: "${PROJECT:=}"
: "${REGION:=us-central1}"

NS="${NAMESPACE:-cp-recovery}"

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=scripts/isorun/_guards.sh
source "$SCRIPT_DIR/../_guards.sh"
iso_refuse_protected_namespace "$NS"

echo "==> cp-recovery cleanup: deleting namespace '$NS' (cluster: $CLUSTER)"
kubectl delete namespace "$NS" --ignore-not-found --wait=true --timeout=120s

# kind-internal backup files are removed with the cluster; nothing else
# host-side needs cleaning up.
