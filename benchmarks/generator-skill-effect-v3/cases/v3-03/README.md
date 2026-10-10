# Team roster

A single-page team roster table with five seeded members, a leave toggle and an inline removal confirmation. `node app.mjs` serves the page at `/` and a JSON API: `GET /api/members`, `PATCH /api/members/:id` (`{ "onLeave" }`), `DELETE /api/members/:id`, and the test seam `POST /api/reset`, which restores the seeded roster. State lives in memory for the life of the process.

End-to-end tests live in `tests/` and run with `npm run test:e2e` (`playwright test`); the Playwright config starts the app itself.
