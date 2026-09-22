import { describe, it, expect, beforeAll } from "vitest";
import { drawMarks, marksWidth, iconGutter, setupIconsPlugin, legendMarksPlugin, MARK_PX } from "./chartIcons.js";

// jsdom has no canvas, so the drawing goes to a recorder. What is under test is
// the geometry — where each mark lands and how wide it is — not the pixels.
beforeAll(() => {
    globalThis.Path2D = class { constructor(d) { this.d = d; } };
});

function fakeCtx() {
    const calls = [];
    const ctx = {
        calls,
        save() {}, restore() {}, beginPath() {}, fill() {}, translate(x, y) { calls.push(["translate", x, y]); },
        scale() {}, roundRect(x, y) { calls.push(["roundRect", x, y]); }, stroke() {}, arc(x, y) { calls.push(["arc", x, y]); },
        fillText() {},
        createLinearGradient() { return { addColorStop() {} }; }
    };
    return ctx;
}

const model = { logo: "alpha" };
const harness = { logo: "terminal", accent: "#0ea5e9" };

describe("marks", () => {
    it("reports the same width it goes on to draw", () => {
        const ctx = fakeCtx();
        expect(drawMarks(ctx, { model, harness }, 0, 0)).toBe(marksWidth({ model, harness }));
        // A layout pass that disagreed with the paint pass would either clip the
        // label text or leave a gap in front of it.
        expect(marksWidth({ model, harness }, 10)).toBe(2 * (10 + 4));
    });

    it("charges nothing for a mark it cannot draw", () => {
        // A model or harness the catalog does not carry, or one whose logo key
        // has no glyph: reserving width for it would indent the text past a
        // mark that never appears.
        expect(marksWidth({ model: { logo: "nope" }, harness })).toBe(marksWidth({ harness }));
        expect(marksWidth({})).toBe(0);
    });

    it("packs the harness after the model, both against the same left edge", () => {
        const ctx = fakeCtx();
        drawMarks(ctx, { model, harness }, 100, 20, 10);
        expect(ctx.calls).toEqual([["roundRect", 100, 20], ["translate", 114, 20]]);
        // Harness alone starts at the left edge rather than in the second slot.
        const solo = fakeCtx();
        drawMarks(solo, { harness }, 100, 20, 10);
        expect(solo.calls).toEqual([["translate", 100, 20]]);
    });

    it("draws vector logos for google, anthropic, and openai", () => {
        const googleCtx = fakeCtx();
        drawMarks(googleCtx, { model: { logo: "google" } }, 50, 10, 14);
        expect(googleCtx.calls).toEqual([["translate", 50, 10]]);

        const anthropicCtx = fakeCtx();
        drawMarks(anthropicCtx, { model: { logo: "anthropic" } }, 50, 10, 14);
        expect(anthropicCtx.calls).toEqual([["translate", 50, 10]]);

        const openaiCtx = fakeCtx();
        drawMarks(openaiCtx, { model: { logo: "openai" } }, 50, 10, 14);
        expect(openaiCtx.calls).toEqual([["translate", 50, 10]]);
    });

    it("draws vector logos for legacy gemini and claude keys", () => {
        const geminiCtx = fakeCtx();
        drawMarks(geminiCtx, { model: { logo: "gemini" } }, 50, 10, 14);
        expect(geminiCtx.calls).toEqual([["translate", 50, 10]]);

        const claudeCtx = fakeCtx();
        drawMarks(claudeCtx, { model: { logo: "claude" } }, 50, 10, 14);
        expect(claudeCtx.calls).toEqual([["translate", 50, 10]]);
    });

    it("draws vector logos for qwen and alibaba", () => {
        const qwenCtx = fakeCtx();
        drawMarks(qwenCtx, { model: { logo: "qwen" } }, 50, 10, 14);
        expect(qwenCtx.calls).toEqual([["translate", 50, 10]]);

        const alibabaCtx = fakeCtx();
        drawMarks(alibabaCtx, { model: { logo: "alibaba" } }, 50, 10, 14);
        expect(alibabaCtx.calls).toEqual([["translate", 50, 10]]);
    });

    it("draws brand vector logos when harness uses google or anthropic", () => {
        const agyCtx = fakeCtx();
        drawMarks(agyCtx, { harness: { logo: "google" } }, 50, 10, 14);
        expect(agyCtx.calls).toEqual([["translate", 50, 10]]);

        const claudeCtx = fakeCtx();
        drawMarks(claudeCtx, { harness: { logo: "anthropic" } }, 50, 10, 14);
        expect(claudeCtx.calls).toEqual([["translate", 50, 10]]);
    });
});

describe("setupIconsPlugin", () => {
    const chartWith = ticks => ({
        ctx: fakeCtx(),
        scales: {
            y: {
                left: 200,
                ticks,
                getPixelForTick: i => 50 + i * 30
            }
        }
    });

    it("puts one pair per tick in the gutter the layout reserved", () => {
        const chart = chartWith([{ value: 0 }, { value: 1 }]);
        setupIconsPlugin.afterDraw(chart, {}, { slots: 2, rowAt: () => ({ model, harness }) });
        const gutter = 200 - iconGutter(2) + 4;
        expect(chart.ctx.calls).toEqual([
            ["roundRect", gutter, 50 - MARK_PX / 2], ["translate", gutter + MARK_PX + 4, 50 - MARK_PX / 2],
            ["roundRect", gutter, 80 - MARK_PX / 2], ["translate", gutter + MARK_PX + 4, 80 - MARK_PX / 2]
        ]);
    });

    it("skips a tick with no row rather than shifting the ones that have one", () => {
        // The distribution strip's axis is linear, so a tick can fall between
        // rows; drawing the next row's marks there would mislabel it.
        const chart = chartWith([{ value: 0 }, { value: 1 }]);
        setupIconsPlugin.afterDraw(chart, {}, { slots: 2, rowAt: (_t, i) => (i ? { model, harness } : null) });
        expect(chart.ctx.calls.map(c => c[2])).toEqual([80 - MARK_PX / 2, 80 - MARK_PX / 2]);
    });

    it("draws nothing without a rowAt, so an unconfigured chart is unchanged", () => {
        const chart = chartWith([{ value: 0 }]);
        setupIconsPlugin.afterDraw(chart, {}, {});
        expect(chart.ctx.calls).toEqual([]);
    });
});

describe("legendMarksPlugin", () => {
    const chart = () => ({
        ctx: fakeCtx(),
        legend: {
            legendItems: [{ text: "Alpha Pro" }, { text: "Beta Sonic", hidden: true }],
            legendHitBoxes: [{ left: 10, top: 0, height: 12 }, { left: 90, top: 0, height: 12 }]
        }
    });

    it("paints the colour dot and the mark inside each item's own box", () => {
        const c = chart();
        legendMarksPlugin.afterDraw(c, {}, { markAt: () => ({ model, color: "#f00" }) });
        expect(c.ctx.calls).toEqual([
            ["arc", 14, 6], ["roundRect", 22, 0],
            ["arc", 94, 6], ["roundRect", 102, 0]
        ]);
    });

    it("leaves an item alone when the series behind it cannot be resolved", () => {
        const c = chart();
        legendMarksPlugin.afterDraw(c, {}, { markAt: item => (item.hidden ? null : { model }) });
        expect(c.ctx.calls).toEqual([["roundRect", 22, 0]]);
    });
});
