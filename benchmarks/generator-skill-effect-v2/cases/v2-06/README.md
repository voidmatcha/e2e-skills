# Article tags

A single-page tag editor with chips. `node app.mjs` serves the page at `/` and a JSON API: `GET /api/tags` (`{ "tags" }`), `PUT /api/tags` (`{ "tags": [...] }`, at most five), and the test seam `POST /api/reset`, which clears the saved tags. State lives in memory for the life of the process.

End-to-end tests live in `tests/` and run with `npm run test:e2e` (`playwright test`); the Playwright config starts the app itself.
