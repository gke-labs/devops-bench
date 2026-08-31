import { describe, it, expect, vi } from "vitest";
import { render, screen, fireEvent } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";

// Stub the chart (jsdom has no real canvas) and the data context.
vi.mock("react-chartjs-2", () => ({ Line: () => null }));

const FIXTURE = {
    models: {
        "alpha-pro": { name: "Alpha Pro", provider: "Acme", logo: "alpha" },
        "gamma-coder": { name: "Gamma Coder", provider: "Initech", logo: "gamma" }
    },
    harnesses: {
        "gemini-cli": { name: "Gemini CLI", type: "cli", accent: "#0ea5e9", logo: "terminal" },
        "openclaw": { name: "OpenClaw", type: "cli", accent: "#f43f5e", logo: "claw" }
    },
    setups: [
        // Deliberately ranked against the alphabet: Gamma Coder leads on
        // composite while Alpha Pro leads on latency, so a sort assertion can
        // tell rank order, reverse-rank order and name order apart.
        {
            id: "alpha-pro-gemini-cli", order: 0, model: "alpha-pro", harness: "gemini-cli",
            augmentation: [], color: "#3b82f6",
            tasks: [{ folder: "a", name: "A", scores: { pass1: 90, pass5: 95, passMax: 100, composite: 70, latency: 20 } }],
            history: [{ t: "2026-01-15T00:00:00Z", scores: { pass1: 90, pass5: 95, passMax: 100, composite: 70, latency: 20 } }]
        },
        {
            id: "gamma-coder-openclaw-mcp-skills", order: 1, model: "gamma-coder", harness: "openclaw",
            augmentation: ["mcp", "skills"], color: "#ec4899",
            tasks: [{ folder: "a", name: "A", scores: { pass1: 70, pass5: 75, passMax: 80, composite: 90, latency: 50 } }],
            history: [{ t: "2026-01-15T00:00:00Z", scores: { pass1: 70, pass5: 75, passMax: 80, composite: 90, latency: 50 } }]
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

describe("Leaderboard", () => {
    it("renders one row link per setup", () => {
        renderPage();
        expect(screen.getAllByRole("link")).toHaveLength(2);
        expect(screen.getByText("2 of 2")).toBeInTheDocument();
    });

    it("narrows the list when a facet is toggled", () => {
        renderPage();
        // The model "Alpha Pro" filter chip (a button, distinct from the row link).
        fireEvent.click(screen.getByRole("button", { name: "Alpha Pro" }));
        expect(screen.getByText("1 of 2")).toBeInTheDocument();
        expect(screen.getAllByRole("link")).toHaveLength(1);
    });

    it("updates the active metric on toggle", () => {
        renderPage();
        const pass5 = screen.getByRole("button", { name: "Pass@5" });
        fireEvent.click(pass5);
        expect(pass5).toHaveAttribute("aria-pressed", "true");
    });

    it("names the selected metric in the trend heading and caption", () => {
        // The heading used to be hardcoded "Accuracy Performance Trend Over
        // Time", which reads as a falsehood under an efficiency metric where
        // the series is seconds or tokens rather than a success rate.
        renderPage();
        expect(screen.getByRole("heading", { name: /Outcome Trend Over Time/i })).toBeInTheDocument();

        fireEvent.click(screen.getByRole("button", { name: "Pass@5" }));
        expect(screen.getByRole("heading", { name: /Pass@5 Trend Over Time/i })).toBeInTheDocument();
        expect(screen.queryByText(/success rates/i)).not.toBeInTheDocument();
    });
});

// Row order, read off the links in DOM order.
const order = () => screen.getAllByRole("link").map(a => a.getAttribute("aria-label"));
const modelHeader = () => screen.getByRole("button", { name: /^MODEL/ });
const metricHeader = () => screen.getByRole("button", { name: /^METRIC/ });

describe("Leaderboard sorting", () => {
    it("still opens ranked best-first, so it reads as a leaderboard", () => {
        renderPage();
        // Gamma leads on composite despite sorting second alphabetically.
        expect(order()[0]).toMatch(/Gamma Coder/);
    });

    it("sorts alphabetically when the identity header is clicked", () => {
        renderPage();
        fireEvent.click(modelHeader());
        expect(order()[0]).toMatch(/Alpha Pro/);
    });

    it("holds that order across metric tabs, which is the point of having it", () => {
        // The reason to sort by name is to read one setup down the columns.
        // Re-ranking on every tab makes that impossible, so the sort key has to
        // survive a metric change. Composite and latency rank oppositely here,
        // so a regression to auto-rank would visibly reorder.
        renderPage();
        fireEvent.click(modelHeader());
        for (const m of ["Latency", "Pass@5"]) {
            fireEvent.click(screen.getByRole("button", { name: m }));
            expect(order()[0]).toMatch(/Alpha Pro/);
        }
    });

    it("re-ranks per metric while sorted by rank, the pre-existing behavior", () => {
        renderPage();
        expect(order()[0]).toMatch(/Gamma Coder/);
        // Best latency is the SMALLEST, so Alpha (20s) leads Gamma (50s).
        fireEvent.click(screen.getByRole("button", { name: "Latency" }));
        expect(order()[0]).toMatch(/Alpha Pro/);
    });

    it("flips direction when the active header is clicked again", () => {
        renderPage();
        fireEvent.click(modelHeader());
        expect(order()[0]).toMatch(/Alpha Pro/);
        fireEvent.click(modelHeader());
        expect(order()[0]).toMatch(/Gamma Coder/);

        fireEvent.click(metricHeader());
        expect(order()[0]).toMatch(/Gamma Coder/);
        fireEvent.click(metricHeader());
        expect(order()[0]).toMatch(/Alpha Pro/);
    });

    it("points the arrow at the values, not the sort flag, on a lower-is-better metric", () => {
        // Best-first on latency is ASCENDING numbers. A ▼ there would sit above
        // a column reading 20.0s → 50.0s.
        renderPage();
        fireEvent.click(screen.getByRole("button", { name: "Latency" }));
        expect(metricHeader()).toHaveAccessibleName(/sorted ascending/);
        fireEvent.click(metricHeader());
        expect(metricHeader()).toHaveAccessibleName(/sorted descending/);
    });
});
