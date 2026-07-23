#!/usr/bin/env bash
# Pre-run reset for tasks/common/optimize-scale. Idempotent: safe to run when
# nothing exists.
set -euo pipefail

: "${CLUSTER:=autopilot-cluster-1}"
: "${PROJECT:=}"
: "${REGION:=us-central1}"

NS="${NAMESPACE:-default}"

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=scripts/isorun/_guards.sh
source "$SCRIPT_DIR/../_guards.sh"

# scale-target is the {{TARGET_DEPLOYMENT_NAME}} default. The HPA sweep must
# match preflight/optimize-scale.sh's assertion scope exactly: that preflight
# asserts ZERO HorizontalPodAutoscalers namespace-wide, so an agent-created
# HPA under an unrelated name would otherwise survive this cleanup and
# permanently wedge every later run. "default" is skipped by the
# protected-namespace guard here because it is this task's own, legitimate
# namespace; the guard still refuses a stray NAMESPACE pointed at
# kube-system/kube-public/kube-node-lease before the namespace-wide HPA
# sweep runs.
echo "==> optimize-scale cleanup: deleting scale-target deploy/svc, and all HPAs, in namespace '$NS' (cluster: $CLUSTER)"
if [[ "$NS" != "default" ]]; then
  iso_refuse_protected_namespace "$NS"
fi
kubectl -n "$NS" delete deploy/scale-target svc/scale-target --ignore-not-found
kubectl -n "$NS" delete hpa --all --ignore-not-found
