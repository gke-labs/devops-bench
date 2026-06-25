// =============================================================================
// devops-bench leaderboard — FIRESTORE SEED SCRIPT (Node, firebase-admin).
//
// Writes the FABRICATED benchmark data the dashboard renders:
//
//   models      <- mock-data.models          (metadata, read by the dashboard)
//   harnesses   <- mock-data.harnesses       (metadata, read by the dashboard)
//   results     <- generateRaw()             (RAW source of truth, per iteration)
//   setups      <- derive(generateRaw())     (DERIVED read-model the UI renders)
//
// Two targets, selected by whether FIRESTORE_EMULATOR_HOST is set:
//
//   EMULATOR (default, no credentials needed):
//     FIRESTORE_EMULATOR_HOST=127.0.0.1:8080 GCLOUD_PROJECT=devops-bench-demo \
//       node seed.mjs                                  # → DB leaderboard-test
//
//   REAL Firestore (the shared TEST database — uses Application Default Creds;
//   run `gcloud auth application-default login` first):
//     GCLOUD_PROJECT=devops-bench-shared FIRESTORE_DATABASE_ID=leaderboard-test \
//       node seed.mjs
//
// This script writes FAKE data, so it HARD-REFUSES to target the production
// database (`leaderboard`) unless ALLOW_PROD_SEED=true is explicitly set — prod
// gets real ingest, not this. Admin writes bypass the security rules.
// =============================================================================

import admin from "firebase-admin";
import { getFirestore } from "firebase-admin/firestore";
import { models, harnesses, generateRaw, derive } from "./mock-data.mjs";

const EMULATOR = !!process.env.FIRESTORE_EMULATOR_HOST;
const PROJECT_ID =
    process.env.GCLOUD_PROJECT ||
    process.env.GOOGLE_CLOUD_PROJECT ||
    (EMULATOR ? "devops-bench-demo" : "devops-bench-shared");
// Named Firestore database (must match the client's VITE_FIRESTORE_DATABASE_ID).
// Defaults to the test DB; never silently defaults to prod.
const DATABASE_ID = process.env.FIRESTORE_DATABASE_ID || "leaderboard-test";
const PROD_DATABASE_ID = "leaderboard"; // real-data DB this fake seeder must not touch
const BATCH_LIMIT = 450; // Firestore caps a batch at 500 ops; stay safely under.

// Guard: fabricated data must never land in production unless explicitly forced.
if (DATABASE_ID === PROD_DATABASE_ID && process.env.ALLOW_PROD_SEED !== "true") {
    console.error(
        `Refusing to seed FAKE data into the production database "${PROD_DATABASE_ID}".\n` +
        "Production is populated by the real ingest pipeline, not this script.\n" +
        "Target the test DB instead (FIRESTORE_DATABASE_ID=leaderboard-test), or — if\n" +
        "you really mean it — re-run with ALLOW_PROD_SEED=true."
    );
    process.exit(1);
}

// Emulator needs no credentials; real Firestore uses Application Default Creds.
const app = admin.initializeApp(
    EMULATOR
        ? { projectId: PROJECT_ID }
        : { projectId: PROJECT_ID, credential: admin.credential.applicationDefault() }
);
const db = getFirestore(app, DATABASE_ID);

// Commit a list of {ref, data} writes in chunks that respect the batch limit.
async function commitAll(writes) {
    for (let i = 0; i < writes.length; i += BATCH_LIMIT) {
        const batch = db.batch();
        for (const w of writes.slice(i, i + BATCH_LIMIT)) batch.set(w.ref, w.data);
        await batch.commit();
    }
}

// Delete every doc in a collection so re-seeding is idempotent (no stale rows).
async function clearCollection(name) {
    const snap = await db.collection(name).get();
    const refs = snap.docs.map(d => d.ref);
    for (let i = 0; i < refs.length; i += BATCH_LIMIT) {
        const batch = db.batch();
        for (const ref of refs.slice(i, i + BATCH_LIMIT)) batch.delete(ref);
        await batch.commit();
    }
    return refs.length;
}

async function main() {
    const target = EMULATOR ? `emulator (${process.env.FIRESTORE_EMULATOR_HOST})` : "REAL Firestore";
    console.log(`Seeding ${target} — project: ${PROJECT_ID}, database: ${DATABASE_ID}...`);

    for (const c of ["models", "harnesses", "results", "setups"]) {
        const n = await clearCollection(c);
        if (n) console.log(`  cleared ${n} existing docs from ${c}`);
    }

    // --- metadata collections (doc id = the key) ---
    await commitAll(Object.entries(models).map(([id, data]) => ({
        ref: db.collection("models").doc(id), data
    })));
    await commitAll(Object.entries(harnesses).map(([id, data]) => ({
        ref: db.collection("harnesses").doc(id), data
    })));
    console.log(`  wrote ${Object.keys(models).length} models, ${Object.keys(harnesses).length} harnesses`);

    // --- raw results (source of truth, auto-id docs) ---
    const raw = generateRaw();
    await commitAll(raw.map(row => ({
        ref: db.collection("results").doc(), data: row
    })));
    console.log(`  wrote ${raw.length} raw results rows`);

    // --- derived setups read-model (doc id = setup.id) ---
    const setups = derive(raw);
    await commitAll(setups.map(s => ({
        ref: db.collection("setups").doc(s.id), data: s
    })));
    console.log(`  wrote ${setups.length} derived setups`);

    console.log("Seed complete.");
}

main().catch(err => {
    console.error("Seed failed:", err);
    process.exit(1);
});
