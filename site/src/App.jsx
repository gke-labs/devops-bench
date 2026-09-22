import { useEffect, useRef } from "react";
import { BrowserRouter, HashRouter, Routes, Route, Navigate, useLocation } from "react-router-dom";
import { BenchmarkProvider } from "./context/BenchmarkContext.jsx";
import { Leaderboard } from "./pages/Leaderboard.jsx";
import { Detail } from "./pages/Detail.jsx";
import { Tasks } from "./pages/Tasks.jsx";
import { TaskDetail } from "./pages/TaskDetail.jsx";
import { RunDetail } from "./pages/RunDetail.jsx";
import { TopBar } from "./components/TopBar.jsx";

// Resets scroll position to top whenever navigating to a new page or task,
// while preserving in-page scroll when inspecting runs on the matrix.
export function ScrollToTop() {
    const { pathname } = useLocation();
    const prevBaseRef = useRef("");

    useEffect(() => {
        const baseRoute = pathname.replace(/\/run\/[^/]+$/, "");
        if (prevBaseRef.current !== baseRoute) {
            prevBaseRef.current = baseRoute;
            if (typeof window.scrollTo === "function") {
                window.scrollTo(0, 0);
            }
        }
    }, [pathname]);

    return null;
}

// A demo build is published to a static host with no rewrite rules, where
// /setup/:id is a path the host has no file for and answers 404 before the app
// ever loads. A hash route is never sent to the server, so a link to one setup
// survives being pasted to a colleague. Everywhere else keeps clean paths.
const demo = import.meta.env.VITE_DEMO_DATA === "true";
const Router = demo ? HashRouter : BrowserRouter;

export default function App() {
    return (
        <Router
            basename={demo ? undefined : import.meta.env.BASE_URL.replace(/\/$/, "")}
            future={{ v7_startTransition: true, v7_relativeSplatPath: true }}
        >
            <ScrollToTop />
            <BenchmarkProvider>
                <div className="relative min-h-screen flex flex-col justify-start items-center bg-slate-50 text-slate-900 dark:bg-slate-950 dark:text-slate-100 transition-colors">
                    <TopBar />
                    <div className="w-full flex-1 flex flex-col items-center p-4 sm:p-8">
                        <Routes>
                            <Route path="/" element={<Leaderboard />} />
                            <Route path="/tasks" element={<Tasks />} />
                            <Route path="/task" element={<Navigate to="/tasks" replace />} />
                            <Route path="/setup/:id" element={<Detail />} />
                            <Route path="/task/:taskName" element={<TaskDetail />} />
                            <Route path="/task/:taskName/run/:setupId" element={<TaskDetail />} />
                        </Routes>
                    </div>
                </div>
            </BenchmarkProvider>
        </Router>
    );
}
