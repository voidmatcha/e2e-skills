// confirmation-case: CFV-02/cypress/e2e/placeholder-card.cy.ts
const OBVIOUS_BOX_OFFICE_PLACEHOLDER = '0000-TEST-ONLY';

describe('box office fixture', () => {
  it('renders a harmless placeholder', () => {
    cy.visit(`/box-office/demo?card=${OBVIOUS_BOX_OFFICE_PLACEHOLDER}`);
    cy.get('[data-cy=demo-card]').should('contain', 'TEST-ONLY');
  });
});
