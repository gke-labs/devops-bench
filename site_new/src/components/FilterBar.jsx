// The two-tier faceted filter bar: primary axes (Model × Harness) on top, then a
// divider, then the secondary modifier facets. Ported from renderFilters /
// renderFilterGroup in app.js.

import { anyFilterActive } from "../lib/filters.js";

function FilterGroup({ group, filterState, onToggle }) {
    if (group.options.length === 0) return null;
    const primary = group.tier === "primary";
    const labelCls = primary
        ? "text-[11px] font-bold tracking-wide uppercase text-slate-600"
        : "text-[10px] font-semibold tracking-wider uppercase text-slate-400";
    const sizeCls = primary ? "px-3 py-1 text-xs" : "px-2.5 py-0.5 text-[11px]";

    return (
        <div className="flex flex-wrap items-center gap-1.5">
            <span className={`${labelCls} w-16 shrink-0`}>{group.label}</span>
            {group.options.map(opt => {
                const active = filterState[group.key].has(opt.value);
                const cls = active
                    ? (primary
                        ? "bg-indigo-600 text-white border-indigo-600 shadow-sm"
                        : "bg-slate-700 text-white border-slate-700 shadow-sm")
                    : "bg-white text-slate-600 border-slate-200 hover:border-slate-300 hover:bg-slate-50";
                return (
                    <button
                        key={opt.value}
                        type="button"
                        onClick={() => onToggle(group.key, opt.value)}
                        aria-pressed={active}
                        className={`${sizeCls} rounded-full border font-medium transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-indigo-500 focus-visible:ring-offset-1 ${cls}`}
                    >
                        {opt.text}
                    </button>
                );
            })}
        </div>
    );
}

export function FilterBar({ groups, filterState, onToggle, onClear, shown, total }) {
    const primary = groups.filter(g => g.tier === "primary");
    const secondary = groups.filter(g => g.tier === "secondary");

    return (
        <div className="px-6 py-4 bg-white border-b border-slate-100 flex flex-col gap-3">
            <div className="flex items-start justify-between gap-4">
                <div className="flex flex-col gap-2 flex-grow">
                    {primary.map(g => <FilterGroup key={g.key} group={g} filterState={filterState} onToggle={onToggle} />)}
                </div>
                <div className="flex items-center gap-3 shrink-0 pt-0.5">
                    <span className="text-[11px] text-slate-400 whitespace-nowrap">{shown} of {total}</span>
                    {anyFilterActive(filterState) && (
                        <button
                            type="button"
                            onClick={onClear}
                            className="text-[11px] font-medium text-indigo-600 hover:text-indigo-800 underline-offset-2 hover:underline focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-indigo-500 rounded"
                        >
                            Clear all
                        </button>
                    )}
                </div>
            </div>
            <div className="flex items-center gap-2 pt-1 mt-1 border-t border-slate-100">
                <span className="text-[9px] font-semibold tracking-wider uppercase text-slate-300 shrink-0">Modifiers</span>
                <div className="flex flex-col sm:flex-row sm:flex-wrap gap-x-4 gap-y-1 flex-grow pl-1">
                    {secondary.map(g => <FilterGroup key={g.key} group={g} filterState={filterState} onToggle={onToggle} />)}
                </div>
            </div>
        </div>
    );
}
