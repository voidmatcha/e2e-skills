# Survey builder

A single-page survey builder with two seeded questions, nested option lists, question reordering and a preview region. `node app.mjs` serves the page at `/` and a JSON API: `GET /api/questions`, `POST /api/questions/:id/options` (`{ "text" }`), `DELETE /api/questions/:id/options/:index`, `PUT /api/order` (`{ "order": [ids] }`), and the test seam `POST /api/reset`, which restores the seeded survey. State lives in memory for the life of the process.

End-to-end tests live in `tests/` and run with `npm run test:e2e` (`playwright test`); the Playwright config starts the app itself.
