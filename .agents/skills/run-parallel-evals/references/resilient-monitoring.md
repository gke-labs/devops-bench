# Resilient monitoring — tiered subagents + recovery

Load this for a **real, long, or hands-off** matrix run (it's the default once you
actually launch one). Goal: the run survives quiet stretches, subagent API errors,
and local drops, and the background job is never classified as finished while combos
are still going.

The **bastion is the source of truth** — every combo's state lives in
`~/matrix-runs/<stamp>/<rid>/` (`status`, `run.log`) plus the pulled results.
Subagents are disposable readers of that state: losing one loses nothing, because a
fresh one re-reads the same `RESUME_STAMP`.

## Roles & model tiers

| Role | Model tier | Cadence | Job |
|---|---|---|---|
| **Supervisor** | the session/main model (you) | every ~5 min while combos run; longer when idle | dispatch + re-spawn subagents, decide retries, keep the job alive, never go silent |
| **Monitor** | **low** — Haiku (`Agent` with `model: "haiku"`), or Gemini Flash-low via the antigravity plugin | each tick | `ssh` the bastion, read each combo's `status` + `run.log` tail, return a one-line-per-combo digest + an overall `running / done / flaked / .done` summary. No analysis, no log dumps. |
| **Analyzer** | **mid** — Sonnet (`model: "sonnet"`), or Gemini Flash-medium | once per finished combo (or a small batch) | pull + read that combo's `results.json` + `run.log`, return scores + pass/fail checks + a root-cause digest if it failed |

Spawn monitor/analyzer with `subagent_type: general-purpose` (they need Bash for
`ssh` / `gcloud` / `gh`). Give each the connection env (`BASTION_*`, project) and the
`RESUME_STAMP`. Tell them to **return a compact digest, not raw logs** — that keeps
your context clean (progressive disclosure applies to tool output too).

## Supervision loop

1. Launch the matrix detached (Phase 4) and capture `RESUME_STAMP`; record stamp +
   combo list in a **TaskList** so a context reset can resume.
2. Spawn the **monitor** as a background agent (`run_in_background: true`) pointed at
   the stamp (or run a short foreground monitor each tick — background is cheaper on
   your turns).
3. Each supervisor tick:
   - Read the monitor's latest digest; emit a one-line status to the user (keepalive).
   - Newly `exit=0` combos → dispatch an **analyzer** (parallel across them).
   - **Flaked** combos → Phase-5 retry procedure (cap 2); or, in unlimited mode, the
     `references/unlimited-mode.md` loop.
   - `.done` present **and** every combo has an analyzer result → go to Phase 6.
   - Otherwise schedule the next wake (`ScheduleWakeup`, ~5 min while active; 20–30
     min if genuinely idle) and stop the turn — do **not** busy-loop.

## Recovery — subagent stuck / API error

- A background subagent that dies on a terminal API error returns null/an error and
  re-invokes you; a foreground one returns an error. Either way **re-spawn a fresh
  one** pointed at the same `RESUME_STAMP` — no state is lost.
- Cap re-spawns (≤3 per role per tick). If a role keeps dying, **fall back to doing
  that check yourself** (a single `ssh` digest) so the run still advances, and note
  the degradation.
- Whole detached runner died on the VM (no `.done`, no live process) → re-attach with
  `RESUME_STAMP`; if truly dead, relaunch the unfinished combos.
- Local/SSH `exit 255` is a transient relay blip — retry; the detached run is fine.

## Keep the background job alive

The job-list classifier reads only **your message text**. During a long run:
- **Never** emit `result:` / "done" / "completed" / "failed" until *every* combo is
  terminal and summarized — those read as stop signals.
- Each tick, emit a short `still working: N running / M done / K flaked` line so the
  job stays classified as active.
- Drive cadence with `ScheduleWakeup` (dynamic) so the session re-engages instead of
  going silent. Use `needs input:` only for a genuine blocker (e.g. a missing API key
  you can't supply) — and in unlimited mode, avoid even that by deciding sanely.

## Cost discipline

Poll with the cheap monitor (frequent), analyze with the mid model (per-finish only),
spend the main model rarely (supervise/decide). Never analyze a combo twice; prefer
one batched analyzer when several combos finish together.
