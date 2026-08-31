import { describe, it, expect } from "vitest";
import {
    setupScore,
    setupHistory,
    allRunDates,
    formatRunDate,
    setupLabel,
    setupTags,
    yAxisBounds
} from "./accessors.js";

const models = { "alpha-pro": { name: "Alpha Pro" } };
const harnesses = { "gemini-cli": { name: "Gemini CLI" } };

function makeSetup(overrides = {}) {
    return {
        id: "alpha-pro-gemini-cli",
        model: "alpha-pro",
        harness: "gemini-cli",
        augmentation: [],
        color: "#3b82f6",
        tasks: [
            { folder: "a", name: "A", scores: { pass1: 90, pass5: 95, passMax: 100 } },
            { folder: "b", name: "B", scores: { pass1: 80, pass5: 85, passMax: 90 } }
        ],
        history: [
            { t: "2026-02-15T00:00:00Z", scores: { pass1: 70, pass5: 75, passMax: 80 } },
            { t: "2026-01-15T00:00:00Z", scores: { pass1: 60, pass5: 65, passMax: 70 } }
        ],
        ...overrides
    };
}

describe("setupScore", () => {
    it("is the mean over tasks for the metric", () => {
        expect(setupScore(makeSetup(), "pass1")).toBe(85); // (90+80)/2
    });

    it("ignores tasks with no score for the metric (null-safe)", () => {
        const s = makeSetup({
            tasks: [
                { folder: "a", name: "A", scores: { pass1: 90 } },
                { folder: "b", name: "B", scores: { pass1: null } }
            ]
        });
        expect(setupScore(s, "pass1")).toBe(90);
    });

    it("returns null when no task has a score", () => {
        const s = makeSetup({ tasks: [{ folder: "a", name: "A", scores: {} }] });
        expect(setupScore(s, "pass1")).toBeNull();
    });
});

describe("setupHistory", () => {
    it("maps each point to {x: epoch ms, y: score}", () => {
        const pts = setupHistory(makeSetup(), "pass1");
        expect(pts).toEqual([
            { x: Date.parse("2026-02-15T00:00:00Z"), y: 70 },
            { x: Date.parse("2026-01-15T00:00:00Z"), y: 60 }
        ]);
    });
});

describe("allRunDates", () => {
    it("returns the sorted union of run timestamps across setups", () => {
        const a = makeSetup();
        const b = makeSetup({
            history: [{ t: "2026-03-15T00:00:00Z", scores: { pass1: 1, pass5: 1, passMax: 1 } }]
        });
        expect(allRunDates([a, b])).toEqual([
            "2026-01-15T00:00:00Z",
            "2026-02-15T00:00:00Z",
            "2026-03-15T00:00:00Z"
        ]);
    });
});

describe("formatRunDate", () => {
    it("formats as yyyy-mm-dd pinned to UTC", () => {
        // Midnight UTC must not roll back a day in negative-offset locales.
        expect(formatRunDate("2026-01-15T00:00:00Z")).toBe("2026-01-15");
        expect(formatRunDate(Date.parse("2026-06-01T00:00:00Z"))).toBe("2026-06-01");
    });
});

describe("setupLabel", () => {
    it("leads with model × harness, then 'Baseline' when augmentation is empty", () => {
        expect(setupLabel(makeSetup(), models, harnesses)).toBe("Alpha Pro × Gemini CLI · Baseline");
    });

    it("appends one segment per augmentation token", () => {
        const s = makeSetup({ augmentation: ["mcp", "skills"] });
        expect(setupLabel(s, models, harnesses)).toBe("Alpha Pro × Gemini CLI · MCP · Skills");
    });

    it("title-cases unknown augmentation tokens", () => {
        const s = makeSetup({ augmentation: ["rules"] });
        expect(setupLabel(s, models, harnesses)).toBe("Alpha Pro × Gemini CLI · Rules");
    });
});

describe("setupTags", () => {
    it("returns a single 'Baseline' chip when augmentation is empty", () => {
        expect(setupTags(makeSetup()).map(t => t.text)).toEqual(["Baseline"]);
    });

    it("returns one chip per augmentation token", () => {
        expect(setupTags(makeSetup({ augmentation: ["mcp", "skills"] })).map(t => t.text)).toEqual(["MCP", "Skills"]);
    });
});

describe("yAxisBounds", () => {
    it("fits the plotted scores, padded by 5 and snapped to tens", () => {
        // makeSetup() history pass1 = {70, 60} → pad to [55, 75] → snap to [50, 80].
        expect(yAxisBounds([makeSetup()], "pass1")).toEqual({ min: 50, max: 80 });
    });

    it("clamps to [0, 100] so low and high scores are never clipped", () => {
        const low = makeSetup({ history: [{ t: "2026-01-15T00:00:00Z", scores: { pass1: 3 } }] });
        expect(yAxisBounds([low], "pass1")).toEqual({ min: 0, max: 10 });   // 3% stays visible
        const high = makeSetup({ history: [{ t: "2026-01-15T00:00:00Z", scores: { pass1: 99 } }] });
        expect(yAxisBounds([high], "pass1")).toEqual({ min: 90, max: 100 });
    });

    it("falls back to the full 0..100 range when there are no scored points", () => {
        expect(yAxisBounds([makeSetup({ history: [] })], "pass1")).toEqual({ min: 0, max: 100 });
        const allNull = makeSetup({ history: [{ t: "2026-01-15T00:00:00Z", scores: { pass1: null } }] });
        expect(yAxisBounds([allNull], "pass1")).toEqual({ min: 0, max: 100 });
    });

    describe("absolute metrics", () => {
        const withHistory = (metric, values) => makeSetup({
            history: values.map((v, i) => ({
                t: `2026-0${i + 1}-15T00:00:00Z`,
                scores: { [metric]: v }
            }))
        });

        it("follows the data instead of clamping to 100", () => {
            // Token means run to five figures; a [0, 100] clamp would push every
            // series off the top of the chart.
            const b = yAxisBounds([withHistory("outputTokens", [23200, 24100, 25200])], "outputTokens");
            expect(b.min).toBeGreaterThan(100);
            expect(b.min).toBeLessThan(23200);
            expect(b.max).toBeGreaterThan(25200);
        });

        it("snaps the endpoints to a round step so no stray label crowds a gridline", () => {
            // Raw padding gave [45.3, 54.7], printing "54.8s" against "54.0s".
            expect(yAxisBounds([withHistory("latency", [47.9, 50.1, 52.2])], "latency"))
                .toEqual({ min: 44, max: 56 });
            expect(yAxisBounds([withHistory("outputTokens", [23200, 24100, 25200])], "outputTokens"))
                .toEqual({ min: 21000, max: 27000 });
        });

        it("scales the step to the magnitude rather than assuming tens", () => {
            // Sub-minute latencies need a fractional step; tokens need thousands.
            const small = yAxisBounds([withHistory("latency", [2.1, 2.4])], "latency");
            expect(small).toEqual({ min: 1, max: 3.5 });
        });

        it("keeps a non-zero height for a single data point", () => {
            const b = yAxisBounds([withHistory("latency", [50])], "latency");
            expect(b.max).toBeGreaterThan(b.min);
        });

        it("never drops the axis below zero", () => {
            const b = yAxisBounds([withHistory("latency", [0.5])], "latency");
            expect(b.min).toBeGreaterThanOrEqual(0);
        });
    });
});
