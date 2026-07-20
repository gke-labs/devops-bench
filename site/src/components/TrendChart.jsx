// Score-over-time line chart, shared by the leaderboard (many lines) and the
// detail page (one filled line). Ported from initTrendChart/updateTrendChart in
// app.js + initSetupChart in detail.js. Includes the sr-only accessibility table.

import { useMemo } from "react";
import { Line } from "react-chartjs-2";
import {
    Chart,
    LineElement,
    PointElement,
    LinearScale,
    Filler,
    Tooltip,
    Legend
} from "chart.js";
import { setupHistory, setupLabel, allRunDates, formatRunDate, yAxisBounds } from "../lib/accessors.js";
import { useIsDark } from "../hooks/useIsDark.js";

// Register Chart.js parts + apply the Inter styling once at module load. Colors
// that differ by theme are set per-instance in `options` below (canvas can't use
// Tailwind `dark:` variants); the tooltip is dark in both themes.
Chart.register(LineElement, PointElement, LinearScale, Filler, Tooltip, Legend);
Chart.defaults.font.family = "'Inter', sans-serif";
Chart.defaults.plugins.tooltip.backgroundColor = "#0f172a";
Chart.defaults.plugins.tooltip.titleColor = "#f8fafc";
Chart.defaults.plugins.tooltip.bodyColor = "#cbd5e1";
Chart.defaults.plugins.tooltip.padding = 12;
Chart.defaults.plugins.tooltip.cornerRadius = 8;
Chart.defaults.plugins.tooltip.borderWidth = 1;
Chart.defaults.plugins.tooltip.borderColor = "#334155";

export function TrendChart({
    setups,
    metric,
    models,
    harnesses,
    showLegend = true,
    fill = false,
    ariaLabel = "Score trend over time",
    caption
}) {
    const isDark = useIsDark();
    // Theme-aware axis/legend colors (the tick + grid can't use `dark:`).
    const textColor = isDark ? "#94a3b8" : "#64748b"; // slate-400 / slate-500
    const gridColor = isDark ? "#1e293b" : "#f1f5f9"; // slate-800 / slate-100
    const pointHover = isDark ? "#0f172a" : "#ffffff";

    // Shared x-axis dates: union of run timestamps across the plotted setups.
    const dates = useMemo(() => allRunDates(setups), [setups]);

    // Data-fitted y-axis (clamped to [0,100]) so low scores aren't clipped.
    const yBounds = useMemo(() => yAxisBounds(setups, metric), [setups, metric]);

    const data = useMemo(() => ({
        datasets: setups.map(setup => ({
            label: setupLabel(setup, models, harnesses),
            data: setupHistory(setup, metric),
            borderColor: setup.color,
            backgroundColor: `${setup.color}1a`,
            pointBorderColor: setup.color,
            pointBackgroundColor: setup.color,
            fill
        }))
    }), [setups, metric, models, harnesses, fill]);

    const options = useMemo(() => ({
        responsive: true,
        maintainAspectRatio: false,
        interaction: { mode: "nearest", intersect: false },
        plugins: {
            legend: showLegend
                ? { display: true, position: "bottom", labels: { color: textColor, usePointStyle: true, boxWidth: 8, padding: 20, font: { size: 11, weight: "500" } } }
                : { display: false },
            tooltip: {
                callbacks: {
                    title: items => (items.length ? formatRunDate(items[0].parsed.x) : ""),
                    label: ctx => ` ${ctx.dataset.label}: ${ctx.parsed.y.toFixed(1)}%`
                }
            }
        },
        scales: {
            x: {
                type: "linear",
                bounds: "data",
                // Real time axis: ticks land exactly on the run dates, spaced
                // proportionally to elapsed time.
                afterBuildTicks: axis => { axis.ticks = dates.map(t => ({ value: Date.parse(t) })); },
                grid: { display: false },
                ticks: { color: textColor, callback: value => formatRunDate(value), maxRotation: 0, autoSkip: false, padding: 8 }
            },
            y: {
                min: yBounds.min,
                max: yBounds.max,
                border: { display: false },
                grid: { color: gridColor },
                ticks: { color: textColor, callback: value => value + "%", stepSize: 10, padding: 8 }
            }
        },
        elements: {
            line: { tension: 0.35, borderWidth: 3 },
            point: { radius: 3, hitRadius: 12, hoverRadius: 6, hoverBackgroundColor: pointHover, hoverBorderWidth: 3 }
        }
    }), [dates, showLegend, yBounds, textColor, gridColor, pointHover]);

    return (
        <div className="chart-container flex-grow">
            <Line data={data} options={options} role="img" aria-label={ariaLabel} />
            {/* Accessible screen-reader-only data table. */}
            <table className="sr-only">
                {caption ? <caption>{caption}</caption> : null}
                <thead>
                    <tr>
                        <th scope="col">Setup</th>
                        {dates.map(d => <th key={d} scope="col">{formatRunDate(d)}</th>)}
                    </tr>
                </thead>
                <tbody>
                    {setups.map(setup => (
                        <tr key={setup.id}>
                            <th scope="row">{setupLabel(setup, models, harnesses)}</th>
                            {dates.map(d => {
                                // Guard both a missing run AND a present run with a
                                // null value for this metric (sparse real data).
                                const v = setup.history.find(h => h.t === d)?.scores[metric];
                                return <td key={d}>{v == null ? "—" : v.toFixed(1) + "%"}</td>;
                            })}
                        </tr>
                    ))}
                </tbody>
            </table>
        </div>
    );
}
