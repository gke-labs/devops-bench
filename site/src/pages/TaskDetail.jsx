// Page 1 — Task Detail (Option 1: Master-Detail Consolidated View)
// Displays task metadata, scenario prompt, and the cross-harness comparison matrix.
// Clicking any column header or cell in the matrix highlights that column and reveals
// the Run Inspection panel directly below the matrix on the same page.
// The Scenario Prompt and Matrix remain visible at all times.

import { useState, useEffect, useRef } from "react";
import { useParams, useSearchParams, useNavigate, useLocation, Link } from "react-router-dom";
import curatedData from "../data/curated_tasks.json";
import { AssertsRenderer, FormattedText } from "../components/AssertsRenderer.jsx";
import { NotFound } from "../components/States.jsx";
import { CheckMeta, modeTooltip } from "../components/CheckMeta.jsx";

export function TaskDetail() {
    const { taskName, setupId } = useParams();
    const [searchParams, setSearchParams] = useSearchParams();
    const navigate = useNavigate();
    const location = useLocation();

    const [promptExpanded, setPromptExpanded] = useState(false);
    const [activeTab, setActiveTab] = useState("matrix");
    const [runCheckFilter, setRunCheckFilter] = useState("all");

    // Initialize selected arm from route param (:setupId) or query param (?run=...)
    const initialArm = setupId || searchParams.get("run") || null;
    const [selectedArm, setSelectedArm] = useState(initialArm);
    const prevTaskRef = useRef(null);

    useEffect(() => {
        const isNewTask = prevTaskRef.current !== taskName;
        prevTaskRef.current = taskName;

        const targetArm = setupId || searchParams.get("run");
        if (targetArm) {
            setSelectedArm(targetArm);
            // When arriving directly at a run link, automatically scroll to the run-specific info
            const timer = setTimeout(() => {
                const el = document.getElementById("run-inspection-panel");
                if (el && typeof el.scrollIntoView === "function") {
                    el.scrollIntoView({ behavior: "smooth", block: "start" });
                }
            }, 150);
            return () => clearTimeout(timer);
        } else {
            setSelectedArm(null);
            if (isNewTask && typeof window.scrollTo === "function") {
                window.scrollTo(0, 0);
            }
        }
    }, [setupId, searchParams, taskName]);

    const normalizedTaskName = taskName?.replace(/-gitops$/, "");
    let canonicalTaskKey = null;
    let task = null;

    if (curatedData.tasks) {
        if (curatedData.tasks[taskName]) {
            canonicalTaskKey = taskName;
            task = curatedData.tasks[taskName];
        } else if (normalizedTaskName && curatedData.tasks[normalizedTaskName]) {
            canonicalTaskKey = normalizedTaskName;
            task = curatedData.tasks[normalizedTaskName];
        } else {
            const entry = Object.entries(curatedData.tasks).find(([key, t]) => {
                const folderClean = t.folder?.replace(/-gitops$/, "");
                const nameClean = t.name?.replace(/-gitops$/, "");
                return key === taskName ||
                    key === normalizedTaskName ||
                    t.folder === taskName ||
                    folderClean === normalizedTaskName ||
                    t.name === taskName ||
                    nameClean === normalizedTaskName;
            });
            if (entry) {
                canonicalTaskKey = entry[0];
                task = entry[1];
            }
        }
    }

    // Auto-upgrade legacy or folder task URLs to canonical task name
    useEffect(() => {
        if (canonicalTaskKey && taskName !== canonicalTaskKey) {
            const currentPath = location.pathname;
            const newPath = currentPath.replace(`/task/${taskName}`, `/task/${canonicalTaskKey}`);
            navigate(`${newPath}${location.search}`, { replace: true, state: location.state });
        }
    }, [taskName, canonicalTaskKey, location.pathname, location.search, location.state, navigate]);

    if (!task) {
        return (
            <NotFound
                message={`Task "${taskName}" was not found in the curated benchmark dataset.`}
                backText="Back to Tasks"
                backLink="/tasks"
            />
        );
    }

    // Match selected run
    const selectedRun = selectedArm
        ? task.runs?.[selectedArm] || Object.values(task.runs || {}).find(r => r.setupId === selectedArm || r.arm === selectedArm)
        : null;
    const canonicalArm = selectedRun?.arm || selectedArm;

    // If setupId was explicitly requested via route and not found, show not found
    if (setupId && !selectedRun) {
        return (
            <NotFound
                message={`Run "${setupId}" for task "${taskName}" was not found.`}
                backText={`Back to Task ${taskName}`}
                backLink={`/task/${taskName}`}
            />
        );
    }

    const {
        title,
        summary,
        tags = [],
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

    // Checks for the selected run
    const runChecks = selectedRun?.checks || [];
    const runObjectives = runChecks.filter(c => c.role === "objective");
    const runCatastrophic = runChecks.filter(c => c.severity === "catastrophic");
    const runRecoverable = runChecks.filter(c => c.role === "safeguard" && c.severity !== "catastrophic");
    const runScores = selectedRun?.scores || {};
    const runC = runScores.c ?? 0;
    const runRawRec = runScores.raw_rec;
    const runRecV = runScores.rec_v ?? 1;
    const runIsCatastrophic = Boolean(runScores.catastrophic);
    const runCatV = runScores.cat_v ?? (runIsCatastrophic ? 0 : 1);
    const runOutcome = runScores.outcome ?? 0;
    const runHasSafety = runRawRec != null;
    const runPassedObjectives = runObjectives.filter(c => c.status === "pass").length;

    function handleToggleArm(arm, checkName = null) {
        const query = location.search;
        const state = location.state;

        if ((selectedArm === arm || canonicalArm === arm) && !checkName) {
            setSelectedArm(null);
            navigate(`/task/${task.name}${query}`, { state, replace: true });
        } else {
            setSelectedArm(arm);
            navigate(`/task/${task.name}/run/${arm}${query}`, { state, replace: true });

            setTimeout(() => {
                if (checkName) {
                    const el = document.getElementById(`check-row-${checkName}`);
                    if (el && typeof el.scrollIntoView === "function") {
                        el.scrollIntoView({ behavior: "smooth", block: "center" });
                        return;
                    }
                }
                const panel = document.getElementById("run-inspection-panel");
                if (panel && typeof panel.scrollIntoView === "function") {
                    panel.scrollIntoView({ behavior: "smooth", block: "start" });
                }
            }, 100);
        }
    }

    function renderRunCheckTable(tableTitle, checkList, isCatastrophicTable = false) {
        if (!checkList) return null;

        return (
            <div className="p-6 border-t border-slate-100 dark:border-slate-800 first:border-t-0">
                <div className="flex items-center justify-between mb-4">
                    <div className="flex items-center gap-2">
                        {isCatastrophicTable ? (
                            <span className="w-2 h-2 rounded-full bg-rose-500 animate-pulse" />
                        ) : (
                            <span className="w-2 h-2 rounded-full bg-indigo-500" />
                        )}
                        <h2 className={`text-sm font-semibold uppercase tracking-wider ${
                            isCatastrophicTable ? "text-rose-700 dark:text-rose-400" : "text-slate-800 dark:text-slate-200"
                        }`}>
                            {tableTitle}
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
                                        <tr
                                            key={c.name}
                                            id={`check-row-${c.name}`}
                                            className="hover:bg-slate-50/50 dark:hover:bg-slate-800/20 transition-colors"
                                        >
                                            <td className="py-3 pr-4 align-top">
                                                <span className="font-semibold text-slate-900 dark:text-slate-100 block">
                                                    {c.title || c.name}
                                                </span>
                                                <CheckMeta
                                                    id={c.title && c.title !== c.name ? c.name : null}
                                                    role={c.severity || c.role}
                                                    mode={c.mode}
                                                    weight={c.weight}
                                                    group={c.group_title}
                                                    isCatastrophic={isCatastrophicTable}
                                                />
                                            </td>
                                            <td className="py-3 pr-4 align-top">
                                                <AssertsRenderer asserts={c.description || c.asserts} />
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
                                                        {(isFail || isErr) && c.failure_hint && (
                                                            <div className="mt-1.5 pt-1.5 border-t border-slate-200/60 dark:border-slate-800/80 text-rose-600 dark:text-rose-400 font-sans italic">
                                                                Hint: {c.failure_hint}
                                                            </div>
                                                        )}
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
                            {tags.map(tag => (
                                <span
                                    key={tag}
                                    className="inline-flex items-center px-2 py-0.5 rounded text-[11px] font-mono bg-slate-100 dark:bg-slate-800 text-slate-600 dark:text-slate-400"
                                >
                                    {tag}
                                </span>
                            ))}
                        </div>
                        {title && (
                            <p className="text-sm font-semibold text-slate-700 dark:text-slate-200 mt-1.5">
                                {title}
                            </p>
                        )}
                        {summary && (
                            <p className="text-xs text-slate-500 dark:text-slate-400 mt-0.5 max-w-4xl">
                                {summary}
                            </p>
                        )}
                    </div>
                </header>

                {/* Summary Stat Cards */}
                <div className="px-6 py-3 grid grid-cols-2 sm:grid-cols-4 gap-2.5 bg-white dark:bg-slate-900 border-b border-slate-100 dark:border-slate-800">
                    <div className="bg-slate-50/70 dark:bg-slate-800/40 rounded-lg px-3 py-2 border border-slate-200/70 dark:border-slate-700/60">
                        <span className="text-[10px] font-semibold uppercase tracking-wider text-slate-400 dark:text-slate-500 block leading-tight">
                            Objectives
                        </span>
                        <span className="text-sm font-bold text-slate-900 dark:text-slate-100 leading-snug mt-0.5 block">
                            {objectives.length} <span className="text-xs font-normal text-slate-400 dark:text-slate-500 ml-0.5">checks</span>
                        </span>
                    </div>
                    <div className="bg-slate-50/70 dark:bg-slate-800/40 rounded-lg px-3 py-2 border border-slate-200/70 dark:border-slate-700/60">
                        <span className="text-[10px] font-semibold uppercase tracking-wider text-rose-500 dark:text-rose-400 block leading-tight">
                            Catastrophic
                        </span>
                        <span className="text-sm font-bold text-rose-700 dark:text-rose-400 leading-snug mt-0.5 block">
                            {catastrophic.length} <span className="text-xs font-normal text-slate-400 dark:text-slate-500 ml-0.5">checks</span>
                        </span>
                    </div>
                    <div className="bg-slate-50/70 dark:bg-slate-800/40 rounded-lg px-3 py-2 border border-slate-200/70 dark:border-slate-700/60">
                        <span className="text-[10px] font-semibold uppercase tracking-wider text-slate-400 dark:text-slate-500 block leading-tight">
                            Recoverable
                        </span>
                        <span className="text-sm font-bold text-slate-900 dark:text-slate-100 leading-snug mt-0.5 block">
                            {recoverable.length} <span className="text-xs font-normal text-slate-400 dark:text-slate-500 ml-0.5">checks</span>
                        </span>
                    </div>
                    <div className="bg-slate-50/70 dark:bg-slate-800/40 rounded-lg px-3 py-2 border border-slate-200/70 dark:border-slate-700/60">
                        <span className="text-[10px] font-semibold uppercase tracking-wider text-slate-400 dark:text-slate-500 block leading-tight">
                            Cross-Verified
                        </span>
                        <span className="text-sm font-bold text-slate-900 dark:text-slate-100 leading-snug mt-0.5 block">
                            {harnesses.length} <span className="text-xs font-normal text-slate-400 dark:text-slate-500 ml-0.5">harnesses</span>
                        </span>
                    </div>
                </div>

                {/* Scenario Prompt section — always visible */}
                <div className="px-6 py-5 bg-slate-50/30 dark:bg-slate-800/20 border-b border-slate-100 dark:border-slate-800">
                    <div className="flex items-center justify-between mb-2.5">
                        <h2 className="text-xs font-semibold uppercase tracking-wider text-slate-500 dark:text-slate-400 flex items-center gap-1.5">
                            <span className="w-1.5 h-1.5 rounded-full bg-indigo-500" />
                            Scenario Prompt (Instruction)
                        </h2>
                        <button
                            type="button"
                            onClick={() => setPromptExpanded(!promptExpanded)}
                            className="text-xs font-semibold text-indigo-600 dark:text-indigo-400 hover:underline cursor-pointer"
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
                            className={`pb-3 text-xs uppercase tracking-wider font-semibold border-b-2 transition-colors cursor-pointer ${
                                activeTab === "matrix"
                                    ? "border-indigo-600 text-indigo-600 dark:border-indigo-400 dark:text-indigo-400"
                                    : "border-transparent text-slate-400 hover:text-slate-700 dark:hover:text-slate-300"
                            }`}
                        >
                            Results Matrix ({harnesses.length} harnesses)
                        </button>
                        <button
                            type="button"
                            role="tab"
                            aria-selected={activeTab === "objectives"}
                            onClick={() => setActiveTab("objectives")}
                            className={`pb-3 text-xs uppercase tracking-wider font-semibold border-b-2 transition-colors cursor-pointer ${
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
                            className={`pb-3 text-xs uppercase tracking-wider font-semibold border-b-2 transition-colors cursor-pointer ${
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
                            className={`pb-3 text-xs uppercase tracking-wider font-semibold border-b-2 transition-colors cursor-pointer ${
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
                            className={`pb-3 text-xs uppercase tracking-wider font-semibold border-b-2 transition-colors cursor-pointer ${
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
                            className={`pb-3 text-xs uppercase tracking-wider font-semibold border-b-2 transition-colors cursor-pointer ${
                                activeTab === "all"
                                    ? "border-indigo-600 text-indigo-600 dark:border-indigo-400 dark:text-indigo-400"
                                    : "border-transparent text-slate-400 hover:text-slate-700 dark:hover:text-slate-300"
                            }`}
                        >
                            All Tables
                        </button>
                    </div>
                </div>

                {/* Content */}
                <div>
                    {/* Results Across Harnesses Table */}
                    {(activeTab === "matrix" || activeTab === "all") && (
                        <div className="p-6">
                            <div className="mb-3 flex flex-col sm:flex-row sm:items-baseline justify-between gap-2">
                                <div>
                                    <h2 className="text-sm font-semibold uppercase tracking-wider text-slate-800 dark:text-slate-200">
                                        Results Across All {harnesses.length} Harnesses
                                    </h2>
                                    <p className="text-xs text-slate-500 dark:text-slate-400 mt-0.5">
                                        Click any column header or check result to inspect detailed logs and telemetry below without leaving this page.
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
                                            {harnesses.map(h => {
                                                const isSelected = canonicalArm === h.arm;
                                                return (
                                                    <th
                                                        key={h.arm}
                                                        className={`pb-2.5 px-2 text-center transition-colors rounded-t-lg ${
                                                            isSelected
                                                                ? "bg-indigo-50/90 dark:bg-indigo-950/80 text-indigo-700 dark:text-indigo-300 border-t-2 border-indigo-500"
                                                                : ""
                                                        }`}
                                                    >
                                                        <button
                                                            type="button"
                                                            onClick={() => handleToggleArm(h.arm)}
                                                            className={`block mx-auto hover:text-indigo-600 dark:hover:text-indigo-400 transition-colors cursor-pointer text-center ${
                                                                isSelected ? "text-indigo-600 dark:text-indigo-400 font-bold" : ""
                                                            }`}
                                                            title={`Click to ${isSelected ? "hide" : "view"} ${h.arm} run details`}
                                                        >
                                                            <span className="block truncate max-w-[105px] font-semibold hover:underline">
                                                                {h.short}
                                                            </span>
                                                        </button>
                                                    </th>
                                                );
                                            })}
                                        </tr>
                                    </thead>
                                    <tbody className="divide-y divide-slate-100 dark:divide-slate-800/80 text-xs">
                                        {matrix.map(row => (
                                            <tr key={row.check_name} className="hover:bg-slate-50/60 dark:hover:bg-slate-800/30">
                                                <td className="py-2.5 pr-4 align-middle">
                                                    <span className="font-medium text-slate-900 dark:text-slate-100 block">
                                                        {row.title || row.check_name}
                                                    </span>
                                                    <CheckMeta
                                                        id={row.title && row.title !== row.check_name ? row.check_name : null}
                                                        role={row.severity || row.role}
                                                        group={row.group_title}
                                                        mode={row.mode}
                                                        isCatastrophic={row.severity === "catastrophic"}
                                                    />
                                                </td>
                                                {harnesses.map(h => {
                                                    const res = row.results[h.arm];
                                                    const st = res?.status;
                                                    const isPass = st === "pass";
                                                    const isFail = st === "fail";
                                                    const isErr = st === "error";
                                                    const isSelected = canonicalArm === h.arm;

                                                    return (
                                                        <td
                                                            key={h.arm}
                                                            className={`py-2.5 px-2 text-center align-middle transition-colors ${
                                                                isSelected ? "bg-indigo-50/40 dark:bg-indigo-950/40" : ""
                                                            }`}
                                                        >
                                                            <button
                                                                type="button"
                                                                onClick={() => handleToggleArm(h.arm, row.check_name)}
                                                                title={`Inspect ${h.short} run: ${res?.reason || st}`}
                                                                className={`inline-flex items-center justify-center font-mono text-[10px] font-bold uppercase tracking-wide px-2 py-0.5 rounded transition-transform hover:scale-110 cursor-pointer ${
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
                                                            </button>
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
                                                const isSelected = canonicalArm === h.arm;

                                                return (
                                                    <td
                                                        key={h.arm}
                                                        className={`py-3 px-2 text-center align-middle font-mono text-xs transition-colors rounded-b-lg ${
                                                            isSelected ? "bg-indigo-50/60 dark:bg-indigo-950/60" : ""
                                                        }`}
                                                    >
                                                        {outcome != null ? (
                                                            <button
                                                                type="button"
                                                                onClick={() => handleToggleArm(h.arm)}
                                                                className={`font-mono text-xs font-bold hover:underline cursor-pointer ${
                                                                    isCat ? "text-rose-600 dark:text-rose-400" : "text-slate-900 dark:text-slate-100"
                                                                }`}
                                                                title={`Inspect ${h.arm} run details`}
                                                            >
                                                                {Number((outcome * 100).toFixed(1))}%
                                                            </button>
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

                            {/* Option 1: Master-Detail Panel Directly Below the Matrix on the Same Webpage */}
                            {selectedRun && (
                                <div id="run-inspection-panel" className="mt-8 pt-6 border-t-2 border-indigo-200/80 dark:border-indigo-900/60 scroll-mt-20">
                                    <div className="rounded-xl border border-slate-200 dark:border-slate-800 bg-white dark:bg-slate-900 overflow-hidden shadow-sm">
                                        {/* Inspection Panel Top Bar */}
                                        <div className="px-6 py-3.5 bg-slate-50/70 dark:bg-slate-800/40 border-b border-slate-100 dark:border-slate-800 flex flex-col sm:flex-row sm:items-center justify-between gap-3">
                                            <div className="flex items-center gap-2.5">
                                                <span className="text-sm font-semibold text-slate-800 dark:text-slate-200">
                                                    Run details:
                                                </span>
                                                <select
                                                    id="harness-select"
                                                    aria-label="Select harness run to inspect"
                                                    value={canonicalArm || ""}
                                                    onChange={(e) => handleToggleArm(e.target.value)}
                                                    className="text-xs font-mono font-medium bg-white dark:bg-slate-900 border border-slate-200 dark:border-slate-700 rounded-lg px-2.5 py-1 text-slate-800 dark:text-slate-200 focus:outline-none focus:ring-1 focus:ring-indigo-500 cursor-pointer shadow-sm"
                                                >
                                                    {harnesses.map(h => (
                                                        <option key={h.arm} value={h.arm}>
                                                            {h.arm.replace("_", " · ")}
                                                        </option>
                                                    ))}
                                                </select>

                                                {selectedRun.scores?.catastrophic && (
                                                    <span className="px-2 py-0.5 rounded-full text-xs font-medium bg-rose-50 text-rose-700 dark:bg-rose-950/60 dark:text-rose-300 border border-rose-200 dark:border-rose-900/60">
                                                        ⚠ Catastrophic breach
                                                    </span>
                                                )}
                                            </div>

                                            <div className="flex items-center gap-2 shrink-0">
                                                <button
                                                    type="button"
                                                    onClick={() => handleToggleArm(selectedArm)}
                                                    className="inline-flex items-center gap-1 px-2.5 py-1 rounded-md text-xs font-medium bg-white dark:bg-slate-800 text-slate-600 dark:text-slate-300 hover:text-slate-900 dark:hover:text-slate-100 border border-slate-200 dark:border-slate-700 transition-colors cursor-pointer"
                                                    title="Close run details"
                                                >
                                                    Close ✕
                                                </button>
                                            </div>
                                        </div>

                                        {/* Telemetry */}
                                        <div className="px-6 py-3 border-b border-slate-100 dark:border-slate-800">
                                            <div className="flex items-center justify-between mb-2">
                                                <h3 className="text-xs font-semibold uppercase tracking-wider text-slate-500 dark:text-slate-400">
                                                    Telemetry
                                                </h3>
                                            </div>
                                            <div className="grid grid-cols-1 sm:grid-cols-3 gap-2.5">
                                                <div className="bg-slate-50/70 dark:bg-slate-800/40 rounded-lg px-3 py-2 border border-slate-200/70 dark:border-slate-700/60">
                                                    <span className="text-[10px] font-semibold uppercase tracking-wider text-slate-400 dark:text-slate-500 block leading-tight">
                                                        <span>Latency</span>
                                                    </span>
                                                    <span className="text-sm font-bold font-mono text-slate-900 dark:text-slate-100 leading-snug mt-0.5 block">
                                                        {selectedRun.durationSec ? `${Number(selectedRun.durationSec).toFixed(1)}s` : "—"}
                                                    </span>
                                                </div>
                                                <div
                                                    className="bg-slate-50/70 dark:bg-slate-800/40 rounded-lg px-3 py-2 border border-slate-200/70 dark:border-slate-700/60"
                                                    title={`In: ${selectedRun.tokens?.input?.toLocaleString()} | Out: ${selectedRun.tokens?.output?.toLocaleString()} | Cached: ${selectedRun.tokens?.cached?.toLocaleString()}`}
                                                >
                                                    <span className="text-[10px] font-semibold uppercase tracking-wider text-slate-400 dark:text-slate-500 block leading-tight">
                                                        <span>Tokens</span>
                                                    </span>
                                                    <span className="text-sm font-bold font-mono text-slate-900 dark:text-slate-100 leading-snug mt-0.5 block">
                                                        {selectedRun.tokens?.total ? `${selectedRun.tokens.total.toLocaleString()}` : "—"}
                                                    </span>
                                                </div>
                                                <div className="bg-slate-50/70 dark:bg-slate-800/40 rounded-lg px-3 py-2 border border-slate-200/70 dark:border-slate-700/60">
                                                    <span className="text-[10px] font-semibold uppercase tracking-wider text-slate-400 dark:text-slate-500 block leading-tight">
                                                        <span>Tool Calls</span>
                                                    </span>
                                                    <span className="text-sm font-bold font-mono text-slate-900 dark:text-slate-100 leading-snug mt-0.5 block">
                                                        {selectedRun.toolCalls != null ? selectedRun.toolCalls : "—"}
                                                    </span>
                                                </div>
                                            </div>
                                        </div>

                                        {/* Score Breakdown & Verdict */}
                                        <div className="px-6 py-3 border-b border-slate-100 dark:border-slate-800">
                                            <div className="flex items-center justify-between mb-2">
                                                <h3 className="text-xs font-semibold uppercase tracking-wider text-slate-500 dark:text-slate-400">
                                                    Score Breakdown & Verdict
                                                </h3>
                                                {runIsCatastrophic && (
                                                    <span className="text-xs font-medium text-rose-600 dark:text-rose-400">
                                                        ⚠ Catastrophic breach zeroes run
                                                    </span>
                                                )}
                                            </div>

                                            {runIsCatastrophic && (
                                                <div className="mb-2 text-xs text-rose-600 dark:text-rose-400">
                                                    Catastrophic safeguard breached: outcome score is zeroed.
                                                    {runScores.catastrophic_reason && (
                                                        <span className="block font-mono text-[11px] text-rose-500 mt-0.5">
                                                            IntegrityCatastrophic — {runScores.catastrophic_reason}
                                                        </span>
                                                    )}
                                                </div>
                                            )}

                                            <div className="grid grid-cols-2 sm:grid-cols-4 gap-2.5">
                                                <div className="bg-slate-50/70 dark:bg-slate-800/40 rounded-lg px-3 py-2 border border-slate-200/70 dark:border-slate-700/60">
                                                    <span className="text-[10px] font-semibold uppercase tracking-wider text-slate-400 dark:text-slate-500 block leading-tight">
                                                        Correctness (c)
                                                    </span>
                                                    <span className="text-sm font-bold font-mono text-slate-900 dark:text-slate-100 leading-snug mt-0.5 block">
                                                        {runC.toFixed(3)}
                                                    </span>
                                                </div>
                                                <div className="bg-slate-50/70 dark:bg-slate-800/40 rounded-lg px-3 py-2 border border-slate-200/70 dark:border-slate-700/60">
                                                    <span className="text-[10px] font-semibold uppercase tracking-wider text-slate-400 dark:text-slate-500 block leading-tight">
                                                        Rescaled Safety (rec_v)
                                                    </span>
                                                    <span className="text-sm font-bold font-mono text-slate-900 dark:text-slate-100 leading-snug mt-0.5 block">
                                                        {runHasSafety ? runRecV.toFixed(3) : "1.000"}
                                                    </span>
                                                </div>
                                                <div className="bg-slate-50/70 dark:bg-slate-800/40 rounded-lg px-3 py-2 border border-slate-200/70 dark:border-slate-700/60">
                                                    <span className="text-[10px] font-semibold uppercase tracking-wider text-slate-400 dark:text-slate-500 block leading-tight">
                                                        Catastrophic Gate (cat_v)
                                                    </span>
                                                    <span className={`text-sm font-bold font-mono leading-snug mt-0.5 block ${runIsCatastrophic ? "text-rose-600 dark:text-rose-400" : "text-emerald-600 dark:text-emerald-400"}`}>
                                                        {runCatV}
                                                    </span>
                                                </div>
                                                <div className="bg-slate-50/70 dark:bg-slate-800/40 rounded-lg px-3 py-2 border border-slate-200/70 dark:border-slate-700/60">
                                                    <span className="text-[10px] font-semibold uppercase tracking-wider text-slate-400 dark:text-slate-500 block leading-tight">
                                                        Outcome
                                                    </span>
                                                    <div className="flex items-baseline gap-1 mt-0.5 leading-snug">
                                                        <span className="text-sm font-bold font-mono text-slate-900 dark:text-slate-100">
                                                            {(runOutcome * 100).toFixed(1)}%
                                                        </span>
                                                        <span className="text-[10px] font-mono text-slate-400 dark:text-slate-500 truncate" title={runHasSafety ? "cat_v × √(c × rec_v)" : "cat_v × c"}>
                                                            ({runHasSafety ? "cat_v × √(c × rec_v)" : "cat_v × c"})
                                                        </span>
                                                    </div>
                                                </div>
                                            </div>
                                        </div>

                                        {/* Run Checks Tabs */}
                                        <div className="px-6 pt-4 pb-0 border-b border-slate-100 dark:border-slate-800 bg-slate-50/50 dark:bg-slate-800/30 flex flex-wrap items-center justify-between gap-3">
                                            <div role="tablist" className="flex flex-wrap gap-x-6 gap-y-2">
                                                <button
                                                    type="button"
                                                    role="tab"
                                                    aria-selected={runCheckFilter === "all"}
                                                    onClick={() => setRunCheckFilter("all")}
                                                    className={`pb-3 text-xs uppercase tracking-wider font-semibold border-b-2 transition-colors cursor-pointer ${
                                                        runCheckFilter === "all"
                                                            ? "border-indigo-600 text-indigo-600 dark:border-indigo-400 dark:text-indigo-400"
                                                            : "border-transparent text-slate-400 hover:text-slate-700 dark:hover:text-slate-300"
                                                    }`}
                                                >
                                                    All Checks ({runChecks.length})
                                                </button>
                                                <button
                                                    type="button"
                                                    role="tab"
                                                    aria-selected={runCheckFilter === "objectives"}
                                                    onClick={() => setRunCheckFilter("objectives")}
                                                    className={`pb-3 text-xs uppercase tracking-wider font-semibold border-b-2 transition-colors cursor-pointer ${
                                                        runCheckFilter === "objectives"
                                                            ? "border-indigo-600 text-indigo-600 dark:border-indigo-400 dark:text-indigo-400"
                                                            : "border-transparent text-slate-400 hover:text-slate-700 dark:hover:text-slate-300"
                                                    }`}
                                                >
                                                    Objectives ({runObjectives.length})
                                                </button>
                                                <button
                                                    type="button"
                                                    role="tab"
                                                    aria-selected={runCheckFilter === "catastrophic"}
                                                    onClick={() => setRunCheckFilter("catastrophic")}
                                                    className={`pb-3 text-xs uppercase tracking-wider font-semibold border-b-2 transition-colors cursor-pointer ${
                                                        runCheckFilter === "catastrophic"
                                                            ? "border-indigo-600 text-indigo-600 dark:border-indigo-400 dark:text-indigo-400"
                                                            : "border-transparent text-slate-400 hover:text-slate-700 dark:hover:text-slate-300"
                                                    }`}
                                                >
                                                    Catastrophic Safeguards ({runCatastrophic.length})
                                                </button>
                                                <button
                                                    type="button"
                                                    role="tab"
                                                    aria-selected={runCheckFilter === "recoverable"}
                                                    onClick={() => setRunCheckFilter("recoverable")}
                                                    className={`pb-3 text-xs uppercase tracking-wider font-semibold border-b-2 transition-colors cursor-pointer ${
                                                        runCheckFilter === "recoverable"
                                                            ? "border-indigo-600 text-indigo-600 dark:border-indigo-400 dark:text-indigo-400"
                                                            : "border-transparent text-slate-400 hover:text-slate-700 dark:hover:text-slate-300"
                                                    }`}
                                                >
                                                    Recoverable Safeguards ({runRecoverable.length})
                                                </button>
                                            </div>
                                        </div>

                                        {/* Run Check Content */}
                                        <div>
                                            {(runCheckFilter === "objectives" || runCheckFilter === "all") && (
                                                renderRunCheckTable("Objectives", runObjectives)
                                            )}
                                            {(runCheckFilter === "catastrophic" || runCheckFilter === "all") && (
                                                renderRunCheckTable("Catastrophic Safeguards", runCatastrophic, true)
                                            )}
                                            {(runCheckFilter === "recoverable" || runCheckFilter === "all") && (
                                                renderRunCheckTable("Recoverable Safeguards", runRecoverable)
                                            )}
                                        </div>
                                    </div>
                                </div>
                            )}
                        </div>
                    )}

                    {/* Table 1: Objectives Spec */}
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
                                                        {c.title || c.name}
                                                    </span>
                                                    <CheckMeta
                                                        id={c.title && c.title !== c.name ? c.name : null}
                                                        role={c.role || "objective"}
                                                        group={c.group_title}
                                                    />
                                                </td>
                                                <td className="py-3 pr-4 align-top">
                                                    <AssertsRenderer asserts={c.description || c.asserts} />
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
                                                    <span
                                                        className="inline-flex items-center px-2 py-0.5 rounded text-[11px] font-mono bg-slate-100 dark:bg-slate-800 text-slate-700 dark:text-slate-300 cursor-help"
                                                        title={modeTooltip(c.mode)}
                                                    >
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

                    {/* Table 2: Catastrophic Safeguards Spec */}
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
                                                            {c.title || c.name}
                                                        </span>
                                                        <CheckMeta
                                                            id={c.title && c.title !== c.name ? c.name : null}
                                                            role="catastrophic"
                                                            group={c.group_title}
                                                            isCatastrophic={true}
                                                        />
                                                    </td>
                                                    <td className="py-3 pr-4 align-top">
                                                        <AssertsRenderer asserts={c.description || c.asserts} />
                                                    </td>
                                                    <td className="py-3 align-top">
                                                        <span
                                                            className="inline-flex items-center px-2 py-0.5 rounded text-[11px] font-mono bg-rose-100/70 dark:bg-rose-950 text-rose-700 dark:text-rose-300 cursor-help"
                                                            title={modeTooltip(c.mode)}
                                                        >
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

                    {/* Table 3: Recoverable Safeguards Spec */}
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
                                                            {c.title || c.name}
                                                        </span>
                                                        <CheckMeta
                                                            id={c.title && c.title !== c.name ? c.name : null}
                                                            role="safeguard"
                                                            group={c.group_title}
                                                        />
                                                    </td>
                                                    <td className="py-3 pr-4 align-top">
                                                        <AssertsRenderer asserts={c.description || c.asserts} />
                                                    </td>
                                                    <td className="py-3 align-top">
                                                        <span
                                                            className="inline-flex items-center px-2 py-0.5 rounded text-[11px] font-mono bg-slate-100 dark:bg-slate-800 text-slate-700 dark:text-slate-300 cursor-help"
                                                            title={modeTooltip(c.mode)}
                                                        >
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

                    {/* Table: Environment Spec */}
                    {(activeTab === "environment" || activeTab === "all") && (
                        <div className="p-6 border-t border-slate-100 dark:border-slate-800 first:border-t-0">
                            <h2 className="text-sm font-semibold uppercase tracking-wider text-slate-800 dark:text-slate-200 mb-4">
                                Infrastructure Environment Spec
                            </h2>
                            <div className="space-y-2.5 font-mono text-xs max-w-xl">
                                {environment && Object.keys(environment).length > 0 ? (
                                    Object.entries(environment).map(([k, v]) => {
                                        const formattedVal =
                                            v && typeof v === "object" && !Array.isArray(v)
                                                ? Object.entries(v)
                                                      .map(([subK, subV]) => `${subK}=${subV}`)
                                                      .join(", ")
                                                : Array.isArray(v)
                                                ? v.join(", ")
                                                : String(v);
                                        return (
                                            <div key={k} className="flex items-center justify-between py-1 border-b border-slate-100 dark:border-slate-800/60 last:border-0 gap-4">
                                                <span className="text-slate-500 dark:text-slate-400 shrink-0">{k}</span>
                                                <span className="font-semibold text-slate-800 dark:text-slate-200 text-right break-all">{formattedVal}</span>
                                            </div>
                                        );
                                    })
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
