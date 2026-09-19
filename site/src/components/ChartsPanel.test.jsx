import { describe, it, expect, vi } from "vitest";
import { render, screen, within, fireEvent } from "@testing-library/react";

// Stub the canvases; what is under test is the section logic and the sr-only
// tables the charts render beside them.
vi.mock("react-chartjs-2", () => ({ Scatter: () => null, Bar: () => null }));

import { ChartsPanel } from "./ChartsPanel.jsx";

const models = { "alpha-pro": { name: "Alpha Pro" }, "beta-sonic": { name: "Beta Sonic" } };
const harnesses = {
    "gemini-cli": { name: "Gemini CLI", accent: "#0ea5e9", logo: "terminal" },
    "openclaw": { name: "OpenClaw", accent: "#f43f5e", logo: "claw" }
};

const setup = (id, model, harness, scores, tasks) => ({
    id,
    model,
    harness,
    augmentation: [],
    color: "#3b82f6",
    tasks: tasks ?? [{ folder: "t1", name: "Task 1", scores }],
    history: [{ t: "2026-02-15T00:00:00Z", scores }]
});

const full = {
    composite: 82, correctness: 85, recoverableSafety: 90,
    cost: 0.4, tokens: 40000, latency: 30,
    tokensInput: 10000, tokensCached: 25000, tokensCacheWrite: 3000,
    tokensReasoning: 1000, tokensOutput: 1000,
    turns: 14, toolCalls: 31
};
const cheaper = {
    composite: 74, correctness: 78, recoverableSafety: 85,
    cost: 0.1, tokens: 12000, latency: 18,
    tokensInput: 8000, tokensCached: 3000, tokensCacheWrite: 500,
    tokensReasoning: null, tokensOutput: 500,
    turns: 8, toolCalls: 12
};

const setups = [
    setup("a", "alpha-pro", "gemini-cli", full),
    setup("b", "beta-sonic", "openclaw", cheaper)
];

function renderPanel(props = {}) {
    return render(<ChartsPanel setups={setups} models={models} harnesses={harnesses} {...props} />);
}

describe("ChartsPanel layout", () => {
    it("renders the Score vs Efficiency plot with vs tabs and subtab toggle", () => {
        renderPanel();
        expect(screen.getByRole("heading", { level: 2, name: /Score vs. Efficiency/i })).toBeInTheDocument();

        // Check tabs
        expect(screen.getByRole("button", { name: "Score vs Time" })).toBeInTheDocument();
        expect(screen.getByRole("button", { name: "Score vs Cost" })).toBeInTheDocument();
        expect(screen.getByRole("button", { name: "Score vs Tokens" })).toBeInTheDocument();

        // Check subtab aggregation options
        expect(screen.getByRole("button", { name: "Average" })).toBeInTheDocument();
        expect(screen.getByRole("button", { name: "Total" })).toBeInTheDocument();
    });

    it("switches vs tabs on click", () => {
        renderPanel();
        expect(screen.getByRole("heading", { level: 3, name: "Score vs Time" })).toBeInTheDocument();

        fireEvent.click(screen.getByRole("button", { name: "Score vs Cost" }));
        expect(screen.getByRole("heading", { level: 3, name: "Score vs Cost" })).toBeInTheDocument();

        fireEvent.click(screen.getByRole("button", { name: "Score vs Tokens" }));
        expect(screen.getByRole("heading", { level: 3, name: "Score vs Tokens" })).toBeInTheDocument();
    });

    it("switches aggregation subtab between Average and Total", () => {
        renderPanel();
        const avgBtn = screen.getByRole("button", { name: "Average" });
        const totalBtn = screen.getByRole("button", { name: "Total" });

        expect(avgBtn).toHaveAttribute("aria-pressed", "true");
        expect(totalBtn).toHaveAttribute("aria-pressed", "false");

        fireEvent.click(totalBtn);
        expect(totalBtn).toHaveAttribute("aria-pressed", "true");
        expect(avgBtn).toHaveAttribute("aria-pressed", "false");
        expect(screen.getByText(/across all tasks/i)).toBeInTheDocument();
    });

    it("renders the box plot collapsed by default and expands on click", () => {
        renderPanel();
        expect(screen.getByRole("heading", { level: 2, name: /Task Performance Spread/i })).toBeInTheDocument();
        const toggleBtn = screen.getByRole("button", { name: /Expand Box Plot/i });
        expect(toggleBtn).toBeInTheDocument();

        // Box plot content is not visible yet
        expect(screen.queryByText(/Spread Across Tasks/i)).not.toBeInTheDocument();

        // Click to expand
        fireEvent.click(toggleBtn);
        expect(screen.getByText(/Collapse Box Plot/i)).toBeInTheDocument();
        expect(screen.getByText(/Spread Across Tasks/i)).toBeInTheDocument();

        // Metric buttons in box plot are visible
        expect(screen.getByRole("button", { name: "Overall Score" })).toBeInTheDocument();
        expect(screen.getByRole("button", { name: "Time" })).toBeInTheDocument();

        // Click to collapse
        fireEvent.click(screen.getByRole("button", { name: /Collapse Box Plot/i }));
        expect(screen.queryByText(/Spread Across Tasks/i)).not.toBeInTheDocument();
    });

    it("allows adjusting the box plot metric when expanded", () => {
        renderPanel();
        fireEvent.click(screen.getByRole("button", { name: /Expand Box Plot/i }));

        expect(screen.getByRole("heading", { level: 3, name: /Outcome Spread Across Tasks/i })).toBeInTheDocument();

        // Click Time metric
        fireEvent.click(screen.getByRole("button", { name: "Time" }));
        expect(screen.getByRole("heading", { level: 3, name: /Latency Spread Across Tasks/i })).toBeInTheDocument();
    });

    it("omits tabs for unmeasured metrics", () => {
        const noCost = [setup("a", "alpha-pro", "gemini-cli", { ...full, cost: null })];
        render(<ChartsPanel setups={noCost} models={models} harnesses={harnesses} />);
        expect(screen.queryByRole("button", { name: "Score vs Cost" })).not.toBeInTheDocument();
        expect(screen.getByRole("button", { name: "Score vs Time" })).toBeInTheDocument();
    });
});
