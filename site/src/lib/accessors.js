// @ts-check
// =============================================================================
// Derived accessors — pure, read-only functions over a `setup`.
//
// Ported verbatim from the old data.js section 3, with one change: setupLabel now
// takes (setup, models, harnesses) explicitly instead of reading module globals,
// so it stays a pure, easily-tested function.
// =============================================================================

import { AUGMENTATIONS, augmentationLabel, metricMeta } from "./vocab.js";

/**
 * @typedef {import('./schema').Setup} Setup
 * @typedef {import('./schema').ModelMap} ModelMap
 * @typedef {import('./schema').HarnessMap} HarnessMap
 * @typedef {import('./schema').MetricKey} MetricKey
 */

// Per-augmentation chip style. Tokens not listed here use the neutral fallback.
const AUG_TAG_CLS = {
    skills: "bg-indigo-50 dark:bg-indigo-500/10 text-indigo-700 dark:text-indigo-300 ring-1 ring-indigo-100 dark:ring-indigo-500/30",
    mcp: "bg-emerald-50 dark:bg-emerald-500/10 text-emerald-700 dark:text-emerald-300 ring-1 ring-emerald-100 dark:ring-emerald-500/30"
};
const AUG_TAG_FALLBACK = "bg-slate-100 dark:bg-slate-800 text-slate-500 dark:text-slate-400";

// Full label distinguishing a setup. Leads with the first-class pairing
// (model × harness), then one segment per augmentation token (or "Baseline"
// when the augmentation array is empty). Used by the chart legend.
/**
 * @param {Setup} setup
 * @param {ModelMap} models
 * @param {HarnessMap} harnesses
 * @returns {string}
 */
export function setupLabel(setup, models, harnesses) {
    const parts = [`${models[setup.model].name} × ${harnesses[setup.harness].name}`];
    if (setup.augmentation.length) {
        for (const token of setup.augmentation) parts.push(augmentationLabel(token));
    } else {
        parts.push(AUGMENTATIONS.baseline);
    }
    return parts.join(" · ");
}

// Alphabetical ordering over the identity a row actually displays — model, then
// harness, then the augmentation chips — rather than over setup.id, which is a
// slug and would sort "api-loop" above "Gemini CLI" on punctuation the reader
// cannot see. `numeric` keeps gpt-5-2 ahead of gpt-5-10 instead of ordering the
// version digits as text.
/**
 * @param {Setup} a
 * @param {Setup} b
 * @param {ModelMap} models
 * @param {HarnessMap} harnesses
 * @returns {number}
 */
export function compareByName(a, b, models, harnesses) {
    const cmp = (x, y) => x.localeCompare(y, undefined, { numeric: true, sensitivity: "base" });
    return cmp(models[a.model].name, models[b.model].name)
        || cmp(harnesses[a.harness].name, harnesses[b.harness].name)
        || cmp(a.augmentation.join(","), b.augmentation.join(","));
}

// Secondary modifier chips — one per augmentation token, or a single neutral
// "Baseline" chip when the augmentation array is empty. The harness type chip
// is built separately at the call site (it needs the per-harness accent color).
export function setupTags(setup) {
    if (!setup.augmentation.length) {
        return [{ text: AUGMENTATIONS.baseline, cls: AUG_TAG_FALLBACK }];
    }
    return setup.augmentation.map(token => ({
        text: augmentationLabel(token),
        cls: AUG_TAG_CLS[token] ?? AUG_TAG_FALLBACK
    }));
}

// Aggregated headline score for a setup under the selected metric. Mean over
// tasks; null-safe (ignores tasks with no score); null if no scored tasks.
/**
 * @param {Setup} setup
 * @param {MetricKey} metric
 * @returns {number | null}
 */
export function setupScore(setup, metric) {
    const vals = setup.tasks.map(t => t.scores[metric]).filter(v => v != null);
    return vals.length ? vals.reduce((sum, v) => sum + v, 0) / vals.length : null;
}

// Trend points for the metric as { x: <epoch ms>, y: <score> }, in time order.
// Sparse by construction — a setup only yields points for runs it actually has.
/**
 * @param {Setup} setup
 * @param {MetricKey} metric
 * @returns {{ x: number, y: number | null }[]}
 */
export function setupHistory(setup, metric) {
    return setup.history.map(h => ({ x: Date.parse(h.t), y: h.scores[metric] }));
}

// Sorted union of run timestamps (ISO) across the given setups. Used to build a
// stable shared axis for the trend chart and its accessibility table.
export function allRunDates(setupsList) {
    const set = new Set();
    setupsList.forEach(s => s.history.forEach(h => set.add(h.t)));
    return [...set].sort();
}

// Format a run timestamp (ISO string or epoch ms) as yyyy-mm-dd for axis ticks /
// table headers. Pinned to UTC; en-CA yields ISO order.
export function formatRunDate(t) {
    return new Date(t).toLocaleDateString("en-CA", { timeZone: "UTC", year: "numeric", month: "2-digit", day: "2-digit" });
}

// A round tick step for an absolute range: 1, 2, 2.5 or 5 times a power of ten,
// the smallest that keeps the axis under ~8 gridlines. The percentage branch can
// hardcode 10 because its range is always 0..100; an absolute range spans
// seconds to tens of thousands of tokens, so the step has to follow the data.
function niceStep(range) {
    const magnitude = 10 ** Math.floor(Math.log10(range / 4));
    for (const m of [1, 2, 2.5, 5]) {
        if (range / (magnitude * m) <= 8) return magnitude * m;
    }
    return magnitude * 10;
}

// Round `value` to a multiple of `step` with `round` (Math.floor / Math.ceil).
// The trailing toFixed(6) drops float dust so a 0.1 step yields 24.3, not
// 24.299999999999997, which would print as a long decimal on the axis.
function snap(value, step, round) {
    return Number((round(value / step) * step).toFixed(6));
}

// Trend-chart y-axis [min, max] for the given setups + metric. Fits the plotted
// scores instead of a fixed 60–100 window so low scorers aren't clipped off the
// bottom: pad by 5, snap to tens (keeps the 10-step ticks clean), clamp to
// [0, 100]. Falls back to the full 0..100 range when there are no scored points.
/**
 * @param {import('./schema').Setup[]} setupsList
 * @param {MetricKey} metric
 * @returns {{ min: number, max: number }}
 */
export function yAxisBounds(setupsList, metric) {
    const ys = setupsList
        .flatMap(s => setupHistory(s, metric))
        .map(p => p.y)
        .filter(y => y != null);
    if (!ys.length) return { min: 0, max: 100 };
    const lo = Math.min(...ys);
    const hi = Math.max(...ys);
    // Absolute metrics (latency, tokens) have no 100 ceiling — clamping them
    // there would flatten every series onto the top gridline. Pad by a tenth of
    // the range instead and let the axis follow the data.
    if (!metricMeta(metric).percentage) {
        const pad = Math.max((hi - lo) * 0.1, hi * 0.05, 1);
        // Snap to a round step for the same reason the percentage branch snaps
        // to tens: Chart.js labels the endpoints as well as the interior ticks,
        // so a raw padded bound prints a stray "54.8s" hard against the "54.0s"
        // gridline above it.
        const step = niceStep(hi + pad - Math.max(0, lo - pad));
        return {
            min: Math.max(0, snap(lo - pad, step, Math.floor)),
            max: snap(hi + pad, step, Math.ceil)
        };
    }
    const min = Math.max(0, Math.floor((lo - 5) / 10) * 10);
    const max = Math.min(100, Math.ceil((hi + 5) / 10) * 10);
    // Guard against a zero-height axis when all points sit in one 10-wide band.
    return { min, max: max > min ? max : Math.min(100, min + 10) };
}
