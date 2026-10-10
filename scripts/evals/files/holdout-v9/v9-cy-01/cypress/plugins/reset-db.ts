import { copyFileSync } from 'node:fs';

export function resetDatabase(): null {
  copyFileSync('data/seed.sqlite', 'data/e2e.sqlite');
  return null;
}
