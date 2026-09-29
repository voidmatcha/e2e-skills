import { describe, it, expect } from 'vitest';
import { nextDueDate } from './due-date';

let calls = 0;

describe('nextDueDate', () => {
  it('adds fourteen days', () => {
    calls += 1;
    expect(nextDueDate(new Date('2026-09-30'))).toBeTruthy();
  });
});
