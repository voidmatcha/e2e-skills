# Isolated remediation round 1 — adversarial review

Date: 2026-07-30  
Decision: **FAIL / REQUEST CHANGES**  
Score: **77/100**

The reviewer used a no-Git, temporary-HOME snapshot with global skills, local
state, labeled corpora, prior reviews, model reports, and reviewer benchmark
directories physically absent.

| Category | Score |
|---|---:|
| Behavior correctness | 22/25 |
| Scanner precision and recall robustness | 14/20 |
| Benchmark validity and unbiasedness | 15/20 |
| Executable evidence | 11/15 |
| Documentation and product clarity | 8/10 |
| Maintainability and security | 7/10 |
| **Total** | **77/100** |

## Findings

1. Comparator recomputation did not propagate non-public
   `source_read_isolation`, so rewritten reports could drop the isolation gate.
2. The floating-Promise archive had stale helper provenance.
3. Aliased Playwright test bindings such as `pwTest.only` could bypass #7.
4. Unresolved workspace/path-alias fixtures were conservatively admitted only
   for #7, allowing other candidates to disappear instead of reaching triage.
5. Colon-containing filenames broke colon-delimited hit parsing.
6. Framework-scope CI enforced only Puppeteer although contributor policy
   declares five excluded frameworks.

The review snapshot did not contain the labeled oracle, prior metrics, Git,
external skills, or machine-local logs. All findings above are source-level;
the stale evidence item was refreshed through the live six-cell runner after
this snapshot.
