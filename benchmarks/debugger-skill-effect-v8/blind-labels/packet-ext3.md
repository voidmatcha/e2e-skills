# Blind F-code mapping packet, extension ext3 (v8)

2 already-diagnosed E2E failures. For each item you see only the root-cause statement and the fix.

## item-103 (cypress)

Root cause: The page also requests /nodes and /pipelines on load, and the test neither stubs nor waits for them. Depending on when those two responses arrive relative to the test's next steps, the download button is still disabled when the test uses it.

Fix: Intercept GET /nodes and GET /pipelines with their fixture data and wait for them together with the three option requests after cy.visit('/').

## item-104 (playwright)

Root cause: viewLogDetails(0) opens the first row, but the logs table can still be loading when the test calls it, so there is no first row yet.

Fix: Assert that the logs table has exactly one row (expect(logsPage.tableRows).toHaveCount(1)) before calling viewLogDetails(0).
