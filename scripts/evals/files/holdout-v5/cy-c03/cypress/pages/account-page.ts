import type { AccountFields } from '../support/state';

export class AccountPage {
  open() {
    cy.visit('/account');
  }

  fill(fields: AccountFields) {
    cy.get('[data-cy=email]').type(fields.email);
    cy.get('[data-cy=password]').type(fields.password);
  }

  submit() {
    cy.get('[data-cy=submit]').click();
  }
}
