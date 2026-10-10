# Budget envelopes

A single-page budget tracker with three envelope cards (Groceries $120 of $300, Transport $150 of $150, Fun $0 of $100), each with a progress bar, an Add spending input and a Reset envelope button. `node app.mjs` serves the page at `/` and a JSON API: `GET /api/envelopes`, `POST /api/envelopes/:id/spend` (`{ "amount" }`), `POST /api/envelopes/:id/reset`, and the test seam `POST /api/reset`, which restores the seeded envelopes. State lives in memory for the life of the process.

End-to-end tests live in `tests/` and run with `npm run test:e2e` (`playwright test`); the Playwright config starts the app itself.
