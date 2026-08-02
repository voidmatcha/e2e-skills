import { expect, test, type Locator, type Page } from '@playwright/test';

class SettingsPage {
  readonly submitButton: Locator;

  constructor(page: Page) {
    this.submitButton = page.getByRole('button', { name: 'Submit settings' });
  }

  async submitWithoutAwait(): Promise<void> {
    this.submitButton.click();
  }
}

function returnDispatchedChange(page: Page): Promise<void> {
  return page.locator('#return-dispatch').dispatchEvent('change');
}

test.describe('missing-await context boundaries', () => {
  test('finds floating promises even inside retry wrappers', async ({ page }) => {
    await page.goto('/settings');

    await expect(async () => {
      expect(page.getByRole('status')).toHaveText('Saved');
      page.getByRole('button', { name: 'Retry save' }).click();
    }).toPass();
  });

  test('finds locator variables and POM properties', async ({ page }) => {
    await page.goto('/settings');
    const saveButton = page.getByRole('button', { name: 'Save' });
    saveButton.click();

    const settings = new SettingsPage(page);
    await settings.submitWithoutAwait();
  });

  test('keeps observed promise arrays outside the missing-await finding', async ({ page }) => {
    await page.goto('/settings');

    await Promise.all([
      page.waitForResponse((response) => response.url().endsWith('/api/settings')),
      page.getByRole('button', { name: 'Save' }).click(),
    ]);

    if (await page.getByRole('dialog').isVisible()) {
      await page.getByRole('button', { name: 'Close' }).click();
    }

    await expect(page.getByRole('status')).toHaveText('Saved');
  });

  test('keeps formatted promise combinators outside the P0 gate', async ({ page }) => {
    await Promise.all([page.waitForResponse((response) => response.url().endsWith('/api/inline')),
      page.locator('#inline-save').click(),
    ]);

    await Promise.all([
      // A comment between the opener and action must not reset the ancestor.
      page.waitForResponse((response) => response.url().endsWith('/api/commented')),
      page.locator('#commented-save').click(),
    ]);

    await Promise.all([
      Promise.all([
        page.waitForResponse((response) => response.url().endsWith('/api/nested')),
      ]),
      page.locator('#nested-save').click(),
    ]);

    await Promise.race([
      page.waitForResponse((response) => response.url().endsWith('/api/race')),
      page.locator('#race-save').click(),
    ]);

    await Promise.all(
      [
        page.locator('#split-all-save').click(),
      ],
    );

    await Promise.race(
      [
        page.locator('#split-race-save').click(),
      ],
    );

    await Promise.all(
      /* Keep these operations concurrent
         to avoid the response race. */
      [
        page.locator('#commented-split-all').click(),
      ],
    );

    await Promise.race(
      /* The first meaningful argument token is still an array. */
      [
        page.locator('#commented-split-race').click(),
      ],
    );
  });

  test('does not leak Promise state into an unrelated later array', async ({ page }) => {
    const requests = [page.waitForResponse('https://example.test/api/ready')];
    await Promise.all(requests);
    const floating = [
      page.locator('#real-floating-action').click(),
    ];
    expect(floating).toHaveLength(1);
  });

  test('covers the complete action surface and multiline receivers', async ({ page }) => {
    page
      .getByRole('button', { name: 'Open details' })
      .dblclick();
    page.locator('#touch-target').tap();
    page.locator('#search').clear();
    page.locator('#search').pressSequentially('query');
    page.locator('#enabled').setChecked(true);
    page.locator('#card').dragTo(page.locator('#column'));
    page.locator('#editable').dispatchEvent('change');
    page.locator('#footer').scrollIntoViewIfNeeded();
    page.locator('#title').selectText();

    const control = page.locator('#variable-control');
    control
      .dblclick();
    control.tap();
    control.clear();
    control.pressSequentially('query');
    control.setChecked(false);
    control.dragTo(page.locator('#variable-target'));
    control.dispatchEvent('input');
    control.scrollIntoViewIfNeeded();
    control.selectText();

    await page
      .locator('#awaited-multiline')
      .tap();
    await control.clear();
    await Promise.all([
      control
        .dispatchEvent('change'),
    ]);
    await returnDispatchedChange(page);
  });

  test('ignores action-shaped tokens in comments and strings', async ({ page }) => {
    page.locator('#comment-token').filter({ hasText: 'ready' })
      /* .click() */;
    page.locator('#string-token').filter({ hasText: 'ready' })
      [".click("];

    await expect(page.locator('#still-real')).toBeVisible();
  });

  test('keeps same-line Promise consumers outside the missing-await finding', async ({ page }) => {
    const preview = page.locator('#preview');
    await Promise.all([page.locator('#all-save').click()]);
    await Promise.race([page.locator('#race-save-inline').click()]);
    await Promise.allSettled([page.locator('#settled-preview').screenshot()]);
    await Promise.any([preview.screenshot()]);
  });

  test('covers Locator screenshot without broadening to every async method', async ({ page }) => {
    page.locator('#floating-preview').screenshot();
    const preview = page.locator('#variable-preview');
    preview.screenshot();
    await page.locator('#awaited-preview').screenshot();
    await preview.screenshot();
  });

  test('detects discouraged direct Page selector actions', async ({ page }) => {
    await page.click('#click');
    await page.dblclick('#dblclick');
    await page.tap('#tap');
    await page.fill('#fill', 'value');
    await page.type('#type', 'value');
    await page.press('#press', 'Enter');
    await page.check('#check');
    await page.uncheck('#uncheck');
    await page.setChecked('#set-checked', true);
    await page.selectOption('#select', 'option');
    await page.setInputFiles('#files', 'fixture.txt');
    await page.hover('#hover');
    await page.focus('#focus');
    await page.dispatchEvent('#dispatch', 'change');
    await page.dragAndDrop('#source', '#target');
  });

  test('only suppresses actions whose Promise aggregate is observed', async ({ page }) => {
    await Promise.all([page.locator('#awaited-aggregate').drop()]);
    Promise.all([page.locator('#floating-aggregate').click()]);
    const assignedAggregate = Promise.all([page.locator('#assigned-aggregate').drop()]);
    void assignedAggregate;
    return Promise.all([page.locator('#returned-aggregate').drop()]);
  });
});
