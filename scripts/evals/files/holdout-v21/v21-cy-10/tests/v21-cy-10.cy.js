import { route } from './route';
describe('feature behavior', () => {

it("shows rain forecast and temperature", () => {
  cy.visit(route);
  cy.get("[data-testid=forecast-heading]").should('have.text', "Rain tomorrow");
});

});
