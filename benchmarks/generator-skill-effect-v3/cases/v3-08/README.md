# Issues

A single-page issue list with five seeded issues, per-issue priority selects and Assign to me buttons, and filter chips with live counts. The signed-in user is Ada. `node app.mjs` serves the page at `/` and a JSON API: `GET /api/issues`, `PATCH /api/issues/:id` (`{ "assignee" }` and/or `{ "priority" }`), and the test seam `POST /api/reset`, which restores the seeded issues. State lives in memory for the life of the process.

End-to-end tests live in `tests/` and run with `npm run test:e2e` (`playwright test`); the Playwright config starts the app itself.
