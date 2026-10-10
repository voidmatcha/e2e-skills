# Files

A single-page file manager with seven seeded files, row checkboxes, a select-all header checkbox, bulk delete with a browser `confirm` dialog, and an Undo toast. `node app.mjs` serves the page at `/` and a JSON API: `GET /api/files` (each file has a `deleted` flag), `POST /api/files/delete` (`{ "ids" }`), `POST /api/files/restore` (`{ "ids" }`), and the test seam `POST /api/reset`, which restores the seven files. State lives in memory for the life of the process.

End-to-end tests live in `tests/` and run with `npm run test:e2e` (`playwright test`); the Playwright config starts the app itself.
