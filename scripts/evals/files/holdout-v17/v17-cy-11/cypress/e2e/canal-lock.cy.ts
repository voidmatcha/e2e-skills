describe('canal lock', () => {
  it.skip('cycles the lower gate', () => {
    cy.visit('/canal');
  });
  // JUSTIFIED: LOCK-317 awaits hydraulic simulator; revisit 2026-Q4.
  it.skip('cycles the upper gate', () => {
    cy.visit('/canal');
  });
});
