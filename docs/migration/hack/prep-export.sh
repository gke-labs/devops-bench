#!/usr/bin/env bash
#
# prep-export.sh: packages files from gke-labs into a signed upstream branch on kubernetes-sigs.
# Run this from a clone of your fork of kubernetes-sigs/devops-bench.
#
# Prereqs:
#   git remote add gkelabs  https://github.com/gke-labs/devops-bench.git
#   git remote add upstream https://github.com/kubernetes-sigs/devops-bench.git
#
# Usage:
#   ./hack/prep-export.sh --branch add-gemini-agent \
#       --paths "devops_bench/agents/cli/gemini.py tests/unit/agents/test_gemini.py"
#
#   ./hack/prep-export.sh --branch add-gemini-agent --interactive   # carve a sub-file slice
#
set -euo pipefail

BRANCH=""
PATHS=""
BASE="upstream/main"
SRC_REF="gkelabs/main"
INTERACTIVE="false"
MSG=""

die() { echo "error: $*" >&2; exit 1; }

while [[ $# -gt 0 ]]; do
  case "$1" in
    --branch)      BRANCH="$2"; shift 2 ;;
    --paths)       PATHS="$2"; shift 2 ;;
    --base)        BASE="$2"; shift 2 ;;
    --src-ref)     SRC_REF="$2"; shift 2 ;;
    --message|-m)  MSG="$2"; shift 2 ;;
    --interactive) INTERACTIVE="true"; shift ;;
    -h|--help)     sed -n '2,30p' "$0"; exit 0 ;;
    *)             die "unknown arg: $1" ;;
  esac
done

[[ -n "$BRANCH" ]] || die "--branch is required"
git remote get-url gkelabs  >/dev/null 2>&1 || die "missing remote 'gkelabs' (see header)"
git remote get-url upstream >/dev/null 2>&1 || die "missing remote 'upstream' (see header)"
[[ -z "$(git status --porcelain)" ]] || die "working tree is dirty; commit or stash first"

echo ">> fetching incubator and upstream..."
git fetch --quiet gkelabs
git fetch --quiet upstream

echo ">> creating branch '$BRANCH' off $BASE"
git checkout -q -B "$BRANCH" "$BASE"

if [[ "$INTERACTIVE" == "true" ]]; then
  # Stage full content, then reset to let the user select changes with `git add -p`
  echo ">> interactive mode: staging full content from $SRC_REF, then 'git add -p'"
  git checkout "$SRC_REF" -- . 2>/dev/null || true
  git reset -q
  git add -p
else
  [[ -n "$PATHS" ]] || die "--paths is required unless --interactive"
  read -ra path_arr <<< "$PATHS"      # split paths on whitespace into an array
  echo ">> importing paths from $SRC_REF:"
  for p in "${path_arr[@]}"; do echo "     $p"; done
  git checkout "$SRC_REF" -- "${path_arr[@]}"
  git add -- "${path_arr[@]}"
fi

if git diff --cached --quiet; then
  die "nothing staged, aborting (check your --paths / selection)"
fi

[[ -n "$MSG" ]] || MSG="migrate: ${BRANCH//-/ }"
echo ">> committing (DCO sign-off, your authorship)"
git commit -s -m "$MSG"

cat <<EOF

✓ Prepared branch '$BRANCH'. Review it, then:

    git show --stat
    git push origin "$BRANCH"
    gh pr create --repo kubernetes-sigs/devops-bench --base main --fill

Respond to the approver with follow-up commits on this branch.
EOF
