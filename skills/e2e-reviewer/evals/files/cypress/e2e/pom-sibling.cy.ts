// SPDX-License-Identifier: Apache-2.0
import { WizardPage } from '../pageobjects/WizardPage';

it('opens the create wizard and dismisses the help overlay', () => {
  WizardPage.open();
  cy.getByTestId('create_btn').click();
  cy.get('body').type('{esc}');
  cy.getByTestId('wizard_form').should('be.visible');
});
