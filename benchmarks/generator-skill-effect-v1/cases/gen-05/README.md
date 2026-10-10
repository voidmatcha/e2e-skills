# Preferences

A single-page preferences form (dark mode and language). `node app.mjs` serves the page at `/` and a JSON API: `GET /api/preferences`, `PUT /api/preferences` (`{ "theme": "light" | "dark", "language": "en" | "de" | "fr" }`), and the test seam `POST /api/reset`, which restores the defaults (`light`, `en`). State lives in memory for the life of the process.

End-to-end tests live in `tests/` and run with `npm run test:e2e` (`playwright test`); the Playwright config starts the app itself.
