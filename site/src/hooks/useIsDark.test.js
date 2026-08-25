import { describe, it, expect, beforeEach } from "vitest";
import { renderHook, act, waitFor } from "@testing-library/react";

import { useIsDark } from "./useIsDark.js";

const root = () => document.documentElement;

beforeEach(() => {
    root().classList.remove("dark");
});

describe("useIsDark", () => {
    it("reads the class already on <html> at mount", () => {
        root().classList.add("dark");
        expect(renderHook(() => useIsDark()).result.current).toBe(true);
    });

    it("re-renders when the class flips, in both directions", async () => {
        // This is the whole point of the hook: Chart.js paints to a canvas and
        // can't use Tailwind's `dark:` variants, so it needs a value that
        // changes rather than one read once at mount.
        const { result } = renderHook(() => useIsDark());
        expect(result.current).toBe(false);

        act(() => { root().classList.add("dark"); });
        await waitFor(() => expect(result.current).toBe(true));

        act(() => { root().classList.remove("dark"); });
        await waitFor(() => expect(result.current).toBe(false));
    });

    it("ignores unrelated attribute changes on <html>", async () => {
        const { result } = renderHook(() => useIsDark());
        act(() => { root().setAttribute("lang", "fr"); });
        await waitFor(() => expect(result.current).toBe(false));
        root().removeAttribute("lang");
    });

    it("stops observing after unmount", async () => {
        const { result, unmount } = renderHook(() => useIsDark());
        unmount();
        // A leaked MutationObserver would call setState on an unmounted hook.
        act(() => { root().classList.add("dark"); });
        await waitFor(() => expect(result.current).toBe(false));
    });
});
