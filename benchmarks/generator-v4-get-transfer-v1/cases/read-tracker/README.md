# Reading tracker fixture

A disposable single-page app with two titles. Opening a title through `GET /api/open?id=...` changes in-memory read state and increments an open counter exactly once per request. `GET /api/items` reads that state; `POST /api/reset` is a test seam. The normal UI updates only after a successful open response. This makes request cardinality, item selection, reload persistence, and a failed-write V4 probe independently observable.

License: Apache-2.0.
