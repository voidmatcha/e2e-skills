import { AccountPage } from '../pages/account-page';

describe('account access', () => {
  it('signs in with the member profile', () => {
    const account = new AccountPage();
    account.open();
    cy.get('[data-cy=email]').type('member@example.test');
    cy.get('[data-cy=password]').type('Summer2026!');
    cy.get('[data-cy=submit]').click();
    cy.get('[data-cy=account-home]').should('be.visible');
  });
});
