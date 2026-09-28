import { describe, it, expect } from "vitest";
import {
    generateRaw,
    derive,
    passAtK,
    passPowK,
    passKScores,
    PASS_THRESHOLD,
    PASSK_THRESHOLD,
    K,
    inputTokensOf,
    outputTokensOf,
    cachedTokensOf,
    latencyOf
} from "./mock-data.mjs";

describe("token axes", () => {
    // The whole point of the split: these three must never be summed into one
    // figure, so each has to pick up exactly its own billed-rate family.
    const row = {
        inputTokens: 100,
        cacheWriteTokens: 7,
        outputTokens: 20,
        reasoningTokens: 5,
        cachedTokens: 400
    };

    it("groups the buckets by billed rate, keeping the axes disjoint", () => {
        expect(inputTokensOf(row)).toBe(107);   // input + cache write
        expect(outputTokensOf(row)).toBe(25);   // output + reasoning
        expect(cachedTokensOf(row)).toBe(400);  // cache reads alone
    });

    it("counts reasoning as output, since it is a sibling bucket and not a subset", () => {
        // Dropping it would undercount every reasoning model on the one axis
        // that is billed at the highest rate.
        expect(outputTokensOf({ outputTokens: 20, reasoningTokens: 5 })).toBe(25);
        expect(outputTokensOf({ outputTokens: 20 })).toBe(20);
    });

    it("ignores a provider total, which cannot be attributed to an axis", () => {
        // sumTokens used to prefer totalTokens. A total says nothing about the
        // input/output split, so a row carrying only one reads as unmeasured
        // rather than being silently attributed to a single axis.
        const totalOnly = { totalTokens: 993225 };
        expect(inputTokensOf(totalOnly)).toBeNull();
        expect(outputTokensOf(totalOnly)).toBeNull();
        expect(cachedTokensOf(totalOnly)).toBeNull();
        // ...and a total alongside buckets never overrides them.
        expect(inputTokensOf({ totalTokens: 993225, inputTokens: 135329 })).toBe(135329);
    });

    it("keeps cache reads off the input axis", () => {
        // Only some harnesses report cache reads (134 of 260 fleet rows, none of
        // ours). Folding them into input would make a harness that reports them
        // look more expensive than one that stays silent.
        expect(inputTokensOf({ inputTokens: 100, cachedTokens: 400 })).toBe(100);
        expect(cachedTokensOf({ inputTokens: 100 })).toBeNull();
    });

    it("is null when the axis was never captured at all", () => {
        expect(inputTokensOf({ inputTokens: null })).toBeNull();
        expect(outputTokensOf({})).toBeNull();
        expect(cachedTokensOf({})).toBeNull();
    });

    // Regression: antigravity's parser returns {input: 0, output: 0, total: 0,
    // cached: 0} for an empty session log (parsing.py) and normalize.py coerces
    // those through as ints rather than nulls. Reporting a real 0 would rank
    // that setup FIRST on a lower-is-better metric with a full bar — the same
    // failure latencyOf() guards against.
    it("treats an all-zero usage record as unmeasured, not as zero tokens", () => {
        const zeroed = { inputTokens: 0, outputTokens: 0, cachedTokens: 0, totalTokens: 0 };
        expect(inputTokensOf(zeroed)).toBeNull();
        expect(outputTokensOf(zeroed)).toBeNull();
        expect(cachedTokensOf(zeroed)).toBeNull();
        expect(latencyOf({ latencySec: 0 })).toBeNull();
    });

    it("keeps an axis that was captured when a sibling axis is zeroed", () => {
        // A zeroed bucket is per-axis: output going quiet must not blank input.
        expect(inputTokensOf({ inputTokens: 400, outputTokens: 0 })).toBe(400);
        expect(outputTokensOf({ inputTokens: 400, outputTokens: 0 })).toBeNull();
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

describe("passPowK", () => {
    it("is 1 only when every attempt passed", () => {
        expect(passPowK(5, 5, 5)).toBe(1);
        expect(passPowK(20, 20, 5)).toBe(1);
    });

    it("is 0 when fewer passes than samples exist", () => {
        // c = 4 < k = 5 → every 5-subset must contain a failure.
        expect(passPowK(5, 4, 5)).toBe(0);
        expect(passPowK(20, 0, 5)).toBe(0);
    });

    it("matches C(c,k)/C(n,k) on a hand-computed case", () => {
        // C(5,5)/C(10,5) = 1/252.
        expect(passPowK(10, 5, 5)).toBeCloseTo(1 / 252, 10);
    });

    it("equals c/n at k=1, where 'all pass' and 'one passes' coincide", () => {
        expect(passPowK(20, 9, 1)).toBeCloseTo(9 / 20, 10);
        expect(passPowK(20, 9, 1)).toBeCloseTo(passAtK(20, 9, 1), 10);
    });

    it("never exceeds passAtK for the same (n, c, k)", () => {
        // "All k pass" is a sub-event of "at least one of k passes".
        for (let c = 0; c <= 20; c++) {
            expect(passPowK(20, c, 5)).toBeLessThanOrEqual(passAtK(20, c, 5));
        }
    });
});

describe("passKScores", () => {
    const attempt = outcomeScore => ({ outcomeScore });

    it("is null below K scored attempts — no estimate beats extrapolation", () => {
        const four = Array.from({ length: K - 1 }, () => attempt(1.0));
        expect(passKScores(four)).toEqual({ pass5: null, passMax: null });
        expect(passKScores([])).toEqual({ pass5: null, passMax: null });
    });

    it("treats unscored attempts as missing data, not failures", () => {
        // 5 perfect + 1 unscored: the null drops out of n entirely.
        const rows = [...Array.from({ length: 5 }, () => attempt(1.0)), attempt(null)];
        expect(passKScores(rows)).toEqual({ pass5: 100, passMax: 100 });
        // ...and if the null made n dip below K, the estimate disappears.
        expect(passKScores([...Array.from({ length: 4 }, () => attempt(1.0)), attempt(null)]))
            .toEqual({ pass5: null, passMax: null });
    });

    it("only a PERFECT outcomeScore counts as a pass", () => {
        // 0.9999 clears pass1's 0.7 bar but not the pass@k bar.
        const rows = Array.from({ length: 5 }, () => attempt(0.9999));
        expect(passKScores(rows)).toEqual({ pass5: 0, passMax: 0 });
        expect(PASSK_THRESHOLD).toBe(1.0);
    });

    it("pools attempts into the unbiased estimators, as percentages", () => {
        // n=10, c=5: pass@5 = 1 - C(5,5)/C(10,5), pass^5 = C(5,5)/C(10,5).
        const rows = [
            ...Array.from({ length: 5 }, () => attempt(1.0)),
            ...Array.from({ length: 5 }, () => attempt(0.4))
        ];
        expect(passKScores(rows)).toEqual({
            pass5: Math.round((1 - 1 / 252) * 1000) / 10,
            passMax: Math.round((1 / 252) * 1000) / 10
        });
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

    it("yields numeric pass1/pass5/passMax per task (every mock task has ≥K attempts)", () => {
        for (const s of setups) {
            for (const t of s.tasks) {
                expect(typeof t.scores.pass1).toBe("number");
                expect(typeof t.scores.pass5).toBe("number");
                expect(typeof t.scores.passMax).toBe("number");
                // Pass^5 ⊆ Pass@5: consistency can never exceed capability.
                expect(t.scores.passMax).toBeLessThanOrEqual(t.scores.pass5);
            }
        }
    });

    it("pools pass@k attempts across every run, not just the latest", () => {
        const s = setups[0];
        const folder = s.tasks[0].folder;
        const attempts = raw.filter(
            r => r.setupId === s.id && r.taskFolder === folder && Number.isFinite(r.outcomeScore)
        );
        const c = attempts.filter(r => r.outcomeScore >= PASSK_THRESHOLD).length;
        expect(s.tasks[0].scores.pass5).toBeCloseTo(100 * passAtK(attempts.length, c, K), 1);
        expect(s.tasks[0].scores.passMax).toBeCloseTo(100 * passPowK(attempts.length, c, K), 1);
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
            composite: null,
            correctness: null,
            recoverableSafety: null
        });
        // pass@k pools attempts across EVERY run, so blanking the latest run's
        // cell only shrinks n — earlier runs still provide ≥K scored attempts.
        expect(typeof task.scores.pass5).toBe("number");
        expect(typeof task.scores.passMax).toBe("number");
        // Blank the task across ALL runs and the pass@k estimate disappears too.
        const fullyBlanked = raw.map(r =>
            r.setupId === s.id && r.taskFolder === folder
                ? { ...r, outcomeScore: null, correctnessScore: null, recoverableSafetyScore: null }
                : r
        );
        const blankTask = derive(fullyBlanked)
            .find(x => x.id === s.id)
            .tasks.find(t => t.folder === folder);
        expect(blankTask.scores.pass5).toBeNull();
        expect(blankTask.scores.passMax).toBeNull();
        // Efficiency is telemetry, not a score: the blanked cell still consumed
        // wall-clock and tokens, so those survive while every score is null.
        expect(task.scores.latency).toBeGreaterThan(0);
        expect(task.scores.inputTokens).toBeGreaterThan(0);
        expect(task.scores.outputTokens).toBeGreaterThan(0);
    });
});
