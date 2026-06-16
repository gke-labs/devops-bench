# Migrating `devops-bench` to kubernetes-sigs: maintainer runbook

This document is the official, step-by-step action plan for **`gke-labs` repository maintainers** migrating `devops-bench` to its permanent upstream home in `kubernetes-sigs`.

---

## 1. The migration model in one minute

```text
                              [PHASE 1]
                     Restructure gke-labs in-place
                     (All code under devops_bench/)
                                  |
                                  v
+------------------+          [PHASE 2]           +-------------------+
|     gke-labs     |  ------------------------->  |  kubernetes-sigs  |
|  (devops-bench)  |     (A) Forward PR export    |  (devops-bench)   |
|                  |     (Using prep-export.sh)   |                   |
|                  |                              |                   |
|  Source of truth |  <-------------------------  |  Source of truth  |
|   for remaining  |       (B) Back-sync bot      |    for migrated   |
|      modules     |     (copy.bara.sky + GHA)    |      modules      |
+------------------+                              +-------------------+
                                  |
                                  v
                              [PHASE 3]
                     All modules migrated; archive
                         and retire gke-labs
```

- **Phase 1 (Restructure)**: Restructure the `gke-labs` repository in-place into the target layout before exporting any files upstream.
- **Phase 2 (Migrate Module-by-Module)**: Export files chunk-by-chunk. For each migrated module:
  - **Flow A (Export)**: Create an upstream PR. Once merged, uncomment its paths in `migrated.bara.sky` (this "flips" the source of truth).
  - **Flow B (Back-sync)**: A scheduled, automated Copybara bot syncs upstream edits back to `gke-labs` so the remaining modules can import them and keep building.
- **Phase 3 (Retire)**: Once 100% of required modules are migrated, archive and retire the `gke-labs` repository.

### Document index
- For the target directory layout and path mapping, see [directory-structure.md](./directory-structure.md).
- For a deep dive into component design and principles, see [component-design.md](./component-design.md).
- For the Stage-by-Stage PR sequence, see [pr-plan.md](./pr-plan.md).
- For instructions on validating the setup on a test branch, see [VALIDATION.md](./VALIDATION.md).

---

## 2. Maintainer prerequisites

Before executing any commands, ensure you have:
1. Created a personal fork of `kubernetes-sigs/devops-bench` on GitHub.
2. Signed the **CNCF CLA (Contributor License Agreement)**.
3. Authenticated your local GitHub CLI (`gh auth login`).
4. Set your local git identity to match your CNCF CLA email (`git config --global user.email`).

---

## 3. Phase 1: Restructure `gke-labs` in-place

Restructure `gke-labs` before pushing any code upstream. No upstream PRs should be created until this stage is green.

1. **Set Up the Toolchain**: 
   - Add `pyproject.toml` (referencing Hatchling and `ruff` configurations), `uv.lock`, and `.python-version` to the `gke-labs` repo. (`.github/workflows/guardrails.yml` and the `hack/check-migrated-readonly.sh` guard it invokes are **pre-installed in the repository and act as a green no-op (see [Section 6](#6-toolkit-installation-locations)) and stay a green no-op until these manifests and `devops_bench/` land.)
2. **Reorganize Code Paths**:
   - Move `pkg/` into the `devops_bench/` namespace.
   - Restructure submodules and write companion unit tests directly inside `tests/`.
   - Reorganize Terraform files from `tf/` to `infra/`.
3. **Verify Locally**:
   - Run the local testing and linting suite:
     ```bash
     uv sync --all-extras
     uv run ruff check .
     uv run pytest tests/ -v
     ```
4. **Merge and Verify CI**:
   - Merge the restructure PR into the `gke-labs` `main` branch. Ensure the GitHub Actions `guardrails.yml` run is green.

---

## 4. Phase 2: Migrate module by module

Follow the 5-stage order defined in [pr-plan.md](./pr-plan.md).

### Step 2.1: Export a module (Flow A)

For each module (e.g., `gemini` CLI agent):

#### Remote Setup Strategy

Before executing Flow A, ensure your local repository is set up with three distinct remotes:
- `origin`: Points to your personal GitHub fork (e.g., `https://github.com/YOUR_USERNAME/devops-bench.git`).
- `gkelabs`: Points to the source incubator repository (`https://github.com/gke-labs/devops-bench.git`).
- `upstream`: Points to the canonical target repository (`https://github.com/kubernetes-sigs/devops-bench.git`).

If you cloned directly from `gke-labs`, rename the default `origin` remote first:
```bash
git remote rename origin gkelabs
git remote add origin https://github.com/YOUR_USERNAME/devops-bench.git
git remote add upstream https://github.com/kubernetes-sigs/devops-bench.git
```

1. Set up remote endpoints in your local clone:
   ```bash
   git remote add gkelabs  https://github.com/gke-labs/devops-bench.git
   git remote add upstream https://github.com/kubernetes-sigs/devops-bench.git
   ```
2. Run `prep-export.sh` to compile a clean, scoped branch containing only the desired files and their unit tests, branched directly off `upstream/main`:
   ```bash
   ./hack/prep-export.sh \
     --branch add-gemini-agent \
     --paths "devops_bench/agents/cli/gemini.py tests/test_factory.py"
   ```
3. Push the branch to your fork and submit an upstream Pull Request:
   ```bash
   git push origin add-gemini-agent
   gh pr create --repo kubernetes-sigs/devops-bench --base main --fill
   ```
4. Respond to upstream review comments and complete the merge into `kubernetes-sigs/devops-bench`.

---

### Step 2.2: Flip the module frontier (Optional / Automated)

Once the upstream PR merges, its ownership must be flipped in `gke-labs`. While you can do this manually, **this step is automated** by the periodic `suggest-flips` workflow, which uncomments the paths and submits a flip PR automatically.

#### Automated path (Recommended)
Simply wait for the periodic `suggest-flips` GitHub Action to detect the upstream merge. It will automatically:
1. Identify the newly merged paths.
2. Uncomment them in `migrated.bara.sky`.
3. Open a pull request in `gke-labs` to lock the paths and activate the back-sync bot.

#### Manual path (Fallback)
If you need to flip the frontier immediately without waiting for the scheduled workflow:

1. Open `migrated.bara.sky` at the `gke-labs` repository root.
2. **Uncomment** the lines corresponding to the migrated paths (both implementation and unit tests):
   ```python
   MIGRATED = [
       # ...
       "devops_bench/agents/cli/**",
       "tests/agents/**",
       # ...
   ]
   ```
3. Verify the status locally:
   ```bash
   ./hack/migration-status.sh
   ```
   *Expected Outcome*: The uncommented paths will move from "not started" to the "Migrated" list.
4. Merge this change into the `gke-labs` `main` branch via a standard pull request.

> [!NOTE]
> Uncommenting a line activates the **Read-Only Guard** in `gke-labs` CI. From this moment, any PR in `gke-labs` that attempts to mutate those paths will be rejected by `check-migrated-readonly.sh`. Edits must now be made upstream.

---

### Step 2.3: Manage the back-sync bot (Flow B)

With the frontier updated, the back-sync bot mirrors upstream changes back to `gke-labs`, ensuring remaining modules can import them and build successfully.

#### Bot automation setup (one-time)
The back-sync runs as a dedicated, allowlisted bot account,
[`devops-bench-sync-bot`](https://github.com/devops-bench-sync-bot) (committer
`devops-bench-sync-bot@google.com`), **not** the built-in `github-actions[bot]`. This keeps the bot's
push/PR identity stable and allowlistable for the migration.

1. Ensure the `devops-bench-sync-bot` GitHub account has write access to `gke-labs/devops-bench`.
2. Create a (fine-grained) **PAT** for that account scoped to push branches and open PRs on the repo.
3. In `gke-labs` settings, add it as the repository secret **`SYNC_BOT_TOKEN`** (the name
   `backsync.yml` reads). A PAT acts as a normal user, so the *"Allow GitHub Actions to create and
   approve pull requests"* setting is **not** required.

The bot runs `.github/workflows/backsync.yml` daily via cron or on demand via `workflow_dispatch`,
authenticating with `SYNC_BOT_TOKEN`.

#### Running locally or debugging
```bash
# Real run (push/PR as the bot): use the bot's PAT
export GITHUB_TOKEN="$SYNC_BOT_TOKEN"
./hack/backsync.sh

# Dry-run only: your own token is fine (nothing is pushed, no PR is opened)
export GITHUB_TOKEN="$(gh auth token)"
./hack/backsync.sh --dry-run
```
The git **committer** is stamped as `devops-bench-sync-bot` regardless of the token; **authors** stay
as the original upstream contributors (see the CLA note below).

> [!WARNING]
> **CLA Enforcement on Back-Syncs**: The back-sync bot runs Copybara in `ITERATIVE` mode with `pass_thru` author preservation. If an upstream commit is authored by a contributor who has **not** signed the `gke-labs` CLA, the back-sync PR in `gke-labs` will be blocked until they sign. Do not change this configuration; squashing commits into a bot-authored commit violates license tracking and bypasses the security gate.

---

### Step 2.4: Leverage `suggest-flips` automation

To reduce manual tracking, the **`suggest-flips`** automated workflow (`.github/workflows/suggest-flips.yml`) runs weekly or on-demand:
1. It compares local paths against what currently exists on `upstream/main`.
2. It automatically uncomments any paths in `migrated.bara.sky` that have successfully landed upstream.
3. It opens a Pull Request in `gke-labs` with the suggested flips for maintainer review.

---

## 5. Phase 3: Archive and retire `gke-labs`

When `migrated.bara.sky` includes 100% of paths:
1. Verify that `kubernetes-sigs/devops-bench` is fully functional and running tests successfully.
2. Disable the `.github/workflows/backsync.yml` and `suggest-flips.yml` pipelines in `gke-labs`.
3. Put a deprecation banner on the `gke-labs` `README.md` redirecting users to the upstream repo.
4. Archive the `gke-labs/devops-bench` repository.

---

## 6. Toolkit installation locations

Most files in `docs/migration/` are **inert templates**: GitHub Actions only runs workflows under
`.github/workflows/`, and Copybara plus the `hack/` scripts resolve `copy.bara.sky` and
`migrated.bara.sky` from the repo root. To activate, each must be copied to the destination below. The
active copies are kept **byte-identical** to these templates (so they can be diffed); the templates
remain the source for the eventual `kubernetes-sigs` install.

**Initially, only the CI guardrail is installed in `gke-labs`** (see the note below). Every row
marked ⛔ is still an inert template that **must still be installed** in a later step.

| Source File in `docs/migration/` | Active Target Destination | Host Repository | Status | Purpose |
|---|---|---|---|---|
| `workflows/guardrails.yml` | `.github/workflows/guardrails.yml` | **Both** | ✅ Installed in `gke-labs` (this PR); ⛔ TODO in `kubernetes-sigs` | CI testing, ruff lints, header checks |
| `hack/check-migrated-readonly.sh` | `hack/check-migrated-readonly.sh` | `gke-labs` | ✅ Installed (this PR) — invoked by `guardrails.yml` | Blocks edits to migrated files |
| `migrated.bara.sky` | `migrated.bara.sky` (Root) | `gke-labs` | ⛔ Not yet installed | Single source-of-truth frontier |
| `copy.bara.sky` | `copy.bara.sky` (Root) | `gke-labs` | ⛔ Not yet installed | Back-sync bot configuration |
| `workflows/backsync.yml` | `.github/workflows/backsync.yml` | `gke-labs` | ⛔ Not yet installed (needs `SYNC_BOT_TOKEN`) | Automated back-sync GHA pipeline |
| `workflows/suggest-flips.yml` | `.github/workflows/suggest-flips.yml` | `gke-labs` | ⛔ Not yet installed | Suggests flips in `migrated.bara.sky` |
| `hack/prep-export.sh` | `hack/prep-export.sh` | `gke-labs` | ⛔ Not yet installed | Pulls files and stages upstream branch |
| `hack/backsync.sh` | `hack/backsync.sh` | `gke-labs` | ⛔ Not yet installed | Runs Copybara locally or via CI |
| `hack/migration-status.sh` | `hack/migration-status.sh` | `gke-labs` | ⛔ Not yet installed | Migration progress CLI tracker |

> [!IMPORTANT]
> **`guardrails.yml` is live and active in `gke-labs`, but the rest of the toolkit is not; it still must be installed.**
> - The workflow is a deliberate **green no-op until the Phase-1 toolchain lands**: its `detect` job
>   short-circuits the build/lint/test matrix until `pyproject.toml` + `devops_bench/` exist.
> - Its `migrated-readonly` job (gke-labs only) shells out to `hack/check-migrated-readonly.sh`, so that
>   one script is installed alongside it. With no `migrated.bara.sky` at the root yet, the guard cleanly
>   no-ops ("nothing is locked yet"); installing `migrated.bara.sky` later *arms* it.
> - **Still to do** (the ⛔ rows above): install `migrated.bara.sky` + `copy.bara.sky` at the root,
>   `backsync.yml` + `suggest-flips.yml` under `.github/workflows/`, and the remaining `hack/` scripts,
>   plus the one-time back-sync bot setup (`SYNC_BOT_TOKEN`, §2.3). These come online in Phase 2.

---

## 7. Crucial do's and don'ts

* **DO** complete Phase 1 restructure entirely before sending the first forward PR.
* **DO** include unit tests in the same forward PR as the code files.
* **DO** develop migrated files exclusively in `kubernetes-sigs` once they have been flipped.
* **DON'T** edit a migrated path directly inside the `gke-labs` repo. The back-sync bot will automatically overwrite/revert your edits.
* **DON'T** let the back-sync bot sync manifests (`pyproject.toml`, `uv.lock`, `.python-version`, `LICENSE`). These are marked as `NEVER_SYNC` and are managed manually per-repo to prevent version skew and dependency conflicts.
