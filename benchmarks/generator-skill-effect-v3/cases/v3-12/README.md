# Garden planner

A single-page garden planner with four bed cards, each with a plant select, a Water button and a last-watered line; beds not watered for three or more days need water. `node app.mjs` serves the page at `/` and a JSON API: `GET /api/beds`, `PATCH /api/beds/:id` (`{ "plant" }`), `POST /api/beds/:id/water`, and the test seam `POST /api/reset`, which restores the seeded beds (watered 1, 4, 3 and 0 days ago). State lives in memory for the life of the process.

End-to-end tests live in `tests/` and run with `npm run test:e2e` (`playwright test`); the Playwright config starts the app itself.
