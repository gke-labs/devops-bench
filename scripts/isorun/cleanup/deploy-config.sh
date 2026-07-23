#!/usr/bin/env bash
# Pre-run reset for tasks/gcp/deploy-config. Idempotent: safe to run when
# nothing exists.
set -euo pipefail

: "${CLUSTER:=autopilot-cluster-1}"
: "${PROJECT:=}"
: "${REGION:=us-central1}"
: "${NAMESPACE:=default}"

# Uses $NAMESPACE (not a hardcoded literal) so this cleanup step, the seed's
# own reset, and the preflight's namespace-match check all target the same
# namespace end to end; see preflight/deploy-config.sh for why any value
# other than "default" is refused before the agent runs.
echo "==> deploy-config cleanup: deleting hypercomputer-d1-vllm-server deploy/svc/hpa in namespace '$NAMESPACE' (cluster: $CLUSTER)"
kubectl -n "$NAMESPACE" delete deploy/hypercomputer-d1-vllm-server svc/hypercomputer-d1-vllm-service hpa/hypercomputer-d1-vllm-hpa --ignore-not-found
