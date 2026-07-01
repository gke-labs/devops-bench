#!/usr/bin/env bash
#
# Setup for the greenops-consolidation task. Runs from OUTSIDE the cluster during
# `tofu apply`, before the agent starts:
#   1. deploys a lightly-loaded fleet across the multi-node kind cluster. With
#      four empty workers at bring-up the scheduler spreads the workloads roughly
#      one-per-node, so every worker carries a little load — the underutilized,
#      energy-wasteful "before" state the agent must consolidate,
#   2. waits for the fleet to become Available so the agent starts healthy.
#
# The kubectl apply isn't expressible as plan-time-safe declarative TF (kind has
# no cluster at plan time); the carbon report is delivered declaratively by a
# local_file resource in main.tf, not here.
#
# Nothing here tells the agent which nodes to drain or how far to consolidate — it
# must read the report, inspect node utilization and the workloads' scheduling
# constraints, and decide itself.
set -euo pipefail

export KUBECONFIG="${KUBECONFIG:-$HOME/.kube/config}"
MANIFESTS_DIR="${MANIFESTS_DIR:?MANIFESTS_DIR is required}"
MANIFESTS_DIR="$(cd "${MANIFESTS_DIR}" && pwd)"

echo "==> Deploying the workload fleet across the worker nodes..."
kubectl apply -f "${MANIFESTS_DIR}/workloads/"

echo "==> Waiting for the fleet to become Available..."
# Start the agent from a healthy fleet so any unavailability during consolidation
# is the agent's doing, not a flaky fixture.
kubectl -n workloads wait --for=condition=Available deploy --all --timeout=300s

echo "==> Setup complete."
echo "    Node utilization:   kubectl get nodes ; kubectl top nodes (if metrics available)"
echo "    Pod placement:      kubectl -n workloads get pods -o wide"
