import { describe, it, expect, afterEach } from "vitest";
import { render, screen, cleanup } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { LeaderboardRow } from "./LeaderboardRow.jsx";

const MODELS = { "alpha-pro": { name: "Alpha Pro", provider: "Acme", logo: "alpha" } };
const HARNESSES = {
    "gemini-cli": { name: "Gemini CLI", type: "cli", accent: "#0ea5e9", logo: "terminal" }
};

// Two catastrophic tasks, and readings on both metric families so the row has
// something to print whichever one is selected.
const SETUP = {
    id: "alpha-pro-gemini-cli",
    order: 0,
    model: "alpha-pro",
    harness: "gemini-cli",
    augmentation: [],
    color: "#3b82f6",
    catastrophicCount: 2,
    tasks: [{ folder: "a", name: "A", scores: { composite: 84, latency: 40, outputTokens: 900 } }],
    history: [{ t: "2026-01-15T00:00:00Z", scores: { composite: 84, latency: 40, outputTokens: 900 } }]
};

function renderRow(metric, setup = SETUP, supportMax) {
    return render(
        <MemoryRouter future={{ v7_startTransition: true, v7_relativeSplatPath: true }}>
            <LeaderboardRow
                setup={setup}
                models={MODELS}
                harnesses={HARNESSES}
                metric={metric}
                metricBest={metric === "composite" ? 84 : 40}
                supportMax={supportMax}
            />
        </MemoryRouter>
    );
}

describe("LeaderboardRow catastrophic badge", () => {
    afterEach(cleanup);

    it("badges a quality metric, where the violation is what zeroed the figure", () => {
        renderRow("composite");
        expect(screen.getByText("⚠ 2")).toBeInTheDocument();
    });

    it("drops the badge on the efficiency metrics, which a violation does not zero", () => {
        // A catastrophic violation zeroes the OUTCOME score. The seconds and
        // tokens a run consumed are unaffected and still valid, so a badge
        // beside them would flag a reading it has no bearing on.
        for (const metric of ["latency", "inputTokens", "outputTokens", "cachedTokens"]) {
            renderRow(metric);
            expect(screen.queryByText("⚠ 2")).not.toBeInTheDocument();
            cleanup();
        }
    });

    it("still prints the efficiency figure it was hiding the badge next to", () => {
        // Guard against "fixing" the badge by dropping the whole slot including
        // the value: the number is the point of the column.
        renderRow("latency");
        expect(screen.getByText("40.0s")).toBeInTheDocument();
    });

    it("shows no badge for a clean setup on any metric", () => {
        const clean = { ...SETUP, catastrophicCount: 0 };
        for (const metric of ["composite", "latency"]) {
            renderRow(metric, clean);
            expect(screen.queryByText(/⚠/)).not.toBeInTheDocument();
            cleanup();
        }
    });
});

describe("LeaderboardRow support count", () => {
    afterEach(cleanup);

    // Three tasks, two of them unscored on composite. The row's figure is a
    // mean over ONE task, and without the count there is nothing on screen that
    // distinguishes it from a mean over all three.
    const THIN = {
        ...SETUP,
        catastrophicCount: 0,
        tasks: [
            { folder: "a", name: "A", scores: { composite: 95, latency: 40 } },
            { folder: "b", name: "B", scores: { composite: null, latency: 40 } },
            { folder: "c", name: "C", scores: { composite: null, latency: 40 } }
        ]
    };

    it("prints how many tasks the mean is over", () => {
        renderRow("composite", THIN, 1);
        expect(screen.getByText("n=1")).toBeInTheDocument();
        expect(screen.getByTitle("Mean over 1 of 3 tasks")).toBeInTheDocument();
    });

    it("marks a row resting on less evidence than the best-covered row on screen", () => {
        // The failure mode: this row can outrank a fully-measured one purely by
        // being measured on its single best task.
        renderRow("composite", THIN, 3);
        expect(screen.getByTitle(/fewer than the 3 behind the best-covered row/)).toBeInTheDocument();
    });

    it("counts the tasks that have a reading for THIS metric, not the task list", () => {
        // Same setup, different column: latency is telemetry and is recorded
        // even where the score is blank, so its mean is over all three.
        renderRow("latency", THIN, 3);
        expect(screen.getByText("n=3")).toBeInTheDocument();
    });

    it("prints no count for a row with nothing to average", () => {
        const empty = { ...SETUP, catastrophicCount: 0, tasks: [{ folder: "a", name: "A", scores: { composite: null } }] };
        renderRow("composite", empty, 3);
        expect(screen.queryByText(/^n=/)).not.toBeInTheDocument();
    });
});
