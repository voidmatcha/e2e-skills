# Poll

A single-page poll with three options (Vim, Emacs, VS Code). `node app.mjs` serves the page at `/` and a JSON API: `GET /api/results` (`{ "options", "votes", "voted" }`; sets a `visitor` cookie on first contact), `POST /api/votes` (`{ "option" }`; 409 once the visitor has voted), and the test seam `POST /api/reset`, which clears all votes and lets every visitor vote again. State lives in memory for the life of the process.

End-to-end tests live in `tests/` and run with `npm run test:e2e` (`playwright test`); the Playwright config starts the app itself.
