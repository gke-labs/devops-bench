// Reactive "is the app in dark mode?" — reads the `dark` class on <html> and
// re-renders the consumer whenever it flips (so canvas-based UI like the
// Chart.js trend chart, which can't use Tailwind `dark:` variants, restyles
// live on toggle).

import { useEffect, useState } from "react";

export function useIsDark() {
    const [isDark, setIsDark] = useState(
        () => document.documentElement.classList.contains("dark")
    );

    useEffect(() => {
        const el = document.documentElement;
        const observer = new MutationObserver(() =>
            setIsDark(el.classList.contains("dark"))
        );
        observer.observe(el, { attributes: true, attributeFilter: ["class"] });
        return () => observer.disconnect();
    }, []);

    return isDark;
}
