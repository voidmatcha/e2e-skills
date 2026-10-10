# Reading list

A single-page reading list of 25 articles loaded ten at a time. `node app.mjs` serves the page at `/` and a JSON API: `GET /api/articles?offset=N&limit=10` (`{ "items", "total" }`), `POST /api/articles/:id/read`, `POST /api/articles/:id/unread`, and the test seam `POST /api/reset`, which marks every article unread. State lives in memory for the life of the process.

End-to-end tests live in `tests/` and run with `npm run test:e2e` (`playwright test`); the Playwright config starts the app itself.
