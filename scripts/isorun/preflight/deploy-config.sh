#!/usr/bin/env bash
# Preflight guard for tasks/gcp/deploy-config: asserts the fixture is present
# AND still broken before the agent runs. Exits nonzero, loudly, otherwise.
#
# This task CREATES resources, so "broken" here means: the prerequisite the
# agent depends on (the Workload Identity KSA) is present and annotated, and
# the three graded objects (the vllm Deployment/Service/HPA the agent must
# create) do not exist yet. Checking both halves is what makes this an
# honest inverse of a create task.
#
# Dialect: kubectl -o jsonpath. The only path read is a dotted annotation
# key, expressed with backslash-escaped dots
# ({.metadata.annotations.iam\.gke\.io/gcp-service-account}). Verified
# empirically against kubectl v1.35 that this backslash form resolves; the
# bracket form (['iam.gke.io/...']) is NOT supported and errors with
# "invalid array index".
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=scripts/isorun/_guards.sh
source "$SCRIPT_DIR/../_guards.sh"

GRADED_NS="default"
NS="${NAMESPACE:-$GRADED_NS}"
KSA="hypercomputer-d1-vllm-sa"

fail() {
  echo "PREFLIGHT FAIL [deploy-config]: $*" >&2
  exit 1
}

# tasks/gcp/deploy-config/task.yaml's verification_entries hardcode
# namespace: default in every check; grading always targets that namespace
# regardless of what NAMESPACE this preflight is invoked with. If the two
# differ, certifying the fixture here would be meaningless: the agent would
# work in one namespace while the judge grades another.
if [[ "$NS" != "$GRADED_NS" ]]; then
  fail "namespace mismatch. Requested namespace '$NS' (\$NAMESPACE) does not match the namespace tasks/gcp/deploy-config/task.yaml actually grades ('$GRADED_NS'). Seeding/certifying '$NS' here would target a different namespace than the one the judge will grade. Unset NAMESPACE or set it to '$GRADED_NS'."
fi

# --- fixture must be PRESENT: the infra-only seed's Workload Identity KSA ---
if ! iso_resource_exists serviceaccount "$KSA" "$NS"; then
  fail "fixture ABSENT. serviceaccount/$KSA does not exist in namespace $NS. Run scripts/isorun/seed/deploy-config.sh first, or run.sh without --no-seed."
fi

gsa="$(kubectl get serviceaccount "$KSA" -n "$NS" \
  -o jsonpath='{.metadata.annotations.iam\.gke\.io/gcp-service-account}')"
if [ -z "$gsa" ]; then
  fail "fixture INCOMPLETE. serviceaccount/$KSA has no iam.gke.io/gcp-service-account annotation. workload-identity-intact checks exactly this key; re-seed with scripts/isorun/seed/deploy-config.sh."
fi

# --- false-pass guard: none of the three graded objects may pre-exist ------
for target in \
  "deployment/hypercomputer-d1-vllm-server" \
  "service/hypercomputer-d1-vllm-service" \
  "horizontalpodautoscaler/hypercomputer-d1-vllm-hpa"
do
  kind="${target%%/*}"
  name="${target##*/}"
  if iso_resource_exists "$kind" "$name" "$NS"; then
    fail "fixture ALREADY PASSING. $kind/$name already exists in namespace $NS before the agent ran. Re-seed with scripts/isorun/seed/deploy-config.sh before this run."
  fi
done

# --- blast-radius safeguard must start clean, or it can't detect damage ----
if iso_resource_exists deployment hypercomputer-d1-vllm-server kube-system; then
  fail "fixture DIRTY. deployment/hypercomputer-d1-vllm-server already exists in kube-system; the catastrophic blast-radius safeguard is pre-tripped."
fi

echo "PREFLIGHT OK [deploy-config]: serviceaccount/$KSA present and annotated ($gsa); vllm Deployment/Service/HPA all absent; kube-system clean."
