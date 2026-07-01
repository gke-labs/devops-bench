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
- For the stage-by-stage PR sequence, see [pr-plan.md](./pr-plan.md).
- For the temporary legacy↔refactor regression gate used during the cutover, see [legacy-comparison.md](./legacy-comparison.md).

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

Follow the wave plan in [pr-plan.md](./pr-plan.md) §3.2 — it fixes which PR is next, its owner, and its exact paths.

### Step 2.1: Export a module (Flow A)

Per-PR export is driven by the **`migration-prep` skill** ([SKILL.md](../../.agents/skills/migration-prep/SKILL.md)): it picks the next ready PR (reconciling the wave plan, the `migrated.bara.sky` frontier, and upstream merged/in-flight state), scopes a branch off `upstream/main` with `prep-export.sh`, carries along any dependency delta a later module needs, gates it green (`uv sync` + `ruff` + `pytest`), and opens the upstream PR. It **prepares only** — it never merges or flips the frontier.

One-time before your first export: complete the [prerequisites](#2-maintainer-prerequisites) and, in your fork clone, point `origin` at your fork and add the other two remotes:
```bash
git remote add gkelabs  https://github.com/gke-labs/devops-bench.git
git remote add upstream https://github.com/kubernetes-sigs/devops-bench.git
```
Then invoke the skill per module and respond to upstream review until it merges.

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

> [!IMPORTANT]
> Keep the flip PR **self-contained**: do **not** reference the forward/upstream PR (no `owner/repo#NN` or bare `#NN`) in its commit message or body. GitHub turns such references into a cross-repo backlink between `gke-labs` and `kubernetes-sigs`. Say "merge after the corresponding upstream change lands" instead. (The automated `suggest-flips` PR already avoids this.)

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

#### Scope: what actually syncs back
Two things bound what the bot writes into `gke-labs`:
- **Paths** — only the `MIGRATED` frontier (minus `NEVER_SYNC`). While the frontier is empty the run is a NO_OP; upstream code outside the frontier is **never** mirrored back, so pre-existing upstream files don't land in `gke-labs`.
- **History** — Copybara `ITERATIVE` replays upstream commits *after* the last synced revision. **Seed the baseline on the first run** so only new commits flow; otherwise it replays a path's full upstream history (including pre-migration commits):
  ```bash
  ./hack/backsync.sh --last-rev "$(git ls-remote https://github.com/kubernetes-sigs/devops-bench.git main | cut -f1)"
  ```
  After the seed, later runs pick the baseline up automatically from the bot's own PRs.

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

## 5. Phase 3: Archive and retire `gke-labs`

When `migrated.bara.sky` includes 100% of paths:
1. Verify that `kubernetes-sigs/devops-bench` is fully functional and running tests successfully.
2. Disable the `.github/workflows/backsync.yml` and `suggest-flips.yml` pipelines in `gke-labs`.
3. Put a deprecation banner on the `gke-labs` `README.md` redirecting users to the upstream repo.
4. Archive the `gke-labs/devops-bench` repository.

---

## 6. Toolkit locations

The toolkit is installed at its active locations in `gke-labs` (only `README.md`, `pr-plan.md`, and `legacy-comparison.md` remain under `docs/migration/`). The back-sync workflows are inert until the bot is configured (§2.3): they carry a `github.repository == 'gke-labs/devops-bench'` guard and no-op on the empty frontier. To install upstream, copy each file from its `gke-labs` location.

| Location | Host | Purpose |
|---|---|---|
| `.github/workflows/guardrails.yml` | both | CI: `uv sync`, ruff, unit tests |
| `hack/check-migrated-readonly.sh` | gke-labs | flip guard invoked by `guardrails.yml` |
| `migrated.bara.sky` (root) | gke-labs | single source-of-truth frontier |
| `copy.bara.sky` (root) | gke-labs | back-sync (Copybara) configuration |
| `.github/workflows/backsync.yml` | gke-labs | back-sync pipeline (needs `SYNC_BOT_TOKEN`) |
| `.github/workflows/suggest-flips.yml` | gke-labs | opens flip PRs (needs `SYNC_BOT_TOKEN`) |
| `hack/prep-export.sh` | gke-labs | stage a scoped upstream export branch |
| `hack/backsync.sh` | gke-labs | run Copybara locally or in CI |
| `hack/migration-status.sh` | gke-labs | migration progress tracker |


---

## 7. Crucial do's and don'ts

* **DO** complete Phase 1 restructure entirely before sending the first forward PR.
* **DO** include unit tests in the same forward PR as the code files.
* **DO** develop migrated files exclusively in `kubernetes-sigs` once they have been flipped.
* **DON'T** edit a migrated path directly inside the `gke-labs` repo. The back-sync bot will attempt overwrite/revert your edits.
* **DON'T** let the back-sync bot sync manifests (`pyproject.toml`, `uv.lock`, `.python-version`, `LICENSE`). These are marked as `NEVER_SYNC` and are managed manually per-repo to prevent version skew and dependency conflicts.
