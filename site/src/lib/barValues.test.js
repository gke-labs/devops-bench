import { describe, it, expect } from "vitest";
import { barValuePlugin, valuePad } from "./barValues.js";

// Chart.js hands the plugin a live canvas; jsdom has none, so drive it with a
// stub that records what was drawn where. What is under test is the text and
// its position, not the pixels.
function stubChart({ datasets, hidden = [] }) {
    const drawn = [];
    return {
        drawn,
        chart: {
            ctx: {
                save() {}, restore() {},
                fillText: (text, x, y) => drawn.push({ text, x, y })
            },
            data: { datasets: datasets.map(d => ({ data: d.values })) },
            getDatasetMeta: i => ({ hidden: hidden.includes(i), data: datasets[i].bars })
        }
    };
}

const opts = { color: "#64748b", format: v => `$${v.toFixed(2)}` };

describe("barValuePlugin", () => {
    it("prints each bar's value past the end of the bar", () => {
        // The axis ticks only bracket a bar; reading $0.31 off one sitting
        // between the $0.20 and $0.40 gridlines is a guess.
        const { chart, drawn } = stubChart({
            datasets: [{ values: [0.31, 0.4], bars: [{ x: 120, y: 20 }, { x: 155, y: 50 }] }]
        });
        barValuePlugin.afterDatasetsDraw(chart, {}, opts);
        expect(drawn.map(d => d.text)).toEqual(["$0.31", "$0.40"]);
        // Past the bar end, not on top of it.
        expect(drawn[0].x).toBeGreaterThan(120);
        expect(drawn[1].x).toBeGreaterThan(155);
        // On the bar's own row.
        expect(drawn.map(d => d.y)).toEqual([20, 50]);
    });

    it("labels every series of a grouped chart, not just the first", () => {
        // The harness comparison puts one dataset per runner, so stopping at
        // dataset 0 would number one bar of each pair and leave the other bare.
        const { chart, drawn } = stubChart({
            datasets: [
                { values: [0.31], bars: [{ x: 120, y: 20 }] },
                { values: [0.5], bars: [{ x: 180, y: 46 }] }
            ]
        });
        barValuePlugin.afterDatasetsDraw(chart, {}, opts);
        expect(drawn.map(d => d.text)).toEqual(["$0.31", "$0.50"]);
    });

    it("skips the gap where a series has no bar", () => {
        // A model that ran on only one harness leaves a null in the other
        // series, and a gap has no number to print against it.
        const { chart, drawn } = stubChart({
            datasets: [{ values: [null, 0.4], bars: [{ x: 0, y: 20 }, { x: 155, y: 50 }] }]
        });
        barValuePlugin.afterDatasetsDraw(chart, {}, opts);
        expect(drawn.map(d => d.text)).toEqual(["$0.40"]);
    });

    it("draws nothing for a hidden dataset", () => {
        const { chart, drawn } = stubChart({
            datasets: [{ values: [0.31], bars: [{ x: 120, y: 20 }] }],
            hidden: [0]
        });
        barValuePlugin.afterDatasetsDraw(chart, {}, opts);
        expect(drawn).toEqual([]);
    });
});

describe("valuePad", () => {
    it("reserves room for the longest value, so the top bar's is not clipped", () => {
        expect(valuePad(["$1.00", "$123.45"])).toBeGreaterThan(valuePad(["$1.00", "$2.00"]));
    });

    it("reserves nothing when there is nothing to print", () => {
        expect(valuePad([])).toBe(0);
    });
});
