export class AccountPage {
  open() {
    cy.visit('/account');
  }

  submit() {
    cy.get('[data-cy=submit]').click();
  }
}
