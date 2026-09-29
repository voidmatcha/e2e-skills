describe('ink vats', () => {
  it('counts cyan vats', () => {
    cy.visit('/ink-vats');
    const vats = cy.get('[data-cy=cyan-vat]');
    expect(vats).to.have.length(3);
  });
});
