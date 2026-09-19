// =============================================================================
// Firebase client (modular SDK).
//
// Config comes from Vite env vars (VITE_FIREBASE_*) so the project config isn't
// hardcoded in source — see .env.example. A Firebase web API key is NOT a secret
// (access is enforced by Firestore Security Rules), so these values are safe to
// ship in the client bundle; the env indirection is for config hygiene and
// multi-environment, not secrecy.
//
// Emulator vs real Firestore:
//   - `npm run dev`            → import.meta.env.DEV = true  → emulator
//   - `npm run build`/preview  → import.meta.env.DEV = false → real Firestore
//   - override either way with VITE_USE_EMULATOR=true|false
// =============================================================================

import { initializeApp } from "firebase/app";
import { initializeFirestore, connectFirestoreEmulator } from "firebase/firestore";

const firebaseConfig = {
    apiKey: import.meta.env.VITE_FIREBASE_API_KEY,
    authDomain: import.meta.env.VITE_FIREBASE_AUTH_DOMAIN,
    projectId: import.meta.env.VITE_FIREBASE_PROJECT_ID,
    storageBucket: import.meta.env.VITE_FIREBASE_STORAGE_BUCKET,
    messagingSenderId: import.meta.env.VITE_FIREBASE_MESSAGING_SENDER_ID,
    appId: import.meta.env.VITE_FIREBASE_APP_ID
};

const app = initializeApp(firebaseConfig);

// Force HTTP long-polling: WebChannel streaming connections often fail or time
// out behind corporate proxies and restrictive firewalls.
const settings = { experimentalForceLongPolling: true };

// Optional named database (e.g. "leaderboard"); empty/unset → the (default) DB.
const databaseId = import.meta.env.VITE_FIRESTORE_DATABASE_ID;
export const db = databaseId
    ? initializeFirestore(app, settings, databaseId)
    : initializeFirestore(app, settings);

// Route to the local emulator in dev (or when explicitly toggled).
const useEmulator =
    import.meta.env.VITE_USE_EMULATOR != null
        ? import.meta.env.VITE_USE_EMULATOR === "true"
        : import.meta.env.DEV;

if (useEmulator) {
    connectFirestoreEmulator(db, "127.0.0.1", 8088);
}
