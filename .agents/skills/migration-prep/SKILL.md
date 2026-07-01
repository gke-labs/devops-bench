---
name: migration-prep
description: Prepare the next upstream migration PR for devops-bench (gke-labs -> kubernetes-sigs). Invoke when the user wants to "send the next migration PR", "what migration PR is next", "prep the <module> export", "cut the next forward PR", or otherwise export a module to kubernetes-sigs using the migration toolkit. Picks the next PR from the wave plan + frontier + upstream state, builds a scoped export branch with prep-export.sh, carries along any not-yet-migrated dependencies, and gates it submit-ready with lint + tests before it goes out.
---

# Prepare a migration PR

Cut the next forward PR in the `gke-labs` -> `kubernetes-sigs` migration: pick the
right module, carve a clean scoped branch off `upstream/main`, make sure every
dependency it needs has already migrated (or travels with it), and prove it builds
green before it leaves. This skill **prepares** a PR up to `gh pr create`; it does
not merge, and it never flips the frontier (that is post-merge, automated).

The plan and process are the source of truth — **read them, don't re-derive them:**

- The wave/assignment plan (which PR is next, who owns it, exact paths, the
  import basis that fixes each PR's wave) → the **"PRs by wave"** table in
  [`../../../docs/migration/pr-plan.md`](../../../docs/migration/pr-plan.md).
- The per-PR runbook (prereqs, remotes, `prep-export.sh`, flips, back-sync,
  do's/don'ts) → [`../../../docs/migration/README.md`](../../../docs/migration/README.md).
- The migrated frontier (single source of truth for what has flipped) →
  [`migrated.bara.sky`](../../../migrated.bara.sky) at the repo root.

> The `hack/` scripts live at the repo root (`hack/prep-export.sh`, etc.). Run
> `prep-export.sh` from a **clone of your fork of `kubernetes-sigs/devops-bench`**
> with the three remotes wired (`origin`=your fork, `gkelabs`, `upstream`), not
> from a plain `gke-labs` clone.

---

## Flow

### 1. Establish current state (three inputs, live)

Do not trust any single source; reconcile all three, most-current wins:

1. **The plan** — read the "PRs by wave" table in
   [`pr-plan.md`](../../../docs/migration/pr-plan.md). Each row is one PR with its
   `Paths`, its `Imports (basis)` (the dependency that fixes its wave), and its
   `Owner`. This is the ordered backlog.
2. **What has landed / is in flight** — run the tracker, which also lists open
   upstream PRs, then fetch the real upstream file list (ground truth, fresher
   than the frontier):
   ```bash
   ./hack/migration-status.sh                 # migrated frontier + open upstream PRs
   git fetch --quiet upstream
   git ls-tree -r --name-only upstream/main   # what actually exists upstream now
   ```
3. **The frontier** — read [`migrated.bara.sky`](../../../migrated.bara.sky):
   an **uncommented** path is *flipped* (merged upstream **and** locked read-only
   in gke-labs). A path merged upstream but not yet flipped is still mid-cutover.

### 2. Resolve the owner, then pick the next PR

First identify **who you are**, so the plan can be filtered to your lane. Resolve
the owner in this order:

1. If the user named an owner, use that.
2. Otherwise read `git config user.name` and match it to an owner in the §3.2 /
   §3.4 tables on given name (e.g. `pradeepvrd` or "Pradeep Varadharajan" →
   **Pradeep**).
3. If neither yields a confident match, **ask the user** which owner they are,
   listing the plan's owners — do not guess.

Then classify each plan row:

- **MERGED** — its `Paths` already exist on `upstream/main`. Skip.
- **IN FLIGHT** — an open upstream PR already covers it. Skip (don't duplicate);
  offer to help finish it instead.
- **BLOCKED** — one or more of its `Imports (basis)` is not yet **merged upstream
  and flipped**. Cannot go yet.
- **READY** — everything in its `Imports (basis)` is merged + flipped, and it is
  neither merged nor in flight.

Pick the **earliest-wave READY** row owned by the resolved owner (lowest wave
number first; within a wave any order — wave rows are mutually independent by
construction). If that owner has no READY row, say so and offer the earliest READY
row across all owners. Report the choice with its paths and *why it is unblocked*
(which imports are satisfied), and name what is still BLOCKED behind it. If nothing
is READY anywhere, say which merges/flips must land first — don't force a premature
PR.

### 3. Resolve exact paths + carry-along dependencies

This is the step that keeps the boundary clean (pr-plan.md principle: **no
cross-border imports**). Before building the branch:

1. Take the row's `Paths` (implementation) **and** its co-located
   `tests/unit/<area>/...` — they travel in the same PR. Confirm each exists in
   the gke-labs tree (`git ls-files <path>`).
2. Scan the selected files' internal imports (`devops_bench.*`, plus referenced
   `skills/` guides, `tasks/` data, or `infra/` stacks). For each internal target,
   check: is it **already on `upstream/main`** or **included in this PR's paths**?
   - **Yes** → fine.
   - **No, and it's a whole later-wave module** → the PR is mis-ordered or its
     dependency hasn't landed. Re-select (step 2) or flag as BLOCKED. Do **not**
     smuggle a later module in early.
   - **No, but it's a small definition the migrated code needs that isn't upstream
     yet** (e.g. a new type added to `core/` for a new agent, added *after* `core/`
     first migrated) → that definition **must travel in this PR**. Add the file or
     hunk that provides it to `--paths`. This is the "changes that travel along
     with later modules" case: the module and the delta it needs ship together.
3. **Reconcile third-party dependencies in this PR.** Scan the selected files'
   *external* imports (non-stdlib, non-`devops_bench`). For any package not already
   in upstream's `pyproject.toml`, add it here — the manifests are `NEVER_SYNC`, so
   a dependency can only land **with** the code that needs it, never ahead of it.
   On the export branch (based on `upstream/main`), add the package to the right
   `[project.optional-dependencies]` extra or `[project.dependencies]`, run
   `uv lock` to refresh `uv.lock`, and include both files in the PR. Edit the
   manifests in place — never copy gke-labs' whole `pyproject.toml`/`uv.lock` over
   upstream's. (`core/` is pure-stdlib and adds none; models/metrics/agents/tasks
   each pull their own, e.g. `pydantic`, `pyyaml`, `deepeval`, `mcp`, `google-genai`.)
4. If the plan says this PR **supersedes** upstream files (e.g. `chaos/` replaces
   upstream `agents/chaos/`), note the `git rm` of the superseded files as part of
   the same branch.

The submit-ready gate in step 5 is what *proves* you got this right: a missing
internal symbol shows up as an import error/`NameError`, and a missing or
undeclared package fails `uv sync --frozen` (lockfile out of date) or import —
both against `upstream/main`.

### 4. Build the scoped export branch

From your fork clone (remotes wired, working tree clean, `git config user.email`
== your CNCF CLA email):

```bash
./hack/prep-export.sh \
  --branch <descriptive-branch> \
  --paths "<impl paths> <test paths>"
```

`prep-export.sh` branches off `upstream/main`, imports only those paths from
`gkelabs/main`, and commits DCO-signed (`git commit -s`) with your authorship.
Use `--interactive` to carve a sub-file slice (e.g. to include just the new
`core/` hunk from step 3 without the whole file's later changes). Then apply the
step-3 dependency edits on the branch (`pyproject.toml` + `uv lock`) and any
`git rm` of superseded files, and commit them before the gate.

### 5. Gate it submit-ready (do not skip)

Run the CI gate **on the export branch** — i.e. `upstream/main` + only the imported
files. This is the real test that the module stands alone upstream (and catches
cross-border imports from step 3):

```bash
uv sync --frozen                          # strict library-mode build (as CI does)
uv run ruff check devops_bench tests/unit # lint scope CI uses; or scope to the PR's paths
uv run pytest tests/unit/<area> -q        # the co-located tests for this PR
```

This mirrors the live gate in
[`../../../.github/workflows/guardrails.yml`](../../../.github/workflows/guardrails.yml):
`uv sync` builds in strict library mode, `ruff` must be clean, unit tests must
pass. If a boilerplate/header checker is installed (`hack/boilerplate.py`, per
pr-plan.md Stage 0 — not present in every clone yet), run it too so new files
carry their license headers. **Green is the gate.** If it fails on a missing
import/symbol, go back to step 3 — a dependency didn't travel. Fix, re-run. Never
open the PR on red.

### 6. Write the commit + PR text as fresh code, review, then push (prep only)

Only after the gate is green.

**Frame it as a brand-new addition, not a migration (upstream's point of view).**
From `kubernetes-sigs`' side this is a new project, not a port — the commit
message and the PR title/body must read as if this code is being added to the
repo for the first time:

- Use "**add(s) …**" ("add the foundation package", never "migrate …").
- **Do not** mention the migration, `gke-labs`, waves, the frontier, back-sync,
  or dependency reconciliation (intra-repo *or* third-party) anywhere in the
  upstream commit/PR text. Describe only what the code is and does.
- `prep-export.sh`'s default message is migration-flavored — override it with
  `-m "<fresh-code message>"` (or amend before pushing) so it reads as fresh code.

**Review the commit message and PR title/body with the user before pushing.**
Show them the exact text and get their sign-off (they may edit) — do not
`git push` or `gh pr create` until they approve.

Then, once approved:

```bash
git push origin <branch>
gh pr create --repo kubernetes-sigs/devops-bench --base main \
  --title "<fresh-code title>" --body "<fresh-code body>"   # not --fill
```

Report: the PR chosen and why, the exact paths (impl + tests + any carried-along
delta + any `git rm`), the gate result (lint/tests/headers), and the PR URL. Then
stop — merging and the frontier flip are out of scope.

---

## Pre-flight checklist (steps that must be true for any migration PR)

Verify these before/while cutting the branch — they come from README §2/§4/§7 and
the pr-plan principles:

- [ ] **Remotes wired**: `origin` = your fork, `gkelabs`, `upstream` (README §4.1).
- [ ] **CLA**: CNCF EasyCLA signed, and `git config user.email` matches the CLA
  identity — back-sync preserves authorship, so an unsigned author later blocks
  the sync PR.
- [ ] **Branch off `upstream/main`** (prep-export.sh does this).
- [ ] **Tests co-located** with the implementation in the same PR.
- [ ] **Smallest reviewable unit** — one concrete per PR once its base has landed.
- [ ] **No cross-border imports** — every internal dependency is upstream or travels along.
- [ ] **Third-party deps reconciled in-PR** — new external imports are added to
  `pyproject.toml` + `uv.lock` in this PR (manifests are `NEVER_SYNC`; deps land with their code).
- [ ] **Upstream text reads as fresh code** — commit/PR say "add(s) …"; no
  migration / `gke-labs` / wave / back-sync / dependency-reconciliation narrative.
- [ ] **Commit + PR text reviewed with the user** before `git push` / `gh pr create`.
- [ ] **DCO sign-off** on every commit (`git commit -s`; prep-export.sh does it).
- [ ] **Boilerplate headers** on new files (where a header checker is installed).
- [ ] **Superseded files removed** where the plan says so (e.g. chaos → `agents/chaos/`).
- [ ] **Gate green** — `uv sync` + `ruff` + `pytest` on the export branch.

---

## Wrong tool?

- **Flipping the frontier after a merge** → don't do it here. The `suggest-flips`
  workflow uncomments merged paths in `migrated.bara.sky` and opens the flip PR
  (README §2.2). Only fall back to a manual flip if asked — and if you do, keep
  the flip PR **self-contained: do not reference the forward/upstream PR** (no
  `owner/repo#NN` or `#NN`) in its commit message or body, or GitHub will
  cross-link the two repos. Say "merge after the corresponding upstream change
  lands" instead.
- **Editing an already-migrated (flipped) path** → that path is read-only in
  gke-labs; make the change upstream and let the back-sync bot mirror it. The
  `check-migrated-readonly.sh` guard will reject it otherwise.
- **Keeping docs/configs in step with a plan change** (not cutting a PR) → that's
  the config-sync / [`docs-sync`](../docs-sync/SKILL.md) work, not this skill.
