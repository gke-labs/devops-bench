#!/usr/bin/env bash
# Preflight guard for tasks/gcp/fix-config: asserts the fixture is present
# AND still broken before the agent runs. Exits nonzero, loudly, otherwise.
#
# Graded pre-state (tasks/gcp/fix-config/task.yaml verification_entries,
# config-restored):
#   containers[0].env[USE_GEMINI_API].value == "false"   <- what the agent must produce
#   containers[0].env[VLLM_API_URL].value   == "http://hypercomputer-d1-vllm-service:8000/v1/chat/completions"
# So the pre-agent fixture must have USE_GEMINI_API == "true" (the seeded
# misconfiguration) and VLLM_API_URL already at the golden value (the seed
# sets it correctly; only USE_GEMINI_API is broken).
#
# Dialect: kubectl -o jsonpath. Verified empirically against kubectl v1.35
# (kubectl create --dry-run=client -f ... -o jsonpath=...) that the filter
# predicate env[?(@.name=="X")] parses and resolves. kubectl returns an EMPTY
# STRING with rc=0 both when a key is missing and when it resolves to an
# empty value, so a bare .value read can't tell "absent" from "empty"; the
# .name sub-probe below is what distinguishes them.
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=scripts/isorun/_guards.sh
source "$SCRIPT_DIR/../_guards.sh"

GRADED_NS="default"
NS="${NAMESPACE:-$GRADED_NS}"
DEPLOY="hypercomputer-d1-frontend"
EXPECT_VLLM_URL="http://hypercomputer-d1-vllm-service:8000/v1/chat/completions"

fail() {
  echo "PREFLIGHT FAIL [fix-config]: $*" >&2
  exit 1
}

# tasks/gcp/fix-config/task.yaml's verification_entries (config-restored)
# hardcode namespace: default in every check; grading always targets that
# namespace regardless of what NAMESPACE this preflight is invoked with. If
# the two differ, certifying the fixture here would be meaningless: the agent
# would work in one namespace while the judge grades another.
if [[ "$NS" != "$GRADED_NS" ]]; then
  fail "namespace mismatch. Requested namespace '$NS' (\$NAMESPACE) does not match the namespace tasks/gcp/fix-config/task.yaml actually grades ('$GRADED_NS'). Seeding/certifying '$NS' here would target a different namespace than the one the judge will grade. Unset NAMESPACE or set it to '$GRADED_NS'."
fi

if ! iso_resource_exists deployment "$DEPLOY" "$NS"; then
  fail "fixture ABSENT. deployment/$DEPLOY does not exist in namespace $NS. Run scripts/isorun/seed/fix-config.sh first, or run.sh without --no-seed."
fi

env_name="$(kubectl get deployment "$DEPLOY" -n "$NS" \
  -o jsonpath='{.spec.template.spec.containers[0].env[?(@.name=="USE_GEMINI_API")].name}')"
if [ "$env_name" != "USE_GEMINI_API" ]; then
  fail "fixture MALFORMED. deployment/$DEPLOY containers[0] has no USE_GEMINI_API env var. Re-seed with scripts/isorun/seed/fix-config.sh."
fi

use_gemini="$(kubectl get deployment "$DEPLOY" -n "$NS" \
  -o jsonpath='{.spec.template.spec.containers[0].env[?(@.name=="USE_GEMINI_API")].value}')"
case "$use_gemini" in
  true)
    : ;;
  false)
    fail "fixture ALREADY PASSING. USE_GEMINI_API is already 'false' before the agent ran. Re-seed with scripts/isorun/seed/fix-config.sh before this run." ;;
  *)
    fail "fixture MALFORMED. USE_GEMINI_API='${use_gemini}', expected the broken value 'true'." ;;
esac

vllm_url="$(kubectl get deployment "$DEPLOY" -n "$NS" \
  -o jsonpath='{.spec.template.spec.containers[0].env[?(@.name=="VLLM_API_URL")].value}')"
if [ "$vllm_url" != "$EXPECT_VLLM_URL" ]; then
  fail "fixture DRIFTED. VLLM_API_URL='${vllm_url}', expected '${EXPECT_VLLM_URL}'. Re-seed with scripts/isorun/seed/fix-config.sh."
fi

echo "PREFLIGHT OK [fix-config]: deployment/$DEPLOY present and broken (USE_GEMINI_API=true)."
