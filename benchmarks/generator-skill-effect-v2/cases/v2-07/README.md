# Inbox

A single-page inbox with four seeded messages (three unread). `node app.mjs` serves the page at `/` and a JSON API: `GET /api/messages`, `POST /api/messages/:id/read`, `POST /api/messages/read-all`, and the test seam `POST /api/reset`, which restores the seeded messages and their read state. State lives in memory for the life of the process.

End-to-end tests live in `tests/` and run with `npm run test:e2e` (`playwright test`); the Playwright config starts the app itself.
