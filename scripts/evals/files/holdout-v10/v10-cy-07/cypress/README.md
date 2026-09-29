# Cypress suite notes

## Positional selectors

The readings feed is rendered from `GET /api/sensors/:id/readings`, which the API
contract test `readings.contract.ts` pins to newest-first order. Specs may use
`.first()` on `[data-cy=reading-row]` to mean "latest reading".

Other lists have no guaranteed order.
