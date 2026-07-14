import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

// React SPA. Vitest config lives here too (jsdom env for component tests).
export default defineConfig({
    // Served from the domain root locally (`/`), but GitHub Pages serves a project
    // repo from a subpath (e.g. `/devops-bench/`). The Pages workflow sets
    // VITE_BASE_PATH so dev/preview stay at `/` while the deployed build is prefixed.
    base: process.env.VITE_BASE_PATH || "/",
    plugins: [react()],
    build: {
        rollupOptions: {
            output: {
                // Split the heavy third-party deps into their own chunks so a code
                // change doesn't bust the vendor cache and the app loads them in
                // parallel. (Avoids the single >500 kB bundle warning.)
                manualChunks: {
                    react: ["react", "react-dom", "react-router-dom"],
                    firebase: ["firebase/app", "firebase/firestore"],
                    charts: ["chart.js", "react-chartjs-2"]
                }
            }
        }
    },
    test: {
        environment: "jsdom",
        globals: true,
        setupFiles: ["./src/test/setup.js"],
        // Include the Node-side seed + ingest tests (mjs) alongside the src tests.
        include: ["src/**/*.test.{js,jsx}", "seed/**/*.test.mjs", "ingest/**/*.test.mjs"]
    }
});
