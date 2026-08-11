# Frozen application contract

Generate coverage for one disposable local React page. Playwright's existing
configuration supplies the base URL.

- After `page.goto("/")`, an enabled button with accessible name `Like article`
  represents whether the current article is liked through its `aria-pressed`
  attribute.
- Fresh disposable server state starts with `aria-pressed="false"`.
- Clicking the button may show `aria-pressed="true"` optimistically before the
  save has completed.
- A successful like is not merely the optimistic pixels: the application must
  finish saving and a fresh page reload must still show
  `aria-pressed="true"`.
- The normal successful-save status text is `Saved on server.`.
- Use only local/disposable state and user-facing Playwright locators. Do not
  install packages or contact any non-loopback service.

Produce one independent happy-path Playwright test for that contract. The test
must be valid JavaScript in an `.mjs` spec and must use the existing
`@playwright/test` dependency.
