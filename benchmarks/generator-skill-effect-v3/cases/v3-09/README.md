# Flashcards

A single-page flashcard app with two seeded decks (Spanish basics, three cards, one already learned; Capitals, two cards) and a study panel. `node app.mjs` serves the page at `/` and a JSON API: `GET /api/decks`, `PATCH /api/cards/:id` (`{ "learned" }`), and the test seam `POST /api/reset`, which restores the seeded decks. State lives in memory for the life of the process.

End-to-end tests live in `tests/` and run with `npm run test:e2e` (`playwright test`); the Playwright config starts the app itself.
