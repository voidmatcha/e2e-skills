# Saved-items fixture

The GET `/api/toggle?item=oak|cedar` flips persistent server-side saved state. The user task requires Oak, Cedar, reload, Oak; the final visible state is Oak not saved, Cedar saved, saved count 1. `GET /api/saved` re-reads persistent state after reload. The reset route is for the benchmark harness only.

License: Apache-2.0.
