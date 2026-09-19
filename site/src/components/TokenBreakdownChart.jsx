// Stacked token breakdown: one horizontal bar per setup, split into the five
// billed buckets.
//
// The `tokens` column on the leaderboard is a single number, and a single number
// hides the thing that actually drives cost. Two setups can report the same
// total while one paid list price for all of it and the other served 90% from
// cache at a tenth of the rate — a 5x cost difference the total cannot show.
// This chart is that split.
//
// `task` narrows it to a single task's own numbers instead of the mean across
// the suite. A mean flattens the thing worth seeing: one long-context task can
// carry a setup's whole cache-write bill, and averaged over twelve tasks it
// looks like a mild overhead everywhere rather than one expensive task.
//
// `aggregate` picks mean or total across those tasks. They answer different
// questions — "what does a task cost me" against "what did the suite cost" —
// and they do not rank setups identically, because the total is sensitive to
// how many tasks a setup actually reported and the mean is not.

import { useMemo } from "react";
import { Bar } from "react-chartjs-2";
import {
    Chart,
    BarElement,
    CategoryScale,
    LinearScale,
    Tooltip,
    Legend
} from "chart.js";
import { setupLabel, setupValue } from "../lib/accessors.js";
import {
    METRIC_LABELS,
    TOKEN_BUCKET_COLORS,
    TOKEN_BUCKET_METRICS,
    formatMetric
} from "../lib/vocab.js";
import { setupIconsPlugin, iconGutter } from "../lib/chartIcons.js";
import { useIsDark } from "../hooks/useIsDark.js";

Chart.register(BarElement, CategoryScale, LinearScale, Tooltip, Legend);

// Row height per setup. A stacked bar chart with a fixed canvas height squeezes
// bars to hairlines once there are more than a handful of setups, so the canvas
// grows with the data instead.
const ROW_PX = 34;
const CHROME_PX = 90;

export function TokenBreakdownChart({ setups, models, harnesses, task, aggregate = "mean", ariaLabel, caption }) {
    const isDark = useIsDark();
    const textColor = isDark ? "#94a3b8" : "#64748b";
    const gridColor = isDark ? "#1e293b" : "#f1f5f9";

    // Only setups that broke their usage down at all. One that reports a bare
    // total would otherwise draw an empty row, reading as "used no tokens"
    // rather than "did not say where they went". Under a task filter that also
    // drops the setups which never ran that task, rather than showing them empty.
    //
    // Sorted by the length of the bar it will draw — the sum of the buckets, not
    // the reported total, so the shortest bar is always the top row. Fewest
    // tokens first, matching every other chart's best-first order.
    const plotted = useMemo(() => {
        const bucketsOf = setup => Object.fromEntries(
            TOKEN_BUCKET_METRICS.map(m => [m, setupValue(setup, m, { task, aggregate })])
        );
        return setups
            .map(setup => ({ setup, buckets: bucketsOf(setup) }))
            .filter(row => TOKEN_BUCKET_METRICS.some(m => row.buckets[m] != null))
            .map(row => ({ ...row, total: TOKEN_BUCKET_METRICS.reduce((sum, m) => sum + (row.buckets[m] ?? 0), 0) }))
            .sort((a, b) => a.total - b.total);
    }, [setups, task, aggregate]);

    const labels = useMemo(
        () => plotted.map(row => setupLabel(row.setup, models, harnesses)),
        [plotted, models, harnesses]
    );

    const data = useMemo(() => ({
        labels,
        datasets: TOKEN_BUCKET_METRICS.map(metric => ({
            label: METRIC_LABELS[metric],
            // A bucket this setup never reported contributes 0 to the stack —
            // it cannot contribute null, and the tooltip below distinguishes the
            // two so the bar's silence isn't read as a measurement.
            data: plotted.map(row => row.buckets[metric] ?? 0),
            backgroundColor: TOKEN_BUCKET_COLORS[metric],
            borderWidth: 0,
            borderRadius: 2,
            metricKey: metric
        }))
    }), [labels, plotted]);

    const options = useMemo(() => ({
        indexAxis: "y",
        responsive: true,
        maintainAspectRatio: false,
        interaction: { mode: "index", axis: "y", intersect: false },
        layout: { padding: { left: iconGutter(2) } },
        plugins: {
            setupIcons: { slots: 2, rowAt: (_tick, i) => plotted[i] && { model: models[plotted[i].setup.model], harness: harnesses[plotted[i].setup.harness] } },
            legend: {
                display: true,
                position: "bottom",
                labels: { color: textColor, usePointStyle: true, boxWidth: 8, padding: 16, font: { size: 11, weight: "500" } }
            },
            tooltip: {
                callbacks: {
                    label: ctx => {
                        const metric = ctx.dataset.metricKey;
                        const raw = plotted[ctx.dataIndex]?.buckets[metric];
                        // "not reported" and "reported as zero" are different
                        // facts about the harness, and the stack draws both as
                        // nothing.
                        return ` ${ctx.dataset.label}: ${raw == null ? "not reported" : formatMetric(metric, raw)}`;
                    },
                    footer: items => {
                        const total = items.reduce((sum, i) => sum + i.parsed.x, 0);
                        return `Total: ${formatMetric("tokens", total)}`;
                    }
                }
            }
        },
        scales: {
            x: {
                stacked: true,
                border: { display: false },
                grid: { color: gridColor },
                ticks: { color: textColor, callback: v => formatMetric("tokens", v), maxTicksLimit: 8, padding: 6 }
            },
            y: {
                stacked: true,
                border: { display: false },
                grid: { display: false },
                ticks: { color: textColor, font: { size: 10 }, autoSkip: false, crossAlign: "far" }
            }
        }
    }), [textColor, gridColor, plotted, models, harnesses]);

    if (!plotted.length) {
        return (
            <p className="text-xs text-slate-500 dark:text-slate-400 py-10 text-center">
                {task
                    ? "No setup in the current selection reports token buckets for this task."
                    : "No setup breaks its token usage into buckets yet — the harness reports a total only."}
            </p>
        );
    }

    return (
        <div style={{ height: plotted.length * ROW_PX + CHROME_PX }}>
            <Bar data={data} options={options} plugins={[setupIconsPlugin]} role="img" aria-label={ariaLabel} />
            <table className="sr-only">
                {caption ? <caption>{caption}</caption> : null}
                <thead>
                    <tr>
                        <th scope="col">Setup</th>
                        {TOKEN_BUCKET_METRICS.map(m => <th key={m} scope="col">{METRIC_LABELS[m]}</th>)}
                    </tr>
                </thead>
                <tbody>
                    {plotted.map(row => (
                        <tr key={row.setup.id}>
                            <th scope="row">{setupLabel(row.setup, models, harnesses)}</th>
                            {TOKEN_BUCKET_METRICS.map(m => <td key={m}>{formatMetric(m, row.buckets[m])}</td>)}
                        </tr>
                    ))}
                </tbody>
            </table>
        </div>
    );
}
