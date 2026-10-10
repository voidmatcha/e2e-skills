# Playlist

A single-page playlist editor with four seeded tracks, a Now playing panel, reorder buttons, a Repeat toggle and a running total. `node app.mjs` serves the page at `/` and a JSON API: `GET /api/playlist` (`{ "repeat", "tracks" }`), `PUT /api/order` (`{ "order": [ids] }`), `PATCH /api/repeat` (`{ "repeat" }`), `DELETE /api/tracks/:id`, and the test seam `POST /api/reset`, which restores the seeded playlist. Playback is simulated on the page only. State lives in memory for the life of the process.

End-to-end tests live in `tests/` and run with `npm run test:e2e` (`playwright test`); the Playwright config starts the app itself.
