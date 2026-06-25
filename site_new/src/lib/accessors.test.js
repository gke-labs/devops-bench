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
        id: "alpha-pro-gemini-cli-baseline",
        model: "alpha-pro",
        harness: "gemini-cli",
        mcp: false,
        augmentation: "baseline",
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
    it("leads with model × harness, then modifiers", () => {
        expect(setupLabel(makeSetup(), models, harnesses)).toBe("Alpha Pro × Gemini CLI · Baseline");
    });

    it("appends MCP and GCA when set", () => {
        const s = makeSetup({ mcp: true, augmentation: "gca" });
        expect(setupLabel(s, models, harnesses)).toBe("Alpha Pro × Gemini CLI · GCA + Skills · MCP");
    });
});

describe("setupTags", () => {
    it("returns the augmentation chip only when no MCP", () => {
        expect(setupTags(makeSetup()).map(t => t.text)).toEqual(["Baseline"]);
    });

    it("adds an MCP chip when mcp is true", () => {
        expect(setupTags(makeSetup({ mcp: true })).map(t => t.text)).toEqual(["Baseline", "MCP"]);
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
});
