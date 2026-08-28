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
    it("draws a lettered tile for a known brand", () => {
        const { container } = render(<BrandLogo logo="claude" />);
        expect(container.querySelector("rect")).toHaveAttribute("fill", "#d97757");
        expect(container.querySelector("text")).toHaveTextContent("C");
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
});
