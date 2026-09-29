Cypress.on('uncaught:exception', (exception) => {
  // Known third-party chat widget bug, tracked in BAKE-219; every other error must fail the spec.
  if (exception.message.includes('ChatWidget: socket closed')) return false;
  throw exception;
});
