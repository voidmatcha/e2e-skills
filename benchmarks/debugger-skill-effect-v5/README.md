# Debugger skill-effect v5: Playwright answer-contract candidate (2026-10-10)

Status: **development comparison, not a holdout. The preregistered rule returned `SUPPORTED_DEVELOPMENT_SIGNAL`, but the margin is one tied-to-better case, so this does not justify shipping or extending to Cypress.** The candidate is kept only as a snapshot; `skills/` is unchanged.

## What was tested

Candidate (`skill-snapshots/candidate`): the working-tree `playwright-debugger` plus a "Default answer" section (observed failure → most likely cause with evidence → smallest check → fix; F-code last and optional; origins the artifact does not show go to `CANNOT_VERIFY`), a "Not verifiable" finding field, and an output schema with `cannot_verify` and `f_code: none`. All safety, redaction, no-follow, exact-command-approval and V1–V6 text is byte-identical. Compared with `current` (same snapshot without the edit, F-code schema) and a taxonomy-free prompt on the 14 Playwright cases of the v3 corpus (real merged fixes), Claude `claude-sonnet-5-5`, zero tools, 3 repetitions, 126/126 calls scored. Blind Codex `gpt-6-sol` judges: the v2 mechanism rubric, and a new count of root-cause claims the excerpt does not support (sees the excerpt only, not the truth or arm). Protocol and digests: [`protocol.json`](protocol.json); results: [`reports/results.json`](reports/results.json).

## Results

| Metric | candidate | current | free |
| --- | ---: | ---: | ---: |
| Strict mechanism match | 0.762 | 0.738 | 0.786 |
| Product/test diagnosis matches maintainers | 0.833 | 0.786 | 0.786 |
| Unsupported claims per answer (mean) | 1.48 | 1.57 | 2.31 |
| Answers with any unsupported claim | 0.69 | 0.76 | 0.83 |
| F-code exact (labeled cases) | 0.47 | 0.69 | n/a |
| Output tokens / summed call time (42 calls) | 61,332 / 521 s | 29,973 / 355 s | 15,949 / 256 s |
| Input tokens, cache included | 1.15 M | 1.44 M | 0.14 M |

Paired (case-cluster bootstrap): strict candidate − current +0.024 (95% CI 0.000 to +0.071; 1 better, 0 worse, 13 tied); unsupported claims candidate − current −0.10 (CI −0.69 to +0.50; 5 better, 8 worse, 1 tied), i.e. no detectable difference; skill arms had fewer unsupported claims than free (CI excludes 0). Current − free strict −0.048.

## Reading

- Root-cause identification: tie. The free prompt remained at least as accurate as either skill arm, repeating v2–v4.
- Unsupported assertions: candidate not distinguishable from current. `cannot_verify` was non-empty in 42/42 candidate answers, so it behaves as a filled-in field rather than a discriminating signal.
- Cost: the candidate doubled output tokens and was 1.5× slower per call, the opposite of a lighter flow. F-code agreement fell by design (it is optional) and is not a loss of correctness.
- My rule's "strict > 0" clause was satisfied by a single case; it was too permissive and should not be reused.

## Limits

Cases overlap v3, which informed the candidate, so this is not independent; zero-tool prompts do not test CI download, reader, or safety flow; model judges; one host; schemas differ between arms by design; 14 cases. The 100-event CI-artifact set was not used because only one event has a maintainer-linked cause ([debugger-ci-artifacts-v1](../debugger-ci-artifacts-v1/README.md)).

Reproduce: `python3 scripts/evals/run-debugger-skill-effect-v5.py run|judge|analyze` (see its docstring). Raw calls stay in `~/.cache/e2e-skills-bench/debugger-v5/`.
