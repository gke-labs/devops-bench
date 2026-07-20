// Theme persistence + application. Toggles the `dark` class on <html>, which
// Tailwind's darkMode:"class" keys off. Resolution order: the user's saved
// choice, then the OS preference.

const KEY = "theme";

/** @returns {"light" | "dark"} */
export function getInitialTheme() {
    const saved = localStorage.getItem(KEY);
    if (saved === "light" || saved === "dark") return saved;
    return window.matchMedia?.("(prefers-color-scheme: dark)").matches ? "dark" : "light";
}

/** Apply a theme to the document root (no persistence). */
export function applyTheme(theme) {
    document.documentElement.classList.toggle("dark", theme === "dark");
}

/** Persist + apply a theme. */
export function setTheme(theme) {
    localStorage.setItem(KEY, theme);
    applyTheme(theme);
}
