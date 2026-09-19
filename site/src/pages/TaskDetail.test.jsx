import { describe, it, expect } from "vitest";
import { render, screen, fireEvent } from "@testing-library/react";
import { MemoryRouter, Routes, Route } from "react-router-dom";
import { TaskDetail } from "./TaskDetail.jsx";

describe("TaskDetail", () => {
    function renderTask(taskName = "canary-promotion") {
        return render(
            <MemoryRouter initialEntries={[`/task/${taskName}`]}>
                <Routes>
                    <Route path="/task/:taskName" element={<TaskDetail />} />
                </Routes>
            </MemoryRouter>
        );
    }

    it("renders task name as heading", () => {
        renderTask("canary-promotion");
        expect(screen.getByRole("heading", { level: 1 })).toHaveTextContent("canary-promotion");
    });

    it("renders instruction scenario block and toggles expand", () => {
        renderTask("canary-promotion");
        expect(screen.getByText(/Instruction/i)).toBeInTheDocument();
        const toggleBtn = screen.getByRole("button", { name: "Expand" });
        expect(toggleBtn).toBeInTheDocument();
        fireEvent.click(toggleBtn);
        expect(screen.getByRole("button", { name: "Collapse" })).toBeInTheDocument();
    });

    it("renders the 9-harness results matrix tab by default", () => {
        renderTask("canary-promotion");
        expect(screen.getByText(/Results Across All 9 Harnesses/i)).toBeInTheDocument();
        expect(screen.getByText("Outcome Score")).toBeInTheDocument();
    });

    it("switches tabs to objectives, catastrophic, recoverable, and all tables", () => {
        renderTask("canary-promotion");

        // Click Objectives tab
        fireEvent.click(screen.getByRole("tab", { name: /Objectives/i }));
        expect(screen.getByRole("heading", { name: /Objectives/i })).toBeInTheDocument();

        // Click All Tables tab
        fireEvent.click(screen.getByRole("tab", { name: /All Tables/i }));
        expect(screen.getByRole("heading", { name: /Results Across All 9 Harnesses/i })).toBeInTheDocument();
        expect(screen.getByRole("heading", { name: /Objectives/i })).toBeInTheDocument();
        expect(screen.getByRole("heading", { name: /Catastrophic Safeguards/i })).toBeInTheDocument();
        expect(screen.getByRole("heading", { name: /Recoverable Safeguards/i })).toBeInTheDocument();
    });

    it("renders outcome scores in results matrix without line-through and shows catastrophic in red", () => {
        const { container } = renderTask("single-revision-rollout");
        expect(screen.getByText("Outcome Score")).toBeInTheDocument();
        // Ensure no line-through strikethrough dashes in the outcome score cells
        const struckElements = container.querySelectorAll(".line-through");
        expect(struckElements.length).toBe(0);

        // Ensure catastrophic failures are highlighted in red without dash
        const redScores = container.querySelectorAll(".text-rose-600");
        expect(redScores.length).toBeGreaterThan(0);
        expect(redScores[0]).toHaveTextContent("0%");
    });

    it("renders not found state for unknown task", () => {
        renderTask("non-existent-task");
        expect(screen.getByText(/Task "non-existent-task" was not found/i)).toBeInTheDocument();
    });
});
