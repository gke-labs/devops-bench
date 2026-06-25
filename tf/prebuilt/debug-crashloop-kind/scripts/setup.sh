#!/usr/bin/env bash
#
# Setup for the debug-crashloop task. Runs from OUTSIDE the cluster during
# `tofu apply`, before the agent starts: applies the deliberately-broken
# 'frontend' deployment so the agent has a real CrashLoopBackOff to investigate.
# Without this the cluster is healthy and the task is unsolvable.
set -euo pipefail

export KUBECONFIG="${KUBECONFIG:-$HOME/.kube/config}"
NAMESPACE="${NAMESPACE:-default}"
MANIFESTS_DIR="${MANIFESTS_DIR:?MANIFESTS_DIR is required}"
MANIFESTS_DIR="$(cd "${MANIFESTS_DIR}" && pwd)"

echo "==> ensuring namespace ${NAMESPACE}"
kubectl create namespace "${NAMESPACE}" --dry-run=client -o yaml | kubectl apply -f -

echo "==> applying broken 'frontend' fixture to ${NAMESPACE}"
kubectl -n "${NAMESPACE}" apply -f "${MANIFESTS_DIR}/frontend-crashloop.yaml"
