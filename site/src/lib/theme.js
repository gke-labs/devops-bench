// Theme persistence + application. Toggles the `dark` class on <html>, which
// Tailwind's darkMode:"class" keys off. Resolution order: the user's saved
// choice, then the OS preference.
//
// Every localStorage touch is guarded. Safari in private browsing, and any
// profile with site storage blocked by policy, THROW on access rather than
// returning null — and main.jsx calls getInitialTheme() at module scope, before
// the first render. So an unguarded read doesn't degrade to "forgot your theme",
// it takes the module down and the page never paints at all.

/** localStorage key holding the persisted choice; also the `storage` event key. */
export const THEME_KEY = "theme";
const KEY = THEME_KEY;

/** The saved choice, or null when storage is unreadable or holds something else. */
function readStoredTheme() {
    try {
        const saved = localStorage.getItem(KEY);
        return saved === "light" || saved === "dark" ? saved : null;
    } catch {
        return null;
    }
}

/** @returns {"light" | "dark"} */
export function getInitialTheme() {
    const saved = readStoredTheme();
    if (saved) return saved;
    return window.matchMedia?.("(prefers-color-scheme: dark)").matches ? "dark" : "light";
}

/** Apply a theme to the document root (no persistence). */
export function applyTheme(theme) {
    document.documentElement.classList.toggle("dark", theme === "dark");
}

/** Persist + apply a theme. */
export function setTheme(theme) {
    try {
        localStorage.setItem(KEY, theme);
    } catch {
        // Storage blocked or over quota. The choice won't survive a reload, but
        // the click still has to take effect for this session — so fall through
        // to applyTheme rather than returning early.
    }
    applyTheme(theme);
}
