// Metric segmented control, shared by the leaderboard header and the detail
// hero. `available` (optional) marks which metrics have data — the others render
// DISABLED rather than hidden, so the UI advertises the axis exists and says why
// it's empty. The reason is per-metric (see metricUnavailableReason): pass@k is
// waiting on multi-iteration runs, the efficiency axes on harness telemetry.
// When `available` is omitted (or empty), every metric is enabled (back-compat).
//
// The metrics are split into two pills, quality and efficiency, rather than one
// long strip: ten buttons overflow the leaderboard's score column, and the
// break should fall BETWEEN the two families rather than mid-strip. Wrapping the
// pills puts it there, and the seam doubles as the visual cue that the efficiency
// axes read the other way — lower is better, absolute units.
//
// Both levels wrap. The pill seam is the PREFERRED break, but the quality group
// alone ("Recoverable Safety" plus five others) still outgrows a narrow score
// column, and a nowrap pill cannot shrink below its content — it just overflows
// again. Letting buttons wrap inside a pill makes overflow impossible at any
// width; the group split only decides where the break lands first.

import { METRICS, METRIC_LABELS, metricDescription, metricMeta, metricShortLabel, metricUnavailableReason } from "../lib/vocab.js";

// Quality metrics first, then efficiency, each preserving METRICS order. Empty
// groups are dropped so a vocab with only one family renders a single pill.
function metricGroups() {
    const quality = METRICS.filter(m => metricMeta(m).percentage);
    const efficiency = METRICS.filter(m => !metricMeta(m).percentage);
    return [quality, efficiency].filter(g => g.length > 0);
}

export function MetricToggle({ value, onChange, available }) {
    const hasFilter = Array.isArray(available) && available.length > 0;
    const isEnabled = m => !hasFilter || available.includes(m);
    return (
        <div className="flex flex-wrap items-center gap-1.5 min-w-0 max-w-full">
            {metricGroups().map(group => (
                <div
                    key={group[0]}
                    className="inline-flex flex-wrap p-0.5 bg-slate-100 dark:bg-slate-800 rounded-lg text-[11px]"
                >
                    {group.map(m => {
                        const active = m === value;
                        const enabled = isEnabled(m);
                        const cls = active
                            ? "bg-white dark:bg-slate-700 text-slate-800 dark:text-slate-100 shadow-sm"
                            : enabled
                                ? "text-slate-600 dark:text-slate-300 hover:text-slate-800 dark:hover:text-slate-100"
                                : "text-slate-300 dark:text-slate-600";
                        return (
                            <button
                                key={m}
                                type="button"
                                onClick={() => enabled && onChange(m)}
                                disabled={!enabled}
                                aria-pressed={active}
                                // The visible text may be abbreviated to fit; the
                                // accessible name stays the full metric label.
                                aria-label={METRIC_LABELS[m]}
                                title={enabled ? metricDescription(m) : metricUnavailableReason(m)}
                                className={`px-2 py-1 font-medium rounded-md whitespace-nowrap transition-all duration-200 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-indigo-500 focus-visible:ring-offset-2 dark:focus-visible:ring-offset-slate-900 disabled:cursor-not-allowed ${cls}`}
                            >
                                {metricShortLabel(m)}
                            </button>
                        );
                    })}
                </div>
            ))}
        </div>
    );
}
