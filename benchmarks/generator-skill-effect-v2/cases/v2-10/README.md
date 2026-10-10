# Inventory

A single-page sortable inventory table (six tools; Name, Price, Stock). `node app.mjs` serves the page at `/`; the rows are embedded in the page and also available as `GET /api/inventory`. The chosen sort is mirrored in the URL query (`?sort=price&dir=desc`). There is no server state.

End-to-end tests live in `tests/` and run with `npm run test:e2e` (`playwright test`); the Playwright config starts the app itself.
