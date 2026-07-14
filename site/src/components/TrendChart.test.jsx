import { describe, it, expect, vi } from "vitest";
import { render, screen, within } from "@testing-library/react";

// Stub the canvas chart; the logic under test is the sr-only data table that
// mirrors it for screen readers.
vi.mock("react-chartjs-2", () => ({ Line: () => null }));

import { TrendChart } from "./TrendChart.jsx";

const models = { "alpha-pro": { name: "Alpha Pro" }, "beta-sonic": { name: "Beta Sonic" } };
const harnesses = { "gemini-cli": { name: "Gemini CLI" } };

// Setup B is missing the first run date, so the union axis has two columns and
// B's first cell must render the "—" placeholder.
const setups = [
    {
        id: "a", model: "alpha-pro", harness: "gemini-cli", augmentation: [], color: "#3b82f6",
        history: [
            { t: "2026-01-15T00:00:00Z", scores: { pass1: 70, pass5: 75, passMax: 80 } },
            { t: "2026-02-15T00:00:00Z", scores: { pass1: 80, pass5: 85, passMax: 90 } }
        ]
    },
    {
        id: "b", model: "beta-sonic", harness: "gemini-cli", augmentation: [], color: "#ec4899",
        history: [
            { t: "2026-02-15T00:00:00Z", scores: { pass1: 90, pass5: 95, passMax: 100 } }
        ]
    }
];

function renderChart() {
    return render(
        <TrendChart
            setups={setups}
            metric="pass1"
            models={models}
            harnesses={harnesses}
            caption="Score trend summary"
        />
    );
}

describe("TrendChart accessibility table", () => {
    it("renders the caption and a column per run date (union, sorted)", () => {
        renderChart();
        expect(screen.getByText("Score trend summary")).toBeInTheDocument();
        expect(screen.getByRole("columnheader", { name: "2026-01-15" })).toBeInTheDocument();
        expect(screen.getByRole("columnheader", { name: "2026-02-15" })).toBeInTheDocument();
    });

    it("renders one row per setup with its label", () => {
        renderChart();
        expect(screen.getByRole("rowheader", { name: /Alpha Pro × Gemini CLI/ })).toBeInTheDocument();
        expect(screen.getByRole("rowheader", { name: /Beta Sonic × Gemini CLI/ })).toBeInTheDocument();
    });

    it("fills cells with the metric value and '—' for runs a setup is missing", () => {
        renderChart();
        const rowB = screen.getByRole("rowheader", { name: /Beta Sonic/ }).closest("tr");
        const cells = within(rowB).getAllByRole("cell");
        expect(cells[0]).toHaveTextContent("—");      // missing 2026-01-15
        expect(cells[1]).toHaveTextContent("90.0%");  // present 2026-02-15

        const rowA = screen.getByRole("rowheader", { name: /Alpha Pro/ }).closest("tr");
        const cellsA = within(rowA).getAllByRole("cell");
        expect(cellsA[0]).toHaveTextContent("70.0%");
        expect(cellsA[1]).toHaveTextContent("80.0%");
    });

    it("renders '—' for a present run whose metric value is null (sparse data)", () => {
        // Regression: before the guard, a present run with a null metric crashed
        // on rec.scores[metric].toFixed(...). Now it must render the placeholder.
        const withNull = [{
            id: "c", model: "alpha-pro", harness: "gemini-cli", augmentation: [], color: "#3b82f6",
            history: [
                { t: "2026-01-15T00:00:00Z", scores: { pass1: null, pass5: 50, passMax: 60 } },
                { t: "2026-02-15T00:00:00Z", scores: { pass1: 88, pass5: 90, passMax: 95 } }
            ]
        }];
        render(
            <TrendChart setups={withNull} metric="pass1" models={models} harnesses={harnesses} caption="x" />
        );
        const row = screen.getByRole("rowheader", { name: /Alpha Pro/ }).closest("tr");
        const cells = within(row).getAllByRole("cell");
        expect(cells[0]).toHaveTextContent("—");      // present run, null pass1
        expect(cells[1]).toHaveTextContent("88.0%");
    });
});
