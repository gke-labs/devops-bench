// Provides the loaded benchmark data ({ models, harnesses, setups, loading,
// error }) to the whole tree so pages and nested components (which pass
// models/harnesses into accessors like setupLabel) don't prop-drill it.

import { createContext, useContext } from "react";
import { useBenchmarkData } from "../hooks/useBenchmarkData.js";

const BenchmarkContext = createContext(null);

export function BenchmarkProvider({ children }) {
    const value = useBenchmarkData();
    return <BenchmarkContext.Provider value={value}>{children}</BenchmarkContext.Provider>;
}

export function useBenchmark() {
    const ctx = useContext(BenchmarkContext);
    if (ctx === null) throw new Error("useBenchmark must be used within a BenchmarkProvider");
    return ctx;
}
