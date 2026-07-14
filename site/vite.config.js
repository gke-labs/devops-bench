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
        rolldownOptions: {
            output: {
                // Split the heavy third-party deps into their own chunks so a code
                // change doesn't bust the vendor cache and the app loads them in
                // parallel. (Avoids the single >500 kB bundle warning.)
                // Vite 8's rolldown bundler dropped the manualChunks object form;
                // codeSplitting groups are its replacement.
                codeSplitting: {
                    groups: [
                        {
                            name: "react",
                            test: /[\\/]node_modules[\\/](react|react-dom|react-router|react-router-dom|scheduler|@remix-run)[\\/]/
                        },
                        {
                            name: "firebase",
                            test: /[\\/]node_modules[\\/](firebase|@firebase|idb)[\\/]/
                        },
                        {
                            name: "charts",
                            test: /[\\/]node_modules[\\/](chart\.js|react-chartjs-2|@kurkle)[\\/]/
                        }
                    ]
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
