# Real-code fix pairs (fixpair-v1)

This public development corpus pairs an E2E spec immediately before an upstream fix with the same spec after the fix. A confirmed catalog instance in the BEFORE file is the positive label; its mapped location in the AFTER file is the clean control. The [corpus](corpus.json) records the exact source line, pattern, severity, diff mapping, upstream commit and first parent, and both model judgments. The [scores](scores/) contain one scored run per sample and arm.

## Construction and labels

Candidates came from local upstream commit histories: commits changing Playwright or Cypress spec files were filtered for plausible test reliability or assertion fixes, then the changed spec lines and parent/fix snapshots were inspected. Batch B contains 10 MIT/Apache-2.0 fix commits with 15 model-adjudicated labels from a Claude-verified mining round (two #10c labels are not supported by the later source audit below). Batch C adds 7 MIT fix commits with 12 confirmed instances, classified by Codex `gpt-6-sol` and independently checked by Codex `gpt-6-astra` against quoted reviewer contract text. Batch D adds 2 MIT fix commits and 6 confirmed instances from a relaxed mining round aimed at semantic patterns `#1`, `#2`, `#20`, `#22`, and `#23`; none of those patterns were found. Its confirmed instances are four `#4h` one-shot URL assertions (P1) and two `#4f` Locator truthiness assertions (P0). Codex `gpt-6-astra` independently confirmed these 6 and rejected 14 other proposed instances, including a project `wait()` helper that was not catalog `#9` and Promise truthiness that was not Locator `#4f`. B checked 31 proposed instances and rejected 4 across its development batches; C's 12 published instances were all confirmed by its verifier. The C and D verifier is in the same model family as the classifier. There are no human labels. The two snapshots for each spec were checked byte-for-byte against the candidate snapshots; D snapshots also match the manifest hashes.

## Evaluation

### Controlled three-model development rerun (2026-10-03, pre-fix)

The B+C+D corpus was rerun from one frozen skill snapshot (`c1432adeaf3c25c62cf0f7a0b5619a54959d7962`), one case manifest (`168f8e2fa8a5976167356d9cae2436d1316f0bab9e3a49ecdb2cdbbf3dc3128c`), and the same pattern legend and report format in both arms. Each model reviewed 42 BEFORE/AFTER samples once per arm; the skill arm had the complete skill and scanner, while the no-skill arm had only the legend. The [matrix summarizer](../../scripts/evals/summarize-fixpair-matrix.py) checks all 18 saved run logs, input digests, sample identity, completion, and raw heading-aware scores. Logs and sparse checkouts are in the local development harness outside this repository; these figures are not independently replayable from the committed archive or release-eligible.

| Model | Skill BEFORE | No-skill BEFORE | AFTER alarms (skill / no-skill) | Input tokens (skill / no-skill) | Sum call time (skill / no-skill) |
| --- | ---: | ---: | ---: | ---: | ---: |
| `gpt-6-sol` | 25/33 | 14/33 | 0/33 / 1/33 | 20,759,001 / 5,173,839 | 5,174 / 2,292 s |
| `gpt-6-astra` | 28/33 | 20/33 | 0/33 / 1/33 | 19,012,340 / 4,918,538 | 6,916 / 3,384 s |
| `claude-sonnet-5-5` | 25/33 | 17/33 | 1/33 / 1/33 | 11,172,880 / 869,924 | 2,453 / 484 s |

The paired, case-cluster bootstrap 95% intervals for the strict-recall difference (skill minus no-skill) are +12.5 to +52.9 points for Sol, 0 to +48.5 for Astra, and +7.4 to +39.5 for Sonnet. Excluding the two unsupported/unresolved `#10c` labels leaves the same numerators over 31; also excluding the two source-supported but unreproduced collision *risks* leaves them over 29. These exclusions are sensitivity checks, not relabeling of the frozen score. One run per sample, model-made labels, repeated mechanisms, and a public development corpus do not justify a general accuracy or efficiency claim. Input-token totals include cache reads and are not billed-token ratios. The skill treatment costs about 4.0×/3.9×/12.8× input tokens and 2.3×/2.0×/5.1× summed call time for Sol/Astra/Sonnet, respectively. The Sonnet run used an earlier evaluator byte snapshot differing only in an auxiliary clustered-metric list; the prompt, skill, corpus, and primary scorer were the same. One Astra auxiliary `leak_reads` flag was a negative `rg` glob excluding `.git`, not a metadata read; the summarizer requires an exact raw-event digest acknowledgement and leaves the raw log unchanged.

The actionable shared miss was narrower than the aggregate: Sol and Sonnet each missed two semicolonless `expect(page.url()).toBe(...)` assertions in Payload, even though the catalog already defines them as `#4h`. The scanner also missed those lines because it borrowed a `#4f` assertion terminator; it surfaced the adjacent `toContain` lines only accidentally. A targeted scanner regression fix now emits all four BEFORE `#4h` hits and none of the corresponding retry-wrapped AFTER hits. That mechanical correction is not counted as an improvement in the pre-fix table.

### Controlled post-fix rerun (2026-10-03)

The same 33 labels, manifest digest, legend, task prompts, scoring rule, and one-run-per-sample schedule were used after the scanner fix. The frozen post-fix skill is commit `ad5aedbd746fd0b4543c7fa8110268b259ddad2e`. All 18 B/C/D arm logs completed and passed the [matrix summarizer](../../scripts/evals/summarize-fixpair-matrix.py)'s input-digest, identity, completion, and raw-score checks. The logs remain in the external local harness, not this archive. A later regression fix restored detection of multiline `expect(page.url())` matcher chains; it is outside this measured snapshot.

| Model | Skill BEFORE | No-skill BEFORE | AFTER alarms (skill / no-skill) | Input tokens (skill / no-skill) | Sum call time (skill / no-skill) |
| --- | ---: | ---: | ---: | ---: | ---: |
| `gpt-6-sol` | 26/33 | 14/33 | 0/33 / 1/33 | 20,112,548 / 5,094,773 | 4,109 / 1,807 s |
| `gpt-6-astra` | 27/33 | 22/33 | 0/33 / 0/33 | 20,103,982 / 4,787,608 | 5,900 / 2,436 s |
| `claude-sonnet-5-5` | 27/33 | 21/33 | 0/33 / 1/33 | 11,130,030 / 885,408 | 2,543 / 488 s |

The paired case-cluster bootstrap 95% intervals for skill minus no-skill strict recall are +12.0 to +59.5 points for Sol, −3.7 to +34.4 for Astra, and 0 to +39.5 for Sonnet. The skill arm used 4.0×/4.2×/12.6× as many input tokens and 2.3×/2.4×/5.2× as much summed model-call time, respectively. Input tokens include cache reads; call time is not end-to-end wall time. Relative to the pre-fix run, Sol's skill recall rose by one of 33, but Astra's fell by one while its no-skill arm rose by two; both Sonnet arms rose. These are separate stochastic runs, so those shifts cannot be attributed to the scanner fix. The fix establishes direct scanner coverage of the missed syntax; this small, public, model-labeled development rerun does not establish a general model-accuracy or efficiency gain. Excluding the two disputed `#10c` labels, then also the two unreproduced collision risks, leaves each numerator unchanged and does not change that conclusion.

#### Tool-output profile, not a token attribution

A read-only pass over the successful Codex `gpt-6-sol` post-fix event files (42 samples in each arm; no retries in these folders) classified completed shell calls by their command. The skill arm produced 356 skill-document reads with 5,025,073 output characters, 42 scanner calls with 153,890 output characters, and 333 repository/other calls with 1,119,759 output characters. The no-skill arm produced 322 repository/other calls with 1,257,671 output characters. Commands combining a document read with repository inspection are counted in the document category, so the categories describe commands, not an exact byte-level source split. Among the 42 skill calls, `semantic-review.md` was read 43 times (including absolute-path variants) and `SKILL.md` 42 times. The result locates a large repeated *tool-output surface*, but does not measure per-stage model tokens, billed cost, or elapsed time: Codex records usage only at turn completion, and cached context is repeatedly counted in input-token totals. The event files live in the external local harness, not this archive. Future stage-level comparisons need usage and timestamps at declared stage boundaries; if a host cannot provide those, report the total and this tool-output proxy separately rather than allocating tokens by guesswork. No skill text was shortened based on this proxy; that would require a fixed accuracy and false-positive safety check on source-complete cases.

The development runs used real-repository sparse checkouts at each commit's first parent (BEFORE) and fix commit (AFTER), with Git metadata removed before review. Codex `gpt-6-sol` ran once on each sample per arm: 24 batch B samples, 14 batch C samples, and 4 batch D samples. The skill and no-skill prompts used the same output format and pattern legend; the no-skill arm received the legend without the skill instructions. Strict recall requires the pattern ID and exact BEFORE line. An AFTER false alarm means the same base pattern appears within two lines of the mapped clean location. The Inspect harness, prompts, and full logs are development infrastructure outside this repository; the B, C, and D score rows are published in [samples.json](scores/samples.json).

| Batch | Arm | Strict BEFORE recall | AFTER false alarms | Input tokens |
| --- | --- | ---: | ---: | ---: |
| B (24 samples/arm) | Skill | 10/15 | 0/15 | 11,165,602 |
| B (24 samples/arm) | No skill | 5/15 | 0/15 | 2,765,948 |
| C (14 samples/arm) | Skill | 11/12 | 0/12 | 7,160,696 |
| C (14 samples/arm) | No skill | 7/12 | 0/12 | 2,038,578 |
| D (4 samples/arm) | Skill | 4/6 | 0/6 | 2,128,166 |
| D (4 samples/arm) | No skill | 1/6 | 0/6 | 485,924 |
| B+C+D (42 samples/arm) | Skill | 25/33 | 0/33 | 20,454,464 |
| B+C+D (42 samples/arm) | No skill | 13/33 | 0/33 | 5,290,450 |

### Additional model runs on batch B

| Model | Arm | Strict BEFORE recall | AFTER false alarms | Input tokens |
| --- | --- | ---: | ---: | ---: |
| `gpt-6-astra` | Skill | 10/15 | 0/15 | 11,571,501 |
| `gpt-6-astra` | No skill | 10/15 | 0/15 | 2,891,803 |
| `claude-sonnet-5-5` | Skill | 9/15 | 0/15 | 7,804,777 |
| `claude-sonnet-5-5` | No skill | 9/15 | 0/15 | 954,600 |

A separate, release-ineligible Codex `gpt-6-astra` development run on the same batch B samples scored **10/15** strict BEFORE hits with the skill and **10/15** without it, with **0/15 AFTER false alarms** in both arms. That differs from the `gpt-6-sol` result above (**10/15** versus **5/15**): on this small batch, Astra erased the skill arm's recall advantage. The Astra skill arm used 11,571,501 input tokens across 24 side samples, a mean of **482,145.875 per sample**; the no-skill arm used 2,891,803, a mean of **120,491.792 per sample**. The table below transcribes each paired BEFORE strict-recall and AFTER false-alarm score from the saved Inspect logs; each row is one spec pair, and the denominators are that pair's confirmed instances.

| Sample | Skill BEFORE | Skill AFTER alarms | No-skill BEFORE | No-skill AFTER alarms |
| --- | ---: | ---: | ---: | ---: |
| `appsmi-b7510d1b-6b9472` | 1/1 | 0/1 | 1/1 | 0/1 |
| `appsmi-ec4ea27d-ca7b28` | 0/1 | 0/1 | 0/1 | 0/1 |
| `backst-02a0f0df-27e82e` | 0/1 | 0/1 | 0/1 | 0/1 |
| `backst-daaaa72e-38c493` | 0/1 | 0/1 | 0/1 | 0/1 |
| `backst-daaaa72e-9b7887` | 0/1 | 0/1 | 0/1 | 0/1 |
| `cypres-d081b173-a861fe` | 1/1 | 0/1 | 1/1 | 0/1 |
| `react--44f7e565-9a0ac6` | 2/2 | 0/2 | 2/2 | 0/2 |
| `storyb-457eeac9-7a2ca3` | 1/1 | 0/1 | 1/1 | 0/1 |
| `storyb-457eeac9-d00259` | 1/1 | 0/1 | 1/1 | 0/1 |
| `storyb-613551da-06aa67` | 0/1 | 0/1 | 0/1 | 0/1 |
| `storyb-8e8a1d31-0f2bfc` | 2/2 | 0/2 | 2/2 | 0/2 |
| `storyb-efb5d516-337174` | 2/2 | 0/2 | 2/2 | 0/2 |
| **Total** | **10/15** | **0/15** | **10/15** | **0/15** |

A `claude-sonnet-5-5` run on the same 12 pairs scored **9/15 versus 9/15** strict recall and **0/15 versus 0/15** AFTER alarms (skill versus no skill). The 24 side samples per arm used **7,804,777 versus 954,600** input tokens, or **325,199 versus 39,775** per sample. Its [per-sample score ledger](scores/sonnet-5-5-b-samples.json) records the Inspect scores, including the two one-instance disagreements between arms. This is one development run per sample on the 2.0.0 skill, not a release gate.

### Post-run audit of the strong-model misses (2026-10-02)

The published scores above are the frozen scorer output, not a count of independently established product misses. A local raw-transcript audit found that the Sonnet skill arm did report the Appsmith `#11c` finding at `JSObject_Tests_spec.ts:239`; the scorer missed it because its finding parser extracted cited lines from the text after a finding heading, while this answer put the target line in the heading and mentioned only other lines in the body. The local parser now reads heading citations too. [The audit script](../../scripts/evals/audit-fixpair-logs.py) reproduced every frozen per-sample score in the archived Sol B/C/D, Astra B, and Sonnet B logs (106 side samples per arm, including Sol's local-only batch A) before applying that rule equally to both arms. It found only this one changed score: Sonnet strict recall would be **10/15 versus 9/15**, not 9/15 versus 9/15. The published ledger is left unchanged. Full raw Inspect transcripts remain outside this repository, so the correction is not independently replayable from the committed archive and is not a new benchmark result.

The four scored `#10c` misses are not four independent product failures: three repeat Backstage's `APIs` locator shape. A read-only audit of the exact upstream parent commits supplied the application source omitted by the sparse evaluation checkouts. The evaluated scanner had surfaced all four as LLM-triage candidates; the distinctions below concern the final semantic verdict, not scanner coverage.

| Labeled instance | Source-backed adjudication |
| --- | --- |
| Backstage default-app template | **Supported collision risk, not a reproduced failure.** [The root route is the catalog](https://github.com/backstage/backstage/blob/f746ec202a11c24a7e813124953850ec361f8678/packages/create-app/templates/default-app/app-config.yaml.hbs#L15-L18); [catalog entity names are links](https://github.com/backstage/backstage/blob/f746ec202a11c24a7e813124953850ec361f8678/plugins/catalog-react/src/components/EntityDataTable/columnFactories.tsx#L45-L64) alongside the `APIs` navigation link. A backend-provided entity title containing “APIs” could match the page-scoped substring locator. The shipped example entities do not demonstrate an actual collision. |
| Backstage next-app template | **Same supported risk, not an independent mechanism or reproduced failure.** [Its root route also renders the catalog](https://github.com/backstage/backstage/blob/d156cf48bb6aeb99aaeb824335950892a436494d/packages/create-app/templates/next-app/app-config.yaml.hbs#L8-L12); the [catalog name column renders entity links](https://github.com/backstage/backstage/blob/d156cf48bb6aeb99aaeb824335950892a436494d/plugins/catalog/src/components/CatalogTable/columns.tsx#L32-L58), while the [API navigation item is titled `APIs`](https://github.com/backstage/backstage/blob/d156cf48bb6aeb99aaeb824335950892a436494d/plugins/api-docs/src/alpha.tsx#L42-L48). |
| Backstage `packages/app` | **Unresolved; the label's stated rationale is contradicted.** [The root page is the Example Pages Plugin with fixed links](https://github.com/backstage/backstage/blob/d156cf48bb6aeb99aaeb824335950892a436494d/packages/app/src/examples/pagesPlugin.tsx#L56-L140), not the [catalog page at `/catalog`](https://github.com/backstage/backstage/blob/d156cf48bb6aeb99aaeb824335950892a436494d/plugins/catalog/src/alpha/pages.tsx#L58-L75). No same-role dynamic link collision on the tested page was established. |
| Storybook survey | **The labeled story-name collision is unsupported.** [The survey contains its Submit action inside a Modal](https://github.com/storybookjs/storybook/blob/87733f1a77f5a0cdb7889ec30eaeedbfb3acf491/code/addons/onboarding/src/features/IntentSurvey/IntentSurvey.tsx#L174-L251), and the [Modal hides outside content from the accessibility tree while open](https://github.com/storybookjs/storybook/blob/87733f1a77f5a0cdb7889ec30eaeedbfb3acf491/code/core/src/components/components/Modal/Modal.tsx#L177-L181). Dynamic story names outside the dialog therefore do not prove a competing accessible button. |

This is source-backed static adjudication, not a live browser reproduction or a retroactive score change. It supports keeping `#10c` as a context-dependent triage rule. Do not promote an absent `exact: true` option alone into a confirmed finding to recover this benchmark score.

As a sensitivity check, omit only the two `#10c` labels whose stated collision rationale is unsupported or unresolved (Backstage `packages/app` and Storybook), and apply the heading-aware parser to both arms. On the remaining **13 model-adjudicated B labels**, Sol is **10/13 versus 5/13**, Astra **10/13 versus 10/13**, and Sonnet **10/13 versus 9/13** (skill versus no skill). Neither excluded label was a hit in any arm. The two retained Backstage template labels describe a supported *risk*, not reproduced failures; this is not a new ground-truth score or a replacement for the frozen table.

The pairing controlled model within each comparison, the BEFORE/AFTER spec snapshots, pattern legend, and report format. It did not isolate skill wording: the skill arm could use its bundled scanner and workflow, while the no-skill arm received the catalog legend only. The treatment is therefore the whole skill package. One run per sample, model-made labels, repeated Backstage cases, incomplete app context in the evaluated sparse checkouts, and archived raw logs outside this repo prevent a stable population-effect claim. The Sonnet input-token ratio measures workflow consumption, not an equal-budget comparison or a billing ratio. `0/15` AFTER alarms tests only the labeled patterns near mapped fix locations, not whole-report precision.

**Decision after audit:** No additional model calls were made. On this development batch, the corrected strong-model signal is one Sonnet hit out of 13 retained labels and no Astra gain, alongside substantially greater input-token use in the skill arms. That is insufficient reason to expand the same mined corpus merely to obtain a stronger headline. A future efficacy claim would need a predeclared, source-complete set of independent defects, blind adjudication of every reported finding, fresh repeated sessions under a fixed model/tool/budget protocol, and measured cost and latency. Until then, cite this as workflow and case evidence, not a general accuracy lift.

The local Sonnet transcripts also separate the 24 scored skill calls' **7,804,777 input tokens** into 1,229,956 cache writes, 6,574,471 cache reads, and 350 uncached input tokens; the no-skill calls' **954,600** split into 282,466 cache writes, 672,038 cache reads, and 96 uncached input tokens. These totals include repeatedly read context, not just new prompt text. The transcripts do not assign the excess to one review stage, and input-token ratios are not billing ratios. Failed attempts retained by the harness are excluded from these scored-call totals.

Batch B's labels were independently verified by a Claude subagent, not by Astra; the Astra classifier run therefore is a second-model comparison against those existing model-made labels, not an independent relabeling or human adjudication.

The preregistered rule was skill minus no-skill strict recall **at least 20 percentage points** and skill AFTER false alarms **at most 1**. Batch B gained **33.3 percentage points**, batch C gained **33.3 percentage points**, and batch D gained **50.0 percentage points**. B+C+D gained **36.4 percentage points**, with **0** skill false alarms, so the rule was met. Including a local-only AGPL batch not published here, the all-batch aggregate was **36/44** skill versus **23/44** no skill, with **0 versus 1** AFTER false alarms. No case, snapshot, or result row from that local-only batch is included here.

This is a single-host, one-run-per-sample development measurement on model-made labels. The sample is small, with many P1 mechanical patterns; D's two P0 labels come from one case. Two source-supported template `#10c` risks in B were missed; the other two scored `#10c` labels are unresolved or unsupported, as audited above. Two `#4h` instances in D were also missed. A separate search for a Playwright `#20` case found no MIT/Apache-licensed product repository whose E2E writes reached a shared external backend; the only qualifying repository found was refine, whose relevant E2E suite uses Cypress. The public corpus is inspectable and was available to its authors, so this is not a sealed release benchmark.

## Reproduce

Read each case's `upstream_url`, `parent`, `commit`, and `spec_paths` in [corpus.json](corpus.json). Fetch those SHAs in the named upstream repository, create sparse checkouts containing each spec and its relevant project configuration at the parent and fix commits, then remove `.git` before giving either side to a reviewer. Verify the spec bytes against [cases/](cases/) before scoring. Run one read-only review per side and arm with `gpt-6-sol`, the same pattern legend and report format, and score exact BEFORE pattern and line matches plus mapped AFTER false alarms within two lines. The original Inspect task and checkout preparation scripts live in the local development harness outside this repository and are described here rather than vendored.

## Third-party material

The snapshots are unmodified excerpts of the named spec files at the named commits and keep their upstream licenses. Each upstream LICENSE file (and Backstage's NOTICE) is copied verbatim from the recorded commit into `licenses/`.

| Upstream | URL | SPDX license | License text at commit | Copyright line |
|---|---|---|---|---|
| Appsmith | https://github.com/appsmithorg/appsmith | Apache-2.0 | [licenses/appsmith-LICENSE.txt](licenses/appsmith-LICENSE.txt) | Apache-2.0 text; no copyright line in the file |
| Backstage | https://github.com/backstage/backstage | Apache-2.0 | [licenses/backstage-LICENSE.txt](licenses/backstage-LICENSE.txt), [NOTICE](licenses/backstage-NOTICE.txt) | see NOTICE |
| Cypress Real World App | https://github.com/cypress-io/cypress-realworld-app | MIT | [licenses/cypress-realworld-app-LICENSE.txt](licenses/cypress-realworld-app-LICENSE.txt) | Copyright (c) 2020 Cypress.io |
| Payload | https://github.com/payloadcms/payload | MIT | [licenses/payload-LICENSE.txt](licenses/payload-LICENSE.txt) | Copyright (c) 2018-2025 Payload CMS, Inc. |
| react-admin | https://github.com/marmelab/react-admin | MIT | [licenses/react-admin-LICENSE.txt](licenses/react-admin-LICENSE.txt) | Copyright (c) 2016-present, Francois Zaninotto, Marmelab |
| React Router | https://github.com/remix-run/react-router | MIT | [licenses/react-router-LICENSE.txt](licenses/react-router-LICENSE.txt) | Copyright (c) React Training LLC 2015-2019 (and later holders listed in the file) |
| Storybook | https://github.com/storybookjs/storybook | MIT | [licenses/storybook-LICENSE.txt](licenses/storybook-LICENSE.txt) | Copyright (c) 2024 Storybook |
| TanStack Router | https://github.com/TanStack/router | MIT | [licenses/router-LICENSE.txt](licenses/router-LICENSE.txt) | Copyright (c) 2021-present Tanner Linsley |
