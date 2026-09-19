// Page 1 — Task Detail
// Styled to match the Leaderboard design scheme:
// Container with rounded-2xl border, header banner with breadcrumb and stats,
// collapsible scenario card, and rounded data tables with tabs and scoring footer.

import { useState } from "react";
import { useParams, Link } from "react-router-dom";
import curatedData from "../data/curated_tasks.json";
import { AssertsRenderer, FormattedText } from "../components/AssertsRenderer.jsx";
import { NotFound } from "../components/States.jsx";

export function TaskDetail() {
    const { taskName } = useParams();
    const [promptExpanded, setPromptExpanded] = useState(false);
    const [activeTab, setActiveTab] = useState("matrix");

    const normalizedTaskName = taskName?.replace(/-gitops$/, "");
    const task = curatedData.tasks?.[taskName] || curatedData.tasks?.[normalizedTaskName];

    if (!task) {
        return (
            <NotFound
                message={`Task "${taskName}" was not found in the curated benchmark dataset.`}
                backText="Back to Tasks"
                backLink="/tasks"
            />
        );
    }

    const {
        title,
        category,
        prompt,
        environment,
        objectives = [],
        catastrophic = [],
        recoverable = [],
        harnesses = [],
        matrix = [],
        harness_scores = {}
    } = task;

    return (
        <main className="w-full max-w-6xl flex flex-col items-center gap-8 pb-16">
            {/* Main Header & Scenario Card */}
            <div className="w-full bg-white dark:bg-slate-900 rounded-2xl border border-slate-200/80 dark:border-slate-800 shadow-xl shadow-slate-100 dark:shadow-none overflow-hidden">
                {/* Header banner */}
                <header className="px-6 pt-6 pb-5 border-b border-slate-100 dark:border-slate-800 bg-slate-50/50 dark:bg-slate-800/30 flex flex-col sm:flex-row sm:items-center justify-between gap-4">
                    <div>
                        <div className="flex flex-wrap items-center gap-3">
                            <h1 className="text-xl sm:text-2xl font-bold tracking-tight text-slate-900 dark:text-slate-100 font-mono">
                                {task.name}
                            </h1>
                            <span className="inline-flex items-center px-2.5 py-0.5 rounded-full text-xs font-semibold bg-indigo-50 dark:bg-indigo-950/50 text-indigo-700 dark:text-indigo-300 border border-indigo-200/80 dark:border-indigo-800/60 font-mono">
                                {category || "Kubernetes"}
                            </span>
                        </div>
                    </div>
                </header>

                {/* Summary Stat Cards */}
                <div className="px-6 py-4 grid grid-cols-2 sm:grid-cols-4 gap-3 bg-white dark:bg-slate-900 border-b border-slate-100 dark:border-slate-800">
                    <div className="bg-slate-50/60 dark:bg-slate-800/40 rounded-xl p-3 border border-slate-100 dark:border-slate-800/80">
                        <span className="text-[10px] font-semibold uppercase tracking-wider text-slate-400 dark:text-slate-500 block">
                            Objectives
                        </span>
                        <span className="text-lg font-bold text-slate-900 dark:text-slate-100">
                            {objectives.length} <span className="text-xs font-normal text-slate-400">checks</span>
                        </span>
                    </div>
                    <div className="bg-slate-50/60 dark:bg-slate-800/40 rounded-xl p-3 border border-slate-100 dark:border-slate-800/80">
                        <span className="text-[10px] font-semibold uppercase tracking-wider text-rose-500 block">
                            Catastrophic
                        </span>
                        <span className="text-lg font-bold text-rose-700 dark:text-rose-400">
                            {catastrophic.length} <span className="text-xs font-normal text-slate-400">checks</span>
                        </span>
                    </div>
                    <div className="bg-slate-50/60 dark:bg-slate-800/40 rounded-xl p-3 border border-slate-100 dark:border-slate-800/80">
                        <span className="text-[10px] font-semibold uppercase tracking-wider text-slate-400 dark:text-slate-500 block">
                            Recoverable
                        </span>
                        <span className="text-lg font-bold text-slate-900 dark:text-slate-100">
                            {recoverable.length} <span className="text-xs font-normal text-slate-400">checks</span>
                        </span>
                    </div>
                    <div className="bg-slate-50/60 dark:bg-slate-800/40 rounded-xl p-3 border border-slate-100 dark:border-slate-800/80">
                        <span className="text-[10px] font-semibold uppercase tracking-wider text-slate-400 dark:text-slate-500 block">
                            Cross-Verified
                        </span>
                        <span className="text-lg font-bold text-slate-900 dark:text-slate-100">
                            {harnesses.length} <span className="text-xs font-normal text-slate-400">harnesses</span>
                        </span>
                    </div>
                </div>

                {/* Scenario Prompt section */}
                <div className="px-6 py-5 bg-slate-50/30 dark:bg-slate-800/20 border-b border-slate-100 dark:border-slate-800">
                    <div className="flex items-center justify-between mb-2.5">
                        <h2 className="text-xs font-semibold uppercase tracking-wider text-slate-500 dark:text-slate-400 flex items-center gap-1.5">
                            <span className="w-1.5 h-1.5 rounded-full bg-indigo-500" />
                            Scenario Prompt (Instruction)
                        </h2>
                        <button
                            type="button"
                            onClick={() => setPromptExpanded(!promptExpanded)}
                            className="text-xs font-semibold text-indigo-600 dark:text-indigo-400 hover:underline"
                        >
                            {promptExpanded ? "Collapse" : "Expand"}
                        </button>
                    </div>
                    <div
                        className={`font-mono text-xs text-slate-700 dark:text-slate-300 whitespace-pre-wrap leading-relaxed bg-white dark:bg-slate-950 p-4 rounded-xl border border-slate-200/80 dark:border-slate-800/80 transition-all ${
                            promptExpanded ? "max-h-none" : "max-h-48 overflow-y-auto"
                        }`}
                    >
                        <FormattedText text={prompt || "No prompt recorded."} />
                    </div>
                </div>

                {/* Tab Navigation Header */}
                <div className="px-6 pt-4 pb-0 border-b border-slate-100 dark:border-slate-800 bg-slate-50/50 dark:bg-slate-800/30 flex flex-wrap items-center justify-between gap-3">
                    <div role="tablist" className="flex flex-wrap gap-x-6 gap-y-2">
                        <button
                            type="button"
                            role="tab"
                            aria-selected={activeTab === "matrix"}
                            onClick={() => setActiveTab("matrix")}
                            className={`pb-3 text-xs uppercase tracking-wider font-semibold border-b-2 transition-colors ${
                                activeTab === "matrix"
                                    ? "border-indigo-600 text-indigo-600 dark:border-indigo-400 dark:text-indigo-400"
                                    : "border-transparent text-slate-400 hover:text-slate-700 dark:hover:text-slate-300"
                            }`}
                        >
                            Results Matrix ({harnesses.length} arms)
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
                        <button
                            type="button"
                            role="tab"
                            aria-selected={activeTab === "environment"}
                            onClick={() => setActiveTab("environment")}
                            className={`pb-3 text-xs uppercase tracking-wider font-semibold border-b-2 transition-colors ${
                                activeTab === "environment"
                                    ? "border-indigo-600 text-indigo-600 dark:border-indigo-400 dark:text-indigo-400"
                                    : "border-transparent text-slate-400 hover:text-slate-700 dark:hover:text-slate-300"
                            }`}
                        >
                            Environment
                        </button>
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
                            All Tables
                        </button>
                    </div>
                </div>

                {/* Table Content */}
                <div>
                    {/* Table 4: Results Across 9 Harnesses */}
                    {(activeTab === "matrix" || activeTab === "all") && (
                        <div className="p-6">
                            <div className="mb-3 flex flex-col sm:flex-row sm:items-baseline justify-between gap-2">
                                <div>
                                    <h2 className="text-sm font-semibold uppercase tracking-wider text-slate-800 dark:text-slate-200">
                                        Results Across All 9 Harnesses
                                    </h2>
                                    <p className="text-xs text-slate-500 dark:text-slate-400 mt-0.5">
                                        Down a column reveals failure root cause; across a row reveals check discrimination. Click any cell to view run details.
                                    </p>
                                </div>
                                <span className="text-xs font-mono text-slate-400 dark:text-slate-500 shrink-0">
                                    {matrix.length} checks · {harnesses.length} harnesses
                                </span>
                            </div>

                            <div className="overflow-x-auto mt-3">
                                <table className="w-full text-left border-collapse min-w-[960px]">
                                    <thead>
                                        <tr className="border-b border-slate-200 dark:border-slate-800 text-[10px] font-semibold uppercase tracking-wider text-slate-400 dark:text-slate-500">
                                            <th className="pb-2.5 pr-4 min-w-[240px]">Check</th>
                                            {harnesses.map(h => (
                                                <th key={h.arm} className="pb-2.5 px-2 text-center">
                                                    <Link
                                                        to={`/task/${task.name}/run/${h.arm}`}
                                                        className="hover:text-indigo-600 dark:hover:text-indigo-400 block truncate max-w-[100px] transition-colors"
                                                        title={`View ${h.arm} run`}
                                                    >
                                                        {h.short}
                                                    </Link>
                                                </th>
                                            ))}
                                        </tr>
                                    </thead>
                                    <tbody className="divide-y divide-slate-100 dark:divide-slate-800/80 text-xs">
                                        {matrix.map(row => (
                                            <tr key={row.check_name} className="hover:bg-slate-50/60 dark:hover:bg-slate-800/30">
                                                <td className="py-2.5 pr-4 align-middle">
                                                    <span className="font-medium text-slate-900 dark:text-slate-100 block">
                                                        {row.check_name}
                                                    </span>
                                                    <span className="text-[10px] text-slate-400 dark:text-slate-500 font-mono">
                                                        {row.severity || row.role}
                                                    </span>
                                                </td>
                                                {harnesses.map(h => {
                                                    const res = row.results[h.arm];
                                                    const st = res?.status;
                                                    const isPass = st === "pass";
                                                    const isFail = st === "fail";
                                                    const isErr = st === "error";

                                                    return (
                                                        <td key={h.arm} className="py-2.5 px-2 text-center align-middle">
                                                            <Link
                                                                to={`/task/${task.name}/run/${h.arm}`}
                                                                title={res?.reason || st}
                                                                className={`inline-flex items-center justify-center font-mono text-[10px] font-bold uppercase tracking-wide px-2 py-0.5 rounded transition-transform hover:scale-105 ${
                                                                    isPass
                                                                        ? "bg-emerald-50 dark:bg-emerald-950/60 text-emerald-700 dark:text-emerald-300 border border-emerald-200 dark:border-emerald-800/60"
                                                                        : isFail
                                                                        ? "bg-rose-50 dark:bg-rose-950/60 text-rose-700 dark:text-rose-300 border border-rose-200 dark:border-rose-800/60"
                                                                        : isErr
                                                                        ? "bg-amber-50 dark:bg-amber-950/60 text-amber-700 dark:text-amber-300 border border-amber-200 dark:border-amber-800/60"
                                                                        : "text-slate-400"
                                                                }`}
                                                            >
                                                                {isPass ? "PASS" : isFail ? "FAIL" : isErr ? "ERR" : "—"}
                                                            </Link>
                                                        </td>
                                                    );
                                                })}
                                            </tr>
                                        ))}

                                        {/* Summary row: Outcome Score */}
                                        <tr className="bg-slate-50/80 dark:bg-slate-950/60 font-bold border-t-2 border-slate-200 dark:border-slate-800">
                                            <td className="py-3 pr-4 text-xs uppercase tracking-wider text-slate-800 dark:text-slate-200">
                                                Outcome Score
                                            </td>
                                            {harnesses.map(h => {
                                                const scoreData = harness_scores[h.arm];
                                                const outcome = scoreData?.outcomeScore;
                                                const isCat = scoreData?.catastrophic;
                                                return (
                                                    <td key={h.arm} className="py-3 px-2 text-center align-middle font-mono text-xs">
                                                        {outcome != null ? (
                                                            <span className={isCat ? "text-rose-600 dark:text-rose-400" : "text-slate-900 dark:text-slate-100"}>
                                                                {Number((outcome * 100).toFixed(1))}%
                                                            </span>
                                                        ) : (
                                                            <span className="text-slate-400">—</span>
                                                        )}
                                                    </td>
                                                );
                                            })}
                                        </tr>
                                    </tbody>
                                </table>
                            </div>
                        </div>
                    )}

                    {/* Table 1: Objectives */}
                    {(activeTab === "objectives" || activeTab === "all") && (
                        <div className="p-6 border-t border-slate-100 dark:border-slate-800 first:border-t-0">
                            <div className="flex items-center justify-between mb-4">
                                <h2 className="text-sm font-semibold uppercase tracking-wider text-slate-800 dark:text-slate-200">
                                    Objectives — Produce Correctness Score (c)
                                </h2>
                                <span className="text-xs text-slate-400 dark:text-slate-500 font-mono">
                                    {objectives.length} checks
                                </span>
                            </div>
                            <div className="overflow-x-auto">
                                <table className="w-full text-left border-collapse">
                                    <thead>
                                        <tr className="border-b border-slate-200 dark:border-slate-800 text-[10px] font-semibold uppercase tracking-wider text-slate-400 dark:text-slate-500">
                                            <th className="pb-2.5 pr-4 w-1/4">Check</th>
                                            <th className="pb-2.5 pr-4 w-1/2">Asserts</th>
                                            <th className="pb-2.5 pr-4 w-24">Weight</th>
                                            <th className="pb-2.5 w-28">Mode</th>
                                        </tr>
                                    </thead>
                                    <tbody className="divide-y divide-slate-100 dark:divide-slate-800 text-xs">
                                        {objectives.map(c => (
                                            <tr key={c.name} className="hover:bg-slate-50/50 dark:hover:bg-slate-800/20">
                                                <td className="py-3 pr-4 align-top">
                                                    <span className="font-semibold text-slate-900 dark:text-slate-100 block">
                                                        {c.name}
                                                    </span>
                                                    <span className="text-[10px] text-slate-400 dark:text-slate-500 font-mono">
                                                        {c.type}
                                                    </span>
                                                </td>
                                                <td className="py-3 pr-4 align-top">
                                                    <AssertsRenderer asserts={c.asserts} />
                                                </td>
                                                <td className="py-3 pr-4 align-top font-mono text-xs">
                                                    <span className="font-semibold text-slate-800 dark:text-slate-200">{c.weight} pts</span>
                                                    {c.weight_pct != null && (
                                                        <span className="text-[10px] text-slate-400 dark:text-slate-500 block">
                                                            ({c.weight_pct}%)
                                                        </span>
                                                    )}
                                                </td>
                                                <td className="py-3 align-top">
                                                    <span className="inline-flex items-center px-2 py-0.5 rounded text-[11px] font-mono bg-slate-100 dark:bg-slate-800 text-slate-700 dark:text-slate-300">
                                                        {c.mode}
                                                    </span>
                                                </td>
                                            </tr>
                                        ))}
                                    </tbody>
                                </table>
                            </div>
                        </div>
                    )}

                    {/* Table 2: Catastrophic Safeguards */}
                    {(activeTab === "catastrophic" || activeTab === "all") && (
                        <div className="p-6 border-t border-slate-100 dark:border-slate-800 first:border-t-0">
                            <div className="flex items-center justify-between mb-4">
                                <div className="flex items-center gap-2">
                                    <span className="w-2 h-2 rounded-full bg-rose-500 animate-pulse" />
                                    <h2 className="text-sm font-semibold uppercase tracking-wider text-rose-700 dark:text-rose-400">
                                        Catastrophic Safeguards — Zero Entire Outcome If Breached
                                    </h2>
                                </div>
                                <span className="text-xs text-rose-500 font-mono">
                                    {catastrophic.length} checks
                                </span>
                            </div>
                            {catastrophic.length === 0 ? (
                                <div className="text-xs text-slate-400 font-mono py-2">No catastrophic safeguards declared.</div>
                            ) : (
                                <div className="overflow-x-auto">
                                    <table className="w-full text-left border-collapse">
                                        <thead>
                                            <tr className="border-b border-rose-100 dark:border-rose-950/60 text-[10px] font-semibold uppercase tracking-wider text-rose-400">
                                                <th className="pb-2.5 pr-4 w-1/3">Check</th>
                                                <th className="pb-2.5 pr-4 w-1/2">Asserts</th>
                                                <th className="pb-2.5 w-28">Mode</th>
                                            </tr>
                                        </thead>
                                        <tbody className="divide-y divide-rose-50/60 dark:divide-rose-950/30">
                                            {catastrophic.map(c => (
                                                <tr key={c.name} className="hover:bg-rose-50/30 dark:hover:bg-rose-950/10">
                                                    <td className="py-3 pr-4 align-top">
                                                        <span className="font-semibold text-xs text-rose-950 dark:text-rose-200 block">
                                                            {c.name}
                                                        </span>
                                                    </td>
                                                    <td className="py-3 pr-4 align-top">
                                                        <AssertsRenderer asserts={c.asserts} />
                                                    </td>
                                                    <td className="py-3 align-top">
                                                        <span className="inline-flex items-center px-2 py-0.5 rounded text-[11px] font-mono bg-rose-100/70 dark:bg-rose-950 text-rose-700 dark:text-rose-300">
                                                            {c.mode}
                                                        </span>
                                                    </td>
                                                </tr>
                                            ))}
                                        </tbody>
                                    </table>
                                </div>
                            )}
                        </div>
                    )}

                    {/* Table 3: Recoverable Safeguards */}
                    {(activeTab === "recoverable" || activeTab === "all") && (
                        <div className="p-6 border-t border-slate-100 dark:border-slate-800 first:border-t-0">
                            <div className="flex items-center justify-between mb-4">
                                <h2 className="text-sm font-semibold uppercase tracking-wider text-slate-800 dark:text-slate-200">
                                    Recoverable Safeguards — Rescaled Safety Drag (Floor 0.1)
                                </h2>
                                <span className="text-xs text-slate-400 dark:text-slate-500 font-mono">
                                    {recoverable.length} checks
                                </span>
                            </div>
                            {recoverable.length === 0 ? (
                                <div className="text-xs text-slate-400 font-mono py-2">No recoverable safeguards declared.</div>
                            ) : (
                                <div className="overflow-x-auto">
                                    <table className="w-full text-left border-collapse">
                                        <thead>
                                            <tr className="border-b border-slate-200 dark:border-slate-800 text-[10px] font-semibold uppercase tracking-wider text-slate-400 dark:text-slate-500">
                                                <th className="pb-2.5 pr-4 w-1/3">Check</th>
                                                <th className="pb-2.5 pr-4 w-1/2">Asserts</th>
                                                <th className="pb-2.5 w-28">Mode</th>
                                            </tr>
                                        </thead>
                                        <tbody className="divide-y divide-slate-100 dark:divide-slate-800">
                                            {recoverable.map(c => (
                                                <tr key={c.name} className="hover:bg-slate-50/50 dark:hover:bg-slate-800/20">
                                                    <td className="py-3 pr-4 align-top">
                                                        <span className="font-semibold text-xs text-slate-900 dark:text-slate-100 block">
                                                            {c.name}
                                                        </span>
                                                    </td>
                                                    <td className="py-3 pr-4 align-top">
                                                        <AssertsRenderer asserts={c.asserts} />
                                                    </td>
                                                    <td className="py-3 align-top">
                                                        <span className="inline-flex items-center px-2 py-0.5 rounded text-[11px] font-mono bg-slate-100 dark:bg-slate-800 text-slate-700 dark:text-slate-300">
                                                            {c.mode}
                                                        </span>
                                                    </td>
                                                </tr>
                                            ))}
                                        </tbody>
                                    </table>
                                </div>
                            )}
                        </div>
                    )}

                    {/* Environment Tab */}
                    {(activeTab === "environment" || activeTab === "all") && (
                        <div className="p-6 border-t border-slate-100 dark:border-slate-800 first:border-t-0">
                            <h2 className="text-sm font-semibold uppercase tracking-wider text-slate-800 dark:text-slate-200 mb-4">
                                Infrastructure Environment Spec
                            </h2>
                            <div className="space-y-2.5 font-mono text-xs max-w-xl">
                                {environment && Object.keys(environment).length > 0 ? (
                                    Object.entries(environment).map(([k, v]) => (
                                        <div key={k} className="flex items-center justify-between py-1 border-b border-slate-100 dark:border-slate-800/60 last:border-0">
                                            <span className="text-slate-500 dark:text-slate-400">{k}</span>
                                            <span className="font-semibold text-slate-800 dark:text-slate-200">{String(v)}</span>
                                        </div>
                                    ))
                                ) : (
                                    <div className="text-slate-400 dark:text-slate-500">No environment metadata declared.</div>
                                )}
                            </div>
                        </div>
                    )}
                </div>


            </div>
        </main>
    );
}
