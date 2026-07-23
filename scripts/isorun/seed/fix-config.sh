#!/usr/bin/env bash
# Seed hook for tasks/gcp/fix-config: reset, then re-apply the broken-frontend
# fixture, for fast local iteration against an already-standing cluster (no
# tofu, no cluster build).
#
# Fixture: scripts/isorun/fixtures/fix-config.yaml. See that file's header
# for the full derivation (tf/prebuilt/hypercomputer-d1, seed_mode =
# "broken-frontend") and the fields deliberately omitted.
#
# Idempotent: safe to run repeatedly. Uses kubectl apply, never create.
set -euo pipefail

: "${CLUSTER:=autopilot-cluster-1}"
: "${PROJECT:=}"
: "${REGION:=us-central1}"
: "${NAMESPACE:=default}"

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
FIXTURE="$SCRIPT_DIR/../fixtures/fix-config.yaml"

# (a) RESET: remove whatever a previous agent run left behind. The agent's
# job is to re-apply/patch this same Deployment, so any leftover copy
# (fixed or otherwise) must go before we re-seed the broken one.
echo "==> fix-config seed: RESET (cluster: $CLUSTER, namespace: $NAMESPACE)"
kubectl -n "$NAMESPACE" delete deploy/hypercomputer-d1-frontend --ignore-not-found

# (b) SEED: apply the fixture so the broken pre-state exists. The fixture
# hardcodes namespace: default (matching var.namespace's default), so it is
# applied without -n to avoid a namespace-mismatch error if NAMESPACE differs.
echo "==> fix-config seed: SEED (apply $FIXTURE)"
kubectl apply -f "$FIXTURE"

echo "==> fix-config seed: done. deployment/hypercomputer-d1-frontend is present with USE_GEMINI_API=true (broken)."
