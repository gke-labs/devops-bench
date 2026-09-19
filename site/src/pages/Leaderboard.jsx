// Leaderboard page (route "/"). Ported from index.html chrome + app.js logic:
// faceted filtering + metric selection drive a sorted list of setups and the
// score-over-time trend chart.

import { useMemo, useState } from "react";
import { useSearchParams } from "react-router-dom";
import { useBenchmark } from "../context/BenchmarkContext.jsx";
import { buildFilterGroups, getFilteredSetups, emptyFilterState } from "../lib/filters.js";
import { setupScore } from "../lib/accessors.js";
import { METRIC_LABELS, availableMetrics, metricDescription, isLowerBetter } from "../lib/vocab.js";
import { getCommonTaskKeys, getMaxTaskCount, getScopedSetups, ENABLE_SCOPE_FILTER } from "../lib/taskScope.js";
import { FilterBar } from "../components/FilterBar.jsx";
import { LeaderboardRow } from "../components/LeaderboardRow.jsx";
import { MetricToggle } from "../components/MetricToggle.jsx";
import { ChartsPanel } from "../components/ChartsPanel.jsx";
import { EmptyState, LoadError, Loading } from "../components/States.jsx";

export function Leaderboard() {
    const { models, harnesses, setups, loading, error } = useBenchmark();
    const [searchParams, setSearchParams] = useSearchParams();
    const [metric, setMetric] = useState("composite");
    const [filterState, setFilterState] = useState(emptyFilterState);

    const queryScope = searchParams.get("scope");
    const [taskScope, setTaskScope] = useState(queryScope === "common" ? "common" : "full");
    const activeScope = ENABLE_SCOPE_FILTER ? taskScope : "full";

    const commonTaskKeys = useMemo(() => getCommonTaskKeys(setups), [setups]);
    const fullTaskCount = useMemo(() => getMaxTaskCount(setups), [setups]);
    const commonTaskCount = commonTaskKeys.length;

    function handleScopeChange(newScope) {
        setTaskScope(newScope);
        setSearchParams(prev => {
            const next = new URLSearchParams(prev);
            if (newScope === "common") next.set("scope", "common");
            else next.delete("scope");
            return next;
        }, { replace: true });
    }

    const scopedSetups = useMemo(
        () => getScopedSetups(setups, activeScope, commonTaskKeys),
        [setups, activeScope, commonTaskKeys]
    );

    const groups = useMemo(() => buildFilterGroups(models, harnesses, scopedSetups), [models, harnesses, scopedSetups]);
    const available = useMemo(() => availableMetrics(scopedSetups), [scopedSetups]);

    const filtered = useMemo(
        () => getFilteredSetups(scopedSetups, groups, filterState),
        [scopedSetups, groups, filterState]
    );

    // Sort the filtered setups by aggregated score under the selected metric.
    // Efficiency metrics rank ascending (lower latency / fewer tokens is better).
    // A setup with no value for the metric sorts last either way rather than
    // being treated as a 0, which would make it look like the best latency.
    const sorted = useMemo(() => {
        const lower = isLowerBetter(metric);
        return [...filtered].sort((a, b) => {
            const av = setupScore(a, metric);
            const bv = setupScore(b, metric);
            if (av == null && bv == null) return 0;
            if (av == null) return 1;
            if (bv == null) return -1;
            return lower ? av - bv : bv - av;
        });
    }, [filtered, metric]);

    // Maximum value on screen for absolute metrics so their bars scale to
    // actual magnitude. Null for percentage metrics, which need none.
    const metricMax = useMemo(() => {
        const vals = sorted.map(s => setupScore(s, metric)).filter(v => v != null && v > 0);
        return vals.length ? Math.max(...vals) : null;
    }, [sorted, metric]);

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
            <div className="w-full bg-white dark:bg-slate-900 rounded-2xl border border-slate-200/80 dark:border-slate-800 shadow-xl shadow-slate-100 dark:shadow-none overflow-hidden">
                {/* Header banner */}
                <header className="px-6 pt-6 pb-5 border-b border-slate-100 dark:border-slate-800 bg-slate-50/50 dark:bg-slate-800/30">
                    <h1 className="text-sm font-semibold text-slate-500 dark:text-slate-400 flex items-center gap-2 uppercase tracking-wider">
                        <svg className="w-4 h-4 text-indigo-500 dark:text-indigo-400" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M9 19v-6a2 2 0 00-2-2H5a2 2 0 00-2 2v6a2 2 0 002 2h2a2 2 0 002-2zm0 0V9a2 2 0 012-2h2a2 2 0 012 2v10m-6 0a2 2 0 002 2h2a2 2 0 002-2m0 0V5a2 2 0 012-2h2a2 2 0 012 2v14a2 2 0 01-2 2h-2a2 2 0 01-2-2z" />
                        </svg>
                        DevOps Bench Leaderboard
                    </h1>
                    <p className="text-xs text-slate-500 dark:text-slate-400 mt-1">Benchmarking model × harness pairings across DevOps tasks — the LLM and the agent runner driving it. All leaderboard scores and metrics represent the average per task across the suite.</p>
                </header>

                {/* Filter bar */}
                {!loading && !error && (
                    <FilterBar
                        groups={groups}
                        filterState={filterState}
                        onToggle={toggleFilter}
                        onClear={clearFilters}
                        shown={filtered.length}
                        total={scopedSetups.length}
                        taskScope={activeScope}
                        onScopeChange={ENABLE_SCOPE_FILTER ? handleScopeChange : undefined}
                        fullTaskCount={fullTaskCount}
                        commonTaskCount={commonTaskCount}
                    />
                )}

                {/* Controls & column headers */}
                <div className="px-6 py-4 bg-white dark:bg-slate-900 border-b border-slate-100 dark:border-slate-800 hidden sm:grid grid-cols-12 gap-4 items-center font-semibold text-xs tracking-wider text-slate-500 dark:text-slate-400 select-none">
                    <div className="col-span-7 sm:col-span-7 grid grid-cols-[1fr_auto_1fr] items-center gap-1 sm:gap-2">
                        <span>MODEL</span>
                        <span aria-hidden="true" className="flex items-center justify-center gap-1 px-0.5 sm:px-1 shrink-0">
                            <span className="hidden sm:block h-px w-2.5"></span>
                            <span className="flex items-center justify-center w-5 h-5 text-slate-300 dark:text-slate-600 font-normal">×</span>
                            <span className="hidden sm:block h-px w-2.5"></span>
                        </span>
                        <span>HARNESS <span className="text-slate-300 dark:text-slate-600 font-normal normal-case tracking-normal">&amp; config</span></span>
                    </div>
                    <div className="col-span-5 sm:col-span-5 flex flex-col gap-2 pr-2">
                        <div className="flex items-center gap-1 min-w-[70px]">
                            {/* "METRIC", not "SCORE": the toggle below can select
                                latency or tokens, and neither is a score. Naming the
                                selected metric here instead would just echo the
                                highlighted button an inch beneath it. */}
                            <span>METRIC</span>
                            <span className="text-[10px] text-slate-400 dark:text-slate-500 font-normal normal-case tracking-normal">
                                (task average)
                            </span>
                            <div tabIndex={0} aria-label={`${METRIC_LABELS[metric]} explanation`} className="group relative cursor-pointer focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-indigo-500/50 rounded-full">
                                <svg aria-hidden="true" className="w-3.5 h-3.5 text-slate-500 dark:text-slate-400 hover:text-slate-700 dark:hover:text-slate-200 transition-colors" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M13 16h-1v-4h-1m1-4h.01M21 12a9 9 0 11-18 0 9 9 0 0118 0z" />
                                </svg>
                                <div role="tooltip" className="absolute bottom-full left-1/2 -translate-x-1/2 mb-2 w-64 p-2.5 bg-slate-900 dark:bg-slate-700 text-white text-[11px] font-normal tracking-normal rounded-lg opacity-0 pointer-events-none group-hover:opacity-100 group-focus-within:opacity-100 transition-opacity shadow-lg z-20 leading-relaxed">
                                    {metricDescription(metric)}
                                </div>
                            </div>
                            {metric === "tokens" && (
                                <div className="ml-auto flex items-center gap-2 text-[10px] font-normal normal-case tracking-normal text-slate-400 dark:text-slate-500">
                                    <span className="inline-flex items-center gap-1"><span className="w-1.5 h-1.5 rounded-full bg-amber-500"></span>In</span>
                                    <span className="inline-flex items-center gap-1"><span className="w-1.5 h-1.5 rounded-full bg-emerald-500"></span>Cached</span>
                                    <span className="inline-flex items-center gap-1"><span className="w-1.5 h-1.5 rounded-full bg-blue-500"></span>Out</span>
                                </div>
                            )}
                        </div>
                        <MetricToggle value={metric} onChange={setMetric} available={available} />
                    </div>
                </div>

                {/* Rows */}
                <div className="divide-y divide-slate-100 dark:divide-slate-800">
                    {loading ? <Loading />
                        : error ? <LoadError />
                        : sorted.length === 0 ? <EmptyState onClear={clearFilters} />
                        : sorted.map(setup => (
                            <LeaderboardRow
                                key={setup.id}
                                setup={setup}
                                models={models}
                                harnesses={harnesses}
                                metric={metric}
                                metricMax={metricMax}
                                taskScope={activeScope}
                            />
                        ))}
                </div>

                {/* Table footnote */}
                {!loading && !error && sorted.length > 0 && (
                    <div className="px-6 py-2.5 bg-slate-50/50 dark:bg-slate-800/20 border-t border-slate-100 dark:border-slate-800 text-[11px] text-slate-400 dark:text-slate-500 flex flex-col sm:flex-row items-start sm:items-center justify-between gap-1">
                        <span>
                            * {ENABLE_SCOPE_FILTER && activeScope === "common"
                                ? `Common tasks view: all figures evaluated across the ${commonTaskCount} common task(s) (${commonTaskKeys.join(", ")}).`
                                : "All leaderboard scores and efficiency figures represent task averages (mean across evaluated tasks)."}
                        </span>
                        <span className="text-[10px] text-slate-400 dark:text-slate-500">Click any row for granular per-task breakdown.</span>
                    </div>
                )}
            </div>

            {/* Efficiency charts — the same filtered setups the table shows. */}
            {!loading && !error && filtered.length > 0 && (
                <ChartsPanel setups={filtered} models={models} harnesses={harnesses} />
            )}
        </main>
    );
}
