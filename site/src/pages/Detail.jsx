// Setup detail page (route "/setup/:id"). Ported from detail.html + detail.js:
// identity hero + metric toggle, summary stat cards, sortable per-task table, and
// a single-setup trend chart. Metric carries over from the leaderboard via ?metric=.

import { useEffect, useMemo, useState } from "react";
import { useParams, useSearchParams, Link } from "react-router-dom";
import { useBenchmark } from "../context/BenchmarkContext.jsx";
import { setupScore, setupLabel } from "../lib/accessors.js";
import { METRICS, METRIC_LABELS, availableMetrics, formatMetric, metricBarFraction, isLowerBetter, metricMeta, bestValue } from "../lib/vocab.js";
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
        <div className="bg-white dark:bg-slate-900 rounded-xl border border-slate-200/80 dark:border-slate-800 shadow-sm p-4 flex flex-col gap-1">
            <span className="text-[10px] font-semibold uppercase tracking-wider text-slate-400 dark:text-slate-500">{label}</span>
            <span className="text-xl font-bold text-slate-900 dark:text-slate-100">{value}</span>
            {sub ? <span className="text-[10px] text-slate-400 dark:text-slate-500">{sub}</span> : null}
        </div>
    );
}

function TaskTable({ setup, metric }) {
    const [sort, setSort] = useState({ key: "score", dir: "desc" });

    // Mirrors the leaderboard's ordering (Leaderboard.jsx): "desc" means BEST
    // first, which for latency/tokens is the smallest value, and a task with no
    // value for this metric sorts last in either direction rather than being
    // read as a 0 — otherwise an unmeasured task would head the ascending list
    // as if it were the fastest.
    const tasks = useMemo(() => {
        const dir = sort.dir === "asc" ? 1 : -1;
        const lower = isLowerBetter(metric);
        return [...setup.tasks].sort((a, b) => {
            if (sort.key === "name") return dir * a.name.localeCompare(b.name);
            const av = a.scores[metric];
            const bv = b.scores[metric];
            if (av == null && bv == null) return 0;
            if (av == null) return 1;
            if (bv == null) return -1;
            return dir * (lower ? bv - av : av - bv);
        });
    }, [setup, metric, sort]);

    // Best value across this setup's tasks, so an absolute metric's bar has a
    // scale (percentage metrics ignore it). Same helper the leaderboard uses,
    // so the two cannot disagree about what "best" means.
    const taskBest = useMemo(
        () => bestValue(metric, setup.tasks.map(t => t.scores[metric])),
        [setup, metric]
    );

    function sortBy(key) {
        setSort(prev => prev.key === key
            ? { key, dir: prev.dir === "asc" ? "desc" : "asc" }
            : { key, dir: key === "name" ? "asc" : "desc" });
    }

    // The arrow reports which way the VALUES run, not the internal sort flag.
    // "desc" means best-first, and best-first under latency/tokens is ascending
    // numbers — so the glyph has to invert or the column reads 22.3k → 28.0k
    // under a ▼.
    const Arrow = ({ k }) => {
        if (sort.key !== k) return <span className="text-slate-300 dark:text-slate-600">↕</span>;
        const ascending = k === "name"
            ? sort.dir === "asc"
            : (sort.dir === "asc") !== isLowerBetter(metric);
        return <span className="text-indigo-500 dark:text-indigo-400">{ascending ? "▲" : "▼"}</span>;
    };

    return (
        <div className="w-full bg-white dark:bg-slate-900 rounded-2xl border border-slate-200/80 dark:border-slate-800 shadow-xl shadow-slate-100 dark:shadow-none p-6">
            <div className="mb-3 font-semibold text-slate-500 dark:text-slate-400 tracking-wider uppercase text-xs">Granular Task Breakdown</div>
            <table className="w-full text-left">
                <thead>
                    <tr className="text-[10px] font-semibold uppercase tracking-wider text-slate-400 dark:text-slate-500 select-none">
                        <th className="pb-2 pr-4 cursor-pointer" onClick={() => sortBy("name")}>Task <Arrow k="name" /></th>
                        {/* The metric names the column on its own: "Score (Tokens)"
                            calls a token count a score, and the parenthetical was
                            only ever there because "Score" couldn't carry which one. */}
                        <th className="pb-2 pr-4 cursor-pointer" onClick={() => sortBy("score")}>{METRIC_LABELS[metric]} <Arrow k="score" /></th>
                    </tr>
                </thead>
                <tbody>
                    {tasks.map(task => {
                        // Null-safe: an unscored task shows an empty bar and "—".
                        const s = task.scores[metric];
                        const barPct = metricBarFraction(metric, s, taskBest) * 100;
                        return (
                            <tr key={task.folder} className="border-t border-slate-100 dark:border-slate-800">
                                <td className="py-3 pr-4">
                                    <div className="flex flex-col">
                                        <span className="font-semibold text-slate-700 dark:text-slate-200 text-sm">{task.name}</span>
                                        <span className="text-[10px] font-mono text-slate-400 dark:text-slate-500 mt-0.5">{task.folder}/</span>
                                    </div>
                                </td>
                                <td className="py-3 pr-4 w-1/2">
                                    <div className="flex items-center gap-3">
                                        <div className="flex-grow bg-slate-100 dark:bg-slate-800 h-2 rounded-full overflow-hidden">
                                            <div className="progress-bar-fill h-full rounded-full" style={{ width: `${barPct}%`, backgroundColor: setup.color }} />
                                        </div>
                                        <span className="text-sm font-semibold text-slate-700 dark:text-slate-200 w-14 text-right shrink-0">{formatMetric(metric, s)}</span>
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
        queryMetric && METRIC_LABELS[queryMetric] ? queryMetric : "composite"
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
            <Link to="/" className="inline-flex items-center gap-1.5 text-sm font-medium text-slate-500 dark:text-slate-400 hover:text-indigo-600 dark:hover:text-indigo-400 transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-indigo-500 rounded">
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
    const score = setupScore(setup, metric);

    // Null-safe summary stats: drop tasks with no score for this metric, and
    // guard the all-empty case so a sparse setup renders "—" instead of NaN /
    // -Infinity. Mirrors setupScore()'s null handling; `vals.length` is the
    // number of *scored* tasks, which is what "Average over N tasks" should mean.
    const vals = setup.tasks.map(t => t.scores[metric]).filter(v => v != null);
    // "Best" follows the metric's direction: the fastest task, not the slowest.
    const best = vals.length ? (isLowerBetter(metric) ? Math.min(...vals) : Math.max(...vals)) : null;
    const avg = vals.length ? vals.reduce((a, b) => a + b, 0) / vals.length : null;
    const med = vals.length ? median(vals) : null;
    const pct = v => formatMetric(metric, v);

    // The fifth card reports an efficiency axis the toggle is NOT showing, so it
    // adds a number instead of repeating one. This card used to be a hardcoded
    // "Avg Speed", which was independent of the metric back when latency wasn't
    // selectable; now that it is, selecting Latency makes "Average" the mean
    // latency and the two cards print the same figure side by side. Taking the
    // first efficiency metric other than the selected one gives Tokens under
    // Latency and Latency everywhere else, without naming either key here.
    const companion = METRICS.find(m => !metricMeta(m).percentage && m !== metric);
    const companionVals = companion
        ? setup.tasks.map(t => t.scores[companion]).filter(v => v != null)
        : [];
    const companionAvg = companionVals.length
        ? companionVals.reduce((a, b) => a + b, 0) / companionVals.length
        : null;

    return (
        <main className="w-full max-w-5xl flex flex-col items-center gap-6">
            {backLink}

            <div className="w-full flex flex-col gap-6">
                {/* Identity hero */}
                <div className="w-full bg-white dark:bg-slate-900 rounded-2xl border border-slate-200/80 dark:border-slate-800 shadow-xl shadow-slate-100 dark:shadow-none p-6 flex flex-col lg:flex-row lg:items-center gap-6 justify-between">
                    <div className="flex items-center gap-3 sm:gap-4 min-w-0">
                        <SetupIdentity setup={setup} model={model} harness={harness} variant="hero" />
                    </div>
                    {/* At eight metrics the toggle is two buttons wider than it
                        was, which is enough to clip the longest model name to
                        "Gamma Co…" — the one string on the page that must not be
                        abbreviated. Merely making this column shrinkable isn't
                        enough: flex splits the shortfall in proportion to content
                        width, so the identity still gives up pixels it can only
                        pay for by truncating, while the toggle beside it could
                        have wrapped for free. The lopsided shrink factor says
                        which item yields — this one, all the way down to the
                        headline figure (shrink-0, so it never breaks), and only
                        then does the name start to shorten. */}
                    <div className="flex flex-col items-start lg:items-end gap-2 min-w-0 shrink-[100]">
                        <div className="flex items-baseline gap-1.5 shrink-0 whitespace-nowrap">
                            <span className="text-4xl font-bold text-slate-900 dark:text-slate-100">{formatMetric(metric, score)}</span>
                            <span className="text-xs font-medium text-slate-400 dark:text-slate-500 uppercase tracking-wide">{METRIC_LABELS[metric]}</span>
                        </div>
                        <MetricToggle value={metric} onChange={setMetric} available={available} />
                    </div>
                </div>

                {/* Summary cards */}
                <div className="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-5 gap-3 w-full">
                    <StatCard label="Best Task" value={pct(best)} sub={METRIC_LABELS[metric]} />
                    <StatCard label="Average" value={pct(avg)} sub={`over ${vals.length} tasks`} />
                    <StatCard label="Median" value={pct(med)} sub={METRIC_LABELS[metric]} />
                    <StatCard
                        label="Catastrophic"
                        value={String(setup.catastrophicCount ?? 0)}
                        // "outcome zeroed", not "task zeroed": the task still ran
                        // and still has its other measurements; what a
                        // catastrophic violation zeroes is the Outcome score.
                        sub={
                            setup.catastrophicCount === 1
                                ? "outcome zeroed"
                                : setup.catastrophicCount
                                  ? "outcomes zeroed"
                                  : "none"
                        }
                    />
                    {companion ? (
                        <StatCard
                            label={`Avg ${METRIC_LABELS[companion]}`}
                            value={formatMetric(companion, companionAvg)}
                            sub={companionAvg == null ? "not captured" : `over ${companionVals.length} tasks`}
                        />
                    ) : null}
                </div>

                {/* Task breakdown */}
                <TaskTable setup={setup} metric={metric} />
            </div>

            {/* Single-setup trend chart */}
            <section className="w-full bg-white dark:bg-slate-900 rounded-2xl border border-slate-200/80 dark:border-slate-800 shadow-xl shadow-slate-100 dark:shadow-none p-6 flex flex-col">
                <div className="mb-4">
                    <h2 className="text-xs font-semibold text-slate-500 dark:text-slate-400 uppercase tracking-wider flex items-center gap-2">
                        <svg className="w-4 h-4 text-emerald-500 dark:text-emerald-400" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M7 12l3-3 3 3 4-4M8 21h8a2 2 0 002-2V5a2 2 0 00-2-2H8a2 2 0 00-2 2v14a2 2 0 002 2z" />
                        </svg>
                        {METRIC_LABELS[metric]} Trend Over Time
                    </h2>
                    <p className="text-[10px] text-slate-500 dark:text-slate-400 mt-1">This setup&apos;s {METRIC_LABELS[metric].toLowerCase()} across historical run iterations.</p>
                </div>
                <TrendChart
                    setups={[setup]}
                    metric={metric}
                    models={models}
                    harnesses={harnesses}
                    showLegend={false}
                    fill
                    ariaLabel={`${METRIC_LABELS[metric]} trend over time for this setup`}
                    caption={`${METRIC_LABELS[metric]} trend for ${setupLabel(setup, models, harnesses)}`}
                />
            </section>
        </main>
    );
}
