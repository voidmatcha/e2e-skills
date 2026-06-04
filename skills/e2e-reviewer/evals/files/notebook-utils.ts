import { Page, BrowserContext } from '@playwright/test';

// Module-level mutable counter — collides across parallel workers and survives
// retries within a worker. Anti-pattern #19.
let testNotebookSequence = 0;

// Module-level mutable cache without a worker-scoping justification.
let resultCache = new Map<string, string>();

// Idiomatic Playwright fixtures: pure type-only declarations, reassigned in
// beforeEach. These are NOT module-level mutable state smells.
let page: Page;
let context: BrowserContext;

// JUSTIFIED: worker-scoped warm cache, reset in beforeAll per worker; the
// parallel-collision concern of #19 does not apply to worker-scoped state.
let workerScopedCache = new Map<string, number>();

export function nextNotebookName(): string {
  testNotebookSequence += 1;
  return `notebook-${testNotebookSequence}`;
}

export function buildLabels(count: number): string[] {
  // Local loop counter inside a function body — not module-level state.
  let counter = 0;
  const labels: string[] = [];
  while (counter < count) {
    labels.push(`label-${counter}`);
    counter += 1;
  }
  return labels;
}

export function cacheResult(key: string, value: string): void {
  resultCache.set(key, value);
}

export function bindFixtures(p: Page, c: BrowserContext): void {
  page = p;
  context = c;
}
