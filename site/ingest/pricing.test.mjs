import { describe, it, expect } from "vitest";

import { MODEL_PRICES, costUsd, priceFor, stampCost } from "./pricing.mjs";

const row = over => ({
    setupId: "s", model: "claude-opus-4-8", harness: "claude", augmentation: [],
    runId: "run_20260101_000000", t: "2026-01-01T00:00:00Z",
    taskFolder: "t", taskName: "T", iteration: 0, status: "success",
    outcomeScore: 1, toolScore: 1, latencySec: 10,
    inputTokens: null, outputTokens: null, validated: true,
    ...over
});

describe("priceFor — which rate card applies", () => {
    it("resolves a raw model id through the catalog aliases", () => {
        expect(priceFor(row({ model: "claude-sonnet-5" }))).toEqual(MODEL_PRICES["claude-sonnet-5"]);
        expect(priceFor(row({ model: "sonnet" }))).toEqual(MODEL_PRICES["claude-sonnet-5"]);
    });

    it("prices the 1M-context variant at the standard rate", () => {
        // Regression: `[1m]` selects a context window, not a pricing tier —
        // Claude 4.6+ includes the full 1M context at standard rates. Treating
        // the suffix as a premium tier would overstate every long-context run.
        expect(priceFor(row({ model: "claude-opus-4-8[1m]" })))
            .toEqual(MODEL_PRICES["claude-opus-4-8"]);
    });

    it("does not let a short alias swallow a longer, more specific one", () => {
        // Regression: "opus" is a substring of "claude-opus-4-8[1m]". Scanning
        // aliases in declaration order resolved that row to the bare `opus`
        // shorthand — the wrong model, and the wrong rate the moment the tiers
        // diverge.
        const opus48 = priceFor(row({ model: "claude-opus-4-8[1m]" }));
        const bareOpus = priceFor(row({ model: "opus" }));
        expect(opus48).toEqual(MODEL_PRICES["claude-opus-4-8"]);
        expect(bareOpus).toEqual(MODEL_PRICES["claude-opus-5"]);
    });

    it("prefers servedModel over the requested model", () => {
        // `model` is only what the run asked for; the harness may have been
        // served something else entirely.
        expect(priceFor(row({ model: "haiku", servedModel: "claude-opus-4-8" })))
            .toEqual(MODEL_PRICES["claude-opus-4-8"]);
    });

    it("falls back to model when servedModel is empty or a failover list", () => {
        expect(priceFor(row({ model: "haiku", servedModel: "" })))
            .toEqual(MODEL_PRICES["claude-haiku-4-5"]);
        // A comma-joined servedModel means the run was answered by more than one
        // model; no single rate is right, so don't pretend one is.
        expect(priceFor(row({ model: "haiku", servedModel: "claude-opus-5,claude-haiku-4-5" })))
            .toEqual(MODEL_PRICES["claude-haiku-4-5"]);
    });

    it("returns null for a model with no rate on file", () => {
        expect(priceFor(row({ model: "some-new-model" }))).toBeNull();
    });
});

describe("costUsd — pricing one row's buckets", () => {
    it("prices each bucket at its own rate", () => {
        const usd = costUsd(row({
            model: "claude-opus-4-8",
            inputTokens: 1_000_000,
            outputTokens: 1_000_000,
            cachedTokens: 1_000_000,
            cacheWriteTokens: 1_000_000
        }));
        // 5 + 25 + 0.5 + 6.25
        expect(usd).toBeCloseTo(36.75, 6);
    });

    it("bills reasoning at the OUTPUT rate, on top of output", () => {
        // Reasoning is a sibling bucket of output, not a subset. Omitting it
        // makes every reasoning model's largest bucket free.
        const withoutReasoning = costUsd(row({ outputTokens: 1_000_000 }));
        const withReasoning = costUsd(row({ outputTokens: 1_000_000, reasoningTokens: 1_000_000 }));
        expect(withoutReasoning).toBeCloseTo(25, 6);
        expect(withReasoning).toBeCloseTo(50, 6);
    });

    it("is null for an unpriced model, never zero", () => {
        // Zero would rank an unpriced setup first on a lower-is-better axis.
        expect(costUsd(row({ model: "some-new-model", inputTokens: 1000 }))).toBeNull();
    });

    it("is null when no bucket was captured", () => {
        expect(costUsd(row({ inputTokens: null, outputTokens: null }))).toBeNull();
    });

    it("ignores totalTokens — a total cannot be priced", () => {
        // The buckets a total collapses are billed at rates that differ by up to
        // 50x, so costing a bare total at any single rate is a fabrication.
        expect(costUsd(row({ totalTokens: 1_000_000 }))).toBeNull();
    });

    it("counts the buckets it has and skips the ones it does not", () => {
        expect(costUsd(row({ inputTokens: 1_000_000, outputTokens: null })))
            .toBeCloseTo(5, 6);
    });
});

describe("stampCost", () => {
    it("stamps costUsd without mutating the input rows", () => {
        const input = [row({ inputTokens: 1_000_000 })];
        const { rows } = stampCost(input);
        expect(rows[0].costUsd).toBeCloseTo(5, 6);
        expect("costUsd" in input[0]).toBe(false);
    });

    it("reports unpriced models so ingest can warn instead of silently zeroing", () => {
        const { rows, unpriced } = stampCost([
            row({ model: "some-new-model", inputTokens: 100 }),
            row({ inputTokens: 100 })
        ]);
        expect(rows[0].costUsd).toBeNull();
        expect(rows[1].costUsd).not.toBeNull();
        expect([...unpriced]).toEqual(["some-new-model"]);
    });

    it("does not report a priced model that merely captured no usage", () => {
        // Missing telemetry is a harness problem; a missing rate is a catalog
        // problem. Conflating them sends the operator to the wrong file.
        const { unpriced } = stampCost([row({ inputTokens: null, outputTokens: null })]);
        expect(unpriced.size).toBe(0);
    });
});
