# Outfitters

A small server-rendered storefront: `/` lists three products, `/products/:id` shows one (or a `Product not found` page), and `/wishlist` shows the saved products. Every page's header links to the wishlist with the current count. `node app.mjs` serves the pages and a JSON API: `GET /api/wishlist`, `POST /api/wishlist` (`{ "id" }`), `DELETE /api/wishlist/:id`, and the test seam `POST /api/reset`, which empties the wishlist. State lives in memory for the life of the process.

End-to-end tests live in `tests/` and run with `npm run test:e2e` (`playwright test`); the Playwright config starts the app itself.
