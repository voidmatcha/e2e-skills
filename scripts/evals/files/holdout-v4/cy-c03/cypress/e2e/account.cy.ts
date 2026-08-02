import { AccountPage } from '../pages/account-page';

describe('account form', () => {
  it('rejects an invalid passphrase', () => {
    const account = new AccountPage();
    account.open();
    cy.get('[data-cy=email]').type('member@example.test');
    cy.get('[data-cy=password]').type('short');
    account.submit();
    cy.get('[data-cy=password-error]').should('be.visible');
  });
});
