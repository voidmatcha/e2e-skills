# Checkout coupons

A single-page checkout summary for a fixed two-item cart (subtotal $80.00, shipping $6.00) with a coupon box. `node app.mjs` serves the page at `/` and a JSON API: `GET /api/summary` (`{ "coupon", "subtotal", "discount", "shipping", "total" }`), `POST /api/coupon` (`{ "code" }`; 404 for an unknown code, 410 for an expired one), `DELETE /api/coupon`, and the test seam `POST /api/reset`, which removes any applied coupon. Known codes: `SAVE10`, `FREESHIP`, `EXPIRED1`. State lives in memory for the life of the process.

End-to-end tests live in `tests/` and run with `npm run test:e2e` (`playwright test`); the Playwright config starts the app itself.
