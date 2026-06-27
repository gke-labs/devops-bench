// Setup detail page (route "/setup/:id"). Ported from detail.html + detail.js:
// identity hero + metric toggle, summary stat cards, sortable per-task table, and
// a single-setup trend chart. Metric carries over from the leaderboard via ?metric=.

import { useEffect, useMemo, useState } from "react";
import { useParams, useSearchParams, Link } from "react-router-dom";
import { useBenchmark } from "../context/BenchmarkContext.jsx";
import { setupScore, setupLabel } from "../lib/accessors.js";
import { METRIC_LABELS, availableMetrics } from "../lib/vocab.js";
import { SetupIdentity } from "../components/SetupIdentity.jsx";
import { MetricToggle } from "../components/MetricToggle.jsx";
import { TrendChart } from "../components/TrendChart.jsx";
import { NotFound, Loading, LoadError } from "../components/States.jsx";

function median(nums) {
    const s = [...nums].sort((a, b) => a - b);
    const mid = Math.floor(s.length / 2);
    return s.length % 2 ? s[mid] : (s[mid - 1] + s[mid]) / 2;
}

function StatCard({ label, value, sub }) {
    return (
        <div className="bg-white rounded-xl border border-slate-200/80 shadow-sm p-4 flex flex-col gap-1">
            <span className="text-[10px] font-semibold uppercase tracking-wider text-slate-400">{label}</span>
            <span className="text-xl font-bold text-slate-900">{value}</span>
            {sub ? <span className="text-[10px] text-slate-400">{sub}</span> : null}
        </div>
    );
}

function TaskTable({ setup, metric }) {
    const [sort, setSort] = useState({ key: "score", dir: "desc" });

    const tasks = useMemo(() => {
        const dir = sort.dir === "asc" ? 1 : -1;
        return [...setup.tasks].sort((a, b) =>
            sort.key === "name"
                ? dir * a.name.localeCompare(b.name)
                : dir * ((a.scores[metric] ?? 0) - (b.scores[metric] ?? 0))
        );
    }, [setup, metric, sort]);

    function sortBy(key) {
        setSort(prev => prev.key === key
            ? { key, dir: prev.dir === "asc" ? "desc" : "asc" }
            : { key, dir: key === "name" ? "asc" : "desc" });
    }

    const Arrow = ({ k }) => sort.key === k
        ? <span className="text-indigo-500">{sort.dir === "asc" ? "▲" : "▼"}</span>
        : <span className="text-slate-300">↕</span>;

    return (
        <div className="w-full bg-white rounded-2xl border border-slate-200/80 shadow-xl shadow-slate-100 p-6">
            <div className="mb-3 font-semibold text-slate-500 tracking-wider uppercase text-xs">Granular Task Breakdown</div>
            <table className="w-full text-left">
                <thead>
                    <tr className="text-[10px] font-semibold uppercase tracking-wider text-slate-400 select-none">
                        <th className="pb-2 pr-4 cursor-pointer" onClick={() => sortBy("name")}>Task <Arrow k="name" /></th>
                        <th className="pb-2 pr-4 cursor-pointer" onClick={() => sortBy("score")}>Score ({METRIC_LABELS[metric]}) <Arrow k="score" /></th>
                    </tr>
                </thead>
                <tbody>
                    {tasks.map(task => {
                        // Null-safe: an unscored task shows an empty bar and "—".
                        const s = task.scores[metric];
                        return (
                            <tr key={task.folder} className="border-t border-slate-100">
                                <td className="py-3 pr-4">
                                    <div className="flex flex-col">
                                        <span className="font-semibold text-slate-700 text-sm">{task.name}</span>
                                        <span className="text-[10px] font-mono text-slate-400 mt-0.5">{task.folder}/</span>
                                    </div>
                                </td>
                                <td className="py-3 pr-4 w-1/2">
                                    <div className="flex items-center gap-3">
                                        <div className="flex-grow bg-slate-100 h-2 rounded-full overflow-hidden">
                                            <div className="progress-bar-fill h-full rounded-full" style={{ width: `${s ?? 0}%`, backgroundColor: setup.color }} />
                                        </div>
                                        <span className="text-sm font-semibold text-slate-700 w-12 text-right shrink-0">{s == null ? "—" : `${s}%`}</span>
                                    </div>
                                </td>
                            </tr>
                        );
                    })}
                </tbody>
            </table>
        </div>
    );
}

export function Detail() {
    const { id } = useParams();
    const [searchParams] = useSearchParams();
    const { models, harnesses, setups, loading, error } = useBenchmark();

    const queryMetric = searchParams.get("metric");
    const [metric, setMetric] = useState(
        queryMetric && METRIC_LABELS[queryMetric] ? queryMetric : "pass1"
    );

    const setup = useMemo(() => setups.find(s => s.id === id) || null, [setups, id]);
    const available = useMemo(() => (setup ? availableMetrics([setup]) : []), [setup]);

    useEffect(() => {
        document.title = setup
            ? `${setupLabel(setup, models, harnesses)} · DevOps Bench Leaderboard`
            : "Setup Detail · DevOps Bench Leaderboard";
    }, [setup, models, harnesses]);

    const backLink = (
        <div className="w-full">
            <Link to="/" className="inline-flex items-center gap-1.5 text-sm font-medium text-slate-500 hover:text-indigo-600 transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-indigo-500 rounded">
                <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M15 19l-7-7 7-7" />
                </svg>
                Back to Leaderboard
            </Link>
        </div>
    );

    if (loading) {
        return <main className="w-full max-w-5xl flex flex-col items-center gap-6">{backLink}<Loading /></main>;
    }
    if (error) {
        return <main className="w-full max-w-5xl flex flex-col items-center gap-6">{backLink}<LoadError /></main>;
    }
    if (!setup) {
        return <main className="w-full max-w-5xl flex flex-col items-center gap-6">{backLink}<NotFound id={id} /></main>;
    }

    const model = models[setup.model];
    const harness = harnesses[setup.harness];
    const score = setupScore(setup, metric) ?? 0;

    // Null-safe summary stats: drop tasks with no score for this metric, and
    // guard the all-empty case so a sparse setup renders "—" instead of NaN /
    // -Infinity. Mirrors setupScore()'s null handling; `vals.length` is the
    // number of *scored* tasks, which is what "Average over N tasks" should mean.
    const vals = setup.tasks.map(t => t.scores[metric]).filter(v => v != null);
    const best = vals.length ? Math.max(...vals) : null;
    const avg = vals.length ? vals.reduce((a, b) => a + b, 0) / vals.length : null;
    const med = vals.length ? median(vals) : null;
    const pct = v => (v == null ? "—" : `${v.toFixed(1)}%`);

    return (
        <main className="w-full max-w-5xl flex flex-col items-center gap-6">
            {backLink}

            <div className="w-full flex flex-col gap-6">
                {/* Identity hero */}
                <div className="w-full bg-white rounded-2xl border border-slate-200/80 shadow-xl shadow-slate-100 p-6 flex flex-col lg:flex-row lg:items-center gap-6 justify-between">
                    <div className="flex items-center gap-3 sm:gap-4 min-w-0">
                        <SetupIdentity setup={setup} model={model} harness={harness} variant="hero" />
                    </div>
                    <div className="flex flex-col items-start lg:items-end gap-2 shrink-0">
                        <div className="flex items-baseline gap-1.5">
                            <span className="text-4xl font-bold text-slate-900">{score.toFixed(1)}<span className="text-2xl">%</span></span>
                            <span className="text-xs font-medium text-slate-400 uppercase tracking-wide">{METRIC_LABELS[metric]}</span>
                        </div>
                        <MetricToggle value={metric} onChange={setMetric} available={available} />
                    </div>
                </div>

                {/* Summary cards */}
                <div className="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-5 gap-3 w-full">
                    <StatCard label="Best Task" value={pct(best)} sub={METRIC_LABELS[metric]} />
                    <StatCard label="Average" value={pct(avg)} sub={`over ${vals.length} tasks`} />
                    <StatCard label="Median" value={pct(med)} sub={METRIC_LABELS[metric]} />
                    <StatCard label="Avg Cost" value="N/A" sub="not captured yet" />
                    <StatCard label="Avg Speed" value="N/A" sub="not captured yet" />
                </div>

                {/* Task breakdown */}
                <TaskTable setup={setup} metric={metric} />
            </div>

            {/* Single-setup trend chart */}
            <section className="w-full bg-white rounded-2xl border border-slate-200/80 shadow-xl shadow-slate-100 p-6 flex flex-col">
                <div className="mb-4">
                    <h2 className="text-xs font-semibold text-slate-500 uppercase tracking-wider flex items-center gap-2">
                        <svg className="w-4 h-4 text-emerald-500" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M7 12l3-3 3 3 4-4M8 21h8a2 2 0 002-2V5a2 2 0 00-2-2H8a2 2 0 00-2 2v14a2 2 0 002 2z" />
                        </svg>
                        Score Trend Over Time
                    </h2>
                    <p className="text-[10px] text-slate-500 mt-1">This setup's success rate across historical run iterations.</p>
                </div>
                <TrendChart
                    setups={[setup]}
                    metric={metric}
                    models={models}
                    harnesses={harnesses}
                    showLegend={false}
                    fill
                    ariaLabel="Score trend over time for this setup"
                    caption={`Score trend for ${setupLabel(setup, models, harnesses)} (metric: ${metric})`}
                />
            </section>
        </main>
    );
}
