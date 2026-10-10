# Passwordless sign-in

A single-page sign-in with one-time codes. `node app.mjs` serves the page at `/` and a JSON API: `POST /api/codes` (`{ "email" }`; issues a six-digit code), the development seam `GET /api/dev/last-code` (`{ "email", "code" }`, the most recently issued code), `POST /api/session` (`{ "email", "code" }`; 401 for a wrong code, 423 once a code has had three wrong attempts, 410 for a code that was already used; sets an `sid` cookie), `GET /api/session`, `DELETE /api/session`, and the test seam `POST /api/reset`, which forgets every code and session. State lives in memory for the life of the process.

End-to-end tests live in `tests/` and run with `npm run test:e2e` (`playwright test`); the Playwright config starts the app itself.
