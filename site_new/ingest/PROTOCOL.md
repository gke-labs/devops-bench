# Upload protocol — `ResultRow[]` (`rows.json`)

This is the contract between an eval run and the leaderboard ingest. The Python
eval harness writes one **`rows.json` per run** (a flat array of `ResultRow`
objects) under `results/run_<timestamp>/`, alongside a `manifest.json` the ingest
does **not** read. `ingest.mjs` validates the rows, writes them to the raw
`results` collection, and re-derives everything the dashboard renders.

If a file validates against this document, it will ingest. Nothing else about
how it was produced matters.

---

## 1. What you provide vs. what is computed

You provide **only `ResultRow[]`** — the raw, per-iteration source of truth.
Everything the dashboard displays is *derived from it* by ingest and must **not**
appear in the input:

| Layer | Who produces it | In the upload? |
|---|---|---|
| `ResultRow` (raw rows) | **the harness** | ✅ yes — this is the protocol |
| `Setup` / `Task` / `HistoryPoint` (read-model) | `derive()` at ingest | ❌ no — computed |
| `Model` / `Harness` display metadata | `catalog.mjs` (hardcoded in this repo) | ❌ no — see §6 |

There is no top-level envelope object. A `rows.json` file is literally a JSON
array:

```json
[ { /* ResultRow */ }, { /* ResultRow */ }, ... ]
```

Rows may be split across **any number of files**. Point `ingest.mjs` at a single
`rows.json`, at one `run_<ts>/` directory, or at the whole `results/` tree —
directory arguments are searched recursively for `rows.json` (the sibling
`manifest.json` is skipped). Grouping is by field values (§4), never by file or
directory.

---

## 2. The `ResultRow` object

One row = **one (setup × task × run × iteration)** — the atomic unit. Today the
harness emits exactly one iteration per (setup × task × run), so `iteration` is
always `0`; the schema is already shaped for multi-iteration runs (§4).

| Field | Type | Constraint | Meaning |
|---|---|---|---|
| `setupId` | string | non-empty | The setup this row belongs to. The dashboard's join key (§3). |
| `model` | string | curated key | Model key, e.g. `"alpha-pro"`. Must exist in `catalog.mjs` (§6). |
| `harness` | string | curated key | Harness key, e.g. `"gemini-cli"`. Must exist in `catalog.mjs` (§6). |
| `augmentation` | string[] | tokens | Capability tokens stacked on the base pairing, e.g. `["mcp", "skills"]`. **`[]` means baseline.** |
| `runId` | string | `^run_\d{8}_\d{6}(_<suffix>)?$` | Run id, `run_YYYYMMDD_HHMMSS` with an optional `_<suffix>`. Identifies the run; ties its tasks/iterations together. The timestamp alone is not unique, so isolated parallel runs append a `_<suffix>` (pid / matrix id) to stay distinct in the `setupId__runId__taskFolder__iteration` doc id. |
| `t` | string | ISO 8601 | Run timestamp, e.g. `"2026-06-01T12:00:00Z"`. The trend x-axis. |
| `taskFolder` | string | non-empty | Task folder id, e.g. `"deploy-config"`. The task axis key. |
| `taskName` | string | non-empty | Human-readable task name. |
| `iteration` | integer | `>= 0` | 0-based iteration index within the run (always `0` today). |
| `status` | string | `"success"` \| `"failed"` | Terminal outcome of the iteration (the harness flags crashes/timeouts). |
| `outcomeScore` | number \| null | `[0, 1]` or null | Judge outcome score. Passes at `>= 0.7` (the threshold lives in `derive`). **`null` when unscored** (§5). |
| `toolScore` | number \| null | `[0, 1]` or null | Tool-invocation score; `null` when unscored. |
| `latencySec` | number | `>= 0` | Agent wall-clock latency, seconds. |
| `inputTokens` | integer \| null | `>= 0` or null | Prompt tokens consumed; `null` when usage was not captured. |
| `outputTokens` | integer \| null | `>= 0` or null | Completion tokens produced; `null` when usage was not captured. |

`setupId`, `model`, `harness`, `augmentation`, `runId`, `t` are **denormalized
onto every row** — they repeat across all of a run's rows (they mirror the run's
`manifest.json`). That redundancy is intentional: each row is self-describing and
lands in `results` verbatim, so the ingest never needs the manifest.

---

## 3. The join key (read before choosing `setupId`)

`setupId` is the **grouping key for the entire dashboard** — one `setupId`
becomes one line on the leaderboard. By convention it is the tuple
`(model, harness, augmentation)` rendered as:

```
<model>-<harness>[-<sorted augmentation tokens>]   // non-alphanumerics stripped
```

The augmentation tokens are **sorted** so the id is independent of token order,
and a baseline arm (no tokens) has **no augmentation suffix**.

Examples:

| model | harness | augmentation | `setupId` |
|---|---|---|---|
| `alpha-pro` | `gemini-cli` | `["mcp", "skills"]` | `alpha-pro-gemini-cli-mcp-skills` |
| `gamma-coder` | `api-loop` | `[]` | `gamma-coder-api-loop` |

**Rules:**
- Keep `setupId` **stable across runs** — that's what stitches a setup's history
  together over time. Two runs that should appear as one trend line must share a
  `setupId`.
- The identity fields (`setupId` + `model`/`harness`/`augmentation`) must be
  **consistent**: every row with a given `setupId` should carry the same
  model/harness/augmentation. (Derive reads identity from the first row it sees
  for a setup.)

Within a setup, ingest sub-groups by `t` (→ history points) and by `taskFolder`
(→ the per-task table at the latest run), collapsing `iteration` rows via the
pass@k formula.

---

## 4. How rows become the dashboard

`derive()` (run automatically by `ingest.mjs`) does, per `setupId`:

- **`tasks[]`** — for the **latest** `t`, group by `taskFolder`; each task's
  `pass1/pass5/passMax` is computed from its iterations' `outcomeScore`s.
- **`history[]`** — one point per distinct `t` (time-ordered); each point is the
  mean of that run's per-task scores.

Scoring (single definition, in `seed/mock-data.mjs`, reused by ingest):
- An iteration **passes** when `outcomeScore >= 0.7`.
- `pass1` = pass rate over the run's scored iterations.
- `pass5` / `passMax` are **`null` today**: the harness emits a single iteration
  per (setup × task × run), so a pass@k estimate would only ever collapse onto
  `pass1`, and the dashboard hides metrics that are all-null. The pass@k
  estimator is retained in `derive` and re-enables, unchanged, once the harness
  starts emitting multi-iteration runs.

---

## 5. Failed / errored iterations

A failed iteration is **kept**, not dropped: it carries `status: "failed"` and a
`null` `outcomeScore` (and typically `null` token counts). Derive **excludes
null-scored iterations** from both the pass numerator and denominator — a missing
score is missing data, not a 0%, which is the correct statistical treatment. Do
**not** invent a `0.0` score for a crash; that would wrongly drag the pass rate
down.

Keeping the row (rather than omitting it) means the failure stays visible
downstream — the raw `results` collection records that the iteration ran and how
it ended.

(If a task has *zero* scored iterations in a run, its scores derive to `null` and
the dashboard renders them blank.)

---

## 6. Model & harness keys must exist in the catalog

Rows carry only the `model`/`harness` **keys**, never display metadata
(name/provider/license/logo, type/accent). That metadata is **hardcoded** in
`catalog.mjs` and upserted into the `models`/`harnesses` collections at ingest.

- Use keys that already exist in `catalog.mjs` (`MODELS` / `HARNESSES`).
- A key **not** in the catalog is **not dropped** — ingest synthesizes minimal
  metadata and prints a `⚠ unknown model/harness` warning. Add a real entry to
  `catalog.mjs` to give it a proper name/logo. (A setup whose metadata never
  resolves is silently hidden by the frontend, so heed the warning.)

`order` and `color` (per-setup presentation) are likewise **not** in the upload;
they default to discovery order + a palette, overridable per `setupId` via
`SETUP_CATALOG` in `catalog.mjs`.

---

## 7. Idempotency

Each raw row's Firestore id is `setupId__runId__taskFolder__iteration`. Re-uploading
the same run **overwrites** those rows instead of duplicating them, so a corrected
re-run is safe. `setups` are always re-derived from the **full** `results` set,
so previously ingested runs keep their history.

---

## 8. Minimal valid file

```json
[
  {
    "setupId": "alpha-pro-gemini-cli-mcp-skills",
    "model": "alpha-pro",
    "harness": "gemini-cli",
    "augmentation": ["mcp", "skills"],
    "runId": "run_20260601_120000",
    "t": "2026-06-01T12:00:00Z",
    "taskFolder": "get-app-architecture",
    "taskName": "Summarize Application Architecture",
    "iteration": 0,
    "status": "success",
    "outcomeScore": 0.9,
    "toolScore": 0.85,
    "latencySec": 12.35,
    "inputTokens": 9000,
    "outputTokens": 420
  }
]
```

See `fixtures/run_20260601_120000/rows.json` and
`fixtures/run_20260615_120000/rows.json` for a two-run example (the latter also
carries a `manifest.json` the ingest skips).
