#!/usr/bin/env bash
# Launches one devops-bench task from an isolated scratch workspace, after
# running the task's pre-run cleanup hook (if any), its seed hook (if any),
# and its preflight guard (if any).
#
# Usage: run.sh <task.yaml-path> [gemini|oc] [--no-infra|--infra] [--keep] [--no-seed]
set -euo pipefail

usage() {
  cat <<'USAGE' >&2
Usage: run.sh <task.yaml-path> [gemini|oc] [--no-infra|--infra] [--keep] [--no-seed]

  <task.yaml-path>  Path to a task.yaml, absolute or relative to the repo root.
  gemini|oc         Agent to run (default: gemini).
  --no-infra        Skip infra provisioning; reuse the ambient cluster (default).
  --infra           Provision infra via tofu (required for tofu-seeded tasks).
  --keep            Do not delete the scratch workspace on exit.
  --no-seed         Skip the cleanup, seed, and preflight hooks entirely; run
                    against whatever state is already on the cluster,
                    unchecked. Use this when you deliberately want to test
                    against custom or partially-modified cluster state rather
                    than the canonical fixture.
USAGE
}

if [[ $# -lt 1 || "$1" == "-h" || "$1" == "--help" ]]; then
  usage
  exit 1
fi

TASK_ARG="$1"; shift
AGENT="gemini"
MODE="--no-infra"
KEEP=0
NO_SEED=0

for arg in "$@"; do
  case "$arg" in
    gemini|oc) AGENT="$arg" ;;
    --no-infra|--infra) MODE="$arg" ;;
    --keep) KEEP=1 ;;
    --no-seed) NO_SEED=1 ;;
    *)
      echo "run.sh: unknown argument: $arg" >&2
      usage
      exit 1
      ;;
  esac
done

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=scripts/isorun/_common.sh
source "$SCRIPT_DIR/_common.sh"
# shellcheck source=scripts/isorun/_guards.sh
source "$SCRIPT_DIR/_guards.sh"

if [[ "$TASK_ARG" = /* ]]; then
  TASK_PATH="$TASK_ARG"
else
  TASK_PATH="$REPO/$TASK_ARG"
fi

if [[ ! -f "$TASK_PATH" ]]; then
  echo "run.sh: task file not found: $TASK_PATH" >&2
  exit 1
fi

TASKNAME="$(basename "$(dirname "$TASK_PATH")")"

echo "==> Task: $TASKNAME ($TASK_PATH)"
echo "==> Agent: $AGENT, mode: $MODE"

# Hard refusal BEFORE the pin below: for tasks whose cleanup hook runs
# `kubectl delete namespace`, a stray ambient NAMESPACE pointed at a protected
# system namespace must abort loudly here, rather than either being silently
# discarded by the pin (which would hide a misconfigured shell from the user)
# or, worse, reaching a `kubectl delete namespace` call. Pure string check: no
# kubectl call, so this always runs, dry-run or not.
case "$TASKNAME" in
  cp-recovery|cve-remediation|migration-and-upgrade|opa-remediation|secret-rotation|spot-rebalancing)
    if [[ -n "${NAMESPACE:-}" ]]; then
      iso_refuse_protected_namespace "$NAMESPACE"
    fi
    ;;
esac

# Special-case the NAMESPACE for stacks with a non-default one; computed here
# so both the cleanup hook (below) and the harness invocation see it. These
# assignments are authoritative (unconditional, not "${NAMESPACE:-x}"): an
# unrelated ambient NAMESPACE must never redirect a destructive delete meant
# for one of these pinned namespaces. fix-config and deploy-config hardcode
# namespace: default in every verification_entries check; their own preflight
# now aborts if NAMESPACE requests anything else (see preflight/fix-config.sh
# and preflight/deploy-config.sh). optimize-scale grades against whatever
# {{NAMESPACE}} the matrix orchestrator substitutes (default "default"), so it
# has no single fixed value to check against.
case "$TASKNAME" in
  secret-rotation) NAMESPACE="secret-rotation" ;;
  cp-recovery) NAMESPACE="cp-recovery" ;;
  migration-and-upgrade) NAMESPACE="migration" ;;
  spot-rebalancing) NAMESPACE="apps" ;;
  fix-config|deploy-config|optimize-scale) NAMESPACE="${NAMESPACE:-default}" ;;
  *) ;;
esac

# Verify kubectl actually points at $CLUSTER before touching anything. Reads
# only (no mutation), so this could run for real even under a dry run; it is
# still gated the same way as the other steps below purely so a dry run in an
# environment with no live kubeconfig (e.g. CI) does not fail on this check.
if [[ "${ISORUN_DRYRUN:-0}" == "1" ]]; then
  echo "[dry-run] would verify kubectl context matches CLUSTER=$CLUSTER"
else
  iso_verify_cluster_context "$CLUSTER"
fi

CLEANUP_HOOK="$SCRIPT_DIR/cleanup/$TASKNAME.sh"
SEED_HOOK="$SCRIPT_DIR/seed/$TASKNAME.sh"
PREFLIGHT_HOOK="$SCRIPT_DIR/preflight/$TASKNAME.sh"

# The preflight gate is mandatory, not opt-in by filename: a task with a
# cleanup or seed hook but no preflight would get the destructive half of this
# harness with none of the protective half (a re-run could grade a fixture
# that is missing or already fixed and report a perfect score). Skippable only
# via --no-seed, which now skips the destructive half too (see below).
if [[ "$NO_SEED" -eq 0 ]]; then
  if { [[ -f "$CLEANUP_HOOK" ]] || [[ -f "$SEED_HOOK" ]]; } && [[ ! -f "$PREFLIGHT_HOOK" ]]; then
    cat <<ABORT >&2
==> ABORT: task '$TASKNAME' has a cleanup and/or seed hook but no preflight
    guard at:
      $PREFLIGHT_HOOK
    Running the destructive cleanup/seed half of this harness with no
    preflight guard can produce a meaningless score: an agent could be graded
    against a fixture that is missing, already fixed, or left over from a
    prior run, and still report a perfect result. Write $PREFLIGHT_HOOK before
    running this task, or pass --no-seed to explicitly skip cleanup, seed, and
    preflight, and run against whatever is already on the cluster, unchecked.
ABORT
    exit 1
  fi
fi

# Per-cluster lock: serializes the whole cleanup -> seed -> preflight ->
# harness sequence, so two concurrent isorun invocations against the same
# cluster cannot cross-credit each other via shared fixture objects. flock's
# lock is tied to the open file descriptor below, so it cannot leak a stale
# lock if this script is killed: the kernel releases it the moment the
# process dies, no matter how.
LOCKFILE="/tmp/isorun-$CLUSTER.lock"
if command -v flock >/dev/null 2>&1; then
  exec 9>"$LOCKFILE"
  if ! flock -n 9; then
    echo "==> ABORT: another isorun run already holds the lock for cluster '$CLUSTER' ($LOCKFILE). Wait for it to finish, then retry." >&2
    exit 1
  fi
  echo "==> Acquired per-cluster lock: $LOCKFILE"
else
  cat <<WARN >&2
############################################################
WARNING: 'flock' is not available (macOS does not ship it by default).
Concurrent isorun runs against cluster '$CLUSTER' are NOT serialized: two
simultaneous runs can seed/grade over top of each other and cross-credit
results. Install flock (e.g. via Homebrew: 'brew install flock') for real
protection. Continuing WITHOUT a lock.
############################################################
WARN
fi

if [[ "$NO_SEED" -eq 1 ]]; then
  echo "==> --no-seed: skipping cleanup, seed, and preflight hooks for task '$TASKNAME'; running against whatever is already on the cluster, unchecked."
else
  if [[ -x "$CLEANUP_HOOK" ]]; then
    if [[ "${ISORUN_DRYRUN:-0}" == "1" ]]; then
      echo "[dry-run] would run cleanup: $CLEANUP_HOOK"
    else
      echo "==> Running pre-run cleanup hook: $CLEANUP_HOOK"
      CLUSTER="$CLUSTER" PROJECT="$PROJECT" REGION="$REGION" NAMESPACE="${NAMESPACE:-}" "$CLEANUP_HOOK"
    fi
  elif [[ -f "$CLEANUP_HOOK" ]]; then
    echo "==> ABORT: cleanup hook exists but is not executable: $CLEANUP_HOOK. Run 'chmod +x $CLEANUP_HOOK' and retry." >&2
    exit 1
  else
    echo "==> No cleanup hook for task '$TASKNAME'; skipping pre-run reset."
  fi

  if [[ -x "$SEED_HOOK" ]]; then
    if [[ "${ISORUN_DRYRUN:-0}" == "1" ]]; then
      echo "[dry-run] would run seed: $SEED_HOOK"
    else
      echo "==> Running seed hook: $SEED_HOOK"
      CLUSTER="$CLUSTER" PROJECT="$PROJECT" REGION="$REGION" NAMESPACE="${NAMESPACE:-}" "$SEED_HOOK"
    fi
  elif [[ -f "$SEED_HOOK" ]]; then
    echo "==> ABORT: seed hook exists but is not executable: $SEED_HOOK. Run 'chmod +x $SEED_HOOK' and retry." >&2
    exit 1
  else
    echo "==> No seed hook for task '$TASKNAME'; skipping fixture seeding."
  fi

  if [[ -x "$PREFLIGHT_HOOK" ]]; then
    if [[ "${ISORUN_DRYRUN:-0}" == "1" ]]; then
      echo "[dry-run] would run preflight: $PREFLIGHT_HOOK"
    else
      echo "==> Running preflight guard: $PREFLIGHT_HOOK"
      if ! CLUSTER="$CLUSTER" PROJECT="$PROJECT" REGION="$REGION" NAMESPACE="${NAMESPACE:-}" "$PREFLIGHT_HOOK"; then
        # Reorder-vs-cleanup-on-abort: reordering (preflight before seed) is
        # not viable here, because every preflight validates the POST-seed
        # state (e.g. "the fixture exists and is still unsized"); it has
        # nothing to check before seeding. So instead, on abort, re-run the
        # cleanup hook to tear down whatever the seed just created. This
        # keeps the fixture faithful to the tofu source (e.g. optimize-scale's
        # LoadBalancer Service stays a real LoadBalancer, matching the tofu
        # stack) while still guaranteeing a failed guard cannot leave a
        # billable object provisioned on the cluster.
        echo "==> Preflight failed for task '$TASKNAME'. Tearing down what the seed step just created, so a failed guard cannot leave a billable object provisioned." >&2
        if [[ -x "$CLEANUP_HOOK" ]]; then
          CLUSTER="$CLUSTER" PROJECT="$PROJECT" REGION="$REGION" NAMESPACE="${NAMESPACE:-}" "$CLEANUP_HOOK" || echo "==> WARNING: post-abort cleanup also failed; check the cluster by hand for leftover objects from task '$TASKNAME'." >&2
        fi
        echo "==> ABORT: preflight guard failed for task '$TASKNAME'. The cluster is not in the expected pre-agent state (see the PREFLIGHT FAIL message above). Re-seed or investigate cluster drift before running again; refusing to launch the agent against an untrustworthy fixture." >&2
        exit 1
      fi
    fi
  elif [[ -f "$PREFLIGHT_HOOK" ]]; then
    echo "==> ABORT: preflight guard exists but is not executable: $PREFLIGHT_HOOK. Run 'chmod +x $PREFLIGHT_HOOK' and retry." >&2
    exit 1
  else
    echo "==> No preflight guard for task '$TASKNAME'; skipping pre-agent state check."
  fi
fi

# The tofu/--no-infra state warning below is now redundant for any task with a
# seed hook: seed/$TASKNAME.sh and preflight/$TASKNAME.sh handle establishing
# and verifying that state instead. Only tasks without one still need it.
if [[ "$MODE" == "--no-infra" ]] && grep -Eq 'deployer:[[:space:]]*"tofu"' "$TASK_PATH" && [[ ! -x "$SEED_HOOK" ]]; then
  cat <<WARN >&2
############################################################
WARNING: task '$TASKNAME' uses deployer: "tofu" and depends on
tofu-SEEDED cluster state (broken configs, Kyverno policies, bare
GitOps repos, etc). --no-infra will NOT seed that state; it only
reuses the ambient cluster. If the seed isn't already present,
re-run with --infra or seed the stack manually before continuing.
############################################################
WARN
fi

if [[ -n "${NAMESPACE:-}" ]]; then
  export NAMESPACE
fi

case "$AGENT" in
  gemini) iso_auth_gemini ;;
  oc) iso_auth_oc ;;
esac

export GKE_CLUSTER_NAME="$CLUSTER"
export AGENT_TIMEOUT_SEC="${AGENT_TIMEOUT_SEC:-1800}"

RESULTS_ROOT="$REPO/results/iso-$TASKNAME"
CMD=(uv run --project "$REPO" python -m devops_bench "$MODE" --project "$PROJECT" --cluster "$CLUSTER" --results-root "$RESULTS_ROOT" "$TASK_PATH")

WS="$(iso_stage_ws)"
if [[ "$KEEP" -eq 0 ]]; then
  trap 'rm -rf "$WS"' EXIT
fi

echo "==> Isolated workspace: $WS"
echo "==> Results root: $RESULTS_ROOT"

if [[ "${ISORUN_DRYRUN:-0}" == "1" ]]; then
  echo "==> [dry-run] would cd to $WS and run:"
  printf '%q ' "${CMD[@]}"
  echo
else
  cd "$WS"
  "${CMD[@]}"
fi

echo "==> Results: $RESULTS_ROOT"
echo "==> Audit reminder: judge this run by the verification_entries results under $RESULTS_ROOT, not by kubectl's own output or the agent's narration. kubectl printing 'created' or 'configured' only confirms a write happened; it does not confirm the fix was correct, and a fixture that was never actually broken would print the exact same thing."
