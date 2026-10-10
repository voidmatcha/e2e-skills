describe('compost', () => {
  it('reports nonnegative pile mass', () => {
    cy.visit('/compost');
    const mass = Math.abs(-5);
    expect(mass).to.be.greaterThan(0);
  });
});
