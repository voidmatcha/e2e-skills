describe('feedback form', () => {
  it('shows the thank-you message after sending feedback', () => {
    cy.intercept('POST', '/api/feedback', { statusCode: 201 }).as('sendFeedback');
    cy.visit('/feedback');
    cy.get('[data-cy=feedback-text]').type('The export is fast now.');
    cy.get('[data-cy=send-feedback]').click();
    cy.wait('@sendFeedback').its('request.body.text').should('eq', 'The export is fast now.');
    cy.get('[data-cy=feedback-thanks]').should('have.text', 'Thanks for the feedback!');
  });
});
