# Optimistic Like demo

A passing UI-only test does not prove the write.

This small React app updates a Like button optimistically: the heart fills and the count goes up before `POST /api/like` returns. A test that checks only the screen stays green even when the request is never sent. This is the runnable demo behind the talk; it is a demo app, not a product.

## Run

From this directory (Node 20.19+ or 22.12+):

```bash
npm ci
npx playwright install chromium
npm run test:e2e
```

`npm start` serves the app at `http://127.0.0.1:4173`. The server keeps the like in memory. `POST /api/reset` clears it, and `POST /api/fail-next` makes the next `POST /api/like` return HTTP 500.

## Tests

| File | What it checks |
|---|---|
| `tests/like-shows-liked.spec.mjs` | UI only: heart, count, status text. Intentionally weak. |
| `tests/like-sends-post.spec.mjs` | Waits for the `POST /api/like` request, then checks the UI. |
| `tests/like-response.spec.mjs` | Success path: waits for a 200 response, then checks the UI. |
| `tests/like-rejected.spec.mjs` | Rejection path: a 500 response must roll back `aria-pressed` and the count and show an error. |

## Faults

Each script edits only `src/LikeButton.jsx`, is idempotent, and refuses to run if the source does not match what it expects.

- Fault 1, `./break-post.sh`: removes `await postLike()`, so no request is sent.
- Fault 2, `./break.sh`: removes the rejection recovery block, so a failed save is not rolled back.

| State | Expected result |
|---|---|
| Normal | All 4 tests pass. |
| Fault 1 (POST removed) | The UI-only test passes. `like-sends-post` fails waiting for the POST (`page.waitForRequest` timeout). The two response-waiting tests also time out. |
| Fault 2 (recovery removed) | The success-path tests pass. The rollback test fails at `aria-pressed` (expected `false`, received `true`). |

## Restore

```bash
./restore.sh
```

This restores both faults and is safe to run in any state. `./break-post.sh restore` and `./break.sh restore` undo one fault each.
