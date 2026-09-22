import { describe, it, expect } from "vitest";
import { render } from "@testing-library/react";

import { BrandLogo, HarnessIcon, BRAND_KEYS, HARNESS_GLYPH_KEYS } from "./Logo.jsx";
import { MODELS, HARNESSES } from "../../ingest/catalog.mjs";

// The catalog and the renderer are two separate tables joined by a bare string
// key, and an unmatched key fails SILENTLY: BrandLogo returns null and
// HarnessIcon renders an empty <svg>. Adding a curated entry without its glyph
// therefore ships a blank icon rather than an error, so the join is asserted
// here instead of being left to a visual check.
describe("catalog logo keys", () => {
    it("has a brand for every curated model", () => {
        for (const [id, meta] of Object.entries(MODELS)) {
            expect(BRAND_KEYS, `model "${id}" uses logo "${meta.logo}"`).toContain(meta.logo);
        }
    });

    it("has a glyph for every curated harness", () => {
        for (const [id, meta] of Object.entries(HARNESSES)) {
            expect(HARNESS_GLYPH_KEYS, `harness "${id}" uses logo "${meta.logo}"`).toContain(meta.logo);
        }
    });
});

describe("BrandLogo", () => {
    it("draws a lettered tile for a mock brand", () => {
        const { container } = render(<BrandLogo logo="alpha" />);
        expect(container.querySelector("rect")).toHaveAttribute("fill", "#64748b");
        const text = container.querySelector("text");
        expect(text).toHaveTextContent("A");
        expect(text).toHaveAttribute("text-anchor", "middle");
        expect(text).toHaveAttribute("dominant-baseline", "central");
    });

    it("draws SVG logo for google, anthropic, and openai", () => {
        const google = render(<BrandLogo logo="google" />);
        expect(google.container.querySelectorAll("path").length).toBe(4);

        const anthropic = render(<BrandLogo logo="anthropic" />);
        expect(anthropic.container.querySelector("path")).toBeTruthy();
        expect(anthropic.container.querySelector("svg")).toHaveAttribute("fill", "currentColor");

        const openai = render(<BrandLogo logo="openai" />);
        expect(openai.container.querySelector("path")).toBeTruthy();
        expect(openai.container.querySelector("svg")).toHaveAttribute("fill", "currentColor");
    });

    it("supports legacy gemini and claude aliases", () => {
        const gemini = render(<BrandLogo logo="gemini" />);
        expect(gemini.container.querySelectorAll("path").length).toBe(4);

        const claude = render(<BrandLogo logo="claude" />);
        expect(claude.container.querySelector("path")).toBeTruthy();
        expect(claude.container.querySelector("svg")).toHaveAttribute("fill", "currentColor");
    });

    it("draws SVG logo for qwen and alibaba", () => {
        const qwen = render(<BrandLogo logo="qwen" />);
        expect(qwen.container.querySelectorAll("path").length).toBe(3);
        expect(qwen.container.querySelector("radialGradient")).toBeTruthy();

        const alibaba = render(<BrandLogo logo="alibaba" />);
        expect(alibaba.container.querySelectorAll("path").length).toBe(3);
    });

    it("renders nothing for an unknown brand", () => {
        const { container } = render(<BrandLogo logo="nope" />);
        expect(container).toBeEmptyDOMElement();
    });
});

describe("HarnessIcon", () => {
    it("tints the glyph with the harness accent", () => {
        const { container } = render(<HarnessIcon harness={HARNESSES["kubeagents"]} />);
        const svg = container.querySelector("svg");
        expect(svg).toHaveAttribute("stroke", "#14b8a6");
        expect(svg.querySelectorAll("path").length).toBeGreaterThan(0);
    });

    it("renders brand logos for antigravity and claude-code", () => {
        const agy = render(<HarnessIcon harness={HARNESSES["antigravity"]} />);
        expect(agy.container.querySelectorAll("path").length).toBe(4);

        const claude = render(<HarnessIcon harness={HARNESSES["claude-code"]} />);
        expect(claude.container.querySelector("path")).toBeTruthy();
        expect(claude.container.querySelector("svg")).toHaveAttribute("fill", "currentColor");
    });
});
