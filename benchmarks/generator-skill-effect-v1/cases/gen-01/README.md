# Guestbook

A single-page guestbook. `node app.mjs` serves the page at `/` and a JSON API: `GET /api/entries`, `POST /api/entries` (`{ "name", "message" }`), and the test seam `POST /api/reset`, which clears every entry. State lives in memory for the life of the process.

End-to-end tests live in `tests/` and run with `npm run test:e2e` (`playwright test`); the Playwright config starts the app itself.
