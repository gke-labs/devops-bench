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
        {
            id: "alpha-pro-gemini-cli", order: 0, model: "alpha-pro", harness: "gemini-cli",
            augmentation: [], color: "#3b82f6",
            tasks: [{ folder: "a", name: "A", scores: { pass1: 90, pass5: 95, passMax: 100 } }],
            history: [{ t: "2026-01-15T00:00:00Z", scores: { pass1: 90, pass5: 95, passMax: 100 } }]
        },
        {
            id: "gamma-coder-openclaw-mcp-skills", order: 1, model: "gamma-coder", harness: "openclaw",
            augmentation: ["mcp", "skills"], color: "#ec4899",
            tasks: [{ folder: "a", name: "A", scores: { pass1: 70, pass5: 75, passMax: 80 } }],
            history: [{ t: "2026-01-15T00:00:00Z", scores: { pass1: 70, pass5: 75, passMax: 80 } }]
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
});
