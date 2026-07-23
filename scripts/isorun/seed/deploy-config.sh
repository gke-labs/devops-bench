#!/usr/bin/env bash
# Seed hook for tasks/gcp/deploy-config: reset, then ensure the Workload
# Identity KSA prerequisite exists, for fast local iteration against an
# already-standing cluster (no tofu, no cluster build).
#
# Derived from: tf/prebuilt/hypercomputer-d1, seed_mode = "infra-only". That
# seed_mode creates exactly one in-cluster object: serviceaccount/
# hypercomputer-d1-vllm-sa, annotated iam.gke.io/gcp-service-account (main.tf
# lines 103-111, ungated by count). The three graded objects (the vllm
# Deployment/Service/HPA) are this task's agent's OWN deliverables, so beyond
# the reset, seeding is a no-op for them: this script only creates the KSA
# prerequisite, it never pre-creates the graded objects.
#
# There is no separate fixtures/deploy-config.yaml file: the only seeded
# object is the single ServiceAccount below, so it is inlined here rather than
# split into its own fixture file.
#
# The real tofu stack binds the annotation to a real GSA via
# google_service_account.vllm_gsa. This loop has no matching GCP project
# behind it, so the annotation value here is a placeholder string; that is
# fine, because tasks/gcp/deploy-config/task.yaml's workload-identity-intact
# safeguard only checks that the annotation KEY exists, never that it
# resolves to a real, working GSA.
#
# Idempotent: safe to run repeatedly. Uses kubectl apply, never create.
set -euo pipefail

: "${CLUSTER:=autopilot-cluster-1}"
: "${PROJECT:=}"
: "${REGION:=us-central1}"
: "${NAMESPACE:=default}"

# (a) RESET: remove whatever a previous agent run left behind. Do NOT delete
# the ServiceAccount here: it is the fixture, not a deliverable. Deleting and
# recreating it without the annotation is exactly what workload-identity-intact
# exists to catch.
echo "==> deploy-config seed: RESET (cluster: $CLUSTER, namespace: $NAMESPACE)"
kubectl -n "$NAMESPACE" delete \
  deploy/hypercomputer-d1-vllm-server \
  svc/hypercomputer-d1-vllm-service \
  hpa/hypercomputer-d1-vllm-hpa \
  --ignore-not-found

# (b) SEED: ensure the Workload Identity KSA prerequisite exists. kubectl
# apply is idempotent here too, so re-running this is safe even if the KSA
# already exists from a prior seed.
echo "==> deploy-config seed: SEED (ensure serviceaccount/hypercomputer-d1-vllm-sa exists, annotated)"
GSA_EMAIL="${GSA_EMAIL:-hc-d1-vllm-local-iter@${PROJECT:-local-iteration}.iam.gserviceaccount.com}"
cat <<EOF | kubectl apply -f -
apiVersion: v1
kind: ServiceAccount
metadata:
  name: hypercomputer-d1-vllm-sa
  namespace: $NAMESPACE
  annotations:
    iam.gke.io/gcp-service-account: $GSA_EMAIL
EOF

echo "==> deploy-config seed: done. KSA hypercomputer-d1-vllm-sa annotated ($GSA_EMAIL); vllm Deployment/Service/HPA absent (agent's job to create them)."
