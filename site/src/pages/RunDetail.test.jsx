import { describe, it, expect } from "vitest";
import { render, screen } from "@testing-library/react";
import { MemoryRouter, Routes, Route } from "react-router-dom";
import { RunDetail } from "./RunDetail.jsx";

describe("RunDetail", () => {
    function renderRun(taskName = "canary-promotion", setupId = "antigravity_gemini-3.7-flash-high") {
        return render(
            <MemoryRouter initialEntries={[`/task/${taskName}/run/${setupId}`]}>
                <Routes>
                    <Route path="/task/:taskName/run/:setupId" element={<RunDetail />} />
                </Routes>
            </MemoryRouter>
        );
    }

    it("renders run header with task name and arm", () => {
        renderRun("canary-promotion", "antigravity_gemini-3.7-flash-high");
        expect(screen.getByRole("heading", { level: 1, name: "canary-promotion" })).toBeInTheDocument();
        expect(screen.getByText(/antigravity · gemini-3.7-flash-high/i)).toBeInTheDocument();
        expect(screen.queryByText(/Arm:/i)).not.toBeInTheDocument();
    });

    it("renders telemetry stat cards (latency, tokens, tool calls)", () => {
        renderRun("canary-promotion", "antigravity_gemini-3.7-flash-high");
        expect(screen.getByText("Latency")).toBeInTheDocument();
        expect(screen.getByText("Tokens")).toBeInTheDocument();
        expect(screen.getByText("Tool Calls")).toBeInTheDocument();
    });

    it("renders score breakdown components without raw math equation", () => {
        renderRun("canary-promotion", "antigravity_gemini-3.7-flash-high");
        expect(screen.getByText(/Score Breakdown & Verdict/i)).toBeInTheDocument();
        expect(screen.queryByText(/outcome_score = cat_v \* sqrt\(c \* rec_v\)/i)).not.toBeInTheDocument();
        expect(screen.getByText(/Correctness \(c\):/i)).toBeInTheDocument();
        expect(screen.getByText(/Rescaled Safety \(rec_v\):/i)).toBeInTheDocument();
    });

    it("renders check tables with result badges and observed failure/pass text", () => {
        renderRun("canary-promotion", "antigravity_gemini-3.7-flash-high");
        expect(screen.getByText("Objectives")).toBeInTheDocument();
        expect(screen.getAllByText("Result").length).toBeGreaterThanOrEqual(1);
        expect(screen.getAllByText("Observed").length).toBeGreaterThanOrEqual(1);
    });

    it("renders kubeagents run with both canonical and -gitops task names", () => {
        const { unmount } = renderRun("unsafe-rollback-gitops", "gemini-3-7-flash-kubeagents");
        expect(screen.getByRole("heading", { level: 1, name: "unsafe-rollback" })).toBeInTheDocument();
        expect(screen.getByText(/kubeagents · gemini-3.7-flash/i)).toBeInTheDocument();
        unmount();

        renderRun("unsafe-rollback", "gemini-3-7-flash-kubeagents");
        expect(screen.getByRole("heading", { level: 1, name: "unsafe-rollback" })).toBeInTheDocument();
        expect(screen.getByText(/kubeagents · gemini-3.7-flash/i)).toBeInTheDocument();
    });

    it("renders not found state for unknown run", () => {
        renderRun("canary-promotion", "unknown-harness");
        expect(screen.getByText(/Run "unknown-harness" for task "canary-promotion" was not found/i)).toBeInTheDocument();
    });

    it("displays 66.7% outcome score for claude-opus-5-kubeagents on incomplete-maintenance matching setup page", () => {
        renderRun("incomplete-maintenance", "claude-opus-5-kubeagents");
        expect(screen.getByText("66.7%")).toBeInTheDocument();
    });

    it("surfaces IntegrityCatastrophic safeguard failure and checklist objectives on multi-region-failover", () => {
        renderRun("multi-region-failover", "antigravity_gemini-3.8-flash-high");
        expect(screen.getByText("0%")).toBeInTheDocument();
        expect(screen.getByText("Benchmark Integrity (No Rubric / Harness Access)")).toBeInTheDocument();
        expect(screen.getAllByText(/Accessed benchmark material: harness-environment, harness-repo, task-definition/i).length).toBeGreaterThanOrEqual(1);
        expect(screen.getByText("Objectives (4)")).toBeInTheDocument();
        expect(screen.getByText("Catastrophic Safeguards (2)")).toBeInTheDocument();
    });
});
