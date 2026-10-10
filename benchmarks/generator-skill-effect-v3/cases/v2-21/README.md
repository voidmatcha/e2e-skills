# Release notes

A single-page release-notes article with an English/German language switcher. `node app.mjs` serves the page at `/` and a JSON API: `GET /api/language` (`{ "language": "en" | "de" }`), `PUT /api/language`, and the test seam `POST /api/reset`, which restores English. State lives in memory for the life of the process.

End-to-end tests live in `tests/` and run with `npm run test:e2e` (`playwright test`); the Playwright config starts the app itself.
