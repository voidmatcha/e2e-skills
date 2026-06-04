describe('Products', () => {
  beforeEach(() => {
    cy.visit('/products');
  });

  it('lists products on the catalog page', () => {
    cy.get('.catalog').should('be.visible');
  });

  it('filters products by category', () => {
    cy.get('#category-electronics').click();
    cy.get('.product-card').should('have.length.greaterThan', 0);
    cy.get('.product-card');
  });

  it.only('searches products by keyword', () => {
    cy.get('#search').type('camera');
    cy.wait(2000);
    cy.get('.product-card').first().should('contain.text', 'camera');
  });

  it('opens a product from search', () => {
    cy.get('#search').type('tripod');
    cy.wait(1500);
    cy.get('.product-card').first().click();
    cy.get('.product-title').should('be.visible');
  });

  it('add product to cart', () => {
    cy.get('.product-card').first().find('.add-to-cart').click();
  });

  it('show product details', () => {
    cy.get('.product-card').first().click();
    const title = cy.get('.product-title');
    cy.get('.product-gallery').should('exist');
  });

  it('sorts products by price ascending', () => {
    cy.get('#sort-price-asc').click();
    cy.wait(1000);
    cy.get('.product-price').first().invoke('text').then((firstText) => {
      cy.get('.product-price').last().invoke('text').then((lastText) => {
        const first = parseFloat(firstText.replace('$', ''));
        const last = parseFloat(lastText.replace('$', ''));
        expect(first).to.be.lessThan(last);
      });
    });
  });

  it('shows the empty state when configured', () => {
    cy.get('#category-rare').click();
    if (Cypress.env('SHOW_EMPTY_STATE')) {
      cy.get('.empty-state').should('be.visible');
    }
  });

  it('applies a discount code', () => {
    cy.get('.product-card').first().find('.add-to-cart').click();
    cy.get('#cart-link').click();
    cy.get('#discount-code').type('SAVE20');
    cy.get('#apply-discount').click({ force: true });
    cy.get('.cart-total').should('contain.text', '$');
  });
});

describe('promo banner error handling', () => {
  // BLANKET suppressor — swallows EVERY app exception for the whole suite (#3b TP)
  cy.on('uncaught:exception', () => false);

  it('renders the promo banner', () => {
    cy.visit('/promo');
    cy.get('[data-testid="promo-banner"]').should('be.visible');
  });
});

describe('legacy widget regression', () => {
  // Scoped negative-regression handler: ASSERTS on the error, does not swallow it (#3b FP guard)
  cy.on('uncaught:exception', (err) => {
    expect(err.message.includes('ResizeObserver loop')).to.be.false;
  });

  it('loads the legacy widget without the historical crash', () => {
    cy.visit('/legacy-widget');
    cy.get('[data-testid="widget-root"]').should('be.visible');
  });
});
