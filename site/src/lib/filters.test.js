import { describe, it, expect } from "vitest";
import {
    emptyFilterState,
    buildFilterGroups,
    getFilteredSetups,
    anyFilterActive
} from "./filters.js";

// Minimal models/harnesses; "delta-x" is intentionally UNUSED by any setup so we
// can assert option derivation excludes it.
const models = {
    "alpha-pro": { name: "Alpha Pro" },
    "gamma-coder": { name: "Gamma Coder" },
    "delta-x": { name: "Delta X" }
};
const harnesses = {
    "gemini-cli": { name: "Gemini CLI" },
    "openclaw": { name: "OpenClaw" }
};

function setup(id, model, harness, augmentation) {
    return { id, model, harness, augmentation };
}

// A small spread across every dimension. Augmentation is the new string[]:
// s1 baseline, s2 mcp+skills, s3 skills, s4 baseline.
const setups = [
    setup("s1", "alpha-pro", "gemini-cli", []),
    setup("s2", "alpha-pro", "openclaw", ["mcp", "skills"]),
    setup("s3", "gamma-coder", "gemini-cli", ["skills"]),
    setup("s4", "gamma-coder", "openclaw", [])
];

function groups() {
    return buildFilterGroups(models, harnesses, setups);
}

function stateWith(overrides) {
    return { ...emptyFilterState(), ...overrides };
}

describe("emptyFilterState", () => {
    it("has one empty Set per dimension", () => {
        const s = emptyFilterState();
        expect(Object.keys(s).sort()).toEqual(["augmentation", "harness", "model"]);
        for (const set of Object.values(s)) {
            expect(set).toBeInstanceOf(Set);
            expect(set.size).toBe(0);
        }
    });

    it("returns a fresh object each call (no shared Set references)", () => {
        const a = emptyFilterState();
        const b = emptyFilterState();
        a.model.add("alpha-pro");
        expect(b.model.size).toBe(0);
    });
});

describe("buildFilterGroups", () => {
    it("produces the three dimensions with correct tiers", () => {
        const g = groups();
        expect(g.map(x => x.key)).toEqual(["model", "harness", "augmentation"]);
        expect(g.find(x => x.key === "model").tier).toBe("primary");
        expect(g.find(x => x.key === "harness").tier).toBe("primary");
        expect(g.find(x => x.key === "augmentation").tier).toBe("secondary");
    });

    it("derives model options from live setups, excluding unused models", () => {
        const model = groups().find(g => g.key === "model");
        expect(model.options).toEqual([
            { value: "alpha-pro", text: "Alpha Pro" },
            { value: "gamma-coder", text: "Gamma Coder" }
        ]);
        // delta-x exists in `models` but no setup uses it → no chip.
        expect(model.options.some(o => o.value === "delta-x")).toBe(false);
    });

    it("derives augmentation options from the union of tokens across setups", () => {
        const aug = groups().find(g => g.key === "augmentation");
        expect(aug.options).toEqual([
            { value: "mcp", text: "MCP" },
            { value: "skills", text: "Skills" }
        ]);
    });

    it("title-cases unknown augmentation tokens in option labels", () => {
        const withRules = [setup("x", "alpha-pro", "gemini-cli", ["rules"])];
        const aug = buildFilterGroups(models, harnesses, withRules).find(g => g.key === "augmentation");
        expect(aug.options).toEqual([{ value: "rules", text: "Rules" }]);
    });

    it("valueOf maps a setup to its dimension value for scalar groups", () => {
        const g = groups();
        expect(g.find(x => x.key === "model").valueOf(setups[0])).toBe("alpha-pro");
        expect(g.find(x => x.key === "harness").valueOf(setups[1])).toBe("openclaw");
    });

    it("valuesOf returns the augmentation token array for the multi-valued group", () => {
        const aug = groups().find(g => g.key === "augmentation");
        expect(aug.valuesOf(setups[1])).toEqual(["mcp", "skills"]);
        expect(aug.valuesOf(setups[0])).toEqual([]);
    });
});

describe("getFilteredSetups", () => {
    it("returns all setups when no facet is active", () => {
        expect(getFilteredSetups(setups, groups(), emptyFilterState())).toHaveLength(4);
    });

    it("filters by a single facet value", () => {
        const res = getFilteredSetups(setups, groups(), stateWith({ model: new Set(["alpha-pro"]) }));
        expect(res.map(s => s.id)).toEqual(["s1", "s2"]);
    });

    it("ORs values within a group", () => {
        const res = getFilteredSetups(setups, groups(), stateWith({ harness: new Set(["gemini-cli", "openclaw"]) }));
        expect(res).toHaveLength(4); // both harnesses → everything
    });

    it("ANDs across groups", () => {
        const res = getFilteredSetups(
            setups,
            groups(),
            stateWith({ model: new Set(["alpha-pro"]), harness: new Set(["openclaw"]) })
        );
        expect(res.map(s => s.id)).toEqual(["s2"]);
    });

    it("matches a multi-valued group when the setup's token array intersects the selection", () => {
        // Select "mcp" → only s2 carries it.
        const res = getFilteredSetups(setups, groups(), stateWith({ augmentation: new Set(["mcp"]) }));
        expect(res.map(s => s.id)).toEqual(["s2"]);
    });

    it("ORs token selections inside the multi-valued group", () => {
        // Select "skills" OR "mcp" → s2 (both) and s3 (skills) match.
        const res = getFilteredSetups(setups, groups(), stateWith({ augmentation: new Set(["skills", "mcp"]) }));
        expect(res.map(s => s.id)).toEqual(["s2", "s3"]);
    });

    it("returns empty when facets intersect to nothing", () => {
        // alpha-pro setups are s1 (baseline) and s2 (mcp+skills); requiring "skills"
        // narrows to s2, but s2's harness is openclaw, not gemini-cli.
        const res = getFilteredSetups(
            setups,
            groups(),
            stateWith({
                model: new Set(["alpha-pro"]),
                harness: new Set(["gemini-cli"]),
                augmentation: new Set(["skills"])
            })
        );
        expect(res).toHaveLength(0);
    });
});

describe("anyFilterActive", () => {
    it("is false for a fresh state", () => {
        expect(anyFilterActive(emptyFilterState())).toBe(false);
    });

    it("is true once any group has a selection", () => {
        expect(anyFilterActive(stateWith({ augmentation: new Set(["skills"]) }))).toBe(true);
    });
});
