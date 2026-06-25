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

function setup(id, model, harness, augmentation, mcp) {
    return { id, model, harness, augmentation, mcp };
}

// A small spread across every dimension.
const setups = [
    setup("s1", "alpha-pro", "gemini-cli", "baseline", false),
    setup("s2", "alpha-pro", "openclaw", "gca", true),
    setup("s3", "gamma-coder", "gemini-cli", "gca", true),
    setup("s4", "gamma-coder", "openclaw", "baseline", false)
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
        expect(Object.keys(s).sort()).toEqual(["augmentation", "harness", "mcp", "model"]);
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
    it("produces the four dimensions with correct tiers", () => {
        const g = groups();
        expect(g.map(x => x.key)).toEqual(["model", "harness", "augmentation", "mcp"]);
        expect(g.find(x => x.key === "model").tier).toBe("primary");
        expect(g.find(x => x.key === "harness").tier).toBe("primary");
        expect(g.find(x => x.key === "augmentation").tier).toBe("secondary");
        expect(g.find(x => x.key === "mcp").tier).toBe("secondary");
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

    it("derives augmentation options with display labels", () => {
        const aug = groups().find(g => g.key === "augmentation");
        expect(aug.options).toEqual([
            { value: "baseline", text: "Baseline" },
            { value: "gca", text: "GCA + Skills" }
        ]);
    });

    it("offers both mcp options when setups are mixed", () => {
        const mcp = groups().find(g => g.key === "mcp");
        expect(mcp.options).toEqual([
            { value: "mcp", text: "MCP" },
            { value: "nomcp", text: "No MCP" }
        ]);
    });

    it("offers only the present mcp option when setups are uniform", () => {
        const allMcp = [setup("a", "alpha-pro", "gemini-cli", "gca", true)];
        const g = buildFilterGroups(models, harnesses, allMcp).find(x => x.key === "mcp");
        expect(g.options).toEqual([{ value: "mcp", text: "MCP" }]);
    });

    it("valueOf maps a setup to its dimension value (mcp → mcp/nomcp)", () => {
        const g = groups();
        expect(g.find(x => x.key === "model").valueOf(setups[0])).toBe("alpha-pro");
        expect(g.find(x => x.key === "mcp").valueOf(setups[1])).toBe("mcp");
        expect(g.find(x => x.key === "mcp").valueOf(setups[0])).toBe("nomcp");
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

    it("maps the mcp facet through valueOf", () => {
        const res = getFilteredSetups(setups, groups(), stateWith({ mcp: new Set(["nomcp"]) }));
        expect(res.map(s => s.id)).toEqual(["s1", "s4"]);
    });

    it("returns empty when facets intersect to nothing", () => {
        const res = getFilteredSetups(
            setups,
            groups(),
            stateWith({ model: new Set(["alpha-pro"]), augmentation: new Set(["baseline"]), mcp: new Set(["mcp"]) })
        );
        expect(res).toHaveLength(0); // alpha-pro+baseline is s1, which is nomcp
    });
});

describe("anyFilterActive", () => {
    it("is false for a fresh state", () => {
        expect(anyFilterActive(emptyFilterState())).toBe(false);
    });

    it("is true once any group has a selection", () => {
        expect(anyFilterActive(stateWith({ mcp: new Set(["mcp"]) }))).toBe(true);
    });
});
