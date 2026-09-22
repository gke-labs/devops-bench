import { describe, it, expect, beforeEach, vi } from "vitest";
import { render, screen, fireEvent, within, cleanup } from "@testing-library/react";
import { MemoryRouter, Routes, Route, useLocation } from "react-router-dom";
import curatedData from "../data/curated_tasks.json";
import { Detail } from "./Detail.jsx";
import { TopBar } from "../components/TopBar.jsx";

// Stub the chart (jsdom has no canvas)
vi.mock("react-chartjs-2", () => ({ Line: () => null }));

// Mutable benchmark state
let benchmark;
vi.mock("../context/BenchmarkContext.jsx", () => ({
    useBenchmark: () => benchmark
}));

function buildSetupFromCurated(setupId, modelInfo, harnessInfo) {
    const tasks = [];
    let catastrophicCount = 0;

    for (const [folder, t] of Object.entries(curatedData.tasks || {})) {
        const run = t.runs?.[setupId];
        if (!run) continue;

        const isCat = Boolean(run.scores?.catastrophic);
        if (isCat) catastrophicCount++;

        const catDetails = {};
        const catKinds = [];
        if (run.checks) {
            for (const c of run.checks) {
                if (c.severity === "catastrophic" && c.status === "fail") {
                    const gate = c.name?.includes("Integrity") ? "IntegrityCatastrophic" : "VerificationCatastrophic";
                    if (!catDetails[gate]) catDetails[gate] = [];
                    catDetails[gate].push({
                        name: c.name,
                        reason: c.observed || c.failure_hint || "Check failed",
                        trial: 1
                    });
                    if (!catKinds.includes(gate)) catKinds.push(gate);
                }
            }
        }

        tasks.push({
            folder,
            name: folder, // when folder is used as name
            scores: {
                composite: run.scores?.outcome != null ? Number((run.scores.outcome * 100).toFixed(1)) : null,
                pass1: run.scores?.c != null ? Number((run.scores.c * 100).toFixed(1)) : null,
                latency: run.durationSec ? Number(run.durationSec.toFixed(1)) : null,
                tokens: run.tokens?.total ?? null,
                tokensInput: run.tokens?.input ?? null,
                tokensCached: run.tokens?.cached ?? null,
                tokensOutput: run.tokens?.output ?? null,
                inputTokens: run.tokens?.input ?? null,
                cachedTokens: run.tokens?.cached ?? null,
                outputTokens: run.tokens?.output ?? null,
            },
            catastrophic: isCat,
            catastrophicKinds: catKinds,
            catastrophicDetails: catDetails
        });
    }

    return {
        id: setupId,
        order: 0,
        model: modelInfo.id,
        harness: harnessInfo.id,
        augmentation: [],
        color: "#3b82f6",
        tasks,
        catastrophicCount,
        history: []
    };
}

// Helper component to track current location during test navigation
function LocationTracker({ onLocation }) {
    const location = useLocation();
    onLocation(location);
    return null;
}

describe("Setup Detail Page Interactive Reviewer Suite", () => {
    let lastLocation = null;

    function renderDetailApp(initialPath = "/setup/claude-fable-5-1-openclaw?metric=composite") {
        lastLocation = null;
        return render(
            <MemoryRouter initialEntries={[initialPath]} future={{ v7_startTransition: true, v7_relativeSplatPath: true }}>
                <LocationTracker onLocation={(loc) => { lastLocation = loc; }} />
                <TopBar />
                <Routes>
                    <Route path="/setup/:id" element={<Detail />} />
                    <Route path="/task/:taskName/run/:setupId" element={<div>Run Detail View</div>} />
                    <Route path="/task/:taskName" element={<div>Task Detail View</div>} />
                    <Route path="/tasks" element={<div>All Tasks View</div>} />
                    <Route path="/" element={<div>Leaderboard View</div>} />
                </Routes>
            </MemoryRouter>
        );
    }

    const models = {
        "claude-fable-5-1": { name: "Claude Fable 5.1", provider: "Anthropic", logo: "anthropic" },
        "gemini-3.8-flash-high": { name: "Gemini 3.8 Flash High", provider: "Google", logo: "gemini" },
        "gpt-5.6-sol": { name: "GPT 5.6 Sol", provider: "OpenAI", logo: "openai" }
    };

    const harnesses = {
        "openclaw": { name: "OpenClaw", type: "cli", accent: "#f43f5e", logo: "claw" },
        "antigravity": { name: "Antigravity", type: "api", accent: "#f59e0b", logo: "google" }
    };

    beforeEach(() => {
        const setupClaude = buildSetupFromCurated(
            "claude-fable-5-1-openclaw",
            { id: "claude-fable-5-1" },
            { id: "openclaw" }
        );
        const setupGemini = buildSetupFromCurated(
            "gemini-3-8-flash-high-antigravity",
            { id: "gemini-3.8-flash-high" },
            { id: "antigravity" }
        );
        const setupGpt = buildSetupFromCurated(
            "gpt-5-6-sol-openclaw",
            { id: "gpt-5.6-sol" },
            { id: "openclaw" }
        );

        benchmark = {
            models,
            harnesses,
            setups: [setupClaude, setupGemini, setupGpt],
            loading: false,
            error: null
        };
    });

    describe("1. Metric Toggle Buttons & Group Interactions", () => {
        it("switches metrics on click in claude-fable-5-1-openclaw and updates headline & stat cards", () => {
            renderDetailApp("/setup/claude-fable-5-1-openclaw?metric=composite");

            // Hero setup identity
            expect(screen.getByText("Claude Fable 5.1")).toBeInTheDocument();
            expect(screen.getByText("OpenClaw")).toBeInTheDocument();

            // Initial Outcome metric
            expect(screen.getByRole("button", { name: "Outcome" })).toHaveAttribute("aria-pressed", "true");
            expect(screen.getByRole("columnheader", { name: /Outcome/ })).toBeInTheDocument();

            // Click Pass@1
            const pass1Btn = screen.getByRole("button", { name: "Pass@1" });
            fireEvent.click(pass1Btn);
            expect(pass1Btn).toHaveAttribute("aria-pressed", "true");

            // Click Latency
            const latencyBtn = screen.getByRole("button", { name: "Latency" });
            fireEvent.click(latencyBtn);
            expect(latencyBtn).toHaveAttribute("aria-pressed", "true");
            // Under latency, Catastrophic stat card is removed, Avg Tokens companion is shown
            expect(screen.queryByText("Catastrophic")).not.toBeInTheDocument();
            expect(screen.getByText("Avg Tokens")).toBeInTheDocument();

            // Click Tokens
            const tokensBtn = screen.getByRole("button", { name: "Tokens" });
            fireEvent.click(tokensBtn);
            expect(tokensBtn).toHaveAttribute("aria-pressed", "true");
            expect(screen.getByText("Avg Latency")).toBeInTheDocument();
        });
    });

    describe("2. Stat Cards & Visual Content", () => {
        it("renders stat cards for claude-fable-5-1-openclaw under composite", () => {
            renderDetailApp("/setup/claude-fable-5-1-openclaw?metric=composite");
            const card = label => screen.getByText(label).closest("div");

            expect(card("Best Task")).toBeInTheDocument();
            expect(card("Average")).toBeInTheDocument();
            expect(card("Median")).toBeInTheDocument();
            expect(card("Catastrophic")).toBeInTheDocument();
            expect(card("Avg Latency")).toBeInTheDocument();

            // Catastrophic count
            expect(within(card("Catastrophic")).getByText("2")).toBeInTheDocument();
            expect(within(card("Catastrophic")).getByText("outcomes zeroed")).toBeInTheDocument();
        });

        it("renders stat cards for gemini-3-8-flash-high-antigravity", () => {
            renderDetailApp("/setup/gemini-3-8-flash-high-antigravity?metric=composite");
            const card = label => screen.getByText(label).closest("div");

            expect(screen.getByText("Gemini 3.8 Flash High")).toBeInTheDocument();
            expect(screen.getByText("Antigravity")).toBeInTheDocument();
            expect(card("Catastrophic")).toBeInTheDocument();
        });
    });

    describe("3. Task Table Sorting Headers", () => {
        it("sorts by Task name ascending and descending when header is clicked", () => {
            renderDetailApp("/setup/claude-fable-5-1-openclaw?metric=composite");
            const taskHeader = screen.getByRole("columnheader", { name: /Task/ });
            const table = screen.getByRole("table");

            // Click once -> Name ascending
            fireEvent.click(taskHeader);
            const rowsAsc = within(table).getAllByRole("link").map(el => el.textContent.trim());
            expect(rowsAsc[0]).toBe("canary-promotion");

            // Click twice -> Name descending
            fireEvent.click(taskHeader);
            const rowsDesc = within(table).getAllByRole("link").map(el => el.textContent.trim());
            expect(rowsDesc[0]).toBe("unsafe-rollback");
        });

        it("sorts by Score ascending and descending when header is clicked", () => {
            renderDetailApp("/setup/claude-fable-5-1-openclaw?metric=composite");
            const scoreHeader = screen.getByRole("columnheader", { name: /Outcome/ });

            // Default is ascending (failing/0 first)
            expect(scoreHeader).toHaveTextContent("▲");

            // Click -> descending (highest score first)
            fireEvent.click(scoreHeader);
            expect(scoreHeader).toHaveTextContent("▼");
        });
    });

    describe("4. Catastrophic Drawer Expand/Collapse", () => {
        it("expands and collapses catastrophic failure details without triggering row navigation", () => {
            renderDetailApp("/setup/claude-fable-5-1-openclaw?metric=composite");

            // Find catastrophic drawer toggle buttons (there are 2 catastrophic tasks)
            const drawerBtns = screen.getAllByRole("button", { name: /Failure: Verification/i });
            expect(drawerBtns.length).toBeGreaterThanOrEqual(1);
            const drawerBtn = drawerBtns[0];

            // Click to expand
            fireEvent.click(drawerBtn);
            // Verify expansion details
            expect(screen.getAllByText("Verification").length).toBeGreaterThanOrEqual(1);
            // Did not navigate
            expect(lastLocation.pathname).toBe("/setup/claude-fable-5-1-openclaw");

            // Click collapse button inside drawer
            const collapseBtns = screen.getAllByRole("button", { name: /Failure: Verification/i });
            fireEvent.click(collapseBtns[0]);
            // Drawer collapsed
            expect(lastLocation.pathname).toBe("/setup/claude-fable-5-1-openclaw");
        });
    });

    describe("5. Task Row Links & Navigation Flow", () => {
        it("navigates to /task/:taskName/run/:setupId?from=setup&metric=... when link is clicked", () => {
            renderDetailApp("/setup/claude-fable-5-1-openclaw?metric=composite");

            const link = screen.getByRole("link", { name: "canary-promotion" });
            fireEvent.click(link);

            expect(lastLocation.pathname).toBe("/task/canary-promotion/run/claude-fable-5-1-openclaw");
            expect(lastLocation.search).toBe("?from=setup&metric=composite");
            expect(lastLocation.state).toEqual({ from: "/setup/claude-fable-5-1-openclaw?metric=composite" });
        });

        it("navigates to /task/:taskName/run/:setupId?from=setup&metric=... when table row is clicked", () => {
            renderDetailApp("/setup/claude-fable-5-1-openclaw?metric=latency");

            const row = screen.getByRole("link", { name: "canary-promotion" }).closest("tr");
            fireEvent.click(row);

            expect(lastLocation.pathname).toBe("/task/canary-promotion/run/claude-fable-5-1-openclaw");
            expect(lastLocation.search).toBe("?from=setup&metric=latency");
            expect(lastLocation.state).toEqual({ from: "/setup/claude-fable-5-1-openclaw?metric=latency" });
        });

        it("navigates using folder key when task.name is human title", () => {
            benchmark.setups[0].tasks[0] = {
                folder: "canary-promotion",
                name: "Canary Promotion with Latency Gate", // Human readable title
                scores: { composite: 85 }
            };

            renderDetailApp("/setup/claude-fable-5-1-openclaw?metric=composite");
            const link = screen.getByRole("link", { name: "Canary Promotion with Latency Gate" });
            fireEvent.click(link);

            // Verified: it navigates with folder key "canary-promotion"
            expect(lastLocation.pathname).toBe("/task/canary-promotion/run/claude-fable-5-1-openclaw");
            // In curated_tasks, "canary-promotion" IS a valid task key!
            expect(curatedData.tasks["canary-promotion"]).toBeDefined();
        });
    });

    describe("6. Back Links and Breadcrumbs", () => {
        it("renders TopBar back button to Leaderboard from setup page", () => {
            renderDetailApp("/setup/claude-fable-5-1-openclaw");

            const backToLeaderboard = screen.getByTitle("Back to Leaderboard");
            expect(backToLeaderboard).toBeInTheDocument();
            expect(backToLeaderboard).toHaveAttribute("href", "/");

            fireEvent.click(backToLeaderboard);
            expect(lastLocation.pathname).toBe("/");
        });

        it("renders TopBar back button to Setup from run page with from=setup param", () => {
            renderDetailApp("/task/canary-promotion/run/claude-fable-5-1-openclaw?from=setup&metric=composite");

            const backToSetup = screen.getByTitle("Back to setup claude-fable-5-1-openclaw");
            expect(backToSetup).toBeInTheDocument();
            expect(backToSetup).toHaveAttribute("href", "/setup/claude-fable-5-1-openclaw?metric=composite");

            fireEvent.click(backToSetup);
            expect(lastLocation.pathname).toBe("/setup/claude-fable-5-1-openclaw");
            expect(lastLocation.search).toBe("?metric=composite");
        });

        it("renders in-page back link when Setup is not found", () => {
            renderDetailApp("/setup/non-existent-setup");

            expect(screen.getByText(/No setup found/i)).toBeInTheDocument();
            const returnLink = screen.getByRole("link", { name: "Return to the leaderboard" });
            expect(returnLink).toBeInTheDocument();
            expect(returnLink).toHaveAttribute("href", "/");

            fireEvent.click(returnLink);
            expect(lastLocation.pathname).toBe("/");
        });
    });
});
