import { useState } from "react";

export function modeTooltip(mode) {
    if (mode === "converge") return "Converge: polled repeatedly until true within timeout budget";
    if (mode === "assert") return "Assert: evaluated once instantaneously at the end of the run";
    if (mode === "hold") return "Hold: sampled continuously in background — must stay true throughout";
    if (mode === "judge") return "Judge: evaluated by LLM judge against prompt criteria";
    if (mode === "audit") return "Audit: deterministic scan of shell commands and tool calls";
    return mode;
}

export function CheckMeta({
    id,
    role,
    group,
    mode,
    weight,
    isCatastrophic = false,
    defaultExpanded = false
}) {
    const [expanded, setExpanded] = useState(defaultExpanded);

    const pillBase = isCatastrophic
        ? "bg-rose-50/70 dark:bg-rose-950/40 text-rose-700 dark:text-rose-300 border border-rose-200/50 dark:border-rose-900/40"
        : "bg-slate-100/80 dark:bg-slate-800/70 text-slate-600 dark:text-slate-300 border border-slate-200/40 dark:border-slate-700/50";

    const keyLabel = isCatastrophic
        ? "text-rose-400 dark:text-rose-500 font-medium"
        : "text-slate-400 dark:text-slate-500 font-medium";

    const extraItems = [];
    if (id) extraItems.push({ key: "id", value: id });
    if (mode) extraItems.push({ key: "mode", value: mode, isMode: true });
    if (weight != null && weight !== "") {
        extraItems.push({
            key: "weight",
            value: typeof weight === "number" ? `${weight} pts` : weight
        });
    }
    if (group) extraItems.push({ key: "group", value: group });

    let primaryItem = role ? { key: "role", value: role } : null;
    let collapsibles = extraItems;

    if (!primaryItem && collapsibles.length > 0) {
        primaryItem = collapsibles[0];
        collapsibles = collapsibles.slice(1);
    }

    if (!primaryItem && collapsibles.length === 0) return null;

    return (
        <div className="flex flex-wrap items-center gap-1.5 mt-1 font-mono text-[10px]">
            {primaryItem && (
                <span className={`inline-flex items-center gap-1 px-1.5 py-0.5 rounded ${pillBase}`}>
                    <span className={keyLabel}>{primaryItem.key}:</span>
                    <span>{primaryItem.value}</span>
                </span>
            )}

            {expanded && collapsibles.map(item => (
                <span key={item.key} className={`inline-flex items-center gap-1 px-1.5 py-0.5 rounded ${pillBase}`}>
                    <span className={keyLabel}>{item.key}:</span>
                    {item.isMode ? (
                        <span
                            className="cursor-help"
                            title={modeTooltip(item.value)}
                        >
                            {item.value}
                        </span>
                    ) : (
                        <span>{item.value}</span>
                    )}
                </span>
            ))}

            {collapsibles.length > 0 && (
                <button
                    type="button"
                    onClick={() => setExpanded(!expanded)}
                    className="inline-flex items-center gap-0.5 px-1.5 py-0.5 rounded text-[10px] font-mono text-slate-400 dark:text-slate-500 hover:text-indigo-600 dark:hover:text-indigo-400 hover:bg-slate-100 dark:hover:bg-slate-800/80 transition-colors cursor-pointer border border-dashed border-slate-300 dark:border-slate-700"
                    title={expanded ? "Collapse details" : `Show ${collapsibles.map(it => it.key).join(", ")}`}
                    aria-label={expanded ? "Collapse details" : `Show ${collapsibles.map(it => it.key).join(", ")}`}
                >
                    {expanded ? "− less" : `+${collapsibles.length} more`}
                </button>
            )}
        </div>
    );
}
