#!/usr/bin/env bash
#
# Setup for the coredns-loop task. Runs from OUTSIDE the cluster during
# `tofu apply`, before the agent starts:
#   1. reads the live CoreDNS Corefile and appends a server block that
#      forwards a zone back to the cluster's own kube-dns Service IP,
#   2. re-applies the ConfigMap and restarts CoreDNS so it picks up the
#      change - CoreDNS's built-in "loop" plugin detects the self-referencing
#      query and calls log.Fatal, crash-looping every CoreDNS pod cluster-wide,
#   3. seeds the gke_<project>_<location>_<cluster> kubeconfig context the GKE
#      MCP server's k8s tools require (they resolve that literal context name
#      derived from the tool-call args, never the cluster's own kind context).
#
# Nothing here tells the agent what is wrong - it must read the CoreDNS logs
# and ConfigMap itself to find the self-referencing forward.
set -euo pipefail

export KUBECONFIG="${KUBECONFIG:-$HOME/.kube/config}"
CLUSTER_NAME="${CLUSTER_NAME:?CLUSTER_NAME is required}"
PROJECT_ID="${PROJECT_ID:?PROJECT_ID is required}"
LOCATION="${LOCATION:?LOCATION is required}"
KIND_CONTEXT="kind-${CLUSTER_NAME}"
GKE_CONTEXT="gke_${PROJECT_ID}_${LOCATION}_${CLUSTER_NAME}"

echo "==> Reading the live CoreDNS Corefile and kube-dns Service IP..."
KUBE_DNS_IP="$(kubectl --context "${KIND_CONTEXT}" -n kube-system get svc kube-dns -o jsonpath='{.spec.clusterIP}')"
ORIGINAL_COREFILE="$(kubectl --context "${KIND_CONTEXT}" -n kube-system get configmap coredns -o jsonpath='{.data.Corefile}')"

echo "==> Appending a self-referencing forward zone (loop via ${KUBE_DNS_IP})..."
NEW_COREFILE_FILE="$(mktemp)"
{
  printf '%s\n' "${ORIGINAL_COREFILE}"
  printf 'internal.example.com:53 {\n    forward . %s\n    loop\n}\n' "${KUBE_DNS_IP}"
} > "${NEW_COREFILE_FILE}"

kubectl --context "${KIND_CONTEXT}" -n kube-system create configmap coredns \
  --from-file=Corefile="${NEW_COREFILE_FILE}" --dry-run=client -o yaml \
  | kubectl --context "${KIND_CONTEXT}" apply -f -
rm -f "${NEW_COREFILE_FILE}"

echo "==> Restarting CoreDNS so it picks up the loop..."
kubectl --context "${KIND_CONTEXT}" -n kube-system delete pod -l k8s-app=kube-dns --wait=false

echo "==> Waiting for CoreDNS to start crash-looping..."
for _ in $(seq 1 24); do
  RESTARTS="$(kubectl --context "${KIND_CONTEXT}" -n kube-system get pods -l k8s-app=kube-dns \
    -o jsonpath='{.items[*].status.containerStatuses[0].restartCount}' 2>/dev/null || echo "")"
  if echo "${RESTARTS}" | tr ' ' '\n' | grep -qE '^[1-9][0-9]*$'; then
    echo "    CoreDNS is restarting (restart counts: ${RESTARTS})."
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
kubectl config set-context "${GKE_CONTEXT}" --cluster="${GKE_CONTEXT}" --user="${GKE_CONTEXT}" --namespace=kube-system >/dev/null
rm -f "${CERT_FILE}" "${KEY_FILE}"

echo "==> Setup complete."
echo "    CoreDNS status: kubectl --context ${GKE_CONTEXT} -n kube-system get pods -l k8s-app=kube-dns"
