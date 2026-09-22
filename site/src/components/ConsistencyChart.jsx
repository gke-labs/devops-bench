// Consistency across the suite: one box plot per setup. The box is the middle
// half of its tasks, the line inside is the median, and the whiskers reach its
// best task and its worst.
//
// The box is the part that matters. A wide whisker on a narrow box is one
// awkward task; a wide box is a setup that behaves differently every time you
// run it. Reading only the full range would call those two the same.
//
// Every other view on this page is a mean, and a mean cannot separate a setup
// that costs the same on all twelve tasks from one that is nearly free on eleven
// and ruinous on the twelfth. Those are the same number and not the same
// product — and which one you have is what decides whether you can budget for
// it. This is the only section that says which.
//
// It ranks on predictability, NOT on quality. A setup that is uniformly bad is
// perfectly consistent and sits at the top; the charts above are where quality
// is ranked. Read this one as "can I trust the average".

import { useMemo } from "react";
import { Bar } from "react-chartjs-2";
import {
    Chart,
    BarElement,
    CategoryScale,
    LinearScale,
    Tooltip
} from "chart.js";
import { taskSpreads } from "../lib/charts.js";
import { METRIC_LABELS, formatMetric } from "../lib/vocab.js";
import { setupIconsPlugin, iconGutter } from "../lib/chartIcons.js";
import { VALUE_FONT, VALUE_GAP, valuePad } from "../lib/barValues.js";
import { useIsDark } from "../hooks/useIsDark.js";

Chart.register(BarElement, CategoryScale, LinearScale, Tooltip);

const ROW_PX = 32;
const CHROME_PX = 64;

const WHISKER_PX = 2;
// End caps at half the box height: tall enough to read as a terminator, short
// enough that they do not compete with the box for attention.
const CAP_RATIO = 0.5;

const rangeText = (metric, row) => `${formatMetric(metric, row.min)} – ${formatMetric(metric, row.max)}`;

// Everything a box plot has that a bar does not: the whiskers out to the best
// and worst task with a cap on each end, the median line through the box, and
// the full range in text past the right-hand whisker. Chart.js draws the box
// itself as a floating bar.
export const spreadMarkerPlugin = {
    id: "spreadMarkers",
    afterDatasetsDraw(chart, _args, opts) {
        const rows = opts?.rows;
        const meta = chart.getDatasetMeta(0);
        if (!rows?.length || meta.hidden) return;
        const { ctx } = chart;
        const x = chart.scales.x;
        ctx.save();
        ctx.lineWidth = WHISKER_PX;
        meta.data.forEach((bar, i) => {
            const row = rows[i];
            if (!row) return;
            const half = bar.height / 2;
            const cap = half * CAP_RATIO;

            ctx.strokeStyle = row.color;
            ctx.beginPath();
            // The cap belongs on the far end of each whisker, which is the box
            // edge on one side of the pair and the extreme task on the other.
            for (const [inner, outer] of [[row.q1, row.min], [row.q3, row.max]]) {
                const end = x.getPixelForValue(outer);
                ctx.moveTo(x.getPixelForValue(inner), bar.y);
                ctx.lineTo(end, bar.y);
                ctx.moveTo(end, bar.y - cap);
                ctx.lineTo(end, bar.y + cap);
            }
            ctx.stroke();

            const mid = x.getPixelForValue(row.median);
            ctx.strokeStyle = opts.markerColor;
            ctx.beginPath();
            ctx.moveTo(mid, bar.y - half);
            ctx.lineTo(mid, bar.y + half);
            ctx.stroke();

            ctx.font = VALUE_FONT;
            ctx.fillStyle = opts.textColor;
            ctx.textAlign = "left";
            ctx.textBaseline = "middle";
            ctx.fillText(rangeText(opts.metric, row), x.getPixelForValue(row.max) + VALUE_GAP, bar.y);
        });
        ctx.restore();
    }
};

export function ConsistencyChart({ setups, metric, models, harnesses, ariaLabel, caption }) {
    const isDark = useIsDark();
    const textColor = isDark ? "#94a3b8" : "#64748b";
    const gridColor = isDark ? "#1e293b" : "#f1f5f9";

    const rows = useMemo(
        () => taskSpreads(setups, metric, models, harnesses),
        [setups, metric, models, harnesses]
    );

    const data = useMemo(() => ({
        labels: rows.map(r => r.label),
        datasets: [{
            label: METRIC_LABELS[metric],
            // The box: a floating bar from Q1 to Q3, so its length IS the
            // spread of the middle half rather than the size of the numbers.
            data: rows.map(r => [r.q1, r.q3]),
            backgroundColor: rows.map(r => `${r.color}59`),
            borderColor: rows.map(r => r.color),
            borderWidth: 1,
            borderSkipped: false,
            // Square, as a box plot is. Rounded ends would read as a bar.
            borderRadius: 0
        }]
    }), [rows, metric]);

    const pad = useMemo(
        () => valuePad(rows.map(r => rangeText(metric, r))),
        [rows, metric]
    );

    const options = useMemo(() => ({
        indexAxis: "y",
        responsive: true,
        maintainAspectRatio: false,
        interaction: { mode: "index", axis: "y", intersect: false },
        layout: { padding: { left: iconGutter(2), right: pad } },
        plugins: {
            legend: { display: false },
            spreadMarkers: { rows, metric, textColor, markerColor: isDark ? "#e2e8f0" : "#334155" },
            setupIcons: {
                slots: 2,
                rowAt: (_tick, i) => rows[i] && { model: models[rows[i].setup.model], harness: harnesses[rows[i].setup.harness] }
            },
            tooltip: {
                animation: false,
                callbacks: {
                    label: ctx => {
                        const row = rows[ctx.dataIndex];
                        return [
                            ` Best task: ${formatMetric(metric, row.min)}`,
                            ` Middle half: ${formatMetric(metric, row.q1)} – ${formatMetric(metric, row.q3)}`,
                            ` Median of ${row.count}: ${formatMetric(metric, row.median)}`,
                            ` Worst task: ${formatMetric(metric, row.worst.value)} — ${row.worst.task}`
                        ];
                    }
                }
            }
        },
        scales: {
            x: {
                // From zero, so the boxes sit at their true position on the
                // scale and a narrow box near the origin reads as cheap AND
                // steady. The whiskers are drawn by a plugin, so the axis has
                // never seen them and would otherwise crop the far one.
                beginAtZero: true,
                suggestedMax: Math.max(...rows.map(r => r.max)),
                title: { display: true, text: METRIC_LABELS[metric], color: textColor, font: { size: 11, weight: "600" } },
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
    }), [rows, metric, textColor, gridColor, isDark, pad, models, harnesses]);

    if (!rows.length) {
        return (
            <p className="text-xs text-slate-500 dark:text-slate-400 py-10 text-center">
                No setup in the current selection reports {METRIC_LABELS[metric]} on more than one task,
                so there is no spread to measure.
            </p>
        );
    }

    return (
        <div style={{ height: rows.length * ROW_PX + CHROME_PX }}>
            <Bar data={data} options={options} plugins={[spreadMarkerPlugin, setupIconsPlugin]} role="img" aria-label={ariaLabel} />
            <table className="sr-only">
                {caption ? <caption>{caption}</caption> : null}
                <thead>
                    <tr>
                        <th scope="col">Rank</th>
                        <th scope="col">Setup</th>
                        <th scope="col">Tasks</th>
                        <th scope="col">Best task</th>
                        <th scope="col">Lower quartile</th>
                        <th scope="col">Median</th>
                        <th scope="col">Upper quartile</th>
                        <th scope="col">Worst task</th>
                        <th scope="col">Worst task name</th>
                    </tr>
                </thead>
                <tbody>
                    {rows.map((row, i) => (
                        <tr key={row.setup.id}>
                            <td>{i + 1}</td>
                            <th scope="row">{row.label}</th>
                            <td>{row.count}</td>
                            <td>{formatMetric(metric, row.min)}</td>
                            <td>{formatMetric(metric, row.q1)}</td>
                            <td>{formatMetric(metric, row.median)}</td>
                            <td>{formatMetric(metric, row.q3)}</td>
                            <td>{formatMetric(metric, row.worst.value)}</td>
                            <td>{row.worst.task}</td>
                        </tr>
                    ))}
                </tbody>
            </table>
        </div>
    );
}
