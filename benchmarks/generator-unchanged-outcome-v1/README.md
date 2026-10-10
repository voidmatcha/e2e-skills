# Targeted unchanged-outcome remeasurement v1

Status: **NO_TARGETED_SIGNAL**. All six frozen calls and their scoring completed. The targeted fault was killed in 3/3 before calls and 1/3 after calls. All six passed clean 3/3 and markup-refactor checks, with zero scanner P0 hits. Paired fault-kill non-worsening failed. This does not establish benefit or causally attribute worsening to the wording. Thirteen offline tests, review and security gates, and a four-test model-free scorer readiness run passed before launch. Full CI on this successor remains pending.

The before arm reached the ceiling, making the frozen strict-improvement decision unreachable in this sample. Posthoc raw-output review attributed two before kills to request payload assertions and one to the DOM primary; the single after kill was at the DOM primary. The two after misses asserted an already-true DOM value without action-completion evidence. All three after transcripts contain the added rule: missing reference reads do not explain these misses. Their V6 review requests did not include the generator's V1 completion contract. These observations motivate a successor, not an alteration of this frozen study or a general accuracy claim.

A separate source audit found that before r1 assigned application globals through `page.evaluate`, and before r3 rewrote served HTML to add an otherwise unreachable filter. The frozen scorer's scope guard did not capture these runtime interventions. Their self-reported `complete` statuses are not proof of approved-scope correctness; the frozen scores remain unchanged. This limitation is distinct from the targeted boundary assertion result.

Reports and generated candidates are retained under `reports/`. Raw transcripts and scoring stdout/stderr remain in the external `gen-unchanged-outcome-v1` cache because they contain machine-local paths. Their frozen SHA-256 bindings remain in `scores.json`; replaying analysis requires those original raw files. No raw originals were deleted.

This is a fresh, posthoc comparison on the public, spent `v3-02` fixture: three
paired repetitions, six generation attempts maximum. It measures the known
`f3-servings-below-one` boundary fault, not general skill accuracy or cost.
The before arm uses the frozen full-fixed generator. The after arm derives from
that exact snapshot and adds only the two new unchanged-outcome paragraphs.
The create-only freeze validates byte isolation and binds every source input.
Eval metadata is not supplied to either model arm. Common environment approvals
are identical; the rejected environment-guidance intervention is absent.

The scorer remains unchanged. Clean 3/3, refactor survival, P0, timeout, scope,
and paired effective fault-kill guards accompany the targeted count. Tool
indicators and self-reported status do not prove V4/V6 or causal fault attribution.
Raw transcripts must be retained outside this checkout. No USD claim is made.
Every scoring browser invocation retains its raw stdout/stderr with SHA-256
bindings, including infrastructure retries. The unchanged scorer summarizes the
final retry; earlier payloads remain in the complete raw manifest rather than
being separately attributed in its summary. Causal assertion attribution is
reviewed posthoc as described above; V4/V6 process compliance remains unverified.

A create-only external attempt-start ledger is written before each generation
attempt. An interrupted/unreported attempt prevents resume rather than spending
a seventh call. Scoring checks the disk floor before each browser invocation.

```bash
python3 scripts/ci/test-generator-unchanged-outcome-v1.py
python3 scripts/evals/run-generator-unchanged-outcome-v1.py plan
python3 scripts/evals/run-generator-unchanged-outcome-v1.py freeze
# Only after disk >= 4 GiB and explicit six-call authorization:
python3 scripts/evals/run-generator-unchanged-outcome-v1.py run --allow-live --output /absolute/cache/path/final.json
python3 scripts/evals/run-generator-unchanged-outcome-v1.py score /absolute/cache/path/final.json --output /absolute/cache/path/scores.json
python3 scripts/evals/run-generator-unchanged-outcome-v1.py analyze /absolute/cache/path/scores.json --output /absolute/cache/path/results.json
```
