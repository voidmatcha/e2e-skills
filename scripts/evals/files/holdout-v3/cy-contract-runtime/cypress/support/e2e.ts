Cypress.on(
  'uncaught:exception',
  (error) => {
    console.warn(error.message);
    return false;
  },
);

Cypress.on('uncaught:exception', (error) => {
  expect(error.message).to.include('ResizeObserver loop');
  return error.message.includes('ResizeObserver loop') ? false : true;
});
