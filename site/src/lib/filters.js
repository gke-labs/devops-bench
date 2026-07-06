// Faceted filtering over the setup dimensions. WITHIN a group selected values are
// OR'd; ACROSS groups they are AND'd (standard faceted behavior). An empty group
// means "no filter" for that dimension. Shared by FilterBar (rendering) and
// Leaderboard (filtering + counts) so the two never drift.

import { augmentationLabel } from "./vocab.js";

// Fresh filter state: one empty Set per group.
export function emptyFilterState() {
    return { model: new Set(), harness: new Set(), augmentation: new Set() };
}

// Build the group definitions, with options derived from the LIVE setups so an
// unused dimension value simply doesn't show a chip. Groups expose EITHER
// `valueOf` (single scalar per setup, equality match) OR `valuesOf` (array of
// tokens per setup, intersection match) — never both. See getFilteredSetups.
export function buildFilterGroups(models, harnesses, setups) {
    // Union of augmentation tokens present across setups, sorted so chip order
    // is stable.
    const augTokens = [...new Set(setups.flatMap(s => s.augmentation))].sort();
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
            valuesOf: s => s.augmentation,
            options: augTokens.map(token => ({ value: token, text: augmentationLabel(token) }))
        }
    ];
}

// The setups passing every active facet. A group with `valueOf` matches by
// equality on the scalar; a group with `valuesOf` matches when the setup's
// token array INTERSECTS the selected set (OR within group). An empty group
// selection matches everything.
export function getFilteredSetups(setups, groups, filterState) {
    return setups.filter(setup =>
        groups.every(group => {
            const selected = filterState[group.key];
            if (selected.size === 0) return true;
            if (group.valuesOf) {
                return group.valuesOf(setup).some(v => selected.has(v));
            }
            return selected.has(group.valueOf(setup));
        })
    );
}

export function anyFilterActive(filterState) {
    return Object.values(filterState).some(set => set.size > 0);
}
