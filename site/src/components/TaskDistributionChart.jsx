// Per-task distribution strip: one row per setup, one dot per task.
//
// Every other view on this page is a mean, and a mean over a dozen tasks hides
// the shape that decides whether a setup is usable. A setup that costs $0.20 on
// every task and one that costs $0.02 on eleven and $2.20 on the twelfth have
// the same mean and are not the same product. The strip shows the spread the
// average flattens.

import { useMemo } from "react";
import { Scatter } from "react-chartjs-2";
import {
    Chart,
    PointElement,
    LinearScale,
    Tooltip
} from "chart.js";
import { setupLabel, setupScore } from "../lib/accessors.js";
import { taskValues } from "../lib/charts.js";
import { METRIC_LABELS, formatMetric, isLowerBetter, metricMeta } from "../lib/vocab.js";
import { useIsDark } from "../hooks/useIsDark.js";

Chart.register(PointElement, LinearScale, Tooltip);

const ROW_PX = 30;
const CHROME_PX = 70;

export function TaskDistributionChart({ setups, metric, models, harnesses, ariaLabel, caption }) {
    const isDark = useIsDark();
    const textColor = isDark ? "#94a3b8" : "#64748b";
    const gridColor = isDark ? "#1e293b" : "#f1f5f9";

    // One row per setup that measured this metric on at least one task, best
    // mean first and numbered from the top down (highest y = first row), so the
    // strip ranks the same way every other chart on the page does. Sorting on
    // the mean rather than on the spread keeps this row order comparable with
    // the ranked bars above it — the point of the strip is what the mean hides,
    // which is easiest to see when the means are in order.
    const rows = useMemo(() => {
        const lower = isLowerBetter(metric);
        return setups
            .map(setup => ({ setup, values: taskValues(setup, metric), mean: setupScore(setup, metric) }))
            .filter(r => r.values.length)
            .sort((a, b) => (lower ? a.mean - b.mean : b.mean - a.mean));
    }, [setups, metric]);

    const data = useMemo(() => ({
        datasets: rows.map((row, i) => ({
            label: setupLabel(row.setup, models, harnesses),
            data: row.values.map(v => ({ x: v.value, y: rows.length - 1 - i, task: v.task })),
            backgroundColor: `${row.setup.color}b3`,
            borderColor: row.setup.color,
            borderWidth: 1,
            pointRadius: 5,
            pointHoverRadius: 8
        }))
    }), [rows, models, harnesses]);

    const options = useMemo(() => ({
        responsive: true,
        maintainAspectRatio: false,
        interaction: { mode: "nearest", intersect: true },
        plugins: {
            legend: { display: false },
            tooltip: {
                callbacks: {
                    title: items => items[0]?.raw?.task ?? "",
                    label: ctx => ` ${ctx.dataset.label}: ${formatMetric(metric, ctx.parsed.x)}`
                }
            }
        },
        scales: {
            x: {
                title: { display: true, text: METRIC_LABELS[metric], color: textColor, font: { size: 11, weight: "600" } },
                border: { display: false },
                grid: { color: gridColor },
                ticks: {
                    color: textColor,
                    callback: v => formatMetric(metric, v),
                    ...(metricMeta(metric).percentage ? { stepSize: 20 } : { maxTicksLimit: 8 }),
                    padding: 6
                }
            },
            y: {
                // A category axis would centre the dots in bands; a linear axis
                // with integer ticks puts each setup on an exact gridline, which
                // is what makes the rows readable as rows.
                min: -0.5,
                max: rows.length - 0.5,
                border: { display: false },
                grid: { color: gridColor },
                ticks: {
                    color: textColor,
                    font: { size: 10 },
                    stepSize: 1,
                    autoSkip: false,
                    crossAlign: "far",
                    callback: value => {
                        const row = rows[rows.length - 1 - value];
                        return row ? setupLabel(row.setup, models, harnesses) : "";
                    }
                }
            }
        }
    }), [metric, rows, textColor, gridColor, models, harnesses]);

    if (!rows.length) {
        return (
            <p className="text-xs text-slate-500 dark:text-slate-400 py-10 text-center">
                No per-task {METRIC_LABELS[metric]} data in the current selection.
            </p>
        );
    }

    return (
        <div style={{ height: rows.length * ROW_PX + CHROME_PX }}>
            <Scatter data={data} options={options} role="img" aria-label={ariaLabel} />
            <table className="sr-only">
                {caption ? <caption>{caption}</caption> : null}
                <thead>
                    <tr>
                        <th scope="col">Setup</th>
                        <th scope="col">Task</th>
                        <th scope="col">{METRIC_LABELS[metric]}</th>
                    </tr>
                </thead>
                <tbody>
                    {rows.flatMap(row => row.values.map(v => (
                        <tr key={`${row.setup.id}-${v.task}`}>
                            <th scope="row">{setupLabel(row.setup, models, harnesses)}</th>
                            <td>{v.task}</td>
                            <td>{formatMetric(metric, v.value)}</td>
                        </tr>
                    )))}
                </tbody>
            </table>
        </div>
    );
}
