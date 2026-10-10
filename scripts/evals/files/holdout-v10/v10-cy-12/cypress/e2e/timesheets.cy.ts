describe('weekly timesheet', () => {
  beforeEach(() => {
    cy.request('POST', '/auth/session', { username: 'contractor-7', password: 'Timesheet#77' });
    cy.visit('/timesheets/current');
  });

  it('totals the logged hours', async () => {
    cy.get('[data-cy=hours-mon]').type('7.5');
    cy.get('[data-cy=hours-tue]').type('8');
    cy.get('[data-cy=week-total]').should('have.text', '15.5 h');
  });

  it('submits the week for approval', () => {
    const submit = cy.get('[data-cy=submit-week]');
    submit.click();
    cy.get('[data-cy=approval-state]').should('have.text', 'Awaiting approval');
  });
});
