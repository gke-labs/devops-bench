#!/usr/bin/env bash
#
# migration-status.sh: reports migration progress by comparing migrated.bara.sky and upstream main.
# --suggest-flips lists/uncomments entries whose paths now exist upstream.
#
# Usage:
#   ./hack/migration-status.sh
#   ./hack/migration-status.sh --suggest-flips --upstream-files <file>          # report ready-to-flip
#   ./hack/migration-status.sh --suggest-flips --apply --upstream-files <file>  # uncomment them
#
set -euo pipefail

MANIFEST="${MANIFEST:-migrated.bara.sky}"
SRC="${SRC:-devops_bench}"
UPSTREAM="${UPSTREAM:-kubernetes-sigs/devops-bench}"
MODE="status"
APPLY="false"
UPSTREAM_FILES=""

while [[ $# -gt 0 ]]; do
  case "$1" in
    --manifest)       MANIFEST="$2"; shift 2 ;;
    --src)            SRC="$2"; shift 2 ;;
    --upstream)       UPSTREAM="$2"; shift 2 ;;
    --suggest-flips)  MODE="suggest"; shift ;;
    --apply)          APPLY="true"; shift ;;
    --upstream-files) UPSTREAM_FILES="$2"; shift 2 ;;
    -h|--help)        sed -n '2,18p' "$0"; exit 0 ;;
    *) echo "unknown arg: $1" >&2; exit 2 ;;
  esac
done

[[ -f "$MANIFEST" ]] || { echo "error: manifest '$MANIFEST' not found (run from repo root)" >&2; exit 1; }

# --- suggest-flips: auto-uncomment entries present upstream -----------------
# A commented path is ready to flip once it exists in upstream main.
if [[ "$MODE" == "suggest" ]]; then
  [[ -n "$UPSTREAM_FILES" && -f "$UPSTREAM_FILES" ]] \
    || { echo "error: --suggest-flips needs --upstream-files <file> (e.g. git ls-tree -r --name-only upstream/main)" >&2; exit 2; }

  to_flip=()
  while IFS= read -r path; do
    [[ -n "$path" ]] || continue
    case "$path" in
      *'/**') prefix="${path%/**}/"; awk -v p="$prefix" 'index($0,p)==1{f=1} END{exit f?0:1}' "$UPSTREAM_FILES" && to_flip+=("$path") ;;
      *'/*')  prefix="${path%/*}/";  awk -v p="$prefix" 'index($0,p)==1{f=1} END{exit f?0:1}' "$UPSTREAM_FILES" && to_flip+=("$path") ;;
      *)      grep -qxF -- "$path" "$UPSTREAM_FILES" && to_flip+=("$path") ;;
    esac
  done < <(grep -oE '^[[:space:]]*#[[:space:]]*"[^"]+"' "$MANIFEST" | grep -oE '"[^"]+"' | tr -d '"')

  if [[ ${#to_flip[@]} -eq 0 ]]; then
    echo "No commented frontier entries are present upstream yet; nothing to flip."
    exit 0
  fi

  echo "Ready to flip (present upstream, still commented): ${#to_flip[@]}"
  for p in "${to_flip[@]}"; do echo "  + $p"; done

  if [[ "$APPLY" == "true" ]]; then
    for path in "${to_flip[@]}"; do
      esc="$(printf '%s' "$path" | sed 's/[.*]/\\&/g')"   # escape regex metacharacters in paths
      sed -i.bak -E "s|^([[:space:]]*)#[[:space:]]*(\"${esc}\",)|\1\2|" "$MANIFEST"
    done
    rm -f "$MANIFEST.bak"
    echo "Uncommented ${#to_flip[@]} entries in $MANIFEST."
  else
    echo "(run with --apply to uncomment these in $MANIFEST)"
  fi
  exit 0
fi

# Parse active (uncommented) paths from migrated.bara.sky.
# Uses while-read for compatibility with macOS Bash 3.2.
MIGRATED=()
while IFS= read -r line; do
  [[ -n "$line" ]] && MIGRATED+=("$line")
done < <(sed 's/#.*//' "$MANIFEST" | grep -oE '"[^"]+"' | tr -d '"')

echo "== Migrated (${#MIGRATED[@]}) — kubernetes-sigs is source of truth, read-only in gke-labs =="
if [[ ${#MIGRATED[@]} -eq 0 ]]; then
  echo "  (none yet — still in Phase 1: restructure gke-labs before any forward PR)"
else
  for p in "${MIGRATED[@]}"; do echo "  ✓ $p"; done
fi

echo
echo "== In-flight upstream PRs ($UPSTREAM) =="
if command -v gh >/dev/null 2>&1; then
  gh pr list --repo "$UPSTREAM" --state open \
     --json number,title,headRefName \
     --template '{{range .}}  #{{.number}}  {{.title}}  ({{.headRefName}}){{"\n"}}{{end}}' \
     2>/dev/null || echo "  (could not query gh — check auth / repo exists yet)"
else
  echo "  (gh not installed; skipping)"
fi

echo
echo "== Coverage of top-level packages under $SRC/ =="
if [[ -d "$SRC" ]]; then
  remaining=0; partial=0
  while IFS= read -r dir; do
    pkg="$(basename "$dir")"
    prefix="$SRC/$pkg"
    state="remaining"
    if [[ ${#MIGRATED[@]} -gt 0 ]]; then
      for m in "${MIGRATED[@]}"; do
        # Check if package is fully or partially migrated
        if [[ "$m" == "$prefix" || "$m" == "$prefix/" || "$m" == "$prefix/*" || "$m" == "$prefix/**" ]]; then
          state="full"; break
        elif [[ "$m" == "$prefix/"* ]]; then
          [[ "$state" == "full" ]] || state="partial"
        fi
      done
    fi
    case "$state" in
      full)      echo "  ✓ $prefix/  (migrated)" ;;
      partial)   echo "  ◑ $prefix/  (partially migrated)"; partial=$((partial+1)) ;;
      remaining) echo "  ◻ $prefix/  (not started)"; remaining=$((remaining+1)) ;;
    esac
  done < <(find "$SRC" -mindepth 1 -maxdepth 1 -type d -not -name '__pycache__' | sort)
  echo
  echo "  $remaining not started, $partial partially migrated."
else
  echo "  (source directory not present yet)"
fi
