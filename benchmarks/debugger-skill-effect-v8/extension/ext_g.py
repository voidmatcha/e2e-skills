"""Batch G of the v8 extension: three distinct failures documented in one pull request (kubeflow/kale #982)."""
CASES = []


def add(**kw):
    CASES.append(kw)


add(id="pw-n55", framework="playwright", repo="kubeflow/kale", license="Apache-2.0", pr=982, merged="2026-10-02",
    test="labextension/ui-tests/tests/kale-ui-components.spec.ts > Open a Notebook and Enable Kale > (the test that checks the Configure step control)",
    observed="On a fresh run of the UI suite 10 of the 11 tests failed. This test gets as far as the labels Cell type, Step name and Depends on, which are visible, and then fails on the Configure step control. The control is on the page.",
    error="Error: strict mode violation: locator('[aria-label=\"Configure step\"]') resolved to 2 elements",
    environment="JupyterLab extension (React with MUI) driven by Playwright against one shared server.",
    spec_before="await expect(page.locator('label:has-text(\"Depends on\")')).toBeVisible();\nawait expect(page.locator('[aria-label=\"Configure step\"]')).toBeVisible();",
    diag="test_defect", side="Test (locator)",
    explanation="The MUI Tooltip wrapper around the button carries the same aria-label as the button itself, so an attribute selector on aria-label matches two elements.",
    fix="Locate the button by role: page.getByRole('button', { name: 'Configure step' }).",
    f="F2", second="F12", fit="clean",
    rationale="An attribute selector that matches both a wrapper and the button is a strict mode violation from the start; the page did not change.")

add(id="pw-n56", framework="playwright", repo="kubeflow/kale", license="Apache-2.0", pr=982, merged="2026-10-02",
    test="labextension/ui-tests/tests/kale-ui-components.spec.ts > Volumes (fillAndSubmitVolume helper)",
    observed="On a fresh run of the UI suite 10 of the 11 tests failed. The volume dialog opens and the PVC name is filled; the helper fails on the next field, the mount path.",
    error="Error: locator.fill: Error: strict mode violation: getByLabel('Mount path') resolved to 2 elements",
    environment="The volume dialog is a React form; besides the mount path text box it has a checkbox to expose the mount path as an environment variable.",
    spec_before="await dialog.getByLabel('PVC name').fill(name);\nawait dialog.getByLabel('Mount path').fill(mountPoint);\nawait dialog.getByRole('button', { name: 'Add volume', exact: true }).click();",
    diag="test_defect", side="Test (locator)",
    explanation="getByLabel matches by substring and ignores the element type, so the label Mount path also matches the label of the 'Expose mount path as env var' checkbox, and the locator resolves to two elements.",
    fix="Use the role and name: dialog.getByRole('textbox', { name: 'Mount path' }).",
    f="F2", second="F12", fit="clean",
    rationale="A substring label locator that is ambiguous within the dialog; nothing about the dialog changed.")

add(id="pw-n57", framework="playwright", repo="kubeflow/kale", license="Apache-2.0", pr=982, merged="2026-10-02",
    test="labextension/ui-tests/tests/kale-ui-components.spec.ts > (tests that open the Kale tab)",
    observed="On a fresh run of the UI suite 10 of the 11 tests failed. Several fail on a click that is blocked by a Select Kernel dialog that the test never opened. The first test of the file passes; the dialog shows up in later tests.",
    error="Error: locator.click: Timeout 120000ms exceeded.\n<div class=\"jp-Dialog\"> Select Kernel ... intercepts pointer events",
    environment="All tests share one JupyterLab server (workers: 1) and each test loads /lab; JupyterLab restores the previous workspace.",
    spec_before="async function openKaleTab(page: Page): Promise<void> {\n  await page.goto('http://localhost:8889/lab', { waitUntil: 'load' });\n\n  await page.waitForTimeout(3000);",
    diag="test_defect", side="Test (shared state across tests)",
    explanation="Because every test shares one server, the notebooks opened by earlier tests are restored when the next test loads /lab, and restoring them pops up a Select Kernel dialog that blocks clicks.",
    fix="Load /lab?reset so each test starts from an empty workspace.",
    f="F7", second="F8", fit="clean",
    rationale="Workspace state left by earlier tests on a shared server breaks later tests; the first test passes alone.")
