// @ts-check
// =============================================================================
// Comparability — what has to be said out loud before two rows are ranked.
//
// A leaderboard makes one implicit claim: the numbers in a column were produced
// the same way, so the order means something. That claim is not always true, and
// when it is false the table gives no sign — a mean over 6 tasks and a mean over
// 20 render identically, and the shorter one is usually the higher one.
//
// So the caveats are DERIVED from the rows on screen rather than written as
// static prose under the table. A hardcoded sentence is wrong the moment the
// data moves: it keeps warning about a gap that closed, or stays silent about
// one that opened. These functions answer "what is true of exactly these arms,
// under exactly this metric", and the page renders nothing when the answer is
// "nothing" — a caveat strip that is always there is furniture, and gets read
// as such.
//
// Scope: what the read-model can actually support. Notably absent is
// verification coverage (how much of each task was really checked), which the
// harness computes per run but does not carry onto a leaderboard row. Until it
// does, this module cannot speak to it, and says nothing rather than guessing.
// =============================================================================

import { setupScoreSupport } from "./accessors.js";
import { METRIC_LABELS, metricMeta } from "./vocab.js";

/**
 * @typedef {import('./schema').Setup} Setup
 * @typedef {import('./schema').MetricKey} MetricKey
 */

// Metrics the catastrophic gate reaches. Outcome is zeroed by it directly
// (cat_v = 0) and Pass@1 counts a gated attempt as a failure. Correctness and
// recoverable safety are deliberately NOT gated: they report what the agent
// achieved, which stays true of a run that then tripped a tripwire.
const GATED_METRICS = new Set(["composite", "pass1"]);

/**
 * Tasks each visible arm has a reading for, under this metric: the `min`–`max`
 * spread of those counts, the largest task list any arm attempted (`attempted`),
 * and the total number of attempted cells left blank.
 *
 * @param {Setup[]} setups
 * @param {MetricKey} metric
 * @returns {{ min: number, max: number, attempted: number, blanks: number }}
 */
export function supportSpread(setups, metric) {
    const support = setups.map(s => setupScoreSupport(s, metric));
    const counts = support.map(s => s.n);
    return {
        min: counts.length ? Math.min(...counts) : 0,
        max: counts.length ? Math.max(...counts) : 0,
        attempted: support.length ? Math.max(...support.map(s => s.total)) : 0,
        blanks: support.reduce((sum, s) => sum + (s.total - s.n), 0)
    };
}

/**
 * Caveat lines for the arms currently on screen, under the selected metric.
 * Empty when the table is comparable as rendered.
 *
 * @param {Setup[]} setups
 * @param {MetricKey} metric
 * @returns {string[]}
 */
export function comparabilityNotes(setups, metric) {
    if (setups.length < 1) return [];
    const notes = [];
    const label = (METRIC_LABELS[metric] ?? metric).toLowerCase();
    const { min, max, attempted, blanks } = supportSpread(setups, metric);

    // The one that actually changes ranks. An arm measured on fewer tasks is
    // not ahead of one measured on more; it sat a shorter exam.
    if (max > min) {
        notes.push(
            `Each arm is ranked on its mean over the tasks it has a ${label} reading for — between ${min} and ${max} of them. Those means are not like-for-like.`
        );
    } else if (blanks > 0) {
        // Even support, so the ranking is fair; the coverage is still partial
        // and saying so is the difference between "scored 62%" and "scored 62%
        // on the two thirds of the suite we could measure".
        notes.push(
            `Every arm is ranked on ${min} of ${attempted} tasks; the rest have no ${label} reading.`
        );
    }

    if (blanks > 0) {
        notes.push(
            `${blanks} attempted ${plural(blanks, "cell")} ${plural(blanks, "has", "have")} no ${label} reading and ${plural(blanks, "is", "are")} left out of the mean — blank, not 0.`
        );
    }

    const gated = setups.reduce((sum, s) => sum + (s.catastrophicCount || 0), 0);
    if (gated > 0) {
        notes.push(
            GATED_METRICS.has(metric)
                ? `${gated} ${plural(gated, "cell")} tripped a catastrophic safeguard (⚠). ${plural(gated, "It counts", "They count")} as a zero here, whatever the agent otherwise achieved.`
                : `${gated} ${plural(gated, "cell")} tripped a catastrophic safeguard (⚠), which this column does not apply — it reports what the agent achieved. The outcome and pass@1 columns are gated.`
        );
    }

    // Mixed scoring versions in one column: two rules under one heading.
    const versions = scoringVersions(setups);
    if (versions.length > 1) {
        notes.push(
            `Scores in this table were produced by more than one scoring version (${versions.join(", ")}). Versions are not interchangeable and results are never rescored in place.`
        );
    }

    if (!metricMeta(metric).percentage) {
        notes.push(
            "Telemetry, not a score: this is recorded even for attempts that never scored, so it covers cells the score columns leave blank."
        );
    }

    return notes;
}

/** Sorted union of the scoring versions behind the visible arms. */
/**
 * @param {Setup[]} setups
 * @returns {string[]}
 */
export function scoringVersions(setups) {
    const seen = new Set();
    for (const s of setups) {
        for (const v of s.provenance?.scoringVersions ?? []) seen.add(v);
    }
    return [...seen].sort();
}

/**
 * Attempts behind each cell, as a single figure when every arm agrees and a
 * range when they do not. Null when no arm reports it (pre-provenance data).
 *
 * @param {Setup[]} setups
 * @returns {string | null}
 */
export function attemptsPerCell(setups) {
    const counts = setups.map(s => s.provenance?.attempts).filter(n => Number.isFinite(n) && n > 0);
    if (counts.length === 0) return null;
    const min = Math.min(...counts);
    const max = Math.max(...counts);
    return min === max ? `${min}` : `${min}–${max}`;
}

function plural(n, one, many) {
    return n === 1 ? one : (many ?? `${one}s`);
}
