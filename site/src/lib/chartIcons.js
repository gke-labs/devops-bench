// Model and harness marks painted onto a chart canvas.
//
// The row labels and dot labels read "Alpha Pro × Gemini CLI · Baseline". That
// is accurate and it is slow to scan, because the eye has to read to the fourth
// word before the runner is known. The same marks the leaderboard rows carry put
// the model and the runner ahead of the text.
//
// Chart.js has no notion of an image tick or an image label, so the glyphs are
// redrawn with the canvas 2D API from the path data the SVG components use —
// one definition in Logo.jsx, two ways of painting it.

import { Chart } from "chart.js";
import { BRANDS, HARNESS_PATHS, MODEL_PATHS } from "../components/Logo.jsx";

const GAP_PX = 4;
// Authoring viewBox of the harness paths.
const VIEWBOX = 24;
// Default mark size, used by the axis gutter. Dot labels ask for a smaller one.
export const MARK_PX = 14;

// Width to reserve as `layout.padding.left` for `slots` marks per row.
export const iconGutter = (slots, size = MARK_PX) => slots * (size + GAP_PX) + GAP_PX;

function drawModel(ctx, model, x, y, size) {
    const brand = BRANDS[model?.logo];
    if (!brand) return;
    const modelPath = MODEL_PATHS[model?.logo];

    ctx.save();
    if (modelPath) {
        ctx.translate(x, y);
        ctx.scale(size / modelPath.viewBox, size / modelPath.viewBox);
        if (modelPath.paths) {
            for (const p of modelPath.paths) {
                ctx.fillStyle = p.fill;
                ctx.fill(new Path2D(p.d));
            }
        } else {
            ctx.fillStyle = modelPath.fill ?? brand.fill ?? "#ffffff";
            ctx.fill(new Path2D(modelPath.path));
        }
    } else {
        // Fallback letter badge for synthetic/mock models (alpha, beta, gamma)
        ctx.fillStyle = brand.fill ?? "#64748b";
        ctx.beginPath();
        ctx.roundRect(x, y, size, size, size * 0.25);
        ctx.fill();
        ctx.fillStyle = "#ffffff";
        ctx.font = `bold ${Math.round(size * 0.6)}px system-ui, sans-serif`;
        ctx.textAlign = "center";
        ctx.textBaseline = "middle";
        ctx.fillText(brand.letter, x + size / 2, y + size / 2);
    }
    ctx.restore();
}

function getHarnessLogo(harness) {
    if (!harness) return undefined;
    const name = harness.name?.toLowerCase();
    if (name === "antigravity" || harness.logo === "google") {
        return "google";
    }
    if (name === "claude code" || harness.logo === "anthropic") {
        return "anthropic";
    }
    return harness.logo;
}

function hasHarnessIcon(harness) {
    const logo = getHarnessLogo(harness);
    return Boolean(HARNESS_PATHS[logo] || MODEL_PATHS[logo] || BRANDS[logo]);
}

function drawHarness(ctx, harness, x, y, size) {
    const logo = getHarnessLogo(harness);
    const effectiveHarness = logo !== harness?.logo ? { ...harness, logo } : harness;
    if (MODEL_PATHS[logo] || BRANDS[logo]) {
        drawModel(ctx, effectiveHarness, x, y, size);
        return;
    }
    const paths = HARNESS_PATHS[logo];
    if (!paths) return;
    ctx.save();
    ctx.translate(x, y);
    ctx.scale(size / VIEWBOX, size / VIEWBOX);
    ctx.strokeStyle = harness.accent;
    ctx.lineWidth = 2;
    ctx.lineCap = "round";
    ctx.lineJoin = "round";
    for (const d of paths) ctx.stroke(new Path2D(d));
    ctx.restore();
}

/** Width `drawMarks` would take, for a caller that must lay out before it paints. */
export function marksWidth({ model, harness }, size = MARK_PX) {
    return (BRANDS[model?.logo] ? size + GAP_PX : 0) + (hasHarnessIcon(harness) ? size + GAP_PX : 0);
}

/**
 * Paints the marks left-to-right from (x, y), the top-left of the first one.
 * Either may be absent — a legend keyed on harness has no model to draw.
 *
 * @returns {number} the width taken, so a caller drawing text after it knows
 *          where the text starts.
 */
export function drawMarks(ctx, { model, harness }, x, y, size = MARK_PX) {
    let dx = 0;
    if (BRANDS[model?.logo]) {
        drawModel(ctx, model, x, y, size);
        dx += size + GAP_PX;
    }
    if (hasHarnessIcon(harness)) {
        drawHarness(ctx, harness, x + dx, y, size);
        dx += size + GAP_PX;
    }
    return dx;
}

/**
 * Draws the axis gutter. Configure with `plugins.setupIcons`:
 *
 *   rowAt  (tick, index) => ({ model, harness }) — either may be undefined, and
 *          returning nothing leaves that row blank, so a chart whose axis is not
 *          one-setup-per-row can still use the ones it has.
 *   slots  how many marks wide the gutter is; must match `iconGutter(slots)` in
 *          `layout.padding.left`, or the marks land on top of the labels.
 */
export const setupIconsPlugin = {
    id: "setupIcons",
    afterDraw(chart, _args, opts) {
        const scale = chart.scales.y;
        if (!opts?.rowAt || !scale?.ticks?.length) return;
        const { ctx } = chart;
        const left = scale.left - iconGutter(opts.slots ?? 2) + GAP_PX;
        scale.ticks.forEach((tick, i) => {
            const row = opts.rowAt(tick, i);
            if (row) drawMarks(ctx, row, left, scale.getPixelForTick(i) - MARK_PX / 2);
        });
    }
};

// Legend size, matched to the 11px legend font.
const LEGEND_MARK_PX = 12;
// Blank swatch width reserved per legend item: the colour dot, then the mark.
export const LEGEND_BOX_PX = 10 + LEGEND_MARK_PX + GAP_PX * 2;

/**
 * Blanks the native legend swatch so `legendMarksPlugin` can paint the slot
 * itself. Chart.js still owns the layout, the text and the click-to-hide, which
 * an HTML legend would have cost.
 */
export function markedLegendLabels(chart) {
    const items = Chart.defaults.plugins.legend.labels.generateLabels(chart);
    for (const item of items) item.fillStyle = item.strokeStyle = "transparent";
    return items;
}

/**
 * Paints each legend item's colour dot and mark. Configure with
 * `plugins.legendMarks.markAt: (item, index) => ({ model, harness, color })`.
 */
export const legendMarksPlugin = {
    id: "legendMarks",
    afterDraw(chart, _args, opts) {
        const boxes = chart.legend?.legendHitBoxes;
        if (!opts?.markAt || !boxes?.length) return;
        const { ctx } = chart;
        chart.legend.legendItems.forEach((item, i) => {
            const mark = opts.markAt(item, i);
            const box = boxes[i];
            if (!mark || !box) return;
            ctx.save();
            // Hidden series are struck through by Chart.js; fade to match, so
            // the mark does not read as the one live entry in a muted row.
            if (item.hidden) ctx.globalAlpha = 0.35;
            if (mark.color) {
                ctx.fillStyle = mark.color;
                ctx.beginPath();
                ctx.arc(box.left + 4, box.top + box.height / 2, 4, 0, Math.PI * 2);
                ctx.fill();
            }
            drawMarks(ctx, mark, box.left + 8 + GAP_PX, box.top + (box.height - LEGEND_MARK_PX) / 2, LEGEND_MARK_PX);
            ctx.restore();
        });
    }
};
