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

    // A point release is a sibling, not a version suffix: "claude-fable-5-1"
    // contains "claude-fable-5", so without its own exact key the substring pass
    // would label every 5.1 run as 5.
    it("keeps a point release off its base model", () => {
        expect(resolveModel("claude-fable-5-1", null)).toEqual({
            key: "claude-fable-5-1", meta: MODELS["claude-fable-5-1"], known: true
        });
        expect(MODELS["claude-fable-5-1"].name).toBe("Claude Fable 5.1");
        expect(resolveModel("claude-fable-5", null).key).toBe("claude-fable-5");
    });

    // "-high" is a reasoning-effort setting. Both families resolve to the base
    // model's display name, 3.7 via the substring pass and 3.8 via its own key.
    it("folds a -high effort suffix onto the base model's metadata", () => {
        expect(resolveModel("gemini-3.7-flash-high", "Google").key).toBe("gemini-3.7-flash");
        expect(resolveModel("gemini-3.8-flash-high", "Google").meta.name).toBe("Gemini 3.8 Flash");
    });

    it("resolves the Qwen id to curated metadata", () => {
        expect(resolveModel("qwen3.8-27b-fp8", null)).toEqual({
            key: "qwen3.8-27b-fp8", meta: MODELS["qwen3.8-27b-fp8"], known: true
        });
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

    it("maps both Claude Code spellings to one entry", () => {
        expect(resolveHarness("claude_code")).toEqual({
            key: "claude-code", meta: HARNESSES["claude-code"], known: true
        });
        expect(resolveHarness("claude-code").key).toBe("claude-code");
    });

    it("synthesizes an unknown harness as a cli-typed entry", () => {
        const r = resolveHarness("mystery-runner");
        expect(r.known).toBe(false);
        expect(r.key).toBe("mystery-runner");
        expect(r.meta.type).toBe("cli");
    });
});
