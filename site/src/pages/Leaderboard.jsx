// Leaderboard page (route "/"). Ported from index.html chrome + app.js logic:
// faceted filtering + metric selection drive a sorted list of setups and the
// score-over-time trend chart.

import { useMemo, useState } from "react";
import { useBenchmark } from "../context/BenchmarkContext.jsx";
import { buildFilterGroups, getFilteredSetups, emptyFilterState } from "../lib/filters.js";
import { setupScore, compareByName } from "../lib/accessors.js";
import { METRIC_LABELS, availableMetrics, metricDescription, isLowerBetter, bestValue } from "../lib/vocab.js";
import { FilterBar } from "../components/FilterBar.jsx";
import { LeaderboardRow } from "../components/LeaderboardRow.jsx";
import { MetricToggle } from "../components/MetricToggle.jsx";
import { TrendChart } from "../components/TrendChart.jsx";
import { EmptyState, LoadError, Loading } from "../components/States.jsx";

export function Leaderboard() {
    const { models, harnesses, setups, loading, error } = useBenchmark();
    const [metric, setMetric] = useState("composite");
    const [filterState, setFilterState] = useState(emptyFilterState);
    // Rank-first is the default, so the page still opens as a leaderboard. The
    // key deliberately SURVIVES a metric change: the reason to sort by name is
    // to hold every row still while you click across the metric tabs and read
    // one setup down the columns, which re-ranking on each tab makes impossible.
    const [sort, setSort] = useState({ key: "metric", dir: "desc" });

    const groups = useMemo(() => buildFilterGroups(models, harnesses, setups), [models, harnesses, setups]);
    const available = useMemo(() => availableMetrics(setups), [setups]);

    const filtered = useMemo(
        () => getFilteredSetups(setups, groups, filterState),
        [setups, groups, filterState]
    );

    // Sort the filtered setups, either alphabetically or by aggregated score
    // under the selected metric. "desc" means BEST first, which for latency and
    // the token axes is the SMALLEST value — same convention as the detail
    // page's task table, so the two cannot disagree about which way is up.
    // A setup with no value for the metric sorts last in either direction rather
    // than being treated as a 0, which would make it look like the best latency.
    const sorted = useMemo(() => {
        const dir = sort.dir === "asc" ? 1 : -1;
        const lower = isLowerBetter(metric);
        return [...filtered].sort((a, b) => {
            if (sort.key === "name") return dir * compareByName(a, b, models, harnesses);
            const av = setupScore(a, metric);
            const bv = setupScore(b, metric);
            if (av == null && bv == null) return 0;
            if (av == null) return 1;
            if (bv == null) return -1;
            return dir * (lower ? bv - av : av - bv);
        });
    }, [filtered, metric, sort, models, harnesses]);

    // Best value on screen, so an absolute metric's bars have a scale. Computed
    // for every metric; a percentage metric ignores it downstream in
    // metricBarFraction(). See bestValue() for why non-positive readings are
    // excluded rather than min'd over.
    const metricBest = useMemo(
        () => bestValue(metric, sorted.map(s => setupScore(s, metric))),
        [sorted, metric]
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

    // Clicking the header you are already sorted by flips direction; switching
    // headers picks that column's natural default — A→Z for names, best-first
    // for the metric.
    function sortBy(key) {
        setSort(prev => prev.key === key
            ? { key, dir: prev.dir === "asc" ? "desc" : "asc" }
            : { key, dir: key === "name" ? "asc" : "desc" });
    }

    // The glyph describes the column's ORDER, never the raw digits: on the
    // metric ▼ is best-first and ▲ is worst-first, on every metric alike.
    //
    // Pointing it at the digits instead made it flip with no click, because
    // best-first is DESCENDING numbers on Outcome but ASCENDING numbers on
    // latency and the token axes. Moving between the two families inverted the
    // arrow on its own, which reads as the sort mode changing by itself when
    // all you did was change tabs. Rank is the stable thing here, so the arrow
    // tracks rank; the cost is a ▼ above a latency column that counts upward,
    // which the label spells out.
    //
    // These headers are buttons in a CSS grid, not real columnheaders, so
    // aria-sort would be invalid — the direction rides along as
    // visually-hidden text in the button's accessible name instead.
    const Arrow = ({ k }) => {
        if (sort.key !== k) return <span aria-hidden="true" className="text-slate-300 dark:text-slate-600">↕</span>;
        const down = sort.dir === "desc";
        const directionLabel = k === "name"
            ? (down ? "Z to A" : "A to Z")
            : (down ? "best first" : "worst first");
        return (
            <>
                <span aria-hidden="true" className="text-indigo-500 dark:text-indigo-400">{down ? "▼" : "▲"}</span>
                <span className="sr-only">, sorted {directionLabel}</span>
            </>
        );
    };

    const headerBtn = "flex items-center gap-1 hover:text-slate-700 dark:hover:text-slate-200 transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-indigo-500 rounded";

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
                    <p className="text-xs text-slate-500 dark:text-slate-400 mt-1">Benchmarking model × harness pairings across DevOps tasks — the LLM and the agent runner driving it.</p>
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
                <div className="px-6 py-4 bg-white dark:bg-slate-900 border-b border-slate-100 dark:border-slate-800 hidden sm:grid grid-cols-12 gap-4 items-center font-semibold text-xs tracking-wider text-slate-500 dark:text-slate-400 select-none">
                    <div className="col-span-7 sm:col-span-7 grid grid-cols-[1fr_auto_1fr] items-center gap-1 sm:gap-2">
                        {/* Both halves of the pairing sort the same way — the
                            comparator runs model then harness — so either one is
                            a live target rather than only the leading word. */}
                        <button type="button" onClick={() => sortBy("name")} title="Sort alphabetically, holding row order across metrics" className={headerBtn}>
                            MODEL <Arrow k="name" />
                        </button>
                        <span aria-hidden="true" className="flex items-center justify-center gap-1 px-0.5 sm:px-1 shrink-0">
                            <span className="hidden sm:block h-px w-2.5"></span>
                            <span className="flex items-center justify-center w-5 h-5 text-slate-300 dark:text-slate-600 font-normal">×</span>
                            <span className="hidden sm:block h-px w-2.5"></span>
                        </span>
                        <button type="button" onClick={() => sortBy("name")} title="Sort alphabetically, holding row order across metrics" className={headerBtn}>
                            <span>HARNESS <span className="text-slate-300 dark:text-slate-600 font-normal normal-case tracking-normal">&amp; config</span></span>
                        </button>
                    </div>
                    <div className="col-span-5 sm:col-span-5 flex flex-col sm:flex-row sm:flex-wrap sm:items-center gap-3 sm:gap-x-4 sm:gap-y-2 pr-2">
                        <div className="flex items-center gap-1 min-w-[70px]">
                            {/* "METRIC", not "SCORE": the toggle below can select
                                latency or a token axis, none of which is a score. Naming the
                                selected metric here instead would just echo the
                                highlighted button an inch beneath it. */}
                            <button type="button" onClick={() => sortBy("metric")} title={`Rank by ${METRIC_LABELS[metric]} — ▼ best first, ▲ worst first`} className={headerBtn}>
                                METRIC <Arrow k="metric" />
                            </button>
                            <div tabIndex={0} aria-label={`${METRIC_LABELS[metric]} explanation`} className="group relative cursor-pointer focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-indigo-500/50 rounded-full">
                                <svg aria-hidden="true" className="w-3.5 h-3.5 text-slate-500 dark:text-slate-400 hover:text-slate-700 dark:hover:text-slate-200 transition-colors" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M13 16h-1v-4h-1m1-4h.01M21 12a9 9 0 11-18 0 9 9 0 0118 0z" />
                                </svg>
                                <div role="tooltip" className="absolute bottom-full left-1/2 -translate-x-1/2 mb-2 w-64 p-2.5 bg-slate-900 dark:bg-slate-700 text-white text-[11px] font-normal tracking-normal rounded-lg opacity-0 pointer-events-none group-hover:opacity-100 group-focus-within:opacity-100 transition-opacity shadow-lg z-20 leading-relaxed">
                                    {metricDescription(metric)}
                                </div>
                            </div>
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
                            <LeaderboardRow key={setup.id} setup={setup} models={models} harnesses={harnesses} metric={metric} metricBest={metricBest} />
                        ))}
                </div>
            </div>

            {/* Trend chart */}
            {!loading && !error && filtered.length > 0 && (
                <section className="w-full bg-white dark:bg-slate-900 rounded-2xl border border-slate-200/80 dark:border-slate-800 shadow-xl shadow-slate-100 dark:shadow-none p-6 flex flex-col">
                    <div className="mb-4">
                        <h2 className="text-xs font-semibold text-slate-500 dark:text-slate-400 uppercase tracking-wider flex items-center gap-2">
                            <svg className="w-4 h-4 text-emerald-500 dark:text-emerald-400" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M7 12l3-3 3 3 4-4M8 21h8a2 2 0 002-2V5a2 2 0 00-2-2H8a2 2 0 00-2 2v14a2 2 0 002 2z" />
                            </svg>
                            {METRIC_LABELS[metric]} Trend Over Time
                        </h2>
                        <p className="text-[10px] text-slate-500 dark:text-slate-400 mt-1">Comparing agent configuration {METRIC_LABELS[metric].toLowerCase()} across historical run iterations.</p>
                    </div>
                    <TrendChart
                        setups={filtered}
                        metric={metric}
                        models={models}
                        harnesses={harnesses}
                        showLegend
                        ariaLabel={`${METRIC_LABELS[metric]} trend over time, comparing setups across historical runs`}
                        caption={`${METRIC_LABELS[metric]} trend over time data summary`}
                    />
                </section>
            )}
        </main>
    );
}
