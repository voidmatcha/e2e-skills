import { test, expect } from '@playwright/test';
import { AuditLogPage } from '../pages/audit-log-page';

test('shows the three most recent audit entries', async ({ page }) => {
  const auditLog = new AuditLogPage(page);
  await auditLog.open();
  await expect(auditLog.entries()).toHaveCount(3);
});

test('adds a note to the newest audit entry', async ({ page }) => {
  await page.route('**/api/audit/notes', (route) => route.fulfill({ status: 201 }));
  const auditLog = new AuditLogPage(page);
  await auditLog.open();
  await expect.soft(page.getByTestId('audit-note-editor')).toBeVisible();
  await page.getByTestId('audit-note-editor').fill('Reviewed by security');
  await page.getByRole('button', { name: 'Save note', exact: true }).click();
  await expect(page.getByTestId('audit-note')).toHaveText('Reviewed by security');
});
