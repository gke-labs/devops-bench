import { describe, it, expect } from "vitest";

import { resolveModel, resolveHarness, MODELS, HARNESSES } from "./catalog.mjs";

describe("resolveModel", () => {
    it("resolves a known alias to its curated metadata", () => {
        const r = resolveModel("alpha-pro", "Acme");
        expect(r).toEqual({ key: "alpha-pro", meta: MODELS["alpha-pro"], known: true });
    });

    it("resolves by substring (versioned model id)", () => {
        const r = resolveModel("alpha-pro-20260101", "Acme");
        expect(r.key).toBe("alpha-pro");
        expect(r.known).toBe(true);
    });

    // Two Gemini aliases now share a prefix, and the substring pass walks
    // MODEL_ALIASES in insertion order — so a Flash id must not be captured by
    // an earlier Pro alias, and vice versa.
    it("keeps the Gemini families distinct", () => {
        expect(resolveModel("gemini-3.7-flash", "Google").key).toBe("gemini-3.7-flash");
        expect(resolveModel("gemini-3.7-flash-preview", "Google").key).toBe("gemini-3.7-flash");
        expect(resolveModel("gemini-3.1-pro-preview", "Google").key).toBe("gemini-3.1-pro");
    });

    it("resolves the Anthropic and OpenAI ids to curated metadata", () => {
        expect(resolveModel("claude-opus-5", null)).toEqual({
            key: "claude-opus-5", meta: MODELS["claude-opus-5"], known: true
        });
        expect(resolveModel("claude-fable-5", null).key).toBe("claude-fable-5");
        expect(resolveModel("gpt-5.6-sol", null).key).toBe("gpt-5.6-sol");
    });

    // Same insertion-order hazard as the Gemini families: the two Claude ids
    // share a "claude-" prefix, and a dated suffix must not drift onto the
    // sibling. Guards the "no bare vendor key" rule in MODEL_ALIASES.
    it("keeps the Claude families distinct across versioned ids", () => {
        expect(resolveModel("claude-opus-5-20260101", null).key).toBe("claude-opus-5");
        expect(resolveModel("claude-fable-5-20260101", null).key).toBe("claude-fable-5");
    });

    it("synthesizes (never drops) an unknown model, flagged not-known", () => {
        const r = resolveModel("Totally New Model", "NewCo");
        expect(r.known).toBe(false);
        expect(r.key).toBe("totally-new-model");
        expect(r.meta).toMatchObject({ name: "Totally New Model", provider: "NewCo" });
    });
});

describe("resolveHarness", () => {
    it("maps cli/gemini aliases to gemini-cli", () => {
        expect(resolveHarness("gemini").key).toBe("gemini-cli");
        expect(resolveHarness("cli").key).toBe("gemini-cli");
    });

    it("maps api to api-loop", () => {
        const r = resolveHarness("api");
        expect(r).toEqual({ key: "api-loop", meta: HARNESSES["api-loop"], known: true });
    });

    it("maps the antigravity and kubeagents runners to curated entries", () => {
        expect(resolveHarness("antigravity")).toEqual({
            key: "antigravity", meta: HARNESSES["antigravity"], known: true
        });
        // Both spellings land on one line rather than two near-duplicate rows.
        expect(resolveHarness("kubeagents").key).toBe("kubeagents");
        expect(resolveHarness("kube-agents").key).toBe("kubeagents");
    });

    it("synthesizes an unknown harness as a cli-typed entry", () => {
        const r = resolveHarness("mystery-runner");
        expect(r.known).toBe(false);
        expect(r.key).toBe("mystery-runner");
        expect(r.meta.type).toBe("cli");
    });
});
