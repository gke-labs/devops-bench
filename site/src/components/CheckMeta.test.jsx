import { describe, it, expect } from "vitest";
import { render, screen, fireEvent } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { CheckMeta } from "./CheckMeta.jsx";

describe("CheckMeta component", () => {
    it("renders role by default and extra metadata collapsed with toggle button", () => {
        render(
            <MemoryRouter>
                <CheckMeta
                    id="pods-envfrom-set@vault.wl"
                    role="objective"
                    group="Canary promoted"
                    mode="converge"
                    weight={2.0}
                />
            </MemoryRouter>
        );

        // Role is always visible
        expect(screen.getByText("role:")).toBeInTheDocument();
        expect(screen.getByText("objective")).toBeInTheDocument();

        // Extra metadata items are initially collapsed
        expect(screen.queryByText("id:")).not.toBeInTheDocument();
        expect(screen.queryByText("pods-envfrom-set@vault.wl")).not.toBeInTheDocument();
        expect(screen.queryByText("group:")).not.toBeInTheDocument();

        // Toggle button indicates 4 extra items
        const toggleBtn = screen.getByRole("button", { name: /Show/i });
        expect(toggleBtn).toHaveTextContent("+4 more");

        // Clicking expands details
        fireEvent.click(toggleBtn);
        expect(screen.getByText("id:")).toBeInTheDocument();
        expect(screen.getByText("pods-envfrom-set@vault.wl")).toBeInTheDocument();
        expect(screen.getByText("mode:")).toBeInTheDocument();
        expect(screen.getByText("converge")).toBeInTheDocument();
        expect(screen.getByText("weight:")).toBeInTheDocument();
        expect(screen.getByText("2 pts")).toBeInTheDocument();
        expect(screen.getByText("group:")).toBeInTheDocument();
        expect(screen.getByText("Canary promoted")).toBeInTheDocument();
        expect(screen.getByRole("button")).toHaveTextContent("− less");

        // Clicking again collapses details
        fireEvent.click(screen.getByRole("button", { name: /Collapse/i }));
        expect(screen.queryByText("id:")).not.toBeInTheDocument();
        expect(screen.getByRole("button")).toHaveTextContent("+4 more");
    });

    it("renders only role without button when no extra metadata exists", () => {
        render(
            <MemoryRouter>
                <CheckMeta role="objective" />
            </MemoryRouter>
        );

        expect(screen.getByText("role:")).toBeInTheDocument();
        expect(screen.getByText("objective")).toBeInTheDocument();
        expect(screen.queryByRole("button")).not.toBeInTheDocument();
    });

    it("supports defaultExpanded=true", () => {
        render(
            <MemoryRouter>
                <CheckMeta
                    id="check-1"
                    role="safeguard"
                    mode="hold"
                    defaultExpanded={true}
                />
            </MemoryRouter>
        );

        expect(screen.getByText("role:")).toBeInTheDocument();
        expect(screen.getByText("id:")).toBeInTheDocument();
        expect(screen.getByText("check-1")).toBeInTheDocument();
        expect(screen.getByText("mode:")).toBeInTheDocument();
        expect(screen.getByRole("button")).toHaveTextContent("− less");
    });

    it("renders nothing when no props are passed", () => {
        const { container } = render(<CheckMeta />);
        expect(container.firstChild).toBeNull();
    });
});
