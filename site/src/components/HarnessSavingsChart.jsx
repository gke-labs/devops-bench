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
//
// The legend is HTML rather than Chart.js's own: the y-axis labels name the
// model, so the legend is the ONLY place a bar's harness is stated, and colour
// alone is a poor key once two accents are close or the reader cannot tell them
// apart. Rendering it outside the canvas lets it carry the same glyph the rest
// of the dashboard uses for that harness.

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
import { setupIconsPlugin, iconGutter } from "../lib/chartIcons.js";
import { barValuePlugin, valuePad } from "../lib/barValues.js";
import { useIsDark } from "../hooks/useIsDark.js";
import { HarnessIcon } from "./Logo.jsx";

Chart.register(BarElement, CategoryScale, LinearScale, Tooltip, Legend);

const BAR_PX = 26;
// Chart chrome only — the HTML legend sits outside the canvas and takes its own
// space, so the canvas no longer has to reserve room for one.
const CHROME_PX = 56;

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
                if (!byHarness.has(e.harness)) {
                    byHarness.set(e.harness, {
                        key: e.harness,
                        label: e.label,
                        color: e.color,
                        // The glyph is keyed off the catalog entry, so a harness
                        // the catalog does not carry falls back to colour alone
                        // rather than borrowing another runner's mark.
                        harness: harnesses[e.harness]
                    });
                }
            }
        }
        return [...byHarness.values()];
    }, [groups, harnesses]);

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

    const pad = useMemo(
        () => valuePad(groups.flatMap(g => g.entries.map(e => formatMetric(metric, e.value)))),
        [groups, metric]
    );

    const options = useMemo(() => ({
        indexAxis: "y",
        responsive: true,
        maintainAspectRatio: false,
        // One mark only: each row is a model, and the harnesses are the bars
        // within it rather than a property of the row.
        layout: { padding: { left: iconGutter(1), right: pad } },
        plugins: {
            legend: { display: false },   // rendered as HTML below, with the harness glyphs
            barValues: { color: textColor, format: v => formatMetric(metric, v) },
            setupIcons: { slots: 1, rowAt: (_tick, i) => groups[i] && { model: models[groups[i].model] } },
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
    }), [textColor, gridColor, groups, metric, models, pad]);

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
        <div>
            <div style={{ height: barCount * BAR_PX + CHROME_PX }}>
                <Bar data={data} options={options} plugins={[barValuePlugin, setupIconsPlugin]} role="img" aria-label={ariaLabel} />
            </div>
            {/* aria-hidden: the sr-only table below names the harness on every
                row, so a screen reader gets the mapping without this key. */}
            <ul aria-hidden="true" className="flex flex-wrap justify-center gap-x-5 gap-y-2 mt-3">
                {series.map(s => (
                    <li key={s.key} className="flex items-center gap-1.5 text-[11px] font-medium text-slate-600 dark:text-slate-300">
                        {s.harness ? <HarnessIcon harness={s.harness} /> : null}
                        <span className="w-2 h-2 rounded-full shrink-0" style={{ backgroundColor: s.color }} />
                        {s.label}
                    </li>
                ))}
            </ul>
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
