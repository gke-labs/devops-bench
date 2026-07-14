// =============================================================================
// devops-bench leaderboard — REAL INGEST CLI (upload + derive).
//
// Turns real eval-run output into the dashboard's Firestore collections. The
// counterpart to seed.mjs: the seeder fabricates data and CLEARS collections;
// this ingests real runs and is ADDITIVE + IDEMPOTENT, so re-running it (or
// ingesting run #2 after run #1) never wipes prior history.
//
//   results   <- loadResults(paths)         (raw ResultRow[]; deterministic doc
//                                            ids -> re-ingest overwrites, no dupes)
//   setups    <- derive(ALL results)         (re-derived from the FULL row set, so
//                                            history stays complete across runs)
//   models /
//   harnesses <- collectMetadata(ALL rows)   (merge-upsert from the catalog)
//
// Input is the upload protocol (PROTOCOL.md): one or more JSON files, each a
// ResultRow[]. Pass files and/or directories of *.json files:
//
//   node ingest.mjs <path> [<path> ...]      (defaults to $RESULTS_ROOT)
//
// Target + prod guard live in firestore.mjs (shared with derive.mjs): emulator
// when FIRESTORE_EMULATOR_HOST is set, else real Firestore via ADC; defaults to
// the TEST DB, and writing prod ("leaderboard") requires ALLOW_PROD_INGEST=true.
// =============================================================================

import path from "node:path";

import { loadResults } from "./load.mjs";
import { derive } from "./derive.mjs";
import { openDb, commitAll, resultDocId } from "./firestore.mjs";
import { PALETTE, SETUP_CATALOG, collectMetadata } from "./catalog.mjs";

async function main() {
    const args = process.argv.slice(2);
    const paths = args.length ? args : [process.env.RESULTS_ROOT || "results"];

    const { db, info } = openDb();
    console.log(`Ingesting into ${info}`);
    console.log(`  sources: ${paths.map(p => path.resolve(p)).join(", ")}`);

    // 1. Load + validate this invocation's rows (throws on any invalid row).
    const newRows = loadResults(paths);
    const runIds = [...new Set(newRows.map(r => r.runId))];
    console.log(`  loaded ${newRows.length} rows across ${runIds.length} run(s): ${runIds.join(", ")}`);

    // 2. Upsert raw rows (idempotent: deterministic doc ids).
    await commitAll(db, newRows.map(row => ({
        ref: db.collection("results").doc(resultDocId(row)),
        data: row
    })));
    console.log(`  wrote ${newRows.length} raw results rows`);

    // 3. Re-derive setups from the FULL row set so history stays complete.
    const allRows = (await db.collection("results").get()).docs.map(d => d.data());
    const setups = derive(allRows, { catalog: SETUP_CATALOG, palette: PALETTE });
    await commitAll(db, setups.map(s => ({ ref: db.collection("setups").doc(s.id), data: s })));
    console.log(`  derived ${setups.length} setups from ${allRows.length} total rows`);

    // 4. Upsert model/harness metadata for everything the full set references.
    const { models, harnesses, unknown } = collectMetadata(allRows);
    await commitAll(db, [
        ...[...models].map(([id, data]) => ({ ref: db.collection("models").doc(id), data, merge: true })),
        ...[...harnesses].map(([id, data]) => ({ ref: db.collection("harnesses").doc(id), data, merge: true }))
    ]);
    console.log(`  upserted ${models.size} models, ${harnesses.size} harnesses`);
    if (unknown.models.size) {
        console.warn(`  ⚠ unknown models (synthesized — add to catalog.mjs): ${[...unknown.models].join(", ")}`);
    }
    if (unknown.harnesses.size) {
        console.warn(`  ⚠ unknown harnesses (synthesized — add to catalog.mjs): ${[...unknown.harnesses].join(", ")}`);
    }

    console.log("Ingest complete.");
}

main().catch(err => {
    console.error("Ingest failed:", err.message || err);
    process.exit(1);
});
