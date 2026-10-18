<!-- SPDX-License-Identifier: Apache-2.0 -->
# Notepad split dependency mountpoint correction

V2 passed host preflight and source export but Docker stopped before app
startup: its read-only `/app` bind had no `node_modules` mountpoint. V2 is
`CANNOT_VERIFY` with zero native cells; its frozen runner and error remain
under `notepad-split-v2/`. V3 adds an empty `app/node_modules` directory to
each fresh export before mounting the already pinned read-only Linux dependency
tree there. No dependency bytes, source files, app behavior, test, fault,
oracle, schedule or acceptance rule changes. Use a new output root, stop on
the first invalid cell and preserve all attempted artifacts.
