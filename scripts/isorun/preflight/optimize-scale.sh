#!/usr/bin/env bash
# Preflight guard for tasks/common/optimize-scale: asserts the fixture is
# present AND still unsized/unscaled before the agent runs. Exits nonzero,
# loudly, otherwise.
#
# Graded pre-state (tasks/common/optimize-scale/task.yaml verification_entries):
#   resources-set  -> containers[0].resources.requests EXISTS and .limits EXISTS
#   hpa-configured -> every HPA in the namespace has minReplicas > 1 and a
#                     spec.metrics[0].resource.target.averageUtilization
#   scaling_complete (chaos, verification_spec) -> deployment reaches >= 2 replicas
# So the broken fixture must have a Deployment matching app=<target> with NO
# resources.requests/limits, spec.replicas == 1, and ZERO HPAs in the
# namespace.
#
# Dialect: python3 over `kubectl get -o json`, NOT kubectl -o jsonpath.
# kubectl jsonpath cannot express this correctly: (1) the verifier's op is
# "exists" on ...resources.requests, and jsonpath_ng.ext (what the real
# verifier uses) counts an EMPTY dict `requests: {}` as existing, while
# kubectl jsonpath returns an empty string with rc=0 for both "key missing"
# and "key present but empty" -- it cannot tell those apart. Verified
# empirically: jsonpath_ng.ext finds 1 match for `requests: {}` and 0 for
# `resources: {}`. (2) the verifier targets by label selector, so 0-match vs
# 1-match vs N-match must be distinguished, which kubectl jsonpath over a
# List flattens away. python3 is already a hard dependency of this harness.
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=scripts/isorun/_guards.sh
source "$SCRIPT_DIR/../_guards.sh"

NS="${NAMESPACE:-default}"
TARGET="${TARGET_DEPLOYMENT_NAME:-scale-target}"

fail() {
  echo "PREFLIGHT FAIL [optimize-scale]: $*" >&2
  exit 1
}

# --- fixture present, unsized, and not pre-scaled ---------------------------
# The python body lives in a temp file rather than a heredoc piped straight
# into `python3 -`: a heredoc attached to the same command as an incoming
# pipe overrides that command's stdin, so `kubectl ... | python3 - <<'EOF'`
# would hand the script text itself to json.load(sys.stdin), not the piped
# JSON. Verified empirically. Writing the heredoc to a file first, then
# piping JSON into `python3 <file>`, keeps stdin free for the real data.
tmp_py="$(mktemp)"
trap 'rm -f "$tmp_py"' EXIT
cat > "$tmp_py" <<'PYEOF'
import json, sys

ns, target = sys.argv[1], sys.argv[2]
items = json.load(sys.stdin).get("items", [])

if len(items) != 1:
    print(
        f"PREFLIGHT FAIL [optimize-scale]: fixture ABSENT/AMBIGUOUS. Expected exactly 1 "
        f"deployment matching app={target} in namespace {ns}, found {len(items)}. "
        f"Run scripts/isorun/seed/optimize-scale.sh first, or run.sh without --no-seed.",
        file=sys.stderr,
    )
    sys.exit(1)

dep = items[0]
containers = dep["spec"]["template"]["spec"]["containers"]
resources = containers[0].get("resources") or {}

# Mirror jsonpath_ng's `exists`: the KEY being present is a pass, even if empty.
already = [k for k in ("requests", "limits") if k in resources]
if already:
    joined = " and ".join(already)
    print(
        f"PREFLIGHT FAIL [optimize-scale]: fixture ALREADY PASSING. containers[0].resources "
        f"already defines {joined} ({json.dumps(resources)}) before the agent ran. "
        f"This can happen on GKE Autopilot, whose resource-defaulting webhook injects "
        f"requests/limits on admission -- this fixture is not usable on that cluster. "
        f"Otherwise, re-seed with scripts/isorun/seed/optimize-scale.sh.",
        file=sys.stderr,
    )
    sys.exit(1)

replicas = dep["spec"].get("replicas", 1)
if replicas is None or replicas > 1:
    print(
        f"PREFLIGHT FAIL [optimize-scale]: fixture ALREADY PASSING. spec.replicas={replicas} "
        f"(expected 1). The chaos scaling_complete check (min_replicas=2) would be satisfied "
        f"without the agent creating any autoscaler. Re-seed with scripts/isorun/seed/optimize-scale.sh.",
        file=sys.stderr,
    )
    sys.exit(1)
PYEOF

kubectl get deployment -n "$NS" -l "app=$TARGET" -o json | python3 "$tmp_py" "$NS" "$TARGET"
rm -f "$tmp_py"
trap - EXIT

# --- the load-spike target Service must exist -------------------------------
if ! iso_resource_exists service "$TARGET" "$NS"; then
  fail "fixture INCOMPLETE. service/$TARGET missing in namespace $NS. The Planned Load Spike targets it; without it the chaos fault drives no load. Re-seed with scripts/isorun/seed/optimize-scale.sh."
fi

# --- false-pass guard: no HPA may exist yet ---------------------------------
hpa_count="$(kubectl get horizontalpodautoscaler -n "$NS" -o json \
  | python3 -c 'import json,sys; print(len(json.load(sys.stdin).get("items", [])))')"
if [ "$hpa_count" != "0" ]; then
  fail "fixture ALREADY PASSING. ${hpa_count} HorizontalPodAutoscaler(s) already exist in namespace $NS before the agent ran. hpa-configured evaluates every HPA in the namespace, so a pre-existing one can pass it without agent work. Re-seed with scripts/isorun/seed/optimize-scale.sh."
fi

echo "PREFLIGHT OK [optimize-scale]: deployment app=$TARGET present, unsized, replicas=1, 0 HPAs."
