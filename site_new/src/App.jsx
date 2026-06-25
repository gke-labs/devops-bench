// App shell: providers, routing, and the page layout wrapper.

import { BrowserRouter, Routes, Route } from "react-router-dom";
import { BenchmarkProvider } from "./context/BenchmarkContext.jsx";
import { Leaderboard } from "./pages/Leaderboard.jsx";
import { Detail } from "./pages/Detail.jsx";

export default function App() {
    return (
        <BrowserRouter future={{ v7_startTransition: true, v7_relativeSplatPath: true }}>
            <BenchmarkProvider>
                <div className="min-h-screen flex flex-col justify-start items-center p-4 sm:p-8">
                    <Routes>
                        <Route path="/" element={<Leaderboard />} />
                        <Route path="/setup/:id" element={<Detail />} />
                    </Routes>
                </div>
            </BenchmarkProvider>
        </BrowserRouter>
    );
}
