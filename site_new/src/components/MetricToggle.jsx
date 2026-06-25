// Pass@1 / Pass@5 / Pass^5 segmented control, shared by the leaderboard header
// and the detail hero.

import { METRICS, METRIC_LABELS } from "../lib/vocab.js";

export function MetricToggle({ value, onChange }) {
    return (
        <div className="inline-flex p-0.5 bg-slate-100 rounded-lg text-[11px]">
            {METRICS.map(m => {
                const active = m === value;
                const cls = active
                    ? "bg-white text-slate-800 shadow-sm"
                    : "text-slate-600 hover:text-slate-800";
                return (
                    <button
                        key={m}
                        type="button"
                        onClick={() => onChange(m)}
                        aria-pressed={active}
                        className={`px-2.5 py-1 font-medium rounded-md transition-all duration-200 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-indigo-500 focus-visible:ring-offset-2 ${cls}`}
                    >
                        {METRIC_LABELS[m]}
                    </button>
                );
            })}
        </div>
    );
}
