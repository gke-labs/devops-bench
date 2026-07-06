// Small shared empty / error / not-found states.

import { Link } from "react-router-dom";

export function EmptyState({ onClear }) {
    return (
        <div className="px-6 py-12 flex flex-col items-center justify-center text-center gap-2">
            <svg className="w-8 h-8 text-slate-300" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="1.5" d="M21 21l-6-6m2-5a7 7 0 11-14 0 7 7 0 0114 0z" />
            </svg>
            <p className="text-sm font-medium text-slate-500">No setups match the selected filters.</p>
            <button type="button" onClick={onClear} className="text-xs font-medium text-indigo-600 hover:text-indigo-800 hover:underline">
                Clear all filters
            </button>
        </div>
    );
}

export function LoadError() {
    return (
        <div className="px-6 py-12 flex flex-col items-center justify-center text-center gap-2">
            <p className="text-sm font-medium text-slate-500">Couldn't load benchmark data.</p>
            <p className="text-xs text-slate-400">Is the Firestore emulator running and seeded?</p>
        </div>
    );
}

export function Loading() {
    return (
        <div className="px-6 py-12 flex items-center justify-center text-center">
            <p className="text-sm font-medium text-slate-400">Loading benchmark data…</p>
        </div>
    );
}

export function NotFound({ id }) {
    return (
        <div className="w-full bg-white rounded-2xl border border-slate-200/80 shadow-xl shadow-slate-100 p-10 flex flex-col items-center text-center gap-3">
            <svg className="w-10 h-10 text-slate-300" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="1.5" d="M12 9v2m0 4h.01M21 12a9 9 0 11-18 0 9 9 0 0118 0z" />
            </svg>
            <p className="text-sm font-medium text-slate-600">
                No setup found for <span className="font-mono text-slate-800">{id || "(missing id)"}</span>.
            </p>
            <Link to="/" className="text-xs font-medium text-indigo-600 hover:text-indigo-800 hover:underline">
                Return to the leaderboard
            </Link>
        </div>
    );
}
