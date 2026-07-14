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

    it("synthesizes an unknown harness as a cli-typed entry", () => {
        const r = resolveHarness("mystery-runner");
        expect(r.known).toBe(false);
        expect(r.key).toBe("mystery-runner");
        expect(r.meta.type).toBe("cli");
    });
});
