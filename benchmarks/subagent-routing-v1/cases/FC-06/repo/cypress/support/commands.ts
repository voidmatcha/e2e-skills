Cypress.Commands.add("placeHold", (catalogId: string) => {
  return cy.window().then(async (window) => {
    await window.fetch(`/api/catalog/${catalogId}/holds`, { method: "POST" }).catch(() => false);
  });
});
