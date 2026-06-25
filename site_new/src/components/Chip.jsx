// Small label chips reused across rows and the detail hero.

import { HARNESS_TYPES } from "../lib/vocab.js";

// A modifier chip (augmentation / MCP) — `cls` carries the full color classes
// from setupTags().
export function Tag({ text, cls, size = "sm" }) {
    const txt = size === "sm" ? "text-[10px]" : "text-[11px]";
    return (
        <span className={`inline-flex items-center px-2 py-0.5 rounded font-medium ${txt} ${cls}`}>
            {text}
        </span>
    );
}

// The harness CLI/API type chip, accent-tinted via inline style.
export function TypeChip({ harness, size = "sm" }) {
    const pad = size === "sm" ? "px-1.5 py-0.5 text-[10px]" : "px-1.5 py-0.5 text-[11px]";
    return (
        <span
            className={`inline-flex items-center rounded font-semibold uppercase tracking-wide ${pad}`}
            style={{ color: harness.accent, backgroundColor: `${harness.accent}1a` }}
        >
            {HARNESS_TYPES[harness.type]}
        </span>
    );
}
