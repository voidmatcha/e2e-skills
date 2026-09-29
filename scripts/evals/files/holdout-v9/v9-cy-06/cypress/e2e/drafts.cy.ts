describe('drafts', () => {
  beforeEach(() => {
    cy.intercept('GET', '/api/drafts/d-9', { fixture: 'draft.json' });
  });

  it('deletes the draft and returns to the drafts list', () => {
    cy.intercept('DELETE', '/api/drafts/d-9', { statusCode: 204 }).as('deleteDraft');
    cy.visit('/drafts/d-9');
    cy.get('[data-cy=delete-draft]').click();
    cy.wait('@deleteDraft');
    cy.location('pathname').should('eq', '/drafts');
  });

  it('renames the draft and shows the new title', () => {
    cy.intercept('PATCH', '/api/drafts/d-9', { statusCode: 200, body: { title: 'Q3 plan' } }).as('renameDraft');
    cy.visit('/drafts/d-9');
    cy.get('[data-cy=draft-title-input]').clear();
    cy.get('[data-cy=draft-title-input]').type('Q3 plan');
    cy.get('[data-cy=save-title]').click();
    cy.wait('@renameDraft');
  });
});
