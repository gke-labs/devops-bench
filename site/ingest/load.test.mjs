import { fileURLToPath } from "node:url";
import fs from "node:fs";
import os from "node:os";
import path from "node:path";

import { describe, it, expect } from "vitest";

import { validateRow, loadFile, loadResults } from "./load.mjs";

const HERE = path.dirname(fileURLToPath(import.meta.url));
const FIXTURES = path.join(HERE, "fixtures");
const RUN1 = path.join(FIXTURES, "run_20260601_120000", "rows.json");

const validRow = {
    setupId: "alpha-pro-gemini-cli-mcp-skills",
    model: "alpha-pro", harness: "gemini-cli", augmentation: ["mcp", "skills"],
    runId: "run_20260601_120000", t: "2026-06-01T12:00:00Z",
    taskFolder: "get-app-architecture", taskName: "Summarize Application Architecture",
    iteration: 0, status: "success", outcomeScore: 0.9, toolScore: 0.85,
    latencySec: 12.35, inputTokens: 9000, outputTokens: 420
};

describe("validateRow", () => {
    it("accepts a well-formed row", () => {
        expect(validateRow(validRow)).toEqual([]);
    });

    it("accepts an empty augmentation (baseline) array", () => {
        expect(validateRow({ ...validRow, setupId: "gamma-coder-api-loop", augmentation: [] })).toEqual([]);
    });

    it("accepts null scores and tokens (unscored/failed iteration)", () => {
        const row = {
            ...validRow, status: "failed",
            outcomeScore: null, toolScore: null, inputTokens: null, outputTokens: null
        };
        expect(validateRow(row)).toEqual([]);
    });

    it("flags an out-of-range score", () => {
        const errs = validateRow({ ...validRow, outcomeScore: 1.5 });
        expect(errs.join()).toMatch(/outcomeScore.*\[0,1\]/);
    });

    it("flags a bad runId pattern", () => {
        const errs = validateRow({ ...validRow, runId: "2026-06-01" });
        expect(errs.join()).toMatch(/runId/);
    });

    it("accepts a runId with a uniqueness suffix (parallel/aggregated runs)", () => {
        expect(validateRow({ ...validRow, runId: "run_20260601_120000_12345" })).toEqual([]);
        expect(validateRow({ ...validRow, runId: "run_20260601_120000_matrix-7" })).toEqual([]);
    });

    it("flags a non-array augmentation", () => {
        const errs = validateRow({ ...validRow, augmentation: "gca" });
        expect(errs.join()).toMatch(/augmentation/);
    });

    it("flags a bad status enum", () => {
        const errs = validateRow({ ...validRow, status: "crashed" });
        expect(errs.join()).toMatch(/status/);
    });

    it("flags negative iteration and non-integer tokens", () => {
        const errs = validateRow({ ...validRow, iteration: -1, inputTokens: 1.5 });
        expect(errs.join()).toMatch(/iteration/);
        expect(errs.join()).toMatch(/inputTokens/);
    });

    it("rejects a non-object", () => {
        expect(validateRow(null)).toEqual(["not an object"]);
        expect(validateRow([])).toEqual(["not an object"]);
    });
});

describe("loadFile", () => {
    it("loads a valid fixture file", () => {
        const { rows, errors } = loadFile(RUN1);
        expect(errors).toEqual([]);
        expect(rows).toHaveLength(3);
    });

    it("reports invalid JSON with the file name", () => {
        const { errors } = loadFile(path.join(HERE, "does-not-exist.json"));
        expect(errors[0]).toMatch(/invalid JSON|ENOENT/);
    });
});

describe("loadResults", () => {
    it("discovers rows.json across a results tree, ignoring manifest.json", () => {
        // fixtures/ holds run_*/rows.json (+ a run_*/manifest.json the loader
        // must skip): 3 rows (run1) + 2 rows (run2), no manifest rows.
        const rows = loadResults([FIXTURES]);
        expect(rows).toHaveLength(5);
        const runIds = [...new Set(rows.map(r => r.runId))].sort();
        expect(runIds).toEqual(["run_20260601_120000", "run_20260615_120000"]);
    });

    it("throws when a path does not exist", () => {
        expect(() => loadResults([path.join(HERE, "fixtures", "missing-dir-xyz")]))
            .toThrow(/path not found/);
    });

    it("throws a line-by-line report when a row is invalid", () => {
        // A temp file (kept out of fixtures/, which must stay all-valid) with one
        // good row and one bad one, to exercise the aggregated validation throw.
        const dir = fs.mkdtempSync(path.join(os.tmpdir(), "ingest-load-"));
        const file = path.join(dir, "run_20260601_120000.json");
        fs.writeFileSync(file, JSON.stringify([
            { ...validRow },
            { ...validRow, outcomeScore: 1.5, augmentation: "turbo" }
        ]));
        try {
            expect(() => loadResults([file])).toThrow(/Validation failed for 1 row\(s\)/);
            // Report carries file + row-index context and the per-field reasons.
            expect(() => loadResults([file])).toThrow(/\[1\].*augmentation.*outcomeScore/);
        } finally {
            fs.rmSync(dir, { recursive: true, force: true });
        }
    });
});
