// =============================================================================
// devops-bench leaderboard — SHARED DATA MODULE (DOM-free).
//
// The data model + derived accessors that BOTH pages render from:
//   - index.html  / app.js     (the leaderboard)
//   - detail.html / detail.js  (a single setup's detail page)
// Load this file BEFORE the page script so `setups`, the accessors, and the
// logo helpers are available.
//
// FILE MAP (top -> bottom):
//   1. DATA MODEL ......... the structures the whole UI is built on (READ FIRST)
//   2. MOCK DATA .......... generates a fake `setups` so the page renders today
//   3. DERIVED ACCESSORS .. pure functions the render layer calls (score/label/…)
//   4. SHARED RENDER HELPERS  model/harness logos + icons reused by both pages
//
// [MOCK] markers flag anything fabricated that MUST be replaced when real eval
// data is wired in. (For the real loader pattern, see the old site/app.js
// loadData(), which fetches eval_results/eval-results-N.jsonl.)
// =============================================================================

// --- 1. DATA MODEL -----------------------------------------------------------
//
// `setups` is THE load-bearing structure: a flat array where each element is
// ONE leaderboard row. Every render function reads from this shape, so keeping
// it stable is what lets real data drop in without touching the rendering code.
//
// Shape of a single setup:
//   {
//     id:           "alpha-pro-gemini-cli-gca-mcp", // stable, slugified DOM id
//     model:        "alpha-pro",              // key into `models`     (1st-class axis)
//     harness:      "gemini-cli",             // key into `harnesses`  (1st-class axis)
//     mcp:          true | false,             // BENCH_USE_MCP         (modifier)
//     augmentation: "baseline" | "gca",       // GCA + skills + rules  (modifier)
//     color:        "#3b82f6",                // line/bar color for this row
//     tasks: [                                // one entry per benchmark task
//       {
//         folder: "create-deployment",        // real tasks/<folder>
//         name:   "Deploy vLLM Server: …",    // display name
//         scores: { pass1: 96, pass5: 98, passMax: 100 }  // accuracy % per metric
//       }, …
//     ]
//   }
//
// A "setup" is the benchmark ENTITY = a (model × harness) PAIRING run in a
// specific config. Model and harness are the two CO-EQUAL first-class axes:
// we are benchmarking the combined capability of an LLM and the agent runner
// driving it (BENCH_AGENT_TYPE + AGENT_TARGET — e.g. Gemini CLI vs OpenClaw
// vs the internal API loop). `augmentation` (GCA + skills + rules) and `mcp`
// are SECONDARY modifiers layered on top of a pairing. Because every field is
// an independent tag, any one can become the row axis, a filter, or a group-by
// without restructuring the data.
//
// The headline number per row is DERIVED from `tasks` (see setupScore) — it is
// intentionally NOT stored, to avoid a second source of truth that can drift.
//
// NOTE: latency / token-count stats are intentionally NOT surfaced yet — the
// harness capture for those is still inconsistent (harness-dependent token shapes,
// last-turn-only token usage vs cumulative latency, missing-data cases). Add
// them once that's normalized.

// Dimension vocabularies (display labels for the harness values).
const HARNESS_TYPES = { cli: "CLI", api: "API" };                    // BENCH_AGENT_TYPE family
const AUGMENTATIONS = { baseline: "Baseline", gca: "GCA + Skills" };  // secondary modifier layer
// mcp is a boolean (BENCH_USE_MCP) — also a secondary modifier.

// `models` — stable metadata per base LLM, keyed by model id and referenced
// from each setup via `setup.model` (one model fans out to several setups).
// [MOCK] fictional placeholders; replace with real AGENT_MODEL / AGENT_PROVIDER.
const models = {
    "alpha-pro":   { name: "Alpha Pro",   provider: "Acme",    license: "Proprietary", logo: "alpha" },
    "beta-sonic":  { name: "Beta Sonic",  provider: "Globex",  license: "Proprietary", logo: "beta" },
    "gamma-coder": { name: "Gamma Coder", provider: "Initech", license: "Open Source", logo: "gamma" }
};

// `harnesses` — the agent RUNNER under test, a first-class axis CO-EQUAL with
// `models`. Maps to BENCH_AGENT_TYPE + AGENT_TARGET in pkg/evaluator: `cli`
// dispatches on the AGENT_TARGET binary (gemini / openclaw), `api` is the
// internal Python tool-calling loop. `type` is the cli/api family; `accent`
// tints the harness chip so it reads as its own entity class (distinct from the
// model brand). `logo` keys into harnessIcon().
// [MOCK] names/accents are illustrative; wire real AGENT_TARGET values later.
const harnesses = {
    "gemini-cli": { name: "Gemini CLI", type: "cli", accent: "#0ea5e9", logo: "terminal" },
    "openclaw":   { name: "OpenClaw",   type: "cli", accent: "#f43f5e", logo: "claw" },
    "api-loop":   { name: "API Runner", type: "api", accent: "#8b5cf6", logo: "braces" }
};

// `TASK_CATALOG` — the benchmark tasks, shared by every setup (index-aligned
// with the BASE_PROFILE arrays below). `folder` values are REAL (they match the
// tasks/<folder> dirs); `name` is a display label.
const TASK_CATALOG = [
    { folder: "get-app-architecture",          name: "Summarize Application Architecture" },
    { folder: "create-deployment",             name: "Deploy vLLM Server: Gemma 3, GPU, GCS Fuse" },
    { folder: "deploy-config",                 name: "Deploy Kubernetes Configuration Manifests" },
    { folder: "modify-deployment",             name: "Update App Config: Gemini to Local vLLM" },
    { folder: "fix-config",                    name: "Fix & Apply Frontend Deployment Manifest" },
    { folder: "deploy-hello-app",              name: "Productionize & Deploy Hello World App" },
    { folder: "computeclass-spot-fallback",    name: "ComputeClass Spot VMs with N2 Fallback" },
    { folder: "computeclass-active-migration", name: "ComputeClass Active Workload Migration" },
    { folder: "gateway-cloud-armor",           name: "Gateway Cloud Armor Security Policy" },
    { folder: "gateway-https-redirect",        name: "Gateway HTTP-to-HTTPS redirect" },
    { folder: "hpa-metric-filtering",          name: "Prometheus AutoscalingMetric Filter" },
    { folder: "hpa-renamed-metric",            name: "HPA Custom Export-Name Metric Mapping" }
];

// --- 2. MOCK DATA ------------------------------------------------------------
//
// [MOCK] Everything in this section is fabricated so the page renders before
// real results exist. To wire real data: DELETE BASE_PROFILE, SETUP_DEFS, and
// the `setups` generator, then build `setups` (shape documented in section 1)
// from eval_results/*.jsonl instead — aggregating Outcome Validity across the
// per-task `Run #`s to get real pass@1 / pass@5 / pass@max.

// [MOCK] Baseline per-task accuracy per model (index aligns with TASK_CATALOG).
const BASE_PROFILE = {
    "alpha-pro":   [92, 93, 94, 95, 94, 93, 90, 89, 86, 88, 88, 87],
    "beta-sonic":  [90, 91, 92, 93, 92, 91, 85, 84, 80, 82, 83, 81],
    "gamma-coder": [84, 86, 88, 89, 88, 87, 70, 69, 65, 68, 69, 67]
};

// [MOCK] Curated (model × harness) pairings. Not a full cross product
// (model x harness x augmentation x mcp); a representative subset that pairs
// several models with different agent runners and shows each as a baseline-vs-
// GCA pair, so the model AND harness axes are both exercised.
const SETUP_DEFS = [
    { model: "alpha-pro",   harness: "gemini-cli", mcp: false, augmentation: "baseline" },
    { model: "alpha-pro",   harness: "gemini-cli", mcp: true,  augmentation: "gca" },
    { model: "alpha-pro",   harness: "api-loop",   mcp: false, augmentation: "baseline" },
    { model: "alpha-pro",   harness: "api-loop",   mcp: true,  augmentation: "gca" },
    { model: "beta-sonic",  harness: "openclaw",   mcp: false, augmentation: "baseline" },
    { model: "beta-sonic",  harness: "openclaw",   mcp: true,  augmentation: "gca" },
    { model: "gamma-coder", harness: "gemini-cli", mcp: false, augmentation: "baseline" },
    { model: "gamma-coder", harness: "api-loop",   mcp: true,  augmentation: "gca" }
];

// One distinct line/bar color per setup (model brand color drives the logo only).
const PALETTE = ["#3b82f6", "#1d4ed8", "#10b981", "#059669", "#f59e0b", "#d97706", "#8b5cf6", "#ec4899"];

function clampPct(v) {
    return Math.max(0, Math.min(100, v));
}

// [MOCK] Pool of past eval-run timestamps (ISO 8601). Real data: one entry per
// results/run_<timestamp>/ directory that exists for a setup's config. Stored as
// timestamps (not "Iteration N") so the trend chart is a TRUE time-series — the
// x-position is proportional to elapsed time, not evenly-spaced categories.
const MOCK_RUN_DATES = [
    "2026-01-15T00:00:00Z",
    "2026-02-15T00:00:00Z",
    "2026-03-15T00:00:00Z",
    "2026-04-15T00:00:00Z",
    "2026-05-15T00:00:00Z",
    "2026-06-01T00:00:00Z"
];

// [MOCK] Expands the compact source above into the real `setups` shape that the
// render layer consumes (section 1). The accuracy numbers here are SYNTHESIZED:
// a baseline profile plus deltas for augmentation/harness, and pass5/passMax as
// fixed offsets above pass1. Real data replaces this whole block.
const setups = SETUP_DEFS.map((def, i) => {
    const base = BASE_PROFILE[def.model];
    const augDelta = def.augmentation === "gca" ? 5 : 0;            // [MOCK] GCA + skills + rules lift
    const harnessDelta = harnesses[def.harness].type === "cli" ? 1 : 0;  // [MOCK] runner lift
    const delta = augDelta + harnessDelta;

    const tasks = TASK_CATALOG.map((task, t) => {
        const pass1 = clampPct(base[t] + delta);
        return {
            folder: task.folder,
            name: task.name,
            // best-of-N ordering: pass@1 <= pass@5 <= pass@max
            scores: { pass1: pass1, pass5: clampPct(pass1 + 2), passMax: clampPct(pass1 + 4) }
        };
    });

    // [MOCK] SPARSE per-setup run history (Option B). Each setup STARTS at a
    // different run (staggered by index) so the series are ragged — some lines
    // begin later than others, exercising the missing-data case WITHOUT any
    // zero-padding: a setup simply has no points before its first run. The last
    // point equals the current aggregate; earlier points ramp up to it.
    const aggregate = m => clampPct(tasks.reduce((s, t) => s + t.scores[m], 0) / tasks.length);
    const runDates = MOCK_RUN_DATES.slice(i % 4);  // [MOCK] staggered start date
    const history = runDates.map((t, idx, arr) => {
        const frac = arr.length > 1 ? idx / (arr.length - 1) : 1;   // 0 → 1 over present runs
        const ramp = m => Math.round((aggregate(m) - (1 - frac) * 8) * 10) / 10;
        return { t: t, scores: { pass1: ramp("pass1"), pass5: ramp("pass5"), passMax: ramp("passMax") } };
    });

    return {
        id: `${def.model}-${def.harness}-${def.augmentation}${def.mcp ? "-mcp" : ""}`.replace(/[^a-z0-9-]/gi, ""),
        model: def.model,
        harness: def.harness,
        mcp: def.mcp,
        augmentation: def.augmentation,
        color: PALETTE[i % PALETTE.length],
        tasks: tasks,
        // history: [ { t: <ISO run timestamp>, scores: { pass1, pass5, passMax } }, … ]
        history: history
    };
});

// --- 3. DERIVED ACCESSORS ----------------------------------------------------
//
// Pure read-only functions over a `setup`. The render layer (app.js / detail.js)
// only ever reaches the data THROUGH these, so real data only has to match the
// `setups` shape — not the rendering code.

// Full label distinguishing a setup. Leads with the first-class pairing
// (model × harness), then the secondary modifiers. Used by the chart legend.
function setupLabel(setup) {
    const parts = [`${models[setup.model].name} × ${harnesses[setup.harness].name}`];
    parts.push(AUGMENTATIONS[setup.augmentation]);
    if (setup.mcp) parts.push("MCP");
    return parts.join(" · ");
}

// Secondary modifier chips (augmentation + mcp). The harness type chip is built
// separately at the call site because it needs the per-harness accent color.
function setupTags(setup) {
    const tags = [
        {
            text: AUGMENTATIONS[setup.augmentation],
            cls: setup.augmentation === "gca"
                ? "bg-indigo-50 text-indigo-700 ring-1 ring-indigo-100"
                : "bg-slate-100 text-slate-500"
        }
    ];
    if (setup.mcp) tags.push({ text: "MCP", cls: "bg-emerald-50 text-emerald-700 ring-1 ring-emerald-100" });
    return tags;
}

// Aggregated headline score for a setup under the selected metric.
// Placeholder rule = mean over tasks; swap in the real aggregation here later.
// Null-safe: ignores tasks with no score (e.g. a task that didn't run in this
// config) so missing data never drags the mean toward 0. Returns null if the
// setup has no scored tasks at all.
function setupScore(setup, metric) {
    const vals = setup.tasks.map(t => t.scores[metric]).filter(v => v != null);
    return vals.length ? vals.reduce((sum, v) => sum + v, 0) / vals.length : null;
}

// Trend points for the metric as { x: <epoch ms>, y: <score> }, in time order.
// SPARSE by construction: a setup only yields points for runs it actually has,
// so its line starts at its first run — no zero-padding, no fake leading points.
// x is the parsed timestamp (a number) → the chart can use a real time/linear
// axis where spacing is proportional to elapsed time. The axis LABEL is derived
// from that same value (formatRunDate), so there's no separate string→number map.
function setupHistory(setup, metric) {
    return setup.history.map(h => ({ x: Date.parse(h.t), y: h.scores[metric] }));
}

// Sorted union of run timestamps (ISO) across the given setups. Used to build a
// stable shared axis for the trend chart's accessibility table; a setup missing
// a given run simply has a blank cell there (never a 0).
function allRunDates(setupsList) {
    const set = new Set();
    setupsList.forEach(s => s.history.forEach(h => set.add(h.t)));
    return [...set].sort();
}

// Format a run timestamp (ISO string or epoch ms) as yyyy-mm-dd for axis ticks
// / table headers. Pinned to UTC so a midnight-UTC timestamp doesn't render as
// the previous day in negative-offset local timezones. en-CA yields ISO order.
function formatRunDate(t) {
    return new Date(t).toLocaleDateString("en-CA", { timeZone: "UTC", year: "numeric", month: "2-digit", day: "2-digit" });
}

// --- 4. SHARED RENDER HELPERS ------------------------------------------------
// Logos/icons reused by both the leaderboard rows and the detail hero.

const brandLogos = {
    alpha: `<svg aria-hidden="true" focusable="false" class="w-4 h-4 min-w-[16px]" viewBox="0 0 24 24" fill="none"><rect x="2" y="2" width="20" height="20" rx="6" fill="#6366f1"/><text x="12" y="16" fill="white" font-size="12" font-family="system-ui, sans-serif" font-weight="bold" text-anchor="middle">A</text></svg>`,
    beta: `<svg aria-hidden="true" focusable="false" class="w-4 h-4 min-w-[16px]" viewBox="0 0 24 24" fill="none"><rect x="2" y="2" width="20" height="20" rx="6" fill="#0ea5e9"/><text x="12" y="16" fill="white" font-size="12" font-family="system-ui, sans-serif" font-weight="bold" text-anchor="middle">B</text></svg>`,
    gamma: `<svg aria-hidden="true" focusable="false" class="w-4 h-4 min-w-[16px]" viewBox="0 0 24 24" fill="none"><rect x="2" y="2" width="20" height="20" rx="6" fill="#f97316"/><text x="12" y="16" fill="white" font-size="12" font-family="system-ui, sans-serif" font-weight="bold" text-anchor="middle">C</text></svg>`
};

// Harness glyphs — line icons tinted with the harness accent so the runner
// reads as its own entity class (vs the filled-square model logos).
function harnessIcon(harness) {
    const c = harness.accent;
    const glyph = {
        terminal: `<path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M7 8l3 3-3 3m5 1h4"/>`,
        claw:     `<path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M4 7l8-4 8 4-8 4-8-4z"/><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M4 12l8 4 8-4M4 17l8 4 8-4"/>`,
        braces:   `<path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M8 5c-2 0-2 2-2 3.5S6 12 4 12c2 0 2 2.5 2 4s0 3 2 3m8-14c2 0 2 2 2 3.5S18 12 20 12c-2 0-2 2.5-2 4s0 3-2 3"/>`
    }[harness.logo] || '';
    return `<svg aria-hidden="true" focusable="false" class="w-4 h-4 min-w-[16px]" fill="none" stroke="${c}" viewBox="0 0 24 24">${glyph}</svg>`;
}
