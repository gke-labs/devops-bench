#!/usr/bin/env bash
# Setup for b-0033 "The canary nobody promoted: a partitioned StatefulSet rollout with a fence that begs to be blamed". Runs from OUTSIDE
# the cluster during `tofu apply`, before the agent starts: applies the seed
# manifests (manifests/00-gating.yaml, then manifests/10-workloads.yaml, gating
# objects first and waited live before anything they gate is applied -- see
# compiler/manifest.py's GATING_KINDS) and asserts every seeded condition
# actually holds.
set -euo pipefail

export KUBECONFIG="${KUBECONFIG:-$HOME/.kube/config}"
INFRA_PROVIDER="${INFRA_PROVIDER:-kind}"

if [[ "${INFRA_PROVIDER}" == "gcp" ]]; then
  echo "==> Fetching GKE credentials for cluster ${CLUSTER_NAME:?} in project ${PROJECT_ID:?} (${LOCATION:?})"
  gcloud container clusters get-credentials "${CLUSTER_NAME}" --zone "${LOCATION}" --project "${PROJECT_ID}"
fi

MANIFESTS_DIR="${MANIFESTS_DIR:?MANIFESTS_DIR is required}"
MANIFESTS_DIR="$(cd "${MANIFESTS_DIR}" && pwd)"
WAIT_TIMEOUT="${WAIT_TIMEOUT:-180}"

_ERRFILE="$(mktemp)"; trap 'rm -f "$_ERRFILE"' EXIT
guarded_read(){ local __v="$1"; shift; local __out __rc=0; __out="$("$@" 2>"$_ERRFILE")" || __rc=$?; if [ "$__rc" -ne 0 ] && grep -qE 'error parsing jsonpath|invalid array index|unable to parse|unrecognized|unknown flag|unknown command' "$_ERRFILE"; then echo "CHECK BUG: malformed kubectl query ($*): $(cat "$_ERRFILE")" >&2; exit 1; fi; printf -v "$__v" '%s' "$__out"; }

echo "==> Applying gating manifests..."
envsubst '${CLUSTER_NAME}' < "${MANIFESTS_DIR}/00-gating.yaml" | kubectl apply -f -

echo "==> Applying workload manifests..."
envsubst '${CLUSTER_NAME}' < "${MANIFESTS_DIR}/10-workloads.yaml" | kubectl apply -f -

echo "==> Waiting for workload rollouts to land..."
kubectl -n "archive" rollout status statefulset/vault --timeout="${WAIT_TIMEOUT}s"

echo "==> Applying after-settled givens as live mutations..."
kubectl get statefulset vault -n archive -o json | jq '(.spec.template.spec.containers[] | select(.name == "worker").envFrom) |= [{"configMapRef": {"name": "vault-config"}}]' | kubectl apply -f -

# assert the settled-phase condition holds now that it has landed
_deadline=$((SECONDS+$WAIT_TIMEOUT))
while :; do
  guarded_read val kubectl get statefulset vault -n "archive" -o jsonpath='{.spec.template.spec.containers[?(@.name == "worker")].envFrom}'; val_json=$(if [ -z "${val}" ]; then echo ""; else echo "${val}" | python3 -c 'import sys, json; d=json.load(sys.stdin); print(json.dumps(d, sort_keys=True, separators=(",", ":")))' 2>/dev/null || echo ""; fi)
  [ "${val_json}" = '[{"configMapRef":{"name":"vault-config"}}]' ] && break
  if (( SECONDS >= _deadline )); then
    echo "SEED FAIL: sts-envfrom-set@vault.wl not holding (sts-envfrom-set): timed out after ${WAIT_TIMEOUT}s -- path spec.template.spec.containers[?(@.name == \"worker\")].envFrom expected to equal '[{\"configMapRef\":{\"name\":\"vault-config\"}}]'; last observed value was '$val' (empty means the path was absent)"
    exit 1
  fi
  sleep 3
done

# assert seeded conditions actually hold at t0 (a seed that can't prove its
# conditions hold has failed before the experiment starts)
_deadline=$((SECONDS+$WAIT_TIMEOUT))
while :; do
  guarded_read val kubectl get statefulset vault -n "archive" -o jsonpath='{.spec.updateStrategy.rollingUpdate.partition}'
  [ "${val}" = 3 ] && break
  if (( SECONDS >= _deadline )); then
    echo "SEED FAIL: sts-partition-set@vault.wl not holding (sts-partition-set): timed out after ${WAIT_TIMEOUT}s -- path spec.updateStrategy.rollingUpdate.partition expected to equal '3'; last observed value was '$val' (empty means the path was absent)"
    exit 1
  fi
  sleep 3
done

echo "==> Waiting for hold-mode rows and maintain-kind objectives to settle..."
_deadline=$((SECONDS+$WAIT_TIMEOUT))
while :; do
  guarded_read val kubectl get poddisruptionbudget vault-pdb -n "archive" -o jsonpath='{.spec.minAvailable}'
  [ "${val}" = 3 ] && break
  if (( SECONDS >= _deadline )); then
    echo "SETTLE FAIL: pdb-floor-held@vault.pdb did not reach its t0-true state within ${WAIT_TIMEOUT}s"
    exit 1
  fi
  sleep 3
done
_deadline=$((SECONDS+$WAIT_TIMEOUT))
while :; do
  guarded_read val kubectl get statefulset vault -n "archive" -o jsonpath='{.status.readyReplicas}'
  [ -n "$val" ] && [ "$val" -ge 3 ] && break
  if (( SECONDS >= _deadline )); then
    echo "SETTLE FAIL: ready-floor-held@statefulset did not reach its t0-true state within ${WAIT_TIMEOUT}s"
    exit 1
  fi
  sleep 3
done
_deadline=$((SECONDS+$WAIT_TIMEOUT))
while :; do
  guarded_read val kubectl get configmap vault-config -n "archive" -o jsonpath='{.data.APP_MODE}'
  [ "${val}" = canary-v2 ] && break
  if (( SECONDS >= _deadline )); then
    echo "SETTLE FAIL: configmap-data-held@vault-config.cm did not reach its t0-true state within ${WAIT_TIMEOUT}s"
    exit 1
  fi
  sleep 3
done

echo "==> Setup complete."
echo "    Seeded: b-0033 in archive."
echo "    Inspect: kubectl -n archive get all"
