---
name: e2e-reviewer
description: 'Catalog-only control for a preregistered e2e-reviewer ablation.'
license: Apache-2.0
metadata:
  author: voidmatcha
  version: "1.10.0-control"
---

# E2E Reviewer Catalog Control

Review only the Playwright or Cypress files named by the caller.

Use `references/pattern-reference.md` as the canonical definition, severity,
scope, and false-positive contract for every pattern. Inspect all named files
before deciding. Report only findings confirmed by that contract.

Follow the caller's output schema exactly.
