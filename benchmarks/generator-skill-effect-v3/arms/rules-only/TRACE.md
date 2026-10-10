# Rules-only arm derivation trace

Every section of `RULES.md` is a verbatim copy of a section of the `full-fixed` skill snapshot (`arms/full-fixed/playwright-test-generator/`), selected by heading and copied without edits; only the frontmatter, the title and the two-sentence preamble (`HEAD.md`) are new. Line numbers refer to that snapshot at derivation time; `derive.py` regenerates the file and this table and fails when a heading has moved.

| RULES.md section | Source | Lines copied |
| --- | --- | ---: |
| code-rules.md § Hard rules | `code-rules.md:5-15` | 11 |
| code-rules.md § Selector Priority (with the text-only rule) | `code-rules.md:29-45` | 17 |
| best-practices.md § Locators | `best-practices.md:34-42` | 9 |
| best-practices.md § Assertions (web-first) | `best-practices.md:44-52` | 9 |
| code-rules.md § Spec Rules, forbidden table and await rule | `code-rules.md:131-149` | 19 |

Dropped from the skill: every workflow step (environment detection, coverage-gap analysis, exploration, scenario design and approval, code generation procedure, YAGNI audit, e2e-reviewer gate, V1–V6 verification, completion report), the structure-detection and POM template sections, network determinism, SSR, auth, branch seeding, the suppression-convention list (the `// JUSTIFIED:` requirement itself survives inside the copied Selector Priority text), and every safety and approval rule. Nothing was added.
