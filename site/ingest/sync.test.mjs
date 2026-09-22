import { describe, it, expect } from "vitest";

import {
    SYNCED_COLLECTIONS,
    clearCollection,
    readCollections,
    snapshotPath,
    writeCollection,
} from "./sync.mjs";

// Minimal in-memory stand-in for the Admin SDK surface sync.mjs uses:
// collection().get() / collection().doc() and the batch writer commitAll drives.
function fakeDb(seed = {}) {
    const store = new Map(
        Object.entries(seed).map(([name, docs]) => [name, new Map(Object.entries(docs))])
    );
    const col = name => {
        if (!store.has(name)) store.set(name, new Map());
        return store.get(name);
    };
    return {
        dump: name => Object.fromEntries(col(name)),
        collection(name) {
            return {
                async get() {
                    return {
                        docs: [...col(name)].map(([id, data]) => ({
                            id,
                            data: () => data,
                            ref: { collection: name, id },
                        })),
                    };
                },
                doc: id => ({ collection: name, id }),
            };
        },
        batch() {
            const ops = [];
            return {
                set: (ref, data) => ops.push({ kind: "set", ref, data }),
                delete: ref => ops.push({ kind: "delete", ref }),
                async commit() {
                    for (const op of ops) {
                        if (op.kind === "set") col(op.ref.collection).set(op.ref.id, op.data);
                        else col(op.ref.collection).delete(op.ref.id);
                    }
                },
            };
        },
    };
}

describe("SYNCED_COLLECTIONS", () => {
    it("carries the read-model the UI renders", () => {
        for (const c of ["setups", "models", "harnesses"]) {
            expect(SYNCED_COLLECTIONS).toContain(c);
        }
    });

    it("carries the raw rows too, so derive can be re-run locally", () => {
        // Without `results` a teammate could look at the board but could not
        // re-score it after a formula change without re-ingesting from the
        // original run artifacts, which they may not have.
        expect(SYNCED_COLLECTIONS).toContain("results");
    });
});

describe("snapshotPath", () => {
    it("names one file per collection under the snapshot dir", () => {
        expect(snapshotPath("/tmp/snap", "setups")).toBe("/tmp/snap/setups.json");
    });
});

describe("readCollections", () => {
    it("returns id/data pairs per collection", async () => {
        const db = fakeDb({
            setups: { "opus-openclaw": { id: "opus-openclaw", order: 1 } },
            models: { opus: { label: "Opus" } },
        });
        const out = await readCollections(db, ["setups", "models"]);
        expect(out.setups).toEqual([
            { id: "opus-openclaw", data: { id: "opus-openclaw", order: 1 } },
        ]);
        expect(out.models).toEqual([{ id: "opus", data: { label: "Opus" } }]);
    });

    it("returns an empty list for a collection with no documents", async () => {
        const out = await readCollections(fakeDb(), ["setups"]);
        expect(out.setups).toEqual([]);
    });
});

describe("clearCollection", () => {
    it("removes every document and reports how many", async () => {
        const db = fakeDb({ setups: { a: {}, b: {} } });
        expect(await clearCollection(db, "setups")).toBe(2);
        expect(db.dump("setups")).toEqual({});
    });

    it("commits in batches under the Firestore op limit", async () => {
        // 1000 docs is past the 450-op batch size, so a single batch would be
        // rejected by real Firestore.
        const many = Object.fromEntries(Array.from({ length: 1000 }, (_, i) => [`d${i}`, {}]));
        const db = fakeDb({ results: many });
        expect(await clearCollection(db, "results")).toBe(1000);
        expect(db.dump("results")).toEqual({});
    });
});

describe("writeCollection", () => {
    it("writes the snapshot documents", async () => {
        const db = fakeDb();
        await writeCollection(db, "setups", [{ id: "a", data: { order: 1 } }]);
        expect(db.dump("setups")).toEqual({ a: { order: 1 } });
    });

    it("drops a document the snapshot no longer has", async () => {
        // set() alone is an upsert by id, so a setup that was deleted upstream
        // would otherwise linger and show on the local board as a phantom arm.
        const db = fakeDb({ setups: { stale: { order: 9 }, kept: { order: 1 } } });
        await writeCollection(db, "setups", [{ id: "kept", data: { order: 1 } }]);
        expect(db.dump("setups")).toEqual({ kept: { order: 1 } });
    });

    it("leaves the other collections alone", async () => {
        const db = fakeDb({ setups: { a: {} }, models: { m: { label: "M" } } });
        await writeCollection(db, "setups", []);
        expect(db.dump("models")).toEqual({ m: { label: "M" } });
    });
});
