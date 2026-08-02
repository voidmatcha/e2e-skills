# Final re-audit of the holdout v3 oracle

## Current post-remediation audit

Current snapshot freeze time: 2026-07-30 08:29 KST.

Patterns #15 and #16 are P1 in the current taxonomy. Playwright 1.62 live
probes and runner-source inspection showed that their rejected floating
Promises normally fail the test worker rather than necessarily producing a
silent always-pass result. Their invariant defect is unsequenced work and poor
failure attribution; a swallowed rejection remains #3 P0, and an independently
missing postcondition may remain #2 P0.

### Blind source-audit failure and corpus repair

Two fresh auditors first received a physically isolated bundle containing only
the holdout sources, `SKILL.md`, and `pattern-reference.md`. They were barred
from the labeled JSON, reports, scores, prior audits, Git, memory, and parent
directories. Both independently reconstructed **22**, not 24, findings:
5 P0, 14 P1, and 3 P2.

Their agreement exposed two real oracle-design defects rather than model
mistakes:

- `cy-contract-runtime/cypress/e2e/invoices.cy.ts:10` did not make the
  promised restoration outcome explicit enough for #2; and
- `pw-context-boundaries/tests/locator-discard.spec.ts:5` still had an
  independent meaningful status assertion, so it contradicted the #8 P0
  contract.

The benchmark source was repaired before the current model run. The archive
test title now explicitly promises invoice restoration while intentionally
omitting restoration proof, and the dangling-locator test no longer contains
an independent postcondition. No label, severity, threshold, prompt, or
schedule was changed to fit model output.

Two new source-only auditors then received a newly created isolated bundle.
They independently reconstructed:

- 24 findings and one representative false-positive guard for every normalized
  family;
- all 24 stable families exactly once;
- 7 P0, 14 P1, and 3 P2 findings;
- #2 at `cy-contract-runtime/cypress/e2e/invoices.cy.ts:10`; and
- #8 at `pw-context-boundaries/tests/locator-discard.spec.ts:5`.

The labeled corpus itself contains 24 explicit finding anchors and 24 explicit
guard anchors. The corpus schema stores `source_line` as the physical source
line after leading and trailing whitespace is removed.

### Current semantic inputs

| Input | SHA-256 |
|---|---|
| `scripts/evals/reviewer-holdout-v3.json` | `8ae568feceb7bca280441301fdcda0318c92b1552faaeec28d565a203838b08d` |
| Canonical corpus plus staged sources | `4dc569b6d583e2cebca3fa71f7cf59eb1f8948f7cff0d7882f3f2efefcbd597c` |
| `scripts/evals/reviewer-validation-protocol-v3.json` | `860c1207bcfe441e411609cecc1fd0aa287304e192563a737bdb2536a43d7731` |
| `skills/e2e-reviewer/**` | `0ef4839b6bde078a4599e6354dcd60bb522c01a91534086d6f292d5217018214` |
| `skills/e2e-reviewer/SKILL.md` | `0e748bd0e12347b136a38d8283cd7fe5aec6dd9719f29ccd49f3a1acbb3191ec` |
| `skills/e2e-reviewer/references/pattern-reference.md` | `dc9e592f71959036f211c54f7a310161520fa63229ecf17c5a56116ce4a2d7db` |
| `skills/e2e-reviewer/scripts/scan.sh` | `6354925f9e40e80074ab4088b8f9b22ff8ec9faebb4e377533178e71cf2661f1` |
| `scripts/evals/run-reviewer-holdout.py` | `e25d99f3d6a3c82cd1d87fd3215e2e07d7ed67777465d8986352eb87f0ebf987` |
| `scripts/evals/compare-reviewer-holdouts.py` | `f905cd3aa68390bca2cb76d2aa9ad43c9f91bc16aece6c462558a22fdee51e5a` |

These remain model audits from the same Codex family and written taxonomy, not
independent human annotations. They establish reproducible internal
consistency and show that the first blind audit was allowed to invalidate the
oracle. They do not estimate unseen-repository generalization.

## Historical pre-reclassification snapshot

Final snapshot freeze time: 2026-07-30 01:49 KST.

Historical-only notice: the later #15/#16 P0-to-P1 reclassification invalidates
this frozen oracle and all metrics derived from it for the current taxonomy.
Rows and digests below are intentionally preserved as the historical snapshot.

This is a public development corpus. Pre-remediation model output and product
reviews were visible before the final snapshot, so this audit establishes
internal consistency and reproducibility, not blind or sealed generalization.
The original pre-remediation audit remains in
`oracle-audit-pre-remediation.md`.

## Frozen semantic inputs

| Input | SHA-256 |
|---|---|
| `scripts/evals/reviewer-holdout-v3.json` | `fb7f5eb8560687ee8d8a9fedac24fb0f4b674e54e9c610b76404a30330fc4a2d` |
| Canonical corpus plus staged sources | `ee57b615cc63e7ce8716d9d419d09b48226b81194e3bce3965d9053ffd9f8daa` |
| `scripts/evals/reviewer-validation-protocol-v3.json` | `860c1207bcfe441e411609cecc1fd0aa287304e192563a737bdb2536a43d7731` |
| `skills/e2e-reviewer/**` | `a282b3cc9740d76cc32fdd77245a7330f725406378f45e89933d7fadd70f43d9` |
| `skills/e2e-reviewer/SKILL.md` | `1fc20c16d9d71a8615ee20325f29d6768e495ca8ea177b731a47e075bc52d360` |
| `skills/e2e-reviewer/references/pattern-reference.md` | `6f76925d7751c0f66a82f8bd86e0129eb0c4cecdcddba3d054757f67488269d0` |
| `skills/e2e-reviewer/scripts/scan.sh` | `eee4731053f0f6e37b53a5dabd3a5ce7f0e3a9834156c61cbef5a6905e0df5c6` |
| `scripts/evals/run-reviewer-holdout.py` | `da20df81569ea037d291a1f8342f72b550063c9b76035a54749a755be5483856` |
| `scripts/evals/compare-reviewer-holdouts.py` | `54e9632ff7cebd8d6d05a6877f00dbfca0146b8851f5d5f3f6d45114442e8a98` |

Every final report must record the same canonical corpus, complete skill,
protocol, evaluator, prompt-set, schedule, and staged-workspace digests. The
runner verifies original and copied inputs before and after every call; the
comparator re-parses raw output and rejects provenance mismatches.

## Independent source-only reconstruction

Two fresh Codex-native auditors independently read only:

- `scripts/evals/files/holdout-v3/**`
- `skills/e2e-reviewer/SKILL.md`
- `skills/e2e-reviewer/references/pattern-reference.md`

They were barred from the labeled corpus, reports, mutation notes, prior
reviews, oracle files, and Git history. Neither changed files. Both
independently reconstructed exactly:

- 24 non-overlapping findings;
- every one of the 24 base pattern families;
- 9 P0, 12 P1, and 3 P2 findings; and
- no additional defensible finding after the title/anchor correction.

| Family | Severity | Gold source |
|---|---|---|
| #1 | P0 | `cy-contract-runtime/cypress/e2e/invoices.cy.ts:2` |
| #2 | P0 | `cy-contract-runtime/cypress/e2e/invoices.cy.ts:10` |
| #3 | P0 | `pw-rejection-state/pages/report-page.ts:11` |
| #3b | P0 | `cy-contract-runtime/cypress/support/e2e.ts:1` |
| #4 | P1 | `pw-rejection-state/tests/report.spec.ts:9` |
| #5 | P1 | `pw-rejection-state/pages/report-page.ts:16` |
| #6 | P1 | `pw-context-boundaries/tests/admin-unprotected.spec.ts:12` |
| #7 | P0 | `pw-context-boundaries/tests/admin-unprotected.spec.ts:3` |
| #8 | P0 | `pw-context-boundaries/tests/locator-discard.spec.ts:5` |
| #9 | P1 | `cy-command-timing/cypress/e2e/search.cy.ts:10` |
| #10 | P1 | `cy-command-timing/cypress/e2e/search.cy.ts:16` |
| #11 | P2 | `cy-structure-fixture/cypress/pages/catalog-page.ts:10` |
| #12 | P0 | `pw-context-boundaries/tests/admin-unprotected.spec.ts:5` |
| #13 | P1 | `pw-pom-async/tests/settings.spec.ts:7` |
| #14 | P1 | `cy-write-credentials/cypress/e2e/profile.cy.ts:5` |
| #15 | P0 | `pw-pom-async/tests/settings.spec.ts:10` |
| #16 | P0 | `pw-pom-async/tests/settings.spec.ts:12` |
| #17 | P1 | `pw-maintenance-provenance/tests/preferences.spec.ts:5` |
| #18 | P1 | `pw-maintenance-provenance/tests/preferences.spec.ts:17` |
| #19 | P1 | `pw-maintenance-provenance/support/recent-users.ts:3` |
| #20 | P1 | `cy-write-credentials/cypress/e2e/profile.cy.ts:20` |
| #21 | P2 | `pw-maintenance-provenance/playwright.config.ts:7` |
| #22 | P1 | `cy-write-credentials/cypress/e2e/board.cy.ts:6` |
| #23 | P2 | `cy-structure-fixture/cypress/fixtures/guarded-product.json:3` |

The auditors specifically rejected nearby false positives for application
methods named `only`, invalid-password test data, justified forced actions,
retry-wrapper one-shot URL reads, proven absence assertions, authenticated
counterparts, and actions inside `Promise.all`.

These are model audits from the same Codex family and written taxonomy, not
independent human annotations. They support consistency but do not remove
author, model-family, or public-corpus bias.

Licensed under Apache-2.0 with the repository.
