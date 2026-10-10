# Orders

A single-page order list (eight orders) with a status filter and an order-number search, both mirrored in the URL query (`?status=shipped&q=101`). `node app.mjs` serves the page at `/`; the orders are embedded in the page and also available as `GET /api/orders`. There is no server state.

End-to-end tests live in `tests/` and run with `npm run test:e2e` (`playwright test`); the Playwright config starts the app itself.
