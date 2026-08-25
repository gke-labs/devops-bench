import { describe, it, expect, beforeEach, afterEach, vi } from "vitest";

import { THEME_KEY, applyTheme, getInitialTheme, setTheme } from "./theme.js";

// Point matchMedia at a given OS preference. jsdom doesn't implement it, so
// every test that reaches the fallback has to install one.
function mockPrefersDark(matches) {
    window.matchMedia = vi.fn().mockReturnValue({ matches });
}

// Make every storage access throw, the way Safari does in private browsing and
// any profile with site data blocked by policy.
function breakStorage() {
    const boom = () => { throw new DOMException("denied", "SecurityError"); };
    vi.spyOn(localStorage, "getItem").mockImplementation(boom);
    vi.spyOn(localStorage, "setItem").mockImplementation(boom);
}

beforeEach(() => {
    localStorage.clear();
    document.documentElement.classList.remove("dark");
    mockPrefersDark(false);
});

afterEach(() => {
    vi.restoreAllMocks();
});

describe("getInitialTheme", () => {
    it("prefers the saved choice over the OS preference", () => {
        mockPrefersDark(true);
        localStorage.setItem(THEME_KEY, "light");
        expect(getInitialTheme()).toBe("light");
    });

    it("falls back to the OS preference when nothing is saved", () => {
        mockPrefersDark(true);
        expect(getInitialTheme()).toBe("dark");
        mockPrefersDark(false);
        expect(getInitialTheme()).toBe("light");
    });

    it("ignores a junk value in storage", () => {
        // A stale or hand-edited key must not become a class name.
        localStorage.setItem(THEME_KEY, "solarized");
        mockPrefersDark(true);
        expect(getInitialTheme()).toBe("dark");
    });

    it("falls back to light when matchMedia is unavailable", () => {
        // Old browsers and some embedded webviews have no matchMedia at all.
        window.matchMedia = undefined;
        expect(getInitialTheme()).toBe("light");
    });

    it("survives storage that throws instead of returning null", () => {
        // main.jsx calls this at module scope before the first render, so an
        // escaping DOMException doesn't lose the theme, it blanks the page.
        breakStorage();
        mockPrefersDark(true);
        expect(() => getInitialTheme()).not.toThrow();
        expect(getInitialTheme()).toBe("dark");
    });
});

describe("applyTheme", () => {
    it("toggles the `dark` class Tailwind keys off", () => {
        applyTheme("dark");
        expect(document.documentElement).toHaveClass("dark");
        applyTheme("light");
        expect(document.documentElement).not.toHaveClass("dark");
    });
});

describe("setTheme", () => {
    it("persists and applies the choice", () => {
        setTheme("dark");
        expect(localStorage.getItem(THEME_KEY)).toBe("dark");
        expect(document.documentElement).toHaveClass("dark");
    });

    it("still applies the theme when persistence fails", () => {
        // The preference won't survive a reload, but the click has to work now.
        breakStorage();
        expect(() => setTheme("dark")).not.toThrow();
        expect(document.documentElement).toHaveClass("dark");
    });
});
