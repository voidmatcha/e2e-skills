import { LikedCard } from "../../src/LikedCard";

describe("liked items", () => {
  it("does not show an unavailable liked item", () => {
    cy.fixture("hidden-liked").then((item) => {
      cy.mount(<LikedCard item={item} />);
    });
    cy.get('[data-testid="liked-card"]').should("not.exist");
  });

  it("shows a liked item that passes the render guard", () => {
    cy.fixture("visible-liked").then((item) => {
      cy.mount(<LikedCard item={item} />);
    });
    cy.get('[data-testid="liked-card"]').should("contain.text", "Saved lesson");
  });
});
