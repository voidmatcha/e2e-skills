# Isolated remediation round 1 — product review

Date: 2026-07-30  
Decision: **REQUEST CHANGES**  
Score: **83/100**

The reviewer used a no-Git, temporary-HOME snapshot with global skills, local
state, labeled corpora, prior reviews, model reports, and reviewer benchmark
directories physically absent.

| Category | Score |
|---|---:|
| Behavior correctness | 22/25 |
| Scanner precision and recall robustness | 18/20 |
| Benchmark validity and unbiasedness | 16/20 |
| Executable evidence | 12/15 |
| Documentation and product clarity | 8/10 |
| Maintainability and security | 7/10 |
| **Total** | **83/100** |

## Findings

1. The floating-Promise evidence archive referenced the pre-hardening fixture
   helper digest and failed its current dependency check.
2. Generator approval did not disclose later `AGENTS.md` / `CLAUDE.md`
   control-file mutations.
3. Shell-syntax gates could report success after a missing/failing `find`
   enumerated zero files.
4. Ignored local `docs/superpowers/**` files were accidentally included in the
   review snapshot and appeared orphaned. They are not part of the repository
   product surface; later blind snapshots must exclude them.

Items 1–3 are real and require source/evidence fixes. Item 4 is a snapshot
construction defect and is not treated as a repository defect.

