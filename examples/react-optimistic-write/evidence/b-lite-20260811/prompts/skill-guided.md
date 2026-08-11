# B-lite skill-guided generation

Read these frozen inputs in full:

- `app-contract.md`
- `skill-material/SKILL.md`
- `skill-material/code-rules.md`
- `skill-material/verification-rules.md`

Apply the repository's `playwright-test-generator` contract to the single
already-approved scenario below. This is a generation-only experiment: do not
open another approval gate, inspect other files, run the application, install
dependencies, edit the workspace, repair a candidate, or act as the independent
reviewer.

Approved scenario and verification contract:

- Given: fresh disposable server state and an enabled `Like article` button
  with `aria-pressed="false"`.
- When: the user clicks `Like article` once.
- Then / V1: after the normal save settles and the page reloads, the same
  button has `aria-pressed="true"`.
- V3 fault probe: if the browser-originated write is omitted, the unchanged
  post-reload `aria-pressed="true"` primary assertion must fail because fresh
  server truth remains unliked.
- V4 observed write contract: arm request observation before the click and
  prove exactly one `POST /api/like` request with JSON payload
  `{ "liked": true }`; pair that proof with the post-reload V1 outcome.
- Locator map: declare one inline `likeButton` locator using
  `page.getByRole("button", { name: "Like article", exact: true })`.
- Structure: flat `.mjs` spec with exactly one test; no Page Object or control
  file changes.

Return exactly one fenced `javascript` code block containing the complete
`.mjs` Playwright spec. Return no prose before or after the fence.
