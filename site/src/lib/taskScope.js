// @ts-check
// =============================================================================
// Task scope utilities — handles switching between "Full Suite" (setups with all
// tasks completed) and "Common Tasks" (all setups, evaluated strictly on the
// intersection of tasks that every setup ran).
// =============================================================================

/**
 * FEATURE TOGGLE:
 * Set to true to re-enable the Scope filter UI (Full Suite vs Common Tasks)
 * on the Leaderboard and Setup Detail pages.
 * When false, the leaderboard shows only full-suite runs (all 20 tasks),
 * hiding incomplete runs (like kube-agents) and hiding the Scope toggle buttons.
 */
export let ENABLE_SCOPE_FILTER = true;

export function setScopeFilterEnabled(enabled) {
    ENABLE_SCOPE_FILTER = Boolean(enabled);
}

/**
 * @typedef {import('./schema').Setup} Setup
 * @typedef {import('./schema').TaskResult} TaskResult
 */

/**
 * Normalizes a task identifier by stripping '-gitops' suffix.
 * e.g., 'b-0011-gitops' -> 'b-0011', 'unsafe-rollback-gitops' -> 'unsafe-rollback'
 * @param {string | TaskResult | { folder?: string, name?: string, id?: string } | null | undefined} taskOrKey
 * @returns {string}
 */
export function normalizeTaskKey(taskOrKey) {
    if (!taskOrKey) return "";
    const raw = typeof taskOrKey === "string"
        ? taskOrKey
        : (taskOrKey.folder || taskOrKey.name || taskOrKey.id || "");
    return raw.replace(/-gitops$/, "");
}

/**
 * Finds the intersection of normalized task keys across all setups.
 * @param {Setup[]} setups
 * @returns {string[]} Sorted array of common task keys
 */
export function getCommonTaskKeys(setups) {
    if (!setups || setups.length === 0) return [];
    const validSetups = setups.filter(s => Array.isArray(s.tasks) && s.tasks.length > 0);
    if (validSetups.length === 0) return [];

    const sets = validSetups.map(s => new Set(s.tasks.map(normalizeTaskKey)));
    let common = new Set(sets[0]);
    for (const s of sets.slice(1)) {
        common = new Set([...common].filter(k => s.has(k)));
    }
    return [...common].sort();
}

/**
 * Gets the maximum task count present in any single setup.
 * @param {Setup[]} setups
 * @returns {number}
 */
export function getMaxTaskCount(setups) {
    if (!setups || setups.length === 0) return 0;
    return Math.max(0, ...setups.map(s => s.tasks?.length || 0));
}

/**
 * Filters and transforms setups based on the selected task scope:
 * - "full": setups that completed all tasks (tasks.length >= maxTaskCount).
 * - "common": all setups that ran the common tasks, with their tasks list scoped
 *   strictly to the common task intersection and stats recomputed.
 * @param {Setup[]} setups
 * @param {"full" | "common"} scope
 * @param {string[]} commonTaskKeys
 * @returns {Setup[]}
 */
export function getScopedSetups(setups, scope, commonTaskKeys) {
    if (!setups || setups.length === 0) return [];
    if (scope !== "common") {
        const maxCount = getMaxTaskCount(setups);
        return setups.filter(s => (s.tasks?.length || 0) >= maxCount);
    }

    const commonSet = new Set(commonTaskKeys);
    return setups
        .filter(s => {
            const keys = (s.tasks || []).map(normalizeTaskKey);
            return commonTaskKeys.every(k => keys.includes(k));
        })
        .map(s => {
            const scopedTasks = (s.tasks || []).filter(t => commonSet.has(normalizeTaskKey(t)));
            const catastrophicCount = scopedTasks.filter(
                t => t.catastrophic || (t.catastrophicDetails && Object.keys(t.catastrophicDetails).length > 0)
            ).length;
            return {
                ...s,
                tasks: scopedTasks,
                catastrophicCount
            };
        });
}
