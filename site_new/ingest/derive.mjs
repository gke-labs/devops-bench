// =============================================================================
// devops-bench leaderboard — DATA-DRIVEN DERIVATION (raw results -> read-model).
//
// This is the real-ingest counterpart to the mock's derive() in
// seed/mock-data.mjs. The crucial difference: the mock derive iterates a
// HARDCODED setup/task catalog (SETUP_DEFS / TASK_CATALOG), so it can only ever
// emit the 8 fabricated setups and 12 fabricated tasks. Real eval runs contain
// arbitrary setups and tasks, so this derive() DISCOVERS them from the rows
// themselves:
//
//   setups  <- distinct row.setupId           (one dashboard line per setup)
//   tasks   <- distinct row.taskFolder at the LATEST run of each setup
//   history <- one aggregate point per distinct row.t, time-ordered
//
// The SCORING FORMULA is NOT duplicated here — PASS_THRESHOLD and the pass@k
// estimator are imported from seed/mock-data.mjs so test data and real data are
// scored by exactly one definition. Change the formula there and re-run derive
// (see the CLI at the bottom) to re-score everything from the same raw rows.
//
// Presentation (order / color) is not derivable from results — it's curation, so
// it comes from the optional catalog overrides, falling back to discovery order
// and a palette. Model/harness display metadata is handled separately by the
// catalog (see collectMetadata in catalog.mjs); this module only emits setups.
// =============================================================================

import { PASS_THRESHOLD, passAtK } from "../seed/mock-data.mjs";
import { PALETTE, SETUP_CATALOG } from "./catalog.mjs";

/**
 * @typedef {import('../src/lib/schema').ResultRow} ResultRow
 * @typedef {import('../src/lib/schema').Setup} Setup
 * @typedef {import('../src/lib/schema').Scores} Scores
 */

const K = 5; // the k in pass@5; keep aligned with the mock's K.

function round(v, dp) {
    if (typeof v !== "number" || !Number.isFinite(v)) return null;
    const f = 10 ** dp;
    return Math.round(v * f) / f;
}

// pass1/pass5/passMax (as percentages) for a list of iteration rows that all
// belong to the same (setup, task, run). Iterations with a non-finite
// outcomeScore are EXCLUDED from both n and c — an unscored/failed iteration is
// missing data, not a 0% pass — mirroring the schema's nullable Scores. A group
// with no scored iterations yields all-null (the UI renders these as blank).
//
// pass5/passMax stay null today: the harness emits a single iteration per
// (setup × task × run), so pass@k would only ever collapse onto pass1, and the
// dashboard's MetricToggle hides metrics that are all-null. passAtK + K are kept
// (imported above) to re-enable here, unchanged, once multi-iteration runs land
// — keeping mock and real data scored by exactly one definition.
/** @returns {Scores} */
function scoresFor(rows) {
    const scored = rows.filter(r => Number.isFinite(r.outcomeScore));
    const n = scored.length;
    if (n === 0) return { pass1: null, pass5: null, passMax: null };
    const c = scored.filter(r => r.outcomeScore >= PASS_THRESHOLD).length;
    return {
        pass1: round((c / n) * 100, 1),
        pass5: null,
        passMax: null
    };
}

// Mean over a list of per-task Scores, per metric, skipping nulls. A metric with
// no non-null values across the run stays null rather than collapsing to 0.
/** @returns {Scores} */
function meanScores(scoreList) {
    const avg = m => {
        const vals = scoreList.map(s => s[m]).filter(v => typeof v === "number");
        return vals.length ? round(vals.reduce((a, b) => a + b, 0) / vals.length, 1) : null;
    };
    return { pass1: avg("pass1"), pass5: avg("pass5"), passMax: avg("passMax") };
}

// Stable first-appearance order of a key as rows are scanned. Used so the
// derived order is deterministic for a given row ordering and, for mock data,
// matches the old SETUP_DEFS/TASK_CATALOG order.
function firstSeenOrder(rows, keyOf) {
    const order = new Map();
    for (const r of rows) {
        const k = keyOf(r);
        if (!order.has(k)) order.set(k, order.size);
    }
    return order;
}

/**
 * Project raw result rows into the `setups` read-model the dashboard renders.
 *
 * Pure and data-driven: every distinct `setupId` present in `rows` becomes one
 * Setup, with `tasks[]` at its latest run and a complete, time-ordered
 * `history[]`. Pass the FULL row set (all runs ever ingested) so history is
 * complete.
 *
 * @param {ResultRow[]} rows
 * @param {{ catalog?: Record<string, {order?: number, color?: string}>, palette?: string[] }} [opts]
 *   catalog: optional per-setupId presentation overrides; palette: color cycle.
 * @returns {Setup[]} sorted by `order`
 */
export function derive(rows, opts = {}) {
    const catalog = opts.catalog || SETUP_CATALOG || {};
    const palette = opts.palette || PALETTE;

    // TODO(follow-up): gate inclusion on `r.validated === true` here (the mock
    // seeder already does) so only vetted runs reach the leaderboard. Deliberately
    // deferred: enforcing it now would drop most existing rows until the task
    // catalog is vetted/organized. Re-enable with load.mjs:validateRow requiring
    // `validated` once that cleanup lands.
    // Group rows by setupId (the join key the whole UI keys on).
    const bySetup = new Map();
    for (const r of rows) {
        if (!r || !r.setupId) continue;
        if (!bySetup.has(r.setupId)) bySetup.set(r.setupId, []);
        bySetup.get(r.setupId).push(r);
    }

    const discovery = firstSeenOrder(rows.filter(r => r && r.setupId), r => r.setupId);

    const setups = [];
    for (const [id, setupRows] of bySetup) {
        const idx = discovery.get(id);
        const override = catalog[id] || {};

        // Identity is denormalized onto every row; take it from the first one.
        const head = setupRows[0];

        // Time-ordered unique runs; tasks reflect the latest.
        const runTimes = [...new Set(setupRows.map(r => r.t))].sort();
        const latest = runTimes[runTimes.length - 1];

        // Tasks present at the latest run, in first-appearance order, scored.
        const latestRows = setupRows.filter(r => r.t === latest);
        const taskOrder = firstSeenOrder(latestRows, r => r.taskFolder);
        const tasks = [...taskOrder.keys()].map(folder => {
            const taskRows = latestRows.filter(r => r.taskFolder === folder);
            return {
                folder,
                name: taskRows[0].taskName || folder,
                scores: scoresFor(taskRows)
            };
        });

        // History: one aggregate point per run = mean of that run's per-task scores.
        const history = runTimes.map(t => {
            const runRows = setupRows.filter(r => r.t === t);
            const perTaskFolders = firstSeenOrder(runRows, r => r.taskFolder);
            const perTask = [...perTaskFolders.keys()].map(folder =>
                scoresFor(runRows.filter(r => r.taskFolder === folder))
            );
            return { t, scores: meanScores(perTask) };
        });

        setups.push({
            id,
            order: typeof override.order === "number" ? override.order : idx,
            model: head.model,
            harness: head.harness,
            // Capability tokens, copied so the emitted Setup doesn't alias a row.
            augmentation: Array.isArray(head.augmentation) ? head.augmentation.slice() : [],
            color: override.color || palette[idx % palette.length],
            tasks,
            history
        });
    }

    return setups.sort((a, b) => a.order - b.order);
}

// --- standalone CLI: re-derive from the results already in Firestore ----------
//
// Use this after changing the scoring formula (PASS_THRESHOLD / passAtK), to
// re-score every setup from the existing raw rows WITHOUT re-uploading. The
// normal path (ingest.mjs) runs derive automatically after each upload.
//
//   FIRESTORE_EMULATOR_HOST=127.0.0.1:8080 GCLOUD_PROJECT=devops-bench-demo \
//     node derive.mjs
//   GCLOUD_PROJECT=devops-bench-shared FIRESTORE_DATABASE_ID=leaderboard-test \
//     node derive.mjs

import { fileURLToPath } from "node:url";

async function main() {
    const { openDb, commitAll } = await import("./firestore.mjs");
    const { collectMetadata } = await import("./catalog.mjs");

    const { db, info } = openDb();
    console.log(`Re-deriving in ${info}`);

    const snap = await db.collection("results").get();
    const rows = snap.docs.map(d => d.data());
    if (rows.length === 0) {
        console.log("No results rows present; nothing to derive.");
        return;
    }

    const setups = derive(rows, { catalog: SETUP_CATALOG, palette: PALETTE });
    await commitAll(db, setups.map(s => ({ ref: db.collection("setups").doc(s.id), data: s })));
    console.log(`  derived ${setups.length} setups from ${rows.length} rows`);

    const { models, harnesses, unknown } = collectMetadata(rows);
    const meta = [
        ...[...models].map(([id, data]) => ({ ref: db.collection("models").doc(id), data, merge: true })),
        ...[...harnesses].map(([id, data]) => ({ ref: db.collection("harnesses").doc(id), data, merge: true }))
    ];
    await commitAll(db, meta);
    console.log(`  upserted ${models.size} models, ${harnesses.size} harnesses`);
    if (unknown.models.size) console.warn(`  ⚠ unknown models (add to catalog.mjs): ${[...unknown.models].join(", ")}`);
    if (unknown.harnesses.size) console.warn(`  ⚠ unknown harnesses (add to catalog.mjs): ${[...unknown.harnesses].join(", ")}`);

    console.log("Derive complete.");
}

if (process.argv[1] === fileURLToPath(import.meta.url)) {
    main().catch(err => { console.error("Derive failed:", err); process.exit(1); });
}
