# Address book

A single-page address book with dependent Country and Region selects, per-country postal code checks, and a default address. `node app.mjs` serves the page at `/` and a JSON API: `GET /api/addresses`, `POST /api/addresses` (`{ "country": "CA" | "DE" | "US", "region", "postal" }`; the first saved address becomes the default), `POST /api/addresses/:id/default`, and the test seam `POST /api/reset`, which deletes every address. State lives in memory for the life of the process.

End-to-end tests live in `tests/` and run with `npm run test:e2e` (`playwright test`); the Playwright config starts the app itself.
