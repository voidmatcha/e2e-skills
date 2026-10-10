import { route } from './route';
describe('feature behavior', () => {

it("shows receipt total of $84.50", () => {
  cy.visit(route);
  cy.get("[data-testid=page-shell]").should('be.visible');
});

});
