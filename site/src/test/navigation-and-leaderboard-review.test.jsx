import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen, fireEvent, within } from "@testing-library/react";
import { MemoryRouter, Routes, Route } from "react-router-dom";
import { TopBar } from "../components/TopBar.jsx";
import { Leaderboard } from "../pages/Leaderboard.jsx";
import { ChartsPanel } from "../components/ChartsPanel.jsx";
import { MetricToggle, METRIC_ROW_GROUPS } from "../components/MetricToggle.jsx";
import { ThemeToggle } from "../components/ThemeToggle.jsx";
import { setScopeFilterEnabled } from "../lib/taskScope.js";
import { METRIC_LABELS } from "../lib/vocab.js";

// Mock canvas elements used by chart.js
vi.mock("react-chartjs-2", () => ({
    Scatter: () => <div data-testid="scatter-chart" />,
    Bar: () => <div data-testid="bar-chart" />,
    Line: () => <div data-testid="line-chart" />
}));

const MOCK_MODELS = {
    "alpha-pro": { name: "Alpha Pro", provider: "Acme", logo: "alpha" },
    "gamma-coder": { name: "Gamma Coder", provider: "Initech", logo: "gamma" },
    "delta-flash": { name: "Delta Flash", provider: "Google", logo: "delta" }
};

const MOCK_HARNESSES = {
    "gemini-cli": { name: "Gemini CLI", type: "cli", accent: "#0ea5e9", logo: "terminal" },
    "openclaw": { name: "OpenClaw", type: "cli", accent: "#f43f5e", logo: "claw" }
};

// Rich fixture providing scores for all metrics across multiple setups and tasks
const MOCK_SETUPS = [
    {
        id: "alpha-pro-gemini-cli",
        order: 0,
        model: "alpha-pro",
        harness: "gemini-cli",
        augmentation: [],
        color: "#3b82f6",
        catastrophicCount: 0,
        tasks: [
            {
                folder: "task-1",
                name: "Task 1",
                scores: {
                    composite: 85,
                    correctness: 90,
                    recoverableSafety: 95,
                    pass1: 80,
                    pass5: 85,
                    passMax: 90,
                    latency: 20,
                    cost: 0.60,
                    tokens: 120000,
                    inputTokens: 25000,
                    cachedTokens: 85000,
                    outputTokens: 10000,
                    turns: 12,
                    toolCalls: 24
                }
            },
            {
                folder: "task-2",
                name: "Task 2",
                scores: {
                    composite: 85,
                    correctness: 90,
                    recoverableSafety: 95,
                    pass1: 80,
                    pass5: 85,
                    passMax: 90,
                    latency: 30,
                    cost: 0.40,
                    tokens: 80000,
                    inputTokens: 15000,
                    cachedTokens: 55000,
                    outputTokens: 10000,
                    turns: 10,
                    toolCalls: 20
                }
            }
        ],
        history: [
            {
                t: "2026-03-01T00:00:00Z",
                scores: {
                    composite: 85,
                    correctness: 90,
                    recoverableSafety: 95,
                    pass1: 80,
                    pass5: 85,
                    passMax: 90,
                    latency: 25,
                    cost: 0.50,
                    tokens: 100000,
                    inputTokens: 20000,
                    cachedTokens: 70000,
                    outputTokens: 10000
                }
            }
        ]
    },
    {
        id: "gamma-coder-openclaw",
        order: 1,
        model: "gamma-coder",
        harness: "openclaw",
        augmentation: ["mcp"],
        color: "#ec4899",
        catastrophicCount: 1,
        tasks: [
            {
                folder: "task-1",
                name: "Task 1",
                scores: {
                    composite: 65,
                    correctness: 70,
                    recoverableSafety: 75,
                    pass1: 60,
                    pass5: 65,
                    passMax: 70,
                    latency: 40,
                    cost: 0.25,
                    tokens: 60000,
                    inputTokens: 12000,
                    cachedTokens: 42000,
                    outputTokens: 6000,
                    turns: 8,
                    toolCalls: 14
                }
            },
            {
                folder: "task-2",
                name: "Task 2",
                scores: {
                    composite: 75,
                    correctness: 80,
                    recoverableSafety: 85,
                    pass1: 60,
                    pass5: 65,
                    passMax: 70,
                    latency: 50,
                    cost: 0.15,
                    tokens: 40000,
                    inputTokens: 8000,
                    cachedTokens: 28000,
                    outputTokens: 4000,
                    turns: 8,
                    toolCalls: 16
                }
            }
        ],
        history: [
            {
                t: "2026-03-01T00:00:00Z",
                scores: {
                    composite: 70,
                    correctness: 75,
                    recoverableSafety: 80,
                    pass1: 60,
                    pass5: 65,
                    passMax: 70,
                    latency: 45,
                    cost: 0.20,
                    tokens: 50000,
                    inputTokens: 10000,
                    cachedTokens: 35000,
                    outputTokens: 5000
                }
            }
        ]
    },
    {
        id: "delta-flash-openclaw",
        order: 2,
        model: "delta-flash",
        harness: "openclaw",
        augmentation: ["skills"],
        color: "#10b981",
        catastrophicCount: 0,
        // Only task-1 is present -> partial setup (excluded from "full", included in "common")
        tasks: [
            {
                folder: "task-1",
                name: "Task 1",
                scores: {
                    composite: 60,
                    correctness: 65,
                    recoverableSafety: 70,
                    pass1: 50,
                    pass5: 55,
                    passMax: 60,
                    latency: 15,
                    cost: 0.05,
                    tokens: 20000,
                    inputTokens: 4000,
                    cachedTokens: 14000,
                    outputTokens: 2000,
                    turns: 5,
                    toolCalls: 8
                }
            }
        ],
        history: [
            {
                t: "2026-03-01T00:00:00Z",
                scores: {
                    composite: 60,
                    correctness: 65,
                    recoverableSafety: 70,
                    pass1: 50,
                    pass5: 55,
                    passMax: 60,
                    latency: 15,
                    cost: 0.05,
                    tokens: 20000,
                    inputTokens: 4000,
                    cachedTokens: 14000,
                    outputTokens: 2000
                }
            }
        ]
    }
];

vi.mock("../context/BenchmarkContext.jsx", () => ({
    useBenchmark: () => ({
        models: MOCK_MODELS,
        harnesses: MOCK_HARNESSES,
        setups: MOCK_SETUPS,
        loading: false,
        error: null
    })
}));

describe("Comprehensive Review: TopBar Navigation & Theme Toggle", () => {
    beforeEach(() => {
        localStorage.clear();
        document.documentElement.classList.remove("dark");
    });

    it("verifies all TopBar primary links and brand navigation", () => {
        render(
            <MemoryRouter initialEntries={["/"]}>
                <TopBar />
            </MemoryRouter>
        );

        // Brand link
        const brandLink = screen.getByRole("link", { name: /DevOps Bench/i });
        expect(brandLink).toBeInTheDocument();
        expect(brandLink).toHaveAttribute("href", "/");

        // Primary navigation tabs
        const leaderboardLink = screen.getByRole("link", { name: "Leaderboard" });
        const tasksLink = screen.getByRole("link", { name: "Tasks" });
        expect(leaderboardLink).toHaveAttribute("href", "/");
        expect(tasksLink).toHaveAttribute("href", "/tasks");

        // Active tab styling on root path
        expect(leaderboardLink.className).toContain("bg-indigo-50");
        expect(tasksLink.className).not.toContain("bg-indigo-50");

        // External GitHub link
        const githubLink = screen.getByRole("link", { name: /GitHub/i });
        expect(githubLink).toHaveAttribute("href", "https://github.com/kubernetes-sigs/devops-bench");
        expect(githubLink).toHaveAttribute("target", "_blank");
        expect(githubLink).toHaveAttribute("rel", "noopener noreferrer");
    });

    it("verifies active state styling when on /tasks route", () => {
        render(
            <MemoryRouter initialEntries={["/tasks"]}>
                <TopBar />
            </MemoryRouter>
        );

        const leaderboardLink = screen.getByRole("link", { name: "Leaderboard" });
        const tasksLink = screen.getByRole("link", { name: "Tasks" });

        expect(tasksLink.className).toContain("bg-indigo-50");
        expect(leaderboardLink.className).not.toContain("bg-indigo-50");
    });

    it("verifies contextual back button flows for every subroute", () => {
        // Setup detail route -> back to Leaderboard
        const { unmount: unmountSetup } = render(
            <MemoryRouter initialEntries={["/setup/alpha-pro-gemini-cli?metric=composite"]}>
                <TopBar />
            </MemoryRouter>
        );
        const backToLeaderboard = screen.getByRole("link", { name: /← Leaderboard/i });
        expect(backToLeaderboard).toHaveAttribute("href", "/");
        unmountSetup();

        // Task detail route -> back to Tasks catalog
        const { unmount: unmountTask } = render(
            <MemoryRouter initialEntries={["/task/task-1"]}>
                <TopBar />
            </MemoryRouter>
        );
        const backToTasks = screen.getByRole("link", { name: /← Tasks/i });
        expect(backToTasks).toHaveAttribute("href", "/tasks");
        unmountTask();

        // Run detail route from task flow -> back to Task
        const { unmount: unmountRunTask } = render(
            <MemoryRouter initialEntries={["/task/task-1/run/alpha-pro-gemini-cli"]}>
                <TopBar />
            </MemoryRouter>
        );
        const backToTask = screen.getByRole("link", { name: /← Task/i });
        expect(backToTask).toHaveAttribute("href", "/task/task-1");
        unmountRunTask();

        // Run detail route from setup flow -> back to Setup with metric
        const { unmount: unmountRunSetup } = render(
            <MemoryRouter initialEntries={["/task/task-1/run/alpha-pro-gemini-cli?from=setup&metric=latency"]}>
                <TopBar />
            </MemoryRouter>
        );
        const backToSetup = screen.getByRole("link", { name: /← Setup/i });
        expect(backToSetup).toHaveAttribute("href", "/setup/alpha-pro-gemini-cli?metric=latency");
        unmountRunSetup();
    });

    it("verifies ThemeToggle flips theme and updates html class without breaking", () => {
        render(
            <MemoryRouter initialEntries={["/"]}>
                <ThemeToggle />
            </MemoryRouter>
        );

        const themeButton = screen.getByRole("button", { name: /Switch to (dark|light) mode/i });
        expect(themeButton).toBeInTheDocument();

        // Initial toggle
        const initialDark = document.documentElement.classList.contains("dark");
        fireEvent.click(themeButton);

        const nextDark = document.documentElement.classList.contains("dark");
        expect(nextDark).toBe(!initialDark);

        // Second toggle back
        fireEvent.click(themeButton);
        expect(document.documentElement.classList.contains("dark")).toBe(initialDark);
    });
});

describe("Comprehensive Review: Metric Toggles & Leaderboard State", () => {
    it("renders all metric groups in MetricToggle and simulates clicking each metric", () => {
        const onChange = vi.fn();
        const available = [
            "composite", "correctness", "recoverableSafety",
            "pass1", "pass5", "passMax",
            "latency", "tokens", "inputTokens", "outputTokens", "cachedTokens", "cost"
        ];

        render(
            <MetricToggle value="composite" onChange={onChange} available={available} />
        );

        // Verify all 3 groups are displayed
        expect(screen.getByText("Outcome")).toBeInTheDocument();
        expect(screen.getByText("Pass Rates")).toBeInTheDocument();
        expect(screen.getByText("Efficiency")).toBeInTheDocument();

        // Simulate clicking every single available metric button
        for (const metric of available) {
            const expectedLabel = METRIC_LABELS[metric];
            const btn = screen.getByRole("button", { name: expectedLabel });
            expect(btn).toBeInTheDocument();
            expect(btn).not.toBeDisabled();
            fireEvent.click(btn);
            expect(onChange).toHaveBeenCalledWith(metric);
        }
    });

    it("renders disabled state for unavailable metrics", () => {
        const onChange = vi.fn();
        const available = ["composite", "correctness"];

        render(
            <MetricToggle value="composite" onChange={onChange} available={available} />
        );

        const disabledPass5 = screen.getByRole("button", { name: /Pass@5/i });
        expect(disabledPass5).toBeDisabled();
        fireEvent.click(disabledPass5);
        expect(onChange).not.toHaveBeenCalledWith("pass5");
    });

    it("updates Leaderboard table display and sorting across various metrics", () => {
        render(
            <MemoryRouter initialEntries={["/"]}>
                <Leaderboard />
            </MemoryRouter>
        );

        // Default metric: composite
        expect(screen.getByRole("button", { name: "Outcome" })).toHaveAttribute("aria-pressed", "true");
        expect(screen.getAllByText("85.0%").length).toBeGreaterThan(0);

        // Switch to Correctness
        const correctnessBtn = screen.getByRole("button", { name: "Correctness" });
        fireEvent.click(correctnessBtn);
        expect(correctnessBtn).toHaveAttribute("aria-pressed", "true");
        expect(screen.getAllByText("90.0%").length).toBeGreaterThan(0);

        // Switch to Recoverable Safety
        const safetyBtn = screen.getByRole("button", { name: "Recoverable Safety" });
        fireEvent.click(safetyBtn);
        expect(safetyBtn).toHaveAttribute("aria-pressed", "true");
        expect(screen.getAllByText("95.0%").length).toBeGreaterThan(0);

        // Switch to Latency (ascending sort: lower is better)
        const latencyBtn = screen.getByRole("button", { name: "Latency" });
        fireEvent.click(latencyBtn);
        expect(latencyBtn).toHaveAttribute("aria-pressed", "true");
        expect(screen.getAllByText("25.0s").length).toBeGreaterThan(0);
        expect(screen.getAllByText("45.0s").length).toBeGreaterThan(0);

        // Switch to Cost (sub-dollar formatted with 3 decimal places)
        const costBtn = screen.getByRole("button", { name: "Cost" });
        fireEvent.click(costBtn);
        expect(costBtn).toHaveAttribute("aria-pressed", "true");
        expect(screen.getAllByText("$0.500").length).toBeGreaterThan(0);
        expect(screen.getAllByText("$0.200").length).toBeGreaterThan(0);

        // Switch to Tokens (renders breakdown: In, Cached, Out)
        const tokensBtn = screen.getByRole("button", { name: "Tokens" });
        fireEvent.click(tokensBtn);
        expect(tokensBtn).toHaveAttribute("aria-pressed", "true");
        expect(screen.getAllByText("In").length).toBeGreaterThan(0);
        expect(screen.getAllByText("Cached").length).toBeGreaterThan(0);
        expect(screen.getAllByText("Out").length).toBeGreaterThan(0);

        expect(screen.getAllByText("100.0k").length).toBeGreaterThan(0);
        expect(screen.getAllByText("50.0k").length).toBeGreaterThan(0);

        // Switch to Input Tokens
        const inputTokensBtn = screen.getByRole("button", { name: "Input Tokens" });
        fireEvent.click(inputTokensBtn);
        expect(inputTokensBtn).toHaveAttribute("aria-pressed", "true");

        // Switch to Output Tokens
        const outputTokensBtn = screen.getByRole("button", { name: "Output Tokens" });
        fireEvent.click(outputTokensBtn);
        expect(outputTokensBtn).toHaveAttribute("aria-pressed", "true");

        // Switch to Cached Tokens
        const cachedTokensBtn = screen.getByRole("button", { name: "Cached Tokens" });
        fireEvent.click(cachedTokensBtn);
        expect(cachedTokensBtn).toHaveAttribute("aria-pressed", "true");
    });
});

describe("Comprehensive Review: Scope Toggle (Full Suite vs Common Tasks)", () => {
    beforeEach(() => {
        setScopeFilterEnabled(true);
    });

    it("toggles between Full Suite and Common Tasks, updating setup counts and row links", () => {
        render(
            <MemoryRouter initialEntries={["/"]}>
                <Leaderboard />
            </MemoryRouter>
        );

        // Full suite is active initially (2 tasks, 2 setups have all tasks)
        const fullBtn = screen.getByRole("button", { name: /Full Suite/i });
        const commonBtn = screen.getByRole("button", { name: /Common Tasks/i });

        expect(fullBtn).toHaveAttribute("aria-pressed", "true");
        expect(commonBtn).toHaveAttribute("aria-pressed", "false");
        expect(screen.getByText("2 of 2")).toBeInTheDocument();

        // Row links in full suite mode should not have &scope=common
        const linksFull = screen.getAllByRole("link").filter(l => l.getAttribute("href")?.startsWith("/setup/"));
        expect(linksFull).toHaveLength(2);
        expect(linksFull[0].getAttribute("href")).not.toContain("scope=common");

        // Switch to Common Tasks
        fireEvent.click(commonBtn);
        expect(commonBtn).toHaveAttribute("aria-pressed", "true");
        expect(fullBtn).toHaveAttribute("aria-pressed", "false");

        // Common tasks view includes delta-flash (all 3 setups ran task-1)
        expect(screen.getByText("3 of 3")).toBeInTheDocument();
        const linksCommon = screen.getAllByRole("link").filter(l => l.getAttribute("href")?.startsWith("/setup/"));
        expect(linksCommon).toHaveLength(3);
        expect(linksCommon[0].getAttribute("href")).toContain("scope=common");

        // Switch back to Full Suite
        fireEvent.click(fullBtn);
        expect(fullBtn).toHaveAttribute("aria-pressed", "true");
        expect(screen.getByText("2 of 2")).toBeInTheDocument();
    });
});

describe("Comprehensive Review: FilterBar Chips and Clear All", () => {
    it("simulates clicking model/harness filter chips and clearing filters", () => {
        render(
            <MemoryRouter initialEntries={["/"]}>
                <Leaderboard />
            </MemoryRouter>
        );

        expect(screen.getByText("2 of 2")).toBeInTheDocument();

        // Click Alpha Pro chip to filter to 1 setup
        const alphaChip = screen.getByRole("button", { name: /Alpha Pro/i });
        fireEvent.click(alphaChip);
        expect(alphaChip).toHaveAttribute("aria-pressed", "true");
        expect(screen.getByText("1 of 2")).toBeInTheDocument();

        // Clear all button appears
        const clearBtn = screen.getByRole("button", { name: /Clear all/i });
        expect(clearBtn).toBeInTheDocument();
        fireEvent.click(clearBtn);

        // Filter reset to 2 of 2
        expect(screen.getByText("2 of 2")).toBeInTheDocument();
        expect(screen.queryByRole("button", { name: /Clear all/i })).not.toBeInTheDocument();
    });
});

describe("Comprehensive Review: ChartsPanel Tabs, Subtabs, and Box Plot", () => {
    it("simulates clicking comparison tabs, aggregation subtabs, color-by controls, and box plot controls", () => {
        render(
            <ChartsPanel
                setups={MOCK_SETUPS}
                models={MOCK_MODELS}
                harnesses={MOCK_HARNESSES}
            />
        );

        // 1. Comparison tabs
        const timeTab = screen.getByRole("button", { name: "Score vs Time" });
        const costTab = screen.getByRole("button", { name: "Score vs Cost" });
        const tokensTab = screen.getByRole("button", { name: "Score vs Tokens" });

        expect(timeTab).toHaveAttribute("aria-pressed", "true");
        fireEvent.click(costTab);
        expect(costTab).toHaveAttribute("aria-pressed", "true");
        expect(screen.getByRole("heading", { level: 3, name: "Score vs Cost" })).toBeInTheDocument();

        fireEvent.click(tokensTab);
        expect(tokensTab).toHaveAttribute("aria-pressed", "true");
        expect(screen.getByRole("heading", { level: 3, name: "Score vs Tokens" })).toBeInTheDocument();

        // 2. Aggregation subtabs
        const avgBtn = screen.getByRole("button", { name: "Average" });
        const totalBtn = screen.getByRole("button", { name: "Total" });
        expect(avgBtn).toHaveAttribute("aria-pressed", "true");

        fireEvent.click(totalBtn);
        expect(totalBtn).toHaveAttribute("aria-pressed", "true");
        expect(screen.getByText(/across all tasks/i)).toBeInTheDocument();

        fireEvent.click(avgBtn);
        expect(avgBtn).toHaveAttribute("aria-pressed", "true");
        expect(screen.getByText(/average tokens per task/i)).toBeInTheDocument();

        // 3. Color By control
        const colorHarness = screen.getByRole("button", { name: "Color: harness" });
        const colorModel = screen.getByRole("button", { name: "Color: model" });

        expect(colorModel).toHaveAttribute("aria-pressed", "true");
        fireEvent.click(colorHarness);
        expect(colorHarness).toHaveAttribute("aria-pressed", "true");

        // 4. Box Plot expand, metric toggling, and collapse
        const boxPlotToggle = screen.getByRole("button", { name: /Expand Box Plot/i });
        expect(screen.queryByText(/Spread Across Tasks/i)).not.toBeInTheDocument();

        // Expand
        fireEvent.click(boxPlotToggle);
        expect(screen.getByText(/Collapse Box Plot/i)).toBeInTheDocument();
        expect(screen.getByText(/Outcome Spread Across Tasks/i)).toBeInTheDocument();

        // Click Time metric in box plot
        const timeBoxBtn = screen.getByRole("button", { name: "Time" });
        fireEvent.click(timeBoxBtn);
        expect(screen.getByText(/Latency Spread Across Tasks/i)).toBeInTheDocument();

        // Click Cost metric in box plot
        const costBoxBtn = screen.getByRole("button", { name: "Cost" });
        fireEvent.click(costBoxBtn);
        expect(screen.getByText(/Cost Spread Across Tasks/i)).toBeInTheDocument();

        // Click Tokens metric in box plot
        const tokensBoxBtn = screen.getByRole("button", { name: "Tokens" });
        fireEvent.click(tokensBoxBtn);
        expect(screen.getByText(/Tokens Spread Across Tasks/i)).toBeInTheDocument();

        // Collapse
        const collapseBtn = screen.getByRole("button", { name: /Collapse Box Plot/i });
        fireEvent.click(collapseBtn);
        expect(screen.queryByText(/Spread Across Tasks/i)).not.toBeInTheDocument();
    });
});

describe("Comprehensive Review: Table Headers and Static Structure Verification", () => {
    it("verifies Leaderboard table headers are static elements (not sortable buttons)", () => {
        render(
            <MemoryRouter initialEntries={["/"]}>
                <Leaderboard />
            </MemoryRouter>
        );

        // Header column labels
        const modelHeader = screen.getByText("MODEL");
        const harnessHeader = screen.getByText(/HARNESS/);
        const metricHeader = screen.getByText("METRIC");

        expect(modelHeader.tagName).toBe("SPAN");
        expect(harnessHeader.tagName).toBe("SPAN");
        expect(metricHeader.tagName).toBe("SPAN");

        // Ensure headers are NOT buttons and have no sort indicators
        expect(screen.queryByRole("button", { name: "MODEL" })).not.toBeInTheDocument();
        expect(screen.queryByRole("button", { name: /HARNESS/ })).not.toBeInTheDocument();
        expect(screen.queryByRole("button", { name: "METRIC" })).not.toBeInTheDocument();
    });

    it("verifies Leaderboard table rows are links pointing to /setup/:id with metric param", () => {
        render(
            <MemoryRouter initialEntries={["/"]}>
                <Leaderboard />
            </MemoryRouter>
        );

        // Switch to a specific metric first
        const latencyBtn = screen.getByRole("button", { name: "Latency" });
        fireEvent.click(latencyBtn);

        // Verify setup row links contain metric=latency
        const alphaRowLink = screen.getByRole("link", { name: /View details for Alpha Pro × Gemini CLI/i });
        expect(alphaRowLink).toBeInTheDocument();
        expect(alphaRowLink).toHaveAttribute("href", "/setup/alpha-pro-gemini-cli?metric=latency");

        const gammaRowLink = screen.getByRole("link", { name: /View details for Gamma Coder × OpenClaw/i });
        expect(gammaRowLink).toBeInTheDocument();
        expect(gammaRowLink).toHaveAttribute("href", "/setup/gamma-coder-openclaw?metric=latency");
    });
});
