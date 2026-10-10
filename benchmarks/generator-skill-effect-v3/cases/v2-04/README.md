# Account settings

A single-page settings form with two tabs (Profile: display name, bio; Notifications: email alerts, digest). `node app.mjs` serves the page at `/` and a JSON API: `GET /api/settings`, `PUT /api/settings` (the full settings object; the server replaces what it holds), and the test seam `POST /api/reset`, which restores the defaults (`Ada`, empty bio, alerts off, weekly digest). State lives in memory for the life of the process.

End-to-end tests live in `tests/` and run with `npm run test:e2e` (`playwright test`); the Playwright config starts the app itself.
