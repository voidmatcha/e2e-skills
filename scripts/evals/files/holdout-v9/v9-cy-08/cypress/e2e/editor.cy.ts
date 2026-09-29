describe('rich text editor', () => {
  beforeEach(() => {
    cy.intercept('GET', '/api/docs/42', { fixture: 'doc.json' });
    cy.visit('/docs/42');
  });

  it('selects the heading word on double click', () => {
    cy.get('[data-cy=doc-heading]').dblclick().should('have.class', 'is-selected');
  });

  it('shows the toolbar once the document loads', () => {
    cy.get('[data-cy=editor-toolbar]', { timeout: 0 }).should('be.visible');
  });

  it('starts without the unsaved-changes marker', () => {
    // JUSTIFIED: asserts the state at first paint; the marker may legitimately appear after autosave.
    cy.get('[data-cy=unsaved-marker]', { timeout: 0 }).should('not.exist');
    cy.get('[data-cy=doc-heading]').should('have.text', 'Release notes');
  });
});
