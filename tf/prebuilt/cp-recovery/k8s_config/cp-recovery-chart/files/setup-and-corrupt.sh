#!/bin/bash
set -e

# Install kubectl dynamically
echo "Installing kubectl..."
curl -sLO "https://dl.k8s.io/release/v1.30.0/bin/linux/amd64/kubectl"
chmod +x ./kubectl
mv ./kubectl /usr/local/bin/kubectl
echo "kubectl installed successfully!"

# Install etcdctl dynamically
echo "Installing etcdctl..."
curl -sLO https://github.com/etcd-io/etcd/releases/download/v3.5.11/etcd-v3.5.11-linux-amd64.tar.gz
tar -xzf etcd-v3.5.11-linux-amd64.tar.gz
mv etcd-v3.5.11-linux-amd64/etcdctl /usr/local/bin/etcdctl
mv etcd-v3.5.11-linux-amd64/etcdutl /usr/local/bin/etcdutl
rm -rf etcd-v3.5.11-linux-amd64*
echo "etcdctl installed successfully!"

echo "Waiting for mock-apiserver to be up and healthy..."
until curl -sf http://mock-apiserver:8080/healthz; do
  sleep 2
done
echo "mock-apiserver is healthy!"

echo "Creating workload-1 and workload-2..."
curl -sf -X POST -H "Content-Type: application/json" -d '{"name": "workload-1", "image": "nginx:latest"}' http://mock-apiserver:8080/api/v1/workloads
curl -sf -X POST -H "Content-Type: application/json" -d '{"name": "workload-2", "image": "redis:latest"}' http://mock-apiserver:8080/api/v1/workloads

echo "Waiting for all etcd pods to be ready..."
kubectl wait --for=condition=Ready pod/etcd-0 pod/etcd-1 pod/etcd-2 --namespace "${NAMESPACE}" --timeout=150s

echo "Taking snapshot from etcd over the network..."
etcdctl --endpoints=http://etcd-headless:2379 snapshot save /tmp/etcd-backup.db

echo "Calculating SHA256 checksum..."
sha256sum /tmp/etcd-backup.db | awk '{print $1}' > /tmp/etcd-backup.sha256
echo "Checksum is: $(cat /tmp/etcd-backup.sha256)"

echo "Uploading backup and checksum to GCS bucket: gs://${GCS_BUCKET_NAME} ..."
gsutil cp /tmp/etcd-backup.db gs://${GCS_BUCKET_NAME}/etcd-backup.db
gsutil cp /tmp/etcd-backup.sha256 gs://${GCS_BUCKET_NAME}/etcd-backup.sha256

echo "Verifying upload..."
gsutil ls gs://${GCS_BUCKET_NAME}/

echo "Creating workload-3 (after backup, before corruption)..."
curl -sf -X POST -H "Content-Type: application/json" -d '{"name": "workload-3", "image": "memcached:latest"}' http://mock-apiserver:8080/api/v1/workloads

echo "Corrupting etcd-1 and etcd-2..."
# 1. Scale down etcd StatefulSet to 1 replica to release PVC locks
kubectl scale statefulset etcd --replicas=1 --namespace "${NAMESPACE}"
kubectl wait --for=delete pod/etcd-1 pod/etcd-2 --namespace "${NAMESPACE}" --timeout=60s

# 2. Run temporary corruptor pod mounting PVCs of etcd-1 and etcd-2
kubectl apply -f /scripts/corruptor.yaml

# Wait for corruptor pod to succeed
echo "Waiting for etcd-corruptor pod to complete..."
until [ "$(kubectl get pod etcd-corruptor --namespace "${NAMESPACE}" -o jsonpath='{.status.phase}')" = "Succeeded" ]; do
  sleep 2
done

# 3. Clean up the corruptor pod
kubectl delete pod etcd-corruptor --namespace "${NAMESPACE}"

# 4. Scale etcd StatefulSet back to 3 replicas
kubectl scale statefulset etcd --replicas=3 --namespace "${NAMESPACE}"

echo "Corruption initiated successfully!"
