# Quick quiz

A single-page three-question quiz shown one question at a time. `node app.mjs` serves the page at `/` and a JSON API: `GET /api/quiz` (`{ "questions", "lastScore" }`; the questions carry no answers), `POST /api/submissions` (`{ "answers": { "q1": "...", ... } }` returning `{ "score", "total" }`), and the test seam `POST /api/reset`, which forgets the last score. The correct answers are Jupiter, Canberra and 6. State lives in memory for the life of the process.

End-to-end tests live in `tests/` and run with `npm run test:e2e` (`playwright test`); the Playwright config starts the app itself.
