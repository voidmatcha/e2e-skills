# Notes

A single-page notes list with inline editing. `node app.mjs` serves the page at `/` and a JSON API: `GET /api/notes`, `POST /api/notes` (`{ "title" }`), `PATCH /api/notes/:id` (`{ "title" }`), `DELETE /api/notes/:id`, and the test seam `POST /api/reset`, which deletes every note. State lives in memory for the life of the process.

End-to-end tests live in `tests/` and run with `npm run test:e2e` (`playwright test`); the Playwright config starts the app itself.
