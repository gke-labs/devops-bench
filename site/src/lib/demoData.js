// The seeded dataset the Firestore emulator is filled with, bundled into the
// build so a preview needs no database at all.
//
// The point of a preview is to review dashboard changes, and the cloud
// `leaderboard-test` DB only carries pass@k — every efficiency and cost section
// would be omitted for want of data. Reusing the seed generator keeps the
// preview showing exactly what `npm run dev` shows locally.

import { models, harnesses, generateRaw, derive } from "../../seed/mock-data.mjs";

/** @returns {import('./schema').BenchmarkData} */
export function demoBenchmarkData() {
    return { models, harnesses, setups: derive(generateRaw()) };
}
