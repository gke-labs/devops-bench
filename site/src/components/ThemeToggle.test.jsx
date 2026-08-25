import { describe, it, expect, beforeEach, afterEach, vi } from "vitest";
import { render, screen, fireEvent, act } from "@testing-library/react";

import { ThemeToggle } from "./ThemeToggle.jsx";
import { THEME_KEY } from "../lib/theme.js";

const root = () => document.documentElement;
const button = () => screen.getByRole("button");

// Dispatch the cross-tab event the browser fires in OTHER tabs when this key
// changes. `key: null` is what a storage.clear() looks like to a listener.
function fireStorage({ key = THEME_KEY, newValue }) {
    act(() => {
        window.dispatchEvent(new StorageEvent("storage", { key, newValue }));
    });
}

beforeEach(() => {
    localStorage.clear();
    root().classList.remove("dark");
    window.matchMedia = vi.fn().mockReturnValue({ matches: false });
});

afterEach(() => {
    vi.restoreAllMocks();
});

describe("ThemeToggle", () => {
    it("labels itself by the theme it will switch TO", () => {
        render(<ThemeToggle />);
        expect(button()).toHaveAccessibleName("Switch to dark mode");
        fireEvent.click(button());
        expect(button()).toHaveAccessibleName("Switch to light mode");
    });

    it("persists and applies the choice on click", () => {
        render(<ThemeToggle />);
        fireEvent.click(button());
        expect(root()).toHaveClass("dark");
        expect(localStorage.getItem(THEME_KEY)).toBe("dark");

        fireEvent.click(button());
        expect(root()).not.toHaveClass("dark");
        expect(localStorage.getItem(THEME_KEY)).toBe("light");
    });

    it("starts from the persisted choice", () => {
        localStorage.setItem(THEME_KEY, "dark");
        render(<ThemeToggle />);
        expect(button()).toHaveAccessibleName("Switch to light mode");
    });

    it("follows a change made in another tab", () => {
        render(<ThemeToggle />);
        fireStorage({ newValue: "dark" });
        expect(root()).toHaveClass("dark");
        expect(button()).toHaveAccessibleName("Switch to light mode");
    });

    it("ignores storage events for other keys", () => {
        render(<ThemeToggle />);
        fireStorage({ key: "some-other-key", newValue: "dark" });
        expect(root()).not.toHaveClass("dark");
    });

    it("ignores a junk value written by another tab", () => {
        render(<ThemeToggle />);
        fireStorage({ newValue: "solarized" });
        expect(root()).not.toHaveClass("dark");
        expect(button()).toHaveAccessibleName("Switch to dark mode");
    });

    it("falls back to the OS preference when another tab clears storage", () => {
        // key === null means the whole store was cleared, so there is no saved
        // choice left to read — resolution has to start over.
        window.matchMedia = vi.fn().mockReturnValue({ matches: true });
        render(<ThemeToggle />);
        expect(root()).not.toHaveClass("dark");

        fireStorage({ key: null, newValue: null });
        expect(root()).toHaveClass("dark");
    });

    it("stops listening after unmount", () => {
        const { unmount } = render(<ThemeToggle />);
        unmount();
        fireStorage({ newValue: "dark" });
        expect(root()).not.toHaveClass("dark");
    });
});
