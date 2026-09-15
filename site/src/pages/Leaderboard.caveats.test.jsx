// The provenance strip and caveat lines under the table.
//
// Separate from Leaderboard.test.jsx because the context mock is module-level:
// that file's fixture is deliberately comparable (two arms, same task, one
// reading each), which is the case where this strip must NOT appear. This one
// supplies a fixture where it must.

import { describe, it, expect, vi } from "vitest";
import { render, screen } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";

vi.mock("react-chartjs-2", () => ({ Line: () => null }));

const MODELS = {
    "alpha-pro": { name: "Alpha Pro", provider: "Acme", logo: "alpha" },
    "gamma-coder": { name: "Gamma Coder", provider: "Initech", logo: "gamma" }
};
const HARNESSES = {
    "gemini-cli": { name: "Gemini CLI", type: "cli", accent: "#0ea5e9", logo: "terminal" }
};

const scores = c => ({ pass1: c, composite: c, correctness: c, recoverableSafety: c, latency: 20 });
const blank = { pass1: null, composite: null, correctness: null, recoverableSafety: null, latency: 20 };

// alpha is measured on all three tasks; gamma on one, and it is gamma's best.
// Gamma therefore tops the table on a mean over a third of the evidence.
const FIXTURE = {
    models: MODELS,
    harnesses: HARNESSES,
    setups: [
        {
            id: "alpha-pro-gemini-cli", order: 0, model: "alpha-pro", harness: "gemini-cli",
            augmentation: [], color: "#3b82f6", catastrophicCount: 1,
            provenance: { scoringVersions: ["v1"], attempts: 1, runId: "run_20260101_000000" },
            tasks: [
                { folder: "a", name: "A", scores: scores(70) },
                { folder: "b", name: "B", scores: scores(60) },
                { folder: "c", name: "C", scores: scores(65) }
            ],
            history: [{ t: "2026-01-15T00:00:00Z", scores: scores(65) }]
        },
        {
            id: "gamma-coder-gemini-cli", order: 1, model: "gamma-coder", harness: "gemini-cli",
            augmentation: [], color: "#ec4899", catastrophicCount: 0,
            provenance: { scoringVersions: ["v1"], attempts: 1, runId: "run_20260101_000000" },
            tasks: [
                { folder: "a", name: "A", scores: scores(95) },
                { folder: "b", name: "B", scores: blank },
                { folder: "c", name: "C", scores: blank }
            ],
            history: [{ t: "2026-01-15T00:00:00Z", scores: scores(95) }]
        }
    ],
    loading: false,
    error: null
};

vi.mock("../context/BenchmarkContext.jsx", () => ({
    useBenchmark: () => FIXTURE
}));

import { Leaderboard } from "./Leaderboard.jsx";

function renderPage() {
    return render(
        <MemoryRouter future={{ v7_startTransition: true, v7_relativeSplatPath: true }}>
            <Leaderboard />
        </MemoryRouter>
    );
}

describe("Leaderboard provenance strip", () => {
    it("states the scoring version and the attempts behind each cell", () => {
        renderPage();
        expect(screen.getByText("Provenance")).toBeInTheDocument();
        expect(screen.getByText("Scoring v1")).toBeInTheDocument();
        expect(screen.getByText("1 attempt per task cell")).toBeInTheDocument();
        expect(screen.getByText("2 arms shown")).toBeInTheDocument();
    });
});

describe("Leaderboard caveats", () => {
    it("warns that the arms are ranked on different numbers of tasks", () => {
        // The whole point: gamma leads the table on a mean over one task.
        renderPage();
        expect(screen.getByText(/between 1 and 3 of them/)).toBeInTheDocument();
        expect(screen.getByText(/not like-for-like/)).toBeInTheDocument();
    });

    it("says a blank cell is left out of the mean rather than counted as 0", () => {
        renderPage();
        expect(screen.getByText(/blank, not 0/)).toBeInTheDocument();
    });

    it("describes the gate against the column actually selected", () => {
        // Default column is Outcome, which the gate zeroes.
        renderPage();
        expect(screen.getByText(/tripped a catastrophic safeguard/)).toBeInTheDocument();
        expect(screen.getByText(/counts as a zero here/)).toBeInTheDocument();
    });
});
