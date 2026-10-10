# Expenses

A single-page expense tracker with inline amount editing. `node app.mjs` serves the page at `/` and a JSON API: `GET /api/expenses`, `POST /api/expenses` (`{ "description", "amount" }`), `PATCH /api/expenses/:id` (`{ "amount" }`), `DELETE /api/expenses/:id`, and the test seam `POST /api/reset`, which deletes every expense. State lives in memory for the life of the process.

End-to-end tests live in `tests/` and run with `npm run test:e2e` (`playwright test`); the Playwright config starts the app itself.
