# Migration: Validation plan and runbook

### Documentation directory map
- For high-level steps for gke-labs maintainers, see [README.md](./README.md).
- For a deep dive into component design and principles, see [component-design.md](./component-design.md).
- For target directory layouts and glossary, see [directory-structure.md](./directory-structure.md).
- For the phased pull request deployment sequence, see [pr-plan.md](./pr-plan.md).

This document provides a step-by-step, executable runbook designed to validate the entire migration toolchain, scripts, and CI configurations on an isolated test branch inside `gke-labs/devops-bench` before touching any real files.

---

## 1. Overview of the validation strategy

We validate the migration mechanics in layers, starting with offline static analysis, moving to an isolated local git sandbox, and finally dry-running the GitHub Action workflows:

```
+------------------------------------+
|  Phase A: Setup Validation Branch  |  <- Copy toolkit scripts to active folders
+------------------------------------+
                 |
                 v
+------------------------------------+
|  Phase B: Local Tooling Dry-Runs   |  <- Check status, mock readonly guard
+------------------------------------+
                 |
                 v
+------------------------------------+
|   Phase C: Git-Remote Sandbox      |  <- Run local file:// remotes to test
|    (Proves Flow A & Flow B)        |     prep-export.sh & Copybara back-sync
+------------------------------------+
                 |
                 v
+------------------------------------+
|    Phase D: GitHub Actions CI      |  <- Push branch to test guardrails.yml
|          (Real Dry-Run)            |     and check-migrated-readonly.sh
+------------------------------------+
```

---

## Phase A: Setup the validation branch

To keep your working tree clean, we create a temporary validation branch in your local clone of `gke-labs/devops-bench`.

1. **Create and Switch to the Test Branch**:
   ```bash
   # Save the root path of your local clone for reference in sandbox phases
   REPO_ROOT="$(pwd)"
   git checkout -b migration-validation-sandbox
   ```
2. **Deploy the Toolkit to Active Locations**:
   Run the following commands to copy scripts, workflows, and configurations from `docs/migration/` into their active directories:
   ```bash
   # Create directories
   mkdir -p hack .github/workflows

   # Copy configurations and schemas
   cp docs/migration/migrated.bara.sky .
   cp docs/migration/copy.bara.sky .

   # Copy scripts and make them executable
   cp docs/migration/hack/* hack/
   chmod +x hack/*.sh

   # Copy workflows
   cp docs/migration/workflows/* .github/workflows/
   ```
3. **Commit the Toolkit Draft**:
   ```bash
   # Create a dummy file to represent a module we want to migrate
   mkdir -p devops_bench/core
   echo "print('registry')" > devops_bench/core/registry.py

   git add migrated.bara.sky copy.bara.sky hack/ .github/workflows/ devops_bench/
   git commit -m "test: draft migration toolkit and dummy module for sandbox validation"
   ```

---

## Phase B: Local tooling dry-runs

Verify that local scripts can parse configurations and execute logic with the current state of the repository.

### 1. Test the migration tracker
Execute the status script to confirm it properly tracks migrated vs. remaining packages:
```bash
./hack/migration-status.sh
```
*Expected Output*: Since `migrated.bara.sky` is empty, the script should report **100% Tasks Remaining** and display a complete list of legacy packages still needing migration.

### 2. Test the Read-Only Guard (Negative/Fail Test)
We will simulate a scenario where a developer attempts to modify a migrated path.

1. Add a dummy path to `migrated.bara.sky`:
   ```python
   # Edit migrated.bara.sky to simulate a migrated folder
   MIGRATED = [
       "devops_bench/tasks/**",
   ]
   ```
2. Create a dummy file under that simulated migrated path, and commit both files to ensure they are part of HEAD:
   ```bash
   mkdir -p devops_bench/tasks
   echo "print('edit')" > devops_bench/tasks/schema.py
   git add migrated.bara.sky devops_bench/tasks/schema.py
   git commit -m "test: simulate violation of migrated path"
   ```
3. Run the read-only guard script, simulating a pull request targeting `main`:
   ```bash
   # Stub BASE_REF as HEAD~1 to compare current branch commits
   BASE_REF=HEAD~1 ./hack/check-migrated-readonly.sh
   ```
   *Expected Output*: The script must print a failure message and exit with code `1`, indicating that edits to `devops_bench/tasks/schema.py` are blocked.

### 3. Test the read-only guard bypass (pass test)
Verify that the `migrated-override` label or the back-sync bot branch can successfully bypass the guard.

1. Test back-sync branch override:
   ```bash
   # Simulate running inside the back-sync bot branch
   HEAD_REF="backsync/from-upstream" BASE_REF=HEAD~1 ./hack/check-migrated-readonly.sh
   ```
   *Expected Output*: The guard should print a bypass notice and exit with code `0` (Success).

2. Test local environment variable override bypass:
   ```bash
   MIGRATED_OVERRIDE=1 BASE_REF=HEAD~1 ./hack/check-migrated-readonly.sh
   ```
   *Expected Output*: The guard should print a bypass notice and exit with code `0` (Success).

---

## Phase C: Git-remote sandbox (local file://)

This phase simulates the real interaction between `gke-labs` and `kubernetes-sigs` using local git repositories acting as remotes. This completely validates `prep-export.sh` (Flow A) and Copybara (Flow B) without touching GitHub.

> [!IMPORTANT]
> **Prerequisites:** You must have Docker installed and running locally, as the back-sync validation executes Copybara via a Docker container runner.

```
       /tmp/sandbox-incubator/ (Local gke-labs clone)
         /               ^
  Flow A/             (B) Back-sync
       v               /
/tmp/sandbox-canonical/ (Local upstream repo)
```

1. **Initialize the Mock Repositories**:
   Run the following block of commands to set up the sandbox directories:
   ```bash
   # 1. Create directory structures
   mkdir -p /tmp/sandbox-canonical.git
   mkdir -p /tmp/sandbox-incubator-workspace

   # 2. Initialize a bare repository representing the upstream canonical (kubernetes-sigs)
   git init --bare /tmp/sandbox-canonical.git

   # Initialize the bare repo with a main branch containing an initial commit
   git clone /tmp/sandbox-canonical.git /tmp/sandbox-canonical-init
   cd /tmp/sandbox-canonical-init
   git checkout -b main
   echo "# Upstream Repository" > README.md
   git add README.md
   git commit -m "Initial commit"
   git push origin main
   cd -
   rm -rf /tmp/sandbox-canonical-init

   # 3. Create a workspace that clones gke-labs and points to your sandbox branch
   cd /tmp/sandbox-incubator-workspace
   git clone -b migration-validation-sandbox "${REPO_ROOT}" .

   # Configure the mock remote tracking endpoints for sandbox testing
   git remote add gkelabs "${REPO_ROOT}"
   git remote add upstream /tmp/sandbox-canonical.git
    
   # 4. Point the local configurations to the sandbox path instead of GitHub
   # Modify copy.bara.sky destinations to target the local directories
   sed -i.bak 's|https://github.com/kubernetes-sigs/devops-bench.git|file:///tmp/sandbox-canonical.git|g' copy.bara.sky
   sed -i.bak "s|https://github.com/gke-labs/devops-bench.git|file://${REPO_ROOT}|g" copy.bara.sky
   rm -f copy.bara.sky.bak
   git commit -am "test: target local sandbox remotes in copy.bara.sky"
   ```

2. **Validate Flow A — `prep-export.sh`**:
   Verify that we can assemble and package a branch containing only specific files to export:
   ```bash
   # Fetch from our configured sandbox remotes
   git fetch --all 2>/dev/null || true

   # Run prep-export to package devops_bench/core files (pointing to our validation branch as the source)
   ./hack/prep-export.sh \
     --branch test-export-core \
     --src-ref migration-validation-sandbox \
     --paths "devops_bench/core/registry.py"
   ```
   *Expected Output*: The script should successfully package `devops_bench/core/registry.py`, create a new branch `test-export-core` starting off `upstream-mock/main`, preserve your author identity, and add a DCO `Signed-off-by` line. Verify the commit history:
   ```bash
   git log -n 1 --stat test-export-core
   ```

3. **Validate Flow B: Copybara back-sync bot**:
   Ensure Copybara can successfully read from the mock upstream and open a PR back into your local workspace.

   *Prerequisite*: This test requires Docker (or the native Copybara CLI tool) to be installed locally to run `backsync.sh`.
   ```bash
    # Prepare the mock upstream with a commit
    cd /tmp
    git clone /tmp/sandbox-canonical.git sandbox-canonical-clone
    cd sandbox-canonical-clone
    mkdir -p devops_bench/core
    echo "# Upstream edit" >> devops_bench/core/registry.py
    git add devops_bench/core/registry.py
    git commit -m "feat: upstream change to registry" --author="External Contributor <external@example.com>"
    git push origin HEAD:main

    # Back inside the incubator workspace, add the path to migrated.bara.sky
    cd /tmp/sandbox-incubator-workspace
    echo 'MIGRATED = ["devops_bench/core/**"]' > migrated.bara.sky
    git commit -am "test: uncomment core path in migrated.bara.sky"

    # Execute a local dry-run of Copybara
    GITHUB_TOKEN=mock-token ./hack/backsync.sh --dry-run
    ```
   *Expected Output*: The Copybara output should list the diff importing the upstream commit `feat: upstream change to registry` authored by `External Contributor <external@example.com>`, verifying that **ITERATIVE** mode correctly preserved authorship and history.

4. **Verify authorship and committer identity (CLA-critical)**:
   The gke-labs CLA gate is author-keyed; commits must preserve the real upstream author, while the committer must be the allowlisted migration bot (see [README.md](./README.md) §4 Step 2.3 for details). Run these assertions from the workspace root:
   ```bash
   # (a) Author preserved — the dry-run preview shows the upstream contributor, not the bot.
   GITHUB_TOKEN=mock-token ./hack/backsync.sh --dry-run 2>&1 \
     | grep -q "External Contributor <external@example.com>" \
     && echo "PASS: author preserved" || echo "FAIL: author not preserved"

   # (b) Committer wired to the allowlisted bot. (A --dry-run against a file:// remote does not
   #     materialize a commit object, so assert the committer configured on the run command.)
   grep -qE -- '--git-committer-name +"devops-bench-sync-bot"'                hack/backsync.sh \
     && grep -qE -- '--git-committer-email +"devops-bench-sync-bot@google.com"' hack/backsync.sh \
     && echo "PASS: committer = devops-bench-sync-bot" || echo "FAIL: committer not the bot"

   # (c) Attribution-safe config: pass_thru (not overwrite) + ITERATIVE (not SQUASH).
   grep -q "authoring.pass_thru" copy.bara.sky && grep -q 'mode = "ITERATIVE"' copy.bara.sky \
     && echo "PASS: pass_thru + ITERATIVE" || echo "FAIL: authoring/mode would drop attribution"

   # (d) Workflows act AS the bot (its PAT), not the built-in github-actions[bot].
   grep -q "secrets.SYNC_BOT_TOKEN" .github/workflows/backsync.yml \
     && grep -q "secrets.SYNC_BOT_TOKEN" .github/workflows/suggest-flips.yml \
     && echo "PASS: workflows use the bot PAT" || echo "FAIL: workflows not using SYNC_BOT_TOKEN"
   ```
   *Expected Output*: all four checks print `PASS`.

   > [!NOTE]
   > `git.github_pr_destination` needs the GitHub API, so it cannot open a PR against the `file://`
   > sandbox — the committer field is only *materialized* in a real run. To prove it end to end,
   > inspect a real back-sync PR's commit (or run Copybara once into a local bare repo via
   > `git.destination`) and confirm
   > `git log -1 --format='author=%an <%ae>%ncommitter=%cn <%ce>'` shows the upstream author with
   > `devops-bench-sync-bot <devops-bench-sync-bot@google.com>` as the committer.

---

## Phase D: GitHub Actions CI dry-run

Validate that the GitHub Action workflows trigger, pass, and fail exactly when they should in the real GitHub interface.

1. **Push the Validation Branch**:
   Push your `migration-validation-sandbox` branch to the real `gke-labs` repository:
   ```bash
   cd "${REPO_ROOT}"
   git push origin migration-validation-sandbox
   ```

2. **Verify Guardrails Auto-Activation**:
   Navigate to the GitHub Actions tab on your repository.
   - Verify that `guardrails.yml` triggered.
   - *Expected Outcome*: Since we have not done a full restructure yet, the `detect` stage should return `ready=false`, causing the rest of the build, test, and lint stages to be skipped as green no-ops.

3. **Verify Read-Only Guard on a Pull Request**:
   To test the flip guard in the real CI interface:
   - Create a draft PR on GitHub from `migration-validation-sandbox` into `main`.
   - Ensure you have a file edit on a path listed in `migrated.bara.sky` (e.g., `devops_bench/tasks/schema.py`).
   - *Expected Outcome*: The `migrated-readonly` CI status check should fail, blocking the PR.
   - Now, add the `migrated-override` label to the draft PR.
   - *Expected Outcome*: Re-triggering the check should cause it to pass successfully.

---

## Phase E: Cleanup

Once validation is complete, run these commands to clean up temporary sandbox directories and restore your working branch:

```bash
# 1. Clean up mock directories in /tmp
rm -rf /tmp/sandbox-canonical.git
rm -rf /tmp/sandbox-canonical-clone
rm -rf /tmp/sandbox-incubator-workspace

# 2. Return to the main branch
git checkout main

# 3. Safely delete the local validation sandbox branch
git branch -D migration-validation-sandbox

# 4. Optional: Delete the remote tracking branch
git push origin --delete migration-validation-sandbox
```
