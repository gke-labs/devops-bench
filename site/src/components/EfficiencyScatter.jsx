// Quality-versus-spend scatter: one dot per setup, colored by model or harness,
// with the Pareto frontier drawn through the non-dominated dots.
//
// This is the chart the leaderboard table cannot be. A table ranks on one metric
// at a time, so it can say "this setup scores highest" or "this setup is
// cheapest" but never "this setup is the best score you can get at this price" —
// and that last one is the question anyone choosing a setup is actually asking.
// The frontier answers it: everything below the line is beaten outright by
// something on it.

import { useMemo } from "react";
import { Scatter } from "react-chartjs-2";
import {
    Chart,
    LineElement,
    PointElement,
    LinearScale,
    LogarithmicScale,
    Tooltip,
    Legend
} from "chart.js";
import { setupLabel } from "../lib/accessors.js";
import { scatterPoints, paretoFrontier, colorSeries, canUseLogScale, placeLabels } from "../lib/charts.js";
import { METRIC_LABELS, formatMetric, isLowerBetter, metricMeta } from "../lib/vocab.js";
import { drawMarks, marksWidth, legendMarksPlugin, markedLegendLabels, LEGEND_BOX_PX } from "../lib/chartIcons.js";
import { useIsDark } from "../hooks/useIsDark.js";

Chart.register(LineElement, PointElement, LinearScale, LogarithmicScale, Tooltip, Legend);

// Frontier line color — deliberately neutral rather than one of the series
// colors, so it reads as annotation over the data instead of another series.
const FRONTIER_COLOR = "#94a3b8";

const LABEL_FONT_PX = 10;
const LABEL_FONT = `500 ${LABEL_FONT_PX}px system-ui, sans-serif`;
// Marks sized to the label text, so a label reads as one object rather than a
// glyph with a caption.
const LABEL_MARK_PX = 11;

// Names every dot on the canvas, model and harness mark first. The legend groups
// dots by color, which cannot tell apart three dots that share one — and on a
// chart of model × harness pairings, most colors are shared. Geometry lives in
// placeLabels; this only measures the label and draws it.
const pointLabelPlugin = {
    id: "pointLabels",
    afterDatasetsDraw(chart, _args, opts) {
        const { ctx, chartArea } = chart;
        ctx.save();
        ctx.font = LABEL_FONT;
        const dots = [];
        // The frontier as drawn, in pixels, so placeLabels can steer labels off
        // it. Read back from the chart rather than recomputed, so it is the same
        // line the reader sees whatever the axes are doing.
        let frontierLine = [];
        chart.data.datasets.forEach((dataset, di) => {
            const meta = chart.getDatasetMeta(di);
            if (meta.hidden) return;
            if (dataset.showLine) {
                frontierLine = meta.data.map(element => ({ x: element.x, y: element.y }));
                return;
            }
            dataset.data.forEach((point, pi) => {
                const element = meta.data[pi];
                if (!element || !point.label) return;
                // The marks are part of the label's footprint, or placeLabels
                // packs them over the neighbouring dots.
                const markW = marksWidth(point, LABEL_MARK_PX);
                dots.push({
                    x: element.x,
                    y: element.y,
                    r: dataset.pointRadius ?? 4,
                    w: ctx.measureText(point.label).width + markW,
                    h: Math.max(LABEL_FONT_PX + 2, LABEL_MARK_PX),
                    text: point.label,
                    mark: point,
                    markW,
                    color: dataset.borderColor
                });
            });
        });

        // Left-aligned now that a label is marks plus text: placeLabels returns
        // the centre, and the pair is laid out from there.
        ctx.textAlign = "left";
        ctx.textBaseline = "middle";
        // A halo in the page background: labels cross gridlines and, when the
        // plot is crowded, each other.
        ctx.strokeStyle = opts.haloColor;
        ctx.lineWidth = 3;
        ctx.lineJoin = "round";
        placeLabels(dots, chartArea, frontierLine).forEach((spot, i) => {
            const dot = dots[i];
            const left = spot.x - dot.w / 2;
            drawMarks(ctx, dot.mark, left, spot.y - LABEL_MARK_PX / 2, LABEL_MARK_PX);
            ctx.strokeText(dot.text, left + dot.markW, spot.y);
            ctx.fillStyle = dot.color;
            ctx.fillText(dot.text, left + dot.markW, spot.y);
        });
        ctx.restore();
    }
};

export function EfficiencyScatter({
    setups,
    xMetric,
    yMetric,
    models,
    harnesses,
    colorBy = "model",
    xAggregate = "mean",
    showFrontier = false,
    logX = false,
    logY = false,
    ariaLabel,
    caption
}) {
    const isDark = useIsDark();
    const textColor = isDark ? "#94a3b8" : "#64748b";
    const gridColor = isDark ? "#1e293b" : "#f1f5f9";

    const points = useMemo(
        () => scatterPoints(setups, xMetric, yMetric, { aggregate: xAggregate }),
        [setups, xMetric, yMetric, xAggregate]
    );

    const series = useMemo(
        () => colorSeries(points.map(p => p.setup), colorBy, models, harnesses),
        [points, colorBy, models, harnesses]
    );

    const frontier = useMemo(
        () => (showFrontier ? paretoFrontier(points, xMetric, yMetric) : []),
        [points, xMetric, yMetric, showFrontier]
    );

    // A log axis silently drops non-positive values, so fall back to linear when
    // any plotted point would vanish. The control that offers the toggle
    // disables it in the same case; this is the belt to that braces.
    const useLogX = logX && canUseLogScale(points.map(p => p.x));
    const useLogY = logY && canUseLogScale(points.map(p => p.y));

    const data = useMemo(() => {
        const byId = new Map(points.map(p => [p.setup.id, p]));
        const seriesSets = series.map(s => ({
            label: s.label,
            data: s.setups.map(setup => {
                const p = byId.get(setup.id);
                return {
                    x: p.x,
                    y: p.y,
                    label: setupLabel(setup, models, harnesses),
                    model: models[setup.model],
                    harness: harnesses[setup.harness]
                };
            }),
            backgroundColor: s.color,
            borderColor: s.color,
            pointRadius: 6,
            pointHoverRadius: 9,
            pointHitRadius: 20,
            showLine: false,
            order: 1
        }));
        if (!frontier.length) return { datasets: seriesSets };
        return {
            datasets: [
                {
                    label: "Pareto frontier",
                    data: frontier.map(p => ({ x: p.x, y: p.y })),
                    borderColor: FRONTIER_COLOR,
                    borderWidth: 2,
                    borderDash: [6, 4],
                    pointRadius: 0,
                    pointHitRadius: 0,
                    showLine: true,
                    // Behind the dots: the frontier is a reference line, and a
                    // dashed line crossing a point makes the point hard to read.
                    order: 2,
                    // A staircase, not a curve. The line joins discrete choices;
                    // a smoothed spline would imply setups exist between them.
                    tension: 0
                },
                ...seriesSets
            ]
        };
    }, [points, series, frontier, models, harnesses]);

    const xLabel = xAggregate === "total"
        ? (xMetric === "latency" ? "Total Time" : xMetric === "cost" ? "Total Cost (USD)" : `Total ${METRIC_LABELS[xMetric]}`)
        : (xMetric === "latency" ? "Time per Task (Average)" : xMetric === "cost" ? "Cost per Task (Average)" : `${METRIC_LABELS[xMetric]} per Task (Average)`);

    const options = useMemo(() => ({
        responsive: true,
        maintainAspectRatio: false,
        interaction: { mode: "nearest", intersect: false },
        plugins: {
            pointLabels: { haloColor: isDark ? "#0f172a" : "#ffffff" },
            legendMarks: {
                // The legend lists colour-by groups, so one series is one model
                // OR one harness — never both.
                // Matched on the label rather than the dataset index, which the
                // frontier dataset offsets by one only when it is drawn.
                markAt: item => {
                    const s = series.find(x => x.label === item.text);
                    if (!s) return null;
                    return colorBy === "harness"
                        ? { harness: harnesses[s.key], color: s.color }
                        : { model: models[s.key], color: s.color };
                }
            },
            legend: {
                display: true,
                position: "bottom",
                labels: {
                    color: textColor,
                    boxWidth: LEGEND_BOX_PX,
                    generateLabels: markedLegendLabels,
                    padding: 16,
                    font: { size: 11, weight: "500" },
                    // The frontier is annotation, not a series you can compare
                    // against; leaving it in the legend invites toggling it off
                    // as if it were data.
                    filter: item => item.text !== "Pareto frontier"
                }
            },
            tooltip: {
                animation: false,
                callbacks: {
                    title: items => items[0]?.raw?.label ?? "",
                    label: ctx => [
                        ` ${xLabel}: ${formatMetric(xMetric, ctx.parsed.x)}`,
                        ` ${METRIC_LABELS[yMetric]}: ${formatMetric(yMetric, ctx.parsed.y)}`
                    ]
                }
            }
        },
        scales: {
            x: {
                type: useLogX ? "logarithmic" : "linear",
                title: { display: true, text: xLabel, color: textColor, font: { size: 11, weight: "600" } },
                border: { display: false },
                grid: { color: gridColor },
                ticks: {
                    color: textColor,
                    callback: value => formatMetric(xMetric, value),
                    maxTicksLimit: 8,
                    padding: 6
                }
            },
            y: {
                type: useLogY ? "logarithmic" : "linear",
                title: { display: true, text: METRIC_LABELS[yMetric], color: textColor, font: { size: 11, weight: "600" } },
                border: { display: false },
                grid: { color: gridColor },
                ticks: {
                    color: textColor,
                    callback: value => formatMetric(yMetric, value),
                    ...(metricMeta(yMetric).percentage && !useLogY ? { stepSize: 10 } : { maxTicksLimit: 8 }),
                    padding: 6
                }
            }
        }
    }), [xMetric, yMetric, xLabel, textColor, gridColor, useLogX, useLogY, isDark, series, colorBy, models, harnesses]);

    if (!points.length) {
        return (
            <p className="text-xs text-slate-500 dark:text-slate-400 py-10 text-center">
                No setup reports both {METRIC_LABELS[xMetric]} and {METRIC_LABELS[yMetric]} yet.
            </p>
        );
    }

    const onFrontier = new Set(frontier.map(p => p.setup.id));

    // A scatter has no reading order, but its accessible table does, and
    // whatever order the setups arrived in is not one. Rank by the y metric,
    // then by x — the same best-first order the bar charts use, so a screen
    // reader gets the ranking a sighted reader gets from the dot positions.
    const ranked = [...points].sort((a, b) =>
        (isLowerBetter(yMetric) ? a.y - b.y : b.y - a.y) ||
        (isLowerBetter(xMetric) ? a.x - b.x : b.x - a.x)
    );

    return (
        // Fills whatever box the caller gives it. NOT `.chart-container`, which
        // pins 320px and would leave the rest of a taller wrapper as dead space.
        <div className="relative w-full h-full">
            <Scatter data={data} options={options} plugins={[pointLabelPlugin, legendMarksPlugin]} role="img" aria-label={ariaLabel} />
            <table className="sr-only">
                {caption ? <caption>{caption}</caption> : null}
                <thead>
                    <tr>
                        <th scope="col">Setup</th>
                        <th scope="col">{xLabel}</th>
                        <th scope="col">{METRIC_LABELS[yMetric]}</th>
                        {/* Only when a frontier was drawn. Without one, every
                            row would read "no" — an answer to a question this
                            chart never asked. */}
                        {showFrontier ? <th scope="col">On Pareto frontier</th> : null}
                    </tr>
                </thead>
                <tbody>
                    {ranked.map(p => (
                        <tr key={p.setup.id}>
                            <th scope="row">{setupLabel(p.setup, models, harnesses)}</th>
                            <td>{formatMetric(xMetric, p.x)}</td>
                            <td>{formatMetric(yMetric, p.y)}</td>
                            {showFrontier ? <td>{onFrontier.has(p.setup.id) ? "yes" : "no"}</td> : null}
                        </tr>
                    ))}
                </tbody>
            </table>
        </div>
    );
}
