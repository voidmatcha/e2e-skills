# B-lite actual-generation observation

This directory preserves one baseline and one skill-guided Playwright generation
for the React optimistic-write example. Both canonical model calls used Codex
`gpt-5.6-sol` at `xhigh` reasoning in independent, matched, auth-only staged
homes. The candidate matrix then ran sequentially in disposable product copies
with private Vite caches and separate arm ports.

## Result

| Arm | Normal | `omit-post` | `reject-post` | Direct write proof |
|---|---|---|---|---|
| Baseline | Pass | Causal red | Causal red | Absent |
| Skill-guided | Pass | Causal red | Causal red | Exactly one `POST /api/like` with `{ liked: true }` on the normal path |

Both fault runs in both arms stopped at the unchanged exact
`Saved on server.` assertion. They did not reach the later post-reload primary
assertion. The guided output therefore adds request-count and payload evidence,
but this `n=1` observation shows no fault-kill difference.

That request proof was explicitly required by the guided prompt. Its presence
shows compliance with the full guided treatment; it is not an independently
discovered advantage. The two arms intentionally compare a minimal generation
prompt with the skill workflow's approved-scenario contract, not identical
prompts that differ only by hidden skill context.

The bundled reviewer scanner found zero P0 candidates. Its two baseline #10c
triage hits were skipped under the pattern contract because `Like article` is a
distinctive multi-word name on a static-only surface; the guided candidate used
`exact: true`. Neither candidate was repaired or mutated.

The comparative status is **INCONCLUSIVE**. This is a public, prompt-complete
development case with one generation per arm, not a sealed or representative
accuracy evaluation.

## Canonical artifacts

- `protocol.json` and `freeze.json` hold the pre-generation contract and input
  digests.
- `skill-material/` is the immutable local snapshot of the evaluated
  `playwright-test-generator` files. It intentionally does not track the
  repository's current skill files.
- `protocol-amendment.json` records why later clean regeneration and sequential
  execution were required without rewriting the frozen protocol.
- `provenance.json` records model-call lineage, usage, isolation, and exclusions.
- `raw/baseline.md` and `raw/skill-guided.md` are the canonical raw outputs.
- `candidates/*.spec.mjs` are mechanical fence-body extractions.
- `execution.json` and the six top-level `logs/*.txt` files are the canonical
  execution record.
- `results.json` contains the causal adjudication and claim boundary.

## Excluded provenance

The ambient baseline and ambient guided outputs are retained with
`-contaminated` names. The baseline discovered a global skill; both ambient
calls lacked matched staged homes. `execution-attempt-1.json` is also excluded
because parallel runs shared writable Vite cache state and the first normal
baseline hit an optimizer-cache rename error. The second attempt fixed the
runtime isolation but still used contaminated candidates. A first clean
baseline output is retained but excluded because it was generated before both
arms were rerun as a matched pair.

## Verify

From the example directory:

```bash
node --test scripts/test-b-lite-evidence-tools.mjs
node scripts/verify-b-lite-evidence.mjs
```

The verifier recomputes frozen-input, raw-output, candidate, and log hashes;
checks byte-for-byte candidate extraction and unchanged candidate execution;
and enforces the recorded normal/fault exit split.
