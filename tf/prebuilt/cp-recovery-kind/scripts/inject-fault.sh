#!/usr/bin/env bash
#
# Fault injection for the cp-recovery (kind) task.
#
# Runs from OUTSIDE the cluster during `tofu apply`, before the agent starts:
#   1. Takes a verified etcd snapshot from a healthy member and stages it
#      (+ sha256 checksum) into the backup PVC's hostPath on the worker node.
#   2. Corrupts a SINGLE etcd member's on-disk database and restarts it, so the
#      cluster is recoverably degraded: one member crashloops while the other two
#      keep Raft quorum and the API server stays up (the agent keeps kubectl).
#
# Nothing is left inside the cluster pointing at "corruption" — the agent must
# diagnose the unhealthy member itself.
set -euo pipefail

CLUSTER_NAME="${CLUSTER_NAME:?CLUSTER_NAME is required}"
NAMESPACE="${NAMESPACE:?NAMESPACE is required}"
export KUBECONFIG="${KUBECONFIG:-$HOME/.kube/config}"

ETCD_CERTS=(
  --endpoints=https://127.0.0.1:2379
  --cacert=/etc/kubernetes/pki/etcd/ca.crt
  --cert=/etc/kubernetes/pki/etcd/server.crt
  --key=/etc/kubernetes/pki/etcd/server.key
)

echo "==> Waiting for all nodes to be Ready..."
kubectl wait --for=condition=Ready nodes --all --timeout=180s

# Discover node names dynamically (kind names the docker containers the same as
# the Kubernetes node names, e.g. <cluster>-control-plane / <cluster>-worker).
mapfile -t CP_NODES < <(kubectl get nodes \
  -l node-role.kubernetes.io/control-plane \
  -o jsonpath='{range .items[*]}{.metadata.name}{"\n"}{end}')
WORKER_NODE="$(kubectl get nodes \
  -l '!node-role.kubernetes.io/control-plane' \
  -o jsonpath='{.items[0].metadata.name}')"

if [ "${#CP_NODES[@]}" -lt 3 ]; then
  echo "ERROR: expected >=3 control-plane nodes, found ${#CP_NODES[@]}" >&2
  exit 1
fi

SNAP_NODE="${CP_NODES[0]}"            # healthy member we snapshot from
TARGET_NODE="${CP_NODES[$(( ${#CP_NODES[@]} - 1 ))]}"  # member we corrupt (minority)
echo "    control-plane nodes: ${CP_NODES[*]}"
echo "    snapshot source:     ${SNAP_NODE}"
echo "    corruption target:   ${TARGET_NODE}"
echo "    worker (backup host): ${WORKER_NODE}"

echo "==> Waiting for etcd members to be running..."
kubectl -n kube-system wait --for=condition=Ready "pod/etcd-${SNAP_NODE}" --timeout=120s

echo "==> Taking a verified etcd snapshot from ${SNAP_NODE}..."
# etcdctl ships in the etcd image and defaults to API v3; write into the etcd
# data dir (a hostPath), so the file is reachable from the node container.
kubectl -n kube-system exec "etcd-${SNAP_NODE}" -- \
  etcdctl "${ETCD_CERTS[@]}" snapshot save /var/lib/etcd/etcd-backup.db

echo "==> Computing checksum and staging the backup onto ${WORKER_NODE}:/backup ..."
docker exec "${SNAP_NODE}" sha256sum /var/lib/etcd/etcd-backup.db | awk '{print $1}' > /tmp/etcd-backup.sha256
docker cp "${SNAP_NODE}:/var/lib/etcd/etcd-backup.db" /tmp/etcd-backup.db
docker exec "${WORKER_NODE}" mkdir -p /backup
docker cp /tmp/etcd-backup.db "${WORKER_NODE}:/backup/etcd-backup.db"
docker cp /tmp/etcd-backup.sha256 "${WORKER_NODE}:/backup/etcd-backup.sha256"

# Remove the staged copy from the live etcd data dir and the local temp files.
docker exec "${SNAP_NODE}" rm -f /var/lib/etcd/etcd-backup.db
rm -f /tmp/etcd-backup.db /tmp/etcd-backup.sha256
echo "    backup staged: /backup/etcd-backup.db (+ .sha256)"

echo "==> Corrupting the etcd member on ${TARGET_NODE} (minority; quorum preserved)..."
# Overwrite the bbolt database pages so etcd cannot reopen the store.
docker exec "${TARGET_NODE}" sh -c \
  'dd if=/dev/urandom of=/var/lib/etcd/member/snap/db bs=1M count=2 conv=notrunc'
# Restart the etcd static pod so the kubelet re-reads the corrupted data and the
# member enters CrashLoopBackOff.
docker exec "${TARGET_NODE}" sh -c \
  'crictl rm -f $(crictl ps -a -q --name etcd) 2>/dev/null || true'

echo "==> Fault injection complete."
echo "    One etcd member on ${TARGET_NODE} is now corrupted; the cluster should"
echo "    remain reachable via the surviving quorum (${CP_NODES[0]}, ${CP_NODES[1]})."
