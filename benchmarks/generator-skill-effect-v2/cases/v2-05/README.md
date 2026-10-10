# Appointments

A single-page slot booking: three days, three slots each. `node app.mjs` serves the page at `/` and a JSON API that identifies the visitor by a `guest` cookie: `GET /api/state` (`{ "dates", "slots": [{ "date", "time", "taken", "mine", "id" }], "mine" }`), `POST /api/bookings` (`{ "date", "time" }`; 409 `That slot was just taken` when the slot is already booked), `DELETE /api/bookings/:id` (own bookings only), the seam `POST /api/dev/take` (`{ "date", "time" }`) which books a slot as another visitor, and the test seam `POST /api/reset`, which clears all bookings. State lives in memory for the life of the process.

End-to-end tests live in `tests/` and run with `npm run test:e2e` (`playwright test`); the Playwright config starts the app itself.
