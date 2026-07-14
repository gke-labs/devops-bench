// The model × harness pairing block — the co-equal first-class identity shared by
// the leaderboard row and the detail hero. `variant` selects sizing to preserve
// the visual parity of each context ("row" = compact, "hero" = enlarged).

import { BrandLogo, HarnessIcon } from "./Logo.jsx";
import { Tag, TypeChip } from "./Chip.jsx";
import { setupTags } from "../lib/accessors.js";

const VARIANTS = {
    row: {
        modelBox: "p-1 bg-white rounded-md shadow-sm border border-slate-100 flex-shrink-0 group-hover:scale-105 transition-transform",
        harnessBox: "p-1 rounded-md shadow-sm flex-shrink-0 group-hover:scale-105 transition-transform",
        name: "text-slate-900 font-semibold text-sm truncate",
        sub: "text-[10px] text-slate-400 font-normal truncate",
        hair: "w-2.5",
        connector: "w-5 h-5 text-sm group-hover:text-indigo-500 group-hover:ring-indigo-200 transition-colors",
        chipSize: "sm",
        gap: "gap-2"
    },
    hero: {
        modelBox: "p-1.5 bg-white rounded-lg shadow-sm border border-slate-100 flex-shrink-0 scale-125 origin-left",
        harnessBox: "p-1.5 rounded-lg shadow-sm flex-shrink-0 scale-125 origin-left",
        name: "text-slate-900 font-bold text-base sm:text-lg truncate",
        sub: "text-xs text-slate-400 font-normal truncate",
        hair: "w-4",
        connector: "w-6 h-6 text-base",
        chipSize: "md",
        gap: "gap-2.5"
    }
};

export function SetupIdentity({ setup, model, harness, variant = "row" }) {
    const v = VARIANTS[variant];
    const tags = setupTags(setup);

    return (
        <>
            {/* Model entity */}
            <div className={`flex items-center ${v.gap} min-w-0`}>
                <div className={v.modelBox}>
                    <BrandLogo logo={model.logo} />
                </div>
                <div className={`flex flex-col gap-0.5 min-w-0 ${variant === "hero" ? "pl-1" : ""}`}>
                    <span className={v.name}>{model.name}</span>
                    <span className={v.sub}>{model.provider}</span>
                </div>
            </div>

            {/* Pairing connector */}
            <div aria-hidden="true" className="flex items-center justify-center gap-1 px-0.5 sm:px-1 select-none shrink-0">
                <span className={`hidden sm:block h-px bg-gradient-to-r from-transparent to-slate-300 ${v.hair}`}></span>
                <span className={`flex items-center justify-center rounded-md text-slate-400 font-medium leading-none ring-1 ring-slate-200/70 bg-slate-50 ${v.connector}`}>×</span>
                <span className={`hidden sm:block h-px bg-gradient-to-l from-transparent to-slate-300 ${v.hair}`}></span>
            </div>

            {/* Harness entity + config chips */}
            <div className={`flex items-center ${v.gap} min-w-0`}>
                <div
                    className={v.harnessBox}
                    style={{ backgroundColor: `${harness.accent}1a`, border: `1px solid ${harness.accent}33` }}
                >
                    <HarnessIcon harness={harness} />
                </div>
                <div className={`flex flex-col gap-1 min-w-0 ${variant === "hero" ? "pl-1" : ""}`}>
                    <span className={v.name}>{harness.name}</span>
                    <div className="flex flex-wrap items-center gap-1">
                        <TypeChip harness={harness} size={v.chipSize} />
                        {tags.map((tag, i) => <Tag key={i} text={tag.text} cls={tag.cls} size={v.chipSize} />)}
                    </div>
                </div>
            </div>
        </>
    );
}
