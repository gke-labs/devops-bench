import { describe, it, expect, vi } from "vitest";
import { render, screen, fireEvent } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { setScopeFilterEnabled } from "../lib/taskScope.js";

// Stub the chart (jsdom has no real canvas) and the data context.
vi.mock("react-chartjs-2", () => ({ Line: () => null, Bar: () => null, Scatter: () => null }));

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
            augmentation: [], color: "#3b82f6", catastrophicCount: 2,
            tasks: [{ folder: "a", name: "A", scores: { pass1: 90, pass5: 95, passMax: 100, tokens: 150000, inputTokens: 20000, cachedTokens: 120000, outputTokens: 10000 } }],
            history: [{ t: "2026-01-15T00:00:00Z", scores: { pass1: 90, pass5: 95, passMax: 100, tokens: 150000, inputTokens: 20000, cachedTokens: 120000, outputTokens: 10000 } }]
        },
        {
            id: "gamma-coder-openclaw-mcp-skills", order: 1, model: "gamma-coder", harness: "openclaw",
            augmentation: ["mcp", "skills"], color: "#ec4899",
            tasks: [{ folder: "a", name: "A", scores: { pass1: 70, pass5: 75, passMax: 80, tokens: 80000, inputTokens: 15000, cachedTokens: 60000, outputTokens: 5000 } }],
            history: [{ t: "2026-01-15T00:00:00Z", scores: { pass1: 70, pass5: 75, passMax: 80, tokens: 80000, inputTokens: 15000, cachedTokens: 60000, outputTokens: 5000 } }]
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

    it("renders the combined tokens view showing all 3 token counts together", () => {
        renderPage();
        const tokensBtn = screen.getByRole("button", { name: "Tokens" });
        expect(tokensBtn).toBeInTheDocument();
        fireEvent.click(tokensBtn);
        expect(tokensBtn).toHaveAttribute("aria-pressed", "true");

        // Header legend for combined tokens
        expect(screen.getByText("In")).toBeInTheDocument();
        expect(screen.getByText("Cached")).toBeInTheDocument();
        expect(screen.getByText("Out")).toBeInTheDocument();

        // Check that the 3 token counts are visible together for each setup row
        expect(screen.getByText("20.0k in")).toBeInTheDocument();
        expect(screen.getByText("120.0k cached")).toBeInTheDocument();
        expect(screen.getByText("10.0k out")).toBeInTheDocument();

        expect(screen.getByText("15.0k in")).toBeInTheDocument();
        expect(screen.getByText("60.0k cached")).toBeInTheDocument();
        expect(screen.getByText("5.0k out")).toBeInTheDocument();

        // Total token figures are rendered
        expect(screen.getByText("150.0k")).toBeInTheDocument();
        expect(screen.getByText("80.0k")).toBeInTheDocument();
    });

    it("notes that metrics are task averages in header and footnote", () => {
        renderPage();
        expect(screen.getByText(/All leaderboard scores and metrics represent the average per task/i)).toBeInTheDocument();
        expect(screen.getByText(/All leaderboard scores and efficiency figures represent task averages/i)).toBeInTheDocument();
    });

    it("does not render the catastrophic failure badge on the leaderboard rows", () => {
        renderPage();
        expect(screen.queryByText(/Catastrophic Failure/i)).not.toBeInTheDocument();
        expect(screen.queryByText(/⚠ \d+/)).not.toBeInTheDocument();
    });

    it("hides Scope toggle buttons when scope filter is disabled", () => {
        setScopeFilterEnabled(false);
        try {
            renderPage();
            expect(screen.queryByRole("button", { name: /Full Suite/i })).not.toBeInTheDocument();
            expect(screen.queryByRole("button", { name: /Common Tasks/i })).not.toBeInTheDocument();
        } finally {
            setScopeFilterEnabled(true);
        }
    });

    it("renders Scope toggle buttons and switches between scopes when enabled", () => {
        renderPage();
        const fullBtn = screen.getByRole("button", { name: /Full Suite/i });
        const commonBtn = screen.getByRole("button", { name: /Common Tasks/i });
        expect(fullBtn).toBeInTheDocument();
        expect(commonBtn).toBeInTheDocument();
        expect(fullBtn).toHaveAttribute("aria-pressed", "true");
        expect(commonBtn).toHaveAttribute("aria-pressed", "false");

        fireEvent.click(commonBtn);
        expect(commonBtn).toHaveAttribute("aria-pressed", "true");
        expect(fullBtn).toHaveAttribute("aria-pressed", "false");
    });
});
