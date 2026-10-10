// SPDX-License-Identifier: Apache-2.0
export const WizardPage = {
  open: () => cy.visit('/wizard'),
  openCreateWizard: () => cy.getByTestId('create_btn').click(),
  readStatus: () => cy.get('body').invoke('text'),
};
