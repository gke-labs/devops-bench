#!/usr/bin/env bash
#
# backsync.sh: Run the kubernetes-sigs -> gke-labs back-sync.
# Maps to .github/workflows/backsync.yml. Dry-run first.
#
# Auth: Needs GITHUB_TOKEN with push/PR access to gke-labs/devops-bench.
# For local dry-run: export GITHUB_TOKEN="$(gh auth token)"
# For real run:      export GITHUB_TOKEN="$SYNC_BOT_TOKEN"
# Git committer is always stamped as devops-bench-sync-bot.
#
# Usage:
#   ./hack/backsync.sh --dry-run
#   ./hack/backsync.sh
#
set -euo pipefail

COPYBARA_IMAGE="${COPYBARA_IMAGE:-anipos/copybara:latest}"
WORKFLOW="${WORKFLOW:-backsync}"
CONFIG="${CONFIG:-copy.bara.sky}"
EXTRA_ARGS=()

while [[ $# -gt 0 ]]; do
  case "$1" in
    --dry-run)   EXTRA_ARGS+=("--dry-run"); shift ;;
    --workflow)  WORKFLOW="$2"; shift 2 ;;
    --config)    CONFIG="$2"; shift 2 ;;
    -h|--help)   sed -n '2,12p' "$0"; exit 0 ;;
    *)           EXTRA_ARGS+=("$1"); shift ;;
  esac
done

[[ -f "$CONFIG" ]] || { echo "error: $CONFIG not found (run from repo root)" >&2; exit 1; }
command -v docker >/dev/null 2>&1 || { echo "error: docker is required but not found on PATH" >&2; exit 1; }
: "${GITHUB_TOKEN:?set GITHUB_TOKEN (e.g. export GITHUB_TOKEN=\$(gh auth token))}"

echo ">> copybara $WORKFLOW  (image: $COPYBARA_IMAGE)  args: ${EXTRA_ARGS[*]:-none}"

set +e
# Mount /tmp to support local file:// sandbox testing in Copybara.
# Overwrite entrypoint to java to bypass buggy wrappers in some copybara images (like anipos/copybara).
docker run --rm \
  -v "$PWD":/usr/src/app \
  -v /tmp:/tmp \
  -w /usr/src/app \
  -e GITHUB_TOKEN \
  -e COPYBARA_CONFIG_ROOT=/usr/src/app \
  --entrypoint java \
  "$COPYBARA_IMAGE" \
  -jar /opt/copybara/copybara_deploy.jar \
  "$CONFIG" "$WORKFLOW" \
  --git-committer-name  "devops-bench-sync-bot" \
  --git-committer-email "devops-bench-sync-bot@google.com" \
  "${EXTRA_ARGS[@]}"
rc=$?
set -e

# exit 4 == nothing to migrate (frontier already in sync).
if [[ $rc -eq 4 ]]; then
  echo ">> frontier already in sync."
  exit 0
fi
exit $rc
