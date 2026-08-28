// =============================================================================
// devops-bench leaderboard — MODEL RATE CARD + PER-ROW COST.
//
// Cost is the one leaderboard axis that is not measured. Nothing in the eval
// output says what a run was billed; cost is token usage multiplied by a rate
// card, and the rate card has to come from somewhere. This module is that rate
// card, hand-transcribed from the providers' own pricing pages, plus the
// arithmetic that turns one ResultRow's token buckets into USD.
//
// METHODOLOGY (follows Artificial Analysis' coding-agent cost figures):
//   - every billed bucket is priced separately — non-cached input, cache reads,
//     cache writes, visible output, reasoning;
//   - REASONING TOKENS ARE BILLED AT THE OUTPUT RATE. Providers charge thinking
//     as completion, and the canonical schema breaks it out as a SIBLING of
//     output rather than a subset (see normalize.py), so it has to be priced
//     explicitly or every reasoning model comes out free of charge for its
//     largest bucket;
//   - the dashboard then shows the per-task mean, not the per-run total, so a
//     setup that ran more tasks isn't penalised.
//
// Rates are HARDCODED on purpose. Ingest is a batch job that has to produce the
// same number twice; a live price feed would make a re-ingest of the same rows
// silently disagree with the first one, and the disagreement would look like a
// model got cheaper. Update the table by hand when a price moves.
//
// Cost is stamped onto the row at INGEST (see ingest.mjs), not recomputed at
// derive time, so a past run keeps the rate it was actually billed at even after
// the table is updated.
//
// Sources (fetched 2026-08-26):
//   Anthropic — https://platform.claude.com/docs/en/about-claude/pricing
//   Google    — https://ai.google.dev/gemini-api/docs/pricing
// =============================================================================

import { resolveModel } from "./catalog.mjs";

const MTOK = 1e6;

/**
 * USD per million tokens, keyed by the CURATED model id (see catalog.mjs), not
 * the raw `agentModel` string — one curated id can be reached from several raw
 * spellings (`opus`, `claude-opus-5`, a dated snapshot) and they all bill the
 * same. `cacheRead` / `cacheWrite` are the provider's own cache rates, not a
 * multiplier applied here, so a provider that prices caching differently needs
 * no special case.
 *
 * A model absent from this table is NOT priced at zero — it gets no cost at all
 * (null), and ingest warns. Zero would rank an unpriced setup best on a
 * lower-is-better axis.
 *
 * @type {Record<string, {input: number, output: number, cacheRead: number, cacheWrite: number}>}
 */
export const MODEL_PRICES = {
    // --- Anthropic. 5-minute cache writes (1.25x input); cache hits 0.1x input.
    // Claude 4.6+ includes the full 1M-token context at STANDARD pricing, so
    // `claude-opus-4-8[1m]` bills exactly as `claude-opus-4-8` — the `[1m]` in
    // the run's model id selects a context window, not a rate.
    "claude-opus-5":    { input: 5, output: 25, cacheRead: 0.5, cacheWrite: 6.25 },
    "claude-opus-4-8":  { input: 5, output: 25, cacheRead: 0.5, cacheWrite: 6.25 },
    "claude-sonnet-5":  { input: 2, output: 10, cacheRead: 0.2, cacheWrite: 2.5 },
    "claude-haiku-4-5": { input: 1, output: 5,  cacheRead: 0.1, cacheWrite: 1.25 },

    // --- Google. The ≤200k-prompt tier; Gemini 3.1 Pro charges a premium above
    // 200k input tokens ($4 / $18 / $0.40) that a per-row bucket total cannot
    // detect — the buckets are summed over a whole multi-turn run, so a run of
    // twenty 30k-token calls is indistinguishable from one 600k-token call.
    // Pricing every call at the base tier under-reports the rare long-prompt run
    // rather than over-reporting every short one.
    // Gemini publishes no separate cache-WRITE rate: creating a cache bills the
    // tokens at the normal input rate (plus per-hour storage the row cannot see).
    "gemini-3.1-pro":   { input: 2, output: 12, cacheRead: 0.2, cacheWrite: 2 },
    // Flash has one tier at any prompt length.
    "gemini-3.5-flash": { input: 1.5, output: 9, cacheRead: 0.15, cacheWrite: 1.5 },

    // --- Fabricated models used by the mock seed. Not real rates; they exist so
    // the seeded demo exercises the cost axis at all. Chosen to span a plausible
    // frontier-to-budget spread.
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
 * Deliberately ignores `totalTokens`: a total cannot be priced, because the
 * buckets it collapses are billed at rates that differ by up to 50x. A row that
 * reports only a total is uncosted, not costed at the input rate.
 *
 * @param {import('../src/lib/schema').ResultRow} row
 * @returns {number | null}
 */
export function costUsd(row) {
    const price = priceFor(row);
    if (!price) return null;
    // Reasoning bills at the OUTPUT rate — it is a sibling bucket of output, not
    // a subset of it, so it is added rather than already counted.
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
