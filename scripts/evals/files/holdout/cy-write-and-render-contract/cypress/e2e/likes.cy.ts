describe('liked items', () => {
  it('updates the optimistic like state', () => {
    cy.visit('/likes');
    cy.get('[data-cy="like-toggle"]').click();
    cy.get('[data-cy="like-toggle"]').should('have.attr', 'aria-pressed', 'true');
  });

  it('proves the like request before checking the UI', () => {
    cy.visit('/likes');
    cy.get('[data-cy="like-toggle"]').click();
    cy.wait('@saveLike');
    cy.get('[data-cy="like-toggle"]').should('have.attr', 'aria-pressed', 'true');
  });

  it('renders a liked card from the default fixture', () => {
    cy.intercept('GET', '/api/liked-items', { fixture: 'liked.json' }).as('likedItems');
    cy.visit('/likes');
    cy.wait('@likedItems');
    cy.get('[data-cy="liked-card"]').should('be.visible');
  });

  it('renders a liked card from a renderable fixture', () => {
    cy.intercept('GET', '/api/liked-items', {
      fixture: 'visible-liked.json',
    }).as('visibleLikedItems');
    cy.visit('/likes');
    cy.wait('@visibleLikedItems');
    cy.get('[data-cy="liked-card"]').should('be.visible');
  });
});
