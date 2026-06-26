# Unlimited / self-healing mode

Load this **only** when the user explicitly opted in ("unlimited", "keep going until
it finishes", "auto-fix and restart", "self-healing"). It turns a *real* (non-flake)
failure caused by a **task or code bug** into: diagnose → fix → re-sync → restart the
failed combos → continue, until the whole matrix reaches a terminal-acceptable state.
It builds on `references/resilient-monitoring.md` (reuse that loop + recovery +
keepalive); this file only adds the fix-and-restart behavior. It is **harness-
agnostic** — see *Harness portability* in `SKILL.md` for the capability mapping
(isolated worktree, durable state, sub-tasks); tool names here are examples.

## Classify before you "fix" — fixing the wrong thing corrupts the eval

- **Infra flake** → retry, no code change (Phase-5 retry procedure).
- **Model capability** (clean trajectory, low score — the agent ran but did the task
  badly) → **do NOT fix.** That's a real result; record it and move on.
- **Task / stack / harness bug** (the combo cannot succeed regardless of model:
  broken stack, bad prompt template, wrong `expected_output`, missing var, or a
  parallel-safety collision from the known-issues appendix) → **the fixable class.**

When unsure, prefer recording over fixing; only fix when you can name the bug **and**
the change that resolves it.

## The loop

1. **Isolate.** Make changes in an isolated git worktree / branch (Claude Code:
   `EnterWorktree`; else `git worktree add` + a branch), never the shared checkout.
   Branch off the arm under test.
2. **Diagnose** the failing combo with the review checks (the `devops-bench-review`
   skill if your harness loaded it, plus the `docs/parallel-evals.md` failure table).
   Name the bug and the minimal fix.
3. **Fix**, scoped to that bug — don't refactor unrelated code. Run the unit tests /
   `ruff` locally if they cover it (never run an eval to "test" a fix).
4. **Log** the fix in a running changelog (durable state — a notes file or task list):
   combo, symptom, root cause, the change, commit sha.
5. **Re-sync (remote only).** In `BENCH_REMOTE` mode, push the working tree to the
   bastion (`scripts/bastion/sync-to-bastion.sh`; `SKIP_SYNC=1` only after a real
   sync). In local mode the edits are already in place — skip this.
6. **Restart only the failed combo(s)** as fresh single-combo matrices (new stamp),
   after cleaning their leaked GCP resources (cluster, `gke-nodes-*` SA, secrets).
7. **Continue** the resilient-monitoring loop over the remaining + restarted combos.

## Guardrails (so "unlimited" still terminates safely)

- **Cap fix attempts per combo** (default 3). After that, stop fixing it, mark it
  blocked, and keep going on the rest — never loop one combo forever.
- **Scope every change**; commit each fix separately with a clear message; keep the
  changelog for human review at the end.
- **Local commits only.** Do **not** push to or merge shared branches (main, the arm
  branches) unless the user said so — surface the branch/diff for review instead.
- **Self-check risky fixes** with the review checks before restarting — especially
  parallel-safety fixes, since you're about to run them concurrently.
- **Budget awareness.** Each restart costs a cluster + ~25–40 min. Track combos
  fixed/remaining; if a token or wall-clock budget was given, respect it and report
  where you stopped.
- **Checkpoint** stamp + per-combo state + fix log in durable state every tick so a
  context reset resumes mid-flight.
- **Keepalive** as in resilient-monitoring: don't signal completion until the whole
  matrix is done.

## Done condition + final report

Finish when every combo is terminal-acceptable: **passed**, recorded as a genuine
**model-capability** result, or **blocked** after the fix-attempt cap. Then deliver
the Phase-6 summary **plus** the fix changelog (each bug → change → commit) and the
list of still-blocked combos with why.
