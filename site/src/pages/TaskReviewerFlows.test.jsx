import { describe, it, expect, vi } from "vitest";
import { render, screen, fireEvent, within } from "@testing-library/react";
import { MemoryRouter, Routes, Route } from "react-router-dom";
import { Tasks } from "./Tasks.jsx";
import { TaskDetail } from "./TaskDetail.jsx";
import { RunDetail } from "./RunDetail.jsx";

describe("Reviewer Agent 3: Comprehensive Flow Tests", () => {
    // -------------------------------------------------------------
    // Helper to render Tasks catalog
    // -------------------------------------------------------------
    function renderTasksCatalog() {
        return render(
            <MemoryRouter initialEntries={["/tasks"]}>
                <Routes>
                    <Route path="/tasks" element={<Tasks />} />
                    <Route path="/task/:taskName" element={<TaskDetail />} />
                    <Route path="/task/:taskName/run/:setupId" element={<TaskDetail />} />
                </Routes>
            </MemoryRouter>
        );
    }

    // -------------------------------------------------------------
    // Helper to render TaskDetail
    // -------------------------------------------------------------
    function renderTaskDetail(taskName = "canary-promotion", initialPath = `/task/${taskName}`) {
        return render(
            <MemoryRouter initialEntries={[initialPath]}>
                <Routes>
                    <Route path="/task/:taskName" element={<TaskDetail />} />
                    <Route path="/task/:taskName/run/:setupId" element={<TaskDetail />} />
                </Routes>
            </MemoryRouter>
        );
    }

    // -------------------------------------------------------------
    // 1. Tasks Catalog (/tasks)
    // -------------------------------------------------------------
    describe("Tasks Catalog (/tasks)", () => {
        it("renders table headers, badges, and row navigation links", () => {
            renderTasksCatalog();

            // Table headers
            expect(screen.getByText("TASK")).toBeInTheDocument();
            expect(screen.getByText("CATEGORY")).toBeInTheDocument();
            expect(screen.getByText("RUBRIC CHECKS")).toBeInTheDocument();
            expect(screen.getByText("ENVIRONMENT")).toBeInTheDocument();

            // Check badges and rows
            const taskLinks = screen.getAllByRole("link");
            expect(taskLinks.length).toBeGreaterThanOrEqual(20);

            // Row navigation link to single-revision-rollout
            const srrLink = screen.getByText("single-revision-rollout").closest("a");
            expect(srrLink).toHaveAttribute("href", "/task/single-revision-rollout");

            // Category badge in row (e.g. remediate, incident, secure)
            expect(screen.getAllByText("remediate").length).toBeGreaterThan(0);

            // Environment badge (KIND or GCP)
            expect(screen.getAllByText("KIND").length).toBeGreaterThan(0);
        });

        it("filters tasks by search input and clears search with ✕ button", () => {
            renderTasksCatalog();

            const searchInput = screen.getByPlaceholderText(/Filter tasks by name, category/i);
            fireEvent.change(searchInput, { target: { value: "failover" } });

            expect(screen.getByText("multi-region-failover")).toBeInTheDocument();
            expect(screen.queryByText("canary-promotion")).not.toBeInTheDocument();

            // Click clear ✕ button
            const clearBtn = screen.getByRole("button", { name: "✕" });
            fireEvent.click(clearBtn);

            expect(searchInput.value).toBe("");
            expect(screen.getByText("canary-promotion")).toBeInTheDocument();
        });

        it("filters tasks by category dropdown", () => {
            renderTasksCatalog();

            const categorySelect = screen.getByRole("combobox");
            fireEvent.change(categorySelect, { target: { value: "secure" } });

            expect(screen.getByText("secret-rotation")).toBeInTheDocument();
            expect(screen.getByText("cve-remediation")).toBeInTheDocument();
            expect(screen.queryByText("canary-promotion")).not.toBeInTheDocument();
        });

        it("navigates to /task/:taskName on row click", () => {
            renderTasksCatalog();

            const taskRow = screen.getByText("single-revision-rollout").closest("a");
            fireEvent.click(taskRow);

            // Task detail should now be rendered
            expect(screen.getByRole("heading", { level: 1, name: "single-revision-rollout" })).toBeInTheDocument();
        });
    });

    // -------------------------------------------------------------
    // 2. Task Detail (/task/:taskName) across multiple tasks
    // -------------------------------------------------------------
    describe("Task Detail (/task/:taskName) Top Summary and Prompt", () => {
        const testTasks = [
            { name: "single-revision-rollout", objectives: "2", catastrophic: "3", recoverable: "1", harnesses: "9" },
            { name: "canary-promotion", objectives: "2", catastrophic: "2", recoverable: "1", harnesses: "9" },
            { name: "multi-region-failover", objectives: "4", catastrophic: "2", recoverable: "2", harnesses: "9" },
            { name: "incomplete-maintenance", objectives: "6", catastrophic: "3", recoverable: "0", harnesses: "11" },
        ];

        testTasks.forEach(t => {
            it(`renders correct top summary bubbles for ${t.name}`, () => {
                renderTaskDetail(t.name);

                expect(screen.getByRole("heading", { level: 1, name: t.name })).toBeInTheDocument();

                // Objectives bubble
                const objCard = screen.getByText("Objectives").closest("div");
                expect(objCard).toHaveTextContent(t.objectives);
                expect(objCard).toHaveTextContent("checks");

                // Catastrophic bubble
                const catCard = screen.getByText("Catastrophic").closest("div");
                expect(catCard).toHaveTextContent(t.catastrophic);
                expect(catCard).toHaveTextContent("checks");

                // Recoverable bubble
                const recCard = screen.getByText("Recoverable").closest("div");
                expect(recCard).toHaveTextContent(t.recoverable);
                expect(recCard).toHaveTextContent("checks");

                // Cross-Verified bubble
                const crossCard = screen.getByText("Cross-Verified").closest("div");
                expect(crossCard).toHaveTextContent(t.harnesses);
                expect(crossCard).toHaveTextContent("harnesses");
            });
        });

        it("toggles Scenario prompt expand/collapse button", () => {
            renderTaskDetail("canary-promotion");

            const toggleBtn = screen.getByRole("button", { name: "Expand" });
            expect(toggleBtn).toBeInTheDocument();

            fireEvent.click(toggleBtn);
            expect(screen.getByRole("button", { name: "Collapse" })).toBeInTheDocument();

            fireEvent.click(screen.getByRole("button", { name: "Collapse" }));
            expect(screen.getByRole("button", { name: "Expand" })).toBeInTheDocument();
        });
    });

    // -------------------------------------------------------------
    // 3. Matrix Tabs Navigation
    // -------------------------------------------------------------
    describe("Task Detail Tabs Navigation", () => {
        it("navigates through all matrix tabs properly", () => {
            renderTaskDetail("canary-promotion");

            // Default tab is matrix
            expect(screen.getByText(/Results Across All 9 Harnesses/i)).toBeInTheDocument();

            // Tab 2: Objectives
            const objTab = screen.getByRole("tab", { name: /^Objectives/i });
            fireEvent.click(objTab);
            expect(screen.getByRole("heading", { name: /Objectives — Produce Correctness Score/i })).toBeInTheDocument();
            expect(screen.queryByText(/Results Across All 9 Harnesses/i)).not.toBeInTheDocument();

            // Tab 3: Catastrophic Safeguards
            const catTab = screen.getByRole("tab", { name: /^Catastrophic Safeguards/i });
            fireEvent.click(catTab);
            expect(screen.getByRole("heading", { name: /Catastrophic Safeguards — Zero Entire Outcome If Breached/i })).toBeInTheDocument();

            // Tab 4: Recoverable Safeguards
            const recTab = screen.getByRole("tab", { name: /^Recoverable Safeguards/i });
            fireEvent.click(recTab);
            expect(screen.getByRole("heading", { name: /Recoverable Safeguards — Rescaled Safety Drag/i })).toBeInTheDocument();

            // Tab 5: Environment
            const envTab = screen.getByRole("tab", { name: /^Environment/i });
            fireEvent.click(envTab);
            expect(screen.getByRole("heading", { name: /Infrastructure Environment Spec/i })).toBeInTheDocument();

            // Tab 6: All Tables
            const allTab = screen.getByRole("tab", { name: /^All Tables/i });
            fireEvent.click(allTab);
            expect(screen.getByRole("heading", { name: /Results Across All 9 Harnesses/i })).toBeInTheDocument();
            expect(screen.getByRole("heading", { name: /Objectives — Produce Correctness Score/i })).toBeInTheDocument();
            expect(screen.getByRole("heading", { name: /Catastrophic Safeguards — Zero Entire Outcome If Breached/i })).toBeInTheDocument();
            expect(screen.getByRole("heading", { name: /Recoverable Safeguards — Rescaled Safety Drag/i })).toBeInTheDocument();
            expect(screen.getByRole("heading", { name: /Infrastructure Environment Spec/i })).toBeInTheDocument();

            // Switch back to Matrix tab
            const matrixTab = screen.getByRole("tab", { name: /^Results Matrix/i });
            fireEvent.click(matrixTab);
            expect(screen.getByRole("heading", { name: /Results Across All 9 Harnesses/i })).toBeInTheDocument();
            expect(screen.queryByRole("heading", { name: /Infrastructure Environment Spec/i })).not.toBeInTheDocument();
        });

        it("handles zero recoverable safeguards in incomplete-maintenance", () => {
            renderTaskDetail("incomplete-maintenance");

            const recTab = screen.getByRole("tab", { name: /^Recoverable Safeguards/i });
            fireEvent.click(recTab);

            expect(screen.getByText(/No recoverable safeguards declared/i)).toBeInTheDocument();
        });
    });

    // -------------------------------------------------------------
    // 4. Matrix clicking & Master-Detail Run Inspection Panel
    // -------------------------------------------------------------
    describe("Matrix Harness & Cell Clicking to Reveal Inspection Panel", () => {
        it("reveals run details when clicking a harness header button and closes when clicking Close ✕", () => {
            renderTaskDetail("canary-promotion");

            expect(screen.queryByText(/Run details:/i)).not.toBeInTheDocument();

            // Click harness header button
            const harnessBtn = screen.getByRole("button", { name: /ag\/gemini-3\.7-flash-high/i });
            fireEvent.click(harnessBtn);

            // Run inspection panel appears
            expect(screen.getByText(/Run details:/i)).toBeInTheDocument();
            expect(screen.getByText("Latency")).toBeInTheDocument();
            expect(screen.getByText("Tokens")).toBeInTheDocument();
            expect(screen.getByText("Tool Calls")).toBeInTheDocument();
            expect(screen.getByText(/Score Breakdown & Verdict/i)).toBeInTheDocument();

            // Close button
            const closeBtn = screen.getByRole("button", { name: /Close ✕/i });
            fireEvent.click(closeBtn);

            // Panel disappears, matrix remains
            expect(screen.queryByText(/Run details:/i)).not.toBeInTheDocument();
            expect(screen.getByText(/Results Across All 9 Harnesses/i)).toBeInTheDocument();
        });

        it("reveals run details when clicking a check result cell button", () => {
            renderTaskDetail("canary-promotion");

            // Find check result buttons in the matrix (PASS, FAIL, etc.)
            const cellBtns = screen.getAllByRole("button", { name: /PASS|FAIL/i });
            expect(cellBtns.length).toBeGreaterThan(0);

            // Click first result button
            fireEvent.click(cellBtns[0]);

            // Panel appears
            expect(screen.getByText(/Run details:/i)).toBeInTheDocument();
        });

        it("reveals run details when clicking an outcome score button", () => {
            renderTaskDetail("canary-promotion");

            // Click outcome score button (e.g. "66.7%")
            const scoreBtns = screen.getAllByRole("button", { name: /%/i });
            expect(scoreBtns.length).toBeGreaterThan(0);

            fireEvent.click(scoreBtns[0]);
            expect(screen.getByText(/Run details:/i)).toBeInTheDocument();
        });

        it("toggles run inspection off when re-clicking the active harness header button", () => {
            renderTaskDetail("canary-promotion");

            const harnessBtn = screen.getByRole("button", { name: /ag\/gemini-3\.7-flash-high/i });
            fireEvent.click(harnessBtn);
            expect(screen.getByText(/Run details:/i)).toBeInTheDocument();

            // Re-click the same harness button
            fireEvent.click(harnessBtn);
            expect(screen.queryByText(/Run details:/i)).not.toBeInTheDocument();
        });
    });

    // -------------------------------------------------------------
    // 5. In Run Inspection Panel: Dropdown, Check Tabs, Badges, Hints
    // -------------------------------------------------------------
    describe("Run Inspection Panel Interactive Elements", () => {
        it("switches runs using the <select> dropdown", () => {
            renderTaskDetail("canary-promotion");

            // Open panel
            const harnessBtn = screen.getByRole("button", { name: /ag\/gemini-3\.7-flash-high/i });
            fireEvent.click(harnessBtn);

            const select = screen.getByRole("combobox", { name: /Select harness run to inspect/i });
            expect(select).toBeInTheDocument();
            expect(select.value).toBe("antigravity_gemini-3.7-flash-high");

            // Change to openclaw_gpt-5.6-sol
            fireEvent.change(select, { target: { value: "openclaw_gpt-5.6-sol" } });
            expect(select.value).toBe("openclaw_gpt-5.6-sol");
        });

        it("displays correct score breakdown and formula bubbles", () => {
            renderTaskDetail("canary-promotion");

            const harnessBtn = screen.getByRole("button", { name: /ag\/gemini-3\.7-flash-high/i });
            fireEvent.click(harnessBtn);

            expect(screen.getByText("Correctness (c)")).toBeInTheDocument();
            expect(screen.getByText("Rescaled Safety (rec_v)")).toBeInTheDocument();
            expect(screen.getByText("Catastrophic Gate (cat_v)")).toBeInTheDocument();
            expect(screen.getByText("Outcome")).toBeInTheDocument();
            expect(screen.getByText(/cat_v ×/i)).toBeInTheDocument();
        });

        it("displays catastrophic breach banner on catastrophic failures", () => {
            renderTaskDetail("single-revision-rollout");

            // Open run with catastrophic failure
            const harnessBtn = screen.getByRole("button", { name: /ag\/gemini-3\.7-flash-high/i });
            fireEvent.click(harnessBtn);

            // Banner appears
            expect(screen.getByText(/Catastrophic breach zeroes run/i)).toBeInTheDocument();
            expect(screen.getByText(/Catastrophic safeguard breached: outcome score is zeroed/i)).toBeInTheDocument();
        });

        it("switches run check tabs inside inspection panel", () => {
            renderTaskDetail("canary-promotion");

            const harnessBtn = screen.getByRole("button", { name: /ag\/gemini-3\.7-flash-high/i });
            fireEvent.click(harnessBtn);

            const panel = document.getElementById("run-inspection-panel");
            expect(panel).toBeInTheDocument();

            // Find tabs within panel
            const allChecksTab = within(panel).getByRole("tab", { name: /^All Checks/i });
            const objTab = within(panel).getByRole("tab", { name: /^Objectives/i });
            const catTab = within(panel).getByRole("tab", { name: /^Catastrophic Safeguards/i });
            const recTab = within(panel).getByRole("tab", { name: /^Recoverable Safeguards/i });

            expect(allChecksTab).toBeInTheDocument();
            expect(objTab).toBeInTheDocument();
            expect(catTab).toBeInTheDocument();
            expect(recTab).toBeInTheDocument();

            // Click Objectives tab
            fireEvent.click(objTab);
            expect(within(panel).getByRole("heading", { name: /^Objectives$/i })).toBeInTheDocument();
            expect(within(panel).queryByRole("heading", { name: /^Catastrophic Safeguards$/i })).not.toBeInTheDocument();

            // Click Catastrophic tab
            fireEvent.click(catTab);
            expect(within(panel).getByRole("heading", { name: /^Catastrophic Safeguards$/i })).toBeInTheDocument();

            // Click Recoverable tab
            fireEvent.click(recTab);
            expect(within(panel).getByRole("heading", { name: /^Recoverable Safeguards$/i })).toBeInTheDocument();

            // Click All Checks tab
            fireEvent.click(allChecksTab);
            expect(within(panel).getByRole("heading", { name: /^Objectives$/i })).toBeInTheDocument();
            expect(within(panel).getByRole("heading", { name: /^Catastrophic Safeguards$/i })).toBeInTheDocument();
            expect(within(panel).getByRole("heading", { name: /^Recoverable Safeguards$/i })).toBeInTheDocument();
        });

        it("displays result badges and observed text with failure hints", () => {
            renderTaskDetail("single-revision-rollout");

            // Open run inspection
            const harnessBtn = screen.getByRole("button", { name: /ag\/gemini-3\.7-flash-high/i });
            fireEvent.click(harnessBtn);

            const panel = document.getElementById("run-inspection-panel");

            // Result badges
            const passBadges = within(panel).getAllByText("PASS");
            const failBadges = within(panel).getAllByText("FAIL");
            expect(passBadges.length).toBeGreaterThan(0);
            expect(failBadges.length).toBeGreaterThan(0);

            // Failure hint
            expect(within(panel).getAllByText(/Hint:/i).length).toBeGreaterThan(0);
        });

        it("toggles CheckMeta metadata pill details with +more / −less button", () => {
            renderTaskDetail("canary-promotion");

            const harnessBtn = screen.getByRole("button", { name: /ag\/gemini-3\.7-flash-high/i });
            fireEvent.click(harnessBtn);

            const panel = document.getElementById("run-inspection-panel");

            // CheckMeta buttons
            const expandBtns = within(panel).getAllByRole("button", { name: /Show/i });
            expect(expandBtns.length).toBeGreaterThan(0);

            // Click first expand button
            fireEvent.click(expandBtns[0]);
            expect(within(panel).getAllByRole("button", { name: /Collapse details/i }).length).toBeGreaterThan(0);

            // Click collapse button
            const collapseBtn = within(panel).getByRole("button", { name: /Collapse details/i });
            fireEvent.click(collapseBtn);
            expect(collapseBtn).toHaveAttribute("aria-label", expect.stringMatching(/Show/i));
        });
    });

    // -------------------------------------------------------------
    // 6. Direct Route Loading (/task/:taskName/run/:setupId)
    // -------------------------------------------------------------
    describe("Direct Route Loading (/task/:taskName/run/:setupId)", () => {
        it("loads directly with inspection panel open and closes with Close ✕", () => {
            renderTaskDetail("canary-promotion", "/task/canary-promotion/run/antigravity_gemini-3.7-flash-high");

            expect(screen.getByText(/Run details:/i)).toBeInTheDocument();
            expect(screen.getByText("Latency")).toBeInTheDocument();

            // Click close
            const closeBtn = screen.getByRole("button", { name: /Close ✕/i });
            fireEvent.click(closeBtn);

            expect(screen.queryByText(/Run details:/i)).not.toBeInTheDocument();
        });

        it("loads directly when setupId format is used instead of arm format", () => {
            renderTaskDetail("single-revision-rollout", "/task/single-revision-rollout/run/gemini-3-7-flash-high-antigravity");

            expect(screen.getByText(/Run details:/i)).toBeInTheDocument();
            expect(screen.getByText("Latency")).toBeInTheDocument();
        });
    });
});

