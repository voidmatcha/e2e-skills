import { expect, test } from '@playwright/test'

/* Entry-route smoke check. Every other e2e spec assumes the shell on `/`
 * mounted and the tab strip is there to click; when that assumption breaks,
 * those specs fail somewhere further in with a much less obvious message.
 * Navigates via the configured baseURL rather than a hard-coded origin. */
test.describe('Application shell', () => {
  test('loads on / with the primary navigation visible', async ({ page }) => {
    // Given: the app is served at the configured baseURL

    // When: a user opens the default route
    await page.goto('/')

    const mainNavigation = page.getByRole('navigation', { name: 'Main' })
    const navigationLinks = mainNavigation.getByRole('link')
    const appTitle = page.getByRole('banner').getByRole('heading', {
      name: 'Playwright Chat Lab',
      level: 1,
    })
    const messageInput = page.getByRole('textbox', { name: 'Type a message…' })

    // Then: the shell has finished loading and shows its five destinations.
    // The chat pane renders "Loading…" with its controls disabled while the
    // initial message fetch is in flight, so an enabled composer is the
    // shell's settled state — gate on it first and the assertions below read
    // a finished render instead of a half-mounted one.
    await expect(messageInput).toBeEnabled()
    await expect(appTitle).toBeVisible()
    await expect(mainNavigation).toBeVisible()
    await expect(navigationLinks).toHaveText([
      'Chat',
      'Search',
      'Message history',
      'Playground',
      'Help',
    ])

    // `/` resolved to the Chat tab, which proves the router mounted and matched
    // the route — not merely that the markup was served.
    await expect(
      mainNavigation.getByRole('link', { name: 'Chat', exact: true }),
    ).toHaveAttribute('aria-current', 'page')
  })
})
