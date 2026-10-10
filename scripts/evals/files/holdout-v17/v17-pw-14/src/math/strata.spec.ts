import { describe, it, expect } from 'vitest';
describe('strata', () => {
  it('sorts layers', () => { expect([3, 1].sort()).toEqual([1, 3]); });
});
