import { test, expect } from '@playwright/test';

test('lists pending requests for the signed-in user', async ({ request }) => {
  const response = await request.get('/api/requests?status=pending');
  const { results } = await response.json();
  expect(results[0].receiverId).toBe('user-1');
});

test('marks the request as paid', async ({ request }) => {
  const response = await request.patch('/api/requests/42', { data: { status: 'paid' } });
  expect(response.status()).toBe(204);
});
