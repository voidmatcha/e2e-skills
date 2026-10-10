# Editor

A single-page post editor with a server-side autosaved draft (saved about 300 ms after the last keystroke). `node app.mjs` serves the page at `/` and a JSON API: `GET /api/state` (`{ "draft", "posts" }`), `PUT /api/draft` (`{ "title", "body" }`), `DELETE /api/draft`, `POST /api/posts` (publishes the given title and body and clears the draft), and the test seam `POST /api/reset`, which clears the draft and the posts. State lives in memory for the life of the process.

End-to-end tests live in `tests/` and run with `npm run test:e2e` (`playwright test`); the Playwright config starts the app itself.
