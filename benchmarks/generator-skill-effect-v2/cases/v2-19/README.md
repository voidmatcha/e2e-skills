# Profile

A single-page profile editor whose header shows the display name and an initials avatar. `node app.mjs` serves the page at `/` and a JSON API: `GET /api/profile`, `PUT /api/profile` (`{ "displayName" }`, 2 to 30 characters), and the test seam `POST /api/reset`, which restores the name `Ada Lovelace`. State lives in memory for the life of the process.

End-to-end tests live in `tests/` and run with `npm run test:e2e` (`playwright test`); the Playwright config starts the app itself.
