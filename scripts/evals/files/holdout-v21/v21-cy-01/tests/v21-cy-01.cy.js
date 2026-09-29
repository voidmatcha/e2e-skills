import { route } from './route';
describe('feature behavior', () => {

it("restores profile summary and dismisses editor", () => {
  cy.visit(route);
  cy.get("[data-testid=edit profile]").should('be.visible');
  cy.get("[data-testid=Cancel]").click();
  cy.get("[data-testid=profile-summary]").should('be.visible');
});

});
