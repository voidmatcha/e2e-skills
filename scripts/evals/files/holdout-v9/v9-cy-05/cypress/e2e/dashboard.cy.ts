const delays = { chartAnimation: 800 };

describe('dashboard', () => {
  it('renders the revenue chart', () => {
    cy.on('uncaught:exception', (error) => {
      if (error.message.includes('ResizeObserver loop completed')) {
        return false;
      }
      throw error;
    });
    cy.intercept('GET', '/api/revenue', { fixture: 'revenue.json' });
    cy.openDashboard();
    cy.wait(delays.chartAnimation);
    cy.get('[data-cy=revenue-chart] [data-cy=bar]').should('have.length', 12);
  });
});
