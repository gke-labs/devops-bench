// =============================================================================
// devops-bench leaderboard — MODEL RATE CARD + PER-ROW COST.
//
// Sources (fetched 2026-09-15):
//   Anthropic — https://platform.claude.com/docs/en/about-claude/pricing
//   Google    — https://ai.google.dev/gemini-api/docs/pricing
//   OpenAi    - https://developers.openai.com/api/docs/pricing
//   Qwen      - https://openrouter.ai/provider/alibaba
// =============================================================================

import { resolveModel } from "./catalog.mjs";

const MTOK = 1e6;

/**
 * @type {Record<string, {input: number, output: number, cacheRead: number, cacheWrite: number}>}
 */
export const MODEL_PRICES = {
    // --- Anthropic
    "claude-opus-5":    { input: 5, output: 25, cacheRead: 0.5, cacheWrite: 6.25 },
    "claude-opus-4-8":  { input: 5, output: 25, cacheRead: 0.5, cacheWrite: 6.25 },
    "claude-sonnet-5":  { input: 2, output: 10, cacheRead: 0.2, cacheWrite: 2.5 },
    "claude-haiku-4-5": { input: 1, output: 5,  cacheRead: 0.1, cacheWrite: 1.25 },
    "claude-fable-5-1": { input: 10, output: 50, cacheRead: 0.25, cacheWrite: 12.5 },
    "claude-fable-5":   { input: 10, output: 50, cacheRead: 1, cacheWrite: 12.5 },

    // --- Google
    // Gemini publishes no separate cache-WRITE rate: creating a cache bills the
    // tokens at the normal input rate (plus per-hour storage the row cannot see).
    "gemini-3.1-pro": { input: 2, output: 12, cacheRead: 0.2, cacheWrite: 2 },
    "gemini-3.5-flash": { input: 0.75, output: 3.75, cacheRead: 0.075, cacheWrite: 0.75 },
    "gemini-3.7-flash": { input: 0.75, output: 3.75, cacheRead: 0.075, cacheWrite: 0.75 },
    "gemini-3.8-flash": { input: 0.75, output: 3.75, cacheRead: 0.075, cacheWrite: 0.75 },

    // --- OpenAI, we use short context as no task has gone over 272k tokens yet
    "gpt-5.6-sol":      { input: 4, output: 20, cacheRead: 0.4, cacheWrite: 5 },

    // --- Alibaba / Qwen
    "qwen3.8-27b-fp8": { input: 0.425, output: 2.55, cacheRead: 0.085, cacheWrite: 0.5313 },

    // --- Fabricated models used by the mock seed
    "alpha-pro":        { input: 5, output: 25, cacheRead: 0.5, cacheWrite: 6.25 },
    "beta-sonic":       { input: 2, output: 10, cacheRead: 0.2, cacheWrite: 2.5 },
    "gamma-coder":      { input: 1, output: 5,  cacheRead: 0.1, cacheWrite: 1.25 }
};

/**
 * The rate card that applies to one row, or null when the model is unpriced.
 *
 * Prices `servedModel` in preference to `model`: `model` is only what the run
 * ASKED for. A request for `sonnet` is served a specific dated Sonnet, and a
 * harness that fails over mid-run answers from a different model entirely — so
 * billing against the requested id can name the wrong rate. `servedModel` is
 * `""` on a harness that does not report it, and comma-joined on the rare
 * failover run; both fall through to `model` rather than guessing.
 *
 * @param {{model?: string, servedModel?: string}} row
 * @returns {{input: number, output: number, cacheRead: number, cacheWrite: number} | null}
 */
export function priceFor(row) {
    const served = String(row?.servedModel || "").trim();
    const raw = served && !served.includes(",") ? served : row?.model;
    const { key } = resolveModel(raw, null);
    return MODEL_PRICES[key] || null;
}

/**
 * USD billed for one row's captured token usage, or null when the model has no
 * rate or the run captured no per-bucket usage.
 *
 * @param {import('../src/lib/schema').ResultRow} row
 * @returns {number | null}
 */
export function costUsd(row) {
    const price = priceFor(row);
    if (!price) return null;
    const billed = [
        [row?.inputTokens, price.input],
        [row?.outputTokens, price.output],
        [row?.cachedTokens, price.cacheRead],
        [row?.cacheWriteTokens, price.cacheWrite],
        [row?.reasoningTokens, price.output]
    ];
    let usd = 0;
    let captured = false;
    for (const [tokens, rate] of billed) {
        if (!Number.isFinite(tokens) || tokens < 0) continue;
        captured = true;
        usd += (tokens * rate) / MTOK;
    }
    return captured ? usd : null;
}

/**
 * Stamp `costUsd` onto every row, returning new row objects (the inputs are the
 * loader's validated rows and are not mutated) plus the set of raw model ids
 * that had no rate, so the caller can warn.
 *
 * @param {import('../src/lib/schema').ResultRow[]} rows
 * @returns {{ rows: import('../src/lib/schema').ResultRow[], unpriced: Set<string> }}
 */
export function stampCost(rows) {
    const unpriced = new Set();
    const stamped = rows.map(row => {
        const usd = costUsd(row);
        if (usd == null && !priceFor(row)) unpriced.add(row.servedModel || row.model);
        return { ...row, costUsd: usd };
    });
    return { rows: stamped, unpriced };
}
