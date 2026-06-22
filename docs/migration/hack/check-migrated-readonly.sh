#!/usr/bin/env bash
#
# check-migrated-readonly.sh: blocks gke-labs PRs from editing paths listed in migrated.bara.sky.
# Exempts back-sync PRs. Runs in gke-labs CI.
#
# Usage (CI):
#   BASE_REF=origin/main ./hack/check-migrated-readonly.sh
#
set -euo pipefail

MANIFEST="${MANIFEST:-migrated.bara.sky}"
BASE_REF="${BASE_REF:-origin/main}"
# PR head branch (set by CI). Exempts backsync/* branches used by the sync bot.
HEAD_REF="${HEAD_REF:-}"

case "$HEAD_REF" in
  backsync/*) echo "OK: back-sync branch ($HEAD_REF) is exempt from the read-only guard."; exit 0 ;;
esac

# Bypass check if MIGRATED_OVERRIDE=1 or PR has the 'migrated-override' label.
# Note: local edits will be overwritten by backsync unless also committed upstream.
OVERRIDE_LABEL="${OVERRIDE_LABEL:-migrated-override}"
if [[ "${MIGRATED_OVERRIDE:-}" == "1" ]] || [[ " ${PR_LABELS:-} " == *" $OVERRIDE_LABEL "* ]]; then
  echo "OK: edits to migrated paths overridden by the '$OVERRIDE_LABEL' label."
  echo "    Reminder: make the same change in kubernetes-sigs, or the back-sync will revert it here."
  exit 0
fi

[[ -f "$MANIFEST" ]] || { echo "OK: no $MANIFEST manifest; nothing is locked yet."; exit 0; }

# Parse active (uncommented) paths from migrated.bara.sky.
# Uses while-read for compatibility with macOS Bash 3.2.
PATTERNS=()
while IFS= read -r line; do
  [[ -n "$line" ]] && PATTERNS+=("$line")
done < <(sed 's/#.*//' "$MANIFEST" | grep -oE '"[^"]+"' | tr -d '"')

if [[ ${#PATTERNS[@]} -eq 0 ]]; then
  echo "OK: $MANIFEST is empty; no migrated paths are locked yet (Phase 1 no-op)."
  exit 0
fi

# Get changed files in the PR range. Falls back to two-dot diff if three-dot fails.
if ! diff_out="$(git diff --name-only "$BASE_REF"...HEAD -- 2>/dev/null)"; then
  diff_out="$(git diff --name-only "$BASE_REF" HEAD --)"
fi

CHANGED=()
while IFS= read -r line; do
  [[ -n "$line" ]] && CHANGED+=("$line")
done <<< "$diff_out"

violations=()
if [[ ${#CHANGED[@]} -gt 0 ]]; then     # guard: empty-array expansion is unbound under bash 3.2 set -u
  for f in "${CHANGED[@]}"; do
    for p in "${PATTERNS[@]}"; do
      # Match file against globs, or check if it starts with the directory prefix.
      # shellcheck disable=SC2053  # intentional glob match of $p against $f
      if [[ "$f" == $p || "$f" == $p/* ]]; then violations+=("$f  (matches '$p')"); break; fi
    done
  done
fi

if [[ ${#violations[@]} -gt 0 ]]; then
  echo "FAIL: this PR edits paths that have migrated to kubernetes-sigs (now their source of truth):" >&2
  for v in "${violations[@]}"; do echo "  - $v" >&2; done
  echo >&2
  echo "Make these changes in kubernetes-sigs/devops-bench instead; the back-sync bot will mirror" >&2
  echo "them back here. (If a module was un-migrated on purpose, remove its line from $MANIFEST.)" >&2
  exit 1
fi

echo "OK: no edits to migrated (read-only) paths."
