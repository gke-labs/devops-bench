#!/usr/bin/env bash
# Seed hook for tasks/common/optimize-scale: reset, then re-apply the
# unsized, unscaled fixture, for fast local iteration against an
# already-standing cluster (no tofu, no cluster build).
#
# Fixture: scripts/isorun/fixtures/optimize-scale.yaml. See that file's
# header for the full derivation (tf/prebuilt/optimize-scale) and the
# GKE Autopilot false-pass warning: if you're on Autopilot, the preflight
# guard in scripts/isorun/preflight/optimize-scale.sh will catch it and
# abort rather than let a false pass through.
#
# The fixture hardcodes the name "scale-target" (matching
# var.target_deployment_name's default, which the matrix orchestrator also
# always exports for this task). If TARGET_DEPLOYMENT_NAME is set to
# something else, this script's reset targets that name but the fixture
# still creates "scale-target"; update the fixture by hand if you need a
# different name.
#
# Idempotent: safe to run repeatedly. Uses kubectl apply, never create.
set -euo pipefail

: "${CLUSTER:=autopilot-cluster-1}"
: "${PROJECT:=}"
: "${REGION:=us-central1}"
: "${NAMESPACE:=default}"
TARGET="${TARGET_DEPLOYMENT_NAME:-scale-target}"

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=scripts/isorun/_guards.sh
source "$SCRIPT_DIR/../_guards.sh"
FIXTURE="$SCRIPT_DIR/../fixtures/optimize-scale.yaml"

# (a) RESET: remove whatever a previous agent run left behind. The HPA sweep
# must match preflight/optimize-scale.sh's assertion scope exactly: that
# preflight asserts ZERO HorizontalPodAutoscalers namespace-wide, so an
# agent-created HPA under an unrelated name/label would otherwise survive
# this reset and permanently wedge every later run. "default" is skipped by
# the protected-namespace guard here because it is this task's own,
# legitimate namespace (see task.yaml's namespace variable); the guard still
# refuses a stray NAMESPACE pointed at kube-system/kube-public/kube-node-lease
# before the namespace-wide HPA sweep runs.
echo "==> optimize-scale seed: RESET (cluster: $CLUSTER, namespace: $NAMESPACE)"
if [[ "$NAMESPACE" != "default" ]]; then
  iso_refuse_protected_namespace "$NAMESPACE"
fi
kubectl -n "$NAMESPACE" delete "deploy/$TARGET" "svc/$TARGET" --ignore-not-found
kubectl -n "$NAMESPACE" delete hpa --all --ignore-not-found

# (b) SEED: apply the fixture so the unsized, unscaled pre-state exists. The
# fixture hardcodes namespace: default, so it is applied without -n to avoid
# a namespace-mismatch error if NAMESPACE differs.
echo "==> optimize-scale seed: SEED (apply $FIXTURE)"
kubectl apply -f "$FIXTURE"

echo "==> optimize-scale seed: done. deployment/scale-target at replicas=1, no resources block, no HPA."
