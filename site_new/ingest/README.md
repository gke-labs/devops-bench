# Real-data ingest (`site_new/ingest`)

Turns real benchmark eval-results into the dashboard's Firestore collections.
The real counterpart to `seed/` (which fabricates data): same data model, same
scoring formula, but reading actual eval output instead of `generateRaw()`.

```
eval run ─▶ results/run_<ts>/rows.json (ResultRow[])
                  │   load.mjs        validate + flatten
                  ▼
            results  (raw, append, idempotent)
                  │   derive.mjs      data-driven: discover setups/tasks from rows
                  ▼
   setups (derived)  ·  models / harnesses (metadata from catalog.mjs)
                  ▲
            dashboard reads ONLY setups / models / harnesses
```

## Input

The Python eval harness writes one **`rows.json` per run** (a flat `ResultRow[]`)
under `results/run_<ts>/`, beside a `manifest.json` the ingest skips. The full,
example-driven contract is in **[`PROTOCOL.md`](./PROTOCOL.md)** — read that to
produce a file. In short: you provide raw per-iteration rows; everything the
dashboard shows (setups, tasks, history) is *derived*, and model/harness display
metadata comes from `catalog.mjs`, not the upload.

## Pieces

| File | Role |
|---|---|
| `load.mjs` | `rows.json` files → validated, flat `ResultRow[]`. Discovers `rows.json` recursively under a dir (skips `manifest.json`). Strict: throws with file+index context on any bad row. Pure/testable. |
| `derive.mjs` | Data-driven `derive(rows)` → `setups` read-model. Discovers setups/tasks **from the rows** (not a hardcoded catalog); reuses `PASS_THRESHOLD`/`passAtK` from `seed/mock-data.mjs`. Also a standalone re-derive CLI. |
| `catalog.mjs` | The dashboard vocabulary: curated `model`/`harness` keys → display metadata, plus per-setup `order`/`color` overrides. Unknown keys are **synthesized, never dropped** (and warned). |
| `firestore.mjs` | Shared plumbing: target selection, prod-write guard, batched commits, deterministic raw-row doc id. |
| `ingest.mjs` | The CLI. Idempotent, additive upsert: upload raw → re-derive → upsert metadata. |

## Running

```bash
npm install          # firebase-admin (run once, in this dir)
```

## Local dev quickstart (emulator → UI)

End-to-end loop to see ingested data in the dashboard locally. Run each numbered
block from the directory shown in its comment.

> **Project id must match the UI.** The emulator separates data by project id,
> and the web client uses `VITE_FIREBASE_PROJECT_ID` (committed as
> `devops-bench-shared` in `.env`). So seed/derive with
> `GCLOUD_PROJECT=devops-bench-shared` — otherwise the UI reads a different
> namespace and shows nothing. (If you prefer another id, set a matching
> `VITE_FIREBASE_PROJECT_ID` in `site_new/.env.local`.)

```bash
# 1. Run the emulator  (from site_new/ — leave running in its own terminal)
export PATH="/opt/homebrew/opt/openjdk/bin:$PATH"     # emulator needs Java (brew install openjdk)
npx -y firebase-tools emulators:start --only firestore --project devops-bench-shared
#    Firestore on :8080, emulator UI on :4000

# 2. Seed the data using the fixtures  (from site_new/ingest/)
FIRESTORE_EMULATOR_HOST=127.0.0.1:8080 GCLOUD_PROJECT=devops-bench-shared \
  node ingest.mjs fixtures/

# 3. Re-derive (optional — only needed after changing the formula or catalog.mjs)
FIRESTORE_EMULATOR_HOST=127.0.0.1:8080 GCLOUD_PROJECT=devops-bench-shared \
  node derive.mjs

# 4. Run the UI that connects to the emulator  (from site_new/)
npm install        # first time only (app deps)
npm run dev        # Vite on http://localhost:5173 — dev mode → emulator, DB leaderboard-test
```

`npm run dev` reads the emulator (DB `leaderboard-test`) because mode
`development` sets `VITE_USE_EMULATOR=true`; ingest writes that same DB by
default, so the two line up with no extra config. The detailed reference for each
command follows below.

### Option A — local emulator (no credentials)

The ingest connects to a Firestore emulator via `FIRESTORE_EMULATOR_HOST`; you
must **start the emulator first** (it does not launch one).

```bash
# 1. The Firestore emulator needs Java (keg-only via Homebrew):
brew install openjdk
export PATH="/opt/homebrew/opt/openjdk/bin:$PATH"

# 2. Start the emulator (from site_new/, leave it running in another terminal):
cd .. && npx -y firebase-tools emulators:start --only firestore --project devops-bench-demo
# Firestore on :8080, emulator UI on :4000

# 3. Ingest against it (from site_new/ingest/):
FIRESTORE_EMULATOR_HOST=127.0.0.1:8080 GCLOUD_PROJECT=devops-bench-demo \
  node ingest.mjs fixtures/
```

### Option B — shared TEST database (real Firestore)

Uses Application Default Credentials — run `gcloud auth application-default login`
first. No emulator needed.

```bash
GCLOUD_PROJECT=devops-bench-shared FIRESTORE_DATABASE_ID=leaderboard-test \
  node ingest.mjs ./results/run_20260601_120000/rows.json
```

Each path argument is either a `rows.json` file or a directory searched
**recursively** for `rows.json` files (so a single `run_<ts>/` or a whole
`results/` tree both work; `manifest.json` is ignored). Defaults to
`$RESULTS_ROOT`.

### What `ingest.mjs` does, step by step

1. **Load + validate** every row from the given files (`load.mjs`). Any invalid
   row aborts the whole batch with a line-by-line report — no partial ingest.
2. **Upsert raw rows** into `results` with id
   `setupId__runId__taskFolder__iteration`, so re-ingesting a run overwrites
   rather than duplicates (**idempotent**).
3. **Re-derive `setups`** from the **full** `results` set (not just this upload),
   so prior runs' history is preserved (**history-complete**).
4. **Upsert `models` / `harnesses`** metadata (`merge: true`) for every key the
   full set references. Unknown keys are synthesized and **warned** — add them to
   `catalog.mjs`.

## Re-deriving without uploading

Changed the scoring formula (`PASS_THRESHOLD` / pass@k in `seed/mock-data.mjs`)
or `catalog.mjs` presentation? Re-score every setup from the **existing** raw
rows — no re-upload (emulator from Option A still running, or ADC for real Firestore):

```bash
FIRESTORE_EMULATOR_HOST=127.0.0.1:8080 GCLOUD_PROJECT=devops-bench-demo \
  node derive.mjs
```

This reads all of `results`, re-runs `derive()`, and rewrites `setups` + metadata.

## Targets & the production guard

Same selection as `seed.mjs`:

- **Emulator** when `FIRESTORE_EMULATOR_HOST` is set (no credentials).
- **Real Firestore** otherwise, via Application Default Credentials
  (`gcloud auth application-default login`).
- `FIRESTORE_DATABASE_ID` picks the named DB; defaults to **`leaderboard-test`**.

Writing the **production** database (`leaderboard`) is refused unless
`ALLOW_PROD_INGEST=true` is set — so a stray invocation can't clobber prod.

```bash
# Publish to production (deliberate):
GCLOUD_PROJECT=devops-bench-shared FIRESTORE_DATABASE_ID=leaderboard \
  ALLOW_PROD_INGEST=true node ingest.mjs ./runs/
```

## Tests

```bash
npm test     # from site_new/ — vitest covers load/derive/catalog
```
