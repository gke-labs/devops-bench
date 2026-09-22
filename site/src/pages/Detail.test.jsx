import { describe, it, expect, beforeEach, vi } from "vitest";
import { render, screen, fireEvent, within, cleanup } from "@testing-library/react";
import { MemoryRouter, Routes, Route } from "react-router-dom";

// Stub the chart (jsdom has no canvas); the context is mocked per-test below.
vi.mock("react-chartjs-2", () => ({ Line: () => null }));

// Mutable benchmark state so individual tests can switch to loading/error/etc.
let benchmark;
vi.mock("../context/BenchmarkContext.jsx", () => ({
    useBenchmark: () => benchmark
}));

import { Detail } from "./Detail.jsx";
import { setScopeFilterEnabled } from "../lib/taskScope.js";

const SETUP_ID = "alpha-pro-gemini-cli-baseline";

// Task scores chosen so name-order and score-order DIFFER, and so best/avg/median
// are all distinct: pass1 = {Apple 60, Banana 90, Cherry 80} → best 90, avg 76.7,
// median 80. Score-desc → Banana, Cherry, Apple. Name-asc → Apple, Banana, Cherry.
function makeBenchmark(overrides = {}) {
    return {
        models: { "alpha-pro": { name: "Alpha Pro", provider: "Acme", logo: "alpha" } },
        harnesses: { "gemini-cli": { name: "Gemini CLI", type: "cli", accent: "#0ea5e9", logo: "terminal" } },
        setups: [
            {
                id: SETUP_ID, order: 0, model: "alpha-pro", harness: "gemini-cli",
                augmentation: [], color: "#3b82f6",
                // Latency/tokens are chosen so their means are round (50.0s,
                // 20.0k) and their best is the SMALLEST, which is the opposite
                // end from the percentage metrics above.
                tasks: [
                    { folder: "a", name: "Apple", scores: { composite: 60, pass1: 60, pass5: 65, passMax: 70, latency: 40, tokens: 10000, inputTokens: 5000 } },
                    { folder: "b", name: "Banana", scores: { composite: 90, pass1: 90, pass5: 95, passMax: 100, latency: 50, tokens: 20000, inputTokens: 10000 } },
                    { folder: "c", name: "Cherry", scores: { composite: 80, pass1: 80, pass5: 85, passMax: 90, latency: 60, tokens: 30000, inputTokens: 15000 } }
                ],
                history: [
                    { t: "2026-01-15T00:00:00Z", scores: { composite: 70, pass1: 70, pass5: 75, passMax: 80 } },
                    { t: "2026-02-15T00:00:00Z", scores: { composite: 80, pass1: 80, pass5: 85, passMax: 90 } }
                ]
            }
        ],
        loading: false,
        error: null,
        ...overrides
    };
}

function renderAt(path) {
    return render(
        <MemoryRouter initialEntries={[path]} future={{ v7_startTransition: true, v7_relativeSplatPath: true }}>
            <Routes>
                <Route path="/setup/:id" element={<Detail />} />
                <Route path="/" element={<div>home</div>} />
            </Routes>
        </MemoryRouter>
    );
}

const taskOrder = () =>
    screen.getAllByText(/^(Apple|Banana|Cherry)$/).map(el => el.textContent);

beforeEach(() => {
    benchmark = makeBenchmark();
});

describe("Detail", () => {
    it("renders the identity hero for the matched setup", () => {
        renderAt(`/setup/${SETUP_ID}`);
        expect(screen.getByText("Alpha Pro")).toBeInTheDocument();
        expect(screen.getByText("Gemini CLI")).toBeInTheDocument();
        expect(document.title).toContain("Alpha Pro × Gemini CLI");
    });

    it("computes best / average / median stat cards", () => {
        renderAt(`/setup/${SETUP_ID}`);
        // Scope each assertion to its card by label — the same "%" values also
        // appear in the trend table, so a global query would be ambiguous.
        const card = label => screen.getByText(label).closest("div");
        expect(within(card("Best Task")).getByText("90.0%")).toBeInTheDocument(); // max(60,90,80)
        expect(within(card("Average")).getByText("76.7%")).toBeInTheDocument();   // 230/3
        expect(within(card("Average")).getByText("over 3 tasks")).toBeInTheDocument();
        expect(within(card("Median")).getByText("80.0%")).toBeInTheDocument();
    });

    it("computes stat cards over only the scored tasks, ignoring nulls", () => {
        benchmark = makeBenchmark({
            setups: [{
                id: SETUP_ID, order: 0, model: "alpha-pro", harness: "gemini-cli",
                augmentation: [], color: "#3b82f6",
                tasks: [
                    { folder: "a", name: "Apple", scores: { composite: 80, pass1: 80, pass5: 1, passMax: 1 } },
                    { folder: "b", name: "Banana", scores: { composite: 60, pass1: 60, pass5: 1, passMax: 1 } },
                    { folder: "c", name: "Cherry", scores: { composite: null, pass1: null, pass5: 1, passMax: 1 } }
                ],
                history: [{ t: "2026-01-15T00:00:00Z", scores: { composite: 70, pass1: 70, pass5: 1, passMax: 1 } }]
            }]
        });
        renderAt(`/setup/${SETUP_ID}`);
        const card = label => screen.getByText(label).closest("div");
        expect(within(card("Best Task")).getByText("80.0%")).toBeInTheDocument();
        expect(within(card("Average")).getByText("70.0%")).toBeInTheDocument(); // (80+60)/2, Cherry ignored
        expect(within(card("Average")).getByText("over 2 tasks")).toBeInTheDocument();
        expect(within(card("Median")).getByText("70.0%")).toBeInTheDocument();
    });

    it("shows '—' in stat cards when no task is scored for the metric", () => {
        benchmark = makeBenchmark({
            setups: [{
                id: SETUP_ID, order: 0, model: "alpha-pro", harness: "gemini-cli",
                augmentation: [], color: "#3b82f6",
                tasks: [
                    { folder: "a", name: "Apple", scores: { pass1: null, pass5: 1, passMax: 1 } },
                    { folder: "b", name: "Banana", scores: { pass5: 1, passMax: 1 } } // pass1 absent
                ],
                history: [{ t: "2026-01-15T00:00:00Z", scores: { pass1: null, pass5: 1, passMax: 1 } }]
            }]
        });
        renderAt(`/setup/${SETUP_ID}`);
        const card = label => screen.getByText(label).closest("div");
        expect(within(card("Best Task")).getByText("—")).toBeInTheDocument();   // no NaN / -Infinity
        expect(within(card("Average")).getByText("—")).toBeInTheDocument();
        expect(within(card("Median")).getByText("—")).toBeInTheDocument();
        expect(within(card("Average")).getByText("over 0 tasks")).toBeInTheDocument();
    });

    it("shows no catastrophic tasks when the field is absent", () => {
        // The common case: the ingest omits catastrophicCount entirely rather
        // than writing a 0, and that has to read the same as an explicit 0.
        renderAt(`/setup/${SETUP_ID}`);
        const card = label => screen.getByText(label).closest("div");
        expect(within(card("Catastrophic")).getByText("0")).toBeInTheDocument();
        expect(within(card("Catastrophic")).getByText("none")).toBeInTheDocument();
    });

    it("shows no catastrophic tasks for an explicit zero", () => {
        benchmark.setups[0].catastrophicCount = 0;
        renderAt(`/setup/${SETUP_ID}`);
        const card = label => screen.getByText(label).closest("div");
        expect(within(card("Catastrophic")).getByText("0")).toBeInTheDocument();
        expect(within(card("Catastrophic")).getByText("none")).toBeInTheDocument();
    });

    it("uses the singular subtitle for one catastrophic task", () => {
        benchmark.setups[0].catastrophicCount = 1;
        renderAt(`/setup/${SETUP_ID}`);
        const card = label => screen.getByText(label).closest("div");
        expect(within(card("Catastrophic")).getByText("1")).toBeInTheDocument();
        // "outcome", not "task": the run happened, only its score was zeroed.
        expect(within(card("Catastrophic")).getByText("outcome zeroed")).toBeInTheDocument();
    });

    it("uses the plural subtitle for several catastrophic tasks", () => {
        benchmark.setups[0].catastrophicCount = 3;
        renderAt(`/setup/${SETUP_ID}`);
        const card = label => screen.getByText(label).closest("div");
        expect(within(card("Catastrophic")).getByText("3")).toBeInTheDocument();
        expect(within(card("Catastrophic")).getByText("outcomes zeroed")).toBeInTheDocument();
    });

    it("drops the catastrophic card on the efficiency metrics", () => {
        // A catastrophic violation zeroes the OUTCOME score. The seconds and
        // tokens the run consumed are untouched, so beside a latency or token
        // headline the card qualifies a figure it has no bearing on.
        benchmark.setups[0].catastrophicCount = 3;
        for (const m of ["latency", "tokensInput", "tokensOutput"]) {
            renderAt(`/setup/${SETUP_ID}?metric=${m}`);
            expect(screen.queryByText("Catastrophic")).not.toBeInTheDocument();
            cleanup();
        }
        // ...and is still there on the quality side, where it explains the score.
        renderAt(`/setup/${SETUP_ID}?metric=composite`);
        expect(screen.getByText("Catastrophic")).toBeInTheDocument();
    });

    it("marks the catastrophic rows in the task breakdown", () => {
        // The count on the card has to be traceable to specific rows. Zeroing is
        // not what identifies them: a task can score 0 without a violation, so
        // reading the flagged set off the figures alone is not possible.
        benchmark.setups[0].catastrophicCount = 1;
        benchmark.setups[0].tasks[0].catastrophic = true;   // Apple, 60
        benchmark.setups[0].tasks[1].scores.composite = 0;  // Banana, 0 but clean
        renderAt(`/setup/${SETUP_ID}`);
        const row = name => screen.getByText(name).closest("tr");
        const marker = /catastrophic safety violation/i;
        expect(within(row("Apple")).getByLabelText(marker)).toBeInTheDocument();
        expect(within(row("Banana")).queryByLabelText(marker)).not.toBeInTheDocument();
        expect(within(row("Cherry")).queryByLabelText(marker)).not.toBeInTheDocument();
    });

    it("drops the task markers on the efficiency metrics", () => {
        // Same rule as the card and the leaderboard badge: the violation zeroes
        // the outcome, not the seconds or the tokens.
        benchmark.setups[0].tasks[0].catastrophic = true;
        const marker = /catastrophic safety violation/i;
        for (const m of ["latency", "tokensInput", "tokensOutput"]) {
            renderAt(`/setup/${SETUP_ID}?metric=${m}`);
            expect(screen.queryByLabelText(marker)).not.toBeInTheDocument();
            cleanup();
        }
        renderAt(`/setup/${SETUP_ID}?metric=composite`);
        expect(screen.getByLabelText(marker)).toBeInTheDocument();
    });

    it("explains the marker in a legend when a task is flagged", () => {
        // The marker's title/aria-label is invisible until hovered and
        // unreachable by touch, so the glyph needs a visible explanation.
        benchmark.setups[0].tasks[0].catastrophic = true;
        renderAt(`/setup/${SETUP_ID}`);
        const legend = screen.getByText(/catastrophic safety violation/i, { selector: "p" });
        expect(legend).toBeInTheDocument();
        expect(legend).toHaveTextContent(/this task/i);          // singular
        expect(legend).toHaveTextContent(/latency and token figures are unaffected/i);
    });

    it("counts the flagged tasks in the legend", () => {
        benchmark.setups[0].tasks[0].catastrophic = true;
        benchmark.setups[0].tasks[1].catastrophic = true;
        renderAt(`/setup/${SETUP_ID}`);
        expect(screen.getByText(/catastrophic safety violation/i, { selector: "p" }))
            .toHaveTextContent(/these 2 tasks/i);
    });

    it("omits the legend when nothing is flagged", () => {
        // A legend for a mark that is not on the page implies the page might
        // contain one.
        renderAt(`/setup/${SETUP_ID}`);
        expect(screen.queryByText(/catastrophic safety violation/i, { selector: "p" }))
            .not.toBeInTheDocument();
    });

    it("omits the legend on the efficiency metrics, with the markers", () => {
        benchmark.setups[0].tasks[0].catastrophic = true;
        for (const m of ["latency", "tokensInput", "tokensOutput"]) {
            renderAt(`/setup/${SETUP_ID}?metric=${m}`);
            expect(screen.queryByText(/catastrophic safety violation/i, { selector: "p" }))
                .not.toBeInTheDocument();
            cleanup();
        }
    });
    it("reports the efficiency axis the toggle is not showing", () => {
        const card = label => screen.getByText(label).closest("div");

        // Under a quality metric the spare card is latency, as it always was.
        renderAt(`/setup/${SETUP_ID}`);
        expect(within(card("Avg Latency")).getByText("50.0s")).toBeInTheDocument();

        // Under Latency it has to switch, or it prints the same figure as
        // "Average" in the card next to it.
        cleanup();
        renderAt(`/setup/${SETUP_ID}?metric=latency`);
        expect(within(card("Average")).getByText("50.0s")).toBeInTheDocument();
        expect(screen.queryByText("Avg Latency")).not.toBeInTheDocument();
        expect(within(card("Avg Tokens")).getByText("20.0k")).toBeInTheDocument();
    });

    it("orients the stat cards by the metric's direction", () => {
        // Best is the FASTEST task under latency — the minimum, where every
        // percentage metric takes the maximum.
        renderAt(`/setup/${SETUP_ID}?metric=latency`);
        const card = label => screen.getByText(label).closest("div");
        expect(within(card("Best Task")).getByText("40.0s")).toBeInTheDocument();
        expect(within(card("Median")).getByText("50.0s")).toBeInTheDocument();
    });

    it("heads the task column with the metric rather than calling it a score", () => {
        // A token count is telemetry, not a score; the old "Score (Tokens)"
        // header said otherwise.
        renderAt(`/setup/${SETUP_ID}?metric=tokens`);
        expect(screen.getByRole("columnheader", { name: /Tokens/ })).toBeInTheDocument();
        expect(screen.queryByRole("columnheader", { name: /Score/ })).not.toBeInTheDocument();
    });

    it("honors the ?metric= query param", () => {
        renderAt(`/setup/${SETUP_ID}?metric=pass5`);
        expect(screen.getByRole("button", { name: "Pass@5" })).toHaveAttribute("aria-pressed", "true");
        expect(screen.getByRole("button", { name: "Pass@1" })).toHaveAttribute("aria-pressed", "false");
    });

    it("falls back to the composite Outcome metric for an unknown metric param", () => {
        renderAt(`/setup/${SETUP_ID}?metric=bogus`);
        expect(screen.getByRole("button", { name: "Outcome" })).toHaveAttribute("aria-pressed", "true");
    });

    it("sorts the task table by score asc by default", () => {
        renderAt(`/setup/${SETUP_ID}`);
        expect(taskOrder()).toEqual(["Apple", "Cherry", "Banana"]); // 60, 80, 90
    });

    it("re-sorts by task name (asc then desc) when the Task header is clicked", () => {
        renderAt(`/setup/${SETUP_ID}`);
        fireEvent.click(screen.getByRole("columnheader", { name: /Task/ }));
        expect(taskOrder()).toEqual(["Apple", "Banana", "Cherry"]);
        fireEvent.click(screen.getByRole("columnheader", { name: /Task/ }));
        expect(taskOrder()).toEqual(["Cherry", "Banana", "Apple"]);
    });

    it("toggles score sort direction on repeated header clicks", () => {
        renderAt(`/setup/${SETUP_ID}`);
        fireEvent.click(screen.getByRole("columnheader", { name: /Outcome/ }));
        expect(taskOrder()).toEqual(["Banana", "Cherry", "Apple"]); // now descending
    });

    it("points the sort arrow the way the values actually run", () => {
        const header = name => screen.getByRole("columnheader", { name });

        renderAt(`/setup/${SETUP_ID}`);
        expect(header(/Outcome/)).toHaveTextContent("▲"); // 60 → 90, ascending

        cleanup();
        renderAt(`/setup/${SETUP_ID}?metric=tokens`);
        expect(header(/Tokens/)).toHaveTextContent("▼"); // 30.0k → 10.0k, descending
        fireEvent.click(header(/Tokens/));
        expect(header(/Tokens/)).toHaveTextContent("▲");
    });

    it("shows a NotFound state for an unknown setup id", () => {
        renderAt("/setup/does-not-exist");
        expect(screen.getByText(/No setup found/i)).toBeInTheDocument();
        expect(screen.getByText("does-not-exist")).toBeInTheDocument();
    });

    it("shows the loading state while data is loading", () => {
        benchmark = makeBenchmark({ loading: true });
        renderAt(`/setup/${SETUP_ID}`);
        expect(screen.getByText(/Loading benchmark data/i)).toBeInTheDocument();
    });

    it("shows the error state when loading failed", () => {
        benchmark = makeBenchmark({ error: new Error("boom") });
        renderAt(`/setup/${SETUP_ID}`);
        expect(screen.getByText(/Couldn't load benchmark data/i)).toBeInTheDocument();
    });

    it("renders catastrophic failure details under task name on quality metrics, expanding when >3 items", () => {
        benchmark = makeBenchmark({
            setups: [
                {
                    id: SETUP_ID,
                    order: 0,
                    model: "alpha-pro",
                    harness: "gemini-cli",
                    augmentation: [],
                    color: "#3b82f6",
                    catastrophicCount: 2,
                    tasks: [
                        {
                            folder: "cat-task",
                            name: "Catastrophic Task",
                            scores: { composite: 0, pass1: 0, latency: 45 },
                            catastrophic: true,
                            catastrophicKinds: ["VerificationCatastrophic", "IntegrityCatastrophic"],
                            catastrophicDetails: {
                                VerificationCatastrophic: [
                                    { name: "chk-1", reason: "deployment/a: replicas expected 1, got 0", trial: 1 },
                                    { name: "chk-2", reason: "deployment/b: image mismatch", trial: 2 },
                                    { name: "chk-3", reason: "cronjob/c: suspend expected false, got true", trial: 2 }
                                ],
                                IntegrityCatastrophic: [
                                    { reason: "Accessed benchmark material", trial: 3 }
                                ]
                            }
                        },
                        {
                            folder: "legacy-task",
                            name: "Legacy Task",
                            scores: { composite: 0, pass1: 0, latency: 30 },
                            catastrophic: true,
                            catastrophicKinds: ["VerificationCatastrophic"],
                            catastrophicDetails: {}
                        }
                    ],
                    history: []
                }
            ]
        });

        renderAt(`/setup/${SETUP_ID}`);

        // Collapsed dropdown button shows "Failure: Verification (3), Integrity (1)"
        const toggleBtn = screen.getByRole("button", { name: /Failure: Verification \(3\), Integrity \(1\)/i });
        expect(toggleBtn).toBeInTheDocument();
        expect(screen.queryByText("chk-1")).not.toBeInTheDocument();
        expect(screen.queryByText("deployment/a: replicas expected 1, got 0")).not.toBeInTheDocument();

        // Click dropdown to expand all entries and reasons
        fireEvent.click(toggleBtn);
        expect(screen.getByText("chk-1")).toBeInTheDocument();
        expect(screen.getByText("deployment/a: replicas expected 1, got 0")).toBeInTheDocument();
        expect(screen.getByText("chk-2")).toBeInTheDocument();
        expect(screen.getByText("chk-3")).toBeInTheDocument();
        expect(screen.getByText("Accessed benchmark material")).toBeInTheDocument();

        // Click header button again to collapse
        fireEvent.click(screen.getByRole("button", { name: /Failure: Verification \(3\), Integrity \(1\)/i }));
        expect(screen.queryByText("chk-1")).not.toBeInTheDocument();

        // Legacy fallback rendered for task with empty catastrophicDetails
        expect(screen.getByText("Failure: Verification")).toBeInTheDocument();

        // When switched to an efficiency metric, failure details are hidden
        cleanup();
        renderAt(`/setup/${SETUP_ID}?metric=latency`);
        expect(screen.queryByText(/Failure: Verification/i)).not.toBeInTheDocument();
    });

    it("hides scope toggle buttons when scope filter is disabled", () => {
        setScopeFilterEnabled(false);
        try {
            renderAt(`/setup/${SETUP_ID}`);
            expect(screen.queryByRole("button", { name: /Common Tasks/i })).not.toBeInTheDocument();
            expect(screen.queryByRole("button", { name: /All Tasks/i })).not.toBeInTheDocument();
        } finally {
            setScopeFilterEnabled(true);
        }
    });

    it("honors ?scope=common and switches task scope on click when enabled", () => {
        renderAt(`/setup/${SETUP_ID}?scope=common`);
        const commonBtn = screen.getByRole("button", { name: /Common Tasks/i });
        const allBtn = screen.getByRole("button", { name: /All Tasks/i });
        expect(commonBtn).toHaveAttribute("aria-pressed", "true");
        expect(allBtn).toHaveAttribute("aria-pressed", "false");

        fireEvent.click(allBtn);
        expect(allBtn).toHaveAttribute("aria-pressed", "true");
        expect(commonBtn).toHaveAttribute("aria-pressed", "false");
    });

    it("displays correct Common Tasks count regardless of currently active scope when enabled", () => {
        benchmark = makeBenchmark({
            setups: [
                {
                    id: SETUP_ID, order: 0, model: "alpha-pro", harness: "gemini-cli",
                    augmentation: [], color: "#3b82f6",
                    tasks: [
                        { folder: "a", name: "Apple", scores: { composite: 60, pass1: 60 } },
                        { folder: "b", name: "Banana", scores: { composite: 90, pass1: 90 } },
                        { folder: "c", name: "Cherry", scores: { composite: 80, pass1: 80 } }
                    ],
                    history: []
                },
                {
                    id: "setup-2", order: 1, model: "alpha-pro", harness: "gemini-cli",
                    augmentation: [], color: "#ef4444",
                    tasks: [
                        { folder: "a", name: "Apple", scores: { composite: 50, pass1: 50 } }
                    ],
                    history: []
                }
            ]
        });

        renderAt(`/setup/${SETUP_ID}`);
        // In full suite view, All Tasks is 3 and Common Tasks is 1
        expect(screen.getByRole("button", { name: "All Tasks (3)" })).toBeInTheDocument();
        expect(screen.getByRole("button", { name: "Common Tasks (1)" })).toBeInTheDocument();

        // Clicking Common Tasks preserves the (1) count label
        fireEvent.click(screen.getByRole("button", { name: "Common Tasks (1)" }));
        expect(screen.getByRole("button", { name: "All Tasks (3)" })).toBeInTheDocument();
        expect(screen.getByRole("button", { name: "Common Tasks (1)" })).toBeInTheDocument();
    });

    it("does not render generic Failure: Catastrophic when details and kinds are absent", () => {
        benchmark = makeBenchmark({
            setups: [
                {
                    id: SETUP_ID, order: 0, model: "alpha-pro", harness: "gemini-cli",
                    augmentation: [], color: "#3b82f6", catastrophicCount: 1,
                    tasks: [
                        { folder: "a", name: "Apple", scores: { composite: 0 }, catastrophic: true }
                    ],
                    history: []
                }
            ]
        });

        renderAt(`/setup/${SETUP_ID}`);
        expect(screen.queryByText(/Failure: Catastrophic/i)).not.toBeInTheDocument();
    });
});
