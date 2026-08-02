import { nextContactName } from '../../src/contact-service';

describe('contact editor', () => {
  it('stores a contact', () => {
    const name = nextContactName();
    cy.visit('/contacts/new');
    cy.get('[data-cy=name]').type(name);
    cy.get('[data-cy=save]').click();
    cy.get('[data-cy=notice]').should('contain.text', 'Saved');
  });
});
