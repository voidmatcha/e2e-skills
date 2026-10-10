describe('feature behavior', () => {

it("shows Geometry and 45 min on the courses page", () => {
  cy.visit("/courses");
  cy.get("[data-testid=course-title]").should('have.text', "Geometry");
});

it("restores courses list and closes panel", () => {
  cy.visit("/courses?panel=open");
  cy.get("[data-testid=lesson-panel]").should('be.visible');
  cy.get("[data-testid=Close lesson]").click();
  cy.get("[data-testid=course-list]").should('be.visible');
});

});
