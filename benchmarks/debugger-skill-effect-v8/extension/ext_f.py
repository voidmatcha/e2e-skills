"""Batch F of the v8 extension: last top-up (F5, F11)."""
CASES = []


def add(**kw):
    CASES.append(kw)


add(id="cy-n18", framework="cypress", repo="neurobagel/query-tool", license="MIT", pr=853, merged="2026-09-03",
    test="cypress/e2e/ResultsTSV.cy.ts > Unprotected response > Checks whether the rows in the participant.tsv file generated according to session_type",
    observed="Intermittent failure in the Unprotected response suite: the download button is disabled when the test tries to use it. The page is visited after the dataset, subject and three options requests are stubbed and waited for; it passes on other runs of the same commit.",
    error="AssertionError: Timed out retrying after 4000ms: expected '<download button>' not to be 'disabled' (shaped; the pull request names the symptom but quotes no text)",
    environment="React query tool whose search form is filled by several option requests when the page loads.",
    spec_before="cy.intercept('POST', '/datasets', unprotectedResponse).as('call');\ncy.intercept('POST', '/subjects', unprotectedSubjectResponse).as('subjectsCall');\n// ... intercepts for diagnosis, assessment tool and imaging modality options\ncy.visit('/');\ncy.wait(['@getDiagnosisOptions', '@getAssessmentToolOptions', '@getImagingModalityOptions']);",
    diag="test_defect", side="Test (race on unordered async results)",
    explanation="The page also requests /nodes and /pipelines on load, and the test neither stubs nor waits for them. Depending on when those two responses arrive relative to the test's next steps, the download button is still disabled when the test uses it.",
    fix="Intercept GET /nodes and GET /pipelines with their fixture data and wait for them together with the three option requests after cy.visit('/').",
    f="F11", second="F3", fit="forced",
    rationale="Two page-load requests are left unawaited; the order of their responses and the test steps decides the outcome, so it is an async order assumption (and an incompletely stubbed API).")

add(id="pw-n54", framework="playwright", repo="maximhq/bifrost", license="Apache-2.0", pr=8365, merged="2026-10-12",
    test="tests/e2e/features/logs/logs.spec.ts > LLM Logs > should show each attempt with its class or reason and its status",
    observed="Intermittent failure of the routing test. The test opens the logs page and immediately opens the details sheet of the first row and then its Routing tab. It fails on some runs with no product change in between, and passes when the table has finished loading.",
    error="Error: locator.click: Timeout 30000ms exceeded.\nwaiting for the first log row (the table has no rows yet)",
    environment="React dashboard; the logs table fills in after the page loads.",
    spec_before="await page.goto('/workspace/logs')\nawait logsPage.viewLogDetails(0)\nawait logsPage.logDetailSheet.getByRole('tab', { name: /Routing/ }).click()",
    diag="test_defect", side="Test (missing wait)",
    explanation="viewLogDetails(0) opens the first row, but the logs table can still be loading when the test calls it, so there is no first row yet.",
    fix="Assert that the logs table has exactly one row (expect(logsPage.tableRows).toHaveCount(1)) before calling viewLogDetails(0).",
    f="F5", second="F11", fit="forced",
    rationale="The test acts on the table before the state it needs (a rendered row) exists; the missing step is the wait for that state.")
