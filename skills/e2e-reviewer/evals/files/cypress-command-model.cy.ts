describe('Cypress command model', () => {
  it('mixes async promises with Cypress commands', async () => {
    await cy.get('[data-testid="save"]');
  });

  beforeEach(async () => {
    await cy.visit('/settings');
  });

  it('assigns a queued command result', () => {
    const button = cy.get('[data-testid="save"]');
    button.click();
  });

  it('chains after a one-shot action', () => {
    cy.get('[data-testid="name"]').type('Ada').should('have.value', 'Ada');
  });

  it('uses a normal Cypress chain', () => {
    cy.get('[data-testid="save"]').should('be.enabled').click();
    cy.get('[role="status"]').should('have.text', 'Saved');
  });

  it('assigns an ordinary application value', () => {
    const expected = 'Saved';
    cy.get('[role="status"]').should('have.text', expected);
  });
});
