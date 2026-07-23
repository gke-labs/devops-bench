#!/usr/bin/env bash
# Pre-run reset for tasks/common/spot-rebalancing. Idempotent: safe to run
# when the namespace doesn't exist.
set -euo pipefail

: "${CLUSTER:=autopilot-cluster-1}"
: "${PROJECT:=}"
: "${REGION:=us-central1}"
: "${NAMESPACE:=apps}"

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=scripts/isorun/_guards.sh
source "$SCRIPT_DIR/../_guards.sh"
iso_refuse_protected_namespace apps

echo "==> spot-rebalancing cleanup: deleting namespace 'apps' (cluster: $CLUSTER)"
kubectl delete namespace apps --ignore-not-found --wait=true --timeout=120s
