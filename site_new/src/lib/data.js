// =============================================================================
// Data loading — reads the DERIVED read-model from Firestore.
//
// The dashboard reads only the read-model collections (models, harnesses,
// setups). The raw per-iteration `results` collection is the source of truth but
// is never read by the client — pass1/pass5/passMax are precomputed into `setups`
// at seed/ingest time (see seed/mock-data.mjs derive()).
// =============================================================================

// @ts-check
import { collection, getDocs, orderBy, query } from "firebase/firestore";

/**
 * @typedef {import('./schema').BenchmarkData} BenchmarkData
 * @typedef {import('./schema').ModelMap} ModelMap
 * @typedef {import('./schema').HarnessMap} HarnessMap
 * @typedef {import('./schema').Model} Model
 * @typedef {import('./schema').Harness} Harness
 * @typedef {import('./schema').Setup} Setup
 */

// Fetch the three read-model collections and shape them the way the UI consumes
// (see ./schema.d.ts for the full shapes):
//   models    : ModelMap   — { [modelId]:   Model }
//   harnesses : HarnessMap — { [harnessId]: Harness }
//   setups    : Setup[]
/**
 * @param {import('firebase/firestore').Firestore} db
 * @returns {Promise<BenchmarkData>}
 */
export async function loadBenchmarkData(db) {
    const [modelsSnap, harnessesSnap, setupsSnap] = await Promise.all([
        getDocs(collection(db, "models")),
        getDocs(collection(db, "harnesses")),
        getDocs(query(collection(db, "setups"), orderBy("order")))
    ]);

    // doc.data() is Firestore's untyped DocumentData; the casts mark the trust
    // boundary — we assert each doc matches the schema (see schema.d.ts), since
    // Firestore can't enforce it. This is exactly the spot a runtime validator
    // would slot in if we ever want a real check, not just a documented shape.
    /** @type {ModelMap} */
    const models = {};
    modelsSnap.forEach(doc => { models[doc.id] = /** @type {Model} */ (doc.data()); });

    /** @type {HarnessMap} */
    const harnesses = {};
    harnessesSnap.forEach(doc => { harnesses[doc.id] = /** @type {Harness} */ (doc.data()); });

    // Drop setups whose model/harness id doesn't resolve in the metadata
    // collections. The three collections are written independently (and in
    // production by separate ingest steps), so a dangling reference is possible;
    // rendering one would crash every accessor that does `models[setup.model].name`.
    // Filtering here upholds the invariant "every setup's refs resolve" for the
    // whole UI. Dropped ids are logged, not silently swallowed.
    const allSetups = setupsSnap.docs.map(doc => /** @type {Setup} */ (doc.data()));
    const setups = allSetups.filter(s => models[s.model] && harnesses[s.harness]);
    const dropped = allSetups.filter(s => !(models[s.model] && harnesses[s.harness]));
    if (dropped.length) {
        console.warn(
            `loadBenchmarkData: dropped ${dropped.length} setup(s) with unresolved model/harness refs:`,
            dropped.map(s => s.id)
        );
    }

    return { models, harnesses, setups };
}
