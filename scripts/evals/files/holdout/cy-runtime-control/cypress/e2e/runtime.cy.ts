describe('runtime controls', () => {
  beforeEach(() => {
    cy.intercept('GET', '/api/plans', {
      statusCode: 200,
      body: [{ id: 'starter', name: 'Starter' }],
    }).as('plans');
  });

  it.only('shows the runtime dashboard', () => {
    cy.visit('/runtime');
    cy.wait(750);
    cy.contains('Runtime dashboard').should('be.visible');
  });

  it('waits for the plans request', () => {
    cy.visit('/runtime');
    cy.wait('@plans');
    cy.contains('Starter').should('be.visible');
  });

  it('loads queued runtime data', async () => {
    await Promise.resolve();
    cy.visit('/runtime');
    cy.contains('Runtime ready').should('be.visible');
  });

  it('builds a native runtime fixture', async () => {
    const fixture = await Promise.resolve({ status: 'ready' });
    expect(fixture.status).to.equal('ready');
  });

  it('treats a focused-test token as text', () => {
    expect("it.only('debug')").to.include('.only');
  });
});
