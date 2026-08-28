import { describe, it, expect, vi } from "vitest";
import { render, screen, within, fireEvent } from "@testing-library/react";

// Stub the canvases; what is under test is the section logic and the sr-only
// tables the charts render beside them.
vi.mock("react-chartjs-2", () => ({ Scatter: () => null, Bar: () => null }));

import { ChartsPanel } from "./ChartsPanel.jsx";

const models = { "alpha-pro": { name: "Alpha Pro" }, "beta-sonic": { name: "Beta Sonic" } };
const harnesses = {
    "gemini-cli": { name: "Gemini CLI", accent: "#0ea5e9" },
    "openclaw": { name: "OpenClaw", accent: "#f43f5e" }
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
    composite: 82, cost: 0.4, tokens: 40000, latency: 30,
    tokensInput: 10000, tokensCached: 25000, tokensCacheWrite: 3000,
    tokensReasoning: 1000, tokensOutput: 1000,
    turns: 14, toolCalls: 31
};
const cheaper = {
    composite: 74, cost: 0.1, tokens: 12000, latency: 18,
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

const sectionTitles = () =>
    screen.getAllByRole("heading", { level: 3 }).map(h => h.textContent);

describe("ChartsPanel layout", () => {
    it("stacks every section on one page, ranked bars before the matching scatter", () => {
        renderPanel();
        expect(sectionTitles()).toEqual([
            "Outcome Index",
            "Harness Comparison",
            "Token Usage per Task",
            "Outcome Index vs. Total Tokens",
            "Cost per Task",
            "Outcome Index vs. Cost per Task",
            "Time per Task",
            "Outcome Index vs. Execution Time",
            "Per-Task Spread"
        ]);
    });

    it("says which direction is good, so a long bar is never ambiguous", () => {
        renderPanel();
        const heading = screen.getByRole("heading", { level: 3, name: "Cost per Task" });
        expect(heading.parentElement).toHaveTextContent("Lower is better");
        expect(
            screen.getByRole("heading", { level: 3, name: "Outcome Index" }).parentElement
        ).toHaveTextContent("Higher is better");
    });

    it("omits a section whose metric nothing measured, rather than drawing it empty", () => {
        const noCost = [setup("a", "alpha-pro", "gemini-cli", { ...full, cost: null })];
        render(<ChartsPanel setups={noCost} models={models} harnesses={harnesses} />);
        expect(sectionTitles()).not.toContain("Cost per Task");
        expect(sectionTitles()).not.toContain("Outcome Index vs. Cost per Task");
        // The metrics that ARE measured still get their sections.
        expect(sectionTitles()).toContain("Time per Task");
    });

    it("ranks each bar chart best-first, which is not the same direction on every metric", () => {
        renderPanel();
        const rank = title => {
            const table = screen.getByRole("heading", { level: 3, name: title })
                .closest("section")
                .querySelector("table");
            return within(table).getAllByRole("rowheader").map(th => th.textContent);
        };
        // Highest outcome first...
        expect(rank("Outcome Index")[0]).toMatch(/Alpha Pro/);
        // ...but cheapest first.
        expect(rank("Cost per Task")[0]).toMatch(/Beta Sonic/);
    });

    it("orders every chart best-first, not by whatever order the setups arrived in", () => {
        // Input order is deliberately the ranking of no metric — Gamma is first
        // in the array and best at nothing — so each assertion below fails if
        // its chart just renders the setups as they arrived.
        const middle = {
            composite: 78, cost: 0.25, tokens: 23000, latency: 24,
            tokensInput: 6000, tokensCached: 15000, tokensCacheWrite: 1000,
            tokensReasoning: 500, tokensOutput: 700,
            turns: 11, toolCalls: 20
        };
        render(
            <ChartsPanel
                setups={[
                    setup("c", "alpha-pro", "openclaw", middle),
                    setup("a", "alpha-pro", "gemini-cli", full),
                    setup("b", "beta-sonic", "openclaw", cheaper)
                ]}
                models={models}
                harnesses={harnesses}
            />
        );
        const firstRow = title => {
            const table = screen.getByRole("heading", { level: 3, name: title })
                .closest("section")
                .querySelector("table");
            return within(table).getAllByRole("rowheader")[0].textContent;
        };
        // Exact labels, not /Alpha Pro/: two of the three setups are Alpha Pro,
        // so a model-name match would pass on an unsorted chart.
        const best = "Alpha Pro × Gemini CLI · Baseline";
        const cheapest = "Beta Sonic × OpenClaw · Baseline";
        expect(firstRow("Outcome Index")).toBe(best);              // highest score
        expect(firstRow("Cost per Task")).toBe(cheapest);          // cheapest
        expect(firstRow("Time per Task")).toBe(cheapest);          // fastest
        expect(firstRow("Token Usage per Task")).toBe(cheapest);   // shortest stack
        expect(firstRow("Per-Task Spread")).toBe(best);            // highest mean
        // The scatter has no reading order, but its accessible table does:
        // ranked on the y metric, so a screen reader gets the same ranking the
        // dot positions give a sighted reader.
        expect(firstRow("Outcome Index vs. Cost per Task")).toBe(best);
    });

    it("marks the non-dominated setups on the outcome scatters", () => {
        renderPanel();
        const table = screen.getByRole("heading", { level: 3, name: "Outcome Index vs. Cost per Task" })
            .closest("section")
            .querySelector("table");
        // Neither beats the other on both axes: b is cheaper, a scores higher.
        expect(within(table).getByRole("columnheader", { name: "On Pareto frontier" })).toBeInTheDocument();
        for (const name of [/Alpha Pro/, /Beta Sonic/]) {
            const row = within(table).getByRole("rowheader", { name }).closest("tr");
            expect(within(row).getAllByRole("cell").at(-1)).toHaveTextContent("yes");
        }
    });

    it("shows the token stack per bucket, with an em dash for an unreported bucket", () => {
        renderPanel();
        const table = screen.getByRole("heading", { level: 3, name: "Token Usage per Task" })
            .closest("section")
            .querySelector("table");
        for (const label of ["Input Tokens", "Cached Tokens", "Cache Write Tokens", "Reasoning Tokens", "Output Tokens"]) {
            expect(within(table).getByRole("columnheader", { name: label })).toBeInTheDocument();
        }
        const row = within(table).getByRole("rowheader", { name: /Beta Sonic/ }).closest("tr");
        expect(within(row).getAllByRole("cell")[3]).toHaveTextContent("—");
    });

    it("compares harnesses with the model held constant", () => {
        const paired = [
            setup("a", "alpha-pro", "gemini-cli", { ...cheaper, cost: 0.2 }),
            setup("b", "alpha-pro", "openclaw", { ...full, cost: 0.5 })
        ];
        render(<ChartsPanel setups={paired} models={models} harnesses={harnesses} />);
        const row = screen.getByRole("rowheader", { name: "Alpha Pro · Baseline" }).closest("tr");
        expect(within(row).getAllByRole("cell")[0]).toHaveTextContent("Gemini CLI");
        expect(screen.getByRole("cell", { name: "150% worse than best" })).toBeInTheDocument();
    });

    it("says nothing to compare when no model ran on two harnesses", () => {
        // The default fixture pairs each model with one harness, so a bar chart
        // here would compare models while claiming to compare harnesses.
        renderPanel();
        expect(screen.getByText(/ran on more than one harness/)).toBeInTheDocument();
    });

    it("switches the metric the harness section compares", () => {
        const paired = [
            setup("a", "alpha-pro", "gemini-cli", { ...cheaper, latency: 10 }),
            setup("b", "alpha-pro", "openclaw", { ...full, latency: 30 })
        ];
        render(<ChartsPanel setups={paired} models={models} harnesses={harnesses} />);
        fireEvent.change(screen.getByLabelText("Metric", { selector: "#harness-metric" }), {
            target: { value: "latency" }
        });
        expect(screen.getByRole("cell", { name: "200% worse than best" })).toBeInTheDocument();
    });

    it("lists one row per task in the spread section", () => {
        const spread = [setup("a", "alpha-pro", "gemini-cli", full, [
            { folder: "t1", name: "Task 1", scores: { composite: 90 } },
            { folder: "t2", name: "Task 2", scores: { composite: 40 } }
        ])];
        render(<ChartsPanel setups={spread} models={models} harnesses={harnesses} />);
        expect(screen.getByRole("cell", { name: "Task 1" })).toBeInTheDocument();
        expect(screen.getByRole("cell", { name: "Task 2" })).toBeInTheDocument();
    });
});

describe("ChartsPanel custom explorer", () => {
    it("is folded away rather than competing with the curated sections", () => {
        renderPanel();
        const summary = screen.getByText("Plot any two metrics");
        expect(summary.closest("details")).not.toHaveAttribute("open");
    });

    it("drops the frontier, where 'non-dominated' has no meaning", () => {
        renderPanel();
        const details = screen.getByText("Plot any two metrics").closest("details");
        expect(within(details).queryByRole("columnheader", { name: "On Pareto frontier" })).not.toBeInTheDocument();
        expect(within(details).getByLabelText("X")).toBeInTheDocument();
        expect(within(details).getByLabelText("Y")).toBeInTheDocument();
    });

    it("offers chart-only axes in the pickers, grouped", () => {
        renderPanel();
        const options = within(screen.getByLabelText("X")).getAllByRole("option").map(o => o.textContent);
        // Token buckets are not leaderboard columns; this is the only place they
        // can be plotted.
        expect(options).toContain("Cached Tokens");
        expect(options).toContain("Tool Calls");
    });

    it("disables a log toggle when a plotted value is zero, which the axis cannot draw", () => {
        const withZero = [
            setup("a", "alpha-pro", "gemini-cli", { ...full, toolCalls: 0, tokens: 40000 }),
            setup("b", "beta-sonic", "openclaw", { ...cheaper, toolCalls: 12, tokens: 12000 })
        ];
        render(<ChartsPanel setups={withZero} models={models} harnesses={harnesses} />);
        expect(screen.getByLabelText("log X")).toBeEnabled();   // tokens, all positive

        fireEvent.change(screen.getByLabelText("X"), { target: { value: "toolCalls" } });
        expect(screen.getByLabelText("log X")).toBeDisabled();
        expect(screen.getByLabelText("log X").checked).toBe(false);
    });
});
