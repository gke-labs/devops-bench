// Leaderboard page (route "/"). Ported from index.html chrome + app.js logic:
// faceted filtering + metric selection drive a sorted list of setups and the
// score-over-time trend chart.

import { useMemo, useState } from "react";
import { useBenchmark } from "../context/BenchmarkContext.jsx";
import { buildFilterGroups, getFilteredSetups, emptyFilterState } from "../lib/filters.js";
import { setupScore } from "../lib/accessors.js";
import { FilterBar } from "../components/FilterBar.jsx";
import { LeaderboardRow } from "../components/LeaderboardRow.jsx";
import { MetricToggle } from "../components/MetricToggle.jsx";
import { TrendChart } from "../components/TrendChart.jsx";
import { EmptyState, LoadError, Loading } from "../components/States.jsx";

export function Leaderboard() {
    const { models, harnesses, setups, loading, error } = useBenchmark();
    const [metric, setMetric] = useState("pass1");
    const [filterState, setFilterState] = useState(emptyFilterState);

    const groups = useMemo(() => buildFilterGroups(models, harnesses, setups), [models, harnesses, setups]);

    const filtered = useMemo(
        () => getFilteredSetups(setups, groups, filterState),
        [setups, groups, filterState]
    );

    // Sort the filtered setups by aggregated score under the selected metric.
    const sorted = useMemo(
        () => [...filtered].sort((a, b) => (setupScore(b, metric) ?? 0) - (setupScore(a, metric) ?? 0)),
        [filtered, metric]
    );

    function toggleFilter(groupKey, value) {
        setFilterState(prev => {
            const next = { ...prev, [groupKey]: new Set(prev[groupKey]) };
            if (next[groupKey].has(value)) next[groupKey].delete(value);
            else next[groupKey].add(value);
            return next;
        });
    }

    function clearFilters() {
        setFilterState(emptyFilterState());
    }

    return (
        <main className="w-full max-w-6xl flex flex-col items-center gap-8">
            <div className="w-full bg-white rounded-2xl border border-slate-200/80 shadow-xl shadow-slate-100 overflow-hidden">
                {/* Header banner */}
                <header className="px-6 pt-6 pb-5 border-b border-slate-100 bg-slate-50/50">
                    <h1 className="text-sm font-semibold text-slate-500 flex items-center gap-2 uppercase tracking-wider">
                        <svg className="w-4 h-4 text-indigo-500" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M9 19v-6a2 2 0 00-2-2H5a2 2 0 00-2 2v6a2 2 0 002 2h2a2 2 0 002-2zm0 0V9a2 2 0 012-2h2a2 2 0 012 2v10m-6 0a2 2 0 002 2h2a2 2 0 002-2m0 0V5a2 2 0 012-2h2a2 2 0 012 2v14a2 2 0 01-2 2h-2a2 2 0 01-2-2z" />
                        </svg>
                        DevOps Bench Leaderboard
                    </h1>
                    <p className="text-xs text-slate-500 mt-1">Benchmarking model × harness pairings across DevOps tasks — the LLM and the agent runner driving it.</p>
                </header>

                {/* Filter bar */}
                {!loading && !error && (
                    <FilterBar
                        groups={groups}
                        filterState={filterState}
                        onToggle={toggleFilter}
                        onClear={clearFilters}
                        shown={filtered.length}
                        total={setups.length}
                    />
                )}

                {/* Controls & column headers */}
                <div className="px-6 py-4 bg-white border-b border-slate-100 hidden sm:grid grid-cols-12 gap-4 items-center font-semibold text-xs tracking-wider text-slate-500 select-none">
                    <div className="col-span-7 sm:col-span-7 grid grid-cols-[1fr_auto_1fr] items-center gap-1 sm:gap-2">
                        <span>MODEL</span>
                        <span aria-hidden="true" className="flex items-center justify-center gap-1 px-0.5 sm:px-1 shrink-0">
                            <span className="hidden sm:block h-px w-2.5"></span>
                            <span className="flex items-center justify-center w-5 h-5 text-slate-300 font-normal">×</span>
                            <span className="hidden sm:block h-px w-2.5"></span>
                        </span>
                        <span>HARNESS <span className="text-slate-300 font-normal normal-case tracking-normal">&amp; config</span></span>
                    </div>
                    <div className="col-span-5 sm:col-span-5 flex flex-col sm:flex-row sm:items-center gap-3 sm:gap-6">
                        <div className="flex items-center gap-1 min-w-[70px]">
                            <span>SCORE</span>
                            <div tabIndex={0} aria-label="Score Explanation" className="group relative cursor-pointer focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-indigo-500/50 rounded-full">
                                <svg aria-hidden="true" className="w-3.5 h-3.5 text-slate-500 hover:text-slate-700 transition-colors" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M13 16h-1v-4h-1m1-4h.01M21 12a9 9 0 11-18 0 9 9 0 0118 0z" />
                                </svg>
                                <div role="tooltip" className="absolute bottom-full left-1/2 -translate-x-1/2 mb-2 w-64 p-2.5 bg-slate-900 text-white text-[11px] font-normal tracking-normal rounded-lg opacity-0 pointer-events-none group-hover:opacity-100 group-focus-within:opacity-100 transition-opacity shadow-lg z-20 leading-relaxed">
                                    Calculated dynamically based on success rate metrics across all core task suites.
                                </div>
                            </div>
                        </div>
                        <MetricToggle value={metric} onChange={setMetric} />
                    </div>
                </div>

                {/* Rows */}
                <div className="divide-y divide-slate-100">
                    {loading ? <Loading />
                        : error ? <LoadError />
                        : sorted.length === 0 ? <EmptyState onClear={clearFilters} />
                        : sorted.map(setup => (
                            <LeaderboardRow key={setup.id} setup={setup} models={models} harnesses={harnesses} metric={metric} />
                        ))}
                </div>
            </div>

            {/* Trend chart */}
            {!loading && !error && filtered.length > 0 && (
                <section className="w-full bg-white rounded-2xl border border-slate-200/80 shadow-xl shadow-slate-100 p-6 flex flex-col">
                    <div className="mb-4">
                        <h2 className="text-xs font-semibold text-slate-500 uppercase tracking-wider flex items-center gap-2">
                            <svg className="w-4 h-4 text-emerald-500" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M7 12l3-3 3 3 4-4M8 21h8a2 2 0 002-2V5a2 2 0 00-2-2H8a2 2 0 00-2 2v14a2 2 0 002 2z" />
                            </svg>
                            Accuracy Performance Trend Over Time
                        </h2>
                        <p className="text-[10px] text-slate-500 mt-1">Comparing agent configuration success rates across historical run iterations.</p>
                    </div>
                    <TrendChart
                        setups={filtered}
                        metric={metric}
                        models={models}
                        harnesses={harnesses}
                        showLegend
                        ariaLabel="Accuracy Performance Trend Over Time Chart comparing different setups across historical runs"
                        caption={`Score trend over time data summary (selected metric: ${metric})`}
                    />
                </section>
            )}
        </main>
    );
}
