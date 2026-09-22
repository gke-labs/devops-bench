// Ranked horizontal bars for one metric — the chart that opens each section.
//
// The leaderboard table already sorts on a metric, so why draw it: a table cell
// reads as a number and bars read as a ratio. "$0.10 versus $0.40" takes a
// division; a bar a quarter the length of its neighbour does not. Direction
// comes from the metric, so the top bar is always the best one.
//
// `task` / `aggregate` are the same task view the token breakdown takes: the
// per-task mean, the suite total, or one task on its own. They go through the
// shared resolver, so a setup ranks the same way here as it does there.

import { useMemo } from "react";
import { Bar } from "react-chartjs-2";
import {
    Chart,
    BarElement,
    CategoryScale,
    LinearScale,
    Tooltip
} from "chart.js";
import { rankedBars } from "../lib/charts.js";
import { setupIconsPlugin, iconGutter } from "../lib/chartIcons.js";
import { barValuePlugin, valuePad } from "../lib/barValues.js";
import { METRIC_LABELS, formatMetric } from "../lib/vocab.js";
import { useIsDark } from "../hooks/useIsDark.js";

Chart.register(BarElement, CategoryScale, LinearScale, Tooltip);

const ROW_PX = 30;
const CHROME_PX = 56;

export function RankedBarChart({ setups, metric, models, harnesses, task = null, aggregate = "mean", ariaLabel, caption }) {
    const isDark = useIsDark();
    const textColor = isDark ? "#94a3b8" : "#64748b";
    const gridColor = isDark ? "#1e293b" : "#f1f5f9";

    const bars = useMemo(
        () => rankedBars(setups, metric, models, harnesses, { task, aggregate }),
        [setups, metric, models, harnesses, task, aggregate]
    );

    const data = useMemo(() => ({
        labels: bars.map(b => b.label),
        datasets: [{
            label: METRIC_LABELS[metric],
            data: bars.map(b => b.value),
            backgroundColor: bars.map(b => b.color),
            borderWidth: 0,
            borderRadius: 3
        }]
    }), [bars, metric]);

    const pad = useMemo(
        () => valuePad(bars.map(b => formatMetric(metric, b.value))),
        [bars, metric]
    );

    const options = useMemo(() => ({
        indexAxis: "y",
        responsive: true,
        maintainAspectRatio: false,
        layout: { padding: { left: iconGutter(2), right: pad } },
        plugins: {
            barValues: { color: textColor, format: v => formatMetric(metric, v) },
            setupIcons: { slots: 2, rowAt: (_tick, i) => bars[i] && { model: models[bars[i].setup.model], harness: harnesses[bars[i].setup.harness] } },
            legend: { display: false },
            tooltip: {
                callbacks: { label: ctx => ` ${METRIC_LABELS[metric]}: ${formatMetric(metric, ctx.parsed.x)}` }
            }
        },
        scales: {
            x: {
                border: { display: false },
                grid: { color: gridColor },
                ticks: { color: textColor, callback: v => formatMetric(metric, v), maxTicksLimit: 8, padding: 6 }
            },
            y: {
                border: { display: false },
                grid: { display: false },
                ticks: { color: textColor, font: { size: 10 }, autoSkip: false, crossAlign: "far" }
            }
        }
    }), [metric, textColor, gridColor, pad, bars, models, harnesses]);

    if (!bars.length) {
        return (
            <p className="text-xs text-slate-500 dark:text-slate-400 py-10 text-center">
                No setup reports {METRIC_LABELS[metric]} {task ? "for this task" : "in the current selection"}.
            </p>
        );
    }

    return (
        <div style={{ height: bars.length * ROW_PX + CHROME_PX }}>
            <Bar data={data} options={options} plugins={[barValuePlugin, setupIconsPlugin]} role="img" aria-label={ariaLabel} />
            <table className="sr-only">
                {caption ? <caption>{caption}</caption> : null}
                <thead>
                    <tr>
                        <th scope="col">Rank</th>
                        <th scope="col">Setup</th>
                        <th scope="col">{METRIC_LABELS[metric]}</th>
                    </tr>
                </thead>
                <tbody>
                    {bars.map((bar, i) => (
                        <tr key={bar.setup.id}>
                            <td>{i + 1}</td>
                            <th scope="row">{bar.label}</th>
                            <td>{formatMetric(metric, bar.value)}</td>
                        </tr>
                    ))}
                </tbody>
            </table>
        </div>
    );
}
