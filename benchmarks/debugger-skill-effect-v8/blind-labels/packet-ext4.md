# Blind F-code mapping packet, extension ext4 (v8)

3 already-diagnosed E2E failures. For each item you see only the root-cause statement and the fix.

## item-105 (playwright)

Root cause: The MUI Tooltip wrapper around the button carries the same aria-label as the button itself, so an attribute selector on aria-label matches two elements.

Fix: Locate the button by role: page.getByRole('button', { name: 'Configure step' }).

## item-106 (playwright)

Root cause: Because every test shares one server, the notebooks opened by earlier tests are restored when the next test loads /lab, and restoring them pops up a Select Kernel dialog that blocks clicks.

Fix: Load /lab?reset so each test starts from an empty workspace.

## item-107 (playwright)

Root cause: getByLabel matches by substring and ignores the element type, so the label Mount path also matches the label of the 'Expose mount path as env var' checkbox, and the locator resolves to two elements.

Fix: Use the role and name: dialog.getByRole('textbox', { name: 'Mount path' }).
