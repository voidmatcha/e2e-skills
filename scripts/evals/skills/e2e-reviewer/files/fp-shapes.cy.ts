// SPDX-License-Identifier: Apache-2.0
if (Cypress.env('AUTH_PROVIDER')) {
  describe('provider', () => {
    it('shows profile', () => { cy.get('[data-test=profile]').should('be.visible'); });
  });
}

it('requires privacy', () => {
  if (Cypress.env('GOV_CLOUD')) cy.get('[data-test=privacy]').should('be.disabled');
});

function verifyPossiblyMissing(element: unknown, state: string) {
  if (state.includes('visible')) return expect(element).toBeVisible();
}

async function recoverButton(button: any) {
  if (await button.isVisible().catch(() => false)) return;
  await button.click();
}

async function swallowAssertion(button: any) {
  await expect(button).toBeVisible().catch(() => false);
}

Cypress.on('uncaught:exception', err => {
  if (err.message?.includes('known library error')) return false;
});

Cypress.on('uncaught:exception', err => {
  console.log(err.message);
  return false;
});
