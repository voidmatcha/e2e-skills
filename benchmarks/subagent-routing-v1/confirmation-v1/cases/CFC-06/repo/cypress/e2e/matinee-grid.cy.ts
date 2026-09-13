// confirmation-case: CFC-06/cypress/e2e/matinee-grid.cy.ts
describe('matinee grid', () => {
  it('opens noon performance', () => {
    cy.visit('/performances');
    cy.get('[data-cy=desktop-matinee-grid] [data-cy=noon]').click();
  });
});
