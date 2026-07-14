// =============================================================================
// devops-bench leaderboard — MOCK DATA MODULE (seed-only, Node ESM).
//
// This is the single home of the fabricated benchmark data, ported from the old
// `data.js` section 1+2. It exists so the seed script can populate Firestore with
// the SAME data the dashboard used to generate in-browser.
//
// Crucially, the mock now flows the way real data will:
//
//     generateRaw()  ->  raw per-iteration `results` rows  (SOURCE OF TRUTH)
//     derive(raw)    ->  `setups[]` read-model the dashboard renders
//
// So `pass1/pass5/passMax` are NOT stored as fabricated constants — they are
// COMPUTED from raw `outcomeScore`s under a single, swappable formula. Change
// the formula (PASS_THRESHOLD / pass@k estimator) and re-run derive(); the raw
// data never has to be regenerated. When real eval results land, only the
// producer (generateRaw) is replaced — `derive()` is reused verbatim.
// =============================================================================

// Shapes shared with the dashboard read side — see src/lib/schema.d.ts. These
// are JSDoc-only annotations (documentation, not runtime checks).
/**
 * @typedef {import('../src/lib/schema').ResultRow} ResultRow
 * @typedef {import('../src/lib/schema').Setup} Setup
 * @typedef {import('../src/lib/schema').ModelMap} ModelMap
 * @typedef {import('../src/lib/schema').HarnessMap} HarnessMap
 */

// --- 1. DIMENSION VOCABULARIES & METADATA ------------------------------------

// `models` — stable metadata per base LLM, keyed by model id. Seeded into the
// `models` collection; the dashboard reads it back to label rows.
/** @type {ModelMap} */
export const models = {
    "alpha-pro":   { name: "Alpha Pro",   provider: "Acme",    license: "Proprietary", logo: "alpha" },
    "beta-sonic":  { name: "Beta Sonic",  provider: "Globex",  license: "Proprietary", logo: "beta" },
    "gamma-coder": { name: "Gamma Coder", provider: "Initech", license: "Open Source", logo: "gamma" }
};

// `harnesses` — the agent runner under test, a first-class axis co-equal with
// `models`. Seeded into the `harnesses` collection.
/** @type {HarnessMap} */
export const harnesses = {
    "gemini-cli": { name: "Gemini CLI", type: "cli", accent: "#0ea5e9", logo: "terminal" },
    "openclaw":   { name: "OpenClaw",   type: "cli", accent: "#f43f5e", logo: "claw" },
    "api-loop":   { name: "API Runner", type: "api", accent: "#8b5cf6", logo: "braces" }
};

// `TASK_CATALOG` — the benchmark tasks (folder values match real tasks/<folder>).
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

// Baseline per-task accuracy per model (index aligns with TASK_CATALOG), as a
// percentage. Used as the underlying "true" pass probability the raw sampler
// draws against — so derived pass rates land near these numbers.
const BASE_PROFILE = {
    "alpha-pro":   [92, 93, 94, 95, 94, 93, 90, 89, 86, 88, 88, 87],
    "beta-sonic":  [90, 91, 92, 93, 92, 91, 85, 84, 80, 82, 83, 81],
    "gamma-coder": [84, 86, 88, 89, 88, 87, 70, 69, 65, 68, 69, 67]
};

// Curated (model × harness) pairings — a representative subset, each shown as a
// baseline-vs-augmented pair so both the model and harness axes are exercised.
// `augmentation` is the set of capability tokens stacked on the base pairing
// (empty array = baseline).
const SETUP_DEFS = [
    { model: "alpha-pro",   harness: "gemini-cli", augmentation: [] },
    { model: "alpha-pro",   harness: "gemini-cli", augmentation: ["mcp", "skills"] },
    { model: "alpha-pro",   harness: "api-loop",   augmentation: [] },
    { model: "alpha-pro",   harness: "api-loop",   augmentation: ["mcp", "skills"] },
    { model: "beta-sonic",  harness: "openclaw",   augmentation: [] },
    { model: "beta-sonic",  harness: "openclaw",   augmentation: ["mcp", "skills"] },
    { model: "gamma-coder", harness: "gemini-cli", augmentation: [] },
    { model: "gamma-coder", harness: "api-loop",   augmentation: ["mcp", "skills"] }
];

// One distinct line/bar color per setup.
const PALETTE = ["#3b82f6", "#1d4ed8", "#10b981", "#059669", "#f59e0b", "#d97706", "#8b5cf6", "#ec4899"];

// Pool of past eval-run timestamps (ISO 8601). One entry per run; setups start
// at staggered runs so the trend lines are ragged (missing-data case).
const MOCK_RUN_DATES = [
    "2026-01-15T00:00:00Z",
    "2026-02-15T00:00:00Z",
    "2026-03-15T00:00:00Z",
    "2026-04-15T00:00:00Z",
    "2026-05-15T00:00:00Z",
    "2026-06-01T00:00:00Z"
];

// How many sampled iterations per (setup × task × run). This is the "Run #"
// repeat count that makes pass@k meaningful; higher N → finer-grained pass rates.
const ITERATIONS = 20;

// --- 2. RAW GENERATION -------------------------------------------------------

// Deterministic PRNG (mulberry32) so re-seeding yields identical data — avoids a
// noisy diff in the emulator and makes the derive() spot-check reproducible.
function makeRng(seed) {
    let a = seed >>> 0;
    return function () {
        a |= 0; a = (a + 0x6d2b79f5) | 0;
        let t = Math.imul(a ^ (a >>> 15), 1 | a);
        t = (t + Math.imul(t ^ (t >>> 7), 61 | t)) ^ t;
        return ((t ^ (t >>> 14)) >>> 0) / 4294967296;
    };
}

function setupId(def) {
    // Sort augmentation tokens so the id is stable regardless of input order.
    // Empty augmentation → "<model>-<harness>" (no trailing dash).
    const augPart = def.augmentation.length
        ? `-${def.augmentation.slice().sort().join("-")}`
        : "";
    // Same slug algorithm as ingest/catalog.mjs and the Python producer
    // (results/normalize.slugify): lower-case, collapse non-alphanumeric runs to
    // a single dash, trim — so a mock and a real id for the same arm coincide.
    return `${def.model}-${def.harness}${augPart}`
        .toLowerCase()
        .replace(/[^a-z0-9]+/g, "-")
        .replace(/^-+|-+$/g, "");
}

function runId(t) {
    // run_YYYYMMDD_HHMMSS, matching the producer's results/run_<timestamp>/ shape.
    return "run_" + t.replace(/[-:TZ]/g, "").slice(0, 15).replace(/(\d{8})(\d{6}).*/, "$1_$2");
}

// Produce the raw `results` rows: one per (setup × task × run × iteration). Each
// row carries the CONTINUOUS outcomeScore (0..1) — never a precomputed pass flag
// — so any future threshold/formula stays computable.
/** @returns {ResultRow[]} */
export function generateRaw() {
    const rng = makeRng(0xC0FFEE);
    const rows = [];

    SETUP_DEFS.forEach((def, i) => {
        const id = setupId(def);
        const base = BASE_PROFILE[def.model];
        const augDelta = def.augmentation.includes("skills") ? 5 : 0;       // skills lift
        const harnessDelta = harnesses[def.harness].type === "cli" ? 1 : 0;  // runner lift
        const delta = augDelta + harnessDelta;

        // Staggered start: this setup only has the later slice of run dates, so
        // its trend line begins after others (ragged series, no zero-padding).
        const runDates = MOCK_RUN_DATES.slice(i % 4);

        runDates.forEach((t, idx, arr) => {
            // Improvement over time: earlier runs sit up to 8 points lower.
            const frac = arr.length > 1 ? idx / (arr.length - 1) : 1;   // 0 → 1
            const timePenalty = (1 - frac) * 8;

            TASK_CATALOG.forEach((task, ti) => {
                // Target per-task pass probability for THIS run (0..1).
                const pct = clampPct(base[ti] + delta - timePenalty);
                const p = pct / 100;

                for (let iter = 1; iter <= ITERATIONS; iter++) {
                    // With prob p the iteration "passes": score in [T,1]; else it
                    // "fails": score in [0,T). The continuous score still varies
                    // within each band so a threshold change is meaningful.
                    const passing = rng() < p;
                    const outcomeScore = passing
                        ? PASS_THRESHOLD + rng() * (1 - PASS_THRESHOLD)
                        : rng() * PASS_THRESHOLD;

                    rows.push({
                        setupId: id,
                        model: def.model,
                        harness: def.harness,
                        augmentation: def.augmentation,
                        runId: runId(t),
                        t: t,
                        taskFolder: task.folder,
                        taskName: task.name,
                        iteration: iter,
                        status: "success",
                        outcomeScore: round(outcomeScore, 4),
                        toolScore: round(Math.min(1, outcomeScore + rng() * 0.1), 4),
                        latencySec: round(20 + rng() * 60, 2),
                        inputTokens: Math.round(8000 + rng() * 30000),
                        outputTokens: Math.round(300 + rng() * 1500),
                        // Mock rows are all vetted so the seeded demo renders;
                        // real rows carry per-task validated from the harness.
                        validated: true
                    });
                }
            });
        });
    });

    return rows;
}

// --- 3. DERIVATION (raw -> read-model) ---------------------------------------
//
// THE one place the scoring formula lives. The dashboard's pass1/pass5/passMax
// are produced here and nowhere else.

// A single iteration "passes" when its judge score clears this bar. Changing it
// (or the pass@k estimator below) and re-running derive() re-scores everything
// from the same raw data.
export const PASS_THRESHOLD = 0.7;
const K = 5; // the k in pass@5

// Unbiased pass@k estimator: probability that at least one of k samples passes,
// given c passes out of n iterations. Returns a fraction in [0,1].
// Exported for direct unit testing.
export function passAtK(n, c, k) {
    if (n === 0) return 0;
    if (c === 0) return 0;
    if (n - c < k) return 1; // fewer than k failures → some k-subset must contain a pass
    // 1 - C(n-c, k) / C(n, k), computed as a running product to avoid overflow.
    let prod = 1;
    for (let i = 0; i < k; i++) prod *= (n - c - i) / (n - i);
    return 1 - prod;
}

// Compute {pass1, pass5, passMax} (as percentages) for a list of iteration rows
// that all belong to the same (setup, task, run). pass5/passMax stay null until
// the harness produces multi-iteration runs — passAtK() and K are kept
// (re-enable here when that lands; nothing about the formula needs to change).
function scoresFor(rows) {
    const n = rows.length;
    const c = rows.filter(r => r.outcomeScore != null && r.outcomeScore >= PASS_THRESHOLD).length;
    return {
        pass1: round((c / n) * 100, 1),
        pass5: null,
        passMax: null
    };
}

// Mean over a list of score objects, per metric. Skips nulls so a metric with
// no scored entries comes back as null instead of NaN.
function meanScores(scoreList) {
    const avg = m => {
        const vals = scoreList.map(x => x[m]).filter(v => v != null);
        return vals.length ? round(vals.reduce((s, v) => s + v, 0) / vals.length, 1) : null;
    };
    return { pass1: avg("pass1"), pass5: avg("pass5"), passMax: avg("passMax") };
}

// Build the dashboard read-model from raw rows: one `setups` doc per setup, with
// `tasks[]` = per-task scores at the LATEST run, and `history[]` = the setup-wide
// aggregate (mean across tasks) at each run, time-ordered.
/**
 * @param {ResultRow[]} rows
 * @returns {Setup[]}
 */
export function derive(rows) {
    // Leaderboard gate: only tasks vetted as correct (validated) promote. A row
    // without an explicit validated:true is excluded so an unvetted/buggy task
    // never counts toward a setup's score.
    rows = rows.filter(r => r.validated === true);
    // Group rows by setupId.
    const bySetup = new Map();
    for (const r of rows) {
        if (!bySetup.has(r.setupId)) bySetup.set(r.setupId, []);
        bySetup.get(r.setupId).push(r);
    }

    return SETUP_DEFS.map((def, i) => {
        const id = setupId(def);
        const setupRows = bySetup.get(id) || [];

        // Sorted unique run timestamps for this setup.
        const runTimes = [...new Set(setupRows.map(r => r.t))].sort();
        const latest = runTimes[runTimes.length - 1];

        // Per-task scores at the latest run (what the detail table shows).
        const tasks = TASK_CATALOG
            .filter(task => setupRows.some(r => r.t === latest && r.taskFolder === task.folder))
            .map(task => ({
                folder: task.folder,
                name: task.name,
                scores: scoresFor(setupRows.filter(r => r.t === latest && r.taskFolder === task.folder))
            }));

        // History: one aggregate point per run (mean of that run's per-task scores).
        const history = runTimes.map(t => {
            const perTask = TASK_CATALOG
                .filter(task => setupRows.some(r => r.t === t && r.taskFolder === task.folder))
                .map(task => scoresFor(setupRows.filter(r => r.t === t && r.taskFolder === task.folder)));
            return { t, scores: meanScores(perTask) };
        });

        return {
            id,
            order: i,
            model: def.model,
            harness: def.harness,
            augmentation: def.augmentation.slice(),
            color: PALETTE[i % PALETTE.length],
            tasks,
            history
        };
    });
}

// --- helpers -----------------------------------------------------------------

function clampPct(v) {
    return Math.max(0, Math.min(100, v));
}

function round(v, dp) {
    const f = 10 ** dp;
    return Math.round(v * f) / f;
}
