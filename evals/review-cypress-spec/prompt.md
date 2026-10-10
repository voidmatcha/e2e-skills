---
max_turns: 30
allowed_tools: [Read, Glob, Grep, Skill]
---

Can you review this Cypress spec for weak or flaky tests? It is `cypress/e2e/settings.cy.ts`, and `cypress/support/e2e.ts` contains the handler shown first:

```ts
// cypress/support/e2e.ts
Cypress.on('uncaught:exception', () => false);
```

```ts
// cypress/e2e/settings.cy.ts
describe('settings', () => {
  it('saves the display name', () => {
    cy.visit('/settings');
    cy.get('[data-cy=display-name]').clear().type('Ada');
    cy.get('[data-cy=save]').click({ force: true });
    cy.wait(2000);
  });
});
```
