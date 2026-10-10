describe('vault', () => {
  it('verifies the vault seal', () => {
    cy.visit('/vault');
    cy.verifyVault();
  });
});
