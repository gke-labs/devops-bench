// Global persistent navigation top bar.
// Contains Leaderboard tab, Tasks tab, contextual backwards tabs, GitHub link, and ThemeToggle.

import { Link, useLocation } from "react-router-dom";
import { ThemeToggle } from "./ThemeToggle.jsx";

export function TopBar() {
    const location = useLocation();
    const pathname = location.pathname;

    const searchParams = new URLSearchParams(location.search);
    const fromSetup = searchParams.get("from") === "setup" || Boolean(location.state?.from && location.state.from.startsWith("/setup"));

    const runMatch = pathname.match(/^\/task\/([^/]+)\/run\/([^/]+)/);
    const taskMatch = !runMatch && pathname.match(/^\/task\/([^/]+)/);
    const setupMatch = pathname.match(/^\/setup\/([^/]+)/);

    const isLeaderboard = pathname === "/" || pathname.startsWith("/setup") || Boolean(runMatch && fromSetup);
    const isTasks = !isLeaderboard && (pathname.startsWith("/tasks") || pathname.startsWith("/task"));

    // Contextual single back button for navigating back to the immediate parent view
    let backButton = null;

    if (runMatch) {
        const taskName = runMatch[1];
        const setupId = runMatch[2];
        if (fromSetup) {
            const metric = searchParams.get("metric");
            const toUrl = location.state?.from || `/setup/${setupId}${metric ? `?metric=${encodeURIComponent(metric)}` : ""}`;
            backButton = { label: "Setup", to: toUrl, title: `Back to setup ${setupId}` };
        } else {
            backButton = { label: "Task", to: `/task/${taskName}`, title: `Back to task ${taskName}` };
        }
    } else if (taskMatch) {
        backButton = { label: "Tasks", to: "/tasks", title: "Back to all tasks" };
    } else if (setupMatch) {
        backButton = { label: "Leaderboard", to: "/", title: "Back to Leaderboard" };
    }

    return (
        <header className="sticky top-0 z-30 w-full border-b border-slate-200/80 dark:border-slate-800 bg-white/85 dark:bg-slate-900/85 backdrop-blur-md transition-colors">
            <div className="max-w-6xl mx-auto px-4 sm:px-8 h-14 flex items-center justify-between gap-4">
                {/* Left: Brand + Navigation & Back Button */}
                <div className="flex items-center gap-2 sm:gap-4 min-w-0">
                    {/* Brand */}
                    <Link
                        to="/"
                        className="flex items-center gap-2 font-bold text-sm tracking-tight text-slate-900 dark:text-slate-100 hover:text-indigo-600 dark:hover:text-indigo-400 transition-colors shrink-0"
                    >
                        <svg className="w-5 h-5 text-indigo-500 shrink-0" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M9 19v-6a2 2 0 00-2-2H5a2 2 0 00-2 2v6a2 2 0 002 2h2a2 2 0 002-2zm0 0V9a2 2 0 012-2h2a2 2 0 012 2v10m-6 0a2 2 0 002 2h2a2 2 0 002-2m0 0V5a2 2 0 012-2h2a2 2 0 012 2v14a2 2 0 01-2 2h-2a2 2 0 01-2-2z" />
                        </svg>
                        <span className="hidden sm:inline">DevOps Bench</span>
                    </Link>

                    {/* Divider */}
                    <span className="text-slate-200 dark:text-slate-800 hidden sm:inline">|</span>

                    {/* Primary Navigation Tabs */}
                    <nav className="flex items-center gap-1 shrink-0">
                        <Link
                            to="/"
                            className={`px-2.5 sm:px-3 py-1.5 rounded-lg text-xs font-semibold transition-colors ${
                                isLeaderboard && pathname === "/"
                                    ? "bg-indigo-50 dark:bg-indigo-950/70 text-indigo-700 dark:text-indigo-300 border border-indigo-200/80 dark:border-indigo-800/80"
                                    : isLeaderboard
                                    ? "text-indigo-600 dark:text-indigo-400 font-semibold hover:bg-slate-100 dark:hover:bg-slate-800/50"
                                    : "text-slate-600 dark:text-slate-400 hover:text-slate-900 dark:hover:text-slate-200 hover:bg-slate-100 dark:hover:bg-slate-800/50"
                            }`}
                        >
                            Leaderboard
                        </Link>
                        <Link
                            to="/tasks"
                            className={`px-2.5 sm:px-3 py-1.5 rounded-lg text-xs font-semibold transition-colors ${
                                isTasks && pathname === "/tasks"
                                    ? "bg-indigo-50 dark:bg-indigo-950/70 text-indigo-700 dark:text-indigo-300 border border-indigo-200/80 dark:border-indigo-800/80"
                                    : isTasks
                                    ? "text-indigo-600 dark:text-indigo-400 font-semibold hover:bg-slate-100 dark:hover:bg-slate-800/50"
                                    : "text-slate-600 dark:text-slate-400 hover:text-slate-900 dark:hover:text-slate-200 hover:bg-slate-100 dark:hover:bg-slate-800/50"
                            }`}
                        >
                            Tasks
                        </Link>
                    </nav>

                    {/* Exactly 1 Back Button */}
                    {backButton && (
                        <div className="flex items-center pl-2 sm:pl-3 border-l border-slate-200 dark:border-slate-800">
                            <Link
                                to={backButton.to}
                                className="inline-flex items-center gap-1.5 px-2.5 py-1 rounded-md text-xs font-medium bg-slate-100/90 dark:bg-slate-800/60 text-slate-600 dark:text-slate-300 hover:text-indigo-600 dark:hover:text-indigo-400 hover:bg-slate-200/70 dark:hover:bg-slate-800 border border-slate-200/60 dark:border-slate-700/60 transition-colors shrink-0"
                                title={backButton.title}
                            >
                                <span className="text-slate-400 dark:text-slate-500">←</span>
                                <span className="truncate max-w-[120px] sm:max-w-[200px] font-mono text-[11px]">{backButton.label}</span>
                            </Link>
                        </div>
                    )}
                </div>

                {/* Right: GitHub Link + ThemeToggle */}
                <div className="flex items-center gap-2 sm:gap-3 shrink-0">
                    <a
                        href="https://github.com/kubernetes-sigs/devops-bench"
                        target="_blank"
                        rel="noopener noreferrer"
                        className="inline-flex items-center gap-1.5 px-2.5 py-1.5 rounded-lg text-xs font-semibold text-slate-600 dark:text-slate-300 hover:text-slate-900 dark:hover:text-white hover:bg-slate-100 dark:hover:bg-slate-800 transition-colors"
                        title="GitHub Repository"
                    >
                        <svg className="w-4 h-4 fill-current" viewBox="0 0 24 24">
                            <path fillRule="evenodd" clipRule="evenodd" d="M12 2C6.477 2 2 6.484 2 12.017c0 4.425 2.865 8.18 6.839 9.504.5.092.682-.217.682-.483 0-.237-.008-.868-.013-1.703-2.782.605-3.369-1.343-3.369-1.343-.454-1.158-1.11-1.466-1.11-1.466-.908-.62.069-.608.069-.608 1.003.07 1.53 1.032 1.53 1.032.892 1.53 2.341 1.088 2.91.832.092-.647.35-1.088.636-1.338-2.22-.253-4.555-1.113-4.555-4.951 0-1.093.39-1.988 1.029-2.688-.103-.253-.446-1.272.098-2.65 0 0 .84-.27 2.75 1.026A9.564 9.564 0 0112 6.844c.85.004 1.705.115 2.504.337 1.909-1.296 2.747-1.027 2.747-1.027.546 1.379.202 2.398.1 2.651.64.7 1.028 1.595 1.028 2.688 0 3.848-2.339 4.695-4.566 4.943.359.309.678.92.678 1.855 0 1.338-.012 2.419-.012 2.747 0 .268.18.58.688.482A10.019 10.019 0 0022 12.017C22 6.484 17.522 2 12 2z" />
                        </svg>
                        <span className="hidden sm:inline">GitHub</span>
                    </a>
                    <ThemeToggle />
                </div>
            </div>
        </header>
    );
}
