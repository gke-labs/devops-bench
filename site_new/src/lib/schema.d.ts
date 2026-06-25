// =============================================================================
// Shared shape of the devops-bench leaderboard data — the canonical description
// of what lives in Firestore, in two layers:
//
//   - the RAW `results` row    : source of truth, one per iteration (written by
//                                the seeder / real ingest)
//   - the DERIVED read-model   : `models` / `harnesses` / `setups`, the only
//                                thing the dashboard reads
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

/** The scoring metrics, in display order. */
export type MetricKey = "pass1" | "pass5" | "passMax";

/**
 * Per-metric scores as percentages (0..100). `null` where a metric has no
 * scored data for the task/run — complete in mock data, potentially sparse once
 * real ingest data lands (the UI must treat these as nullable).
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
    mcp: boolean;
    augmentation: "baseline" | "gca";
    /** Hex line/bar color, e.g. "#3b82f6". */
    color: string;
    tasks: Task[];
    history: HistoryPoint[];
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

// --- raw source-of-truth row (`results` collection) --------------------------
//
// One row per (setup × task × run × iteration). Carries the CONTINUOUS
// `outcomeScore` (never a precomputed pass flag) so any future pass threshold /
// pass@k formula stays computable; `derive()` turns these rows into the Setup
// read-model above.

export interface ResultRow {
    setupId: string;
    model: string;
    harness: string;
    mcp: boolean;
    augmentation: "baseline" | "gca";
    /** run_YYYYMMDD_HHMMSS — matches results/run_<timestamp>/ on the producer. */
    runId: string;
    /** Run timestamp, ISO 8601. */
    t: string;
    taskFolder: string;
    taskName: string;
    iteration: number;
    /** Judge score in [0,1]; an iteration passes when `>= PASS_THRESHOLD`. */
    outcomeScore: number;
    toolScore: number;
    latencySec: number;
    inputTokens: number;
    outputTokens: number;
}
