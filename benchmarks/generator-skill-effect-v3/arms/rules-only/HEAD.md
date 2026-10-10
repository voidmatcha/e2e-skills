---
name: playwright-test-rules
description: 'Benchmark-only reduced variant of playwright-test-generator for generator-skill-effect-v3: the written locator and assertion rules only, copied verbatim from the full-fixed skill text, with no workflow steps, no run-and-fix loop and no scanner. Not a shipped skill.'
license: Apache-2.0
metadata:
  author: voidmatcha
  frameworks: playwright
  testing-types: e2e
  languages: typescript,javascript
  version: "2.0.0-rules-only-bench"
---

# Playwright test-writing rules (rules-only benchmark variant)

The sections below are copied verbatim from `code-rules.md` and `best-practices.md` of the `playwright-test-generator` skill (see `TRACE.md`). Apply them while writing the tests. References to "Step 1", "Step 3", "Step 4", the "Locator Mapping Table", "V-rules" and the "approved plan" point at workflow steps this variant does not include; read them as "what you observed in the application and its config".

