# Seat picker

A single-page seat picker: a 3 x 4 grid of seats (A1 to C4), three of them already taken, a legend, a selection line and a Reserve button. `node app.mjs` serves the page at `/` and a JSON API: `GET /api/seats` (`{ "taken" }`), `POST /api/reservations` (`{ "seats": [...] }`, 1 to 4 seats; 409 when a seat is taken), and the test seam `POST /api/reset`, which restores the three seeded taken seats. State lives in memory for the life of the process.

End-to-end tests live in `tests/` and run with `npm run test:e2e` (`playwright test`); the Playwright config starts the app itself.
