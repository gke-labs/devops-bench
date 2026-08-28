import { describe, it, expect } from "vitest";

import {
    canUseLogScale,
    colorSeries,
    harnessComparisons,
    paretoFrontier,
    placeLabels,
    rankedBars,
    scatterPoints,
    taskValues
} from "./charts.js";

const setup = (id, scores, over = {}) => ({
    id,
    model: "alpha-pro",
    harness: "gemini-cli",
    augmentation: [],
    color: "#3b82f6",
    tasks: [{ folder: "t1", name: "Task 1", scores }],
    history: [],
    ...over
});

describe("scatterPoints", () => {
    it("drops a setup missing either axis rather than pinning it to zero", () => {
        // A setup with no cost data is not a free setup, and plotting it on the
        // axis would put it on the frontier.
        const setups = [
            setup("a", { composite: 80, cost: 0.2 }),
            setup("b", { composite: 90, cost: null }),
            setup("c", { composite: null, cost: 0.1 })
        ];
        expect(scatterPoints(setups, "cost", "composite").map(p => p.setup.id)).toEqual(["a"]);
    });
});

describe("paretoFrontier", () => {
    // Cost is lower-is-better, composite higher-is-better, so the frontier runs
    // up and to the right from the cheapest point.
    const pt = (id, cost, composite) => ({
        x: cost,
        y: composite,
        setup: setup(id, { cost, composite })
    });

    it("keeps only the non-dominated points", () => {
        const points = [
            pt("cheap-weak", 0.1, 60),
            pt("mid", 0.5, 85),
            pt("dominated", 0.6, 80),   // costs more than mid AND scores less
            pt("pricey-best", 2.0, 92)
        ];
        expect(paretoFrontier(points, "cost", "composite").map(p => p.setup.id))
            .toEqual(["cheap-weak", "mid", "pricey-best"]);
    });

    it("reads the better direction from the metric, not from the axis", () => {
        // Same numbers, both axes lower-is-better: now only the bottom-left
        // corner survives.
        const points = [
            { x: 0.1, y: 60, setup: setup("a") },
            { x: 0.5, y: 85, setup: setup("b") },
            { x: 0.05, y: 40, setup: setup("c") }
        ];
        expect(paretoFrontier(points, "cost", "latency").map(p => p.setup.id)).toEqual(["c"]);
    });

    it("keeps exact ties — neither dominates the other", () => {
        // Dropping one would hide a setup that is genuinely as good.
        const points = [pt("a", 0.5, 80), pt("b", 0.5, 80)];
        expect(paretoFrontier(points, "cost", "composite")).toHaveLength(2);
    });

    it("sorts along x so the caller can draw a line through it", () => {
        const points = [pt("z", 2.0, 92), pt("a", 0.1, 60)];
        expect(paretoFrontier(points, "cost", "composite").map(p => p.x)).toEqual([0.1, 2.0]);
    });

    it("returns nothing for no points", () => {
        expect(paretoFrontier([], "cost", "composite")).toEqual([]);
    });
});

describe("colorSeries", () => {
    const models = { "alpha-pro": { name: "Alpha Pro" }, "beta-sonic": { name: "Beta Sonic" } };
    const harnesses = {
        "gemini-cli": { name: "Gemini CLI", accent: "#0ea5e9" },
        "openclaw": { name: "OpenClaw", accent: "#f43f5e" }
    };
    const setups = [
        setup("a", {}, { model: "beta-sonic", harness: "openclaw" }),
        setup("b", {}, { model: "alpha-pro", harness: "gemini-cli" }),
        setup("c", {}, { model: "alpha-pro", harness: "openclaw" })
    ];

    it("groups by model and labels each series", () => {
        const series = colorSeries(setups, "model", models, harnesses);
        expect(series.map(s => s.label)).toEqual(["Alpha Pro", "Beta Sonic"]);
        expect(series[0].setups.map(s => s.id)).toEqual(["b", "c"]);
    });

    it("uses the harness's own brand accent when coloring by harness", () => {
        const series = colorSeries(setups, "harness", models, harnesses);
        expect(series.map(s => [s.key, s.color]))
            .toEqual([["gemini-cli", "#0ea5e9"], ["openclaw", "#f43f5e"]]);
    });

    it("assigns model colors by sorted key, so filtering does not reshuffle them", () => {
        // A legend whose colors change as you tick a filter box is worse than no
        // legend: the same model has to keep the same dot color.
        const all = colorSeries(setups, "model", models, harnesses);
        const filtered = colorSeries(setups.filter(s => s.model === "alpha-pro"), "model", models, harnesses);
        const alphaColor = all.find(s => s.key === "alpha-pro").color;
        expect(filtered[0].color).toBe(alphaColor);
    });

    it("falls back to the raw key when metadata is missing", () => {
        const series = colorSeries([setup("x", {}, { model: "ghost" })], "model", {}, harnesses);
        expect(series[0].label).toBe("ghost");
    });
});

describe("rankedBars", () => {
    const models = { "alpha-pro": { name: "Alpha Pro" }, "beta-sonic": { name: "Beta Sonic" } };
    const harnesses = { "gemini-cli": { name: "Gemini CLI", accent: "#0ea5e9" } };
    const bar = (id, model, scores) => setup(id, scores, { model });

    it("ranks best-first, which is the opposite direction on cost and on score", () => {
        const setups = [
            bar("a", "alpha-pro", { composite: 82, cost: 0.4 }),
            bar("b", "beta-sonic", { composite: 74, cost: 0.1 })
        ];
        expect(rankedBars(setups, "composite", models, harnesses).map(b => b.setup.id)).toEqual(["a", "b"]);
        expect(rankedBars(setups, "cost", models, harnesses).map(b => b.setup.id)).toEqual(["b", "a"]);
    });

    it("drops an unmeasured setup rather than ranking it last", () => {
        // Ranking it last would read as "slowest"; it was never measured.
        const setups = [
            bar("a", "alpha-pro", { cost: 0.4 }),
            bar("b", "beta-sonic", { cost: null })
        ];
        expect(rankedBars(setups, "cost", models, harnesses).map(b => b.setup.id)).toEqual(["a"]);
    });

    it("gives a setup the same color the scatters give it", () => {
        const setups = [
            bar("a", "alpha-pro", { cost: 0.4 }),
            bar("b", "beta-sonic", { cost: 0.1 })
        ];
        const byModel = Object.fromEntries(
            colorSeries(setups, "model", models, harnesses).map(s => [s.key, s.color])
        );
        for (const b of rankedBars(setups, "cost", models, harnesses)) {
            expect(b.color).toBe(byModel[b.setup.model]);
        }
    });

    it("labels each bar with the full setup identity", () => {
        const bars = rankedBars([bar("a", "alpha-pro", { cost: 0.4 })], "cost", models, harnesses);
        expect(bars[0].label).toBe("Alpha Pro × Gemini CLI · Baseline");
    });
});

describe("harnessComparisons", () => {
    const models = { "alpha-pro": { name: "Alpha Pro" }, "beta-sonic": { name: "Beta Sonic" } };
    const harnesses = {
        "gemini-cli": { name: "Gemini CLI", accent: "#0ea5e9" },
        "openclaw": { name: "OpenClaw", accent: "#f43f5e" },
        "api-loop": { name: "API Runner", accent: "#8b5cf6" }
    };
    const arm = (id, model, harness, cost, augmentation = []) =>
        setup(id, { cost }, { model, harness, augmentation });

    it("keeps only models that ran on two or more harnesses", () => {
        // A lone harness has nothing to compare against; drawing it as a single
        // full bar would read as a win over nothing.
        const groups = harnessComparisons([
            arm("a", "alpha-pro", "gemini-cli", 0.21),
            arm("b", "alpha-pro", "openclaw", 0.38),
            arm("c", "beta-sonic", "gemini-cli", 0.11)
        ], "cost", models, harnesses);
        expect(groups.map(g => g.label)).toEqual(["Alpha Pro · Baseline"]);
        expect(groups[0].entries.map(e => e.harness)).toEqual(["gemini-cli", "openclaw"]);
    });

    it("does not compare across augmentations — only the harness may vary", () => {
        // Baseline vs MCP is a different question, and mixing them would credit
        // the harness for a capability it was handed.
        const groups = harnessComparisons([
            arm("a", "alpha-pro", "gemini-cli", 0.21),
            arm("b", "alpha-pro", "openclaw", 0.38, ["mcp"])
        ], "cost", models, harnesses);
        expect(groups).toEqual([]);
    });

    it("groups augmentation regardless of token order", () => {
        const groups = harnessComparisons([
            arm("a", "alpha-pro", "gemini-cli", 0.2, ["mcp", "skills"]),
            arm("b", "alpha-pro", "openclaw", 0.4, ["skills", "mcp"])
        ], "cost", models, harnesses);
        expect(groups.map(g => g.label)).toEqual(["Alpha Pro · MCP · Skills"]);
    });

    it("measures each harness against the best one in its own group", () => {
        const [group] = harnessComparisons([
            arm("a", "alpha-pro", "gemini-cli", 0.2),
            arm("b", "alpha-pro", "openclaw", 0.5)
        ], "cost", models, harnesses);
        expect(group.best).toBe(0.2);
        expect(group.entries.map(e => Math.round(e.pctVsBest))).toEqual([0, 150]);
    });

    it("flips which value is best on a higher-is-better metric", () => {
        // Cache hit rate is the one efficiency axis where more is better, so the
        // best is the maximum and the laggard's percentage is negative.
        const groups = harnessComparisons([
            setup("a", { cacheHitRate: 80 }, { model: "alpha-pro", harness: "gemini-cli" }),
            setup("b", { cacheHitRate: 40 }, { model: "alpha-pro", harness: "openclaw" })
        ], "cacheHitRate", models, harnesses);
        expect(groups[0].best).toBe(80);
        expect(groups[0].entries.map(e => [e.harness, Math.round(e.pctVsBest)]))
            .toEqual([["gemini-cli", 0], ["openclaw", -50]]);
    });

    it("sorts entries best-first and carries the harness brand accent", () => {
        const [group] = harnessComparisons([
            arm("a", "alpha-pro", "openclaw", 0.5),
            arm("b", "alpha-pro", "api-loop", 0.9),
            arm("c", "alpha-pro", "gemini-cli", 0.2)
        ], "cost", models, harnesses);
        expect(group.entries.map(e => e.label)).toEqual(["Gemini CLI", "OpenClaw", "API Runner"]);
        expect(group.entries[0].color).toBe("#0ea5e9");
    });

    it("ignores a harness with no value for the metric", () => {
        // Two harnesses on paper, one measured — still nothing to compare.
        const groups = harnessComparisons([
            arm("a", "alpha-pro", "gemini-cli", 0.2),
            setup("b", { cost: null }, { model: "alpha-pro", harness: "openclaw" })
        ], "cost", models, harnesses);
        expect(groups).toEqual([]);
    });

    it("leaves pctVsBest null when the best value is not positive", () => {
        // A ratio to zero says nothing; reporting it as 0% would claim a tie.
        const [group] = harnessComparisons([
            arm("a", "alpha-pro", "gemini-cli", 0),
            arm("b", "alpha-pro", "openclaw", 0.4)
        ], "cost", models, harnesses);
        expect(group.entries.map(e => e.pctVsBest)).toEqual([null, null]);
    });

    it("ranks the groups by their best harness, not alphabetically", () => {
        // Alphabetical would put Alpha Pro above a model that beats it — the one
        // thing a ranked chart must not do.
        const groups = harnessComparisons([
            arm("a", "alpha-pro", "gemini-cli", 0.40),
            arm("b", "alpha-pro", "openclaw", 0.50),
            arm("c", "beta-sonic", "gemini-cli", 0.10),
            arm("d", "beta-sonic", "openclaw", 0.20)
        ], "cost", models, harnesses);
        expect(groups.map(g => g.label)).toEqual(["Beta Sonic · Baseline", "Alpha Pro · Baseline"]);
    });

    it("falls back to raw keys when catalog metadata is missing", () => {
        const [group] = harnessComparisons([
            arm("a", "ghost", "gemini-cli", 0.2),
            arm("b", "ghost", "phantom", 0.4)
        ], "cost", {}, harnesses);
        expect(group.label).toBe("ghost · Baseline");
        expect(group.entries[1].label).toBe("phantom");
    });
});

describe("taskValues", () => {
    it("returns one entry per measured task, dropping unmeasured ones", () => {
        const s = setup("a", {}, {
            tasks: [
                { folder: "t1", name: "Task 1", scores: { cost: 0.2 } },
                { folder: "t2", name: "Task 2", scores: { cost: null } },
                { folder: "t3", name: "", scores: { cost: 0.4 } }
            ]
        });
        expect(taskValues(s, "cost")).toEqual([
            { value: 0.2, task: "Task 1" },
            { value: 0.4, task: "t3" }   // falls back to the folder when unnamed
        ]);
    });
});

describe("canUseLogScale", () => {
    it("rejects a zero or negative value, which a log axis drops without saying so", () => {
        expect(canUseLogScale([1, 10, 100])).toBe(true);
        expect(canUseLogScale([0, 10])).toBe(false);
        expect(canUseLogScale([-1, 10])).toBe(false);
        expect(canUseLogScale([])).toBe(false);
    });
});

describe("placeLabels", () => {
    const AREA = { left: 0, right: 400, top: 0, bottom: 300 };
    const dot = (x, y, over = {}) => ({ x, y, r: 6, w: 60, h: 12, ...over });
    const box = (spot, d) => ({
        left: spot.x - d.w / 2, right: spot.x + d.w / 2,
        top: spot.y - d.h / 2, bottom: spot.y + d.h / 2
    });
    const overlap = (a, b) => a.left < b.right && b.left < a.right && a.top < b.bottom && b.top < a.bottom;

    it("puts a label beside its dot, clear of the dot itself", () => {
        const dots = [dot(200, 150)];
        const [spot] = placeLabels(dots, AREA);
        expect(spot.y).toBe(150);
        expect(spot.x - 30).toBeGreaterThan(206);
    });

    it("keeps labels off each other when dots sit on top of one another", () => {
        // Two setups can score near-identically; the whole point of labelling
        // every dot is lost if the names land in the same pixels.
        const dots = [dot(200, 150), dot(203, 152), dot(197, 148)];
        const spots = placeLabels(dots, AREA);
        for (let i = 0; i < spots.length; i++) {
            for (let j = i + 1; j < spots.length; j++) {
                expect(overlap(box(spots[i], dots[i]), box(spots[j], dots[j]))).toBe(false);
            }
        }
    });

    it("keeps a label off any other dot, not just off other labels", () => {
        // The default spot for the left dot lands squarely on the right one.
        const dots = [dot(150, 150), dot(200, 150)];
        const spots = placeLabels(dots, AREA);
        for (const spot of spots) {
            for (const d of dots) {
                const hitsDot =
                    Math.abs(d.x - spot.x) < d.w / 2 + d.r && Math.abs(d.y - spot.y) < d.h / 2 + d.r;
                expect(hitsDot).toBe(false);
            }
        }
    });

    it("flips to the inside for a dot against the right edge", () => {
        const dots = [dot(395, 150)];
        const [spot] = placeLabels(dots, AREA);
        expect(spot.x + 30).toBeLessThanOrEqual(AREA.right);
    });

    it("labels every dot even when the plot is too crowded to place them all", () => {
        // A dot with no name is worse than a name that overlaps.
        const dots = Array.from({ length: 40 }, (_, i) => dot(200 + (i % 3), 150 + (i % 2)));
        expect(placeLabels(dots, AREA)).toHaveLength(40);
    });
});
