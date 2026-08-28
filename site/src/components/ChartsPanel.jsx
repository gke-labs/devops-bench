// The charts below the leaderboard table.
//
// Laid out the way Artificial Analysis lays out its coding-agent page: one
// scrolling column of titled sections, each a chart with a one-line italic
// subtitle that says what the numbers are and which direction is good. No tabs.
// A tab hides the comparison a reader did not know to look for — the cost story
// only lands next to the token story, and both only land next to the score.
//
// Each spend metric gets two views, in this order: the ranked bar chart (how
// much), then the same metric scattered against the outcome score (whether it
// bought anything). Sections whose metric is unmeasured are omitted rather than
// drawn empty.
//
// Every chart reads the FILTERED setups, so the filter bar at the top of the
// page drives the plots as well as the table.

import { Fragment, useMemo, useState } from "react";
import { EfficiencyScatter } from "./EfficiencyScatter.jsx";
import { RankedBarChart } from "./RankedBarChart.jsx";
import { TokenBreakdownChart } from "./TokenBreakdownChart.jsx";
import { TaskDistributionChart } from "./TaskDistributionChart.jsx";
import { HarnessSavingsChart } from "./HarnessSavingsChart.jsx";
import { scatterPoints, canUseLogScale } from "../lib/charts.js";
import {
    CHART_METRICS,
    METRIC_GROUPS,
    METRIC_LABELS,
    availableMetrics,
    isLowerBetter,
    metricDescription
} from "../lib/vocab.js";

// The spend axes paired with the outcome score, in the order a reader meets
// them: what it cost in money, then in wall clock. Tokens come first and are
// handled on their own, because their "how much" view is the bucket breakdown
// rather than a single ranked total.
const SPEND_SECTIONS = [
    {
        metric: "cost",
        barTitle: "Cost per Task",
        barSubtitle: "Mean pay-per-token API cost per task, priced from each run's own token buckets at the provider's published rates",
        scatterTitle: "Outcome Index vs. Cost per Task"
    },
    {
        metric: "latency",
        barTitle: "Time per Task",
        barSubtitle: "Mean agent wall-clock time per task, excluding scoring and harness startup",
        scatterTitle: "Outcome Index vs. Execution Time"
    }
];

const SCATTER_SUBTITLE =
    "One dot per model × harness pairing — never a model or a harness on its own, since the same model costs differently in a different runner. Up and to the left is better. The dashed line is the Pareto frontier: everything below it is beaten outright.";

/** "· Higher is better" / "· Lower is better", from the metric vocabulary. */
function withDirection(text, metric) {
    return `${text} · ${isLowerBetter(metric) ? "Lower" : "Higher"} is better`;
}

// --- small shared controls ---------------------------------------------------

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

// Grouped metric dropdown. A <select> rather than more pill buttons: the custom
// section offers every metric in the vocabulary, and seventeen pills is a wall.
function MetricSelect({ id, label, value, onChange, available }) {
    return (
        <label htmlFor={id} className="flex items-center gap-1.5 text-[11px] font-medium text-slate-500 dark:text-slate-400">
            {label}
            <select
                id={id}
                value={value}
                onChange={e => onChange(e.target.value)}
                title={metricDescription(value)}
                className="px-2 py-1 rounded-md bg-slate-100 dark:bg-slate-800 text-slate-700 dark:text-slate-200 text-[11px] font-medium border-0 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-indigo-500"
            >
                {METRIC_GROUPS.map(group => {
                    const options = group.metrics.filter(m => available.includes(m));
                    if (!options.length) return null;
                    return (
                        <optgroup key={group.key} label={group.label}>
                            {options.map(m => <option key={m} value={m}>{METRIC_LABELS[m]}</option>)}
                        </optgroup>
                    );
                })}
            </select>
        </label>
    );
}

function Checkbox({ id, label, checked, onChange, disabled, title }) {
    return (
        <label
            htmlFor={id}
            title={title}
            className={`flex items-center gap-1.5 text-[11px] font-medium ${disabled ? "text-slate-300 dark:text-slate-600 cursor-not-allowed" : "text-slate-500 dark:text-slate-400"}`}
        >
            <input
                id={id}
                type="checkbox"
                checked={checked}
                disabled={disabled}
                onChange={e => onChange(e.target.checked)}
                className="rounded border-slate-300 dark:border-slate-600 text-indigo-500 focus-visible:ring-indigo-500 disabled:cursor-not-allowed"
            />
            {label}
        </label>
    );
}

// One titled chart. The subtitle is not decoration: without it a reader has to
// infer from the axis whether a long bar is good news.
function Section({ title, subtitle, controls, children }) {
    return (
        <section className="mt-10 first:mt-0 pt-10 first:pt-0 border-t first:border-t-0 border-slate-100 dark:border-slate-800">
            <div className="flex flex-wrap items-start justify-between gap-3 mb-4">
                <div className="min-w-0">
                    <h3 className="text-sm font-semibold text-slate-800 dark:text-slate-100">{title}</h3>
                    <p className="text-[11px] italic text-slate-500 dark:text-slate-400 mt-0.5 max-w-3xl">{subtitle}</p>
                </div>
                {controls}
            </div>
            {children}
        </section>
    );
}

// --- panel -------------------------------------------------------------------

export function ChartsPanel({ setups, models, harnesses }) {
    const [colorBy, setColorBy] = useState("model");
    const [harnessMetric, setHarnessMetric] = useState("cost");
    const [spreadMetric, setSpreadMetric] = useState("composite");
    const [customX, setCustomX] = useState("tokens");
    const [customY, setCustomY] = useState("composite");
    const [logX, setLogX] = useState(false);
    const [logY, setLogY] = useState(false);

    const available = useMemo(() => availableMetrics(setups, CHART_METRICS), [setups]);

    // Log scales cannot draw a zero or a negative, and Chart.js drops such points
    // without comment. Offer the toggle only when every plotted value survives.
    const customPoints = useMemo(
        () => scatterPoints(setups, customX, customY),
        [setups, customX, customY]
    );
    const logXOk = canUseLogScale(customPoints.map(p => p.x));
    const logYOk = canUseLogScale(customPoints.map(p => p.y));

    const activeSpreadMetric = available.includes(spreadMetric) ? spreadMetric : (available[0] ?? spreadMetric);
    const activeHarnessMetric = available.includes(harnessMetric) ? harnessMetric : (available[0] ?? harnessMetric);

    // The colour toggle is a LEGEND ENCODING, not a ranking: it groups the dots
    // so a cluster is visible. It applies to every scatter at once, because a
    // reader comparing two charts should not have to re-set it on each.
    const colorControl = (
        <Segmented
            value={colorBy}
            onChange={setColorBy}
            ariaLabel="Color dots by"
            options={[
                { key: "model", label: "Color: model", title: "Color the dots by model. Each dot is still one model × harness pairing — this only groups them." },
                { key: "harness", label: "Color: harness", title: "Color the dots by harness. Each dot is still one model × harness pairing — this only groups them." }
            ]}
        />
    );

    const scatterAgainstOutcome = metric => (
        <div className="h-[26rem]">
            <EfficiencyScatter
                setups={setups}
                xMetric={metric}
                yMetric="composite"
                models={models}
                harnesses={harnesses}
                colorBy={colorBy}
                ariaLabel={`Outcome score against ${METRIC_LABELS[metric].toLowerCase()} for each setup, with the Pareto frontier`}
                caption={`Outcome score versus ${METRIC_LABELS[metric].toLowerCase()} per setup`}
            />
        </div>
    );

    return (
        <section className="w-full bg-white dark:bg-slate-900 rounded-2xl border border-slate-200/80 dark:border-slate-800 shadow-xl shadow-slate-100 dark:shadow-none p-6 flex flex-col">
            <h2 className="text-xs font-semibold text-slate-500 dark:text-slate-400 uppercase tracking-wider flex items-center gap-2 mb-8">
                <svg className="w-4 h-4 text-amber-500 dark:text-amber-400" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M13 10V3L4 14h7v7l9-11h-7z" />
                </svg>
                Performance &amp; Efficiency
            </h2>

            <Section
                title="Outcome Index"
                subtitle={withDirection("Composite outcome score across every graded task: correctness weighted by recoverable safety", "composite")}
            >
                <RankedBarChart
                    setups={setups}
                    metric="composite"
                    models={models}
                    harnesses={harnesses}
                    ariaLabel="Outcome score per setup, ranked"
                    caption="Outcome score by setup"
                />
            </Section>

            <Section
                title="Harness Comparison"
                subtitle={withDirection(`${METRIC_LABELS[activeHarnessMetric]} for one model run on several harnesses, augmentation held constant — the only comparison that isolates the runner. Models that ran on a single harness are omitted`, activeHarnessMetric)}
                controls={
                    <MetricSelect
                        id="harness-metric"
                        label="Metric"
                        value={activeHarnessMetric}
                        onChange={setHarnessMetric}
                        available={available}
                    />
                }
            >
                <HarnessSavingsChart
                    setups={setups}
                    metric={activeHarnessMetric}
                    models={models}
                    harnesses={harnesses}
                    ariaLabel={`${METRIC_LABELS[activeHarnessMetric]} per harness, with the model and augmentation held constant`}
                    caption={`${METRIC_LABELS[activeHarnessMetric]} by harness for each model`}
                />
            </Section>

            {available.includes("tokens") && (
                <>
                    <Section
                        title="Token Usage per Task"
                        subtitle={withDirection("Mean input, cache read, cache write, reasoning and output tokens per task. Cache reads cost about a tenth of fresh input and reasoning bills at the output rate, so two equal totals can differ several-fold in price", "tokens")}
                    >
                        <TokenBreakdownChart
                            setups={setups}
                            models={models}
                            harnesses={harnesses}
                            ariaLabel="Mean tokens per task per setup, stacked by billed bucket"
                            caption="Token usage by bucket per setup"
                        />
                    </Section>

                    <Section title="Outcome Index vs. Total Tokens" subtitle={SCATTER_SUBTITLE}>
                        {scatterAgainstOutcome("tokens")}
                    </Section>
                </>
            )}

            {SPEND_SECTIONS.filter(s => available.includes(s.metric)).map(section => (
                <Fragment key={section.metric}>
                    <Section title={section.barTitle} subtitle={withDirection(section.barSubtitle, section.metric)}>
                        <RankedBarChart
                            setups={setups}
                            metric={section.metric}
                            models={models}
                            harnesses={harnesses}
                            ariaLabel={`${METRIC_LABELS[section.metric]} per setup, ranked`}
                            caption={`${METRIC_LABELS[section.metric]} by setup`}
                        />
                    </Section>
                    <Section
                        title={section.scatterTitle}
                        subtitle={SCATTER_SUBTITLE}
                        controls={section.metric === SPEND_SECTIONS[0].metric ? colorControl : undefined}
                    >
                        {scatterAgainstOutcome(section.metric)}
                    </Section>
                </Fragment>
            ))}

            <Section
                title="Per-Task Spread"
                subtitle={`One dot per task at each setup's latest run. Everything above is a mean; this is the spread it hides — two setups with the same mean ${METRIC_LABELS[activeSpreadMetric].toLowerCase()} are not the same product if one of them is erratic`}
                controls={
                    <MetricSelect
                        id="spread-metric"
                        label="Metric"
                        value={activeSpreadMetric}
                        onChange={setSpreadMetric}
                        available={available}
                    />
                }
            >
                <TaskDistributionChart
                    setups={setups}
                    metric={activeSpreadMetric}
                    models={models}
                    harnesses={harnesses}
                    ariaLabel={`Per-task ${METRIC_LABELS[activeSpreadMetric].toLowerCase()} for each setup`}
                    caption={`Per-task ${METRIC_LABELS[activeSpreadMetric].toLowerCase()} by setup`}
                />
            </Section>

            {/* Folded away, unlike everything above it. Any two of ~17 metrics is
                270-odd plots and almost none of them mean anything — "cache write
                tokens versus pass@1" is a question nobody has — but the long tail
                should still be reachable. */}
            <details className="mt-10 pt-10 border-t border-slate-100 dark:border-slate-800 group">
                <summary className="text-sm font-semibold text-slate-800 dark:text-slate-100 cursor-pointer marker:text-slate-400 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-indigo-500 rounded">
                    Plot any two metrics
                </summary>
                <p className="text-[11px] italic text-slate-500 dark:text-slate-400 mt-1 mb-4 max-w-3xl">
                    One dot per setup. No frontier line: &ldquo;non-dominated&rdquo; only means something when both axes have a better direction the reader agrees with, and an arbitrary pair does not. Log scales help when values span orders of magnitude; they are unavailable on an axis where a plotted value is zero.
                </p>
                <div className="flex flex-wrap items-center gap-x-4 gap-y-2 mb-4">
                    <MetricSelect id="custom-x" label="X" value={customX} onChange={setCustomX} available={available} />
                    <Checkbox
                        id="custom-log-x"
                        label="log X"
                        checked={logX && logXOk}
                        disabled={!logXOk}
                        onChange={setLogX}
                        title={logXOk ? "Logarithmic x-axis" : "A plotted value is zero or negative, which a log axis cannot show"}
                    />
                    <MetricSelect id="custom-y" label="Y" value={customY} onChange={setCustomY} available={available} />
                    <Checkbox
                        id="custom-log-y"
                        label="log Y"
                        checked={logY && logYOk}
                        disabled={!logYOk}
                        onChange={setLogY}
                        title={logYOk ? "Logarithmic y-axis" : "A plotted value is zero or negative, which a log axis cannot show"}
                    />
                </div>
                <div className="h-[26rem]">
                    <EfficiencyScatter
                        setups={setups}
                        xMetric={customX}
                        yMetric={customY}
                        models={models}
                        harnesses={harnesses}
                        colorBy={colorBy}
                        showFrontier={false}
                        logX={logX && logXOk}
                        logY={logY && logYOk}
                        ariaLabel={`${METRIC_LABELS[customY]} against ${METRIC_LABELS[customX]} for each setup`}
                        caption={`${METRIC_LABELS[customY]} versus ${METRIC_LABELS[customX]} per setup`}
                    />
                </div>
            </details>
        </section>
    );
}
