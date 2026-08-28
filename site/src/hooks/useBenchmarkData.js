// Loads the benchmark read-model from Firestore exactly once and exposes it as
// { models, harnesses, setups, loading, error }. Used by the context provider.

import { useEffect, useState } from "react";
import { terminate } from "firebase/firestore";
import { db } from "../lib/firebase.js";
import { loadBenchmarkData } from "../lib/data.js";

export function useBenchmarkData() {
    const [state, setState] = useState({
        models: {},
        harnesses: {},
        setups: [],
        loading: true,
        error: null
    });

    useEffect(() => {
        let cancelled = false;
        // A demo build ships its own dataset and never opens a connection. The
        // import is dynamic so the generator is only fetched by that build.
        const demo = import.meta.env.VITE_DEMO_DATA === "true";
        const load = demo
            ? import("../lib/demoData.js").then(m => m.demoBenchmarkData())
            : loadBenchmarkData(db);
        load
            .then(({ models, harnesses, setups }) => {
                if (!cancelled) setState({ models, harnesses, setups, loading: false, error: null });
                // This dashboard reads once and uses no realtime listeners, so close
                // the Firestore connection to stop its persistent background channel
                // (especially noisy under forced long-polling behind a proxy).
                // Prod-only: in dev, StrictMode double-invokes this effect and would
                // re-read on an already-terminated client.
                if (!demo && import.meta.env.PROD) terminate(db).catch(() => {});
            })
            .catch(err => {
                console.error("Failed to load benchmark data from Firestore:", err);
                if (!cancelled) setState(s => ({ ...s, loading: false, error: err }));
            });
        return () => { cancelled = true; };
    }, []);

    return state;
}
