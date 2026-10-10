# Stock-claim fixture

The GET `/api/claim?sku=lamp|desk` decrements persistent server-side stock and increments the claimed total. The user task requires Lamp, Desk, reload, Lamp; the final visible state is Lamp 1 left, Desk 2 left, Claimed 3. `GET /api/stock` re-reads persistent state after reload. The reset route is for the benchmark harness only.

License: Apache-2.0.
