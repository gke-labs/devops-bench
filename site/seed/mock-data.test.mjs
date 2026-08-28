import { describe, it, expect } from "vitest";
import { generateRaw, derive, passAtK, PASS_THRESHOLD, sumTokens, latencyOf } from "./mock-data.mjs";

describe("sumTokens", () => {
    it("prefers the producer's own total over the buckets", () => {
        expect(sumTokens({ totalTokens: 993225, inputTokens: 135329, outputTokens: 9732 })).toBe(993225);
    });

    it("sums the captured buckets when no total is reported", () => {
        // reasoningTokens is a sibling of output, not a subset, so it is added.
        expect(sumTokens({ inputTokens: 100, outputTokens: 20, reasoningTokens: 5 })).toBe(125);
    });

    it("is null when no usage was captured at all", () => {
        expect(sumTokens({ inputTokens: null, outputTokens: null })).toBeNull();
        expect(sumTokens({})).toBeNull();
    });

    // Regression: antigravity's parser returns {input: 0, output: 0, total: 0,
    // cached: 0} for an empty session log (parsing.py) and normalize.py coerces
    // those through as ints rather than nulls. Reporting a real 0 would rank
    // that setup FIRST on a lower-is-better metric with a full bar — the same
    // failure latencyOf() guards against.
    it("treats an all-zero usage record as unmeasured, not as zero tokens", () => {
        expect(sumTokens({ inputTokens: 0, outputTokens: 0, cachedTokens: 0, totalTokens: 0 })).toBeNull();
        expect(latencyOf({ latencySec: 0 })).toBeNull();
    });

    it("falls through to the buckets when only the total is zeroed", () => {
        expect(sumTokens({ totalTokens: 0, inputTokens: 400, outputTokens: 100 })).toBe(500);
    });
});

describe("passAtK", () => {
    it("is 0 when there are no passes", () => {
        expect(passAtK(20, 0, 5)).toBe(0);
    });

    it("is 1 when fewer than k failures exist", () => {
        // n-c = 2 < k = 5 → every 5-subset must contain a pass.
        expect(passAtK(20, 18, 5)).toBe(1);
    });

    it("is monotonic non-decreasing in k for fixed (n, c)", () => {
        const n = 20, c = 8;
        let prev = -1;
        for (let k = 1; k <= n; k++) {
            const v = passAtK(n, c, k);
            expect(v).toBeGreaterThanOrEqual(prev);
            prev = v;
        }
    });

    it("equals c/n at k=1", () => {
        expect(passAtK(20, 9, 1)).toBeCloseTo(9 / 20, 10);
    });
});

describe("generateRaw", () => {
    it("is deterministic across calls", () => {
        expect(generateRaw()).toEqual(generateRaw());
    });

    it("produces continuous outcomeScores in [0,1]", () => {
        const raw = generateRaw();
        expect(raw.length).toBeGreaterThan(0);
        for (const r of raw) {
            expect(r.outcomeScore).toBeGreaterThanOrEqual(0);
            expect(r.outcomeScore).toBeLessThanOrEqual(1);
            expect(typeof r.iteration).toBe("number");
        }
    });
});

describe("derive", () => {
    const raw = generateRaw();
    const setups = derive(raw);

    it("produces 8 setups, each with 12 tasks", () => {
        expect(setups).toHaveLength(8);
        for (const s of setups) expect(s.tasks).toHaveLength(12);
    });

    it("yields a numeric pass1 and null pass5/passMax per task (pass1-only today)", () => {
        for (const s of setups) {
            for (const t of s.tasks) {
                expect(typeof t.scores.pass1).toBe("number");
                expect(t.scores.pass5).toBeNull();
                expect(t.scores.passMax).toBeNull();
            }
        }
    });

    it("orders history by time ascending", () => {
        for (const s of setups) {
            const times = s.history.map(h => Date.parse(h.t));
            const sorted = [...times].sort((a, b) => a - b);
            expect(times).toEqual(sorted);
        }
    });

    it("derives tasks[].pass1 from the latest run's raw rows", () => {
        const s = setups[0];
        const latest = [...new Set(raw.filter(r => r.setupId === s.id).map(r => r.t))].sort().pop();
        const folder = s.tasks[0].folder;
        const cell = raw.filter(r => r.setupId === s.id && r.t === latest && r.taskFolder === folder);
        // pass1 now thresholds on correctness `c` (not the composite outcomeScore).
        const c = cell.filter(r => r.correctnessScore >= PASS_THRESHOLD).length;
        expect(s.tasks[0].scores.pass1).toBeCloseTo((100 * c) / cell.length, 1);
    });

    it("treats an all-unscored task cell as missing data (null scores), not 0 or NaN", () => {
        // Mirrors ingest/derive.test.mjs. pass1 is a rate over SCORED iterations
        // (PROTOCOL.md §4), so a cell whose iterations all failed to score has no
        // rate to report. Regression guard: without the n===0 check, c/n divides
        // by zero and pass1 comes back NaN.
        const s = setups[0];
        const folder = s.tasks[0].folder;
        const latest = [...new Set(raw.filter(r => r.setupId === s.id).map(r => r.t))].sort().pop();
        const blanked = raw.map(r =>
            r.setupId === s.id && r.t === latest && r.taskFolder === folder
                ? { ...r, outcomeScore: null, correctnessScore: null, recoverableSafetyScore: null }
                : r
        );
        const task = derive(blanked)
            .find(x => x.id === s.id)
            .tasks.find(t => t.folder === folder);
        expect(task.scores).toMatchObject({
            pass1: null,
            pass5: null,
            passMax: null,
            composite: null,
            correctness: null,
            recoverableSafety: null
        });
        // Efficiency is telemetry, not a score: the blanked cell still consumed
        // wall-clock and tokens, so those survive while every score is null.
        expect(task.scores.latency).toBeGreaterThan(0);
        expect(task.scores.tokens).toBeGreaterThan(0);
    });
});
