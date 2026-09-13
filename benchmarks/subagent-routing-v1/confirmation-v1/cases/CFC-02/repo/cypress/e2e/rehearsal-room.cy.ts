// confirmation-case: CFC-02/cypress/e2e/rehearsal-room.cy.ts
describe('rehearsal room', () => {
  it('shows the reserved state', () => {
    cy.reserveRehearsalRoom();
    cy.get('[data-cy=room-state]').should('have.text', 'Reserved');
  });
});
