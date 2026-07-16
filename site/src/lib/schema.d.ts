// =============================================================================
// Shared shape of the devops-bench leaderboard data — the canonical description
// of what lives in Firestore, in two layers:
//
//   - the RAW `rows.json` row : source of truth, one per iteration (written by
//                               the Python eval harness)
//   - the DERIVED read-model  : `models` / `harnesses` / `setups`, the only
//                               thing the dashboard reads
//
// These interfaces are DOCUMENTATION, not runtime validation. Firestore is
// schemaless and `doc.data()` is untyped, so a type here describes the INTENDED
// shape — it does not enforce it, and it cannot express referential integrity
// (e.g. that `Setup.model` is a live key of ModelMap). A malformed or dangling
// doc will still type-check and can still crash at runtime.
//
// Wiring: referenced from the `.js`/`.mjs` sources via JSDoc, e.g.
//   /** @typedef {import('./schema').Setup} Setup */
// Nothing compiles this file (Vite/Vitest ignore `.d.ts`), so the build is
// unchanged. To have the editor hold call sites to these shapes, add a
// `// @ts-check` line at the top of a source file (opt-in, per file).
// =============================================================================

// --- metrics -----------------------------------------------------------------

/**
 * The scoring metrics, in display order. `composite` is the scoring-framework v1
 * headline (cat_v · √(c · rec_v)); `correctness` / `recoverableSafety` are its
 * sub-scores. All are 0..100 means. `pass1/5/Max` are pass rates.
 */
export type MetricKey =
    | "composite"
    | "correctness"
    | "recoverableSafety"
    | "pass1"
    | "pass5"
    | "passMax";

/**
 * Per-metric scores as percentages (0..100). `null` where a metric has no
 * scored data for the task/run. `pass5` and `passMax` are null today — they
 * stay null until the harness produces multi-iteration runs (then `derive()`
 * recomputes them from the same raw rows).
 */
export type Scores = Record<MetricKey, number | null>;

// --- derived read-model (what the dashboard reads) ---------------------------

export interface Model {
    name: string;
    provider: string;
    license: string;
    /** Brand key into the BrandLogo glyph table (e.g. "alpha"). */
    logo: string;
}

export interface Harness {
    name: string;
    type: "cli" | "api";
    /** Hex accent color, e.g. "#0ea5e9". */
    accent: string;
    /** Glyph key into the HarnessIcon table (e.g. "terminal"). */
    logo: string;
}

/** Per-task scores at the latest run — the detail-page table rows. */
export interface Task {
    folder: string;
    name: string;
    scores: Scores;
    /** True when a catastrophic tripwire fired for this task (cat_v = 0). */
    catastrophic?: boolean;
}

/** One aggregate point per run (mean across tasks), time-ordered. */
export interface HistoryPoint {
    /** Run timestamp, ISO 8601 (e.g. "2026-06-01T00:00:00Z"). */
    t: string;
    scores: Scores;
}

export interface Setup {
    id: string;
    /** Stable display order (the `setups` query sorts on this). */
    order: number;
    /** Key into ModelMap. NOT enforced — a dangling id is possible. */
    model: string;
    /** Key into HarnessMap. NOT enforced — a dangling id is possible. */
    harness: string;
    /**
     * Capability tokens stacked on top of the base (model × harness) pairing,
     * e.g. `["mcp", "skills"]`. Empty array means baseline. Order is not
     * significant; the UI renders one badge per token.
     */
    augmentation: string[];
    /** Hex line/bar color, e.g. "#3b82f6". */
    color: string;
    tasks: Task[];
    history: HistoryPoint[];
    /** Count of latest-run tasks with a catastrophic violation (cat_v = 0). */
    catastrophicCount: number;
}

/** The two metadata collections, keyed by doc id, as the dashboard holds them. */
export type ModelMap = Record<string, Model>;
export type HarnessMap = Record<string, Harness>;

/** Full payload returned by loadBenchmarkData(). */
export interface BenchmarkData {
    models: ModelMap;
    harnesses: HarnessMap;
    setups: Setup[];
}

// --- raw source-of-truth row (`rows.json`) -----------------------------------
//
// One row per (setup × task × run × iteration), emitted by the Python eval
// harness into `rows.json`. Iteration is always 0 today (pass1-only); the
// schema is already shaped for multi-iteration runs so pass@k stays
// computable when the harness starts sampling. `derive()` turns these rows
// into the Setup read-model above.

export interface ResultRow {
    setupId: string;
    model: string;
    harness: string;
    /** Capability tokens active for this row, mirroring `Setup.augmentation`. */
    augmentation: string[];
    /** run_YYYYMMDD_HHMMSS — matches results/run_<timestamp>/ on the producer. */
    runId: string;
    /** Run timestamp, ISO 8601. */
    t: string;
    taskFolder: string;
    taskName: string;
    iteration: number;
    /** Terminal outcome of the run (the harness flags crashes/timeouts). */
    status: "success" | "failed";
    /**
     * Composite outcome score in [0,1] — scoring-framework v1 (cat_v · √(c · rec_v)).
     * Null when unscored. (Was the OutcomeValidity judge score before v1.)
     */
    outcomeScore: number | null;
    /** Correctness sub-score `c` in [0,1] (checklist / OutcomeValidity fallback); null when unscored. */
    correctnessScore?: number | null;
    /** Recoverable-safety sub-score `rec_v` in [0.1,1.0]; null when the task defined no safety checks. */
    recoverableSafetyScore?: number | null;
    /** True when a catastrophic tripwire fired (cat_v = 0), zeroing the outcome. */
    catastrophic?: boolean;
    /** Scoring-framework version that produced `outcomeScore` (e.g. "v1"). */
    scoringVersion?: string;
    /** Tool-use score in [0,1]; null when unscored. */
    toolScore: number | null;
    latencySec: number;
    /** Null when token usage was not captured. */
    inputTokens: number | null;
    /** Null when token usage was not captured. */
    outputTokens: number | null;
    /** Whether the task is vetted as correct; only validated tasks promote to the leaderboard. */
    validated: boolean;
}
