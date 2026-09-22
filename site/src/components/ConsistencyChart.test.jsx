import { describe, it, expect } from "vitest";
import { spreadMarkerPlugin } from "./ConsistencyChart.jsx";

// jsdom has no canvas, so the drawing goes to a recorder. What is under test is
// the geometry of the box plot's furniture — where each whisker, cap and median
// lands — not the pixels.
function fakeCtx() {
    const calls = [];
    return {
        calls,
        save() {}, restore() {}, beginPath() {}, stroke() {}, fillText() {},
        moveTo(x, y) { calls.push(["moveTo", x, y]); },
        lineTo(x, y) { calls.push(["lineTo", x, y]); }
    };
}

// One pixel per unit, so an asserted coordinate reads as the value it came from.
const chartWith = ctx => ({
    ctx,
    scales: { x: { getPixelForValue: v => v } },
    getDatasetMeta: () => ({ data: [{ y: 100, height: 20 }] })
});

const row = { min: 10, q1: 40, median: 50, q3: 60, max: 90, color: "#f00" };

const segments = ctx => {
    const out = [];
    for (let i = 0; i < ctx.calls.length; i += 2) out.push([...ctx.calls[i].slice(1), ...ctx.calls[i + 1].slice(1)]);
    return out;
};

describe("spreadMarkerPlugin", () => {
    it("caps each whisker at the extreme task, not at the box edge", () => {
        const ctx = fakeCtx();
        spreadMarkerPlugin.afterDatasetsDraw(chartWith(ctx), {}, { rows: [row], metric: "cost" });
        expect(segments(ctx)).toEqual([
            // Lower whisker: box edge out to the best task, capped there at
            // half the box height.
            [40, 100, 10, 100],
            [10, 95, 10, 105],
            // Upper whisker: box edge out to the worst task, capped there. A cap
            // drawn at q3 instead would sit on the box border and leave the far
            // end of the whisker running off into nothing.
            [60, 100, 90, 100],
            [90, 95, 90, 105],
            // Median, full box height.
            [50, 90, 50, 110]
        ]);
    });

    it("draws nothing when the dataset is hidden or has no rows", () => {
        const hidden = fakeCtx();
        spreadMarkerPlugin.afterDatasetsDraw(
            { ...chartWith(hidden), getDatasetMeta: () => ({ data: [], hidden: true }) },
            {},
            { rows: [row], metric: "cost" }
        );
        expect(hidden.calls).toEqual([]);

        const empty = fakeCtx();
        spreadMarkerPlugin.afterDatasetsDraw(chartWith(empty), {}, { rows: [], metric: "cost" });
        expect(empty.calls).toEqual([]);
    });
});
