// confirmation-case: CFC-08/cypress/e2e/prop-return.cy.ts
describe('prop return', () => {
  it('records lantern return', () => {
    cy.visit('/props/lantern');
    cy.get('[data-cy=return-prop]').click();
    cy.intercept('POST', '/api/props/lantern/return').as('returnProp');
    cy.wait('@returnProp');
  });
});
