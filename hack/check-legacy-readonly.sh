#!/usr/bin/env bash
#
# check-legacy-readonly.sh: blocks PRs from ADDING TO or MODIFYING deprecated legacy codepaths
# without an explicit override. Deletions are always allowed — removing legacy is the goal.
# The canonical pipeline is devops_bench/; the paths below are frozen while they are retired.
# To intentionally add to or modify them, add the 'legacy-override' label to the PR (or set
# LEGACY_OVERRIDE=1 locally).
#
# Usage (CI):
#   BASE_REF=origin/main ./hack/check-legacy-readonly.sh
#
set -euo pipefail

BASE_REF="${BASE_REF:-origin/main}"
OVERRIDE_LABEL="${OVERRIDE_LABEL:-legacy-override}"

# Frozen legacy path prefixes (top-level only; the canonical deployers/ and skills/ live under
# devops_bench/). Adds/edits under these are blocked unless overridden; deletions are always
# allowed.
LEGACY_PATHS=(
  "pkg"
  "deployers"
  "skills"
)

# Bypass via LEGACY_OVERRIDE=1 or the 'legacy-override' PR label.
if [[ "${LEGACY_OVERRIDE:-}" == "1" ]] || [[ " ${PR_LABELS:-} " == *" $OVERRIDE_LABEL "* ]]; then
  echo "OK: edits to legacy paths overridden by the '$OVERRIDE_LABEL' label."
  echo "    Reminder: these paths are deprecated — prefer changing devops_bench/ instead."
  exit 0
fi

# Changed files with status. --no-renames splits a rename into delete+add, so moving a file OUT of a
# legacy path counts as an allowed deletion. Falls back to two-dot diff if three-dot fails.
if ! diff_out="$(git diff --no-renames --name-status "$BASE_REF"...HEAD -- 2>/dev/null)"; then
  diff_out="$(git diff --no-renames --name-status "$BASE_REF" HEAD --)"
fi

# Uses while-read for compatibility with macOS Bash 3.2.
violations=()
while IFS=$'\t' read -r status path _rest; do
  [[ -n "$path" ]] || continue
  [[ "$status" == D* ]] && continue     # deletions from legacy paths are always allowed
  for p in "${LEGACY_PATHS[@]}"; do
    if [[ "$path" == "$p" || "$path" == "$p"/* ]]; then
      violations+=("$status  $path  (legacy path '$p/')"); break
    fi
  done
done <<< "$diff_out"

if [[ ${#violations[@]} -gt 0 ]]; then
  echo "FAIL: this PR adds to or modifies deprecated legacy codepaths (deletions would be fine):" >&2
  for v in "${violations[@]}"; do echo "  - $v" >&2; done
  echo >&2
  echo "The canonical pipeline is devops_bench/. If you must add to or modify these paths, add the" >&2
  echo "'$OVERRIDE_LABEL' label to this PR (or set LEGACY_OVERRIDE=1 locally) to acknowledge it." >&2
  exit 1
fi

echo "OK: no additions or modifications to legacy codepaths (deletions are allowed)."
