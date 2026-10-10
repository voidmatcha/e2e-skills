# Shop

A single-page shop with a three-product catalog and a cart. `node app.mjs` serves the page at `/` and a JSON API: `GET /api/cart`, `POST /api/cart/items` (`{ "productId" }`), `PATCH /api/cart/items/:id` (`{ "quantity" }`), `DELETE /api/cart/items/:id`, and the test seam `POST /api/reset`, which empties the cart. Cart state lives in memory for the life of the process.

End-to-end tests live in `tests/` and run with `npm run test:e2e` (`playwright test`); the Playwright config starts the app itself.
