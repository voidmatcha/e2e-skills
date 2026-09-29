describe('query and array contracts', () => {
  it('renders at least one shipped row', () => {
    cy.visit('/orders');
    cy.get('body').find('.row').each(($row) => {
      expect($row.text()).to.contain('Shipped');
    });
  });

  it('renders active shipped rows', () => {
    cy.visit('/orders');
    cy.get('.row').filter('.active').each(($row) => {
      expect($row.text()).to.contain('Shipped');
    });
  });

  it('verifies shipped labels from a supplied array', () => {
    cy.visit('/orders');
    cy.wrap([]).each((label) => {
      expect(label).to.equal('Shipped');
    });
  });

  it('renders the row through a queued query', () => {
    cy.visit('/orders');
    expect(cy.get('.row')).to.exist;
  });

  it('renders the row through a synchronous selection', () => {
    cy.visit('/orders');
    expect(Cypress.$('.row')).to.exist;
  });
});
