it('opens the Job link by exact string', () => {
  cy.findByRole('link', { name: 'Job' }).click();
});
it('opens the Job link by broad regex', () => {
  cy.findByRole('link', { name: /Job/ }).click();
});
it('opens the Job link by anchored regex', () => {
  cy.findByRole('link', { name: /^Job$/ }).click();
});
