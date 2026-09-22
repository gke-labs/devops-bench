// =============================================================================
// devops-bench leaderboard — DEV DB -> LOCAL EMULATOR SYNC.
//
// Gives the team one shared copy of real run data that everyone can point a
// local dashboard at, without publishing it. The internal `leaderboard-dev`
// database denies all client access (firestore.dev.rules), so nothing here is
// reachable from a browser; reads go through the Admin SDK under Application
// Default Credentials and are gated by project IAM instead.
//
// Two phases, two processes, on purpose. firebase-admin resolves the emulator
// from the process-wide FIRESTORE_EMULATOR_HOST, so one process cannot hold a
// real-Firestore connection and an emulator connection at the same time.
// Splitting also leaves an inspectable snapshot on disk between the two halves.
//
//   node sync.mjs pull [dir]   # real Firestore  -> JSON on disk  (needs ADC)
//   node sync.mjs push [dir]   # JSON on disk    -> emulator      (no creds)
//
// The npm wrappers set the targets; see package.json.
//   npm run sync:dev           # both halves, leaderboard-dev -> emulator
// =============================================================================

import { mkdirSync, readFileSync, writeFileSync } from "node:fs";
import { join } from "node:path";
import { openDb, commitAll, BATCH_LIMIT } from "./firestore.mjs";

// The read-model the UI renders, plus the raw rows it was derived from, so a
// teammate can re-run derive.mjs locally after a formula change instead of
// having to re-ingest from the original run artifacts.
export const SYNCED_COLLECTIONS = ["results", "setups", "models", "harnesses"];

export const DEFAULT_SNAPSHOT_DIR = ".cache/dev-snapshot";

/** Snapshot file for one collection. */
export function snapshotPath(dir, collection) {
    return join(dir, `${collection}.json`);
}

/**
 * Read every document of each collection into `{collection: [{id, data}]}`.
 *
 * @param {FirebaseFirestore.Firestore} db
 * @param {string[]} collections
 * @returns {Promise<Record<string, {id: string, data: object}[]>>}
 */
export async function readCollections(db, collections = SYNCED_COLLECTIONS) {
    const out = {};
    for (const name of collections) {
        const snap = await db.collection(name).get();
        out[name] = snap.docs.map(d => ({ id: d.id, data: d.data() }));
    }
    return out;
}

/**
 * Delete every document in `collection`.
 *
 * A push `set()`s by document id, so without this a document that existed in an
 * earlier snapshot but not the current one would survive and the local board
 * would show a setup or task the dev DB no longer has. Emulator-only, enforced
 * by the caller.
 *
 * @param {FirebaseFirestore.Firestore} db
 * @param {string} collection
 * @returns {Promise<number>} how many documents were removed
 */
export async function clearCollection(db, collection) {
    const snap = await db.collection(collection).get();
    for (let i = 0; i < snap.docs.length; i += BATCH_LIMIT) {
        const batch = db.batch();
        for (const doc of snap.docs.slice(i, i + BATCH_LIMIT)) batch.delete(doc.ref);
        await batch.commit();
    }
    return snap.docs.length;
}

/**
 * Replace `collection` with `docs`.
 *
 * @param {FirebaseFirestore.Firestore} db
 * @param {string} collection
 * @param {{id: string, data: object}[]} docs
 */
export async function writeCollection(db, collection, docs) {
    await clearCollection(db, collection);
    await commitAll(
        db,
        docs.map(d => ({ ref: db.collection(collection).doc(d.id), data: d.data }))
    );
}

async function pull(dir) {
    const { db, info, emulator } = openDb();
    console.log(`Pulling from ${info}`);
    if (emulator) {
        // Not fatal — pulling from an emulator is a legitimate way to hand a
        // snapshot to someone — but it is almost always a forgotten env var.
        console.warn("  note: FIRESTORE_EMULATOR_HOST is set, so this reads the EMULATOR.");
    }

    const data = await readCollections(db);
    mkdirSync(dir, { recursive: true });
    for (const [name, docs] of Object.entries(data)) {
        writeFileSync(snapshotPath(dir, name), JSON.stringify(docs, null, 2));
        console.log(`  ${name}: ${docs.length} docs`);
    }
    console.log(`Snapshot written to ${dir}`);
}

async function push(dir) {
    const { db, info, emulator } = openDb();

    // Hard stop rather than a guard flag. This command's whole purpose is to
    // populate a throwaway local emulator; every real database in the project
    // is either public (leaderboard-test is what the live site serves),
    // published (leaderboard), or the shared source of truth we just read
    // (leaderboard-dev). None of them should be overwritten from a stale
    // snapshot on somebody's laptop.
    if (!emulator) {
        console.error(
            `Refusing to push into ${info}.\n` +
            "sync push only ever writes a local emulator; set FIRESTORE_EMULATOR_HOST " +
            "(e.g. 127.0.0.1:8080), or use ingest.mjs to write a real database."
        );
        process.exit(1);
    }

    console.log(`Pushing into ${info}`);
    for (const name of SYNCED_COLLECTIONS) {
        let docs;
        try {
            docs = JSON.parse(readFileSync(snapshotPath(dir, name), "utf8"));
        } catch {
            console.error(
                `Missing ${snapshotPath(dir, name)} — run "npm run sync:pull" first.`
            );
            process.exit(1);
        }
        await writeCollection(db, name, docs);
        console.log(`  ${name}: ${docs.length} docs`);
    }
    console.log("Done. Start the UI with: npm run dev");
}

async function main() {
    const [mode, dir = DEFAULT_SNAPSHOT_DIR] = process.argv.slice(2);
    if (mode === "pull") return pull(dir);
    if (mode === "push") return push(dir);
    console.error("Usage: node sync.mjs <pull|push> [dir]");
    process.exit(1);
}

// Importable for tests; only the CLI invocation runs main().
if (process.argv[1] && import.meta.url === `file://${process.argv[1]}`) {
    main().catch(err => {
        console.error(err);
        process.exit(1);
    });
}
