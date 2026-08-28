// Display vocabularies — UI constants, not data.

export const HARNESS_TYPES = { cli: "CLI", api: "API" };                    // BENCH_AGENT_TYPE family

// Display label per augmentation token (Setup.augmentation is `string[]`).
// `baseline` is the synthetic label shown when the array is empty. Unknown
// tokens fall back to title case at the consumer (see titleCaseToken).
export const AUGMENTATIONS = {
    baseline: "Baseline",
    skills: "Skills",
    mcp: "MCP"
};

// Title-case an unknown augmentation token so a forward-compatible new value
// renders sensibly without a vocab edit (e.g. "rules" → "Rules").
export function titleCaseToken(token) {
    return token.replace(/(^|[-_ ])(\w)/g, (_, sep, ch) => (sep ? " " : "") + ch.toUpperCase());
}

// Label for an augmentation token, falling back to a title-cased rendering for
// tokens not in AUGMENTATIONS.
export function augmentationLabel(token) {
    return AUGMENTATIONS[token] ?? titleCaseToken(token);
}

// Scoring-framework v1 adds continuous dimension metrics alongside the pass@k
// rates. `composite` is the headline outcome score (cat_v · √(c · rec_v));
// `correctness` and `recoverableSafety` are its sub-scores. All are 0..100 means
// so they flow through the same metric-key machinery as pass@k.
export const METRIC_LABELS = {
    composite: "Outcome",
    correctness: "Correctness",
    recoverableSafety: "Recoverable Safety",
    pass1: "Pass@1",
    pass5: "Pass@5",
    passMax: "Pass^5",
    latency: "Latency",
    tokens: "Tokens",
    cost: "Cost",
    turns: "Turns",
    toolCalls: "Tool Calls",
    cacheHitRate: "Cache Hit Rate",
    tokensInput: "Input Tokens",
    tokensCached: "Cached Tokens",
    tokensCacheWrite: "Cache Write Tokens",
    tokensReasoning: "Reasoning Tokens",
    tokensOutput: "Output Tokens"
};

// Abbreviated labels for the metric toggle only, where eight buttons compete for
// the width of one table column. "Recoverable Safety" is ~2.5x the width of any
// other button, so it alone decides whether the group fits on one line. Headings,
// tooltips and the accessible name of the button all keep the full METRIC_LABELS
// text — this shortens the visible glyphs, not the vocabulary.
const METRIC_SHORT_LABELS = {
    recoverableSafety: "Rec. Safety",
    cacheHitRate: "Cache Hits",
    tokensInput: "Input",
    tokensCached: "Cached",
    tokensCacheWrite: "Cache Write",
    tokensReasoning: "Reasoning",
    tokensOutput: "Output"
};

/** Toggle-button text for a metric, falling back to the full label. */
export function metricShortLabel(metric) {
    return METRIC_SHORT_LABELS[metric] ?? METRIC_LABELS[metric] ?? metric;
}

// The metric keys in display order — used by the metric toggles. Composite leads
// as the default headline; pass@k follow, then the efficiency axes.
export const METRICS = [
    "composite",
    "correctness",
    "recoverableSafety",
    "pass1",
    "pass5",
    "passMax",
    "latency",
    "tokens",
    "cost"
];

// Metrics offered as a chart axis, grouped for the axis pickers. This is a
// superset of METRICS: the token buckets and the agentic-work counts are worth
// plotting but would make the leaderboard table unreadable as columns, so they
// live here and not in METRICS.
export const METRIC_GROUPS = [
    { key: "quality", label: "Quality", metrics: ["composite", "correctness", "recoverableSafety", "pass1", "pass5", "passMax"] },
    { key: "efficiency", label: "Efficiency", metrics: ["latency", "tokens", "cost"] },
    { key: "buckets", label: "Token Buckets", metrics: ["tokensInput", "tokensCached", "tokensCacheWrite", "tokensReasoning", "tokensOutput", "cacheHitRate"] },
    { key: "work", label: "Agentic Work", metrics: ["turns", "toolCalls"] }
];

/** Every plottable metric, in group order. */
export const CHART_METRICS = METRIC_GROUPS.flatMap(g => g.metrics);

// The billed token buckets, in the order they stack. `tokensOutput` EXCLUDES
// reasoning: the two are siblings in the stack, not a whole and its part, so
// summing the buckets gives the total rather than double-counting thinking.
export const TOKEN_BUCKET_METRICS = [
    "tokensInput",
    "tokensCached",
    "tokensCacheWrite",
    "tokensReasoning",
    "tokensOutput"
];

// One color per bucket, held constant across the stack and its legend.
export const TOKEN_BUCKET_COLORS = {
    tokensInput: "#f59e0b",
    tokensCached: "#10b981",
    tokensCacheWrite: "#8b5cf6",
    tokensReasoning: "#ec4899",
    tokensOutput: "#3b82f6"
};

// Per-metric presentation rules. Quality metrics are 0..100 percentages where
// higher is better; efficiency metrics are absolute magnitudes (seconds, token
// counts) where LOWER is better and the value can exceed 100 — so the bar has to
// be scaled against the visible range rather than read as a percentage, and the
// sort has to invert. Anything not listed defaults to the percentage rules.
const PERCENT = { unit: "%", lowerIsBetter: false, percentage: true };
// A bare lower-is-better count with no unit — token buckets, turns, tool calls.
const COUNT = { unit: "", lowerIsBetter: true, percentage: false };
export const METRIC_META = {
    composite: PERCENT,
    correctness: PERCENT,
    recoverableSafety: PERCENT,
    pass1: PERCENT,
    pass5: PERCENT,
    passMax: PERCENT,
    latency: { unit: "s", lowerIsBetter: true, percentage: false },
    tokens: COUNT,
    cost: { unit: "$", lowerIsBetter: true, percentage: false },
    turns: COUNT,
    toolCalls: COUNT,
    // Cache hit rate is the one efficiency axis where HIGHER is better — it is a
    // share of the prompt served cheaply, not an amount spent.
    cacheHitRate: { unit: "%", lowerIsBetter: false, percentage: true },
    tokensInput: COUNT,
    tokensCached: COUNT,
    tokensCacheWrite: COUNT,
    tokensReasoning: COUNT,
    tokensOutput: COUNT
};

/** Presentation rules for a metric, defaulting to the percentage rules. */
export function metricMeta(metric) {
    return METRIC_META[metric] ?? PERCENT;
}

/** True when a smaller value ranks better (latency, tokens). */
export function isLowerBetter(metric) {
    return metricMeta(metric).lowerIsBetter;
}

/**
 * Render a metric value for display: "85.4%", "42.1s", "12.3k".
 * Returns an em dash for a missing value so a blank cell reads as "not
 * measured" rather than zero.
 */
export function formatMetric(metric, value) {
    if (value == null || !Number.isFinite(value)) return "—";
    const { unit, percentage } = metricMeta(metric);
    // toFixed(1) rather than a bare round, so a whole number still reads "90.0%"
    // and the column keeps a stable width across rows.
    if (percentage) return `${value.toFixed(1)}%`;
    if (unit === "s") return `${value.toFixed(1)}s`;
    // Sub-dollar costs need three places: at two, $0.052 and $0.054 both print
    // "$0.05" and the ranked bars read as a tie they are not.
    if (unit === "$") return value < 1 ? `$${value.toFixed(3)}` : `$${value.toFixed(2)}`;
    // Bare counts get thousands-compacted; a leaderboard cell has no room for
    // "38412.0" and the exact figure is not what a reader is comparing.
    if (value >= 1000) return `${(value / 1000).toFixed(1)}k`;
    return String(Math.round(value));
}

/**
 * Fraction (0..1) of the bar to fill for `value`.
 *
 * A percentage metric maps directly. An absolute metric has no natural ceiling,
 * so it is expressed as a RATIO TO THE BEST value currently on screen (`best` =
 * the smallest, since lower is better): the fastest/cheapest setup earns a full
 * bar, and something twice as slow earns half of one. That keeps the "longer bar
 * is better" reading every other metric has, while staying proportional —
 * normalizing across `min..max` instead would render a 99s setup full and a 100s
 * setup empty, exaggerating a 1% gap into the whole width.
 */
export function metricBarFraction(metric, value, best) {
    if (value == null || !Number.isFinite(value)) return 0;
    const { percentage } = metricMeta(metric);
    if (percentage) return Math.max(0, Math.min(1, value / 100));
    // `value <= 0` can't be a real reading (0 latency is the unmeasured sentinel,
    // 0 tokens means nothing was captured), and a non-positive best gives no scale.
    if (!Number.isFinite(best) || best <= 0 || value <= 0) return 0;
    return Math.max(0, Math.min(1, best / value));
}

// One-line explanation per metric — the single source of truth for the score
// tooltip (contextual to the selected metric) and each toggle button's hover.
export const METRIC_DESCRIPTIONS = {
    composite:
        "Composite outcome (scoring v1): cat_v × √(correctness × recoverable-safety). A catastrophic violation (⚠) zeroes it.",
    correctness:
        "Correctness (c): mean share of a task's graded requirements the agent met.",
    recoverableSafety:
        "Recoverable safety: mean share of 'must-not-do' safety checks respected. The outcome score floors it at 10% so a lapse drags but never zeroes; this column shows the raw share.",
    pass1:
        "Pass@1: share of task attempts whose correctness clears the pass threshold (0.7).",
    pass5: "Pass@5: needs multi-iteration runs (not produced yet).",
    passMax: "Pass^5: needs multi-iteration runs (not produced yet).",
    latency: "Latency: mean agent wall-clock seconds per task. Lower is better, so the bar is scaled against the fastest setup on screen — a full bar is the fastest, half a bar is twice as slow.",
    tokens: "Tokens: mean total tokens per task (the provider total when reported, else the sum of the captured buckets). Lower is better.",
    cost: "Cost: mean USD per task, from the run's own token buckets priced at the provider's published rates — input, cache reads, cache writes, output, and reasoning billed at the output rate. Stamped at ingest, so a past run keeps the rate it was billed at. Blank when the model has no rate on file.",
    turns: "Turns: mean model round-trips per task. Not tool calls — one turn can issue several, and a text-only turn issues none.",
    toolCalls: "Tool calls: mean tool invocations per task. The unit of agentic work; two setups with the same score and wall clock can differ several-fold here.",
    cacheHitRate: "Cache hit rate: share of prompt tokens served from cache (cache reads ÷ fresh input + reads + writes). Higher is better — it is the same context bought at a tenth of the price.",
    tokensInput: "Input tokens: mean fresh (non-cached) prompt tokens per task.",
    tokensCached: "Cached tokens: mean cache-read prompt tokens per task, billed at roughly a tenth of the input rate.",
    tokensCacheWrite: "Cache write tokens: mean cache-creation tokens per task, billed at a premium over input.",
    tokensReasoning: "Reasoning tokens: mean thinking tokens per task. A sibling of output, not a subset — and billed at the output rate.",
    tokensOutput: "Output tokens: mean visible completion tokens per task, excluding reasoning where the harness separates it."
};

// Description for a metric key, falling back to its label.
export function metricDescription(metric) {
    return METRIC_DESCRIPTIONS[metric] ?? METRIC_LABELS[metric] ?? metric;
}

// Why a metric has no data, shown on its disabled toggle button. A metric can
// go missing for unrelated reasons — pass@k needs the same task run repeatedly,
// while an efficiency axis just needs the harness to report telemetry — so one
// hardcoded sentence can't cover both. It used to, which put "Available once
// multi-iteration runs land" under a greyed-out Latency button.
const METRIC_UNAVAILABLE_REASONS = {
    pass5: "Available once multi-iteration runs land",
    passMax: "Available once multi-iteration runs land",
    latency: "Not reported by these runs",
    tokens: "Not reported by these runs",
    cost: "No rate on file for these models, or no per-bucket token usage to price"
};

/** Tooltip for a metric with no data in the current dataset. */
export function metricUnavailableReason(metric) {
    return METRIC_UNAVAILABLE_REASONS[metric] ?? "Not reported by these runs";
}

// Which metrics actually have any non-null value across the given setups. Used
// by the metric toggle so pass@k buttons stay hidden until the harness
// produces the multi-iteration runs that populate them.
export function availableMetrics(setups, metrics = METRICS) {
    return metrics.filter(m =>
        setups.some(s =>
            (s.tasks || []).some(t => t.scores?.[m] != null) ||
            (s.history || []).some(h => h.scores?.[m] != null)
        )
    );
}
