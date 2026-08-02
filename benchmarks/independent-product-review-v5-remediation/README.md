# Independent product review v5 remediation confirmation

Current gate: **FAIL** — 3 preregistered attempts are archived and at least one failed.

This archive is a post-hoc targeted confirmation of the raw-ARIA
ambient-environment remediation identified by the r16 Codex review. V4 remains failed;
v5 cannot retroactively change that result.

The preregistered phase uses one frozen 30-file packet and exactly three fresh,
prompt-complete, zero-tool `codex` / `gpt-5.6-sol` attempts. It is not unbiased
defect discovery, not cross-model evidence, not full-product coverage, not an
accuracy measurement, not human review, not sealed review, not independent
ground truth, and not remote model attestation.

Evidence state: Exactly three preregistered model attempts are archived. After all three exact
attempts are ingested, this table contains one immutable row per attempt and
the gate passes only if every independently re-derived verdict is `PASS`.

<!-- V5_ATTEMPTS:START -->
| Attempt | Model | Score | C | H | Verdict |
| --- | --- | ---: | ---: | ---: | --- |
| codex-high-fix-r1 | gpt-5.6-sol | 87.33 | 0 | 2 | FAIL |
| codex-high-fix-r2 | gpt-5.6-sol | 88.00 | 0 | 1 | FAIL |
| codex-high-fix-r3 | gpt-5.6-sol | 88.00 | 0 | 1 | FAIL |
<!-- V5_ATTEMPTS:END -->
