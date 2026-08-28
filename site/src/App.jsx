// App shell: providers, routing, and the page layout wrapper.

import { BrowserRouter, HashRouter, Routes, Route } from "react-router-dom";
import { BenchmarkProvider } from "./context/BenchmarkContext.jsx";
import { Leaderboard } from "./pages/Leaderboard.jsx";
import { Detail } from "./pages/Detail.jsx";
import { ThemeToggle } from "./components/ThemeToggle.jsx";

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
            <BenchmarkProvider>
                <div className="relative min-h-screen flex flex-col justify-start items-center p-4 sm:p-8 bg-slate-50 text-slate-900 dark:bg-slate-950 dark:text-slate-100 transition-colors">
                    <div className="absolute top-4 right-4 sm:top-6 sm:right-6 z-20">
                        <ThemeToggle />
                    </div>
                    <Routes>
                        <Route path="/" element={<Leaderboard />} />
                        <Route path="/setup/:id" element={<Detail />} />
                    </Routes>
                </div>
            </BenchmarkProvider>
        </Router>
    );
}
