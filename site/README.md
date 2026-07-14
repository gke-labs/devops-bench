# devops-bench Leaderboard (`site`)

A React + Vite dashboard for the devops-bench benchmark. It shows **model ×
harness** pairings scored across DevOps tasks, with faceted filtering, per-task
breakdowns, and score-over-time trends. Data is served from **Firestore**.

This README covers three things:

1. [**Data model**](#1-data-model) — how we store benchmark data in (schemaless) Firestore
2. [**App architecture**](#2-app-architecture--data-flow) — how data flows through the React app
3. [**Running locally**](#3-running-locally-dev--staging--prod) — dev / staging / prod commands & DB wiring

---

## 1. Data model

> **Firestore is schemaless.** It enforces no field types, no required fields, and
> no collection structure — any document can hold anything. The shapes below are a
> **convention**, upheld only by the *writer* (`seed/` and the future ingest path)
> and the *reader* (`src/lib/data.js`); the database will not reject a malformed
> doc. This section *is* the schema — there's nowhere else it lives.
>
> A machine-readable mirror of these shapes lives in **`src/lib/schema.d.ts`** and
> is referenced from the JS via JSDoc (`@typedef {import('./schema').Setup}`) for
> editor hints / `// @ts-check`. It's *documentation, not validation* — it can't
> reject a bad doc either. Because the DB makes no guarantees, the reader defends
> at the boundary: it **drops setups whose `model`/`harness` id doesn't resolve**
> (logged, not silent), and the UI treats every score as **nullable** — see below.

### Design principle: raw is the source of truth, the rest is derived

The benchmark's atomic fact is a single **task execution**. Those raw records are
stored immutably; everything the dashboard renders is a *derived projection* of
them. Changing the scoring formula never requires re-collecting data — only
re-deriving.

```
results (raw, immutable)  ──derive()──▶  setups (derived read-model)  ──▶  dashboard reads
   one doc per execution                  pass1/5/max baked in              (never touches `results`)
```

### Collections (4)

#### `models/{modelId}` — metadata, read by the UI
Document id is the model key (e.g. `alpha-pro`).

| field | type | notes |
|---|---|---|
| `name` | string | display name (e.g. "Alpha Pro") |
| `provider` | string | e.g. "Acme" |
| `license` | string | "Proprietary" / "Open Source" |
| `logo` | string | logo key → `BrandLogo` (`alpha` / `beta` / `gamma`) |

#### `harnesses/{harnessId}` — metadata, read by the UI
Document id is the harness key (e.g. `gemini-cli`).

| field | type | notes |
|---|---|---|
| `name` | string | e.g. "Gemini CLI" |
| `type` | string | `cli` or `api` (BENCH_AGENT_TYPE family) |
| `accent` | string | hex color tinting the harness chip/icon |
| `logo` | string | glyph key → `HarnessIcon` (`terminal` / `claw` / `braces`) |

#### `results/{autoId}` — RAW source of truth (NOT read by the client)
One document per `(setup × task × run × iteration)`.

| field | type | notes |
|---|---|---|
| `setupId` | string | which setup this execution belongs to |
| `model`, `harness`, `mcp`, `augmentation` | string/bool | denormalized dimensions for querying |
| `runId` | string | `run_<timestamp>` — groups a batch of executions |
| `t` | string (ISO 8601) | run timestamp; the x-axis of the trend chart |
| `taskFolder` | string | real `tasks/<folder>` id |
| `taskName` | string | display name |
| `iteration` | number | the repeat index (the old "Run #"), for pass@k |
| `outcomeScore` | number `[0,1]` | **continuous** judge score — the real raw signal |
| `toolScore` | number `[0,1]` | tool-invocation score |
| `latencySec`, `inputTokens`, `outputTokens` | number | telemetry (not yet surfaced in the UI) |

> **Why `outcomeScore` is continuous, not a `pass` boolean:** a boolean bakes in a
> threshold. Storing the continuous score lets the pass/fail threshold and the
> pass@k formula change later without re-collecting data.

#### `setups/{setupId}` — DERIVED read-model (what the dashboard renders)
Document id is the setup id, e.g. `alpha-pro-gemini-cli-gca-mcp`. The same value
is also stored in the `id` field (the client reads `doc.data()`, not `doc.id`).

| field | type | notes |
|---|---|---|
| `id` | string | equals the document id |
| `order` | number | generation index → stable `orderBy('order')` load |
| `model`, `harness` | string | keys into `models` / `harnesses` |
| `mcp` | bool | BENCH_USE_MCP modifier |
| `augmentation` | string | `baseline` / `gca` |
| `color` | string | hex line/bar color for this setup |
| `tasks` | array\<TaskScore\> | per-task scores at the **latest** run |
| `history` | array\<HistoryPoint\> | setup-wide aggregate per run, time-ordered |

```jsonc
// TaskScore                         // HistoryPoint
{                                    {
  "folder": "get-app-architecture",   "t": "2026-06-01T00:00:00Z",
  "name":   "Summarize ...",          "scores": { "pass1": 90.8, "pass5": 94.0, "passMax": 96.0 }
  "scores": { "pass1": 95,          }
              "pass5": 100,
              "passMax": 100 }
}
```

> Arrays (`tasks`, `history`) are **embedded** in the setup doc rather than stored
> as subcollections: the dashboard always wants the whole setup at once, so one
> read per setup beats N subcollection queries. The read-model is denormalized on
> purpose.

> **Scores are nullable.** A `scores` entry (`pass1`/`pass5`/`passMax`) may be
> `null` or absent for a task/run with no scored iterations. The mock generator
> always produces complete scores, but real ingest can be sparse, so the UI
> treats them as `number | null` throughout: aggregates ignore nulls (`setupScore`,
> the detail Best/Average/Median cards), the task bar and trend table render `—`,
> and the trend chart's y-axis auto-fits the present scores (clamped to `[0,100]`)
> instead of a fixed window so low scores aren't clipped.

### The derivation formula (one place, swappable)

Lives in `seed/mock-data.mjs` (`derive()` + `passAtK()`), and is the *only* place
scores are computed:

- A "pass" = `outcomeScore >= PASS_THRESHOLD` (currently **0.7**).
- `pass1` = pass rate = `c / n` over a task's `n` iterations in a run (`c` passes).
- `pass5` = unbiased `pass@5` = `1 − C(n−c, 5) / C(n, 5)`.
- `passMax` = `pass@n` ("ever passed").
- `tasks[]` scores come from the **latest run's** iterations.
- Each `history[]` point is the **mean across tasks** of that run's per-task scores.

### Access (security rules, `firestore.rules`)

- `models`, `harnesses`, `setups` → **public read**, no client writes.
- `results` → **no client access at all** (raw data stays server-side).
- Seeding/ingest uses the Admin SDK, which bypasses rules.

---

## 2. App architecture & data flow

The app is a read-only SPA: it loads the three read-model collections **once** on
mount, holds them in React context, and every view is a pure derivation of that
in-memory data. No realtime listeners — `loadBenchmarkData` does one-shot
`getDocs`, and the connection is closed after the first read.

### Data flow (browser)

```
firebase.js (db)                     # modular Firestore client; env-driven config + DB/emulator select
   └─▶ useBenchmarkData()            # useEffect → loadBenchmarkData(db) ONCE → {…, loading, error}
        └─▶ BenchmarkProvider        # holds {models, harnesses, setups, loading, error} in context
             └─▶ useBenchmark()      # consumed by pages, no prop-drilling
                  ├─▶ Leaderboard / Detail        # page state: metric + filters (useState/useMemo)
                  └─▶ lib/accessors + lib/filters  # PURE derivations of display values from setups
```

The client reads **only** the three read-model collections via `loadBenchmarkData`
(`getDocs` on `models`, `harnesses`, and `query(setups, orderBy('order'))`). It
never reads `results`. All scoring is already baked into `setups` by `derive()`,
so the browser does zero score math — only selection, sorting, and formatting.
`loadBenchmarkData` also drops any setup whose `model`/`harness` id doesn't resolve
(logged via `console.warn`), so downstream views can assume every reference is
valid and never crash on a dangling id.

### How data gets into the database

```
seed/mock-data.mjs  generateRaw() ─┐
                                   ├─▶ seed/seed.mjs (firebase-admin) ─▶ Firestore (emulator or real DB)
                    derive(raw) ───┘     writes: models, harnesses, results, setups
```

`seed.mjs` writes via the Admin SDK (bypassing rules). The real ingest path simply
replaces `generateRaw()` with an eval-results adapter and **reuses the same
`derive()`** — so raw `results` and the derived `setups` stay consistent.

### Directory layout

```
site/
├── index.html              # Vite entry: <div id="root"> + /src/main.jsx
├── vite.config.js          # @vitejs/plugin-react, manualChunks, Vitest config
├── tailwind.config.js      # Tailwind (build-time, not CDN)
├── firebase.json           # Hosting (dist + SPA rewrite) + rules for BOTH named DBs
├── firestore.rules         # security rules (see §1)
├── .firebaserc             # default project id (real project passed via --project on deploy)
├── .env, .env.<mode>       # per-environment config (see §3)
│
├── src/
│   ├── main.jsx            # createRoot → <App/>
│   ├── App.jsx             # BrowserRouter + BenchmarkProvider + routes
│   ├── index.css           # @tailwind layers + small custom CSS
│   │
│   ├── lib/                # ── framework-agnostic logic (no React) ──
│   │   ├── firebase.js     #   modular SDK init: env-driven config + named-DB + emulator connect
│   │   ├── data.js         #   loadBenchmarkData(db) → {models, harnesses, setups}
│   │   ├── accessors.js    #   pure: setupScore/History/Label/Tags, allRunDates, formatRunDate
│   │   ├── filters.js      #   pure: faceted filtering (build groups, getFilteredSetups)
│   │   └── vocab.js        #   display constants (AUGMENTATIONS, METRIC_LABELS, …)
│   │
│   ├── hooks/useBenchmarkData.js    # loads data once → {…, loading, error}
│   ├── context/BenchmarkContext.jsx # provides that data to the whole tree
│   │
│   ├── components/         # ── presentational ──
│   │   ├── Logo.jsx        #   BrandLogo / HarnessIcon (SVG)
│   │   ├── Chip.jsx        #   Tag / TypeChip
│   │   ├── MetricToggle.jsx#   Pass@1/5/Max segmented control (shared)
│   │   ├── SetupIdentity.jsx#  model × harness block (shared: row + hero)
│   │   ├── FilterBar.jsx   #   faceted filter UI
│   │   ├── LeaderboardRow.jsx
│   │   ├── TrendChart.jsx  #   react-chartjs-2 line + sr-only a11y table (shared)
│   │   └── States.jsx      #   Loading / LoadError / EmptyState / NotFound
│   │
│   └── pages/
│       ├── Leaderboard.jsx #   route "/"          (filters + metric + chart)
│       └── Detail.jsx      #   route "/setup/:id" (hero + summary + task table + chart)
│
└── seed/                   # ── Node tooling (own package.json) ──
    ├── mock-data.mjs       #   models/harnesses + generateRaw() + derive() + passAtK()
    └── seed.mjs            #   firebase-admin → writes the emulator OR a real named DB
```

### Routing

`react-router-dom` (`BrowserRouter`):

| route | page | notes |
|---|---|---|
| `/` | `Leaderboard` | filter + metric state via `useState`/`useMemo` |
| `/setup/:id` | `Detail` | `:id` selects the setup; `?metric=` carries the metric over |

Deep links need a server rewrite to `index.html` — handled by `firebase.json` for
Firebase Hosting.

### Tooling

- **Vite** (`@vitejs/plugin-react`) — dev server; production build to `dist/`, split
  into `react` / `firebase` / `charts` vendor chunks via `manualChunks`.
- **Tailwind** via PostCSS (purged at build; no CDN).
- **Firebase** modular SDK (tree-shaken) on the client; **firebase-admin** in `seed/`.
- **Chart.js** via `react-chartjs-2`.
- **Vitest** (+ jsdom, Testing Library) — see [Testing](#testing).

---

## 3. Running locally (dev / staging / prod)

There is **one Firebase project** (`devops-bench-shared`) with **two named
Firestore databases**: `leaderboard-test` (fabricated data) and `leaderboard`
(real, production data). The code never branches on environment — the target is
chosen entirely by **Vite mode** via committed `.env.<mode>` files, so switching
environments is a one-word change, not a code edit.

| command | mode | Firestore | database |
|---|---|---|---|
| `npm run dev` | development | **emulator** (localhost) | `leaderboard-test` |
| `npm run dev:staging` | staging | **real** | `leaderboard-test` |
| `npm run build:staging` | staging | **real** | `leaderboard-test` |
| `npm run build` | production | **real** | `leaderboard` (prod) |
| `npm run preview` | — | serves the last `build` output | — |

**How the switch works** — config is layered (Vite precedence, highest first):

```
.env.<mode>.local   gitignored, per-mode personal override
.env.local          gitignored, all-mode personal override   ← do NOT pin the DB id here
.env.<mode>         committed, per-target: VITE_FIRESTORE_DATABASE_ID + VITE_USE_EMULATOR
.env                committed, shared Firebase project config
```

A Firebase web API key is **public** (access is enforced by Security Rules), so the
committed `.env*` files are safe to ship; only `.env.local` is gitignored. See
`.env.example`.

> The Vite mode is named **`staging`**, not `test`, because Vitest reserves the
> `test` mode; the *database* is still named `leaderboard-test`.

### Install

```bash
npm install
cd seed && npm install && cd ..
```

### A) Local emulator (offline, no cloud, default)

Needs **Java** for the Firestore emulator
(`brew install openjdk`; then `export PATH="/opt/homebrew/opt/openjdk/bin:$PATH"`).

```bash
# 1. start the emulator (Firestore :8080, UI :4000)
npx -y firebase-tools emulators:start --only firestore --project devops-bench-demo

# 2. in another shell: seed the emulator (writes to the leaderboard-test DB)
cd seed && FIRESTORE_EMULATOR_HOST=127.0.0.1:8080 GCLOUD_PROJECT=devops-bench-demo npm run seed && cd ..

# 3. run the app — firebase.js auto-connects to the emulator on localhost
npm run dev          # http://localhost:5173
```

### B) Staging (real cloud DB, fabricated data)

> ✅ `leaderboard-test` is **already created and seeded** — just run the dev server:

```bash
npm run dev:staging                       # dev server → real leaderboard-test
```

To re-seed it later (overwrites the mock data):

```bash
gcloud auth application-default login     # once, for the Admin-SDK seeder
cd seed && npm run seed:test && cd ..
```

### C) Production (real cloud DB, real data)

```bash
npm run build        # bundles against the prod `leaderboard` DB → dist/
npm run preview      # serve the built bundle locally to sanity-check
```

The prod `leaderboard` DB is filled by the real ingest pipeline. The mock seeder
**hard-refuses** to write fabricated data there (override only with
`ALLOW_PROD_SEED=true`).

### Testing

```bash
npm test             # Vitest — fast, DB-free unit + component tests
```

| file | covers |
|---|---|
| `src/lib/accessors.test.js` | score/label/history/date accessors, null-safe y-axis bounds |
| `src/lib/filters.test.js` | faceted filtering (OR-within / AND-across, option derivation) |
| `src/lib/data.test.js` | `loadBenchmarkData` shaping + query, drops dangling-ref setups (mocked Firestore SDK) |
| `seed/mock-data.test.mjs` | `passAtK`, `derive()` invariants, `generateRaw()` determinism |
| `src/pages/Leaderboard.test.jsx` | render rows, filter narrows list, metric toggle |
| `src/pages/Detail.test.jsx` | stat-card math (incl. null-safe / empty), task-table sorting, `?metric=` param, not-found/loading/error |
| `src/hooks/useBenchmarkData.test.js` | load-once lifecycle, error capture, terminate-on-PROD |
| `src/components/TrendChart.test.jsx` | sr-only a11y table: date-union columns, `—` for missing runs and null values |

---

## Appendix: cloud setup & deploy

**First-time creation of a named DB** — *already done for `leaderboard-test`;
kept here for reference and any future DB.* Use **Standard** edition; a DB's
location is permanent, so match the prod DB's region:

```bash
gcloud firestore databases create \
  --database=leaderboard-test --edition=standard \
  --location="$(gcloud firestore databases describe --database=leaderboard \
      --project=devops-bench-shared --format='value(locationId)')" \
  --project=devops-bench-shared

# Must print REALTIME_UPDATES_MODE_ENABLED:
gcloud firestore databases describe --database=leaderboard-test \
  --project=devops-bench-shared --format='value(realtimeUpdatesMode)'
```

> **Why Standard edition matters.** On Standard/Native, the native Firestore API
> and realtime updates are always on. **Enterprise** edition can have realtime
> *off* (e.g. a MongoDB-compatibility config) — and the Web SDK then hangs even on
> one-shot reads, because it tunnels reads over the realtime Listen channel and
> retries a never-ready channel forever instead of erroring. Keep all DBs on
> Standard.

**Deploy** (rules apply to both DBs via the `firebase.json` array; hosting serves
`dist/`):

```bash
npm run build
npx -y firebase-tools deploy --only firestore:rules,hosting --project devops-bench-shared
```
