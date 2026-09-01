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
    inputTokens: "Input Tokens",
    outputTokens: "Output Tokens",
    cachedTokens: "Cached Tokens"
};

// Abbreviated labels for the metric toggle only, where ten buttons compete for
// the width of one table column. "Recoverable Safety" is ~2.5x the width of any
// other button, so it alone decides whether the group fits on one line. Headings,
// tooltips and the accessible name of the button all keep the full METRIC_LABELS
// text — this shortens the visible glyphs, not the vocabulary.
//
// The token axes drop the shared "Tokens" noun because the efficiency pill
// already groups them next to each other: three buttons reading "Input Tokens /
// Output Tokens / Cached Tokens" repeat the word twice for no discrimination,
// and the full name survives in the tooltip and the accessible name.
const METRIC_SHORT_LABELS = {
    recoverableSafety: "Rec. Safety",
    inputTokens: "Input",
    outputTokens: "Output",
    cachedTokens: "Cached"
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
    "inputTokens",
    "outputTokens",
    "cachedTokens"
];

// Per-metric presentation rules. Quality metrics are 0..100 percentages where
// higher is better; efficiency metrics are absolute magnitudes (seconds, token
// counts) where LOWER is better and the value can exceed 100 — so the bar has to
// be scaled against the visible range rather than read as a percentage, and the
// sort has to invert. Anything not listed defaults to the percentage rules.
const PERCENT = { unit: "%", lowerIsBetter: false, percentage: true };
const TOKENS = { unit: "", lowerIsBetter: true, percentage: false };
export const METRIC_META = {
    composite: PERCENT,
    correctness: PERCENT,
    recoverableSafety: PERCENT,
    pass1: PERCENT,
    pass5: PERCENT,
    passMax: PERCENT,
    latency: { unit: "s", lowerIsBetter: true, percentage: false },
    inputTokens: TOKENS,
    outputTokens: TOKENS,
    cachedTokens: TOKENS
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

/**
 * The best value among `values` for `metric`, or null when none qualifies.
 *
 * "Best" follows the metric's direction: the smallest for a lower-is-better
 * absolute metric, the largest otherwise. Non-positive readings are dropped
 * from the lower-is-better case because they are the unmeasured sentinel
 * (see `latencyOf` / `bucketSum` in seed/mock-data.mjs). That matters beyond
 * the offending row: `best` is shared by the whole column, so one 0 would trip
 * the `best <= 0` guard above and flatten EVERY bar, not just its own.
 *
 * Shared by the leaderboard (across visible setups) and the detail task table
 * (across one setup's tasks) so the two cannot drift apart.
 */
export function bestValue(metric, values) {
    const vals = values.filter(v => v != null && Number.isFinite(v));
    if (!isLowerBetter(metric)) return vals.length ? Math.max(...vals) : null;
    const positive = vals.filter(v => v > 0);
    return positive.length ? Math.min(...positive) : null;
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
    inputTokens:
        "Input tokens: mean prompt tokens sent per task, including cache writes. Kept separate from output because providers bill it at a fraction of the generated rate. Lower is better.",
    outputTokens:
        "Output tokens: mean generated tokens per task, including reasoning tokens (a sibling of output, not a subset). The most expensive axis, and typically a few percent of the volume. Lower is better.",
    cachedTokens:
        "Cached tokens: mean cache-read tokens per task — prompt content billed at a steep discount. Reported by some harnesses only, so a blank cell means not reported, not zero. Lower is better."
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
    inputTokens: "Not reported by these runs",
    outputTokens: "Not reported by these runs",
    // Cache reads are the one axis a harness can legitimately omit while
    // reporting everything else, so the reason names the harness, not the run.
    cachedTokens: "Not reported by these harnesses"
};

/** Tooltip for a metric with no data in the current dataset. */
export function metricUnavailableReason(metric) {
    return METRIC_UNAVAILABLE_REASONS[metric] ?? "Not reported by these runs";
}

// Which metrics actually have any non-null value across the given setups. Used
// by the metric toggle so pass@k buttons stay hidden until the harness
// produces the multi-iteration runs that populate them.
export function availableMetrics(setups) {
    return METRICS.filter(m =>
        setups.some(s =>
            (s.tasks || []).some(t => t.scores?.[m] != null) ||
            (s.history || []).some(h => h.scores?.[m] != null)
        )
    );
}
