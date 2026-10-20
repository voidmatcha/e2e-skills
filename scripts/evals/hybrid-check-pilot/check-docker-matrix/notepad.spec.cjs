// SPDX-License-Identifier: Apache-2.0
const {test, expect} = require('/opt/fixtures/node_modules/@playwright/test');
const fs = require('node:fs');
const base = 'http://127.0.0.1:3000';
const payload = 'Second OSS persistence control 20261018';
test('edited note content survives reload', async ({page, context}, testInfo) => {
  if (!['weak', 'strong'].includes(process.env.SECOND_STRENGTH)) throw new Error('Unfrozen strength');
  const observed = {targetRequests: [], targetStatus: null, phase: process.env.SECOND_PHASE};
  const editor = page.getByRole('textbox', {name: '', exact: true});
  await context.route('**/*', route => new URL(route.request().url()).origin === base ? route.continue() : route.abort());
  try {
    const initial = page.waitForResponse(response => response.url() === base + '/api/getNote' && response.request().method() === 'POST');
    await page.goto(base + '/second-oss-control');
    await (await initial).finished();
    await expect(editor).toHaveValue('');
    fs.writeFileSync('/test-out/seed-ready', 'ready');
    await expect.poll(() => fs.existsSync('/test-out/seed-continue'), {timeout: 5000}).toBe(true);
    const target = request => request.url() === base + '/second-oss-control' && request.method() === 'POST';
    page.on('request', request => { if (target(request)) observed.targetRequests.push({method: request.method(), url: request.url(), body: request.postDataJSON()}); });
    const saved = page.waitForResponse(response => target(response.request()));
    await editor.fill(payload);
    const response = await saved;
    await response.finished();
    observed.targetStatus = response.status();
    if (process.env.SECOND_STRENGTH === 'strong') {
      const loaded = page.waitForResponse(response => response.url() === base + '/api/getNote' && response.request().method() === 'POST');
      await page.reload();
      await (await loaded).finished();
      await expect(editor, 'note-content-persisted-after-reload').toHaveValue(payload);
    } else {
      // JUSTIFIED: intentionally weak experimental control; echo does not prove persistence.
      await expect(editor, 'note-content-editor-echo').toHaveValue(payload);
    }
  } finally {
    observed.editorValue = await editor.inputValue().catch(() => null);
    observed.serviceWorkers = context.serviceWorkers().length;
    fs.writeFileSync('/test-out/observation.json', JSON.stringify(observed, null, 2));
    await testInfo.attach('second-oss-observation', {body: JSON.stringify(observed), contentType: 'application/json'});
  }
});
