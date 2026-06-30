#!/usr/bin/env bash
#
# Setup for the mesh-federation task. Runs from OUTSIDE the clusters during
# `tofu apply`, before the agent starts. It stands up a REAL Istio multi-primary,
# multi-network federation across two kind clusters, then injects an mTLS
# misconfiguration for the agent to diagnose and fix.
#
# What setup does (the fragile, kind-specific plumbing — NOT the agent's job):
#   1. Download a pinned istioctl + samples (bastion has no istioctl).
#   2. MetalLB on both clusters, with non-overlapping address pools carved from
#      the shared `kind` Docker network so the east-west gateways get LoadBalancer
#      IPs reachable across clusters.
#   3. A shared root CA (cacerts) installed in istio-system on BOTH clusters, so
#      the two trust domains federate (this is the "root CA exchange" prereq).
#   4. Istio multi-primary/multi-network control planes on both (mesh1; per-cluster
#      clusterName + network label).
#   5. East-west gateways + expose-services (*.local) on both.
#   6. Cross-cluster remote secrets, BOTH directions, with the kind API-server
#      address patched to the node's Docker IP (the standard kind workaround so the
#      remote kubeconfig is reachable from the peer cluster).
#   7. The workloads: `backend` (cluster-2) + a `sleep` client (cluster-1), with
#      the `backend` Service present in both clusters.
#
# The INJECTED FAULT (what the agent must fix):
#   - cluster-2 `sample` namespace enforces PeerAuthentication mode STRICT, but
#   - cluster-1 has a DestinationRule for the backend host with tls.mode DISABLE,
#   so the client sends plaintext while the server demands mTLS -> the
#   cross-cluster call fails the mTLS handshake. This is the textbook
#   "DR DISABLE vs PeerAuthentication STRICT" mismatch (SOT step 4).
#
# Nothing here tells the agent the fix — it must observe the failing call and
# reconcile the mTLS configuration to a consistent STRICT posture.
set -euo pipefail

export KUBECONFIG="${KUBECONFIG:-$HOME/.kube/config}"
C1="${C1:?C1 (cluster-1 name) is required}"
C2="${C2:?C2 (cluster-2 name) is required}"
MANIFESTS_DIR="${MANIFESTS_DIR:?MANIFESTS_DIR is required}"
MANIFESTS_DIR="$(cd "${MANIFESTS_DIR}" && pwd)"
ISTIO_VERSION="${ISTIO_VERSION:-1.23.2}"
METALLB_VERSION="${METALLB_VERSION:-v0.14.8}"
KIND_NET="${KIND_NET:-kind}"

CTX1="kind-${C1}"
CTX2="kind-${C2}"
WORK="$(mktemp -d)"
trap 'rm -rf "${WORK}"' EXIT

k1() { kubectl --context "${CTX1}" "$@"; }
k2() { kubectl --context "${CTX2}" "$@"; }

# Both kind clusters are created by TF (cluster-2 into its own kubeconfig to avoid
# clobbering cluster-1's). Merge both contexts into the per-run KUBECONFIG so the
# agent sees kind-<C1> and kind-<C2> in one file.
echo "==> Merging both cluster contexts into ${KUBECONFIG}..."
kind export kubeconfig --name "${C1}" --kubeconfig "${KUBECONFIG}"
kind export kubeconfig --name "${C2}" --kubeconfig "${KUBECONFIG}"

echo "==> Downloading Istio ${ISTIO_VERSION} (istioctl + samples + tools/certs)..."
(
  cd "${WORK}"
  curl -fsSL "https://github.com/istio/istio/releases/download/${ISTIO_VERSION}/istio-${ISTIO_VERSION}-linux-amd64.tar.gz" \
    | tar -xz
)
ISTIO_DIR="${WORK}/istio-${ISTIO_VERSION}"
export PATH="${ISTIO_DIR}/bin:${PATH}"

# --- MetalLB: split the kind Docker subnet into two non-overlapping pools ------
# The east-west gateways need LoadBalancer IPs reachable on the shared kind net.
SUBNET="$(docker network inspect "${KIND_NET}" \
  -f '{{range .IPAM.Config}}{{if .Gateway}}{{.Subnet}} {{end}}{{end}}' \
  | tr ' ' '\n' | grep -E '^[0-9]+\.' | head -1)"
PREFIX="$(echo "${SUBNET}" | cut -d. -f1-2)"   # e.g. 172.18
POOL1="${PREFIX}.255.200-${PREFIX}.255.219"
POOL2="${PREFIX}.255.220-${PREFIX}.255.239"

install_metallb() {
  local kctx="$1" pool="$2"
  kubectl --context "${kctx}" apply -f \
    "https://raw.githubusercontent.com/metallb/metallb/${METALLB_VERSION}/config/manifests/metallb-native.yaml"
  kubectl --context "${kctx}" -n metallb-system wait --for=condition=Available deploy/controller --timeout=180s
  kubectl --context "${kctx}" -n metallb-system rollout status ds/speaker --timeout=180s
  # The webhook can take a few seconds after Available; retry the CR apply.
  for _ in $(seq 1 12); do
    if cat <<EOF | kubectl --context "${kctx}" apply -f -
apiVersion: metallb.io/v1beta1
kind: IPAddressPool
metadata: { name: kind-pool, namespace: metallb-system }
spec: { addresses: ["${pool}"] }
---
apiVersion: metallb.io/v1beta1
kind: L2Advertisement
metadata: { name: l2, namespace: metallb-system }
spec: { ipAddressPools: ["kind-pool"] }
EOF
    then return 0; fi
    sleep 5
  done
  echo "ERROR: metallb config failed on ${kctx}" >&2; return 1
}
echo "==> Installing MetalLB (pool ${POOL1} on ${C1}, ${POOL2} on ${C2})..."
install_metallb "${CTX1}" "${POOL1}"
install_metallb "${CTX2}" "${POOL2}"

# --- Shared root CA -> cacerts on both clusters (federated trust) --------------
echo "==> Generating a shared root CA and installing cacerts on both clusters..."
(
  cd "${ISTIO_DIR}"
  mkdir -p certs
  make -f tools/certs/Makefile.selfsigned.mk root-ca >/dev/null
  make -f tools/certs/Makefile.selfsigned.mk "${C1}-cacerts" >/dev/null
  make -f tools/certs/Makefile.selfsigned.mk "${C2}-cacerts" >/dev/null
)
for pair in "${CTX1}:${C1}" "${CTX2}:${C2}"; do
  kctx="${pair%%:*}"; cname="${pair##*:}"
  kubectl --context "${kctx}" create namespace istio-system --dry-run=client -o yaml | kubectl --context "${kctx}" apply -f -
  kubectl --context "${kctx}" label namespace istio-system topology.istio.io/network="network-${cname}" --overwrite
  kubectl --context "${kctx}" -n istio-system create secret generic cacerts \
    --from-file="${ISTIO_DIR}/${cname}/ca-cert.pem" \
    --from-file="${ISTIO_DIR}/${cname}/ca-key.pem" \
    --from-file="${ISTIO_DIR}/${cname}/root-cert.pem" \
    --from-file="${ISTIO_DIR}/${cname}/cert-chain.pem" \
    --dry-run=client -o yaml | kubectl --context "${kctx}" apply -f -
done

# --- Istio multi-primary control planes ---------------------------------------
install_istio() {
  local kctx="$1" cname="$2"
  cat <<EOF | istioctl install --context "${kctx}" -y -f -
apiVersion: install.istio.io/v1alpha1
kind: IstioOperator
spec:
  values:
    global:
      meshID: mesh1
      multiCluster:
        clusterName: ${cname}
      network: network-${cname}
EOF
}
echo "==> Installing Istio multi-primary control planes..."
install_istio "${CTX1}" "${C1}"
install_istio "${CTX2}" "${C2}"

# --- East-west gateways + expose services -------------------------------------
echo "==> Installing east-west gateways + exposing services..."
gen_eastwest() {
  local kctx="$1" cname="$2"
  "${ISTIO_DIR}/samples/multicluster/gen-eastwest-gateway.sh" \
    --mesh mesh1 --cluster "${cname}" --network "network-${cname}" \
    | istioctl install --context "${kctx}" -y -f -
}
gen_eastwest "${CTX1}" "${C1}"
gen_eastwest "${CTX2}" "${C2}"
for kctx in "${CTX1}" "${CTX2}"; do
  kubectl --context "${kctx}" -n istio-system wait --for=condition=Available deploy/istio-eastwestgateway --timeout=240s
  kubectl --context "${kctx}" apply -n istio-system -f "${ISTIO_DIR}/samples/multicluster/expose-services.yaml"
done

# --- Cross-cluster remote secrets (kind API-IP patched) -----------------------
echo "==> Exchanging remote secrets (kind API-server IPs patched for reachability)..."
node_ip() { docker inspect -f '{{range .NetworkSettings.Networks}}{{.IPAddress}}{{end}}' "${1}-control-plane"; }
IP1="$(node_ip "${C1}")"
IP2="$(node_ip "${C2}")"
# Create a remote secret for C1 and install it into C2 (and vice versa), pointing
# the server at the peer node's Docker IP (the kubeconfig kind writes uses
# 127.0.0.1:<hostport>, unreachable from the peer cluster's pods).
istioctl create-remote-secret --context "${CTX1}" --name "${C1}" --server "https://${IP1}:6443" \
  | kubectl --context "${CTX2}" apply -f -
istioctl create-remote-secret --context "${CTX2}" --name "${C2}" --server "https://${IP2}:6443" \
  | kubectl --context "${CTX1}" apply -f -

# --- Workloads ----------------------------------------------------------------
echo "==> Deploying workloads (backend in ${C2}, sleep client in ${C1}; Service in both)..."
k1 apply -f "${MANIFESTS_DIR}/apps/services.yaml"
k2 apply -f "${MANIFESTS_DIR}/apps/services.yaml"
k2 apply -f "${MANIFESTS_DIR}/apps/backend.yaml"
k1 apply -f "${MANIFESTS_DIR}/apps/frontend.yaml"
k2 -n sample rollout status deploy/backend --timeout=240s
k1 -n sample rollout status deploy/sleep --timeout=240s

# --- Inject the mTLS fault (the thing the agent must fix) ----------------------
echo "==> Injecting mTLS misconfiguration (server STRICT vs client DR DISABLE)..."
# Server side (cluster-2): require strict mTLS in the sample namespace.
cat <<EOF | k2 apply -f -
apiVersion: security.istio.io/v1
kind: PeerAuthentication
metadata:
  name: sample-strict
  namespace: sample
spec:
  mtls:
    mode: STRICT
EOF
# Client side (cluster-1): a DestinationRule that DISABLES mTLS toward the backend
# host -> client sends plaintext, server rejects -> handshake failure.
cat <<EOF | k1 apply -f -
apiVersion: networking.istio.io/v1
kind: DestinationRule
metadata:
  name: backend-no-mtls
  namespace: sample
spec:
  host: backend.sample.svc.cluster.local
  trafficPolicy:
    tls:
      mode: DISABLE
EOF

echo "==> Setup complete."
echo "    Clusters: ${C1} (client) / ${C2} (backend) — contexts ${CTX1} / ${CTX2}"
echo "    Repro the failing cross-cluster call:"
echo "      kubectl --context ${CTX1} -n sample exec deploy/sleep -c sleep -- curl -sS -m 5 backend.sample.svc.cluster.local:8080"
