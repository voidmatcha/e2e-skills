# Recipes

A single-page recipe browser with four recipe cards, tag filter chips, a servings stepper and a meal plan toggle per card. `node app.mjs` serves the page at `/` and a JSON API: `GET /api/plan` (`{ "<recipe id>": { "servings", "planned" } }`), `PATCH /api/plan/:id` (`{ "planned" }` and/or `{ "servings" }`), and the test seam `POST /api/reset`, which restores two servings and no planned recipes. State lives in memory for the life of the process.

End-to-end tests live in `tests/` and run with `npm run test:e2e` (`playwright test`); the Playwright config starts the app itself.
