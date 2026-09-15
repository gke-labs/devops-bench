import { describe, it, expect } from "vitest";

import { comparabilityNotes, supportSpread, scoringVersions, attemptsPerCell, coverageSummary } from "./comparability.js";

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

describe("coverageSummary", () => {
    const withCov = (id, coverage) =>
        setup(id, [full(80)], { provenance: { scoringVersions: ["v1"], attempts: 1, runId: "r", coverage } });

    it("is null when no visible arm reports coverage", () => {
        expect(coverageSummary([setup("a", [full(80)])])).toBeNull();
    });

    it("takes the widest bounds across arms", () => {
        // The weakest cell anywhere is the one that limits the table, so the
        // pooled min is the min of the mins — not an average of them.
        const cov = coverageSummary([
            withCov("a", { min: 60, max: 100, mean: 80, deterministic: 2, cells: 2 }),
            withCov("b", { min: 90, max: 90, mean: 90, deterministic: 2, cells: 2 })
        ]);
        expect(cov.min).toBe(60);
        expect(cov.max).toBe(100);
    });

    it("weights the pooled mean by the cells behind each arm", () => {
        // A one-task arm must not pull the figure as hard as a nine-task one;
        // a plain mean of means would let it.
        const cov = coverageSummary([
            withCov("a", { min: 100, max: 100, mean: 100, deterministic: 9, cells: 9 }),
            withCov("b", { min: 50, max: 50, mean: 50, deterministic: 1, cells: 1 })
        ]);
        expect(cov.mean).toBe(95);
    });

    it("skips arms that report nothing rather than counting them as fully judged", () => {
        const cov = coverageSummary([
            withCov("a", { min: 80, max: 80, mean: 80, deterministic: 3, cells: 3 }),
            setup("b", [full(80)])
        ]);
        expect(cov.cells).toBe(3);
        expect(cov.deterministic).toBe(3);
    });
});

describe("comparabilityNotes — coverage", () => {
    const arm = (id, coverage) =>
        setup(id, [full(80)], { provenance: { scoringVersions: ["v1"], attempts: 1, runId: "r", coverage } });

    it("says nothing when every declared check resolved", () => {
        const notes = comparabilityNotes(
            [arm("a", { min: 100, max: 100, mean: 100, deterministic: 2, cells: 2 })],
            "composite"
        );
        expect(notes).toEqual([]);
    });

    it("gives the range when coverage varies across cells", () => {
        const notes = comparabilityNotes(
            [arm("a", { min: 60, max: 100, mean: 85, deterministic: 4, cells: 4 })],
            "composite"
        );
        expect(notes.some(n => /from 60% to 100%/.test(n))).toBe(true);
        expect(notes.some(n => /mean 85%/.test(n))).toBe(true);
    });

    it("uses the flat phrasing when every cell resolved the same fraction", () => {
        const notes = comparabilityNotes(
            [arm("a", { min: 75, max: 75, mean: 75, deterministic: 4, cells: 4 })],
            "composite"
        );
        expect(notes.some(n => /Only 75% of the declared deterministic checks/.test(n))).toBe(true);
        expect(notes.some(n => /runs from/.test(n))).toBe(false);
    });

    it("names the judged-only tail separately from low coverage", () => {
        // Six tasks, two of which declare no deterministic checks at all. That
        // is a different problem from a spec that half-resolved, and collapsing
        // the two would hide which one the reader is looking at.
        const notes = comparabilityNotes(
            [arm("a", { min: 100, max: 100, mean: 100, deterministic: 4, cells: 6 })],
            "composite"
        );
        expect(notes.some(n => /2 of 6 cells declared no deterministic checks/.test(n))).toBe(true);
    });

    it("keeps coverage off the efficiency columns", () => {
        // Wall-clock is measured whole however much of the task the verifier
        // resolved, so a coverage caveat there would be noise.
        const notes = comparabilityNotes(
            [arm("a", { min: 40, max: 40, mean: 40, deterministic: 2, cells: 4 })],
            "latency"
        );
        expect(notes.some(n => /coverage|deterministic checks/.test(n))).toBe(false);
    });
});
