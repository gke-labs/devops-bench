// Performance and efficiency charts:
// 1. Outcome vs Efficiency comparison plot (Score vs Time, Score vs Cost, Score vs Tokens),
//    with subtabs for Average (mean per task) vs Total (suite total).
// 2. Task Spread & Consistency box plot (adjustable over metrics, collapsed by default).

import { useMemo, useState } from "react";
import { EfficiencyScatter } from "./EfficiencyScatter.jsx";
import { ConsistencyChart } from "./ConsistencyChart.jsx";
import {
    CHART_METRICS,
    METRIC_LABELS,
    availableMetrics,
    isLowerBetter,
    metricShortLabel
} from "../lib/vocab.js";

const SCATTER_H = "h-[30rem]";

const VS_TABS = [
    { key: "latency", label: "Score vs Time", subject: "execution time" },
    { key: "cost", label: "Score vs Cost", subject: "cost" },
    { key: "tokens", label: "Score vs Tokens", subject: "tokens" }
];

const AGG_OPTIONS = [
    { key: "mean", label: "Average" },
    { key: "total", label: "Total" }
];

const BOX_METRIC_CANDIDATES = [
    "composite",
    "correctness",
    "recoverableSafety",
    "latency",
    "cost",
    "tokens"
];

function Segmented({ value, onChange, options, ariaLabel }) {
    return (
        <div role="group" aria-label={ariaLabel} className="inline-flex flex-wrap p-0.5 bg-slate-100 dark:bg-slate-800 rounded-lg text-[11px]">
            {options.map(opt => {
                const active = opt.key === value;
                return (
                    <button
                        key={opt.key}
                        type="button"
                        onClick={() => !opt.disabled && onChange(opt.key)}
                        disabled={opt.disabled}
                        aria-pressed={active}
                        title={opt.title}
                        className={`px-2.5 py-1 font-medium rounded-md whitespace-nowrap transition-all duration-200 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-indigo-500 disabled:cursor-not-allowed ${
                            active
                                ? "bg-white dark:bg-slate-700 text-slate-800 dark:text-slate-100 shadow-sm"
                                : opt.disabled
                                    ? "text-slate-300 dark:text-slate-600"
                                    : "text-slate-600 dark:text-slate-300 hover:text-slate-800 dark:hover:text-slate-100"
                        }`}
                    >
                        {opt.label}
                    </button>
                );
            })}
        </div>
    );
}

export function ChartsPanel({ setups, models, harnesses }) {
    const [colorBy, setColorBy] = useState("model");
    const [vsMetric, setVsMetric] = useState("latency");
    const [aggregation, setAggregation] = useState("mean");
    const [boxMetric, setBoxMetric] = useState("composite");
    const [isBoxPlotOpen, setIsBoxPlotOpen] = useState(false);

    const hasTokenData = useMemo(() => {
        const tokenKeys = ["tokens", "tokensInput", "inputTokens", "tokensOutput", "outputTokens", "tokensCached", "cachedTokens"];
        return setups.some(s =>
            (s.tasks || []).some(t => tokenKeys.some(k => t.scores?.[k] != null)) ||
            (s.history || []).some(h => tokenKeys.some(k => h.scores?.[k] != null))
        );
    }, [setups]);

    const available = useMemo(() => {
        const list = availableMetrics(setups, CHART_METRICS);
        if (hasTokenData && !list.includes("tokens")) {
            return [...list, "tokens"];
        }
        return list;
    }, [setups, hasTokenData]);

    const availableVsTabs = useMemo(() =>
        VS_TABS.filter(t => available.includes(t.key)),
        [available]
    );

    const activeVsMetric = availableVsTabs.some(t => t.key === vsMetric)
        ? vsMetric
        : (availableVsTabs[0]?.key ?? "latency");

    const activeVsTabObj = VS_TABS.find(t => t.key === activeVsMetric) ?? VS_TABS[0];

    const boxMetricOptions = useMemo(() =>
        BOX_METRIC_CANDIDATES
            .filter(m => available.includes(m))
            .map(m => ({
                key: m,
                label: m === "latency" ? "Time" : metricShortLabel(m)
            })),
        [available]
    );

    const activeBoxMetric = boxMetricOptions.some(opt => opt.key === boxMetric)
        ? boxMetric
        : (boxMetricOptions[0]?.key ?? "composite");

    const colorControl = (
        <Segmented
            value={colorBy}
            onChange={setColorBy}
            ariaLabel="Color dots by"
            options={[
                { key: "model", label: "Color: model", title: "Color dots by model" },
                { key: "harness", label: "Color: harness", title: "Color dots by harness" }
            ]}
        />
    );

    const aggControl = (
        <Segmented
            value={aggregation}
            onChange={setAggregation}
            ariaLabel="Aggregation view"
            options={AGG_OPTIONS}
        />
    );

    const vsTabsControl = (
        <Segmented
            value={activeVsMetric}
            onChange={setVsMetric}
            ariaLabel="Comparison tabs"
            options={availableVsTabs}
        />
    );

    const vsSubtitle = `Outcome score vs. ${aggregation === "total" ? "total " : "average "}${activeVsTabObj.subject} ${aggregation === "total" ? "across all tasks" : "per task"} · Up and to the left is better`;

    return (
        <div className="w-full flex flex-col gap-6">
            {/* Plot 1: Comparison Plot ("vs") */}
            {availableVsTabs.length > 0 && (
                <section
                    aria-label="Performance and efficiency comparison"
                    className="w-full bg-white dark:bg-slate-900 rounded-2xl border border-slate-200/80 dark:border-slate-800 shadow-xl shadow-slate-100 dark:shadow-none p-6 flex flex-col gap-4"
                >
                    <div className="flex flex-col gap-3">
                        <div className="flex flex-wrap items-center justify-between gap-3">
                            <div className="flex items-center gap-2">
                                <h2 className="text-xs font-semibold text-indigo-600 dark:text-indigo-400 uppercase tracking-wider flex items-center gap-2">
                                    <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24" aria-hidden="true">
                                        <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M13 10V3L4 14h7v7l9-11h-7z" />
                                    </svg>
                                    Score vs. Efficiency
                                </h2>
                            </div>
                            {availableVsTabs.length > 1 && vsTabsControl}
                        </div>

                        <div className="flex flex-wrap items-center justify-between gap-3 pt-2 border-t border-slate-100 dark:border-slate-800">
                            <div>
                                <h3 className="text-sm font-semibold text-slate-800 dark:text-slate-100">
                                    {activeVsTabObj.label}
                                </h3>
                                <p className="text-[11px] italic text-slate-500 dark:text-slate-400 mt-0.5">
                                    {vsSubtitle}
                                </p>
                            </div>
                            <div className="flex flex-wrap items-center gap-3">
                                <div className="flex items-center gap-1.5 text-[11px] font-medium text-slate-500 dark:text-slate-400">
                                    <span>Mode:</span>
                                    {aggControl}
                                </div>
                                {colorControl}
                            </div>
                        </div>
                    </div>

                    <div className={SCATTER_H}>
                        <EfficiencyScatter
                            setups={setups}
                            xMetric={activeVsMetric}
                            yMetric="composite"
                            xAggregate={aggregation}
                            models={models}
                            harnesses={harnesses}
                            colorBy={colorBy}
                            ariaLabel={`${activeVsTabObj.label} (${aggregation === "total" ? "Total" : "Average"})`}
                            caption={`${activeVsTabObj.label} for each setup`}
                        />
                    </div>
                </section>
            )}

            {/* Plot 2: Box Plot (Task Spread & Consistency) */}
            <section
                aria-label="Task spread and consistency"
                className="w-full bg-white dark:bg-slate-900 rounded-2xl border border-slate-200/80 dark:border-slate-800 shadow-xl shadow-slate-100 dark:shadow-none p-6 flex flex-col"
            >
                <button
                    type="button"
                    onClick={() => setIsBoxPlotOpen(prev => !prev)}
                    aria-expanded={isBoxPlotOpen}
                    aria-controls="box-plot-content"
                    className="w-full flex items-center justify-between gap-4 text-left focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-indigo-500 rounded-lg p-1 transition-colors"
                >
                    <div className="flex items-center gap-3">
                        <div className="w-8 h-8 rounded-lg bg-sky-50 dark:bg-sky-500/10 flex items-center justify-center text-sky-600 dark:text-sky-400 shrink-0">
                            <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24" aria-hidden="true">
                                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M9 19v-6a2 2 0 00-2-2H5a2 2 0 00-2 2v6a2 2 0 002 2h2a2 2 0 002-2zm0 0V9a2 2 0 012-2h2a2 2 0 012 2v10m-6 0a2 2 0 002 2h2a2 2 0 002-2m0 0V5a2 2 0 012-2h2a2 2 0 012 2v14a2 2 0 01-2 2h-2a2 2 0 01-2-2z" />
                            </svg>
                        </div>
                        <div>
                            <h2 className="text-xs font-semibold text-slate-800 dark:text-slate-100 uppercase tracking-wider">
                                Task Performance Spread (Box Plot)
                            </h2>
                            <p className="text-[11px] text-slate-500 dark:text-slate-400 mt-0.5">
                                Distribution across individual tasks (min, 25th percentile, median, 75th percentile, max)
                            </p>
                        </div>
                    </div>
                    <span className="px-3 py-1 text-xs font-medium rounded-full bg-slate-100 dark:bg-slate-800 text-slate-700 dark:text-slate-300 hover:bg-slate-200 dark:hover:bg-slate-700 transition-colors shrink-0">
                        {isBoxPlotOpen ? "Collapse Box Plot ▲" : "Expand Box Plot ▼"}
                    </span>
                </button>

                {isBoxPlotOpen && (
                    <div id="box-plot-content" className="mt-6 pt-6 border-t border-slate-100 dark:border-slate-800 flex flex-col gap-4">
                        <div className="flex flex-wrap items-center justify-between gap-3">
                            <div>
                                <h3 className="text-sm font-semibold text-slate-800 dark:text-slate-100">
                                    {METRIC_LABELS[activeBoxMetric]} Spread Across Tasks
                                </h3>
                                <p className="text-[11px] italic text-slate-500 dark:text-slate-400 mt-0.5">
                                    Box shows middle 50% of tasks, line marks median, whiskers reach min and max · {isLowerBetter(activeBoxMetric) ? "Lower values and tighter boxes indicate consistency" : "Higher values and tighter boxes indicate consistency"}
                                </p>
                            </div>
                            <div className="flex items-center gap-1.5">
                                <span className="text-[11px] font-medium text-slate-500 dark:text-slate-400">Metric:</span>
                                <Segmented
                                    value={activeBoxMetric}
                                    onChange={setBoxMetric}
                                    options={boxMetricOptions}
                                    ariaLabel="Box plot metric"
                                />
                            </div>
                        </div>

                        <ConsistencyChart
                            setups={setups}
                            metric={activeBoxMetric}
                            models={models}
                            harnesses={harnesses}
                            ariaLabel={`Box plot of ${METRIC_LABELS[activeBoxMetric]} across tasks`}
                            caption={`Task distribution of ${METRIC_LABELS[activeBoxMetric]} per setup`}
                        />
                    </div>
                )}
            </section>
        </div>
    );
}
