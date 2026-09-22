import { describe, it, expect } from "vitest";
import {
    normalizeTaskKey,
    getCommonTaskKeys,
    getMaxTaskCount,
    getScopedSetups
} from "./taskScope.js";

describe("taskScope utilities", () => {
    describe("normalizeTaskKey", () => {
        it("strips -gitops suffix from string keys", () => {
            expect(normalizeTaskKey("b-0011-gitops")).toBe("b-0011");
            expect(normalizeTaskKey("unsafe-rollback-gitops")).toBe("unsafe-rollback");
            expect(normalizeTaskKey("cve-remediation")).toBe("cve-remediation");
        });

        it("extracts and normalizes task key from task objects", () => {
            expect(normalizeTaskKey({ folder: "b-0011-gitops" })).toBe("b-0011");
            expect(normalizeTaskKey({ name: "unsafe-rollback-gitops" })).toBe("unsafe-rollback");
            expect(normalizeTaskKey({ id: "t1" })).toBe("t1");
            expect(normalizeTaskKey(null)).toBe("");
        });
    });

    describe("getCommonTaskKeys", () => {
        it("returns intersection of normalized tasks across all setups", () => {
            const setups = [
                {
                    id: "s1",
                    tasks: [
                        { folder: "b-0011" },
                        { folder: "b-0022b" },
                        { folder: "cve-remediation" }
                    ]
                },
                {
                    id: "s2",
                    tasks: [
                        { folder: "b-0011-gitops" },
                        { folder: "b-0022b-gitops" }
                    ]
                },
                {
                    id: "s3",
                    tasks: [
                        { folder: "b-0011-gitops" }
                    ]
                }
            ];
            expect(getCommonTaskKeys(setups)).toEqual(["b-0011"]);
        });

        it("handles empty or invalid inputs", () => {
            expect(getCommonTaskKeys([])).toEqual([]);
            expect(getCommonTaskKeys([{ id: "s1", tasks: [] }])).toEqual([]);
        });
    });

    describe("getMaxTaskCount", () => {
        it("finds max task count across setups", () => {
            const setups = [
                { id: "s1", tasks: new Array(20).fill({}) },
                { id: "s2", tasks: new Array(2).fill({}) }
            ];
            expect(getMaxTaskCount(setups)).toBe(20);
        });
    });

    describe("getScopedSetups", () => {
        const setups = [
            {
                id: "full-1",
                tasks: [
                    { folder: "b-0011", scores: { composite: 0.9 } },
                    { folder: "b-0022b", scores: { composite: 0.8 } }
                ]
            },
            {
                id: "partial-1",
                tasks: [
                    { folder: "b-0011-gitops", scores: { composite: 0.95 } }
                ]
            }
        ];

        it("filters to full setups when scope is 'full'", () => {
            const full = getScopedSetups(setups, "full", ["b-0011"]);
            expect(full.map(s => s.id)).toEqual(["full-1"]);
            expect(full[0].tasks.length).toBe(2);
        });

        it("includes all setups with common tasks when scope is 'common'", () => {
            const common = getScopedSetups(setups, "common", ["b-0011"]);
            expect(common.map(s => s.id)).toEqual(["full-1", "partial-1"]);
            expect(common[0].tasks.length).toBe(1);
            expect(common[0].tasks[0].folder).toBe("b-0011");
            expect(common[1].tasks.length).toBe(1);
            expect(common[1].tasks[0].folder).toBe("b-0011-gitops");
        });
    });
});
