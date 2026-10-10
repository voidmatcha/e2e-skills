# Portal

A single-page sign-in portal. `node app.mjs` serves the page at `/` and a JSON API: `GET /api/session` (200 with the current user, or 401), `POST /api/session` (`{ "email", "code" }`; sets an `sid` cookie), `DELETE /api/session`, and the test seam `POST /api/reset`, which drops every session. Sessions live in memory for the life of the process.

There is one demo account: email `ada@example.com`, access code `4471`, display name `Ada`.

End-to-end tests live in `tests/` and run with `npm run test:e2e` (`playwright test`); the Playwright config starts the app itself.
