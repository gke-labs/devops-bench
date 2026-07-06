// Pass@1 / Pass@5 / Pass^5 segmented control, shared by the leaderboard header
// and the detail hero. `available` (optional) marks which metrics have data —
// the others render DISABLED rather than hidden, so the UI advertises that
// pass5/passMax will return once the harness produces multi-iteration runs.
// When omitted (or empty), every metric is enabled (back-compat).

import { METRICS, METRIC_LABELS } from "../lib/vocab.js";

export function MetricToggle({ value, onChange, available }) {
    const hasFilter = Array.isArray(available) && available.length > 0;
    const isEnabled = m => !hasFilter || available.includes(m);
    return (
        <div className="inline-flex p-0.5 bg-slate-100 rounded-lg text-[11px]">
            {METRICS.map(m => {
                const active = m === value;
                const enabled = isEnabled(m);
                const cls = active
                    ? "bg-white text-slate-800 shadow-sm"
                    : enabled
                        ? "text-slate-600 hover:text-slate-800"
                        : "text-slate-300";
                return (
                    <button
                        key={m}
                        type="button"
                        onClick={() => enabled && onChange(m)}
                        disabled={!enabled}
                        aria-pressed={active}
                        title={enabled ? undefined : "Available once multi-iteration runs land"}
                        className={`px-2.5 py-1 font-medium rounded-md transition-all duration-200 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-indigo-500 focus-visible:ring-offset-2 disabled:cursor-not-allowed ${cls}`}
                    >
                        {METRIC_LABELS[m]}
                    </button>
                );
            })}
        </div>
    );
}
