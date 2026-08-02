# Independent product review v6 selected-remediation confirmation

Current gate: **NOT RUN (SUPERSEDED_BEFORE_FREEZE)** — no packet was frozen, no model was called, and 0 of 3 preregistered attempts were executed.

This archive is a post-hoc confirmation of five selected remediations made
after the completed v5 failure. V4 remains failed, and v5 remains
`COMPLETE` / `FAIL`; v6 cannot retroactively change either result. The separate
remediation ledger also records the evidence-backed false-positive disposition
for the other v5 r1 High finding.

<!-- V6_SUPERSESSION:START -->
An independent pre-call check found a protocol-design defect: the v6 byte
budget measured transformed source bytes, not the larger line-annotated
representation embedded in the prompt. Because no packet had been frozen and
no model had been called, v6 was superseded rather than amended. The immutable
`supersession.json` records the measured representation and binds the corrected
v7 successor schedule.
<!-- V6_SUPERSESSION:END -->

The preregistered phase uses one frozen 30-file packet and exactly three fresh,
prompt-complete, zero-tool `codex` / `gpt-5.6-sol` attempts. The remediation
ledger and prior reports stay outside the model packet and prompt. This is not
unbiased defect discovery, not cross-model evidence, not full-product coverage,
not an accuracy or skill-lift measurement, not human review, not sealed review,
not independent ground truth, and not remote model attestation.

Evidence state: The immutable supersession record is archived; no packet, reservation, model call, raw response, or report exists. Exactly 0 of 3 preregistered attempts were executed under v6.

<!-- V6_ATTEMPTS:START -->
| Attempt | Model | Score | C | H | Reopened targets | Verdict |
| --- | --- | ---: | ---: | ---: | --- | --- |
<!-- V6_ATTEMPTS:END -->
