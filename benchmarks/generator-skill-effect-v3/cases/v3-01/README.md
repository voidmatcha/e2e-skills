# Shopping list

A single-page shopping list with reordering, seeded with three items. `node app.mjs` serves the page at `/` and a JSON API: `GET /api/items`, `POST /api/items` (`{ "name" }`), `PATCH /api/items/:id` (`{ "bought" }`), `PUT /api/order` (`{ "order": [ids] }`), `POST /api/items/clear-bought`, and the test seam `POST /api/reset`, which restores the seeded list. State lives in memory for the life of the process.

End-to-end tests live in `tests/` and run with `npm run test:e2e` (`playwright test`); the Playwright config starts the app itself.
