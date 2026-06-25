// Faceted filtering over the setup dimensions. WITHIN a group selected values are
// OR'd; ACROSS groups they are AND'd (standard faceted behavior). An empty group
// means "no filter" for that dimension. Shared by FilterBar (rendering) and
// Leaderboard (filtering + counts) so the two never drift.

import { AUGMENTATIONS } from "./vocab.js";

// Fresh filter state: one empty Set per group.
export function emptyFilterState() {
    return { model: new Set(), harness: new Set(), augmentation: new Set(), mcp: new Set() };
}

// Build the group definitions, with options derived from the LIVE setups so an
// unused dimension value simply doesn't show a chip.
export function buildFilterGroups(models, harnesses, setups) {
    return [
        {
            key: "model", label: "Model", tier: "primary",
            valueOf: s => s.model,
            options: Object.keys(models)
                .filter(id => setups.some(s => s.model === id))
                .map(id => ({ value: id, text: models[id].name }))
        },
        {
            key: "harness", label: "Harness", tier: "primary",
            valueOf: s => s.harness,
            options: Object.keys(harnesses)
                .filter(id => setups.some(s => s.harness === id))
                .map(id => ({ value: id, text: harnesses[id].name }))
        },
        {
            key: "augmentation", label: "Augment", tier: "secondary",
            valueOf: s => s.augmentation,
            options: Object.keys(AUGMENTATIONS)
                .filter(a => setups.some(s => s.augmentation === a))
                .map(a => ({ value: a, text: AUGMENTATIONS[a] }))
        },
        {
            key: "mcp", label: "MCP", tier: "secondary",
            valueOf: s => (s.mcp ? "mcp" : "nomcp"),
            options: [
                setups.some(s => s.mcp) ? { value: "mcp", text: "MCP" } : null,
                setups.some(s => !s.mcp) ? { value: "nomcp", text: "No MCP" } : null
            ].filter(Boolean)
        }
    ];
}

// The setups passing every active facet.
export function getFilteredSetups(setups, groups, filterState) {
    return setups.filter(setup =>
        groups.every(group => {
            const selected = filterState[group.key];
            return selected.size === 0 || selected.has(group.valueOf(setup));
        })
    );
}

export function anyFilterActive(filterState) {
    return Object.values(filterState).some(set => set.size > 0);
}
