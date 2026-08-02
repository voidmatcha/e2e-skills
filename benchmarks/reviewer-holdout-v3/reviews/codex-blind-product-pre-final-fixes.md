# Codex Blind Product Review — Pre-Fix Development Feedback

- Snapshot: `/private/tmp/e2e-review-blind-final.Oy44Vy`
- Date: 2026-07-30
- Status: Pre-fix development feedback only; this is not benchmark scoring.

## Blind Product Review

**Score: 76/100**  
**Verdict: REQUEST CHANGES**

The taxonomy and evidence harness are strong, but the default scanner has reproducible P0 false negatives and a P0 false positive. These are release blockers for a product whose core promise is deterministic silent-pass detection.

### Rubric

| Category | Score | Evidence |
|---|---:|---|
| Taxonomy correctness and severity | **19/20** | The 24-family taxonomy has explicit severity rationale, primary-line anchoring, overlap rules, and strong contextual exclusions. The executable Playwright 1.62 probes correctly support #15/#16 as P1 and #4g as a deadline/retry hazard rather than always-pass. |
| Semantic/detection correctness | **10/20** | Scanner contract tests pass, but default Tier 3 misses P0 findings in standard module extensions and multiline #4f assertions. |
| False-positive defenses and scope discipline | **9/15** | Framework scoping, custom-fixture resolution, symlink escape rejection, triage routing, and JUSTIFIED handling are well developed. However #7 matches string literals and cannot be suppressed, causing a false CI failure. |
| Executable fixture/mutation evidence | **13/15** | Current evidence binds 11 operators to 33 browser cells, with current fixture/operator/runner/lockfile hashes. Separate 6-cell floating-Promise and 3-cell timeout-zero probes validate nuanced severity choices. Coverage is intentionally limited to 11 of 24 families and documented honestly. |
| Benchmark runner integrity/reproducibility | **13/15** | Deterministic scheduling, snapshots, pre/post workspace hashes, fail-closed infrastructure status, exact rescoring, preregistered thresholds, and matrix comparison are solid. Ambient environment propagation remains an avoidable credential boundary. |
| Public docs/security/install honesty | **12/15** | Public docs distinguish development holdouts from sealed evidence, disclose lack of built-in isolation and lack of runtime attestation, and accurately qualify fixture coverage. Scanner extension limitations and live-run environment exposure are not disclosed. |
| **Total** | **76/100** | |

## Confirmed defects

### [HIGH] Default scanner misses focused tests and related checks in `.mjs`/`.cjs`/`.mts`/`.cts` specs

Files:

- `/private/tmp/e2e-review-blind-final.Oy44Vy/skills/e2e-reviewer/scripts/scan.sh:393`
- `/private/tmp/e2e-review-blind-final.Oy44Vy/skills/e2e-reviewer/scripts/scan.sh:411`
- `/private/tmp/e2e-review-blind-final.Oy44Vy/skills/e2e-reviewer/scripts/scan.sh:1246`
- `/private/tmp/e2e-review-blind-final.Oy44Vy/skills/e2e-reviewer/scripts/scan.sh:1248`
- `/private/tmp/e2e-review-blind-final.Oy44Vy/skills/e2e-reviewer/scripts/scan.sh:1289`

The scanner discovers module extensions at line 459, but Tier 1 configuration and multiple Tier 3 checks only accept `.ts`, `.js`, `.tsx`, or `.jsx`. Copying the existing `auth.spec.ts` and Cypress runtime fixture to `.spec.mjs`/`.cy.mjs` caused the scanner to miss:

- Playwright `test.only`
- Cypress `it.only`
- numeric `cy.wait`
- Cypress async-command mixing

The default P0 gate exited `0`.

**Failure mode:** A committed `.only` in an ESM Playwright/Cypress suite silently excludes tests while the advertised P0 scanner remains green.

**Fix:** Centralize a single JS/TS extension set covering `ts, tsx, mts, cts, js, jsx, mjs, cjs` across Tier 1 and every relevant Tier 3 glob. Add `.spec.mjs`, `.cy.mjs`, `.spec.cjs`, and `.mts` P0 regressions.

### [HIGH] Multiline Locator truthiness bypasses the canonical Tier 3 P0 baseline

File:

- `/private/tmp/e2e-review-blind-final.Oy44Vy/skills/e2e-reviewer/scripts/scan.sh:1262`

The #4f regex requires `expect(...)`, Locator construction, and matcher on one physical line. With optional AST tooling disabled, this canonical P0 shape was not detected:

```ts
expect(
  page.getByText("Welcome"),
).not.toBeNull();
```

The isolated fixture produced `0 P0` and exit `0`.

**Failure mode:** Normal formatter output converts an always-true Locator assertion into a scanner false negative.

**Fix:** Add a bundled multiline/token-aware implementation for #4f rather than depending on optional ast-grep. Cover all canonical nullness/truthiness matchers with multiline regression fixtures.

### [HIGH] #7 reports `.only(` inside string literals as an unsuppressible P0

Files:

- `/private/tmp/e2e-review-blind-final.Oy44Vy/skills/e2e-reviewer/scripts/scan.sh:1025`
- `/private/tmp/e2e-review-blind-final.Oy44Vy/skills/e2e-reviewer/scripts/scan.sh:1246`
- `/private/tmp/e2e-review-blind-final.Oy44Vy/skills/e2e-reviewer/SKILL.md:112`

Running the scanner on the included Cypress runtime fixture produced two #7 hits:

- Real `it.only` at line 9
- `expect("it.only('debug')")` at line 33

Because #7 explicitly bypasses JUSTIFIED suppression, the harmless string literal cannot be exempted and the default scanner exits `1`.

**Failure mode:** Meta-tests, codemods, documentation assertions, or tests inspecting focused-test text cannot pass the default P0 gate.

**Fix:** Detect executable `test.only`/`it.only`/`describe.only` call expressions, not raw substrings. Add string, template-literal, comment, and unrelated `.only()` receiver guards while retaining the no-exemption rule for genuine focus modifiers.

### [MEDIUM] Live benchmark runners inherit unrelated ambient secrets

Files:

- `/private/tmp/e2e-review-blind-final.Oy44Vy/scripts/evals/run-reviewer-holdout.py:471`
- `/private/tmp/e2e-review-blind-final.Oy44Vy/scripts/evals/run-reviewer-holdout.py:618`
- `/private/tmp/e2e-review-blind-final.Oy44Vy/scripts/evals/run-reviewer-holdout.py:623`
- `/private/tmp/e2e-review-blind-final.Oy44Vy/scripts/evals/run-reviewer-holdout.py:1174`

`clean_env()` copies the complete parent environment except CMUX/OMX variables and `CODEX_THREAD_ID`. A synthetic `REVIEW_SECRET=blind-review-proof` remained visible through `clean_env()`. The resulting environment is passed directly to Codex, Claude, or a custom runner.

A corpus controls its own `corpus_visibility`; declaring itself `public` avoids the mandatory isolation wrapper. Prompt-injected source can therefore expose unrelated API keys or tokens to model output and persisted reports.

**Fix:** Use a strict runner-specific environment allowlist containing only required authentication/configuration variables, explicitly redact report output, and require isolation or an explicit trust override for external case bundles regardless of self-declared visibility.

## Validation evidence

Passed within the snapshot:

- Pre-push security: **10/10 checks**
- Eval metadata: **54 evals**
- Reviewer scanner regressions
- Debugger contracts
- Local ESLint trust-path regression
- Verification parity
- Codex agent packaging
- Behavioral eval harness
- Fixture contracts: **33 synthetic classifications + 33 committed browser cells**
- Floating-Promise probes: **6/6**
- Timeout-zero probe: expected **1/0/1**, with fail-closed mutation checks

`ci-local.sh` could not complete because isolation deliberately removed benchmark directories and labeled corpora, making link/orphan and evidence-replay stages fail. Those isolation-induced failures were not scored as product defects.

## Evidence unavailable due to isolation

- Labeled v2/v3 holdout JSON and label oracle
- Prior raw model reports and cross-model scorecards
- Evidence manifests, prior reviews, and adjudication ledgers
- Fresh browser execution: pinned `node_modules` and browser binaries were absent
- Git revision, dirty-state, or change-diff evidence: the snapshot is not a Git checkout
- Live marketplace/install verification and external-link verification
- Modified-file LSP diagnostics: there is no diff or modified-file set in the exported snapshot

**REQUEST CHANGES**
