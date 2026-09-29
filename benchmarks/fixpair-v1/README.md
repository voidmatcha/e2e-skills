# Real-code fix pairs (fixpair-v1)

This public development corpus pairs an E2E spec immediately before an upstream fix with the same spec after the fix. A confirmed catalog instance in the BEFORE file is the positive label; its mapped location in the AFTER file is the clean control. The [corpus](corpus.json) records the exact source line, pattern, severity, diff mapping, upstream commit and first parent, and both model judgments. The [scores](scores/) contain one scored run per sample and arm.

## Construction and labels

Candidates came from local upstream commit histories: commits changing Playwright or Cypress spec files were filtered for plausible test reliability or assertion fixes, then the changed spec lines and parent/fix snapshots were inspected. Batch B contains 10 MIT/Apache-2.0 fix commits with 15 confirmed instances from a Claude-verified mining round. Batch C adds 7 MIT fix commits with 12 confirmed instances, classified by Codex `gpt-6-sol` and independently checked by Codex `gpt-6-astra` against quoted reviewer contract text. Batch D adds 2 MIT fix commits and 6 confirmed instances from a relaxed mining round aimed at semantic patterns `#1`, `#2`, `#20`, `#22`, and `#23`; none of those patterns were found. Its confirmed instances are four `#4h` one-shot URL assertions (P1) and two `#4f` Locator truthiness assertions (P0). Codex `gpt-6-astra` independently confirmed these 6 and rejected 14 other proposed instances, including a project `wait()` helper that was not catalog `#9` and Promise truthiness that was not Locator `#4f`. B checked 31 proposed instances and rejected 4 across its development batches; C's 12 published instances were all confirmed by its verifier. The C and D verifier is in the same model family as the classifier. There are no human labels. The two snapshots for each spec were checked byte-for-byte against the candidate snapshots; D snapshots also match the manifest hashes.

## Evaluation

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

Batch B's labels were independently verified by a Claude subagent, not by Astra; the Astra classifier run therefore is a second-model comparison against those existing model-made labels, not an independent relabeling or human adjudication.

The preregistered rule was skill minus no-skill strict recall **at least 20 percentage points** and skill AFTER false alarms **at most 1**. Batch B gained **33.3 percentage points**, batch C gained **33.3 percentage points**, and batch D gained **50.0 percentage points**. B+C+D gained **36.4 percentage points**, with **0** skill false alarms, so the rule was met. Including a local-only AGPL batch not published here, the all-batch aggregate was **36/44** skill versus **23/44** no skill, with **0 versus 1** AFTER false alarms. No case, snapshot, or result row from that local-only batch is included here.

This is a single-host, one-run-per-sample development measurement on model-made labels. The sample is small, with many P1 mechanical patterns; D's two P0 labels come from one case. Several `#10c` instances in B and two `#4h` instances in D were missed. A separate search for a Playwright `#20` case found no MIT/Apache-licensed product repository whose E2E writes reached a shared external backend; the only qualifying repository found was refine, whose relevant E2E suite uses Cypress. The public corpus is inspectable and was available to its authors, so this is not a sealed release benchmark.

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
