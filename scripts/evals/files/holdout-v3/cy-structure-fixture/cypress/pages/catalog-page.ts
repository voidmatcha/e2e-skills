export class CatalogPage {
  open() {
    cy.visit('/catalog');
  }

  openDetails(id: string) {
    cy.get(`[data-product-id="${id}"]`).click();
  }

  applyWholesaleFilter() {
    cy.get('[data-cy=wholesale-only]').check();
  }
}
