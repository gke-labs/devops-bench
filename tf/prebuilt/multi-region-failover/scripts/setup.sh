#!/usr/bin/env bash
#
# Outside-the-cluster setup for the multi-region DR-failover task. Run by Terraform
# (null_resource.setup) after both GKE clusters, the Cloud SQL pair, and the global LB
# exist. It:
#   1. merges BOTH clusters' credentials into the kubeconfig as stable contexts
#      `east` (primary) and `west` (standby);
#   2. deploys the storefront app (frontend + backend) to both regions;
#   3. leaves the standby (west) region MISSING app-config/app-secret  -> the config
#      drift the agent reconciles after failover;
#   4. injects the regional outage by scaling the primary (east) node pool to 0, so the
#      global endpoint (URL map default -> east) serves 5xx until the agent re-points it;
#   5. seeds the GitOps bare repo with the app's desired state (incl. app-config/secret).
#
# Nothing left in either cluster describes the outage or the fix.
set -euo pipefail

: "${PROJECT_ID:?}" "${NAMESPACE:?}"
: "${EAST_CLUSTER:?}" "${EAST_ZONE:?}" "${WEST_CLUSTER:?}" "${WEST_ZONE:?}"
: "${EAST_IP:?}" "${WEST_IP:?}" "${LB_IP:?}"
: "${REPO_PATH:?}" "${MANIFESTS_DIR:?}"

REPO_PATH="${REPO_PATH/#\~/$HOME}"
MANIFESTS_DIR="$(cd "$MANIFESTS_DIR" && pwd)"

echo "==> Fetching credentials for both clusters"
gcloud container clusters get-credentials "$EAST_CLUSTER" --zone "$EAST_ZONE" --project "$PROJECT_ID"
gcloud container clusters get-credentials "$WEST_CLUSTER" --zone "$WEST_ZONE" --project "$PROJECT_ID"

# Rename the auto-generated gke_* contexts to stable names the agent can rely on.
kubectl config delete-context east >/dev/null 2>&1 || true
kubectl config delete-context west >/dev/null 2>&1 || true
kubectl config rename-context "gke_${PROJECT_ID}_${EAST_ZONE}_${EAST_CLUSTER}" east
kubectl config rename-context "gke_${PROJECT_ID}_${WEST_ZONE}_${WEST_CLUSTER}" west

# ---------------------------------------------------------------------------
# deploy_app <context> <with_config: yes|no>
# ---------------------------------------------------------------------------
deploy_app() {
  local ctx="$1" with_config="$2" ip
  if [[ "$ctx" == "east" ]]; then ip="$EAST_IP"; else ip="$WEST_IP"; fi

  echo "==> [$ctx] creating namespace $NAMESPACE"
  kubectl --context "$ctx" create namespace "$NAMESPACE" \
    --dry-run=client -o yaml | kubectl --context "$ctx" apply -f -

  if [[ "$with_config" == "yes" ]]; then
    echo "==> [$ctx] applying app-config + app-secret"
    kubectl --context "$ctx" -n "$NAMESPACE" apply -f "$MANIFESTS_DIR/app-config.yaml"
    kubectl --context "$ctx" -n "$NAMESPACE" apply -f "$MANIFESTS_DIR/app-secret.yaml"
  else
    echo "==> [$ctx] SKIPPING app-config + app-secret (injected config drift)"
  fi

  echo "==> [$ctx] applying backend + frontend"
  kubectl --context "$ctx" -n "$NAMESPACE" apply -f "$MANIFESTS_DIR/backend.yaml"
  kubectl --context "$ctx" -n "$NAMESPACE" apply -f "$MANIFESTS_DIR/frontend.yaml"

  echo "==> [$ctx] exposing frontend on reserved IP $ip"
  cat <<EOF | kubectl --context "$ctx" -n "$NAMESPACE" apply -f -
apiVersion: v1
kind: Service
metadata:
  name: frontend
  labels:
    app: frontend
spec:
  type: LoadBalancer
  loadBalancerIP: ${ip}
  selector:
    app: frontend
  ports:
    - name: http
      port: 80
      targetPort: 80
EOF
}

# West = healthy standby, but WITHOUT the replicated config (the drift).
deploy_app west no
# East = primary; deploy fully first so its LoadBalancer Service binds the static IP.
deploy_app east yes

echo "==> Waiting for the WEST standby to become healthy"
kubectl --context west -n "$NAMESPACE" rollout status deploy/frontend --timeout=180s || true
kubectl --context west -n "$NAMESPACE" rollout status deploy/backend --timeout=180s || true

echo "==> Waiting for the EAST frontend Service to bind its static IP"
for _ in $(seq 1 30); do
  bound="$(kubectl --context east -n "$NAMESPACE" get svc frontend \
    -o jsonpath='{.status.loadBalancer.ingress[0].ip}' 2>/dev/null || true)"
  [[ "$bound" == "$EAST_IP" ]] && break
  sleep 10
done

# ---------------------------------------------------------------------------
# Inject the regional outage: drop the primary region's compute capacity to zero.
# All east workloads go unschedulable, so the global endpoint (which defaults to the
# east backend) returns 5xx. This cannot be undone by re-applying app manifests — the
# correct recovery is to fail traffic over to the healthy west region.
# ---------------------------------------------------------------------------
echo "==> Injecting outage: scaling EAST node pool to 0"
gcloud container clusters resize "$EAST_CLUSTER" \
  --node-pool primary-node-pool --num-nodes 0 \
  --zone "$EAST_ZONE" --project "$PROJECT_ID" --quiet

# ---------------------------------------------------------------------------
# Seed the GitOps source of truth with the app's DESIRED state (both clusters should
# look like this), including app-config/app-secret that west is currently missing.
# ---------------------------------------------------------------------------
echo "==> Seeding GitOps repo at $REPO_PATH"
rm -rf "$REPO_PATH"
git init --bare "$REPO_PATH" >/dev/null
git -C "$REPO_PATH" symbolic-ref HEAD refs/heads/main

WORK="$(mktemp -d)"
trap 'rm -rf "$WORK"' EXIT
git -C "$WORK" init -q
git -C "$WORK" config user.email "setup@devops-bench.local"
git -C "$WORK" config user.name "devops-bench setup"
mkdir -p "$WORK/manifests"
cp "$MANIFESTS_DIR/app-config.yaml" "$MANIFESTS_DIR/app-secret.yaml" \
   "$MANIFESTS_DIR/backend.yaml" "$MANIFESTS_DIR/frontend.yaml" "$WORK/manifests/"
cat > "$WORK/README.md" <<EOF
# storefront

Kubernetes manifests for the storefront service (namespace \`${NAMESPACE}\`).
EOF
git -C "$WORK" add -A
git -C "$WORK" -c init.defaultBranch=main commit -q -m "storefront desired state"
git -C "$WORK" branch -M main
git -C "$WORK" push -q "$REPO_PATH" main

echo "==> Setup complete."
echo "    Global endpoint : http://${LB_IP}/   (currently 5xx — primary region down)"
echo "    Contexts        : east (primary, drained), west (standby, healthy)"
echo "    GitOps repo     : $REPO_PATH"
