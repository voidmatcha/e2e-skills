import { test, expect, type Page } from '@playwright/test';
import { uniqueProjectName } from './support/names';

let page: Page;

test.beforeEach(async ({ page: fixturePage }) => {
  page = fixturePage;
  await page.goto('/projects');
});

test('filters the project list by the typed name', async () => {
  const name = uniqueProjectName('atlas');
  await page.getByTestId('project-filter').fill(name);
  await expect(page.getByTestId('project-filter-summary')).toHaveText(`Filtering by ${name}`);
});

test('shows no matches for an unknown project name', async () => {
  const name = uniqueProjectName('borealis');
  await page.getByTestId('project-filter').fill(name);
  await expect(page.getByTestId('project-empty-state')).toHaveText(`No projects match ${name}`);
});
