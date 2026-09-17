import { fileURLToPath } from "node:url";
import path from "node:path";

import { describe, it, expect } from "vitest";

import { derive } from "./derive.mjs";
import { loadResults } from "./load.mjs";

const HERE = path.dirname(fileURLToPath(import.meta.url));
const FIXTURES = path.join(HERE, "fixtures");

describe("derive — data-driven", () => {
    it("discovers setups from the rows and builds complete, ordered history", () => {
        const rows = loadResults([FIXTURES]);
        const setups = derive(rows);
        const byId = Object.fromEntries(setups.map(s => [s.id, s]));

        const alpha = byId["alpha-pro-gemini-cli-mcp-skills"];
        expect(alpha).toBeTruthy();
        expect(alpha.model).toBe("alpha-pro");
        expect(alpha.harness).toBe("gemini-cli");
        expect(alpha.augmentation).toEqual(["mcp", "skills"]);

        // Two runs -> two history points, time-ascending.
        expect(alpha.history.map(h => h.t)).toEqual([
            "2026-06-01T12:00:00Z", "2026-06-15T12:00:00Z"
        ]);

        // The task has 4 scored attempts across both runs (0.9, 0.5, 0.95,
        // 0.85): none is a perfect 1.0, so pass1 = 0 under the one shared
        // threshold; pass5/passMax are null because 4 < K = 5 — no estimate,
        // never an extrapolation.
        const arch = alpha.tasks.find(t => t.folder === "get-app-architecture");
        // toMatchObject: v1 adds composite/correctness/recoverableSafety keys;
        // assert the pass-family intent without pinning the full shape.
        expect(arch.scores).toMatchObject({ pass1: 0, pass5: null, passMax: null });

        // The second setup is discovered too (no hardcoded catalog).
        expect(byId["gamma-coder-api-loop"]).toBeTruthy();
    });

    it("computes pass@1 as the share of PERFECT outcomes — the k=1 estimator", () => {
        // The fixture's 0.9 would have passed the old correctness@0.7 rule; under
        // the shared perfect-outcome threshold neither attempt passes (0 of 2).
        const rows = loadResults([path.join(FIXTURES, "run_20260601_120000", "rows.json")]);
        const setups = derive(rows);
        const alpha = setups.find(s => s.id === "alpha-pro-gemini-cli-mcp-skills");
        const arch = alpha.tasks.find(t => t.folder === "get-app-architecture");
        expect(arch.scores.pass1).toBe(0);

        // Promote one attempt to a perfect 1.0 and pass@1 = c/n = 1/2.
        const promoted = rows.map((r, i) =>
            r.taskFolder === "get-app-architecture" && i === 0 ? { ...r, outcomeScore: 1.0 } : r
        );
        const arch2 = derive(promoted)
            .find(s => s.id === "alpha-pro-gemini-cli-mcp-skills")
            .tasks.find(t => t.folder === "get-app-architecture");
        expect(arch2.scores.pass1).toBe(50);
    });

    it("assigns order by discovery and honors catalog overrides", () => {
        const rows = loadResults([FIXTURES]);
        const def = derive(rows);
        expect(def[0].id).toBe("alpha-pro-gemini-cli-mcp-skills"); // first seen
        expect(def[0].order).toBe(0);

        const overridden = derive(rows, {
            catalog: { "alpha-pro-gemini-cli-mcp-skills": { order: 99, color: "#000000" } }
        });
        const alpha = overridden.find(s => s.id === "alpha-pro-gemini-cli-mcp-skills");
        expect(alpha.order).toBe(99);
        expect(alpha.color).toBe("#000000");
    });

    it("treats a non-finite outcomeScore as missing data (null scores), not a 0", () => {
        // Unit-level: derive must be null-safe for any row set handed to it
        // directly (the loader accepts null scores for failed iterations).
        const base = {
            setupId: "s", model: "m", harness: "h", augmentation: [],
            runId: "run_20260101_000000", t: "2026-01-01T00:00:00Z",
            taskFolder: "task-a", taskName: "Task A", status: "failed",
            toolScore: null, latencySec: 1, inputTokens: null, outputTokens: null
        };
        const setups = derive([
            { ...base, iteration: 0, outcomeScore: null },
            { ...base, iteration: 1, outcomeScore: null }
        ]);
        const task = setups[0].tasks.find(t => t.folder === "task-a");
        // Null-safe across all metrics (v1 composite/correctness/safety included).
        expect(task.scores).toEqual({
            pass1: null,
            pass5: null,
            passMax: null,
            composite: null,
            correctness: null,
            recoverableSafety: null,
            // Efficiency is telemetry, not a score: an iteration that never
            // scored still consumed wall-clock, so latency survives while every
            // score is null. The token axes stay null because the fixture
            // captured no usage.
            latency: 1,
            inputTokens: null,
            outputTokens: null,
            cachedTokens: null
        });
    });

    it("pools pass@k attempts across runs: 5 single-iteration runs make one estimate", () => {
        // The real harness emits ONE iteration per (setup × task × run), so the
        // repeated attempts pass@k needs arrive as 5 distinct runIds. 4 perfect
        // (1.0) + 1 imperfect: n=5, c=4 -> pass@5 = 100 (fewer than 5 failures),
        // pass^5 = 0 (not every attempt passed).
        const base = {
            setupId: "s", model: "m", harness: "h", augmentation: [],
            taskFolder: "task-a", taskName: "Task A", status: "success",
            toolScore: null, latencySec: 1, inputTokens: null, outputTokens: null,
            iteration: 0
        };
        const scores = [1.0, 1.0, 1.0, 1.0, 0.9];
        const rows = scores.map((outcomeScore, i) => ({
            ...base,
            runId: `run_2026010${i + 1}_000000`,
            t: `2026-01-0${i + 1}T00:00:00Z`,
            outcomeScore
        }));
        const setups = derive(rows);
        const task = setups[0].tasks.find(t => t.folder === "task-a");
        expect(task.scores.pass5).toBe(100);
        expect(task.scores.passMax).toBe(0);
        // pass1 is the same estimator at k=1: c/n = 4/5. The 0.9 attempt is a
        // near-miss for the whole family — one threshold, one pooling rule.
        expect(task.scores.pass1).toBe(80);

        // All 5 perfect -> both metrics saturate.
        const allPerfect = derive(rows.map(r => ({ ...r, outcomeScore: 1.0 })));
        const perfectTask = allPerfect[0].tasks.find(t => t.folder === "task-a");
        expect(perfectTask.scores.pass5).toBe(100);
        expect(perfectTask.scores.passMax).toBe(100);

        // 4 runs only -> n < K, no estimate.
        const four = derive(rows.slice(0, 4));
        const fourTask = four[0].tasks.find(t => t.folder === "task-a");
        expect(fourTask.scores.pass5).toBeNull();
        expect(fourTask.scores.passMax).toBeNull();

        // History is cumulative: the point at each run t estimates from every
        // attempt up to t, so the k=5 pair is null until the 5th run while
        // pass1 (k=1) reports from the first attempt onward.
        expect(setups[0].history.map(h => h.scores.pass5)).toEqual([null, null, null, null, 100]);
        expect(setups[0].history.map(h => h.scores.passMax)).toEqual([null, null, null, null, 0]);
        expect(setups[0].history.map(h => h.scores.pass1)).toEqual([100, 100, 100, 100, 80]);
    });

    it("treats latencySec 0 as unmeasured, so it can't rank as the fastest", () => {
        // Regression: latencySec is non-nullable upstream and normalize.py
        // coerces a missing measurement to 0.0. Averaging that in gave an
        // unmeasured setup a latency of 0 — first place on a lower-is-better
        // metric, with a full bar.
        const base = {
            setupId: "s", model: "m", harness: "h", augmentation: [],
            runId: "run_20260101_000000", t: "2026-01-01T00:00:00Z",
            taskFolder: "task-a", taskName: "Task A", status: "success",
            toolScore: null, inputTokens: null, outputTokens: null, outcomeScore: 0.9
        };
        const unmeasured = derive([{ ...base, iteration: 0, latencySec: 0 }]);
        expect(unmeasured[0].tasks[0].scores.latency).toBeNull();

        // A 0 alongside real readings drops out of the mean rather than halving it.
        const mixed = derive([
            { ...base, iteration: 0, latencySec: 0 },
            { ...base, iteration: 1, latencySec: 10 }
        ]);
        expect(mixed[0].tasks[0].scores.latency).toBe(10);
    });

    it("projects the token buckets onto three axes rather than one total", () => {
        // Regression: a single summed figure was ~the input count wearing a
        // different label. Output was 0.7% of the fleet's summed buckets, so the
        // most expensive axis was invisible in the number that ranked setups.
        const base = {
            setupId: "s", model: "m", harness: "h", augmentation: [],
            runId: "run_20260101_000000", t: "2026-01-01T00:00:00Z",
            taskFolder: "task-a", taskName: "Task A", status: "success",
            toolScore: null, latencySec: 5, outcomeScore: 0.9, iteration: 0
        };
        const split = derive([
            {
                ...base,
                inputTokens: 100,
                cacheWriteTokens: 50,
                outputTokens: 200,
                reasoningTokens: 700,
                cachedTokens: 4000,
                // A provider total no longer overrides the buckets: it cannot be
                // attributed to an axis.
                totalTokens: 950
            }
        ]);
        expect(split[0].tasks[0].scores).toMatchObject({
            inputTokens: 150,
            outputTokens: 900,
            cachedTokens: 4000
        });
    });

    it("leaves the cached axis null for a harness that reports no cache reads", () => {
        // Only some harnesses report cache reads. A blank cell has to stay
        // distinct from a 0, or a silent harness would rank best on a
        // lower-is-better axis purely for being less talkative.
        const setups = derive([
            {
                setupId: "s", model: "m", harness: "h", augmentation: [],
                runId: "run_20260101_000000", t: "2026-01-01T00:00:00Z",
                taskFolder: "task-a", taskName: "Task A", status: "success",
                toolScore: null, latencySec: 5, outcomeScore: 0.9, iteration: 0,
                inputTokens: 100, outputTokens: 200
            }
        ]);
        expect(setups[0].tasks[0].scores.cachedTokens).toBeNull();
        expect(setups[0].tasks[0].scores.inputTokens).toBe(100);
    });
});
