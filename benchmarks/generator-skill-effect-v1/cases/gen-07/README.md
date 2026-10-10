# Newsletter

A single-page newsletter signup. `node app.mjs` serves the page at `/` and a JSON API: `GET /api/subscribers` (`{ "count", "countLabel" }`), `POST /api/subscribers` (`{ "email" }`; 400 for an invalid address, 409 for a duplicate), and the test seam `POST /api/reset`, which removes every subscriber. State lives in memory for the life of the process.

End-to-end tests live in `tests/` and run with `npm run test:e2e` (`playwright test`); the Playwright config starts the app itself.
