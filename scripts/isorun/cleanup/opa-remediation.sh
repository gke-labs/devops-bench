#!/usr/bin/env bash
# Pre-run reset for tasks/common/opa-remediation. Idempotent: safe to run
# when nothing exists.
set -euo pipefail

: "${CLUSTER:=autopilot-cluster-1}"
: "${PROJECT:=}"
: "${REGION:=us-central1}"
: "${NAMESPACE:=}"

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=scripts/isorun/_guards.sh
source "$SCRIPT_DIR/../_guards.sh"
iso_refuse_protected_namespace team-alpha team-beta team-gamma

echo "==> opa-remediation cleanup: deleting namespaces team-alpha, team-beta, team-gamma (cluster: $CLUSTER)"
kubectl delete namespace team-alpha team-beta team-gamma --ignore-not-found --wait=true --timeout=120s
# Leave the kyverno namespace (and its controllers) alone.

# Unlike the tofu-managed cluster resources above, ~/opa-repo-$CLUSTER.git is
# NOT cleaned by tofu destroy, so it must be removed here for a clean reseed.
echo "==> opa-remediation cleanup: removing $HOME/opa-repo-$CLUSTER.git"
rm -rf "${HOME:?}/opa-repo-$CLUSTER.git"
