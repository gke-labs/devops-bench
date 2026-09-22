import { describe, it, expect, vi } from "vitest";
import { render, screen, fireEvent, act } from "@testing-library/react";
import { MemoryRouter, Routes, Route, useNavigate } from "react-router-dom";
import { TaskDetail } from "./TaskDetail.jsx";
import { ScrollToTop } from "../App.jsx";

describe("TaskDetail", () => {
    function renderTask(taskName = "canary-promotion", initialPath = `/task/${taskName}`) {
        return render(
            <MemoryRouter initialEntries={[initialPath]}>
                <Routes>
                    <Route path="/task/:taskName" element={<TaskDetail />} />
                    <Route path="/task/:taskName/run/:setupId" element={<TaskDetail />} />
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

    it("preserves prompt and reveals run details below matrix when clicking a harness, and closes inspection", () => {
        renderTask("canary-promotion");
        expect(screen.getByText(/Instruction/i)).toBeInTheDocument();
        expect(screen.getByText(/Results Across All 9 Harnesses/i)).toBeInTheDocument();
        expect(screen.queryByText(/Run details:/i)).not.toBeInTheDocument();

        // Click a harness header button to inspect run
        const inspectBtn = screen.getByRole("button", { name: /ag\/gemini-3\.7-flash-high/i });
        fireEvent.click(inspectBtn);

        // Run details should now be visible below matrix with prompt and matrix still present
        expect(screen.getByText(/Run details:/i)).toBeInTheDocument();
        expect(screen.getByText("Latency")).toBeInTheDocument();
        expect(screen.getByText("Tokens")).toBeInTheDocument();
        expect(screen.getByText("Tool Calls")).toBeInTheDocument();
        expect(screen.getByText(/Score Breakdown & Verdict/i)).toBeInTheDocument();
        expect(screen.getByText(/Instruction/i)).toBeInTheDocument();
        expect(screen.getByText(/Results Across All 9 Harnesses/i)).toBeInTheDocument();

        // Click close
        const closeBtn = screen.getByRole("button", { name: /Close/i });
        fireEvent.click(closeBtn);

        // Inspection panel is closed, matrix remains
        expect(screen.queryByText(/Run details:/i)).not.toBeInTheDocument();
        expect(screen.getByText(/Results Across All 9 Harnesses/i)).toBeInTheDocument();
    });

    it("renders not found state for unknown task", () => {
        renderTask("non-existent-task");
        expect(screen.getByText(/Task "non-existent-task" was not found/i)).toBeInTheDocument();
    });

    it("resolves legacy task folder codes (e.g. b-0032) to canonical task", () => {
        renderTask("b-0032");
        expect(screen.getByRole("heading", { level: 1 })).toHaveTextContent("single-revision-rollout-unguarded");
    });

    it("renders run details directly when accessed via legacy task folder and setupId", () => {
        renderTask("b-0032", "/task/b-0032/run/gemini-3-8-flash-high-antigravity?from=setup&metric=composite");
        expect(screen.getByRole("heading", { level: 1 })).toHaveTextContent("single-revision-rollout-unguarded");
        expect(screen.getByText(/Run details:/i)).toBeInTheDocument();
        expect(screen.getByText("Latency")).toBeInTheDocument();
        expect(screen.getByText("Tokens")).toBeInTheDocument();
        expect(screen.getByText("Tool Calls")).toBeInTheDocument();
        expect(screen.getByText(/Score Breakdown & Verdict/i)).toBeInTheDocument();
    });

    it("scrolls window to top when navigating to a task page without run parameter", () => {
        const scrollToSpy = vi.spyOn(window, "scrollTo").mockImplementation(() => {});
        renderTask("single-revision-rollout-unguarded");
        expect(scrollToSpy).toHaveBeenCalledWith(0, 0);
        scrollToSpy.mockRestore();
    });
});

describe("ScrollToTop component", () => {
    it("scrolls window to top on base route change, but not on run sub-route within the same task", () => {
        let navigateFn;
        function NavTester() {
            navigateFn = useNavigate();
            return <ScrollToTop />;
        }

        const scrollToSpy = vi.spyOn(window, "scrollTo").mockImplementation(() => {});
        render(
            <MemoryRouter initialEntries={["/tasks"]}>
                <NavTester />
            </MemoryRouter>
        );
        expect(scrollToSpy).toHaveBeenCalledWith(0, 0);
        scrollToSpy.mockClear();

        // Navigating to task detail changes baseRoute, so it should scroll to top
        act(() => {
            navigateFn("/task/single-revision-rollout-unguarded");
        });
        expect(scrollToSpy).toHaveBeenCalledWith(0, 0);
        scrollToSpy.mockClear();

        // Inspecting a run on the same task does not change baseRoute, so it should NOT reset to top
        act(() => {
            navigateFn("/task/single-revision-rollout-unguarded/run/gemini-3-8-flash-high-antigravity");
        });
        expect(scrollToSpy).not.toHaveBeenCalled();

        scrollToSpy.mockRestore();
    });
});
