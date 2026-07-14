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

        // Latest run (June 15): both iterations >= 0.7 -> pass1 = 100. pass5/passMax
        // stay null (pass1-only until the harness emits multi-iteration runs).
        const arch = alpha.tasks.find(t => t.folder === "get-app-architecture");
        expect(arch.scores).toEqual({ pass1: 100, pass5: null, passMax: null });

        // The second setup is discovered too (no hardcoded catalog).
        expect(byId["gamma-coder-api-loop"]).toBeTruthy();
    });

    it("computes pass@1 from the iteration outcomeScores at a threshold of 0.7", () => {
        // 1 pass (0.9) + 1 fail (0.5) of 2 -> 50%.
        const rows = loadResults([path.join(FIXTURES, "run_20260601_120000", "rows.json")]);
        const setups = derive(rows);
        const alpha = setups.find(s => s.id === "alpha-pro-gemini-cli-mcp-skills");
        const arch = alpha.tasks.find(t => t.folder === "get-app-architecture");
        expect(arch.scores.pass1).toBe(50);
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
        expect(task.scores).toEqual({ pass1: null, pass5: null, passMax: null });
    });
});
