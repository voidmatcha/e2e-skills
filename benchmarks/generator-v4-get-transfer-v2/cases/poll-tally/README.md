# Color poll fixture

The GET `/api/vote?choice=ruby|blue` increments a persistent server-side tally. The user task requires Ruby, Blue, reload, Ruby; the final visible tally is Ruby 2, Blue 1, total 3. `GET /api/tally` re-reads persistent state after reload. The reset route is for the benchmark harness only.

License: Apache-2.0.
