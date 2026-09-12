import { expect, test } from '@playwright/test'
import { PageManager } from './pages/pageManager'

/* The five links the `Main` landmark exposes on `/`, in DOM order. Observed on
 * the live page, not read off the source. */
const MAIN_NAV_LINKS = [
  'Chat',
  'Search',
  'Message history',
  'Playground',
  'Help',
]

test.describe('Application shell', () => {
  test('loads with the primary navigation visible', async ({ page }) => {
    // Given: the application is served at the configured baseURL
    const appLayout = new PageManager(page).onAppLayout()

    // When: a user opens `/`
    await page.goto('/')

    // Then: the shell has loaded. This is also the settled-state gate for the
    // assertion below — the header and the nav landmark paint together, so
    // nothing here observes transitional state.
    await appLayout.expectAppShellLoaded()

    // Then: the primary navigation exposes exactly those five links, in order.
    // Scoped to the landmark on purpose: `/` also renders a separate "Help"
    // button in the chat panel, so an unscoped link or text locator would be a
    // strict-mode hazard.
    await expect(appLayout.mainNavLinks).toHaveText(MAIN_NAV_LINKS)
  })
})
