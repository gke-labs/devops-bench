// Harness savings: the same model run on two or more harnesses, side by side.
//
// The scatter above plots model × harness pairings, which is honest but cannot
// isolate the harness — a cheap dot might be a cheap model. This chart holds the
// model AND the augmentation fixed and varies only the runner, so the gap
// between two bars is what the harness itself cost: how much context it
// re-sends, how many turns it takes, whether it caches.
//
// A model that ran on one harness only is omitted rather than drawn as a lone
// full bar, which would read as a win over nothing.

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
import { harnessComparisons } from "../lib/charts.js";
import { METRIC_LABELS, formatMetric, isLowerBetter } from "../lib/vocab.js";
import { useIsDark } from "../hooks/useIsDark.js";

Chart.register(BarElement, CategoryScale, LinearScale, Tooltip, Legend);

const BAR_PX = 26;
const CHROME_PX = 90;

// "+180%" reads as more of a good thing; on cost it is the opposite. Say which.
function pctText(metric, pct) {
    if (pct == null) return "—";
    if (Math.abs(pct) < 0.05) return "best";
    const worse = isLowerBetter(metric) ? pct > 0 : pct < 0;
    return `${Math.abs(pct).toFixed(0)}% ${worse ? "worse" : "better"} than best`;
}

export function HarnessSavingsChart({ setups, metric, models, harnesses, ariaLabel, caption }) {
    const isDark = useIsDark();
    const textColor = isDark ? "#94a3b8" : "#64748b";
    const gridColor = isDark ? "#1e293b" : "#f1f5f9";

    const groups = useMemo(
        () => harnessComparisons(setups, metric, models, harnesses),
        [setups, metric, models, harnesses]
    );

    // One dataset per harness, in first-appearance order, so the legend is
    // stable and a harness missing from a group leaves a gap rather than
    // shifting the bars of the harnesses that did run.
    const series = useMemo(() => {
        const byHarness = new Map();
        for (const g of groups) {
            for (const e of g.entries) {
                if (!byHarness.has(e.harness)) byHarness.set(e.harness, { key: e.harness, label: e.label, color: e.color });
            }
        }
        return [...byHarness.values()];
    }, [groups]);

    const data = useMemo(() => ({
        labels: groups.map(g => g.label),
        datasets: series.map(s => ({
            label: s.label,
            data: groups.map(g => g.entries.find(e => e.harness === s.key)?.value ?? null),
            backgroundColor: s.color,
            borderWidth: 0,
            borderRadius: 2,
            harnessKey: s.key
        }))
    }), [groups, series]);

    const options = useMemo(() => ({
        indexAxis: "y",
        responsive: true,
        maintainAspectRatio: false,
        plugins: {
            legend: {
                position: "bottom",
                labels: { color: textColor, usePointStyle: true, boxWidth: 8, padding: 16, font: { size: 11, weight: "500" } }
            },
            tooltip: {
                callbacks: {
                    label: ctx => {
                        const entry = groups[ctx.dataIndex]?.entries.find(e => e.harness === ctx.dataset.harnessKey);
                        if (!entry) return ` ${ctx.dataset.label}: —`;
                        return ` ${ctx.dataset.label}: ${formatMetric(metric, entry.value)} (${pctText(metric, entry.pctVsBest)})`;
                    }
                }
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
    }), [textColor, gridColor, groups, metric]);

    if (!groups.length) {
        return (
            <p className="text-xs text-slate-500 dark:text-slate-400 py-10 text-center">
                No model in the current selection ran on more than one harness with the same augmentation,
                so there is no like-for-like harness comparison to draw.
            </p>
        );
    }

    const barCount = groups.reduce((n, g) => n + g.entries.length, 0);

    return (
        <div style={{ height: barCount * BAR_PX + CHROME_PX }}>
            <Bar data={data} options={options} role="img" aria-label={ariaLabel} />
            <table className="sr-only">
                {caption ? <caption>{caption}</caption> : null}
                <thead>
                    <tr>
                        <th scope="col">Model and augmentation</th>
                        <th scope="col">Harness</th>
                        <th scope="col">{METRIC_LABELS[metric]}</th>
                        <th scope="col">Versus best harness</th>
                    </tr>
                </thead>
                <tbody>
                    {groups.flatMap(g => g.entries.map((e, i) => (
                        <tr key={`${g.key}-${e.harness}`}>
                            <th scope="row">{i === 0 ? g.label : ""}</th>
                            <td>{e.label}</td>
                            <td>{formatMetric(metric, e.value)}</td>
                            <td>{pctText(metric, e.pctVsBest)}</td>
                        </tr>
                    )))}
                </tbody>
            </table>
        </div>
    );
}
