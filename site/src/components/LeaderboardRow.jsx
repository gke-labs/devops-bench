// One leaderboard row — links to the detail page, carrying the active metric.
// Ported from the row template in app.js filterAndRender().

import { Link } from "react-router-dom";
import { SetupIdentity } from "./SetupIdentity.jsx";
import { setupScore, setupLabel } from "../lib/accessors.js";

export function LeaderboardRow({ setup, models, harnesses, metric }) {
    const model = models[setup.model];
    const harness = harnesses[setup.harness];
    const score = setupScore(setup, metric) ?? 0;
    const to = `/setup/${encodeURIComponent(setup.id)}?metric=${encodeURIComponent(metric)}`;

    return (
        <Link
            to={to}
            aria-label={`View details for ${setupLabel(setup, models, harnesses)}`}
            className="relative px-6 py-4 flex flex-col sm:grid sm:grid-cols-12 gap-3 sm:gap-4 items-start sm:items-center hover:bg-slate-50/70 cursor-pointer transition-colors group select-none focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-indigo-500 focus-visible:ring-inset"
        >
            {/* Benchmark subject: model × harness pairing */}
            <div className="col-span-7 sm:col-span-7 grid grid-cols-[1fr_auto_1fr] items-center gap-1 sm:gap-2 w-full sm:w-auto pr-6 sm:pr-0">
                <SetupIdentity setup={setup} model={model} harness={harness} variant="row" />
            </div>

            {/* Score progression meter */}
            <div className="col-span-4 sm:col-span-4 flex items-center gap-3 w-full sm:w-auto mt-2 sm:mt-0">
                <span className="text-sm font-semibold text-slate-900 w-12 min-w-[48px]">
                    {score.toFixed(1)}%
                </span>
                <div className="w-full bg-slate-100 h-2 rounded-full overflow-hidden relative">
                    <div className="progress-bar-fill h-full rounded-full" style={{ width: `${score}%`, backgroundColor: setup.color }} />
                </div>
            </div>

            {/* View-details affordance */}
            <div className="absolute right-6 top-5 sm:relative sm:right-auto sm:top-auto col-span-1 sm:col-span-1 flex items-center justify-end">
                <svg aria-hidden="true" className="w-4 h-4 text-slate-300 group-hover:text-indigo-500 group-hover:translate-x-0.5 transition-all" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M9 5l7 7-7 7" />
                </svg>
            </div>
        </Link>
    );
}
