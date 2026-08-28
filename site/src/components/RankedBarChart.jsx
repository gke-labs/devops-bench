// Ranked horizontal bars for one metric — the chart that opens each section.
//
// The leaderboard table already sorts on a metric, so why draw it: a table cell
// reads as a number and bars read as a ratio. "$0.10 versus $0.40" takes a
// division; a bar a quarter the length of its neighbour does not. Direction
// comes from the metric, so the top bar is always the best one.

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
import { METRIC_LABELS, formatMetric } from "../lib/vocab.js";
import { useIsDark } from "../hooks/useIsDark.js";

Chart.register(BarElement, CategoryScale, LinearScale, Tooltip);

const ROW_PX = 30;
const CHROME_PX = 56;

const VALUE_FONT_PX = 11;
const VALUE_GAP = 6;
// Rough advance width per character at the value font. Used to reserve the
// right margin before Chart.js lays out, when there is no ctx to measure with.
const VALUE_CHAR_PX = VALUE_FONT_PX * 0.62;

// Prints each bar's value past its end. A bar shows a ratio at a glance but
// never the number, and the axis ticks only bracket it — reading "$0.31" off a
// bar between the $0.20 and $0.40 gridlines is a guess.
export const barValuePlugin = {
    id: "barValues",
    afterDatasetsDraw(chart, _args, opts) {
        const meta = chart.getDatasetMeta(0);
        if (meta.hidden) return;
        const { ctx } = chart;
        ctx.save();
        ctx.font = `600 ${VALUE_FONT_PX}px system-ui, sans-serif`;
        ctx.fillStyle = opts.color;
        ctx.textAlign = "left";
        ctx.textBaseline = "middle";
        meta.data.forEach((bar, i) => {
            ctx.fillText(opts.format(chart.data.datasets[0].data[i]), bar.x + VALUE_GAP, bar.y);
        });
        ctx.restore();
    }
};

export function RankedBarChart({ setups, metric, models, harnesses, ariaLabel, caption }) {
    const isDark = useIsDark();
    const textColor = isDark ? "#94a3b8" : "#64748b";
    const gridColor = isDark ? "#1e293b" : "#f1f5f9";

    const bars = useMemo(
        () => rankedBars(setups, metric, models, harnesses),
        [setups, metric, models, harnesses]
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

    // Right margin for the printed values. Without it the longest bar's value
    // is drawn past the canvas edge and clipped — and that is the top bar, the
    // one the chart exists to show.
    const valuePad = useMemo(() => {
        if (!bars.length) return 0;
        const widest = Math.max(...bars.map(b => formatMetric(metric, b.value).length));
        return widest * VALUE_CHAR_PX + VALUE_GAP + 4;
    }, [bars, metric]);

    const options = useMemo(() => ({
        indexAxis: "y",
        responsive: true,
        maintainAspectRatio: false,
        layout: { padding: { right: valuePad } },
        plugins: {
            barValues: { color: textColor, format: v => formatMetric(metric, v) },
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
    }), [metric, textColor, gridColor, valuePad]);

    if (!bars.length) {
        return (
            <p className="text-xs text-slate-500 dark:text-slate-400 py-10 text-center">
                No setup reports {METRIC_LABELS[metric]} in the current selection.
            </p>
        );
    }

    return (
        <div style={{ height: bars.length * ROW_PX + CHROME_PX }}>
            <Bar data={data} options={options} plugins={[barValuePlugin]} role="img" aria-label={ariaLabel} />
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
