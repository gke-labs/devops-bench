// =============================================================================
// devops-bench leaderboard — INGEST CATALOG (the dashboard vocabulary).
//
// The benchmark output records the RAW agent identity it ran with
// (`agentModel` / `agentProvider` / `agentType`). The dashboard, however, keys
// on CURATED ids (e.g. `alpha-pro`, `gemini-cli`) and renders metadata
// (display name, provider, license, logo / accent) that does not exist in the
// eval output. This module is the ONE place that bridges the two:
//
//   - MODEL_ALIASES / HARNESS_ALIASES  : raw identity  -> curated id
//   - MODELS / HARNESSES               : curated id    -> dashboard metadata
//   - resolveModel() / resolveHarness(): the lookups, with a safe fallback
//
// Fallback policy: an unknown model/harness is NOT dropped (that would make a
// whole run vanish from the leaderboard). Instead it is slugified into a key and
// given minimal synthesized metadata, and the resolver flags it so the ingest
// can warn. Add a real alias + metadata entry here to give it a proper home.
// =============================================================================

// --- curated metadata (mirrors the `models` / `harnesses` collections) -------

/** @type {Record<string, {name: string, provider: string, license: string, logo: string}>} */
export const MODELS = {
    "alpha-pro":      { name: "Alpha Pro",      provider: "Acme",    license: "Proprietary", logo: "alpha" },
    "beta-sonic":     { name: "Beta Sonic",     provider: "Globex",  license: "Proprietary", logo: "beta" },
    "gamma-coder":    { name: "Gamma Coder",    provider: "Initech", license: "Open Source", logo: "gamma" },
    "gemini-3.1-pro": { name: "Gemini 3.1 Pro", provider: "Google",  license: "Proprietary", logo: "gemini" }
};

/** @type {Record<string, {name: string, type: "cli"|"api", accent: string, logo: string}>} */
export const HARNESSES = {
    "gemini-cli": { name: "Gemini CLI", type: "cli", accent: "#0ea5e9", logo: "terminal" },
    "openclaw":   { name: "OpenClaw",   type: "cli", accent: "#f43f5e", logo: "claw" },
    "api-loop":   { name: "API Runner", type: "api", accent: "#8b5cf6", logo: "braces" }
};

// --- raw identity -> curated id ----------------------------------------------

// Map a raw `agentModel` (as set via AGENT_MODEL) to a curated model id. Keys
// are matched case-insensitively as exact strings first, then as substrings, so
// "claude-opus-4-8" and "claude-opus-4-8-20260101" both resolve.
/** @type {Record<string, string>} */
export const MODEL_ALIASES = {
    "alpha-pro": "alpha-pro",
    "beta-sonic": "beta-sonic",
    "gamma-coder": "gamma-coder",
    // Preview shares the stable Gemini 3.1 Pro metadata. The bare key also lets
    // versioned ids (e.g. gemini-3.1-pro-001) resolve via substring matching.
    "gemini-3.1-pro": "gemini-3.1-pro",
    "gemini-3.1-pro-preview": "gemini-3.1-pro"
};

// Map a raw `agentType` (BENCH_AGENT_TYPE, incl. the harness's own aliases
// cli/binary -> gemini) to a curated harness id.
/** @type {Record<string, string>} */
export const HARNESS_ALIASES = {
    "gemini": "gemini-cli",
    "gemini-cli": "gemini-cli",
    "cli": "gemini-cli",
    "binary": "gemini-cli",
    "openclaw": "openclaw",
    "claw": "openclaw",
    "api": "api-loop",
    "api-loop": "api-loop"
};

// --- presentation ------------------------------------------------------------

// One line/bar color per setup, assigned by discovery order in derive(). Same
// palette the mock seed uses, so test and real data look consistent.
export const PALETTE = [
    "#3b82f6", "#1d4ed8", "#10b981", "#059669",
    "#f59e0b", "#d97706", "#8b5cf6", "#ec4899"
];

// Optional per-setup overrides ({ [setupId]: { order?, color? } }) passed to
// derive(). Empty by default — discovery order + PALETTE are used. Fill this to
// pin a stable order/color for specific setups.
/** @type {Record<string, {order?: number, color?: string}>} */
export const SETUP_CATALOG = {};

// --- resolvers ---------------------------------------------------------------

function slugify(value) {
    return String(value || "")
        .toLowerCase()
        .replace(/[^a-z0-9]+/g, "-")
        .replace(/^-+|-+$/g, "");
}

/**
 * Resolve a raw model identity to a curated key plus the metadata to upsert.
 *
 * @param {string|null|undefined} agentModel raw AGENT_MODEL value
 * @param {string|null|undefined} agentProvider raw AGENT_PROVIDER value
 * @returns {{ key: string, meta: object, known: boolean }}
 */
export function resolveModel(agentModel, agentProvider) {
    const raw = String(agentModel || "").trim();
    const lower = raw.toLowerCase();

    // Exact alias, then substring alias.
    let key = MODEL_ALIASES[lower];
    if (!key) {
        for (const [alias, target] of Object.entries(MODEL_ALIASES)) {
            if (lower && lower.includes(alias.toLowerCase())) { key = target; break; }
        }
    }

    if (key && MODELS[key]) return { key, meta: MODELS[key], known: true };

    // Unknown model: keep it visible with a synthesized entry.
    const fallbackKey = key || slugify(raw) || "unknown-model";
    const meta = MODELS[fallbackKey] || {
        name: raw || "Unknown Model",
        provider: String(agentProvider || "").trim() || "Unknown",
        license: "Unknown",
        logo: "alpha"
    };
    return { key: fallbackKey, meta, known: false };
}

/**
 * Resolve a raw harness/agent type to a curated key plus metadata to upsert.
 *
 * @param {string|null|undefined} agentType raw BENCH_AGENT_TYPE value
 * @returns {{ key: string, meta: object, known: boolean }}
 */
export function resolveHarness(agentType) {
    const raw = String(agentType || "").trim();
    const lower = raw.toLowerCase();

    const key = HARNESS_ALIASES[lower];
    if (key && HARNESSES[key]) return { key, meta: HARNESSES[key], known: true };

    const fallbackKey = key || slugify(raw) || "unknown-harness";
    const meta = HARNESSES[fallbackKey] || {
        name: raw || "Unknown Harness",
        // API loops set AGENT_TYPE "api"; everything else is treated as a CLI.
        type: lower === "api" ? "api" : "cli",
        accent: "#64748b",
        logo: "terminal"
    };
    return { key: fallbackKey, meta, known: false };
}

// --- metadata collection -----------------------------------------------------

/**
 * Collect the `models` / `harnesses` metadata docs referenced by a row set.
 *
 * Producer rows carry only the curated `model` / `harness` KEYS, never the
 * display metadata (name/provider/license/logo, type/accent/...). This bridges
 * each referenced key to the metadata to upsert. A key absent from the catalog
 * is NOT dropped — it gets synthesized metadata and is reported via `unknown` so
 * the operator can add a real entry (a missing entry would otherwise make the
 * frontend's dangling-ref filter silently hide the whole setup).
 *
 * @param {{model: string, harness: string}[]} rows
 * @returns {{ models: Map<string,object>, harnesses: Map<string,object>,
 *             unknown: { models: Set<string>, harnesses: Set<string> } }}
 */
export function collectMetadata(rows) {
    const models = new Map();
    const harnesses = new Map();
    const unknown = { models: new Set(), harnesses: new Set() };

    for (const r of rows) {
        if (r.model && !models.has(r.model)) {
            const m = resolveModel(r.model, null);
            models.set(r.model, m.meta);
            if (!m.known) unknown.models.add(r.model);
        }
        if (r.harness && !harnesses.has(r.harness)) {
            const h = resolveHarness(r.harness);
            harnesses.set(r.harness, h.meta);
            if (!h.known) unknown.harnesses.add(r.harness);
        }
    }
    return { models, harnesses, unknown };
}
