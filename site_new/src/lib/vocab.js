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

export const METRIC_LABELS = { pass1: "Pass@1", pass5: "Pass@5", passMax: "Pass^5" };

// The metric keys in display order — used by the metric toggles.
export const METRICS = ["pass1", "pass5", "passMax"];

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
