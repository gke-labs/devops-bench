import { describe, it, expect, vi } from "vitest";
import { barValuePlugin } from "./RankedBarChart.jsx";

// Chart.js hands the plugin a live canvas; jsdom has none, so drive it with a
// stub that records what was drawn where. What is under test is the text and
// its position, not the pixels.
function stubChart({ values, bars, hidden = false }) {
    const drawn = [];
    return {
        drawn,
        chart: {
            ctx: {
                save() {}, restore() {},
                fillText: (text, x, y) => drawn.push({ text, x, y })
            },
            data: { datasets: [{ data: values }] },
            getDatasetMeta: () => ({ hidden, data: bars })
        }
    };
}

const opts = { color: "#64748b", format: v => `$${v.toFixed(2)}` };

describe("barValuePlugin", () => {
    it("prints each bar's value past the end of the bar", () => {
        // The axis ticks only bracket a bar; reading $0.31 off one sitting
        // between the $0.20 and $0.40 gridlines is a guess.
        const { chart, drawn } = stubChart({
            values: [0.31, 0.4],
            bars: [{ x: 120, y: 20 }, { x: 155, y: 50 }]
        });
        barValuePlugin.afterDatasetsDraw(chart, {}, opts);
        expect(drawn.map(d => d.text)).toEqual(["$0.31", "$0.40"]);
        // Past the bar end, not on top of it.
        expect(drawn[0].x).toBeGreaterThan(120);
        expect(drawn[1].x).toBeGreaterThan(155);
        // On the bar's own row.
        expect(drawn.map(d => d.y)).toEqual([20, 50]);
    });

    it("draws nothing when the dataset is hidden", () => {
        const { chart, drawn } = stubChart({
            values: [0.31],
            bars: [{ x: 120, y: 20 }],
            hidden: true
        });
        barValuePlugin.afterDatasetsDraw(chart, {}, opts);
        expect(drawn).toEqual([]);
    });
});
