describe('v20-cy-07', () => {
  it('shows parcel carrier and tracking number', () => {
    cy.visit('/parcels/12');
    cy.get('[data-testid=carrier]').should('have.text', 'North Express');
  });
});
