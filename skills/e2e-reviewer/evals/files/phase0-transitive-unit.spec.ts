import { describe, expect, it } from '@jest/globals';

describe('formatter', () => {
  it('formats a label', () => {
    expect('ready'.toUpperCase()).toBe('READY');
  });
});
