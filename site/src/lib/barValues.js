// The number printed past the end of a horizontal bar.
//
// A bar shows a ratio at a glance but never the number, and the axis ticks only
// bracket it — reading "$0.31" off a bar sitting between the $0.20 and $0.40
// gridlines is a guess. Every horizontal bar chart on the dashboard prints its
// values the same way, from here, so they line up and read as one convention.

export const VALUE_FONT_PX = 11;
export const VALUE_GAP = 6;
// Rough advance width per character at the value font. Used to reserve the
// right margin before Chart.js lays out, when there is no ctx to measure with.
const VALUE_CHAR_PX = VALUE_FONT_PX * 0.62;

export const VALUE_FONT = `600 ${VALUE_FONT_PX}px system-ui, sans-serif`;

/**
 * Right margin the printed values need. Without it the longest bar's value is
 * drawn past the canvas edge and clipped — and that is the top bar, the one the
 * chart exists to show.
 *
 * @param {string[]} texts Every value as it will be printed.
 */
export function valuePad(texts) {
    if (!texts.length) return 0;
    return Math.max(...texts.map(t => t.length)) * VALUE_CHAR_PX + VALUE_GAP + 4;
}

export const barValuePlugin = {
    id: "barValues",
    afterDatasetsDraw(chart, _args, opts) {
        const { ctx } = chart;
        ctx.save();
        ctx.font = VALUE_FONT;
        ctx.fillStyle = opts.color;
        ctx.textAlign = "left";
        ctx.textBaseline = "middle";
        chart.data.datasets.forEach((dataset, di) => {
            const meta = chart.getDatasetMeta(di);
            if (meta.hidden) return;
            meta.data.forEach((bar, i) => {
                const value = dataset.data[i];
                // A grouped chart leaves a gap where one series has no bar, and
                // a gap has no number to print against it.
                if (value == null) return;
                ctx.fillText(opts.format(value), bar.x + VALUE_GAP, bar.y);
            });
        });
        ctx.restore();
    }
};
