// Setup detail page (route "/setup/:id"). Ported from detail.html + detail.js:
// identity hero + metric toggle, summary stat cards, sortable per-task table, and
// a single-setup trend chart. Metric carries over from the leaderboard via ?metric=.

import { useEffect, useMemo, useState } from "react";
import { useParams, useSearchParams, Link, useNavigate } from "react-router-dom";
import { useBenchmark } from "../context/BenchmarkContext.jsx";
import { setupScore, setupLabel, scoreOf } from "../lib/accessors.js";
import { METRICS, METRIC_LABELS, availableMetrics, formatMetric, metricBarFraction, isLowerBetter, metricMeta, TOKEN_BUCKET_COLORS } from "../lib/vocab.js";
import { getCommonTaskKeys, normalizeTaskKey, ENABLE_SCOPE_FILTER } from "../lib/taskScope.js";
import { SetupIdentity } from "../components/SetupIdentity.jsx";
import { MetricToggle } from "../components/MetricToggle.jsx";
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

function CatastrophicDetails({ task }) {
    const [expanded, setExpanded] = useState(false);

    const flatEntries = useMemo(() => {
        const list = [];
        if (task.catastrophicDetails && typeof task.catastrophicDetails === "object") {
            for (const [gate, items] of Object.entries(task.catastrophicDetails)) {
                if (Array.isArray(items)) {
                    for (const item of items) {
                        if (item && typeof item === "object") {
                            list.push({
                                gate,
                                name: item.name,
                                reason: typeof item.reason === "string" ? item.reason : "",
                                trial: item.trial
                            });
                        }
                    }
                }
            }
        }
        return list;
    }, [task.catastrophicDetails]);

    const kindsLabel = useMemo(() => {
        const counts = new Map();
        if (Array.isArray(task.catastrophicKinds)) {
            for (const k of task.catastrophicKinds) {
                if (typeof k === "string" && k && !counts.has(k)) counts.set(k, 0);
            }
        }
        for (const item of flatEntries) {
            if (item.gate) {
                counts.set(item.gate, (counts.get(item.gate) || 0) + 1);
            }
        }
        const labels = [...counts.entries()].map(([k, count]) => {
            const label = k.replace(/Catastrophic$/, "");
            return count > 0 ? `${label} (${count})` : label;
        }).filter(Boolean);
        return labels.length > 0 ? `Failure: ${labels.join(", ")}` : null;
    }, [task.catastrophicKinds, flatEntries]);

    if (!kindsLabel) {
        return null;
    }

    if (flatEntries.length === 0) {
        return (
            <div className="mt-1">
                <span className="inline-flex max-w-full items-center gap-1.5 rounded-md border border-rose-200/70 dark:border-rose-900/40 bg-rose-50/50 dark:bg-rose-950/25 px-2 py-0.5 text-[11px] font-semibold text-rose-800 dark:text-rose-300 truncate">
                    {kindsLabel}
                </span>
            </div>
        );
    }

    if (!expanded) {
        return (
            <div className="mt-1">
                <button
                    type="button"
                    onClick={() => setExpanded(true)}
                    className="inline-flex max-w-full items-center gap-1.5 rounded-md border border-rose-200/70 dark:border-rose-900/40 bg-rose-50/50 dark:bg-rose-950/25 hover:bg-rose-100/60 dark:hover:bg-rose-950/40 px-2 py-0.5 text-[11px] font-semibold text-rose-800 dark:text-rose-300 transition-colors focus:outline-none"
                >
                    <span className="truncate">{kindsLabel}</span>
                    <span className="shrink-0 text-[10px] text-rose-500 dark:text-rose-400">▼</span>
                </button>
            </div>
        );
    }

    return (
        <div className="mt-1 w-full rounded-lg border border-rose-200/70 dark:border-rose-900/40 bg-rose-50/40 dark:bg-rose-950/20 px-2.5 py-2 text-xs overflow-hidden">
            <button
                type="button"
                onClick={() => setExpanded(false)}
                className="w-full flex items-center justify-between gap-1.5 mb-1.5 pb-1 border-b border-rose-200/60 dark:border-rose-900/40 text-[11px] font-semibold text-rose-800 dark:text-rose-300 hover:text-rose-600 dark:hover:text-rose-200 focus:outline-none text-left"
            >
                <span className="truncate">{kindsLabel}</span>
                <span className="shrink-0 text-[10px] text-rose-500 dark:text-rose-400">▲</span>
            </button>
            <div className="max-h-48 overflow-y-auto pr-1 space-y-1.5">
                {flatEntries.map((item, idx) => (
                    <div key={idx} className={idx > 0 ? "pt-1.5 border-t border-rose-200/50 dark:border-rose-900/30" : ""}>
                        <div className="flex items-center flex-wrap gap-1.5 mb-0.5">
                            {item.trial != null && (
                                <span className="px-1.5 py-0.5 rounded bg-rose-200/60 dark:bg-rose-900/50 text-[10px] font-semibold text-rose-800 dark:text-rose-300">
                                    trial #{item.trial}
                                </span>
                            )}
                            <span className="text-[10px] font-semibold uppercase tracking-wider text-rose-600 dark:text-rose-400">
                                {item.gate.replace(/Catastrophic$/, "")}
                            </span>
                            {item.name && (
                                <span className="font-mono font-semibold text-[11px] text-rose-900 dark:text-rose-200 break-all">
                                    {item.name}
                                </span>
                            )}
                        </div>
                        <div className="font-mono text-[11px] leading-snug text-slate-700 dark:text-slate-300 break-words">
                            {item.reason ? item.reason : <span className="italic text-slate-400">(no reason recorded)</span>}
                        </div>
                    </div>
                ))}
            </div>
        </div>
    );
}

function TaskTable({ setup, metric }) {
    const navigate = useNavigate();
    const [sort, setSort] = useState({ key: "score", dir: "asc" });

    // Defaults to ascending so failing / low-scoring tasks surface first.
    // A task with no value for this metric sorts last in either direction rather
    // than being read as a 0 — otherwise an unmeasured task would head the
    // ascending list as if it were the fastest.
    const tasks = useMemo(() => {
        const dir = sort.dir === "asc" ? 1 : -1;
        const lower = isLowerBetter(metric);
        return [...setup.tasks].sort((a, b) => {
            if (sort.key === "name") return dir * a.name.localeCompare(b.name);
            const av = scoreOf(a.scores, metric);
            const bv = scoreOf(b.scores, metric);
            if (av == null && bv == null) return 0;
            if (av == null) return 1;
            if (bv == null) return -1;
            return dir * (lower ? bv - av : av - bv);
        });
    }, [setup, metric, sort]);

    // Maximum value across this setup's tasks so an absolute metric's bar scales
    // to actual magnitude (percentage metrics ignore it).
    const taskMax = useMemo(() => {
        const vals = setup.tasks.map(t => scoreOf(t.scores, metric)).filter(v => v != null && v > 0);
        if (!vals.length) return null;
        return Math.max(...vals);
    }, [setup, metric]);

    function sortBy(key) {
        setSort(prev => prev.key === key
            ? { key, dir: prev.dir === "asc" ? "desc" : "asc" }
            : { key, dir: "asc" });
    }

    // Same rule as the leaderboard's ⚠ badge and the Catastrophic stat card:
    // only on the quality metrics. What a catastrophic violation zeroes is the
    // Outcome score — the seconds and tokens the run consumed are untouched and
    // still valid, so under an efficiency metric the marker would flag a figure
    // it has no bearing on.
    const badgeable = metricMeta(metric).percentage;

    // Counted off the same tasks[] the table renders, which is also what
    // derive.mjs counts for setup.catastrophicCount — so the legend, the marked
    // rows and the stat card cannot disagree about how many there are.
    const flagged = setup.tasks.filter(t => t.catastrophic).length;

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
            <table className="w-full table-fixed text-left">
                <thead>
                    <tr className="text-[10px] font-semibold uppercase tracking-wider text-slate-400 dark:text-slate-500 select-none">
                        <th className="w-1/2 pb-2 pr-4 cursor-pointer" onClick={() => sortBy("name")}>Task <Arrow k="name" /></th>
                        {/* The metric names the column on its own: "Score (Tokens)"
                            calls a token count a score, and the parenthetical was
                            only ever there because "Score" couldn't carry which one. */}
                        <th className="w-1/2 pb-2 pr-4 cursor-pointer" onClick={() => sortBy("score")}>
                            <div className="flex items-center justify-between">
                                <span>{METRIC_LABELS[metric]} <Arrow k="score" /></span>
                                {metric === "tokens" && (
                                    <div className="flex items-center gap-2 font-normal normal-case tracking-normal text-slate-400 dark:text-slate-500">
                                        <span className="inline-flex items-center gap-1"><span className="w-1.5 h-1.5 rounded-full bg-amber-500"></span>In</span>
                                        <span className="inline-flex items-center gap-1"><span className="w-1.5 h-1.5 rounded-full bg-emerald-500"></span>Cached</span>
                                        <span className="inline-flex items-center gap-1"><span className="w-1.5 h-1.5 rounded-full bg-blue-500"></span>Out</span>
                                    </div>
                                )}
                            </div>
                        </th>
                    </tr>
                </thead>
                <tbody>
                    {tasks.map(task => {
                        // Null-safe: an unscored task shows an empty bar and "—".
                        const s = scoreOf(task.scores, metric);
                        const barPct = metricBarFraction(metric, s, taskMax) * 100;
                        const isTokens = metric === "tokens";
                        const taskInputTokens = isTokens ? scoreOf(task.scores, "inputTokens") : null;
                        const taskCachedTokens = isTokens ? scoreOf(task.scores, "cachedTokens") : null;
                        const taskOutputTokens = isTokens ? scoreOf(task.scores, "outputTokens") : null;
                        const taskSumBuckets = (taskInputTokens || 0) + (taskCachedTokens || 0) + (taskOutputTokens || 0);
                        const tokensTooltip = isTokens
                            ? `Total: ${formatMetric("tokens", s)} (Input: ${formatMetric("inputTokens", taskInputTokens)}, Cached: ${formatMetric("cachedTokens", taskCachedTokens)}, Output: ${formatMetric("outputTokens", taskOutputTokens)})`
                            : undefined;

                        const metricParam = metric ? `&metric=${encodeURIComponent(metric)}` : "";
                        const taskKey = task.name?.replace(/-gitops$/, "") || task.folder?.replace(/-gitops$/, "");
                        const runUrl = `/task/${taskKey}/run/${setup.id}?from=setup${metricParam}`;
                        const fromState = { from: `/setup/${setup.id}${metricParam ? `?${metricParam.slice(1)}` : ""}` };

                        return (
                            <tr
                                key={task.folder}
                                onClick={() => navigate(runUrl, { state: fromState })}
                                className="border-t border-slate-100 dark:border-slate-800 hover:bg-slate-50/70 dark:hover:bg-slate-800/40 cursor-pointer transition-colors group"
                            >
                                <td className="py-3 pr-4 align-top overflow-hidden">
                                    <div className="flex items-center gap-2">
                                        <Link
                                            to={runUrl}
                                            state={fromState}
                                            onClick={(e) => e.stopPropagation()}
                                            className="font-semibold text-slate-800 dark:text-slate-100 group-hover:text-indigo-600 dark:group-hover:text-indigo-400 text-sm block truncate transition-colors"
                                            title="View verification report and rubric results for this run"
                                        >
                                            {task.name}
                                        </Link>
                                    </div>
                                    {badgeable && task.catastrophic && (
                                        <div onClick={(e) => e.stopPropagation()}>
                                            <CatastrophicDetails task={task} />
                                        </div>
                                    )}
                                </td>
                                <td className="py-3 pr-4 w-1/2 align-top">
                                    <div className="flex items-center gap-3">
                                        <div className="flex-grow bg-slate-100 dark:bg-slate-800 h-2 rounded-full overflow-hidden" title={tokensTooltip}>
                                            {isTokens && taskSumBuckets > 0 ? (
                                                <div className="progress-bar-fill h-full rounded-full flex overflow-hidden" style={{ width: `${barPct}%` }}>
                                                    {taskInputTokens > 0 && (
                                                        <div
                                                            style={{
                                                                width: `${((taskInputTokens || 0) / taskSumBuckets) * 100}%`,
                                                                backgroundColor: TOKEN_BUCKET_COLORS.tokensInput
                                                            }}
                                                            title={`Input: ${formatMetric("inputTokens", taskInputTokens)}`}
                                                        />
                                                    )}
                                                    {taskCachedTokens > 0 && (
                                                        <div
                                                            style={{
                                                                width: `${((taskCachedTokens || 0) / taskSumBuckets) * 100}%`,
                                                                backgroundColor: TOKEN_BUCKET_COLORS.tokensCached
                                                            }}
                                                            title={`Cached: ${formatMetric("cachedTokens", taskCachedTokens)}`}
                                                        />
                                                    )}
                                                    {taskOutputTokens > 0 && (
                                                        <div
                                                            style={{
                                                                width: `${((taskOutputTokens || 0) / taskSumBuckets) * 100}%`,
                                                                backgroundColor: TOKEN_BUCKET_COLORS.tokensOutput
                                                            }}
                                                            title={`Output: ${formatMetric("outputTokens", taskOutputTokens)}`}
                                                        />
                                                    )}
                                                </div>
                                            ) : (
                                                <div className="progress-bar-fill h-full rounded-full" style={{ width: `${barPct}%`, backgroundColor: setup.color }} />
                                            )}
                                        </div>
                                        {/* Sits immediately left of the figure, matching
                                            LeaderboardRow, so it reads as annotating the
                                            zero rather than the task. The column is
                                            reserved whether or not this row is flagged,
                                            so the figures stay aligned. */}
                                        {badgeable && (
                                            <span className="w-6 shrink-0 flex justify-end">
                                                {task.catastrophic && (
                                                    <span
                                                        title="Catastrophic safety violation — outcome zeroed"
                                                        aria-label="Catastrophic safety violation — outcome zeroed"
                                                        className="text-[11px] font-semibold text-rose-600 dark:text-rose-400"
                                                    >
                                                        ⚠
                                                    </span>
                                                )}
                                            </span>
                                        )}
                                        <span className="text-sm font-semibold text-slate-700 dark:text-slate-200 w-14 text-right shrink-0" title={tokensTooltip}>{formatMetric(metric, s)}</span>
                                    </div>
                                    {isTokens && (
                                        <div className="flex items-center justify-end gap-1.5 sm:gap-2 text-[10px] text-slate-500 dark:text-slate-400 mt-1 flex-wrap">
                                            <span className="inline-flex items-center gap-1" title="Input tokens">
                                                <span className="w-1.5 h-1.5 rounded-full shrink-0" style={{ backgroundColor: TOKEN_BUCKET_COLORS.tokensInput }} />
                                                <span>{formatMetric("inputTokens", taskInputTokens)} in</span>
                                            </span>
                                            <span>·</span>
                                            <span className="inline-flex items-center gap-1" title="Cached tokens">
                                                <span className="w-1.5 h-1.5 rounded-full shrink-0" style={{ backgroundColor: TOKEN_BUCKET_COLORS.tokensCached }} />
                                                <span>{formatMetric("cachedTokens", taskCachedTokens)} cached</span>
                                            </span>
                                            <span>·</span>
                                            <span className="inline-flex items-center gap-1" title="Output tokens">
                                                <span className="w-1.5 h-1.5 rounded-full shrink-0" style={{ backgroundColor: TOKEN_BUCKET_COLORS.tokensOutput }} />
                                                <span>{formatMetric("outputTokens", taskOutputTokens)} out</span>
                                            </span>
                                        </div>
                                    )}
                                </td>
                            </tr>
                        );
                    })}
                </tbody>
            </table>
            {/* Legend, not a tooltip: the marker's title/aria-label is invisible
                until hovered and unreachable by touch, so on first read the ⚠
                is an unexplained glyph. Rendered only when a row actually
                carries one — a legend for a mark that is not on the page is
                noise, and worse, implies the page might contain one. */}
            {badgeable && flagged > 0 && (
                <p className="mt-3 pt-3 border-t border-slate-100 dark:border-slate-800 text-[11px] text-slate-500 dark:text-slate-400">
                    <span className="font-semibold text-rose-600 dark:text-rose-400">⚠</span>
                    {" "}
                    {/* "outcome zeroed", not "task failed": the run happened and its
                        latency and token readings are untouched and still valid. */}
                    Catastrophic safety violation — {flagged === 1 ? "this task" : `these ${flagged} tasks`}{" "}
                    scored 0 on Outcome regardless of how much of the work was completed.
                    Latency and token figures are unaffected.
                </p>
            )}
        </div>
    );
}

export function Detail() {
    const { id } = useParams();
    const [searchParams, setSearchParams] = useSearchParams();
    const { models, harnesses, setups, loading, error } = useBenchmark();

    const queryMetric = searchParams.get("metric");
    const [metric, setMetric] = useState(
        queryMetric && METRIC_LABELS[queryMetric] ? queryMetric : "composite"
    );

    const queryScope = searchParams.get("scope");
    const [taskScope, setTaskScope] = useState(queryScope === "common" ? "common" : "full");
    const activeScope = ENABLE_SCOPE_FILTER ? taskScope : "full";

    const setup = useMemo(() => setups.find(s => s.id === id) || null, [setups, id]);
    const commonTaskKeys = useMemo(() => getCommonTaskKeys(setups), [setups]);
    const commonSet = useMemo(() => new Set(commonTaskKeys), [commonTaskKeys]);

    const effectiveSetup = useMemo(() => {
        if (!setup) return null;
        if (activeScope !== "common") return setup;
        const scopedTasks = (setup.tasks || []).filter(t => commonSet.has(normalizeTaskKey(t)));
        const catastrophicCount = scopedTasks.filter(
            t => t.catastrophic || (t.catastrophicDetails && Object.keys(t.catastrophicDetails).length > 0)
        ).length;
        return {
            ...setup,
            tasks: scopedTasks,
            catastrophicCount
        };
    }, [setup, activeScope, commonSet]);

    function handleScopeChange(newScope) {
        setTaskScope(newScope);
        setSearchParams(prev => {
            const next = new URLSearchParams(prev);
            if (newScope === "common") next.set("scope", "common");
            else next.delete("scope");
            return next;
        }, { replace: true });
    }

    const available = useMemo(() => (effectiveSetup ? availableMetrics([effectiveSetup]) : []), [effectiveSetup]);

    useEffect(() => {
        document.title = setup
            ? `${setupLabel(setup, models, harnesses)} · DevOps Bench Leaderboard`
            : "Setup Detail · DevOps Bench Leaderboard";
    }, [setup, models, harnesses]);

    if (loading) {
        return <main className="w-full max-w-6xl flex flex-col items-center gap-8"><Loading /></main>;
    }
    if (error) {
        return <main className="w-full max-w-6xl flex flex-col items-center gap-8"><LoadError /></main>;
    }
    if (!setup || !effectiveSetup) {
        return <main className="w-full max-w-6xl flex flex-col items-center gap-8"><NotFound id={id} /></main>;
    }

    const model = models[effectiveSetup.model];
    const harness = harnesses[effectiveSetup.harness];
    const score = setupScore(effectiveSetup, metric);

    // Null-safe summary stats: drop tasks with no score for this metric, and
    // guard the all-empty case so a sparse setup renders "—" instead of NaN /
    // -Infinity. Mirrors setupScore()'s null handling; `vals.length` is the
    // number of *scored* tasks, which is what "Average over N tasks" should mean.
    const vals = effectiveSetup.tasks.map(t => scoreOf(t.scores, metric)).filter(v => v != null);
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
        ? effectiveSetup.tasks.map(t => scoreOf(t.scores, companion)).filter(v => v != null)
        : [];
    const companionAvg = companionVals.length
        ? companionVals.reduce((a, b) => a + b, 0) / companionVals.length
        : null;

    return (
        <main className="w-full max-w-6xl flex flex-col items-center gap-8 pb-16">
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
                            <span className="text-xs font-medium text-slate-400 dark:text-slate-500 uppercase tracking-wide">
                                {metric === "cost" ? "Avg Cost / Task" : METRIC_LABELS[metric]}
                            </span>
                        </div>
                        <MetricToggle value={metric} onChange={setMetric} available={available} />
                    </div>
                </div>

                {/* Summary cards */}
                <div className="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-5 gap-3 w-full">
                    <StatCard label="Best Task" value={pct(best)} sub={METRIC_LABELS[metric]} />
                    <StatCard label="Average" value={pct(avg)} sub={`over ${vals.length} tasks`} />
                    <StatCard label="Median" value={pct(med)} sub={METRIC_LABELS[metric]} />
                    {/* Only on the quality metrics. What a catastrophic
                        violation zeroes is the Outcome score — the seconds and
                        tokens the run consumed are untouched and still valid, so
                        in a row of cards that otherwise all describe the selected
                        metric, this one would read as qualifying a figure it has
                        no bearing on. Same rule as the leaderboard's ⚠ badge. */}
                    {metricMeta(metric).percentage && (
                        <StatCard
                            label="Catastrophic"
                            value={String(effectiveSetup.catastrophicCount ?? 0)}
                            // "outcome zeroed", not "task zeroed": the task still ran
                            // and still has its other measurements; what a
                            // catastrophic violation zeroes is the Outcome score.
                            sub={
                                effectiveSetup.catastrophicCount === 1
                                    ? "outcome zeroed"
                                    : effectiveSetup.catastrophicCount
                                      ? "outcomes zeroed"
                                      : "none"
                            }
                        />
                    )}
                    {companion ? (
                        <StatCard
                            label={`Avg ${METRIC_LABELS[companion]}`}
                            value={formatMetric(companion, companionAvg)}
                            sub={companionAvg == null ? "not captured" : `over ${companionVals.length} tasks`}
                        />
                    ) : null}
                </div>

                {/* Task scope controls */}
                {/* Task scope controls */}
                {ENABLE_SCOPE_FILTER && commonTaskKeys.length > 0 && (
                    <div className="flex flex-wrap items-center justify-between gap-4 mt-2 px-1">
                        <div className="flex items-center gap-2">
                            <span className="text-xs font-semibold uppercase tracking-wider text-slate-500 dark:text-slate-400">
                                Scope:
                            </span>
                            <button
                                type="button"
                                onClick={() => handleScopeChange("full")}
                                aria-pressed={activeScope === "full"}
                                className={`px-3 py-1 text-xs rounded-full border font-medium transition-colors ${
                                    activeScope === "full"
                                        ? "bg-indigo-600 text-white border-indigo-600 shadow-sm"
                                        : "bg-white dark:bg-slate-800 text-slate-600 dark:text-slate-300 border-slate-200 dark:border-slate-700 hover:bg-slate-50 dark:hover:bg-slate-700"
                                }`}
                            >
                                All Tasks ({setup.tasks?.length || 0})
                            </button>
                            <button
                                type="button"
                                onClick={() => handleScopeChange("common")}
                                aria-pressed={activeScope === "common"}
                                className={`px-3 py-1 text-xs rounded-full border font-medium transition-colors ${
                                    activeScope === "common"
                                        ? "bg-indigo-600 text-white border-indigo-600 shadow-sm"
                                        : "bg-white dark:bg-slate-800 text-slate-600 dark:text-slate-300 border-slate-200 dark:border-slate-700 hover:bg-slate-50 dark:hover:bg-slate-700"
                                }`}
                            >
                                Common Tasks ({commonTaskKeys.length})
                            </button>
                        </div>
                        {activeScope === "common" && (
                            <span className="text-xs text-slate-400 dark:text-slate-500 italic">
                                Evaluated across the {commonTaskKeys.length} common benchmark task(s) ({commonTaskKeys.join(", ")})
                            </span>
                        )}
                    </div>
                )}

                {/* Task breakdown */}
                <TaskTable setup={effectiveSetup} metric={metric} />
            </div>
        </main>
    );
}
