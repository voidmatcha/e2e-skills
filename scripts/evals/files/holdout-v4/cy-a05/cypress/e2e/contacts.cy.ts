let createdContacts: string[] = [];

describe('contact editor', () => {
  it('stores a contact', () => {
    const name = `contact-${Date.now()}`;
    createdContacts.push(name);
    cy.visit('/contacts/new');
    cy.get('[data-cy=name]').type(name);
    cy.get('[data-cy=save]').click();
    cy.get('[data-cy=notice]').should('contain.text', 'Saved');
  });
});
