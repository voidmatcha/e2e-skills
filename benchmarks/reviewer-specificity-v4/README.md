# Reviewer specificity v4 — blocked by an infeasible selection contract

Protocol: **FROZEN**. Collection: **BLOCKED**. Evaluation: **NOT_RUN**. Result: **NONE**. Scanner candidates are not admitted clean cases.

The first real batch scanned 10 of 150 extracted spec closures from one eligible repository: four candidate cases and six scans without hits. Another 195 specs had unresolvable closures. One Claude adjudication invocation was started and canceled when the feasibility defect below was identified; no adjudication pass completed and no evaluated-model call started. Local artifacts are preserved, but they are not a completed corpus or benchmark result.

**Blocking defect:** the exact frozen scanner emits only 16 principal pattern IDs. It has no candidate generators for `#1`, `#2`, `#12`, `#13`, `#20`, `#21`, `#22` or `#23`. Tier 2 only adds `#4` and `#15`, already represented in Tier 3. Requiring a scanner-generated principal case for every one of 24 patterns is therefore impossible regardless of repository count. This requirement was inherited from v3 and was not repaired by v4's lazy-order changes. The preflight now fails before additional collection or adjudication calls. Do not relax this frozen protocol in place. A successor needs either independently specified semantic candidate discovery or an explicitly narrower claim and redesigned allocation.

[V4](../../scripts/evals/reviewer-specificity-protocol-v4.json) succeeds [v3](../reviewer-specificity-v3/README.md) without modifying its frozen protocol. An implementation audit found that the lazy collector's nested-manifest eligibility and per-spec scans do not implement v3's root-only eligibility and repository-wide hit order. V4 registers the operational rule explicitly; it does not claim the two selection methods are equivalent.

## Selection contract

- Reuse all 40 search responses from the complete 2026-09-22 snapshot, without refreshing or selecting pages. The original inventory contains 4,000 framework-specific rows, not 4,000 unique eligible repositories. The protocol records its original SHA-256; the importer records the mechanically reordered inventory digest.
- Verify repositories by rank, then framework (Playwright before Cypress). A valid dependency declaration in any pinned `package.json` qualifies. Public visibility, licence evidence and prior-use exclusions remain required.
- Extract each eligible repository before scanning it. Repository-level extraction remains eager; only scanner execution is lazy. Do not describe the extraction cost as bounded by the scanner batch size.
- Scan complete spec closures in repository order, then POSIX spec-path order. Default invocation limits are 10 scans and five new candidate cases. Terminal scan records precede a `not-yet-scanned` suffix; later extraction may only extend the existing order.
- Group a spec's hits into one candidate. Its first hit in path, line, taxonomy and source-byte order supplies one principal guard. Multiple hits cannot create duplicate cases or fill multiple principal slots.
- Require two fresh, mutually blinded Claude-model passes, both whole-case clean across all 24 patterns. Preserve disputed candidates in the ledger. Enforce repository and lineage caps.
- Do not evaluate below 24 admitted cases or with any missing principal pattern. The target remains 48. Counts, missing slots and stopping depth must accompany an early stop at the allowed minimum.

The evaluated Codex host, three arms, three repetitions, metrics and thresholds are unchanged. The adjudication runner disables model tools, uses isolated fresh working directories and the existing credential-isolated runner, includes complete files in the prompt, and excludes scanner labels, other verdicts and treatment output. Model identifiers are recorded provenance, not provider revision attestation.

## Commands

Run serially. Keep working artifacts outside the checkout. Set `GITHUB_TOKEN` through the account's normal credential manager without printing it.

```bash
python3 scripts/evals/collect-reviewer-specificity-v4.py walk \
  --output /path/to/v4-artifacts --snapshot-source /path/to/specificity-v3-20260922
python3 scripts/evals/collect-reviewer-specificity-v4.py preflight --output /path/to/v4-artifacts
python3 scripts/evals/collect-reviewer-specificity-v4.py verify --output /path/to/v4-artifacts
python3 scripts/evals/collect-reviewer-specificity-v4.py extract --output /path/to/v4-artifacts
python3 scripts/evals/collect-reviewer-specificity-v4.py scan --output /path/to/v4-artifacts
python3 scripts/evals/collect-reviewer-specificity-v4.py assemble --output /path/to/v4-artifacts
python3 scripts/evals/adjudicate-reviewer-specificity.py \
  --output /path/to/v4-artifacts --models claude-opus-5 claude-fable-5 \
  --runner-path /absolute/path/to/claude --allow-live --max-candidates 5
python3 scripts/evals/collect-reviewer-specificity-v4.py ledger \
  --output /path/to/v4-artifacts --adjudications /path/to/v4-artifacts/adjudications
python3 scripts/evals/collect-reviewer-specificity-v4.py validate --output /path/to/v4-artifacts
```

The commands after `preflight` describe the implemented workflow, not permission to bypass its failing gate. The current v4 preflight rejects further execution. The ledger implementation can otherwise validate an incomplete collection and reports `NOT_READY`; corpus validation and publication reject incomplete coverage. A model or infrastructure failure is not a finding, clean verdict or completed pass. Evaluation and comparative publication remain pending.

Protocol SHA-256: `032ed21b48d18a98cb97b3cf9da51b8f5056464626e07c3a8378ff2139457c7f`.

The [exploratory semantic-successor design](semantic-successor-design.md) defines a separate, bounded pilot for the missing candidate-generation lane. It does not unblock v4 or freeze a new evaluation protocol.

The [completed exploratory pilot](semantic-pilot-results.md) ran three discovery calls and two blind passes. Both passes returned findings on the selected candidate, so no case was admitted and no evaluation started.

The [successor sampling decision](successor-sampling-decision.md) separates 24-pattern whole-case review from per-pattern clean-sample quotas, proposing a primary ordered clean cohort and a separately reported lookalike challenge cohort. It remains a development draft, not a frozen executable protocol.
