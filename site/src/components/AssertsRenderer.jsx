// Renders check assertions with formatted inline code, lists, and highlighted template placeholder pills.

import React from "react";

/**
 * Format inline text: turns `code` into styled monospace spans
 * and {{PLACEHOLDER}} tokens into styled pill badges.
 */
export function FormattedText({ text }) {
    if (!text) return null;

    // Pattern to match either `code` or {{VAR}}
    const parts = [];
    const regex = /(`[^`]+`|\{\{[^}]+\}\})/g;
    let lastIndex = 0;
    let match;

    while ((match = regex.exec(text)) !== null) {
        if (match.index > lastIndex) {
            parts.push({ type: "text", val: text.slice(lastIndex, match.index) });
        }
        const token = match[0];
        if (token.startsWith("{{") && token.endsWith("}}")) {
            parts.push({ type: "template", val: token });
        } else if (token.startsWith("`") && token.endsWith("`")) {
            parts.push({ type: "code", val: token.slice(1, -1) });
        }
        lastIndex = regex.lastIndex;
    }

    if (lastIndex < text.length) {
        parts.push({ type: "text", val: text.slice(lastIndex) });
    }

    return (
        <span>
            {parts.map((part, i) => {
                if (part.type === "template") {
                    return (
                        <span
                            key={i}
                            title="Unexpanded template variable"
                            className="inline-flex items-center px-1.5 py-0.2 mx-0.5 rounded text-[11px] font-mono font-medium bg-amber-50 dark:bg-amber-950/40 text-amber-700 dark:text-amber-300 border border-amber-200 dark:border-amber-800/60"
                        >
                            {part.val}
                        </span>
                    );
                }
                if (part.type === "code") {
                    return (
                        <code
                            key={i}
                            className="px-1 py-0.5 mx-0.5 rounded text-[11px] font-mono bg-slate-100 dark:bg-slate-800 text-slate-800 dark:text-slate-200"
                        >
                            {part.val}
                        </code>
                    );
                }
                return <span key={i}>{part.val}</span>;
            })}
        </span>
    );
}

export function AssertsRenderer({ asserts }) {
    if (!asserts) return <span className="text-slate-400 dark:text-slate-500">—</span>;

    const lines = asserts.split("\n");
    if (lines.length === 1) {
        return (
            <div className="text-xs text-slate-700 dark:text-slate-300 leading-relaxed font-sans">
                <FormattedText text={lines[0]} />
            </div>
        );
    }

    return (
        <div className="text-xs text-slate-700 dark:text-slate-300 space-y-1 leading-relaxed font-sans">
            {lines.map((line, idx) => {
                const indentLevel = (line.match(/^(\s*)/)[1].length) / 4;
                const trimmed = line.trim();
                const isBullet = trimmed.startsWith("- ");
                const content = isBullet ? trimmed.slice(2) : trimmed;

                return (
                    <div
                        key={idx}
                        style={{ paddingLeft: `${indentLevel * 14}px` }}
                        className="flex items-start gap-1.5"
                    >
                        {isBullet && (
                            <span className="text-slate-400 dark:text-slate-500 font-mono select-none">•</span>
                        )}
                        <span className={trimmed.endsWith(":") ? "font-semibold text-slate-900 dark:text-slate-100" : ""}>
                            <FormattedText text={content} />
                        </span>
                    </div>
                );
            })}
        </div>
    );
}
