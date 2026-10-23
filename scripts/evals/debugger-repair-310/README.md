# Debugger repair decision microexperiment

This contributor-only experiment asks Codex whether four proposed Playwright
repairs preserve an approved generated-test requirement. It compares a common
prompt with and without the current debugger contract and its relevant
references. The model judges supplied source, a constructed DOM, and a real
native error; it does not edit files, run a browser, or invoke a debugger skill
through host routing.

## Frozen design

Before the first model call, `run.py` writes four cases and expected labels, the
output schema, a two-arm schedule, the current skill/reference snapshot and
SHA-256 hashes. Each actual prompt, exact CLI command, native event stream,
structured answer, usage and receipt are retained in its cell directory. Model
calls use the existing holdout harness's configuration-free invocation and
private authentication staging. No API key, Claude invocation or global
configuration change is needed. Authentication copies are temporary private
runtime state and never enter evidence artifacts.

| Case | Proposed repair | Expected decision |
| --- | --- | --- |
| Mechanical selector | Follow an evidenced test-id rename of the same invoice | Accept repair, retain independent caller review |
| Widened wrong item | Search statuses globally and choose the last Paid item | Reject: alpha is Unpaid, beta is irrelevant |
| Relaxed expectation | Replace exact Paid with `/paid/i`, also matching Unpaid | Reject: approved expected state changes |
| Skip | Disable the failing scenario | Reject: scenario no longer runs |

The requirement always names invoice alpha and the exact Paid state. The first
case has evidence of locator drift; the other cases expose a product regression.
The model does not receive expected labels or results of candidate executions.
One mechanical case in both arms is the canary; malformed output, invalid native
controls, unexpected tool activity or changed frozen inputs stops expansion.

## Independent native controls

The harness separately runs actual Playwright tests against tiny authored
`page.setContent` DOMs, with one worker, zero retries and a pinned existing browser
executable. No third-party app or external service is contacted.

- Mechanical repair: original/current fails; repaired/current passes;
  repaired/wrong-state fails; repaired/healthy passes.
- Widened or relaxed repair: original/current fails; repaired/current,
  repaired/wrong-state and repaired/healthy all pass.
- Skip: original/current fails; all repaired variants report skipped, not passed.

A failure must include the expected assertion location. Native JSON reports,
stdout, stderr, exact generated specs and process-group cleanup receipts remain
outside Git. These controls demonstrate that each proposed repair has the
intended acceptance or weakening behavior; they do not establish model quality.

## Run

Supply explicit reviewed executables, dependencies and a fresh external output:

```bash
python3.12 scripts/evals/debugger-repair-310/run.py \
  --output /absolute/new-evidence \
  --runner-path /absolute/codex \
  --dependency-dir /absolute/reviewed-node_modules \
  --browser /absolute/reviewed-chromium-headless-shell \
  --node /absolute/node \
  --model gpt-6.1-sol --allow-live
```

This schedules eight calls: four cases, two arms and one repetition. Native CLI
JSONL events must contain one complete turn and no model tool calls. The primary
score requires the correct repair decision, diagnosis axis and preservation
judgment together; F-code accuracy is separate. Do not count repetitions or arms
as independent defects. The full-context prompt is substantially longer and its
actual token usage must remain visible even when both arms answer correctly.

## Limits

Four public authored cases and one repetition are a feasibility check. Inputs
make the requirement and contrasting DOM explicit; this is easier than finding
the cause in an unfamiliar repository. The experiment cannot verify interactive
skill triggering, artifact-reader routing, repair execution, scanner invocation,
V6 completion or real-world superiority. A tied result supports keeping the
current guardrails; it does not show that the extra context improves accuracy.

## 2026-10-21 observed result

The local run used `gpt-6.1-sol`, Codex CLI 0.159.3, cached Playwright 1.63.0,
TypeScript-independent authored JavaScript specs, and existing Chromium headless
shell revision 1234. Both arms scored **4/4 on the primary decision**. Both accepted
the mechanical correction and rejected all three weakening candidates. There was
no observed incremental decision-accuracy benefit.

| Arm | Primary correct | Input tokens | Output tokens | Call duration total |
| --- | --- | --- | --- | --- |
| Baseline | 4/4 | 51,447 | 995 | 44.6 seconds |
| Debugger context | 4/4 | 85,919 | 1,022 | 46.1 seconds |

Input totals include the CLI's reported context overhead. Cached input was
10,240 tokens for baseline and zero for context, so these totals are not a
pricing comparison. F-code agreement was 2/4 versus 4/4; only the context arm was
given the F-code definitions, making this a label-definition effect rather than
independent evidence of better causal diagnosis. All eight native streams had
zero model tool events, including started and completed items. Sixteen native
report/spec hash pairs and frozen inputs were freshly verified.

Evidence is external under
`$HOME/.cache/e2e-skills-bench/debugger-repair-310-20261021-v1/`; use `result.json`
and `verification-receipt.json` for exact hashes and per-cell decisions. No product
skill was modified on the basis of this tied microexperiment.
