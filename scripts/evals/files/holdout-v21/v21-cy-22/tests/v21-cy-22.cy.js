import { route } from './route';
describe('feature behavior', () => {

it("restores playlist and closes editor", () => {
  cy.visit(route);
  cy.get("[data-testid=playlist-editor]").should('be.visible');
  cy.get("[data-testid=Cancel]").click();
  cy.get("[data-testid=playlist-summary]").should('be.visible');
  cy.get("[data-testid=playlist-editor]").should('not.be.visible');
});

});
