# Task board

A single-page task board with three seeded tasks (Write report, Book flights, Call plumber). `node app.mjs` serves the page at `/` and a JSON API: `GET /api/tasks`, `POST /api/tasks/:id/done`, `POST /api/tasks/:id/undo`, and the test seam `POST /api/reset`, which restores the three seeded tasks as open. State lives in memory for the life of the process.

End-to-end tests live in `tests/` and run with `npm run test:e2e` (`playwright test`); the Playwright config starts the app itself.
