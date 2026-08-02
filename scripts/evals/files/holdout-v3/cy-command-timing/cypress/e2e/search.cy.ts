describe('search command timing', () => {
  it('shows the ready state with a visible result', () => {
    cy.visit('/search?q=tea');
    cy.get('[data-cy=search-result]').should('be.visible');
    cy.get('[data-cy=status]').should('have.text', 'Ready');
  });

  it('waits a fixed delay before checking results', () => {
    cy.visit('/search?q=coffee');
    cy.wait(750);
    cy.get('[data-cy=result-count]').should('not.have.text', '0');
  });

  it('keeps using the subject after an action', () => {
    cy.get('[data-cy=refresh]')
      .click()
      .should('have.attr', 'data-loaded', 'true');
  });

  it('returns an asserted query from a helper', () => {
    const ready = () => {
      return cy.get('[data-cy=status]').should('have.text', 'Ready');
    };
    ready();
  });

  it('waits for the search alias', () => {
    cy.intercept('GET', '/api/search*').as('search');
    cy.visit('/search?q=matcha');
    cy.wait('@search');
    cy.get('[data-cy=result-count]').should('have.text', '1');
  });

  it('requeries after refreshing', () => {
    cy.get('[data-cy=refresh]').click();
    cy.get('[data-cy=refresh]').should('have.attr', 'data-loaded', 'true');
  });
});
