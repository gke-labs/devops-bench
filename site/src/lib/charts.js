// @ts-check
// =============================================================================
// Chart geometry — pure functions over setups, no Chart.js and no React.
//
// The efficiency charts are the first place the dashboard makes a CLAIM about
// the data rather than listing it: "this setup is on the frontier", "these
// dots are the same harness". Both claims are arithmetic, and arithmetic buried
// in a render function is arithmetic nobody tests — so it lives here and the
// components stay presentation.
// =============================================================================

import { setupLabel, setupScore, setupValue, scoreOf } from "./accessors.js";
import { augmentationLabel, isLowerBetter } from "./vocab.js";

/**
 * @typedef {import('./schema').Setup} Setup
 * @typedef {import('./schema').MetricKey} MetricKey
 * @typedef {{ x: number, y: number, setup: Setup }} ScatterPoint
 */

/**
 * Setups plotted as (x, y) under two metrics. A setup missing EITHER value is
 * dropped rather than pinned to an axis at 0 — a setup with no cost data is not
 * a free setup, and drawing it on the y-axis would put it on the frontier.
 *
 * @param {Setup[]} setups
 * @param {MetricKey} xMetric
 * @param {MetricKey} yMetric
 * @param {import('./accessors').TaskView} [xView]
 * @returns {ScatterPoint[]}
 */
export function scatterPoints(setups, xMetric, yMetric, xView = {}) {
    return setups
        .map(setup => ({ x: setupValue(setup, xMetric, xView), y: setupScore(setup, yMetric), setup }))
        .filter(p => Number.isFinite(p.x) && Number.isFinite(p.y));
}

/**
 * The Pareto-optimal subset of `points`, sorted along x so the caller can draw
 * a staircase through it.
 *
 * A point is on the frontier when nothing else beats it on one axis without
 * losing on the other — the set of choices where improving quality costs you
 * something, which is the only honest way to compare a cheap-but-weak setup
 * against an expensive-but-strong one. "Better" is per-axis: lower is better
 * for cost/latency/tokens, higher for a score, so the direction comes from the
 * metric vocabulary rather than being assumed.
 *
 * Exact ties both survive: neither dominates the other, and dropping one would
 * silently hide a setup that is genuinely as good.
 *
 * @param {ScatterPoint[]} points
 * @param {MetricKey} xMetric
 * @param {MetricKey} yMetric
 * @returns {ScatterPoint[]}
 */
export function paretoFrontier(points, xMetric, yMetric) {
    const xLower = isLowerBetter(xMetric);
    const yLower = isLowerBetter(yMetric);
    const atLeastAsGood = (a, b, lower) => (lower ? a <= b : a >= b);
    const strictlyBetter = (a, b, lower) => (lower ? a < b : a > b);

    const dominated = (p, q) =>
        atLeastAsGood(q.x, p.x, xLower) &&
        atLeastAsGood(q.y, p.y, yLower) &&
        (strictlyBetter(q.x, p.x, xLower) || strictlyBetter(q.y, p.y, yLower));

    return points
        .filter(p => !points.some(q => q !== p && dominated(p, q)))
        .sort((a, b) => a.x - b.x);
}

// Colors for the "color by model" mode. Harnesses carry their own brand accent
// in the read-model; models do not, so they draw from a palette by position.
// Assigned over the SORTED key list rather than discovery order so a setup keeps
// its color when the leaderboard is filtered — a legend whose colors shuffle as
// you tick a filter box is worse than no legend.
export const SERIES_PALETTE = [
    "#6366f1", "#f43f5e", "#10b981", "#f59e0b",
    "#0ea5e9", "#a855f7", "#ec4899", "#14b8a6"
];

/**
 * Group setups into color-coded series by model or by harness — purely an
 * ENCODING, so a reader can tell which dot is which and spot clusters.
 *
 * It does NOT rank models or harnesses, and the UI must not imply that it does.
 * Every dot is a model × harness pairing and the two are not separable: the
 * harness decides how much context it re-sends, how many turns it takes and
 * whether it caches, so the same model is a different cost in a different
 * runner. Averaging a model's dots across harnesses would credit the model for
 * its best runner and blame it for its worst. To compare harnesses honestly,
 * hold the model fixed — see {@link harnessComparisons}.
 *
 * Returns series in sorted-key order, each with the setups it covers, so a
 * caller can build one chart dataset per series.
 *
 * @param {Setup[]} setups
 * @param {"model"|"harness"} dimension
 * @param {Record<string, {name: string}>} models
 * @param {Record<string, {name: string, accent: string}>} harnesses
 * @returns {{ key: string, label: string, color: string, setups: Setup[] }[]}
 */
export function colorSeries(setups, dimension, models, harnesses) {
    const byKey = new Map();
    for (const s of setups) {
        const key = dimension === "harness" ? s.harness : s.model;
        if (!byKey.has(key)) byKey.set(key, []);
        byKey.get(key).push(s);
    }
    return [...byKey.keys()].sort().map((key, i) => ({
        key,
        label: (dimension === "harness" ? harnesses[key]?.name : models[key]?.name) ?? key,
        color: dimension === "harness"
            ? (harnesses[key]?.accent ?? SERIES_PALETTE[i % SERIES_PALETTE.length])
            : SERIES_PALETTE[i % SERIES_PALETTE.length],
        setups: byKey.get(key)
    }));
}

/**
 * Setups ranked on one metric, best first — the bar chart that leads each
 * section. Direction comes from the vocabulary, so the top bar is the highest
 * outcome score but the LOWEST cost, and a reader never has to check which way
 * a given chart runs.
 *
 * Setups with no value for the metric are dropped rather than ranked last: an
 * unmeasured setup is not a slow or expensive one. Under a task view that also
 * drops the setups which never ran the selected task.
 *
 * @param {Setup[]} setups
 * @param {MetricKey} metric
 * @param {Record<string, {name: string}>} models
 * @param {Record<string, {name: string, accent: string}>} harnesses
 * @param {import('./accessors.js').TaskView} [view]
 * @returns {{ setup: Setup, label: string, value: number, color: string }[]}
 */
export function rankedBars(setups, metric, models, harnesses, view) {
    const lower = isLowerBetter(metric);
    // Same model colors the scatters use, so a setup is one color down the page.
    const colors = new Map();
    for (const series of colorSeries(setups, "model", models, harnesses)) {
        for (const setup of series.setups) colors.set(setup.id, series.color);
    }
    return setups
        .map(setup => ({
            setup,
            label: setupLabel(setup, models, harnesses),
            value: setupValue(setup, metric, view),
            color: colors.get(setup.id) ?? SERIES_PALETTE[0]
        }))
        .filter(bar => Number.isFinite(bar.value))
        .sort((a, b) => (lower ? a.value - b.value : b.value - a.value));
}

/**
 * The same model run on two or more harnesses, grouped so only the harness
 * varies — the honest way to ask "what does this harness cost me".
 *
 * A scatter of every setup cannot answer that: the dots differ in model AND
 * harness at once, so a cheap dot might be a cheap model rather than an
 * efficient runner. Here the model and the augmentation are held fixed and the
 * remaining spread is the harness's doing — its context handling, its turn
 * count, whether it caches.
 *
 * A group with one harness is dropped: it has nothing to compare against, and
 * showing it as a single full bar would read as a win.
 *
 * `pctVsBest` is `(value / best - 1) * 100` in both directions — positive means
 * "further from the best" on a lower-is-better metric, negative on a
 * higher-is-better one, because the metric name already carries the direction.
 * Null when `best` is not positive, since a ratio to zero says nothing.
 *
 * @param {Setup[]} setups
 * @param {MetricKey} metric
 * @param {Record<string, {name: string}>} models
 * @param {Record<string, {name: string, accent: string}>} harnesses
 * @returns {{ key: string, model: string, label: string, best: number,
 *             entries: { setup: Setup, harness: string, label: string, color: string,
 *                        value: number, pctVsBest: number | null }[] }[]}
 */
export function harnessComparisons(setups, metric, models, harnesses) {
    const lower = isLowerBetter(metric);
    const groups = new Map();

    for (const setup of setups) {
        const value = setupScore(setup, metric);
        if (!Number.isFinite(value)) continue;
        const augmentation = [...setup.augmentation].sort();
        const key = `${setup.model}|${augmentation.join("+")}`;
        if (!groups.has(key)) groups.set(key, { key, setup, augmentation, entries: [] });
        groups.get(key).entries.push({
            setup,
            harness: setup.harness,
            label: harnesses[setup.harness]?.name ?? setup.harness,
            color: harnesses[setup.harness]?.accent ?? SERIES_PALETTE[0],
            value
        });
    }

    return [...groups.values()]
        .filter(g => new Set(g.entries.map(e => e.harness)).size > 1)
        .map(g => {
            const values = g.entries.map(e => e.value);
            const best = lower ? Math.min(...values) : Math.max(...values);
            const modelName = models[g.setup.model]?.name ?? g.setup.model;
            return {
                key: g.key,
                model: g.setup.model,
                label: [modelName, ...(g.augmentation.length ? g.augmentation.map(augmentationLabel) : ["Baseline"])].join(" · "),
                best,
                entries: g.entries
                    .map(e => ({ ...e, pctVsBest: best > 0 ? (e.value / best - 1) * 100 : null }))
                    .sort((a, b) => (lower ? a.value - b.value : b.value - a.value))
            };
        })
        // Groups ranked by their own best harness, best group first. Alphabetical
        // would put "Alpha Pro" above a model that beats it, which is the one
        // thing a ranked chart must not do; the label is a tie-break only.
        .sort((a, b) => (lower ? a.best - b.best : b.best - a.best) || a.label.localeCompare(b.label));
}

/**
 * Per-task values for one setup under a metric, at its latest run. Tasks with no
 * value are dropped, so the result shows what was measured rather than implying
 * a zero.
 *
 * @param {Setup} setup
 * @param {MetricKey} metric
 * @returns {{ value: number, task: string }[]}
 */
export function taskValues(setup, metric) {
    return setup.tasks
        .map(t => ({ value: scoreOf(t.scores, metric), task: t.name || t.folder }))
        .filter(d => d.value != null && Number.isFinite(d.value));
}

// Interpolating between the two order statistics a quantile falls between,
// which is what R's type 7 and numpy's default do. A twelve-task suite puts Q1
// and Q3 between tasks, and snapping to the nearer one would make a box a whole
// task wider or narrower than it is.
const quantile = (sorted, p) => {
    const i = (sorted.length - 1) * p;
    const lo = Math.floor(i);
    return sorted[lo].value + (sorted[Math.ceil(i)].value - sorted[lo].value) * (i - lo);
};

/**
 * How consistent each setup is across the suite, tightest first.
 *
 * Every other view on this page is a mean, and a mean cannot separate a setup
 * that costs the same on all twelve tasks from one that is nearly free on eleven
 * and ruinous on the twelfth. Those are the same number and not the same
 * product, and which one you have decides whether you can budget for it.
 *
 * Ranked on the range RELATIVE to the median, not the raw range: a setup whose
 * numbers are small all round would otherwise take the top of the ranking for
 * being cheap rather than for being predictable. When the median is zero there
 * is no ratio to take, so the raw range stands in.
 *
 * A setup with fewer than two measured tasks is dropped rather than ranked as
 * perfectly consistent, which is what a single measurement would score.
 *
 * `worst` is the task at the bad end, which is the metric's own direction: the
 * slowest task on latency, the lowest-scoring one on an outcome metric.
 *
 * @param {Setup[]} setups
 * @param {MetricKey} metric
 * @param {Record<string, {name: string}>} models
 * @param {Record<string, {name: string, accent: string}>} harnesses
 * @returns {{ setup: Setup, label: string, color: string, count: number,
 *             min: number, q1: number, median: number, q3: number, max: number,
 *             spread: number, worst: { value: number, task: string } }[]}
 */
export function taskSpreads(setups, metric, models, harnesses) {
    const lower = isLowerBetter(metric);
    // Same model colors the rest of the page uses, so a setup is one color down it.
    const colors = new Map();
    for (const series of colorSeries(setups, "model", models, harnesses)) {
        for (const setup of series.setups) colors.set(setup.id, series.color);
    }
    return setups
        .map(setup => {
            const values = taskValues(setup, metric).sort((a, b) => a.value - b.value);
            if (values.length < 2) return null;
            const min = values[0];
            const max = values[values.length - 1];
            const median = quantile(values, 0.5);
            return {
                setup,
                label: setupLabel(setup, models, harnesses),
                color: colors.get(setup.id) ?? SERIES_PALETTE[0],
                count: values.length,
                min: min.value,
                q1: quantile(values, 0.25),
                median,
                q3: quantile(values, 0.75),
                max: max.value,
                spread: median ? (max.value - min.value) / Math.abs(median) : max.value - min.value,
                worst: lower ? max : min
            };
        })
        .filter(Boolean)
        .sort((a, b) => a.spread - b.spread);
}

/**
 * The tasks the given setups have in common ground, as picker options — the
 * union across setups, not the intersection, so a task only one setup ran is
 * still selectable rather than hidden. Ordered by first appearance, which is
 * the order the suite defines them in.
 *
 * @param {Setup[]} setups
 * @returns {{ folder: string, name: string }[]}
 */
export function taskOptions(setups) {
    const byFolder = new Map();
    for (const setup of setups) {
        for (const task of setup.tasks) {
            if (!byFolder.has(task.folder)) byFolder.set(task.folder, task.name || task.folder);
        }
    }
    return [...byFolder].map(([folder, name]) => ({ folder, name }));
}

/**
 * A log axis cannot plot a zero or a negative, and Chart.js renders such a
 * point by dropping it without saying so. Report whether every plotted value on
 * an axis is strictly positive, so the UI can disable the log toggle instead of
 * quietly losing points.
 *
 * @param {number[]} values
 * @returns {boolean}
 */
export function canUseLogScale(values) {
    return values.length > 0 && values.every(v => Number.isFinite(v) && v > 0);
}

/**
 * Place one text label per dot so a reader can name every point without
 * hovering it.
 *
 * A legend only names the color groups, so on a chart where three dots share a
 * color the legend cannot say which is which — the labels have to sit on the
 * dots. That only works if they do not land on top of each other or on another
 * dot, so each label takes the first free spot from a short candidate list:
 * beside the dot, then slid up or down, then above or below it. Placement is
 * greedy in the order given, so pass the dots in ranked order and the best ones
 * get the cleanest positions.
 *
 * When nothing is free the first candidate is used anyway — a label that
 * overlaps is worse than one that doesn't, but far better than a dot with no
 * name at all.
 *
 * @param {{ x: number, y: number, r: number, w: number, h: number }[]} dots
 *   Pixel center, dot radius, and measured label size for each point.
 * @param {{ left: number, right: number, top: number, bottom: number }} area
 * @param {{ x: number, y: number }[]} [line] Pixel vertices of a polyline the
 *   labels must also avoid — the Pareto frontier. It is drawn THROUGH the dots,
 *   so distance from a dot is not distance from the line: a label beside a
 *   frontier dot sits on the segment leaving it whenever that segment is
 *   shallow. Treating it as an obstacle is what pushes the label off it.
 * @param {number} [gap] Clearance between a dot and its own label.
 * @returns {{ x: number, y: number }[]} Label center, parallel to `dots`.
 */
export function placeLabels(dots, area, line = [], gap = 12) {
    const placed = [];
    return dots.map(dot => {
        const hw = dot.w / 2;
        const hh = dot.h / 2;
        const out = dot.r + gap;
        const side = dot.h + 2;
        const candidates = [];
        for (const dy of [0, -side, side]) {
            candidates.push({ x: dot.x + out + hw, y: dot.y + dy });
            candidates.push({ x: dot.x - out - hw, y: dot.y + dy });
        }
        candidates.push({ x: dot.x, y: dot.y - out - hh });
        candidates.push({ x: dot.x, y: dot.y + out + hh });

        const inside = c =>
            c.x - hw >= area.left && c.x + hw <= area.right &&
            c.y - hh >= area.top && c.y + hh <= area.bottom;
        const clearOfLabels = c =>
            !placed.some(p => Math.abs(p.x - c.x) < hw + p.w / 2 && Math.abs(p.y - c.y) < hh + p.h / 2);
        // A dot's own dot never collides: every candidate clears it by `gap`.
        const clearOfDots = c =>
            !dots.some(d => Math.abs(d.x - c.x) < hw + d.r && Math.abs(d.y - c.y) < hh + d.r);
        const clearOfLine = c => {
            const box = { left: c.x - hw, right: c.x + hw, top: c.y - hh, bottom: c.y + hh };
            return !line.some((p, i) => i > 0 && segmentHitsBox(line[i - 1], p, box));
        };

        // The line is the softest constraint: a label crossing it is untidy,
        // while a label on another label is unreadable. So try for a spot that
        // clears everything, and give the line up before giving up a name.
        const ok = c => inside(c) && clearOfLabels(c) && clearOfDots(c);
        const spot =
            candidates.find(c => ok(c) && clearOfLine(c)) ??
            candidates.find(ok) ??
            candidates[0];
        placed.push({ ...spot, w: dot.w, h: dot.h });
        return spot;
    });
}

// Does the segment a→b touch the axis-aligned box? Liang-Barsky: clip the
// segment's parameter range against each edge in turn, and if anything survives
// the segment passes through.
function segmentHitsBox(a, b, { left, right, top, bottom }) {
    const dx = b.x - a.x;
    const dy = b.y - a.y;
    let t0 = 0;
    let t1 = 1;
    for (const [p, q] of [[-dx, a.x - left], [dx, right - a.x], [-dy, a.y - top], [dy, bottom - a.y]]) {
        // Parallel to this edge: either wholly outside it or unconstrained by it.
        if (p === 0) {
            if (q < 0) return false;
            continue;
        }
        const r = q / p;
        if (p < 0) {
            if (r > t1) return false;
            if (r > t0) t0 = r;
        } else {
            if (r < t0) return false;
            if (r < t1) t1 = r;
        }
    }
    return true;
}
