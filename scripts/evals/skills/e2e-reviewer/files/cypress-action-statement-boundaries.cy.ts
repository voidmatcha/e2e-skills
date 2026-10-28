// SPDX-License-Identifier: Apache-2.0
describe('keeps continuation with the candidate action', () => {
  it('distinguishes independent commands and continued actions', () => {
    cy.get('.first').click();
    cy.get('.second').scrollIntoView().should('be.visible');
    cy.get('.third').click()
    cy.get('.fourth').scrollIntoView().should('be.visible')
    cy.get('.actual').click().should('be.visible');
    cy.get('.multiline')
      .click(
        { x: Math.max(1, 2) },
      )
      .should('be.visible')
    cy.get('.independent').click()
    cy.get('.later').should('be.visible')
    cy.get('.plain').click(); cy.get('.same-line').click().should('be.visible');
  })
})
