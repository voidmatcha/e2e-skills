# Order tracking

A single-page order tracking view with a five-step timeline (Ordered, Packed, Shipped, Out for delivery, Delivered), a Cancel order button and a development seam button that advances the order. `node app.mjs` serves the page at `/` and a JSON API: `GET /api/order` (`{ "step", "cancelled" }`), `POST /api/dev/advance`, `POST /api/order/cancel` (409 from the Shipped step on), and the test seam `POST /api/reset`, which puts the order back at step 1. State lives in memory for the life of the process.

End-to-end tests live in `tests/` and run with `npm run test:e2e` (`playwright test`); the Playwright config starts the app itself.
