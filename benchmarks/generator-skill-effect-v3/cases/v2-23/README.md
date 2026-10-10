# Account

A single-page account view with a two-step account-deletion dialog. `node app.mjs` serves the page at `/` and a JSON API: `GET /api/account` (`{ "name", "email", "deleted" }`), `DELETE /api/account`, and the test seam `POST /api/reset`, which restores the account. State lives in memory for the life of the process.

End-to-end tests live in `tests/` and run with `npm run test:e2e` (`playwright test`); the Playwright config starts the app itself.
