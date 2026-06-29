// =============================================================================
// devops-bench leaderboard — RESULT-FILE LOADER + VALIDATOR.
//
// Reads the upload protocol (see PROTOCOL.md): the Python eval harness writes one
// `rows.json` per run (a flat `ResultRow[]`); this loads those files and returns
// a flat, validated ResultRow[] ready to write to the `results` collection. This
// is the real-ingest input boundary, so it VALIDATES strictly and fails with
// file+index context — a malformed row would otherwise corrupt the leaderboard
// or be silently dropped by the frontend.
//
// Pure module (only node:fs / node:path for the file walk) so validation is
// unit-testable without Firestore — see load.test.mjs.
// =============================================================================

import fs from "node:fs";
import path from "node:path";

/** @typedef {import('../src/lib/schema').ResultRow} ResultRow */

const STATUSES = new Set(["success", "failed"]);
// run_YYYYMMDD_HHMMSS + optional `_<suffix>`. The timestamp alone isn't unique,
// so parallel runs append a suffix (pid / matrix id) to keep the
// setupId__runId__taskFolder__iteration doc id distinct.
const RUN_ID_RE = /^run_\d{8}_\d{6}(?:_[A-Za-z0-9_-]+)?$/;

// The harness emits each run as `run_<ts>/rows.json` (alongside a manifest.json
// the ingest does not read — identity is denormalized onto every row). A
// directory load discovers these rows.json files; the manifest is ignored.
const ROWS_FILE = "rows.json";

// Field validators. Each returns an error string or null.
const num01 = v => (v >= 0 && v <= 1 ? null : "must be in [0,1]");
const nonNeg = v => (v >= 0 ? null : "must be >= 0");

/**
 * Validate one parsed row against the ResultRow schema. Returns an array of
 * human-readable error strings (empty when valid). Does not throw.
 *
 * @param {any} row
 * @returns {string[]}
 */
export function validateRow(row) {
    const errs = [];
    if (!row || typeof row !== "object" || Array.isArray(row)) {
        return ["not an object"];
    }
    // TODO(follow-up): enforce `validated` as a required boolean once the
    // leaderboard gate is enabled in derive.mjs (deferred pending task-catalog
    // cleanup). Fixtures omit it today, so it is not yet required here.
    const str = k => {
        if (typeof row[k] !== "string" || row[k] === "") errs.push(`${k}: required non-empty string`);
    };
    const int = (k, check) => {
        if (typeof row[k] !== "number" || !Number.isInteger(row[k])) { errs.push(`${k}: required integer`); return; }
        const e = check && check(row[k]);
        if (e) errs.push(`${k}: ${e}`);
    };
    const float = (k, check) => {
        if (typeof row[k] !== "number" || !Number.isFinite(row[k])) { errs.push(`${k}: required number`); return; }
        const e = check && check(row[k]);
        if (e) errs.push(`${k}: ${e}`);
    };
    // Nullable score/token fields: explicit null is valid (unscored iteration /
    // uncaptured usage); otherwise apply the numeric check.
    const intOrNull = (k, check) => { if (row[k] !== null) int(k, check); };
    const floatOrNull = (k, check) => { if (row[k] !== null) float(k, check); };

    str("setupId");
    str("model");
    str("harness");
    // augmentation: capability tokens (`["mcp", "skills"]`); [] means baseline.
    if (!Array.isArray(row.augmentation) || row.augmentation.some(a => typeof a !== "string" || a === "")) {
        errs.push("augmentation: must be an array of non-empty strings (use [] for baseline)");
    }
    if (typeof row.runId !== "string" || !RUN_ID_RE.test(row.runId)) {
        errs.push("runId: must match run_YYYYMMDD_HHMMSS with an optional _<suffix>");
    }
    str("t");
    str("taskFolder");
    str("taskName");
    int("iteration", v => (v >= 0 ? null : "must be >= 0"));
    if (!STATUSES.has(row.status)) errs.push('status: must be "success" or "failed"');
    floatOrNull("outcomeScore", num01);
    floatOrNull("toolScore", num01);
    float("latencySec", nonNeg);
    intOrNull("inputTokens", nonNeg);
    intOrNull("outputTokens", nonNeg);

    return errs;
}

/**
 * Parse + validate the contents of a single results file.
 *
 * @param {string} file path to a JSON ResultRow[] file
 * @returns {{ rows: ResultRow[], errors: string[] }}
 */
export function loadFile(file) {
    let parsed;
    try {
        parsed = JSON.parse(fs.readFileSync(file, "utf8"));
    } catch (e) {
        return { rows: [], errors: [`${file}: invalid JSON — ${e.message}`] };
    }
    if (!Array.isArray(parsed)) {
        return { rows: [], errors: [`${file}: top level must be a ResultRow[] array`] };
    }
    const rows = [];
    const errors = [];
    parsed.forEach((row, i) => {
        const rowErrs = validateRow(row);
        if (rowErrs.length) {
            errors.push(`${file}[${i}]: ${rowErrs.join("; ")}`);
        } else {
            rows.push(row);
        }
    });
    return { rows, errors };
}

// Recursively collect the `rows.json` files under a directory, path-sorted so a
// `results/` tree of `run_<ts>/rows.json` ingests in chronological run order.
// Everything else (notably the sibling manifest.json) is skipped.
function rowsFilesUnder(dir) {
    const out = [];
    for (const entry of fs.readdirSync(dir, { withFileTypes: true }).sort((a, b) => a.name.localeCompare(b.name))) {
        const full = path.join(dir, entry.name);
        if (entry.isDirectory()) out.push(...rowsFilesUnder(full));
        else if (entry.name === ROWS_FILE) out.push(full);
    }
    return out;
}

// Expand a path to the result files it represents: an explicit file is taken
// as-is (it must be a ResultRow[]); a directory contributes the rows.json files
// found anywhere beneath it, so either a single run dir or a whole results/ tree
// can be ingested in one go.
function filesFor(p) {
    if (!fs.existsSync(p)) throw new Error(`path not found: ${p}`);
    const stat = fs.statSync(p);
    if (stat.isDirectory()) return rowsFilesUnder(p);
    return [p];
}

/**
 * Load and validate ResultRows from a list of file/dir paths. THROWS with a
 * full, line-by-line report if any row fails validation — partial ingest of a
 * malformed batch is never desirable. Returns the flat row set on success.
 *
 * @param {string[]} paths
 * @returns {ResultRow[]}
 */
export function loadResults(paths) {
    const files = paths.flatMap(filesFor);
    if (files.length === 0) {
        throw new Error(`no ${ROWS_FILE} result files found in: ${paths.join(", ")}`);
    }
    const rows = [];
    const errors = [];
    for (const f of files) {
        const res = loadFile(f);
        rows.push(...res.rows);
        errors.push(...res.errors);
    }
    if (errors.length) {
        throw new Error(
            `Validation failed for ${errors.length} row(s):\n  ` + errors.join("\n  ")
        );
    }
    if (rows.length === 0) {
        throw new Error(`no rows found across ${files.length} file(s): ${files.join(", ")}`);
    }
    return rows;
}
