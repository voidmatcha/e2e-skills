// confirmation-case: CFV-04/cypress/e2e/costume-preview.cy.ts
describe('costume preview', () => {
  it('shows the costume name', () => {
    cy.visit('/costumes/preview');
    cy.get('[data-cy=costume-name]').should('contain', 'Moon Chorus');
  });
});
