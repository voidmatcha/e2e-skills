# Checkout

A single-page, three-step checkout for a fixed two-item cart (Desk lamp $40.00, Notebook $8.00) with Standard ($5.00) or Express ($15.00) shipping. `node app.mjs` serves the page at `/` and a JSON API: `GET /api/orders`, `POST /api/orders` (`{ "address": { "name", "street", "city" }, "method": "standard" | "express" }`; the city `Failville` makes the payment provider decline with 402), and the test seam `POST /api/reset`, which clears all orders. State lives in memory for the life of the process.

End-to-end tests live in `tests/` and run with `npm run test:e2e` (`playwright test`); the Playwright config starts the app itself.
