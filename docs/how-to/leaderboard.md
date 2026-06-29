# Operating the leaderboard

The devops-bench leaderboard (`site_new/`) is a React + Vite single-page app that
ranks **model × harness** pairings across DevOps tasks. It is backed by **Cloud
Firestore** and served via **Firebase Hosting**. The live site is at
<https://gke-labs.github.io/devops-bench/>.

The site is **read-only in the browser**: it loads its data once on page load and
does no score math. All scoring is baked in ahead of time, at *ingest* — the step
that turns a finished eval run into the documents the dashboard renders. This
guide explains how the data is organized, what the eval harness has to produce,
and how to ingest a new run and deploy the site.

If you are here to *produce* a run rather than publish one, start with
[running evals](./run-evals.md). For what the per-task metrics mean, see
[metrics](../components/metrics.md). For the project at large, see the
[root README](../../README.md).

## Data model

Everything the leaderboard knows lives in four Firestore collections. Only three
of them are ever read by the browser; the fourth is the raw record the rest is
built from.

| Collection | Role |
|---|---|
| `results` | Raw, immutable source of truth — one document per `(setup × task × run × iteration)`. **Not read by the browser.** |
| `setups` | The derived read-model the dashboard renders: per-task scores plus history over time. One document per setup. |
| `models` | Display metadata for each model — name, provider, license, logo. |
| `harnesses` | Display metadata for each harness — name, type, accent color, logo. |

The guiding principle:

> [!IMPORTANT]
> Raw `results` is the source of truth; `setups` is a **derived projection** of
> it. If the scoring formula changes, you **re-derive** — you never re-collect.
> The continuous scores in `results` carry enough signal to recompute any
> threshold or pass@k formula after the fact.

There is **one Firebase project**, `devops-bench-shared`, holding **two named
Firestore databases**:

| Database | Use |
|---|---|
| `leaderboard-test` | Staging — iterate here freely. The default target. |
| `leaderboard` | Production — what the live site reads. Guarded against accidental writes. |

The frontend never branches on environment; the target database is selected
entirely by Vite mode (committed `.env.<mode>` files), and the ingest tooling
selects it by environment variable. More on both below.

## The data protocol

An eval run hands the leaderboard a single artifact: a **`rows.json`** file. It is
a bare JSON array of `ResultRow` objects — no envelope, no wrapper:

```json
[ { /* ResultRow */ }, { /* ResultRow */ }, ... ]
```

The harness writes one `rows.json` per run under `results/run_<timestamp>/`, beside
a `manifest.json` that the ingest **ignores**. One `ResultRow` is one
`(setup × task × run × iteration)` — the atomic unit. You provide *only* these
raw rows; setups, tasks, history, and all display metadata are computed downstream
and must not appear in the file.

Each row carries its setup and run identity (`setupId`, `model`, `harness`,
`augmentation`, `runId`, `t`) alongside the task, status, scores, latency, and
token counts — the identity fields are denormalized onto **every** row, so each
row is self-describing and the ingest never needs the manifest. The harness emits
rows in this shape for you; for the exact field list and validation rules, see
[`site_new/ingest/PROTOCOL.md`](../../site_new/ingest/PROTOCOL.md).

### The `setupId` convention

By convention `setupId` is the `(model, harness, augmentation)` tuple, rendered as:

```
<model>-<harness>[-<sorted augmentation tokens>]
```

Augmentation tokens are **sorted** so the id is independent of token order, and a
baseline arm (no tokens) has no augmentation suffix.

| model | harness | augmentation | `setupId` |
|---|---|---|---|
| `gemini-3.1-pro` | `gemini-cli` | `["mcp", "skills"]` | `gemini-3.1-pro-gemini-cli-mcp-skills` |
| `gamma-coder` | `api-loop` | `[]` | `gamma-coder-api-loop` |

> [!IMPORTANT]
> Keep `setupId` **stable across runs** — that is what stitches a setup's history
> into one trend line. Every row sharing a `setupId` must also carry the same
> model / harness / augmentation; derive reads identity from the first row it sees
> for a setup.

A failed iteration is kept, not dropped: it carries `status: "failed"` and a
`null` `outcomeScore`. Derive **excludes** null-scored iterations from both the
numerator and denominator of the pass rate — a missing score is missing data, not
a 0%. Do not invent a `0.0` for a crash.

## How ingest works

The ingest CLI lives in `site_new/ingest/`. Running `ingest.mjs` validates the
rows, upserts them into the raw `results` collection (**idempotently** — a doc id
derived from the row's natural key means re-ingesting a run overwrites rather than
duplicates), re-derives the `setups` read-model from the **full** `results` set so
history stays complete, and refreshes `models` / `harnesses` metadata. Unknown
model/harness keys are synthesized with a warning rather than dropped — add real
entries to `catalog.mjs` to give them a name, logo, and color. Because scoring
lives in one place and is reused by derive, you can re-score history from existing
rows without re-uploading (see [Re-derive only](#re-derive-only-no-re-upload)).

For the stage-by-stage breakdown, see
[`site_new/ingest/README.md`](../../site_new/ingest/README.md).

## Ingest new results — step by step

### One-time setup

```bash
cd site_new/ingest
npm install
```

A path argument to `ingest.mjs` may be a single `rows.json` **or a directory**,
which is searched recursively for `rows.json` files. So a single `run_<ts>/`
directory or a whole `results/` tree both work; `manifest.json` is always skipped.

### Against the shared TEST database (real Firestore)

This is where you should iterate. It uses Application Default Credentials and the
`leaderboard-test` database.

```bash
gcloud auth application-default login   # once

GCLOUD_PROJECT=devops-bench-shared FIRESTORE_DATABASE_ID=leaderboard-test \
  node ingest.mjs ./results/run_20260601_120000/rows.json
```

### To production (deliberate, guarded)

Writing the `leaderboard` database is **refused** unless `ALLOW_PROD_INGEST=true`
is set, so a mistargeted run cannot clobber prod.

```bash
GCLOUD_PROJECT=devops-bench-shared FIRESTORE_DATABASE_ID=leaderboard \
  ALLOW_PROD_INGEST=true node ingest.mjs ./runs/
```

### Re-derive only (no re-upload)

After changing the scoring formula or `catalog.mjs`, re-score every setup from the
**existing** raw rows — no upload needed. Run `derive.mjs` with the same target
env you would pass to `ingest.mjs`:

```bash
# Example: re-derive the TEST database
GCLOUD_PROJECT=devops-bench-shared FIRESTORE_DATABASE_ID=leaderboard-test \
  node derive.mjs
```

This reads all of `results`, re-runs derive, and rewrites `setups` plus metadata.

> [!TIP]
> If your run came from a parallel matrix — one `rows.json` per task — combine the
> per-task files into a single `rows.json` first, then ingest the combined file:
>
> ```bash
> python -m devops_bench.results.aggregate <results-root> -o <results-root>
> ```
>
> See [running evals](./run-evals.md) for how the matrix lays out its output.

## Local emulator

For local development you can run everything against the Firestore emulator — no
credentials, no shared database. It needs **Java** and must be **started
manually**; the ingest only connects when `FIRESTORE_EMULATOR_HOST` is set, it
never launches one.

```bash
# Terminal 1 — start the emulator (from site_new/), leave it running
firebase emulators:start --only firestore --project devops-bench-shared

# Terminal 2 — ingest into it (from site_new/ingest/)
FIRESTORE_EMULATOR_HOST=127.0.0.1:8080 GCLOUD_PROJECT=devops-bench-shared \
  node ingest.mjs fixtures/
```

`npm run dev` (below) connects to this same emulator, so once you've ingested you
can see the result immediately in the dev server.

## Run and deploy the site

All commands run from `site_new/`. The target database is chosen by Vite mode, so
switching environments is a one-word change rather than a code edit.

| Command | Firestore | Database |
|---|---|---|
| `npm run dev` | emulator (localhost) | `leaderboard-test` |
| `npm run dev:staging` | real | `leaderboard-test` |
| `npm run build` | real | `leaderboard` (prod) |
| `npm run preview` | serves the last `build` output | — |
| `npm test` | — (DB-free unit + component tests) | — |

`npm run dev` connects to the emulator, which is the same database the default
ingest writes — so the two line up with no extra config, and you can ingest into
the emulator and immediately see it in the dev server.

To publish the site, build against prod and deploy the rules and hosting:

```bash
cd site_new
npm run build
npx -y firebase-tools deploy --only firestore:rules,hosting --project devops-bench-shared
```

## Gotchas

- **Firestore is schemaless.** It enforces no field types or required fields; the
  document shapes above are a convention upheld only by the writer (ingest) and
  the reader. There is no database-side validation — get the `rows.json` right.
- **An unresolved setup is silently hidden.** If a setup's `model` or `harness`
  metadata never resolves, the frontend drops it from the dashboard. Heed every
  `⚠ unknown model/harness` warning from the ingest and add the real entry to
  `catalog.mjs`.
- **Prod writes need `ALLOW_PROD_INGEST=true`.** Without it, any attempt to write
  the `leaderboard` database is refused and the process exits.
- **The emulator needs Java and must be started manually.** The ingest connects to
  an already-running emulator via `FIRESTORE_EMULATOR_HOST`; it never starts one.
- **Keep `runId` suffixes unique for parallel runs.** The raw doc id is
  `setupId__runId__taskFolder__iteration`; isolated parallel runs that share a
  timestamp must append a distinct `_<suffix>` so their docs don't collide and
  overwrite each other.
