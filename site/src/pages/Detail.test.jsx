import { describe, it, expect, beforeEach, vi } from "vitest";
import { render, screen, fireEvent, within } from "@testing-library/react";
import { MemoryRouter, Routes, Route } from "react-router-dom";

// Stub the chart (jsdom has no canvas); the context is mocked per-test below.
vi.mock("react-chartjs-2", () => ({ Line: () => null }));

// Mutable benchmark state so individual tests can switch to loading/error/etc.
let benchmark;
vi.mock("../context/BenchmarkContext.jsx", () => ({
    useBenchmark: () => benchmark
}));

import { Detail } from "./Detail.jsx";

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
                tasks: [
                    { folder: "a", name: "Apple", scores: { pass1: 60, pass5: 65, passMax: 70 } },
                    { folder: "b", name: "Banana", scores: { pass1: 90, pass5: 95, passMax: 100 } },
                    { folder: "c", name: "Cherry", scores: { pass1: 80, pass5: 85, passMax: 90 } }
                ],
                history: [
                    { t: "2026-01-15T00:00:00Z", scores: { pass1: 70, pass5: 75, passMax: 80 } },
                    { t: "2026-02-15T00:00:00Z", scores: { pass1: 80, pass5: 85, passMax: 90 } }
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
                    { folder: "a", name: "Apple", scores: { pass1: 80, pass5: 1, passMax: 1 } },
                    { folder: "b", name: "Banana", scores: { pass1: 60, pass5: 1, passMax: 1 } },
                    { folder: "c", name: "Cherry", scores: { pass1: null, pass5: 1, passMax: 1 } }
                ],
                history: [{ t: "2026-01-15T00:00:00Z", scores: { pass1: 70, pass5: 1, passMax: 1 } }]
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

    it("honors the ?metric= query param", () => {
        renderAt(`/setup/${SETUP_ID}?metric=pass5`);
        expect(screen.getByRole("button", { name: "Pass@5" })).toHaveAttribute("aria-pressed", "true");
        expect(screen.getByRole("button", { name: "Pass@1" })).toHaveAttribute("aria-pressed", "false");
    });

    it("falls back to Pass@1 for an unknown metric param", () => {
        renderAt(`/setup/${SETUP_ID}?metric=bogus`);
        expect(screen.getByRole("button", { name: "Pass@1" })).toHaveAttribute("aria-pressed", "true");
    });

    it("sorts the task table by score desc by default", () => {
        renderAt(`/setup/${SETUP_ID}`);
        expect(taskOrder()).toEqual(["Banana", "Cherry", "Apple"]); // 90, 80, 60
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
        fireEvent.click(screen.getByRole("columnheader", { name: /Score/ }));
        expect(taskOrder()).toEqual(["Apple", "Cherry", "Banana"]); // now ascending
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
});
