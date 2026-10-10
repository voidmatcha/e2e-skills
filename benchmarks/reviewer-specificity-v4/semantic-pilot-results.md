# Semantic discovery pilot — 2026-09-22

Status: **EXPLORATORY COMPLETE; NO ADMITTED CASES; EVALUATION NOT RUN**.

The [draft design](semantic-successor-design.md) was exercised against the existing extraction snapshot, without new network collection or changes to either frozen protocol. This is a local pilot summary, not a published raw benchmark archive or an accuracy result.

## Executed schedule

The stable prefix contained 44 rows. The first three root specs directly importing Playwright's `test` occurred at positions 42–44, all in `freeCodeCamp/freeCodeCamp`: `e2e/action-row.spec.ts`, `e2e/backend.spec.ts`, and `e2e/block-navigation.spec.ts`. Selected source bytes were checked against extraction hashes before and after execution.

Exactly five fresh tool-free model calls ran serially: three Fable discovery calls, followed by Opus and Fable whole-case passes on the first proposed candidate. No model call was retried. Two initially rejected responses were recovered offline after the parser and taxonomy-validator repairs disclosed in the design; their original incomplete records and raw responses remain unchanged. Thus completion includes two disclosed validator recoveries, not five originally successful validations.

| Stage | Observed result |
| --- | --- |
| Discovery, all three specs | Each proposed `#1`; each reported insufficient context for `#21` |
| Discovery, backend spec | Also reported insufficient context for `#20` and `#22` |
| Blind Opus pass, action-row | `finding`: three P1 family `#4` proposals, explained as subtype `#4i`, at lines 24, 42 and 75 |
| Blind Fable pass, action-row | `finding`: three P1 `#4i` proposals at the same lines |
| Admission | No two-clean agreement; zero admitted cases; `evaluation_allowed: false` |

These are model-reported findings, not independently verified upstream defects. The blind prompts did not expose discovery output or the other verdict. Separate sessions do not eliminate shared-provider/model bias. The pilot demonstrates a selection-to-blind-verdict path and rejection of a non-clean candidate; it does not establish oracle correctness, clean yield across eight semantic IDs, 24-slot feasibility or specificity lift.

## Required next work

1. Define deterministic contextual expansion for configuration references, including setup-project `testMatch` files and storage-state producers. The import-only closure supplied the config but omitted `global-setup.ts`; missing evidence must remain unknown, not clean.
2. Define and test principal attribution separately from whole-case cleanliness, combined scanner/semantic grouping, and an outcome-independent open-quota rule that prevents early IDs from monopolizing allocation.
3. Establish plausible clean-lookalike availability for every required slot before freezing a successor. Exclude this pilot repository from later counted evaluation. Do not silently relax v4 or proceed to the three-arm evaluation.

## Local evidence bindings

The external pilot directory retains the selected source snapshot, input manifest, raw responses, original call records, both hash-linked recovery revisions and the final report. No third-party source files are copied into this repository.

- `pilot-inputs.json` SHA-256: `2e69094c22dfa4b2b157388e4f9363bcb5c19e4f0c8f7ffb9349d8fb883239bc`.
- `pilot-report.json` SHA-256: `92be46e2bd9385d51761aeaf1412243a70224e959244545ea22866e2df3f786d`.

These hashes bind local artifacts; they do not make unpublished raw evidence independently accessible.

## Follow-up: pinned context expansion, no model calls

The separate successor preparation tool added `e2e/global-setup.ts` to all three pilot boundaries from the same pinned commit, checking its Git blob hash. The file explicitly writes `playwright/.auth/certified-user.json`; its seed commands remain unexpanded, unexecuted runtime dependencies. This supplies previously missing producer code, not proof that authentication succeeds or that the cases are clean. The old model responses remain bound to their original narrower inputs and cannot be reused as adjudication of the expanded cases.

The first preparation attempt stopped on an incompatible normalized-tree assumption. After that repair, a second attempt collected the setup file. A third, separately preserved attempt also records the runtime-command limitation. Its external `context-report.json` SHA-256 is `c49f885b11b4243eb8cd39dddbb53d9189d4552d669b5c6b6fe11d1d8b704d54`. No additional model call or evaluation ran. Synthetic allocation tests cover duplicate-lane grouping, balanced assignment, exhausted quotas, order binding and rejection of verdict-bearing input; they do not establish actual eight-pattern yield.

## Seed-context follow-up: incomplete, not a negative yield result

A subsequent preparation added the pinned seed entrypoint and its `user-data.js` dependency under the explicit `e2e` cwd hypothesis. Its context-report SHA-256 is `5321583d55ecc588deaf460429cf4b5aa291b1d11abab5e190f81491d88fc33d`. No database command, environment-file read or seed execution was performed. Runtime isolation and component-render context remain unproven.

The separately registered follow-up allowed at most five model calls on these expanded inputs. The first Fable discovery call exited zero after 239,729 ms but returned an `ExitPlanMode` heading and a `plan` object with escaped embedded JSON instead of the required discovery object. The unchanged response validator rejected it with `ValueError` (ambiguous JSON framing). The run stopped after **one actual call, zero validated discoveries and zero blind passes**. No retry, wrapper extraction, candidate substitution or evaluation followed. This is an output-contract failure, not evidence that clean candidates are unavailable. Text embedded in the rejected plan is not an accepted finding, absence judgment or proof of isolation.

Local artifact bindings:

- Follow-up `inputs.json`: `17bcd93a0d1c32bf453aa33822125cbc0d3884df339de6bdffd2cf606e2dc843`.
- Follow-up incomplete `report.json`: `c4884de477963158208deececd25c802f7e8502e41b3157f38b8f81198d62ab9`.
- Original response: `1e09f56db3bda5ed09cd4ddeda6aada7ef25ccc5df5a6cc760d33004ef4c862f`.

The [sampling decision](successor-sampling-decision.md) removes the structural requirement to fill every pattern with a clean principal case in a proposed successor, while retaining all 24 review contracts. It does not convert this failed follow-up into feasibility evidence. Before another counted attempt, validate the model-output contract on disposable transport fixtures and register a new attempt; preserve this one as incomplete.

### Output-contract diagnostic boundary

Confirmed: the shared runner defaults `claude_permission_mode` to `plan` and emits `--permission-mode plan`; model tools remain disabled. The planning-shaped answer is consistent with that mode. Not confirmed: that this option alone caused the failure. The earlier successful discovery calls used the same runner defaults, while this call had expanded input and stochastic model behavior.

| Candidate cause | Evidence and falsifier | Status |
| --- | --- | --- |
| Planning-mode instruction conflicts with JSON-only task | Planning wrapper observed and plan option present; consistent wrapper failure with plan disabled would weaken this explanation | Plausible, not proven |
| Model variability or expanded-prompt interaction | Earlier calls with the same mode succeeded; a controlled same-prompt comparison is needed | Still plausible |
| Parser accepts a valid discovery object incorrectly | Response has `plan`, not the required top-level `patterns`; nested escaped text is not the registered response format | Rejected as an admission fix |

Offline regression now confirms that an exit-zero planning wrapper stops after one invocation, leaves the report incomplete and starts no adjudicator. No shared runner defaults or failed evidence were rewritten. A future diagnostic should vary only the existing `claude_permission_mode` option with identical disposable prompts and preserve tool/credential isolation; it must not be presented as a resumed counted run or as proof that a single passing sample eliminates stochastic failures.

### Controlled transport probe: blocked by provider usage limit

[`probe-specificity-transport.py`](../../scripts/evals/probe-specificity-transport.py) registered four fresh, serial calls in `plan, off, off, plan` order, with identical short classification prompts, model and 60-second timeouts. `off` only omits `--permission-mode plan`; `--safe-mode`, disabled tools, empty settings sources, strict MCP configuration and fresh credential-isolated homes remain unchanged. Offline tests verify this exact command delta and reject planning wrappers and duplicate JSON keys.

The first live invocation returned exit 1 after 3,755 ms: "You've hit your weekly limit", with the provider announcing September 24 at 09:00 Asia/Seoul as the reset. This was a 2026-09-22 observation, not a guarantee of future account availability. The remaining three calls were not attempted. There are **zero scoreable transport responses** and no paired comparison. The planning-mode hypothesis remains unresolved; this failure says nothing about candidate yield or the relative reliability of either mode. Do not change the runner default on this evidence or route around the account limit.

The external run retains its pre-call input manifest, incomplete report and response hash `c4fba92e4d2eaa549ab21f2671344d3e93c2c508e7d6f2e8f192528c05402d70`. After service availability returns, invoke the same probe into a new external directory; never overwrite this attempt. This is diagnostic work only, not a continuation of the failed candidate-collection run.

## Authorized Codex development path

The user subsequently authorized Codex instead of Claude. The new path uses `gpt-5.6-sol`, isolated tool-free sessions and an explicit `independent_adjudication: false` manifest field. It is neither a cross-provider oracle nor an evaluation run. Existing Claude attempts and frozen protocols remain unchanged.

Two seed-inclusive attempts remained incomplete. In each, the small transport check passed before the first discovery failed. The original text transport exceeded the existing one-MiB combined output capture limit. An opt-in JSON-event transport retained that capture limit and exposed a separate input failure. A one-call diagnostic with the same prompt confirmed the CLI error: `input_too_large`, maximum 1,048,576 characters, actual 1,898,388. The seed `user-data.js` alone is 1,606,097 bytes. No oversized source was truncated and no failed discovery was accepted. The diagnostic was a transport inspection, not an additional scored candidate call. Oversized discovery inputs now fail preflight before live invocation. JSON transport requires a terminal completed turn and rejects tool items or failure events; the common runner's default mode remains unchanged.

A **separate setup-only development run** used the already preserved earlier context snapshot with its original source files intact and its seed/runtime limitation explicitly included. It made four successful calls: one transport check and three discoveries. No discovery proposed a candidate, so the preregistered selection rule started zero whole-case passes.

| Case | Candidate IDs | Model-reported insufficient context |
| --- | --- | --- |
| action-row | None | #13 |
| backend | None | #13, #20, #22, #23 |
| block-navigation | None | #12, #13 |

This establishes execution and schema/citation validity, not correctness of each semantic judgment. In particular, no candidate proposal does not prove that no legitimate lookalike exists: discovery can miss clean guard shapes or confuse absence of a defect with absence of a lookalike. The smaller boundaries do not inherit any full-seed validation. There are zero admitted cases and no specificity result; input expansion, discovery recall and independent principal attribution remain open.

Setup-only local bindings:

- `inputs.json`: `90f7f860a287dfe71a469118ba51a017f058001ea2147ffbe31392fad946590c`.
- `report.json`: `186fabd3267034dd501be69af7cbd27d351b0aa1a220324ceb4589d666478759`.

## Discovery calibration and fresh development intake

A controlled diagnostic used three disposable #21 fixtures: a storage-state consumer with its automated producer and project dependency, a spec with no storage-state reference, and a consumer whose producer was omitted. Each was run once under the original discovery wording (v1) and once under an explicit resemblance-versus-defect clarification (v2), serially using Codex `gpt-5.6-sol`. Expected labels were not supplied to the model. All six calls completed.

| Scored #21 fixture | Expected | v1 | v2 |
| --- | --- | --- | --- |
| Supplied regeneration guard | candidate | absent | candidate |
| No storage-state surface | absent | absent | absent |
| Missing producer evidence | insufficient-context | insufficient-context | insufficient-context |

The clarification corrected the observed guarded-lookalike miss in this one fixture trio (2/3 to 3/3). This is not a repeated causal estimate, validation of the other seven discovery IDs, or evidence of whole-case cleanliness. v1 and the frozen protocols remain unchanged; v2 is an opt-in development prompt.

Fresh intake then walked the original inventory order, excluding prior-use repositories and the earlier freeCodeCamp pilot. A first root-manifest-only attempt prepared no cases; a separate revision admitted ancestor manifests for monorepo ownership. That attempt exhausted the unauthenticated GitHub API quota before staging a case. A third attempt reused preserved metadata responses and fetched public source bytes by pinned-commit raw URLs, checking every Git blob hash. It staged two React cases before a later metadata request returned HTTP 403. No credentials, third-party writes, or source execution were used.

The intake remains **incomplete**, not a completed repository sample. Its two staged cases are `compiler/apps/playground/__tests__/e2e/page.spec.ts` and `fixtures/flight/__tests__/__e2e__/smoke.test.js`. A separate Codex follow-up explicitly opts into this prepared prefix; the default runner still rejects incomplete intake. Context completeness is not asserted, and unresolved evidence remains visible to the model. The original attempts are preserved rather than overwritten.

Local artifact bindings:

- Calibration `inputs.json`: `467942fdacde82a585a266ff3174540976ef73e5d060d4d50ed35b3c31072545`.
- Calibration `report.json`: `993c85783ce842aeea28b930031e2a04bf8635e51f0c4522b0d0ffc87325f7ca`.
- Third intake `context-report.json`: `9370a3941daf424df1d06f94254692b991e7573984249d2f4ebd46b79239f805`.

### Prepared-prefix Codex outcome: invalid blind citation

The v2 follow-up made four actual calls: one successful transport check, two validated discoveries, and the first whole-case pass. The playground spec proposed #1 and #2; the flight smoke spec proposed none. The outcome-independent allocator selected the playground case for the blind schedule.

The first blind response exited zero and proposed findings, but cited line 346 of the playground spec, which has only 343 lines. The unchanged validator rejected that out-of-range citation. The report remains **incomplete**, with zero validated blind passes; the second pass was not invoked. No citation was guessed, repaired, or silently removed. The other proposed findings have not been independently verified and the rejected response cannot establish a clean or defective case. There are still zero admitted cases, no independent adjudication, and no specificity evaluation.

- Prepared-prefix `inputs.json`: `bae79e70fd50dff300823d4a96a1944182bfad6536e3365848c171adef0db424`.
- Incomplete `report.json`: `b25b4e7be85721b3da4311666d0534a6275771ca74cef5df8d56e7b36ca5e1dd`.
- Rejected response: `fa21b5c1aaa3c9ab0214e0365263924e081d37111f932d6bed5bd693d746ee8f`.

## Numbered-source citation diagnostic

Confirmed symptom: the first React whole-case response cited line 346 in a 343-line file. Its source was supplied as an unnumbered JSON string; file hashes still matched. The schema validator correctly rejected the response, so weakening it or repairing the model's citation is not an acceptable recovery.

| Candidate cause | Evidence | Discriminating observation |
| --- | --- | --- |
| Counting drift in unnumbered, JSON-escaped source | Original prompt had no explicit source-line map | Explicit numbered lines still producing invalid citations would weaken this explanation |
| Model variability or inattentive citation generation | One failed live response cannot establish a deterministic cause | Mixed results across identical fresh prompts would remain compatible with this explanation |
| Stale or substituted source | Input digests and staged line counts match | Current evidence does not support this explanation |

[`probe-specificity-citations.py`](../../scripts/evals/probe-specificity-citations.py) registers a separate, two-call Codex diagnostic on the same playground boundary. Both fresh sessions receive identical prompts, with each original source line represented as `{line, text}`. Source files, taxonomy, validation, model, timeout and context limitations are unchanged. Neither response is shown to the other session. The explicit case selection is diagnostic, not a new sampled case or a replacement for the rejected run. The original failed run remains incomplete. No evaluation or admission can be emitted by this probe.

Offline checks cover blank-line preservation, exact one-based numbering, identical prompts, the two-call bound, source preservation, no overwrite, and stopping before the second call after an invalid first response. Successful live citations would demonstrate feasibility of this representation on the observed boundary, not prove a general cure or a causal effect from two unpaired samples.

The live probe completed both calls without validator recovery. Both returned `finding`, with the same ten `(pattern, severity, file, line)` tuples after ignoring array order: #2/P0 at line 224 and #4/P1 at lines 149, 176, 180, 206, 215, 253, 280, 308 and 332 of the playground spec. All required pattern-coverage citations also passed the unchanged validation. These are agreeing same-model proposals, not independently verified upstream defects. The case is not eligible as a clean example; no corpus admission or evaluation followed.

The default unnumbered prompt was reconstructed from the original inputs and still matches its recorded SHA-256 `ba2b27d70d5dc6d904463af7dac4b1a69602b4e8fb4e3dcd08aff6f0a9595703`. Numbered presentation is an explicit diagnostic option, not a silent frozen-protocol change. The evidence supports feasibility on this boundary; it does not distinguish formatting effects from model variability conclusively.

- Numbered-source `inputs.json`: `f32344ca6cb2d09eb33f20cf8c10fd0f0f516f49db70b5d203a5044987279a7e`.
- Complete diagnostic `report.json`: `049b2424e4a79efd17861d045925d2bc852e2eb8db634ed88415a5810677fcf7`.
