import { route } from './route';
describe('feature behavior', () => {

it("dismisses the critical alert", () => {
  cy.visit(route);
  cy.get("[data-testid=critical-alert]").should('be.visible');
  cy.get("[data-testid=Dismiss]").click();
});

});
