#!/usr/bin/env bash
#
# Setup for the opa-remediation task. Runs from OUTSIDE the cluster during
# `tofu apply`, before the agent starts:
#   1. installs Kyverno (the Policy-as-Code engine),
#   2. applies two AUDIT-mode compliance policies (disallow-privileged,
#      require-resource-limits) — audit so existing violations are *reported*, not
#      blocked,
#   3. deploys team workloads that violate those policies (live in the cluster),
#   4. seeds a local bare git repo (the GitOps source of truth) with the workload
#      manifests for the agent to remediate.
#
# Nothing here tells the agent what is wrong — it must scan the policy reports and
# discover the violations itself.
set -euo pipefail

export KUBECONFIG="${KUBECONFIG:-$HOME/.kube/config}"
REPO_PATH="${REPO_PATH:?REPO_PATH is required}"
REPO_PATH="${REPO_PATH/#\~/$HOME}"
MANIFESTS_DIR="${MANIFESTS_DIR:?MANIFESTS_DIR is required}"
MANIFESTS_DIR="$(cd "${MANIFESTS_DIR}" && pwd)"
KYVERNO_VERSION="${KYVERNO_VERSION:-v1.12.7}"

echo "==> Installing Kyverno ${KYVERNO_VERSION}..."
# Server-side apply: the Kyverno CRDs are large and exceed the client-side
# last-applied annotation limit.
kubectl apply --server-side -f \
  "https://github.com/kyverno/kyverno/releases/download/${KYVERNO_VERSION}/install.yaml"

echo "==> Waiting for the ClusterPolicy CRD to be established..."
kubectl wait --for=condition=established --timeout=120s crd/clusterpolicies.kyverno.io

echo "==> Waiting for Kyverno to be ready..."
kubectl -n kyverno wait --for=condition=Available deploy --all --timeout=300s

echo "==> Applying compliance policies (audit mode)..."
# The Kyverno admission webhook (mutate-policy.kyverno.svc) can take several seconds
# to start serving *after* its deployment reports Available, so a plain apply can fail
# with "failed calling webhook ... context deadline exceeded". Retry to ride it out.
policy_applied=false
for attempt in $(seq 1 12); do
  if kubectl apply -f "${MANIFESTS_DIR}/policies/"; then
    policy_applied=true
    break
  fi
  echo "    policy apply attempt ${attempt} failed (Kyverno webhook not ready yet), retrying in 5s..."
  sleep 5
done
if [ "${policy_applied}" != true ]; then
  echo "ERROR: Kyverno policies failed to apply after retries" >&2
  exit 1
fi

echo "==> Deploying team workloads (some violate the policies)..."
kubectl apply -f "${MANIFESTS_DIR}/workloads/"

echo "==> Waiting for Kyverno's background scan to populate PolicyReports..."
# Ensures the compliance signal exists before the agent starts, so it can't scan
# an empty report set and wrongly conclude the cluster is already compliant.
for _ in $(seq 1 36); do
  if kubectl get policyreport -A -o json 2>/dev/null \
       | python3 -c 'import sys,json; sys.exit(0 if any(r.get("result")=="fail" for it in json.load(sys.stdin).get("items",[]) for r in it.get("results",[])) else 1)'; then
    echo "    PolicyReports populated with violations."
    break
  fi
  sleep 5
done

echo "==> Seeding GitOps repo at ${REPO_PATH}..."
rm -rf "${REPO_PATH}"
git init --bare "${REPO_PATH}"
WORK="$(mktemp -d)"
(
  cd "${WORK}"
  git init -q
  git config user.email "platform@example.com"
  git config user.name "Platform"
  mkdir -p workloads
  cp "${MANIFESTS_DIR}"/workloads/*.yaml workloads/
  git add .
  git commit -q -m "Add team workload manifests"
  git branch -M main
  git remote add origin "${REPO_PATH}"
  git push -q origin main
)
rm -rf "${WORK}"
# Point the bare repo's HEAD at main so a plain `git clone` checks it out.
git -C "${REPO_PATH}" symbolic-ref HEAD refs/heads/main

echo "==> Setup complete."
echo "    Kyverno is auditing; violations will surface in PolicyReports:"
echo "      kubectl get policyreport,clusterpolicyreport -A"
echo "    Workload manifests (GitOps source of truth): git clone ${REPO_PATH}"
