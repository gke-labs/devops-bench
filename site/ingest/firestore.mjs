// =============================================================================
// devops-bench leaderboard — FIRESTORE PLUMBING (shared by ingest + derive).
//
// One place for: target selection (emulator / shared TEST / prod), the
// production-write guard, batched commits, and the deterministic raw-row doc id.
// Both ingest.mjs (upload + derive) and derive.mjs (re-derive only) open the DB
// through openDb() so they target identically and share the prod guard.
//
// Target selection (same contract as seed.mjs):
//   - FIRESTORE_EMULATOR_HOST set        -> local emulator, no credentials
//   - else                               -> real Firestore via Application
//                                           Default Credentials
//   - FIRESTORE_DATABASE_ID              -> which named DB (default
//                                           "leaderboard-test"); prod is
//                                           "leaderboard" and is GUARDED.
// =============================================================================

import admin from "firebase-admin";
import { getFirestore } from "firebase-admin/firestore";

const PROD_DATABASE_ID = "leaderboard";
export const BATCH_LIMIT = 450; // Firestore caps a batch at 500 ops; stay under.

/**
 * Initialize firebase-admin and return the target Firestore plus a human label.
 * Enforces the production-write guard: writing `leaderboard` requires
 * ALLOW_PROD_INGEST=true, so a mistargeted run can't clobber prod. Exits the
 * process (code 1) when the guard trips.
 *
 * @returns {{ db: FirebaseFirestore.Firestore, info: string,
 *             projectId: string, databaseId: string, emulator: boolean }}
 */
export function openDb() {
    const emulator = !!process.env.FIRESTORE_EMULATOR_HOST;
    const projectId =
        process.env.GCLOUD_PROJECT ||
        process.env.GOOGLE_CLOUD_PROJECT ||
        (emulator ? "devops-bench-demo" : "devops-bench-shared");
    const databaseId = process.env.FIRESTORE_DATABASE_ID || "leaderboard-test";

    if (databaseId === PROD_DATABASE_ID && process.env.ALLOW_PROD_INGEST !== "true") {
        console.error(
            `Refusing to write the production database "${PROD_DATABASE_ID}" ` +
            "without ALLOW_PROD_INGEST=true.\n" +
            "Iterate against the test DB (FIRESTORE_DATABASE_ID=leaderboard-test), " +
            "or set ALLOW_PROD_INGEST=true to publish."
        );
        process.exit(1);
    }

    const app = admin.initializeApp(
        emulator
            ? { projectId }
            : { projectId, credential: admin.credential.applicationDefault() }
    );
    const db = getFirestore(app, databaseId);
    const target = emulator
        ? `emulator (${process.env.FIRESTORE_EMULATOR_HOST})`
        : "REAL Firestore";
    return {
        db,
        info: `${target} — project: ${projectId}, database: ${databaseId}`,
        projectId, databaseId, emulator
    };
}

/**
 * Commit a list of writes in batches under the Firestore op limit.
 * Each write is { ref, data, merge? }; `merge: true` does a partial upsert.
 *
 * @param {FirebaseFirestore.Firestore} db
 * @param {{ref: FirebaseFirestore.DocumentReference, data: object, merge?: boolean}[]} writes
 */
export async function commitAll(db, writes) {
    for (let i = 0; i < writes.length; i += BATCH_LIMIT) {
        const batch = db.batch();
        for (const w of writes.slice(i, i + BATCH_LIMIT)) {
            batch.set(w.ref, w.data, w.merge ? { merge: true } : undefined);
        }
        await batch.commit();
    }
}

/**
 * Deterministic doc id for a raw row: (setupId, runId, taskFolder, iteration) is
 * its natural key, so re-ingesting the same run OVERWRITES instead of
 * duplicating (idempotent). Firestore ids may not contain "/", so slashes in any
 * component are replaced.
 *
 * @param {{setupId: string, runId: string, taskFolder: string, iteration: number}} row
 * @returns {string}
 */
export function resultDocId(row) {
    return [row.setupId, row.runId, row.taskFolder, row.iteration]
        .join("__")
        .replace(/\//g, "_");
}
