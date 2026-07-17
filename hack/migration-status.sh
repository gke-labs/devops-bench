#!/usr/bin/env bash
#
# migration-status.sh: reports migration progress by comparing migrated.bara.sky and upstream main.
# --suggest-flips lists/uncomments entries whose upstream CONTENT matches gke-labs (blob parity).
#
# Usage:
#   ./hack/migration-status.sh
#   ./hack/migration-status.sh --suggest-flips --upstream-tree <file>          # report ready-to-flip
#   ./hack/migration-status.sh --suggest-flips --apply --upstream-tree <file>  # uncomment them
#
# <file> is the FULL upstream tree listing WITH blob hashes:
#   git ls-tree -r upstream/main   (mode type sha<TAB>path — NOT --name-only)
#
# An entry flips only when every local file it covers exists upstream with an identical blob
# hash. Mere path existence is not enough: upstream placeholders (an empty tasks/README.md) and
# same-named-but-different files (a sigs-native AGENTS.md) must never flip ownership. Entries
# tagged with a trailing `# flip-group: <name>` comment flip atomically: none of the group
# flips until every member is content-ready (used to couple a task with its tf stack).
#
set -euo pipefail

MANIFEST="${MANIFEST:-migrated.bara.sky}"
SRC="${SRC:-devops_bench}"
UPSTREAM="${UPSTREAM:-kubernetes-sigs/devops-bench}"
MODE="status"
APPLY="false"
UPSTREAM_TREE=""

while [[ $# -gt 0 ]]; do
  case "$1" in
    --manifest)       MANIFEST="$2"; shift 2 ;;
    --src)            SRC="$2"; shift 2 ;;
    --upstream)       UPSTREAM="$2"; shift 2 ;;
    --suggest-flips)  MODE="suggest"; shift ;;
    --apply)          APPLY="true"; shift ;;
    --upstream-tree)  UPSTREAM_TREE="$2"; shift 2 ;;
    --upstream-files) echo "error: --upstream-files (name-only) was replaced by --upstream-tree" >&2
                      echo "       (existence is not migration; pass 'git ls-tree -r <ref>' output)" >&2
                      exit 2 ;;
    -h|--help)        sed -n '2,20p' "$0"; exit 0 ;;
    *) echo "unknown arg: $1" >&2; exit 2 ;;
  esac
done

[[ -f "$MANIFEST" ]] || { echo "error: manifest '$MANIFEST' not found (run from repo root)" >&2; exit 1; }

# --- suggest-flips: auto-uncomment entries whose content has landed upstream -----------------
if [[ "$MODE" == "suggest" ]]; then
  [[ -n "$UPSTREAM_TREE" && -f "$UPSTREAM_TREE" ]] \
    || { echo "error: --suggest-flips needs --upstream-tree <file> (git ls-tree -r <upstream-ref>)" >&2; exit 2; }
  grep -qE $'^[0-9]+ blob [0-9a-f]{40,64}\t' "$UPSTREAM_TREE" \
    || { echo "error: $UPSTREAM_TREE has no blob hashes; generate it with 'git ls-tree -r <ref>' (not --name-only)" >&2; exit 2; }

  LOCAL_TREE="$(mktemp)"
  trap 'rm -f "$LOCAL_TREE"' EXIT
  git ls-tree -r HEAD > "$LOCAL_TREE"

  MANIFEST="$MANIFEST" UPSTREAM_TREE="$UPSTREAM_TREE" APPLY="$APPLY" \
    LOCAL_TREE="$LOCAL_TREE" python3 - <<'PYEOF'
import os, re, sys

manifest_path = os.environ["MANIFEST"]
apply_mode = os.environ["APPLY"] == "true"

def read_tree(path):
    """Parse `git ls-tree -r` output into {path: blob_sha}."""
    tree = {}
    with open(path, encoding="utf-8") as f:
        for line in f:
            line = line.rstrip("\n")
            if not line or "\t" not in line:
                continue
            meta, fpath = line.split("\t", 1)
            parts = meta.split()
            if len(parts) == 3 and parts[1] == "blob":
                tree[fpath] = parts[2]
    return tree

local = read_tree(os.environ["LOCAL_TREE"])
upstream = read_tree(os.environ["UPSTREAM_TREE"])

# Commented manifest entry, optionally tagged: # "path/**",  # flip-group: name
entry_re = re.compile(r'^(\s*)#\s*("([^"]+)",)\s*(?:#\s*flip-group:\s*(\S+))?\s*$')

entries = []  # (lineno, path, group)
lines = open(manifest_path, encoding="utf-8").read().splitlines(keepends=True)
for i, line in enumerate(lines):
    m = entry_re.match(line)
    if m:
        entries.append((i, m.group(3), m.group(4)))

def covered_files(path):
    """Local files an entry covers. `p/**` is recursive, `p/*` single level, else exact."""
    if path.endswith("/**"):
        prefix = path[:-2]
        return sorted(f for f in local if f.startswith(prefix))
    if path.endswith("/*"):
        prefix = path[:-1]
        return sorted(f for f in local if f.startswith(prefix) and "/" not in f[len(prefix):])
    return [path] if path in local else []

def check(path):
    """Returns (ready, reason)."""
    files = covered_files(path)
    if not files:
        return False, "no local files match (stale manifest entry?)"
    missing = [f for f in files if f not in upstream]
    if missing:
        return False, f"{len(missing)}/{len(files)} file(s) not upstream yet (e.g. {missing[0]})"
    differ = [f for f in files if upstream[f] != local[f]]
    if differ:
        return False, f"{len(differ)}/{len(files)} file(s) differ from upstream (e.g. {differ[0]})"
    return True, f"all {len(files)} file(s) match upstream"

results = {path: check(path) for _, path, _ in entries}

# A flip-group is ready only when every member is ready.
groups = {}
for _, path, group in entries:
    if group:
        groups.setdefault(group, []).append(path)

to_flip, held, pending = [], [], []
for lineno, path, group in entries:
    ready, reason = results[path]
    if not ready:
        pending.append((path, reason))
    elif group and not all(results[p][0] for p in groups[group]):
        waiting = next(p for p in groups[group] if not results[p][0])
        held.append((path, f"flip-group '{group}' not complete (waiting on {waiting})"))
    else:
        to_flip.append((lineno, path))

if pending:
    print(f"Not ready ({len(pending)}):")
    for path, reason in pending:
        print(f"  - {path}: {reason}")
if held:
    print(f"Held back by flip-group ({len(held)}):")
    for path, reason in held:
        print(f"  ~ {path}: {reason}")
if not to_flip:
    print("No commented frontier entries have full content parity upstream yet; nothing to flip.")
    sys.exit(0)

print(f"Ready to flip (content matches upstream, still commented): {len(to_flip)}")
for _, path in to_flip:
    print(f"  + {path}")

if apply_mode:
    for lineno, _ in to_flip:
        lines[lineno] = re.sub(r'^(\s*)#\s*', r'\1', lines[lineno], count=1)
    with open(manifest_path, "w", encoding="utf-8") as f:
        f.writelines(lines)
    print(f"Uncommented {len(to_flip)} entries in {manifest_path}.")
else:
    print(f"(run with --apply to uncomment these in {manifest_path})")
PYEOF
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
