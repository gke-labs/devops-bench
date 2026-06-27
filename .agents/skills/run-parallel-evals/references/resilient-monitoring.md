# Resilient monitoring — tiered sub-tasks + recovery

Load this for a **real, long, or hands-off** matrix run (the default once you
actually launch one). Goal: the run survives quiet stretches, sub-task failures, and
local drops, and — on harnesses that have one — the session is never marked
"finished" while combos are still going.

This is **harness-agnostic** (see *Harness portability* in `SKILL.md`): the roles
below are capabilities, with Claude Code tools named only as examples. The **runner host**
(this machine in local mode, the bastion when `BENCH_REMOTE`) **is the source of
truth** — every combo's state lives in `~/matrix-runs/<stamp>/<rid>/`
(`status`, `run.log`) plus the pulled results. Helper sub-tasks are disposable readers
of that state: losing one loses nothing, because a fresh one re-reads the same
`RESUME_STAMP`. If your harness has **no** sub-tasks at all, do the monitor/analyzer
steps inline yourself — the loop still works, just on one model.

## Roles & model tiers

| Role | Model tier | Cadence | Job |
|---|---|---|---|
| **Supervisor** | your **main/session** model | every ~5 min while combos run; longer when idle | dispatch + re-spawn helpers, decide retries, keep the session alive, never go silent |
| **Monitor** | a **low** tier (Claude Haiku · Gemini Flash · Codex mini · …) | each tick | shell to the runner host (local, or `ssh <bastion>` when `BENCH_REMOTE`), read each combo's `status` + `run.log` tail, return a one-line-per-combo digest + an overall `running / done / flaked / .done` summary. No analysis, no log dumps. |
| **Analyzer** | a **mid** tier (Claude Sonnet · Gemini Flash/Pro · Codex standard · …) | once per finished combo (or a small batch) | pull + read that combo's `results.json` + `run.log`; return scores + pass/fail checks + a root-cause digest if it failed |

Run the monitor/analyzer as **sub-tasks that can shell out on the runner host**
(local shell, or `ssh` / `gcloud` to the bastion in remote mode) — Claude Code: the `Agent` tool with `model:` + `subagent_type: general-purpose`;
other harnesses: their subagent/delegation mechanism. Give each the connection env
(`BASTION_*`, project) and the `RESUME_STAMP`, and tell it to **return a compact
digest, not raw logs** — that keeps the supervisor's context clean (progressive
disclosure applies to tool output too).

## Supervision loop

1. Launch the matrix detached (Phase 4) and capture `RESUME_STAMP`; record the stamp +
   combo list in **durable state** (a task list or a notes file) so a context reset
   can resume.
2. Start the **monitor** — as a **background** sub-task if your harness supports one,
   else a short foreground check each tick.
3. Each supervisor tick:
   - Read the monitor's latest digest; emit a one-line status to the user (keepalive).
   - Newly `exit=0` combos → dispatch an **analyzer** (in parallel across them).
   - **Flaked** combos → Phase-5 retry procedure (cap 2); or, in unlimited mode, the
     `references/unlimited-mode.md` loop.
   - `.done` present **and** every combo has an analyzer result → go to Phase 6.
   - Otherwise **schedule the next wake** (a timer/cron, ~5 min while active; 20–30
     min if genuinely idle) and end the turn — do **not** busy-loop. No scheduler?
     `sleep` between checks in a loop.

## Recovery — sub-task stuck / API error

- A sub-task that dies on a terminal API error comes back as an error / empty result.
  Either way **re-spawn a fresh one** pointed at the same `RESUME_STAMP` — no state is
  lost.
- Cap re-spawns (≤3 per role per tick). If a role keeps dying, **fall back to doing
  that check yourself** (one shell digest) so the run still advances, and note the
  degradation.
- Whole detached runner died on the VM (no `.done`, no live process) → re-attach with
  `RESUME_STAMP`; if truly dead, relaunch the unfinished combos.
- Local/SSH `exit 255` is a transient relay blip — retry; the detached run is fine.

## Keep the session alive (if your harness can stop it)

Some harnesses watch the session and may mark it done — or time it out — during quiet
stretches (Claude Code's background job list classifies from your message text). When
running under one:
- **Never** signal completion (Claude Code: a `result:` / "done" / "failed" line)
  until *every* combo is terminal and summarized.
- Each tick, emit a short `still working: N running / M done / K flaked` line so the
  session stays classified as active.
- Re-engage via a timer rather than blocking, so you don't go silent. Ask the user to
  unblock only for a genuine blocker (e.g. a missing API key you can't supply) — and
  in unlimited mode, avoid even that by deciding sanely.

Harnesses without such a classifier can ignore this section — but emitting periodic
progress is still good practice.

## Cost discipline

Poll with the cheap monitor (frequent), analyze with the mid tier (per-finish only),
spend the main model rarely (supervise/decide). Never analyze a combo twice; prefer
one batched analyzer when several combos finish together.
