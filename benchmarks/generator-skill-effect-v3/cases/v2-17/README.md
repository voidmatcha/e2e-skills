# Notes with Trash

A single-page notes list with a Trash view, seeded with three notes and one already-trashed note. `node app.mjs` serves the page at `/` and a JSON API: `GET /api/notes` (each note has a `trashed` flag), `POST /api/notes/:id/trash`, `POST /api/notes/:id/restore`, `POST /api/trash/empty` (permanent), and the test seam `POST /api/reset`, which restores the seeded notes. Empty trash asks for confirmation with the browser's `confirm` dialog. State lives in memory for the life of the process.

End-to-end tests live in `tests/` and run with `npm run test:e2e` (`playwright test`); the Playwright config starts the app itself.
