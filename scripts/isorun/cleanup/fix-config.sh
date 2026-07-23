#!/usr/bin/env bash
# Pre-run reset for tasks/gcp/fix-config. Idempotent: safe to run when the
# deployment doesn't exist.
set -euo pipefail

: "${CLUSTER:=autopilot-cluster-1}"
: "${PROJECT:=}"
: "${REGION:=us-central1}"
: "${NAMESPACE:=default}"

# The tofu seed re-creates this deployment (broken) under --infra; under
# --no-infra reuse of an ambient cluster, deleting it resets the fixture.
# Uses $NAMESPACE (not a hardcoded literal) so this cleanup step, the seed's
# own reset, and the preflight's namespace-match check all target the same
# namespace end to end; see preflight/fix-config.sh for why any value other
# than "default" is refused before the agent runs.
echo "==> fix-config cleanup: deleting deploy/hypercomputer-d1-frontend in namespace '$NAMESPACE' (cluster: $CLUSTER)"
kubectl -n "$NAMESPACE" delete deploy/hypercomputer-d1-frontend --ignore-not-found
