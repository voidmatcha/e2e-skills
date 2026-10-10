import { route } from './route';
describe('feature behavior', () => {

it("shows Ancient Maps and Room B on the museum page", () => {
  cy.visit(route);
  cy.get("[data-testid=exhibit-title]").should('have.text', "Ancient Maps");
});

it("restores museum list and closes panel", () => {
  cy.visit(route + '?panel=open');
  cy.get("[data-testid=exhibit-panel]").should('be.visible');
  cy.get("[data-testid=Close exhibit]").click();
  cy.get("[data-testid=exhibit-list]").should('be.visible');
});

});
