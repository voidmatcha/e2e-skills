# Library search

A single-page catalog search over twenty book titles. `node app.mjs` serves the page at `/` and a JSON API: `GET /api/search?q=` (`{ "query", "titles", "recent" }`; one- and two-character queries are slow, longer ones fast), `GET /api/recent`, and the test seam `POST /api/reset`, which clears the recent searches. Recent searches live in memory for the life of the process.

End-to-end tests live in `tests/` and run with `npm run test:e2e` (`playwright test`); the Playwright config starts the app itself.
