# Records

A single-page paginated list of 23 records (`Record 1` to `Record 23`), ten per page. `node app.mjs` serves the page at `/` and `GET /api/records?page=N` (`{ "page", "pages", "total", "items" }`). There is no server state.

End-to-end tests live in `tests/` and run with `npm run test:e2e` (`playwright test`); the Playwright config starts the app itself.
