// confirmation-case: CFC-04/cypress/e2e/costume-rack.cy.ts
describe('costume rack', () => {
  it('shows moon-chorus costume', () => {
    cy.visit('/costumes');
    cy.get('[data-cy=moon-chorus]').should('be.visible');
  });
});
