#!/usr/bin/env bash
# Pure guard/helper functions shared by scripts/isorun/*.sh. Source this, do
# not execute it.
#
# Unlike _common.sh, nothing in this file inspects or assigns to CLUSTER,
# PROJECT, REGION, or NAMESPACE at source time: it is safe to source from a
# cleanup or preflight hook without clobbering values that hook already
# received from run.sh's own invocation of it.

# Aborts if any argument names a protected Kubernetes system namespace.
# Call this immediately before any `kubectl delete namespace`, so a stray
# ambient NAMESPACE can never cause a cleanup hook to delete a namespace it
# does not own.
iso_refuse_protected_namespace() {
  local ns
  for ns in "$@"; do
    case "$ns" in
      default|kube-system|kube-public|kube-node-lease)
        echo "REFUSE: '$ns' is a protected Kubernetes system namespace; refusing to delete it. If this is unexpected, check for a stray ambient NAMESPACE in your shell." >&2
        exit 1
        ;;
    esac
  done
}

# Usage: iso_resource_exists <kind> <name> <namespace>
# Returns 0 (true) if the resource exists, 1 (false) if kubectl genuinely
# reports it as absent, and aborts loudly on any other kubectl error
# (Forbidden, timeout, wrong context, an apiserver flake), so a preflight
# guard can never mistake "the query itself failed" for "the resource is
# absent". `kubectl get --ignore-not-found` returns EMPTY OUTPUT with rc 0 for
# a genuine NotFound, and a NONZERO exit (with stderr set) for every other
# failure mode; that is the distinction this depends on.
iso_resource_exists() {
  local kind="$1" name="$2" ns="$3"
  local out
  if ! out="$(kubectl get "$kind" "$name" -n "$ns" --ignore-not-found -o name 2>&1)"; then
    echo "PREFLIGHT ERROR: kubectl get $kind/$name -n $ns failed, and it was not a NotFound: $out" >&2
    exit 1
  fi
  [[ -n "$out" ]]
}
