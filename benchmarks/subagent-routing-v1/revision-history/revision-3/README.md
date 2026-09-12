# Protocol revision 3 archive

Revision 3 completed the full 96-cell Claude measured phase. Those committed
results remain at the benchmark root and are not modified by revision 4.

The later Codex feasibility smoke passed `codex.inline`, but both delegation
routes were structurally unavailable in the installed Codex CLI environment.
`codex.named` was retried once for diagnosis; neither attempt contained a real
delegation event, and the CLI logged `collab spawn failed`. `codex.native-role`
produced the same failure and no attestable `spawn_agent` event. The failed
smoke report and all four raw executions are preserved here.

Preserved digests:

- `protocol.json`: `183d0f184978c9e8b0f90b1c91d7a36373fb3bb60dc5e9216e650e256ed64fa6`
- `run_routing.py`: `e8e3559d272b8e82ba5a0fc356ac2d13036f1098763cf8b0b47f725c2b0ef863`
- `freeze-record.json`: `418b6999434a6c068c82c801a58ca85de06d755e9560836314b92a498465c031`
- `execution-authorization-claude.json`: `c9639f41dd51a92ae6d4e6820c6cc0b007e20019eddbd1bb07d81fadad9e60dd`
- `smoke-results-claude.json`: `8a9b55d5763e5db64a8e2f01699dedaf7f77b178122e6a484dd509fe2454794f`
- `routing-results-claude.json` at the benchmark root: `b51b3044e63297e5554d4ed5df9f078753dc1a87de4f9cd141d80fa47ba8351e`
- failed `smoke-results-codex.json`: `806953673e7b654cbfb0ba3514b2aa99dd8aded56be97528c13d753fcc5518f0`

Revision 4 changes only the Codex availability contract and harness dispatch.
It preserves the 144-cell Codex report schedule, records 96 delegation cells
as zero-cost `UNAVAILABLE`, and permits only 48 real `codex.inline` executions.
