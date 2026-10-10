# Discussion

A single-page comment thread with one level of replies. `node app.mjs` serves the page at `/` and a JSON API: `GET /api/comments`, `POST /api/comments` (`{ "text", "parentId": null | id }`), `PATCH /api/comments/:id` (`{ "text" }`), `DELETE /api/comments/:id` (also removes its replies), and the test seam `POST /api/reset`, which deletes everything. State lives in memory for the life of the process. Deleting asks for confirmation with the browser's `confirm` dialog.

End-to-end tests live in `tests/` and run with `npm run test:e2e` (`playwright test`); the Playwright config starts the app itself.
