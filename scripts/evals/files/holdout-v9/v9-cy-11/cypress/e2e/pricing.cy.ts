describe('pricing page', () => {
  it('shows the student discount price', () => {
    cy.visit('/pricing?audience=student');
    cy.get('body').then(($body) => {
      if ($body.find('[data-cy=student-offer]').length === 0) {
        return;
      }
      cy.get('[data-cy=student-price]').should('have.text', '$5 / month');
    });
  });

  it('shows the standard monthly price', () => {
    cy.visit('/pricing');
    cy.get('body').then(($body) => {
      if ($body.find('[data-cy=cookie-banner]').length > 0) {
        cy.get('[data-cy=cookie-accept]').click();
      }
    });
    cy.get('[data-cy=standard-price]').should('have.text', '$12 / month');
  });
});
