// Page 2 — Run Detail
// Renders one run for a task × harness: telemetry header,
// Objectives/Safeguards with results & observed reasons, and score arithmetic.

import { useState } from "react";
import { useParams, Link } from "react-router-dom";
import curatedData from "../data/curated_tasks.json";
import { AssertsRenderer } from "../components/AssertsRenderer.jsx";
import { NotFound } from "../components/States.jsx";

export function RunDetail() {
    const { taskName, setupId } = useParams();
    const [activeTab, setActiveTab] = useState("all");

    const normalizedTaskName = taskName?.replace(/-gitops$/, "");
    const task = curatedData.tasks?.[taskName] || curatedData.tasks?.[normalizedTaskName];
    if (!task) {
        return (
            <NotFound
                message={`Task "${taskName}" was not found in the curated benchmark dataset.`}
                backText="Back to Leaderboard"
            />
        );
    }

    // Match run either by setupId or arm
    const run = task.runs?.[setupId] || Object.values(task.runs || {}).find(r => r.setupId === setupId || r.arm === setupId);

    if (!run) {
        return (
            <NotFound
                message={`Run "${setupId}" for task "${taskName}" was not found.`}
                backText={`Back to Task ${taskName}`}
                backLink={`/task/${taskName}`}
            />
        );
    }

    const { model, harness, durationSec, tokens, toolCalls, checks, scores, arithmetic } = run;

    const objectives = checks.filter(c => c.role === "objective");
    const catastrophic = checks.filter(c => c.severity === "catastrophic");
    const recoverable = checks.filter(c => c.role === "safeguard" && c.severity !== "catastrophic");

    function renderCheckTable(title, checkList, isCatastrophic = false) {
        if (!checkList) return null;

        return (
            <div className="p-6 border-t border-slate-100 dark:border-slate-800 first:border-t-0">
                <div className="flex items-center justify-between mb-4">
                    <div className="flex items-center gap-2">
                        {isCatastrophic ? (
                            <span className="w-2 h-2 rounded-full bg-rose-500 animate-pulse" />
                        ) : (
                            <span className="w-2 h-2 rounded-full bg-indigo-500" />
                        )}
                        <h2 className={`text-sm font-semibold uppercase tracking-wider ${
                            isCatastrophic ? "text-rose-700 dark:text-rose-400" : "text-slate-800 dark:text-slate-200"
                        }`}>
                            {title}
                        </h2>
                    </div>
                    <span className="text-xs font-mono text-slate-400 dark:text-slate-500">
                        {checkList.length} checks
                    </span>
                </div>

                {checkList.length === 0 ? (
                    <div className="text-xs text-slate-400 font-mono py-2">No checks declared.</div>
                ) : (
                    <div className="overflow-x-auto">
                        <table className="w-full text-left border-collapse">
                            <thead>
                                <tr className="border-b border-slate-200 dark:border-slate-800 text-[10px] font-semibold uppercase tracking-wider text-slate-400 dark:text-slate-500">
                                    <th className="pb-2.5 pr-4 w-1/4">Check</th>
                                    <th className="pb-2.5 pr-4 w-1/3">Asserts</th>
                                    <th className="pb-2.5 pr-4 w-24 text-center">Result</th>
                                    <th className="pb-2.5 w-2/5">Observed</th>
                                </tr>
                            </thead>
                            <tbody className="divide-y divide-slate-100 dark:divide-slate-800/80 text-xs">
                                {checkList.map(c => {
                                    const isPass = c.status === "pass";
                                    const isFail = c.status === "fail";
                                    const isErr = c.status === "error";

                                    return (
                                        <tr key={c.name} className="hover:bg-slate-50/50 dark:hover:bg-slate-800/20">
                                            <td className="py-3 pr-4 align-top">
                                                <span className="font-semibold text-slate-900 dark:text-slate-100 block">
                                                    {c.name}
                                                </span>
                                                <span className="text-[10px] text-slate-400 dark:text-slate-500 font-mono">
                                                    {c.mode} {c.weight ? `· ${c.weight} pts` : ""}
                                                </span>
                                            </td>
                                            <td className="py-3 pr-4 align-top">
                                                <AssertsRenderer asserts={c.asserts} />
                                            </td>
                                            <td className="py-3 pr-4 align-top text-center">
                                                <span
                                                    className={`inline-flex items-center px-2 py-0.5 rounded font-mono text-xs font-bold ${
                                                        isPass
                                                            ? "bg-emerald-50 dark:bg-emerald-950/60 text-emerald-700 dark:text-emerald-300 border border-emerald-200 dark:border-emerald-800/60"
                                                            : isFail
                                                            ? "bg-rose-50 dark:bg-rose-950/60 text-rose-700 dark:text-rose-300 border border-rose-200 dark:border-rose-800/60"
                                                            : isErr
                                                            ? "bg-amber-50 dark:bg-amber-950/60 text-amber-700 dark:text-amber-300 border border-amber-200 dark:border-amber-800/60"
                                                            : "text-slate-400"
                                                    }`}
                                                >
                                                    {isPass ? "PASS" : isFail ? "FAIL" : isErr ? "ERROR" : "–"}
                                                </span>
                                            </td>
                                            <td className="py-3 align-top font-mono text-[11px] text-slate-700 dark:text-slate-300 break-words leading-relaxed">
                                                {c.observed ? (
                                                    <div className="bg-slate-50 dark:bg-slate-950/70 p-2.5 rounded-lg border border-slate-200/60 dark:border-slate-800/80">
                                                        {c.observed}
                                                    </div>
                                                ) : (
                                                    <span className="text-slate-400 dark:text-slate-500">—</span>
                                                )}
                                            </td>
                                        </tr>
                                    );
                                })}
                            </tbody>
                        </table>
                    </div>
                )}
            </div>
        );
    }

    return (
        <main className="w-full max-w-6xl flex flex-col items-center gap-8 pb-16">
            {/* Main Header & Telemetry Card */}
            <div className="w-full bg-white dark:bg-slate-900 rounded-2xl border border-slate-200/80 dark:border-slate-800 shadow-xl shadow-slate-100 dark:shadow-none overflow-hidden">
                {/* Header banner */}
                <header className="px-6 pt-6 pb-5 border-b border-slate-100 dark:border-slate-800 bg-slate-50/50 dark:bg-slate-800/30 flex flex-col sm:flex-row sm:items-center justify-between gap-4">
                    <div>
                        <div className="flex flex-wrap items-center gap-3">
                            <h1 className="text-xl sm:text-2xl font-bold tracking-tight text-slate-900 dark:text-slate-50 font-mono">
                                <Link
                                    to={`/task/${task.name}`}
                                    className="hover:text-indigo-600 dark:hover:text-indigo-400 transition-colors"
                                    title={`View task spec and verification checks for ${task.name}`}
                                >
                                    {task.name}
                                </Link>
                            </h1>
                            <span className="px-2.5 py-0.5 rounded-full text-xs font-semibold bg-indigo-50 dark:bg-indigo-950/60 text-indigo-700 dark:text-indigo-300 border border-indigo-200 dark:border-indigo-800 font-mono">
                                {harness} · {model}
                            </span>
                        </div>
                    </div>

                    {scores.catastrophic && (
                        <div className="shrink-0 self-start sm:self-center">
                            <span className="inline-flex items-center gap-1.5 px-3 py-1 rounded-full text-xs font-bold bg-rose-50 dark:bg-rose-950/60 text-rose-700 dark:text-rose-300 border border-rose-200 dark:border-rose-900/60">
                                <span className="w-1.5 h-1.5 rounded-full bg-rose-500 animate-pulse" />
                                Catastrophic Safeguard Breached
                            </span>
                        </div>
                    )}
                </header>

                {/* Summary Stat Cards */}
                <div className="p-6 grid grid-cols-2 sm:grid-cols-4 gap-4 border-b border-slate-100 dark:border-slate-800">
                    <div className="bg-slate-50/60 dark:bg-slate-800/40 rounded-xl p-3 border border-slate-100 dark:border-slate-800/80">
                        <span className="text-[10px] font-semibold uppercase tracking-wider text-slate-400 dark:text-slate-500 block">
                            Latency
                        </span>
                        <span className="text-lg font-bold text-slate-900 dark:text-slate-100 font-mono">
                            {durationSec ? `${Number(durationSec).toFixed(1)}s` : "—"}
                        </span>
                    </div>
                    <div
                        className="bg-slate-50/60 dark:bg-slate-800/40 rounded-xl p-3 border border-slate-100 dark:border-slate-800/80"
                        title={`In: ${tokens?.input?.toLocaleString()} | Out: ${tokens?.output?.toLocaleString()} | Cached: ${tokens?.cached?.toLocaleString()}`}
                    >
                        <span className="text-[10px] font-semibold uppercase tracking-wider text-slate-400 dark:text-slate-500 block">
                            Tokens
                        </span>
                        <span className="text-lg font-bold text-slate-900 dark:text-slate-100 font-mono">
                            {tokens?.total ? `${tokens.total.toLocaleString()}` : "—"}
                        </span>
                    </div>
                    <div className="bg-slate-50/60 dark:bg-slate-800/40 rounded-xl p-3 border border-slate-100 dark:border-slate-800/80">
                        <span className="text-[10px] font-semibold uppercase tracking-wider text-slate-400 dark:text-slate-500 block">
                            Tool Calls
                        </span>
                        <span className="text-lg font-bold text-slate-900 dark:text-slate-100 font-mono">
                            {toolCalls != null ? toolCalls : "—"}
                        </span>
                    </div>
                    <div className={`rounded-xl p-3 border ${
                        scores.catastrophic
                            ? "bg-rose-50/60 dark:bg-rose-950/40 border-rose-200 dark:border-rose-900/60 text-rose-700 dark:text-rose-300"
                            : "bg-emerald-50/60 dark:bg-emerald-950/40 border-emerald-200 dark:border-emerald-900/60 text-emerald-700 dark:text-emerald-300"
                    }`}>
                        <span className="text-[10px] font-semibold uppercase tracking-wider opacity-70 block">
                            Outcome Score
                        </span>
                        <span className="text-lg font-bold font-mono">
                            {scores.outcome != null ? `${Number((scores.outcome * 100).toFixed(1))}%` : "—"}
                        </span>
                    </div>
                </div>

                {/* Score Breakdown & Verdict */}
                <div className="px-6 py-5 bg-slate-50/30 dark:bg-slate-800/20">
                    <div className="flex items-center justify-between mb-2.5">
                        <h2 className="text-xs font-semibold uppercase tracking-wider text-slate-500 dark:text-slate-400 flex items-center gap-1.5">
                            <span className="w-1.5 h-1.5 rounded-full bg-indigo-500" />
                            Score Breakdown & Verdict
                        </h2>
                        {scores.catastrophic && (
                            <span className="px-2 py-0.5 rounded text-[11px] font-bold bg-rose-100 text-rose-700 dark:bg-rose-950 dark:text-rose-300 border border-rose-200 dark:border-rose-900/60">
                                ⚠ Breach Zeroes Entire Run
                            </span>
                        )}
                    </div>
                    <div className="bg-slate-50/80 dark:bg-slate-950/60 border border-slate-200/80 dark:border-slate-800 p-4 rounded-xl flex flex-col gap-3">
                        <div className="flex items-center gap-2 pb-2.5 border-b border-slate-200/60 dark:border-slate-800/80">
                            <span className="text-[10px] text-slate-400 dark:text-slate-500 font-semibold uppercase tracking-wider">Formula:</span>
                            <code className="font-mono text-xs font-semibold text-indigo-600 dark:text-indigo-400 bg-indigo-50/70 dark:bg-indigo-950/40 px-2 py-0.5 rounded border border-indigo-100 dark:border-indigo-900/50">
                                outcome_score = cat_v × √(c × rec_v)
                            </code>
                        </div>
                        {scores.catastrophic && (
                            <div className="p-2.5 rounded-lg bg-rose-50/80 dark:bg-rose-950/40 border border-rose-200/80 dark:border-rose-900/60 text-xs text-rose-700 dark:text-rose-300 font-medium">
                                Catastrophic safeguard breached: outcome score is zeroed.
                            </div>
                        )}
                        <div className="grid grid-cols-2 sm:grid-cols-4 gap-3 text-xs font-mono">
                            <div>
                                <span className="text-slate-400 dark:text-slate-500 block text-[10px] uppercase font-semibold">Correctness (c):</span>
                                <span className="font-bold text-slate-800 dark:text-slate-200">{(scores.c ?? 0).toFixed(3)}</span>
                            </div>
                            <div>
                                <span className="text-slate-400 dark:text-slate-500 block text-[10px] uppercase font-semibold">Raw Safety Fraction:</span>
                                <span className="font-bold text-slate-800 dark:text-slate-200">{scores.raw_rec != null ? Number(scores.raw_rec).toFixed(3) : "1.000"}</span>
                            </div>
                            <div>
                                <span className="text-slate-400 dark:text-slate-500 block text-[10px] uppercase font-semibold">Rescaled Safety (rec_v):</span>
                                <span className="font-bold text-slate-800 dark:text-slate-200">{(scores.rec_v ?? 1.0).toFixed(3)}</span>
                            </div>
                            <div>
                                <span className="text-slate-400 dark:text-slate-500 block text-[10px] uppercase font-semibold">Catastrophic Gate (cat_v):</span>
                                <span className={`font-bold ${scores.catastrophic ? "text-rose-600 dark:text-rose-400" : "text-emerald-600 dark:text-emerald-400"}`}>
                                    {scores.cat_v ?? 1}
                                </span>
                            </div>
                        </div>
                    </div>
                </div>
            </div>

            {/* Rubric Checks Card with Tab Navigation */}
            <div className="w-full bg-white dark:bg-slate-900 rounded-2xl border border-slate-200/80 dark:border-slate-800 shadow-xl shadow-slate-100 dark:shadow-none overflow-hidden">
                {/* Tab Navigation Header */}
                <div className="px-6 pt-4 pb-0 border-b border-slate-100 dark:border-slate-800 bg-slate-50/50 dark:bg-slate-800/30 flex flex-wrap items-center justify-between gap-3">
                    <div role="tablist" className="flex flex-wrap gap-x-6 gap-y-2">
                        <button
                            type="button"
                            role="tab"
                            aria-selected={activeTab === "all"}
                            onClick={() => setActiveTab("all")}
                            className={`pb-3 text-xs uppercase tracking-wider font-semibold border-b-2 transition-colors ${
                                activeTab === "all"
                                    ? "border-indigo-600 text-indigo-600 dark:border-indigo-400 dark:text-indigo-400"
                                    : "border-transparent text-slate-400 hover:text-slate-700 dark:hover:text-slate-300"
                            }`}
                        >
                            All Checks ({checks.length})
                        </button>
                        <button
                            type="button"
                            role="tab"
                            aria-selected={activeTab === "objectives"}
                            onClick={() => setActiveTab("objectives")}
                            className={`pb-3 text-xs uppercase tracking-wider font-semibold border-b-2 transition-colors ${
                                activeTab === "objectives"
                                    ? "border-indigo-600 text-indigo-600 dark:border-indigo-400 dark:text-indigo-400"
                                    : "border-transparent text-slate-400 hover:text-slate-700 dark:hover:text-slate-300"
                            }`}
                        >
                            Objectives ({objectives.length})
                        </button>
                        <button
                            type="button"
                            role="tab"
                            aria-selected={activeTab === "catastrophic"}
                            onClick={() => setActiveTab("catastrophic")}
                            className={`pb-3 text-xs uppercase tracking-wider font-semibold border-b-2 transition-colors ${
                                activeTab === "catastrophic"
                                    ? "border-indigo-600 text-indigo-600 dark:border-indigo-400 dark:text-indigo-400"
                                    : "border-transparent text-slate-400 hover:text-slate-700 dark:hover:text-slate-300"
                            }`}
                        >
                            Catastrophic Safeguards ({catastrophic.length})
                        </button>
                        <button
                            type="button"
                            role="tab"
                            aria-selected={activeTab === "recoverable"}
                            onClick={() => setActiveTab("recoverable")}
                            className={`pb-3 text-xs uppercase tracking-wider font-semibold border-b-2 transition-colors ${
                                activeTab === "recoverable"
                                    ? "border-indigo-600 text-indigo-600 dark:border-indigo-400 dark:text-indigo-400"
                                    : "border-transparent text-slate-400 hover:text-slate-700 dark:hover:text-slate-300"
                            }`}
                        >
                            Recoverable Safeguards ({recoverable.length})
                        </button>
                    </div>
                </div>

                {/* Table Content */}
                <div>
                    {(activeTab === "objectives" || activeTab === "all") && (
                        renderCheckTable("Objectives", objectives)
                    )}
                    {(activeTab === "catastrophic" || activeTab === "all") && (
                        renderCheckTable("Catastrophic Safeguards", catastrophic, true)
                    )}
                    {(activeTab === "recoverable" || activeTab === "all") && (
                        renderCheckTable("Recoverable Safeguards", recoverable)
                    )}
                </div>
            </div>
        </main>
    );
}
