// Display vocabularies — UI constants, not data.

export const HARNESS_TYPES = { cli: "CLI", api: "API" };                    // BENCH_AGENT_TYPE family
export const AUGMENTATIONS = { baseline: "Baseline", gca: "GCA + Skills" }; // secondary modifier layer
export const METRIC_LABELS = { pass1: "Pass@1", pass5: "Pass@5", passMax: "Pass^5" };

// The metric keys in display order — used by the metric toggles.
export const METRICS = ["pass1", "pass5", "passMax"];
