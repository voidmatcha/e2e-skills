// Vitest unit tests. Intentionally carries none of the framework markers the scanner
// keys on (no Playwright test import, no browser-page object calls, no Cypress commands)
// so E2E content scoping must filter every hit below.
import { describe, it, expect } from 'vitest';
import { render, screen } from '@testing-library/react';
import { computeLayout, Widget } from '../src/widget';

describe('computeLayout', () => {
  it('returns a non-negative left offset', () => {
    const result = computeLayout({ width: 320 });
    expect(result.left).toBeGreaterThanOrEqual(0);
  });

  it('renders the widget title', () => {
    render(Widget({ title: 'hello' }));
    expect(screen.getByText('hello')).toBeTruthy();
  });
});
