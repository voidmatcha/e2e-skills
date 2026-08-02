export class AccountPage {
  open() {
    cy.visit('/account');
  }

  openHistoryPanel() {
    cy.visit('/account/history');
  }
}
