# site/

The leaderboard: a React + Vite app plus a Firestore ingest pipeline in `ingest/`.

Gotchas:

- **Run ingest with Node 22.** It breaks on Node 26 with a "Premature close" error.
- **The Firestore emulator needs Java** and must be started manually before local ingest.
- **Production writes are guarded** — set `ALLOW_PROD_INGEST=true` to write to prod Firestore.

Deeper guide: `../docs/how-to/leaderboard.md`.
