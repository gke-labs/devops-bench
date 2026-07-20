// Light/dark theme toggle. Persists the choice (localStorage) and flips the
// `dark` class on <html>; the initial theme is applied in main.jsx before render
// so there's no flash.

import { useState } from "react";
import { getInitialTheme, setTheme } from "../lib/theme.js";

export function ThemeToggle() {
    const [theme, setThemeState] = useState(getInitialTheme);
    const dark = theme === "dark";

    const toggle = () => {
        const next = dark ? "light" : "dark";
        setTheme(next);
        setThemeState(next);
    };

    return (
        <button
            type="button"
            onClick={toggle}
            aria-label={dark ? "Switch to light mode" : "Switch to dark mode"}
            title={dark ? "Light mode" : "Dark mode"}
            className="inline-flex items-center justify-center w-9 h-9 rounded-lg text-slate-500 hover:text-slate-800 hover:bg-slate-100 dark:text-slate-400 dark:hover:text-slate-100 dark:hover:bg-slate-800 transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-indigo-500"
        >
            {dark ? (
                // Sun
                <svg aria-hidden="true" className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                    <circle cx="12" cy="12" r="4" strokeWidth="2" />
                    <path strokeLinecap="round" strokeWidth="2" d="M12 2v2m0 16v2m10-10h-2M4 12H2m15.07-7.07-1.41 1.41M6.34 17.66l-1.41 1.41m12.73 0-1.41-1.41M6.34 6.34 4.93 4.93" />
                </svg>
            ) : (
                // Moon
                <svg aria-hidden="true" className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M21 12.79A9 9 0 1111.21 3 7 7 0 0021 12.79z" />
                </svg>
            )}
        </button>
    );
}
