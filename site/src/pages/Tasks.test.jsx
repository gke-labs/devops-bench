import { describe, it, expect } from "vitest";
import { render, screen, fireEvent } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { Tasks } from "./Tasks.jsx";

describe("Tasks Page", () => {
    it("renders title, description and task rows in table", () => {
        render(
            <MemoryRouter>
                <Tasks />
            </MemoryRouter>
        );

        expect(screen.getByText("DevOps Bench Tasks")).toBeInTheDocument();
        expect(screen.getByText(/20 benchmark tasks/i)).toBeInTheDocument();
        expect(screen.getByText("cve-remediation")).toBeInTheDocument();
        expect(screen.getByText("TASK")).toBeInTheDocument();
    });

    it("filters tasks by search input", () => {
        render(
            <MemoryRouter>
                <Tasks />
            </MemoryRouter>
        );

        const searchInput = screen.getByPlaceholderText(/Filter tasks by name, category/i);
        fireEvent.change(searchInput, { target: { value: "secret-rotation" } });

        expect(screen.getByText("secret-rotation")).toBeInTheDocument();
        expect(screen.queryByText("cve-remediation")).not.toBeInTheDocument();
    });

    it("filters tasks by category select", () => {
        render(
            <MemoryRouter>
                <Tasks />
            </MemoryRouter>
        );

        const select = screen.getByRole("combobox");
        fireEvent.change(select, { target: { value: "secure" } });

        expect(screen.getByText("cve-remediation")).toBeInTheDocument();
        expect(screen.getByText("secret-rotation")).toBeInTheDocument();
        expect(screen.queryByText("optimize-scale")).not.toBeInTheDocument();
    });
});
