describe('translation glossary', () => {
  beforeEach(() => {
    cy.visit('/glossary/de-DE');
  });

  it('flags an emptied term as invalid', () => {
    cy.get('[data-cy=term-input]').clear().should('have.value', '');
    cy.get('[data-cy=term-input]').blur().should('have.attr', 'aria-invalid', 'true');
  });

  it('saves a new glossary entry', () => {
    cy.get('[data-cy=term-input]').type('Schluessel');
    cy.get('[data-cy=gloss-input]').type('key (cryptography)');
    cy.get('[data-cy=add-entry]').click();
    cy.contains('[data-cy=entry-row]', 'Schluessel').should('be.visible');
  });
});
