Cypress.on("uncaught:exception", (error) => {
  if (error.message === "ShelfMap widget: observer disconnected after panel close") {
    return false;
  }
  throw error;
});
