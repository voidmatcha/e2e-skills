describe('v20-cy-06', () => {
  it('resetting filters clears chips and restores all results', () => {
    cy.visit('/catalog');
    cy.contains('button', 'In stock').click();
    cy.contains('button', 'Reset filters').click();
    cy.get('h1').should('contain.text', 'Catalog');
  });
});
