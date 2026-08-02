import { CatalogPage } from '../pages/catalog-page';

describe('catalog cards', () => {
  const catalog = new CatalogPage();

  it('opens the first detail card', () => {
    catalog.open();
    catalog.openDetails('visible');
    cy.get('[data-cy=detail-toolbar]').should('contain.text', 'Visible product');
  });

  it('opens the second detail card', () => {
    catalog.open();
    catalog.openDetails('visible-2');
    cy.get('[data-cy=detail-toolbar]').should('contain.text', 'Second product');
  });

  it('renders a detail fixture inside the card guard', () => {
    cy.intercept('GET', '/api/catalog/guarded', {
      fixture: 'guarded-product.json',
    });
    catalog.open();
    cy.get('[data-cy=detail-toolbar]').should('be.visible');
  });

  it('renders a visible detail fixture', () => {
    cy.intercept('GET', '/api/catalog/visible', {
      fixture: 'visible-product.json',
    });
    catalog.open();
    cy.get('[data-cy=detail-toolbar]').should('be.visible');
  });
});
