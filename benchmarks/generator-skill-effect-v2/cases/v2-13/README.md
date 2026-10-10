# Sprint board

A single-page kanban board with three columns (Todo, In progress, Done) and seven seeded cards. Cards move by drag and drop or with each card's Move menu. `node app.mjs` serves the page at `/` and a JSON API: `GET /api/cards`, `POST /api/cards/:id/move` (`{ "column" }`; 409 when the target column is at its limit), and the test seam `POST /api/reset`, which restores the seeded board. State lives in memory for the life of the process.

End-to-end tests live in `tests/` and run with `npm run test:e2e` (`playwright test`); the Playwright config starts the app itself.
