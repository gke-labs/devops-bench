#!/usr/bin/env bash
#
# Setup for the broken-webhook task. Runs from OUTSIDE the cluster during
# `tofu apply`, before the agent starts:
#   1. creates the target namespace (labeled so the webhook can scope to it)
#      and deploys a healthy workload in it,
#   2. installs a defunct ValidatingWebhookConfiguration (unreachable backend
#      service, failurePolicy: Fail) scoped to that namespace,
#   3. deletes the running pod so its ReplicaSet's attempt to recreate it hits
#      the broken webhook and fails admission - producing a real, observable
#      failure in the cluster's events/status,
#   4. seeds the gke_<project>_<location>_<cluster> kubeconfig context the GKE
#      MCP server's k8s tools require (they resolve that literal context name
#      derived from the tool-call args, never the cluster's own kind context).
#
# Nothing here tells the agent what is wrong - it must discover the offending
# webhook itself.
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

echo "==> Creating namespace '${NAMESPACE}' and the checkout-api workload..."
kubectl --context "${KIND_CONTEXT}" create namespace "${NAMESPACE}"
kubectl --context "${KIND_CONTEXT}" label namespace "${NAMESPACE}" env=checkout
kubectl --context "${KIND_CONTEXT}" apply -f "${MANIFEST_DIR}/deployment.yaml"
kubectl --context "${KIND_CONTEXT}" -n "${NAMESPACE}" rollout status deployment/checkout-api --timeout=120s

echo "==> Installing the defunct ValidatingWebhookConfiguration..."
kubectl --context "${KIND_CONTEXT}" apply -f "${MANIFEST_DIR}/webhook.yaml"

echo "==> Deleting the running pod so its replacement hits the broken webhook..."
kubectl --context "${KIND_CONTEXT}" -n "${NAMESPACE}" delete pod -l app=checkout-api --wait=false

echo "==> Waiting for the pod-creation failure to surface in events..."
for _ in $(seq 1 24); do
  if kubectl --context "${KIND_CONTEXT}" -n "${NAMESPACE}" get events \
       --field-selector reason=FailedCreate -o name 2>/dev/null | grep -q .; then
    echo "    FailedCreate event present."
    break
  fi
  sleep 5
done

echo "==> Seeding kubeconfig context '${GKE_CONTEXT}' for the GKE MCP server..."
SERVER="$(kubectl config view -o jsonpath="{.clusters[?(@.name==\"${KIND_CONTEXT}\")].cluster.server}")"
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

echo "==> Setup complete."
echo "    Deployment status: kubectl --context ${GKE_CONTEXT} -n ${NAMESPACE} get deploy,events"
