---
name: docs-sync
description: Keep the docs current after a code change — map changed code areas to the docs that describe them, update those docs in place, and prune known-issues rows the code has verifiably fixed. Invoke after editing the pipeline, adding a model/agent/task/metric, moving a directory, or whenever someone asks to "sync the docs", "update the docs for this change", or "do the docs still match the code?".
---

# Sync docs to a code change

Code moved; the docs should move with it. This skill takes a change set and walks
it back to the docs that describe the touched areas, updates those docs, and
removes stale recovery rows the code now fixes. It edits prose only — it does not
change behavior.

Follow the repo's doc conventions while editing: GFM, humanized (not journal-like
or changelog-y), minimal, no contradictions or duplication, and **no model
scores or result tallies** in any doc.

- Doc map (what lives where) → [`../../../docs/README.md`](../../../docs/README.md)
- Capability → tool mapping for your harness →
  [`../../references/harness-capabilities.md`](../../references/harness-capabilities.md)

---

## Flow

### 1. Get the change set

Take the diff or the list of changed files (e.g. `git diff --name-only main...`,
or the working tree). Group the changes by area — a model provider, a deployer, an
agent harness, the CLI, metrics, a task, the leaderboard, a directory move.

### 2. Learn where things are documented

Tree-walk `docs/` and read the doc map in
[`../../../docs/README.md`](../../../docs/README.md). Also read the nearest
`AGENTS.md` to the changed code — the root `AGENTS.md`, plus
`devops_bench/AGENTS.md`, `site_new/AGENTS.md`, or `tasks/AGENTS.md` — since those
route contributors and often need the same edit as the docs.

### 3. Map changed area → affected docs

| Changed code area | Docs to update |
|---|---|
| Model provider (`devops_bench/models/`) | [`model_providers.md`](../../../docs/components/model_providers.md) |
| Deployer / cloud provider (`devops_bench/deployers/`, `tf/`) | [`infra.md`](../../../docs/components/infra.md) |
| Agent harness (`devops_bench/agents/`) | [`agents.md`](../../../docs/components/agents.md) + [`add-an-agent-harness.md`](../../../docs/how-to/add-an-agent-harness.md) |
| CLI flags / env (`devops_bench/cli.py`, `run.py`, `devops_bench/evalharness/`) | [`run-evals.md`](../../../docs/how-to/run-evals.md) + root [`README.md`](../../../README.md) |
| Metrics (`devops_bench/metrics/`) | [`metrics.md`](../../../docs/components/metrics.md) |
| Task schema / placeholders (`devops_bench/tasks/`) | [`add-a-task.md`](../../../docs/how-to/add-a-task.md) + [`glossary.md`](../../../docs/components/glossary.md) |
| Leaderboard / ingest (`site_new/`) | [`leaderboard.md`](../../../docs/how-to/leaderboard.md) |
| Directory move / rename | the codebase tree in [`glossary.md`](../../../docs/components/glossary.md) + the relevant `AGENTS.md` |

A change can touch more than one row (e.g. a new CLI flag that exposes a new
metric). Update every doc the change actually affects, and only those.

### 4. Update the affected docs

Edit in place. Keep edits surgical — change the lines the code change made wrong,
don't rewrite the page. Match the page's existing voice and structure. If a code
change makes a documented example wrong, fix the example. Never paste a score
table or run results into a doc.

### 5. Prune the known-issues router

This is the inverse of what the run skills do: they *append* freshly observed
failures to [`known_issues.md`](../../../docs/appendix/known_issues.md); this
skill *removes* rows the code now fixes.

For every Section 1 (router) or Section 2 (known hacks) row whose root cause your
change set addresses:

- **Confirm the fix exists in the code before removing the row.** Open the file
  the row points at and verify the fix is actually there — cite the file and line
  in your report. A row describes a *current* failure mode; remove it only when
  that failure mode can no longer happen.
- If a hack's stated **removal condition** is now met, remove its Section 2 row.
- If you're not certain the fix is complete, leave the row and say so — a stale
  "still broken" row is safer than a wrong "all clear".

### 6. Verify links + report

Confirm every relative link you touched still resolves (open the target, or check
the path exists). Then report: the change-set → doc map you applied, each file
edited, and each known-issues row removed **with the file/line that proves the
fix**.

---

## Wrong tool?

- **A new failure to record** (not a fix) → that belongs in the run skills, which
  append to the known-issues router; this skill only prunes verified fixes.
- **Authoring brand-new docs for a feature with no home yet** → write the page,
  then add it to the doc map in [`../../../docs/README.md`](../../../docs/README.md)
  and the nearest `AGENTS.md`.

## Guardrails

- No model scores, leaderboard standings, or result tallies in any doc — ever.
- Never remove a known-issues row without citing the code that fixes it.
- Edit prose only; this skill does not change code behavior.
- Keep edits minimal and humanized; don't turn a doc into a changelog.
