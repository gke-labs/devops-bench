import { describe, it, expect, beforeEach, vi } from "vitest";

// Mock the modular Firestore SDK so we can drive loadBenchmarkData without a real
// database. collection/query/orderBy return tagged objects so we can assert how
// they were composed; getDocs is a spy we resolve per-call.
vi.mock("firebase/firestore", () => ({
    collection: vi.fn((db, name) => ({ __collection: name })),
    query: vi.fn((...args) => ({ __query: args })),
    orderBy: vi.fn((field) => ({ __orderBy: field })),
    getDocs: vi.fn()
}));

import * as firestore from "firebase/firestore";
import { loadBenchmarkData } from "./data.js";

// A snapshot whose forEach yields {id, data()} docs (models/harnesses style).
function forEachSnap(entries) {
    return { forEach: cb => entries.forEach(([id, data]) => cb({ id, data: () => data })) };
}
// A snapshot exposing .docs of {data()} (setups style).
function docsSnap(objects) {
    return { docs: objects.map(o => ({ data: () => o })) };
}

const fakeDb = { __db: true };

beforeEach(() => {
    vi.clearAllMocks();
});

describe("loadBenchmarkData", () => {
    it("shapes models/harnesses as keyed objects and setups as an array", async () => {
        firestore.getDocs
            .mockResolvedValueOnce(forEachSnap([
                ["alpha-pro", { name: "Alpha Pro" }],
                ["gamma-coder", { name: "Gamma Coder" }]
            ]))
            .mockResolvedValueOnce(forEachSnap([
                ["gemini-cli", { name: "Gemini CLI" }]
            ]))
            .mockResolvedValueOnce(docsSnap([
                { id: "s1", order: 0, model: "alpha-pro", harness: "gemini-cli" },
                { id: "s2", order: 1, model: "gamma-coder", harness: "gemini-cli" }
            ]));

        const { models, harnesses, setups } = await loadBenchmarkData(fakeDb);

        expect(models).toEqual({
            "alpha-pro": { name: "Alpha Pro" },
            "gamma-coder": { name: "Gamma Coder" }
        });
        expect(harnesses).toEqual({ "gemini-cli": { name: "Gemini CLI" } });
        expect(setups).toEqual([
            { id: "s1", order: 0, model: "alpha-pro", harness: "gemini-cli" },
            { id: "s2", order: 1, model: "gamma-coder", harness: "gemini-cli" }
        ]);
    });

    it("drops setups whose model/harness ref doesn't resolve, and warns", async () => {
        const warn = vi.spyOn(console, "warn").mockImplementation(() => {});
        firestore.getDocs
            .mockResolvedValueOnce(forEachSnap([["alpha-pro", { name: "Alpha Pro" }]]))
            .mockResolvedValueOnce(forEachSnap([["gemini-cli", { name: "Gemini CLI" }]]))
            .mockResolvedValueOnce(docsSnap([
                { id: "ok", order: 0, model: "alpha-pro", harness: "gemini-cli" }, // both resolve
                { id: "bad-model", order: 1, model: "ghost", harness: "gemini-cli" }, // model missing
                { id: "bad-harness", order: 2, model: "alpha-pro", harness: "ghost" } // harness missing
            ]));

        const { setups } = await loadBenchmarkData(fakeDb);

        expect(setups.map(s => s.id)).toEqual(["ok"]);
        expect(warn).toHaveBeenCalledTimes(1);
        // The dropped ids are surfaced in the warning, not silently swallowed.
        expect(warn.mock.calls[0].join(" ")).toContain("bad-model");
        expect(warn.mock.calls[0].join(" ")).toContain("bad-harness");
        warn.mockRestore();
    });

    it("reads the three expected collections and orders setups by `order`", async () => {
        firestore.getDocs
            .mockResolvedValueOnce(forEachSnap([]))
            .mockResolvedValueOnce(forEachSnap([]))
            .mockResolvedValueOnce(docsSnap([]));

        await loadBenchmarkData(fakeDb);

        const collectionNames = firestore.collection.mock.calls.map(c => c[1]);
        expect(collectionNames).toEqual(["models", "harnesses", "setups"]);
        expect(firestore.orderBy).toHaveBeenCalledWith("order");
        // setups is fetched via query(collection, orderBy(...)), not a bare collection.
        expect(firestore.query).toHaveBeenCalledTimes(1);
        expect(firestore.getDocs).toHaveBeenCalledTimes(3);
    });

    it("returns empty shapes when collections are empty", async () => {
        firestore.getDocs
            .mockResolvedValueOnce(forEachSnap([]))
            .mockResolvedValueOnce(forEachSnap([]))
            .mockResolvedValueOnce(docsSnap([]));

        const { models, harnesses, setups } = await loadBenchmarkData(fakeDb);
        expect(models).toEqual({});
        expect(harnesses).toEqual({});
        expect(setups).toEqual([]);
    });

    it("propagates a Firestore error (so the caller can show a load-error state)", async () => {
        firestore.getDocs.mockRejectedValue(new Error("emulator down"));
        await expect(loadBenchmarkData(fakeDb)).rejects.toThrow("emulator down");
    });
});
