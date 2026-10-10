# Release thread

A single-page message thread with four seeded messages (two of them unread), quoted replies, inline editing of the signed-in user's messages (Ada) and a Mark as read control. `node app.mjs` serves the page at `/` and a JSON API: `GET /api/thread` (`{ "messages", "lastReadId" }`), `POST /api/messages` (`{ "text", "quote" }`), `PATCH /api/messages/:id` (`{ "text" }`, own messages only), `POST /api/read`, and the test seam `POST /api/reset`, which restores the seeded thread. State lives in memory for the life of the process.

End-to-end tests live in `tests/` and run with `npm run test:e2e` (`playwright test`); the Playwright config starts the app itself.
