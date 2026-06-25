import { describe, it, expect, vi, beforeEach, afterEach } from "vitest";
import { renderHook, waitFor } from "@testing-library/react";

// Avoid initializing the real Firebase client; stub the db handle, the loader,
// and terminate() so we can drive the hook's lifecycle directly.
vi.mock("../lib/firebase.js", () => ({ db: { __db: true } }));
vi.mock("../lib/data.js", () => ({ loadBenchmarkData: vi.fn() }));
vi.mock("firebase/firestore", () => ({ terminate: vi.fn(() => Promise.resolve()) }));

import { loadBenchmarkData } from "../lib/data.js";
import { terminate } from "firebase/firestore";
import { useBenchmarkData } from "./useBenchmarkData.js";

beforeEach(() => {
    vi.clearAllMocks();
});
afterEach(() => {
    vi.unstubAllEnvs();
});

describe("useBenchmarkData", () => {
    it("starts in a loading state", () => {
        loadBenchmarkData.mockReturnValue(new Promise(() => {})); // never resolves
        const { result } = renderHook(() => useBenchmarkData());
        expect(result.current.loading).toBe(true);
        expect(result.current.error).toBeNull();
        expect(result.current.setups).toEqual([]);
    });

    it("loads the data once and exposes it", async () => {
        loadBenchmarkData.mockResolvedValue({
            models: { m: 1 }, harnesses: { h: 1 }, setups: [{ id: "s" }]
        });
        const { result } = renderHook(() => useBenchmarkData());
        await waitFor(() => expect(result.current.loading).toBe(false));
        expect(result.current.models).toEqual({ m: 1 });
        expect(result.current.harnesses).toEqual({ h: 1 });
        expect(result.current.setups).toEqual([{ id: "s" }]);
        expect(result.current.error).toBeNull();
        expect(loadBenchmarkData).toHaveBeenCalledTimes(1);
    });

    it("captures a load error without throwing", async () => {
        const err = new Error("boom");
        loadBenchmarkData.mockRejectedValue(err);
        const spy = vi.spyOn(console, "error").mockImplementation(() => {});
        const { result } = renderHook(() => useBenchmarkData());
        await waitFor(() => expect(result.current.loading).toBe(false));
        expect(result.current.error).toBe(err);
        expect(result.current.setups).toEqual([]);
        expect(spy).toHaveBeenCalled();
        spy.mockRestore();
    });

    it("does NOT terminate the client in dev (non-PROD)", async () => {
        loadBenchmarkData.mockResolvedValue({ models: {}, harnesses: {}, setups: [] });
        const { result } = renderHook(() => useBenchmarkData());
        await waitFor(() => expect(result.current.loading).toBe(false));
        expect(terminate).not.toHaveBeenCalled();
    });

    it("terminates the client after the one-shot read in PROD", async () => {
        vi.stubEnv("PROD", true);
        loadBenchmarkData.mockResolvedValue({ models: {}, harnesses: {}, setups: [] });
        const { result } = renderHook(() => useBenchmarkData());
        await waitFor(() => expect(result.current.loading).toBe(false));
        await waitFor(() => expect(terminate).toHaveBeenCalledTimes(1));
    });
});
