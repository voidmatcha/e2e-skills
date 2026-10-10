# Notification settings

A single page with a "Send test notification" button that shows toast notifications in a live region. `node app.mjs` serves the page at `/` and a JSON API: `POST /api/test-notification` (`{ "sent" }`, a running count) and the test seam `POST /api/reset`, which zeroes the count. Toasts auto-dismiss after two seconds and at most three are shown at once.

End-to-end tests live in `tests/` and run with `npm run test:e2e` (`playwright test`); the Playwright config starts the app itself.
