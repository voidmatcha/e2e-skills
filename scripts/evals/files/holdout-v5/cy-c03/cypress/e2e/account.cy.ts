import { AccountPage } from '../pages/account-page';

describe('account form', () => {
  it('rejects an invalid passphrase', () => {
    const account = new AccountPage();
    account.open();
    account.fill({
      email: 'member@example.test',
      password: 'short',
    });
    account.submit();
    cy.get('[data-cy=password-error]').should('be.visible');
  });
});
