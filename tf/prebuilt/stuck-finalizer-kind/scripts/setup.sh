#!/usr/bin/env bash
#
# Setup for the stuck-finalizer task. Runs from OUTSIDE the cluster during
# `tofu apply`, before the agent starts:
#   1. installs a trivial CRD (no controller ever watches it),
#   2. creates the target namespace and a custom resource inside it carrying a
#      finalizer that nothing will ever remove,
#   3. deletes the namespace (non-blocking) so it gets stuck in Terminating -
#      the underlying custom resource can never finish finalizing, so neither
#      can the namespace,
#   4. seeds the gke_<project>_<location>_<cluster> kubeconfig context the GKE
#      MCP server's k8s tools require (they resolve that literal context name
#      derived from the tool-call args, never the cluster's own kind context).
#
# Nothing here tells the agent what is wrong - it must discover the stuck
# resource and its finalizer itself.
set -euo pipefail

export KUBECONFIG="${KUBECONFIG:-$HOME/.kube/config}"
CLUSTER_NAME="${CLUSTER_NAME:?CLUSTER_NAME is required}"
PROJECT_ID="${PROJECT_ID:?PROJECT_ID is required}"
LOCATION="${LOCATION:?LOCATION is required}"
NAMESPACE="${NAMESPACE:?NAMESPACE is required}"
MANIFEST_DIR="${MANIFEST_DIR:?MANIFEST_DIR is required}"
MANIFEST_DIR="$(cd "${MANIFEST_DIR}" && pwd)"
KIND_CONTEXT="kind-${CLUSTER_NAME}"
GKE_CONTEXT="gke_${PROJECT_ID}_${LOCATION}_${CLUSTER_NAME}"

echo "==> Installing the SlowResource CRD..."
kubectl --context "${KIND_CONTEXT}" apply -f "${MANIFEST_DIR}/crd.yaml"
kubectl --context "${KIND_CONTEXT}" wait --for=condition=established --timeout=60s \
  crd/slowresources.example.com

echo "==> Creating namespace '${NAMESPACE}' and a stuck SlowResource in it..."
kubectl --context "${KIND_CONTEXT}" create namespace "${NAMESPACE}"
cat <<EOF | kubectl --context "${KIND_CONTEXT}" apply -f -
apiVersion: example.com/v1
kind: SlowResource
metadata:
  name: legacy-billing-job
  namespace: ${NAMESPACE}
  finalizers:
    - example.com/cleanup-never-runs
spec:
  note: "fixture for the stuck-finalizer task; no controller ever clears this finalizer"
EOF

echo "==> Deleting namespace '${NAMESPACE}' (will hang in Terminating)..."
kubectl --context "${KIND_CONTEXT}" delete namespace "${NAMESPACE}" --wait=false

echo "==> Seeding kubeconfig context '${GKE_CONTEXT}' for the GKE MCP server..."
SERVER="$(kubectl config view -o jsonpath="{.clusters[?(@.name==\"${KIND_CONTEXT}\")].cluster.server}")"
CA_DATA="$(kubectl config view --raw -o jsonpath="{.clusters[?(@.name==\"${KIND_CONTEXT}\")].cluster.certificate-authority-data}")"
CERT_DATA="$(kubectl config view --raw -o jsonpath="{.users[?(@.name==\"${KIND_CONTEXT}\")].user.client-certificate-data}")"
KEY_DATA="$(kubectl config view --raw -o jsonpath="{.users[?(@.name==\"${KIND_CONTEXT}\")].user.client-key-data}")"

CERT_FILE="$(mktemp)"
KEY_FILE="$(mktemp)"
echo "${CERT_DATA}" | base64 -d > "${CERT_FILE}"
echo "${KEY_DATA}" | base64 -d > "${KEY_FILE}"

kubectl config set-cluster "${GKE_CONTEXT}" --server="${SERVER}" --insecure-skip-tls-verify=true >/dev/null
kubectl config set-credentials "${GKE_CONTEXT}" --client-certificate="${CERT_FILE}" --client-key="${KEY_FILE}" --embed-certs=true >/dev/null
kubectl config set-context "${GKE_CONTEXT}" --cluster="${GKE_CONTEXT}" --user="${GKE_CONTEXT}" --namespace="${NAMESPACE}" >/dev/null
rm -f "${CERT_FILE}" "${KEY_FILE}"
# Avoid CA_DATA unused-var lint; kept for documentation of what's available.
: "${CA_DATA}"

echo "==> Setup complete."
echo "    Namespace status: kubectl --context ${GKE_CONTEXT} get namespace ${NAMESPACE} -o yaml"
