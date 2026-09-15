import { describe, it, expect } from "vitest";

import { comparabilityNotes, supportSpread, scoringVersions, attemptsPerCell } from "./comparability.js";

// Minimal Setup shapes: only the fields these functions read.
function setup(id, taskScores, extra = {}) {
    return {
        id,
        tasks: taskScores.map((scores, i) => ({ folder: `t${i}`, name: `T${i}`, scores })),
        catastrophicCount: 0,
        provenance: { scoringVersions: ["v1"], attempts: 1, runId: "run_20260101_000000" },
        ...extra
    };
}

const full = s => ({ composite: s, correctness: s, recoverableSafety: s, pass1: s, latency: 10 });
const blank = { composite: null, correctness: null, recoverableSafety: null, pass1: null, latency: 10 };

describe("supportSpread", () => {
    it("reports the min/max tasks with a reading and the blanks behind them", () => {
        const spread = supportSpread(
            [setup("a", [full(80), full(60), full(70)]), setup("b", [full(90), blank, blank])],
            "composite"
        );
        expect(spread).toEqual({ min: 1, max: 3, attempted: 3, blanks: 2 });
    });

    it("is empty-safe", () => {
        expect(supportSpread([], "composite")).toEqual({ min: 0, max: 0, attempted: 0, blanks: 0 });
    });
});

describe("comparabilityNotes", () => {
    it("says nothing when the table is comparable as rendered", () => {
        // Two arms, same tasks, all scored, one version, no gate. Nothing to
        // warn about — and a caveat strip that is always present is furniture.
        const notes = comparabilityNotes(
            [setup("a", [full(80), full(60)]), setup("b", [full(90), full(50)])],
            "composite"
        );
        expect(notes).toEqual([]);
    });

    it("flags arms ranked on different numbers of tasks", () => {
        // The failure this exists for: b's mean is over one task and outranks a,
        // and nothing else on the row says so.
        const notes = comparabilityNotes(
            [setup("a", [full(80), full(60), full(70)]), setup("b", [full(95), blank, blank])],
            "composite"
        );
        expect(notes[0]).toMatch(/between 1 and 3 of them/);
        expect(notes[0]).toMatch(/not like-for-like/);
    });

    it("states partial coverage even when every arm is measured on the same tasks", () => {
        // Even support: the RANKING is fair, the coverage still is not complete.
        const notes = comparabilityNotes(
            [setup("a", [full(80), blank]), setup("b", [full(90), blank])],
            "composite"
        );
        expect(notes[0]).toBe("Every arm is ranked on 1 of 2 tasks; the rest have no outcome reading.");
    });

    it("says a blank is left out of the mean rather than counted as 0", () => {
        const notes = comparabilityNotes([setup("a", [full(80), blank])], "composite");
        expect(notes.join(" ")).toMatch(/blank, not 0/);
    });

    it("describes the gate as decisive on a gated metric", () => {
        const notes = comparabilityNotes(
            [setup("a", [full(80)], { catastrophicCount: 2 })],
            "pass1"
        );
        expect(notes.join(" ")).toMatch(/2 cells tripped a catastrophic safeguard/);
        expect(notes.join(" ")).toMatch(/count as a zero here/);
    });

    it("describes the gate as NOT applied on the correctness column", () => {
        // Correctness reports what the agent achieved; only outcome and pass@1
        // are gated. Saying "zeroed" here would describe a different column.
        const notes = comparabilityNotes(
            [setup("a", [full(80)], { catastrophicCount: 1 })],
            "correctness"
        );
        expect(notes.join(" ")).toMatch(/which this column does not apply/);
        expect(notes.join(" ")).not.toMatch(/counts as a zero/);
    });

    it("flags two scoring versions sharing one column", () => {
        const a = setup("a", [full(80)]);
        const b = setup("b", [full(70)], {
            provenance: { scoringVersions: ["v2"], attempts: 1, runId: "r" }
        });
        expect(comparabilityNotes([a, b], "composite").join(" ")).toMatch(/more than one scoring version \(v1, v2\)/);
    });

    it("marks an efficiency metric as telemetry rather than a score", () => {
        const notes = comparabilityNotes([setup("a", [full(80)])], "latency");
        expect(notes.join(" ")).toMatch(/Telemetry, not a score/);
    });

    it("is empty-safe", () => {
        expect(comparabilityNotes([], "composite")).toEqual([]);
    });
});

describe("provenance summaries", () => {
    it("unions the scoring versions across arms", () => {
        const a = setup("a", [full(80)]);
        const b = setup("b", [full(70)], {
            provenance: { scoringVersions: ["v1", "v2"], attempts: 1, runId: "r" }
        });
        expect(scoringVersions([a, b])).toEqual(["v1", "v2"]);
    });

    it("tolerates an arm with no provenance at all", () => {
        // Rows derived before provenance existed. A missing strip is fine; a
        // crashed board is not.
        const legacy = { id: "old", tasks: [], catastrophicCount: 0 };
        expect(scoringVersions([legacy])).toEqual([]);
        expect(attemptsPerCell([legacy])).toBeNull();
    });

    it("reports attempts as a figure when arms agree and a range when they do not", () => {
        const a = setup("a", [full(80)]);
        const b = setup("b", [full(70)], {
            provenance: { scoringVersions: ["v1"], attempts: 5, runId: "r" }
        });
        expect(attemptsPerCell([a])).toBe("1");
        expect(attemptsPerCell([a, b])).toBe("1–5");
    });
});
