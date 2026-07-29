# Cross-Framework Verification Rules (V1–V6)

<!-- V-RULE-CONTRACT: V1=primary-outcome;V2=assertion-falsification;V3=behavior-fault-injection;V4=write-contract-proof;V5=repeat-and-isolation;V6=independent-re-review;verdicts=PASS,FAIL,CANNOT_VERIFY,ERROR;source=immutable;install=forbidden -->
<!-- V-RESULT-SCHEMA: candidate,runner,verification.V1,verification.V2,verification.V3,verification.V4,verification.V5,verification.V6,sourceUnchanged,temporaryArtifactsRemaining -->

V-rules are runtime proof recommendations, not new smell IDs. Keep the 24-pattern taxonomy and F1-F15 failure taxonomy stable.

| ID | Contract | Playwright proof | Cypress proof |
|---|---|---|---|
| V1 | One primary observable outcome matches the title/actions | one load-bearing web-first assertion | one load-bearing retryable `.should()`/`expect` assertion |
| V2 | Safely invert the primary assertion in a temporary copy; expect red | `.toBeVisible()` ↔ `.not.toBeVisible()`, text/URL/count equivalents | `'be.visible'` ↔ `'not.be.visible'`, text/value/length equivalents |
| V3 | Corrupt an evidenced dependency; unchanged assertion must turn red | `page.route()` or existing fixture | `cy.intercept()` or existing fixture |
| V4 | Prove write method/endpoint/payload/cardinality and failed-write behavior | `waitForRequest`, route-hit capture | alias/intercept plus `cy.wait()` request inspection |
| V5 | Pass bounded solo, repeat, suite-context, and supported parallel checks | repository-native Playwright script | repository-native Cypress script/repeat facility |
| V6 | A writer/debugger cannot approve its own output | rerun e2e-reviewer after repair | rerun e2e-reviewer after repair |

Verdicts: `PASS`, `FAIL`, `CANNOT_VERIFY` with a concrete reason, or verifier `ERROR`. Do not install packages, require `npx`, mutate the trusted source spec, invent an endpoint, or treat a verifier error as a product defect.

## Project-rule merge

Discover `AGENTS.md`, testing docs, package scripts, ESLint config, framework config, CI, fixtures, POMs/custom commands, and existing verifier tooling before reviewing.

1. **Equivalent:** emit one finding with both project-rule and e2e-skills provenance.
2. **Project stronger:** follow it for generation and report a project-convention issue only at its warranted severity.
3. **e2e-skills stronger/semantic:** keep the e2e-skills finding; a green linter cannot prove intent.
4. **Conflict:** P0 silent-pass safety wins over style. P1 can be suppressed only by a concrete local rationale; P2/style follows project convention.

Existing project lint is evidence, not a dependency. Run its documented repository-native lint command when available; the bundled scanner remains the deterministic baseline. Never auto-download ESLint, plugins, AST tools, or mutation tools.

## Finding-to-proof map

| Pattern | Recommended verification |
|---|---|
| #1 name/assertion mismatch, #2 missing Then | V1, then V3 when an evidenced dependency exists |
| #3/#3b error swallowing, #5 conditional assertion, #8 missing assertion, #15/#16 missing await | V2 |
| #4 always-passing, including #4i unproven absence | V2; V3 for selector/data provenance |
| #9/#10 flaky patterns, #19 mutable state | V5 |
| #20 unmocked real writes | V3 + V4, without touching production/third-party systems |
| #22 optimistic UI without call proof | V3 + V4 |

Runtime proof remains optional in a static review. Recommend only the smallest evidence-backed probe; do not claim it ran unless an actual command and result are available.

When runtime proof is actually requested, require a structured result containing the candidate path, repository-native runner, explicit V1–V6 verdict objects, evidence or a concrete reason, `sourceUnchanged`, and `temporaryArtifactsRemaining`. Missing applicable V-rules are not implicit passes. Static review output does not fabricate this object when no runtime command ran.
