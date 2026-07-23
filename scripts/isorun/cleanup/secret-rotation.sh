#!/usr/bin/env bash
# Pre-run reset for tasks/gcp/secret-rotation. Idempotent: safe to run when
# the namespace doesn't exist.
set -euo pipefail

: "${CLUSTER:=autopilot-cluster-1}"
: "${PROJECT:=}"
: "${REGION:=us-central1}"

NS="${NAMESPACE:-secret-rotation}"

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=scripts/isorun/_guards.sh
source "$SCRIPT_DIR/../_guards.sh"
iso_refuse_protected_namespace "$NS"

echo "==> secret-rotation cleanup: deleting namespace '$NS' (cluster: $CLUSTER)"
kubectl delete namespace "$NS" --ignore-not-found --wait=true --timeout=120s

# The Secret Manager secret + GSA are tofu-managed (random-suffixed), so they
# are swept by tofu destroy, not here.
