// Model brand logos and harness glyph icons, ported from data.js section 4.
// Model logos are filled squares with a letter; harness icons are line glyphs
// tinted with the harness accent so the runner reads as its own entity class.

const BRANDS = {
    alpha: { fill: "#6366f1", letter: "A" },
    beta: { fill: "#0ea5e9", letter: "B" },
    gamma: { fill: "#f97316", letter: "C" }
};

export function BrandLogo({ logo }) {
    const brand = BRANDS[logo];
    if (!brand) return null;
    return (
        <svg aria-hidden="true" focusable="false" className="w-4 h-4 min-w-[16px]" viewBox="0 0 24 24" fill="none">
            <rect x="2" y="2" width="20" height="20" rx="6" fill={brand.fill} />
            <text x="12" y="16" fill="white" fontSize="12" fontFamily="system-ui, sans-serif" fontWeight="bold" textAnchor="middle">
                {brand.letter}
            </text>
        </svg>
    );
}

const HARNESS_GLYPHS = {
    terminal: <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M7 8l3 3-3 3m5 1h4" />,
    claw: (
        <>
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M4 7l8-4 8 4-8 4-8-4z" />
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M4 12l8 4 8-4M4 17l8 4 8-4" />
        </>
    ),
    braces: <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M8 5c-2 0-2 2-2 3.5S6 12 4 12c2 0 2 2.5 2 4s0 3 2 3m8-14c2 0 2 2 2 3.5S18 12 20 12c-2 0-2 2.5-2 4s0 3-2 3" />
};

export function HarnessIcon({ harness }) {
    return (
        <svg aria-hidden="true" focusable="false" className="w-4 h-4 min-w-[16px]" fill="none" stroke={harness.accent} viewBox="0 0 24 24">
            {HARNESS_GLYPHS[harness.logo] || null}
        </svg>
    );
}
