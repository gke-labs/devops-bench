import { describe, it, expect } from "vitest";
import {
    formatMetric,
    isLowerBetter,
    metricBarFraction,
    metricMeta,
    bestValue,
    METRICS,
    METRIC_LABELS,
    metricDescription
} from "./vocab.js";

describe("metric presentation rules", () => {
    it("treats quality metrics as higher-is-better percentages", () => {
        for (const m of ["composite", "correctness", "recoverableSafety", "pass1"]) {
            expect(metricMeta(m).percentage).toBe(true);
            expect(isLowerBetter(m)).toBe(false);
        }
    });

    it("treats efficiency metrics as lower-is-better magnitudes", () => {
        for (const m of ["latency", "inputTokens", "outputTokens", "cachedTokens"]) {
            expect(metricMeta(m).percentage).toBe(false);
            expect(isLowerBetter(m)).toBe(true);
        }
    });

    it("keeps the token buckets on separate axes, never summed into one", () => {
        // The buckets are billed at different rates, so a single combined
        // metric reports whichever happens to be largest. Guard the vocabulary
        // against a combined key creeping back in.
        expect(METRICS).toEqual(expect.arrayContaining(["inputTokens", "outputTokens", "cachedTokens"]));
        expect(METRICS).not.toContain("tokens");
        // Each carries its own label and its own explanation.
        const labels = ["inputTokens", "outputTokens", "cachedTokens"].map(m => METRIC_LABELS[m]);
        expect(new Set(labels).size).toBe(3);
        const notes = ["inputTokens", "outputTokens", "cachedTokens"].map(metricDescription);
        expect(new Set(notes).size).toBe(3);
    });

    it("defaults an unknown metric to the percentage rules", () => {
        expect(metricMeta("nope").percentage).toBe(true);
    });
});

describe("formatMetric", () => {
    it("keeps one decimal on percentages so the column width is stable", () => {
        expect(formatMetric("composite", 90)).toBe("90.0%");
        expect(formatMetric("composite", 85.44)).toBe("85.4%");
    });

    it("renders latency in seconds and compacts large token counts", () => {
        expect(formatMetric("latency", 42.66)).toBe("42.7s");
        expect(formatMetric("latency", 8)).toBe("8.0s");
        expect(formatMetric("outputTokens", 38412)).toBe("38.4k");
        expect(formatMetric("outputTokens", 850)).toBe("850");
    });

    it("renders a missing value as an em dash, never as zero", () => {
        expect(formatMetric("latency", null)).toBe("—");
        expect(formatMetric("composite", undefined)).toBe("—");
        expect(formatMetric("outputTokens", NaN)).toBe("—");
    });
});

describe("metricBarFraction", () => {
    it("maps a percentage straight onto the bar", () => {
        expect(metricBarFraction("composite", 75, null)).toBeCloseTo(0.75);
    });

    it("scales an absolute metric as a ratio to the best value on screen", () => {
        // Best (fastest) is 10s: it earns a full bar, and twice as slow is half.
        expect(metricBarFraction("latency", 10, 10)).toBeCloseTo(1);
        expect(metricBarFraction("latency", 20, 10)).toBeCloseTo(0.5);
        expect(metricBarFraction("latency", 100, 10)).toBeCloseTo(0.1);
    });

    it("gives the only visible setup a full bar, not a sliver", () => {
        // Regression: filtering down to one row made value === the scale, which
        // previously floored the bar at 2% for the fastest setup on screen.
        expect(metricBarFraction("latency", 42, 42)).toBeCloseTo(1);
        expect(metricBarFraction("outputTokens", 38412, 38412)).toBeCloseTo(1);
    });

    it("keeps near-equal values near-equal instead of full vs empty", () => {
        // Regression: min..max normalization would render these 1.0 and 0.0,
        // turning a 1% gap into the whole bar width.
        expect(metricBarFraction("latency", 99, 99)).toBeCloseTo(1);
        expect(metricBarFraction("latency", 100, 99)).toBeCloseTo(0.99, 2);
    });

    it("is empty for a missing value or an unusable scale", () => {
        expect(metricBarFraction("latency", null, 100)).toBe(0);
        expect(metricBarFraction("latency", 10, null)).toBe(0);
        // 0 is the unmeasured sentinel, not an instant run — no bar for it.
        expect(metricBarFraction("latency", 0, 10)).toBe(0);
        expect(metricBarFraction("latency", 10, 0)).toBe(0);
    });
});

describe("bestValue", () => {
    it("takes the smallest for a lower-is-better metric and the largest otherwise", () => {
        expect(bestValue("latency", [30, 10, 20])).toBe(10);
        expect(bestValue("outputTokens", [300, 100, 200])).toBe(100);
        expect(bestValue("composite", [30, 10, 20])).toBe(30);
    });

    it("skips nulls and non-finite entries", () => {
        expect(bestValue("latency", [null, 30, undefined, NaN, 20])).toBe(20);
        expect(bestValue("latency", [null, undefined])).toBeNull();
        expect(bestValue("latency", [])).toBeNull();
    });

    // Regression: an unmeasured run normalizes to 0 rather than null, and the
    // min would then be 0. metricBarFraction bails on `best <= 0`, so that one
    // row would empty EVERY bar in the column instead of only its own.
    it("ignores the 0 sentinel so one unmeasured row cannot flatten the column", () => {
        expect(bestValue("outputTokens", [0, 5000, 20000])).toBe(5000);
        expect(bestValue("latency", [0, 42])).toBe(42);
        expect(metricBarFraction("outputTokens", 20000, bestValue("outputTokens", [0, 5000, 20000]))).toBeCloseTo(0.25);
    });

    it("is null when every lower-is-better reading is the sentinel", () => {
        expect(bestValue("outputTokens", [0, 0])).toBeNull();
    });

    // A percentage metric legitimately bottoms out at 0 (a 0% pass rate), so the
    // non-positive filter must not apply on that side.
    it("keeps a genuine 0 for a higher-is-better metric", () => {
        expect(bestValue("composite", [0, 0])).toBe(0);
    });
});
