# Products

A single-page product list with a search box. `node app.mjs` serves the page at `/`; the six products are embedded in the page and also available as `GET /api/products`. There is no server state.

End-to-end tests live in `tests/` and run with `npm run test:e2e` (`playwright test`); the Playwright config starts the app itself.
