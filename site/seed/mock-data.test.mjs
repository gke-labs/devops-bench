import { describe, it, expect } from "vitest";
import { generateRaw, derive, passAtK, PASS_THRESHOLD } from "./mock-data.mjs";

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
        const c = cell.filter(r => r.outcomeScore >= PASS_THRESHOLD).length;
        expect(s.tasks[0].scores.pass1).toBeCloseTo((100 * c) / cell.length, 1);
    });
});
