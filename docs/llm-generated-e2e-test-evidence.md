# Evidence for reviewing LLM-generated E2E tests

This ledger evaluates primary-source support for claims about LLM-generated tests, with special attention to Playwright and Cypress. It preserves the original 49-source audit and adds ten primary sources found during independent follow-up passes. It is an evidence map, not a claim that all 59 sources study browser E2E tests. Most academic results concern unit tests, generated test patches, or benchmark construction. Applying those results to browser tests is an explicit extrapolation.

## How to read this ledger

Evidence was collected and rechecked on **2026-07-31**. Discovery used exact-title, author, organization, and claim searches, plus targeted queries for `LLM generated Playwright mutation testing`, `Cypress AI generated test fault detection`, `browser test oracle LLM`, and related terms. A candidate was retained as evidence only after its original artifact was retrieved from one of these surfaces:

1. official product documentation or an official engineering publication;
2. a DOI publisher record or peer-reviewed proceedings page;
3. an author-posted preprint with stable metadata;
4. a first-person practitioner report that clearly identifies its own sample and method.

Search snippets, social reposts, third-party summaries, and circular vendor claims were not used to establish quantitative results. This was a bounded evidence review, not a systematic literature review. Therefore, “not located” below means **not located in this search**, not “does not exist.”

Status has a strict meaning:

- **Verified primary** — the retrieved original directly supports the scoped claim.
- **Qualified** — the original is real, but the popular summary overstates its scope, venue status, denominator, causal meaning, or applicability to E2E.
- **Not cleared** — the stated claim could not be matched to a durable original, or the original did not contain the claimed result. No link is supplied for these entries.

## Corrected high-value numbers

| Claim | What the primary source supports | Safe interpretation |
|---|---|---|
| “Developers identify incorrect LLM assertions at 49%” | Kaufman et al. report **73.9% accuracy on correct assertions and 49.0% on incorrect assertions**, with **86 programmers**. Participants were similarly confident in both classes. | A controlled preprint shows a serious human-review blind spot. It does not establish that all code review is chance-level or measure E2E review specifically. |
| “68.1% of final suites preserve bugs” | Mathews and Nagappan report **62/91 (68.1%)** CoverUp final suites in the `OG-success / REF-failed` outcome: they passed the original implementation and failed the reference implementation. | This supports a selection-bias mechanism in coverage-guided LLM unit-test generation. It is not a browser-test fault-detection rate. |
| “The strongest model validates only 10.2% of realistic mutants” | SWE-Mutation reports **10.20% verified reproduction rate (VRR)** for the **test-generation task with DeepSeek-V3.1 under Mini-SWE-Agent**. It also reports average relative detection rate falling from **71.04% on conventional mutants to 39.81% on its agentic benchmark mutants**. | Cite the named task, configuration, and metric. Do not relabel it as a universal or “strongest model” score, or claim that the benchmark's realism is independently established. |
| “59.4% of SWE-bench Verified audit problems had bad tests” | OpenAI reports that, among **1,699 random SWE-bench samples** annotated by **93 Python developers**, **61.1%** were flagged for unit tests that may unfairly reject valid solutions; **68.3%** were filtered overall for that or other issues. | The supported figure is 61.1%, not 59.4%. This audits benchmark tests, not LLM-generated tests. |
| “57% of Meta-generated tests were stable; 25% raised coverage” | TestGen-LLM reports that **75% of generated test cases built successfully, 57% passed reliably, and 25% increased coverage**. | These are generated-test-case funnel rates after generation, not mutation scores or browser-E2E rates. |
| “64% of generated Python-test errors were assertion errors” | Alves et al. classify **98 of 151 execution errors (64.9%)** as assertion errors. | This is a peer-reviewed Python unit-test result under the paper’s generation setup, not a Playwright/Cypress estimate. |
| “Generated Playwright tests failed 48% of medium flows” | Slack reports **5 configurations × 20 runs × 2 flows**. Its generated Playwright-test configuration had about **8% failure on the simple flow and 48% on the medium flow**, often completing 70–80% before the final interaction or assertion failed. The same article later says each generated test was generated once and executed five times for runtime analysis, without fully reconciling that statement with the 20-run failure-rate denominator. | This is a transparent company experiment in non-production Slack workspaces, but the 20 trials must not be described as 20 independent generations. It measures execution reliability, not semantic correctness or mutant killing. |
| “Only 6% of an inherited Playwright suite passed locally” | Debbie O’Brien reports **8 of 130 non-skipped tests** passing locally, about **6%**, while CI was green with `workers: 1`. | A valuable first-person architecture case study, not a representative industry rate. |
| “A peer-reviewed Playwright-backed agent reached 96% precision/recall” | WebTestPilot reports **99% task completion and 96% precision and recall** on four open-source web apps with 100 manually injected bugs in four behavior categories. In a separate real-bug replication evaluation, it detected **22 of 23** GitHub-issue bugs. Its implementation generated Playwright-backed oracle scripts. | This is direct browser-E2E fault-detection evidence for one agentic natural-language-to-oracle system. The injected-bug benchmark and 23-case replication study are distinct. Neither is a reusable-suite benchmark, a sealed production evaluation, or an estimate for ordinary LLM-authored Playwright/Cypress files. |
| “WEFix repaired 98.4% of reproduced flaky E2E tests” | WEFix created **122 reconstructed UI-wait flaky tests from seven open-source projects by removing developer-added waits**, then repaired **120/122**, with 1.25× execution overhead versus 3.7× for a fixed two-second wait. | This is direct peer-reviewed evidence for repair of explicitly reconstructed wait faults in Cypress and Selenium. It is not LLM test generation, Playwright evidence, a naturally sampled flake benchmark, or a general repair/prevalence estimate. |
| “GenIA-E2ETest achieved 82% precision and 85% recall” | The SBES 2025 study reports **82% execution precision and 85% recall** across two applications, 12 cases, and 36 executions after minor human adjustment. | This is favorable but narrow evidence for supervised generation on an out-of-scope browser stack. The paper did not evaluate Playwright or Cypress and did not measure mutation killing. |

### Reproducibility locators for numerical claims

The following locators record the exact version or primary artifact checked on **2026-07-31**. Web articles have no stable page numbers; their section and quoted result are named so a later reader can distinguish content drift from a citation error.

| Claim(s) | Primary artifact and version | Locator |
|---|---|---|
| 86 participants; 73.9%; 49.0% | Kaufman et al., [arXiv:2607.08885v1](https://arxiv.org/pdf/2607.08885) | p. 6, controlled-experiment result figures; the paper labels the two classes “Correct” and “Incorrect.” |
| 62/91; 68.1% | Mathews and Nagappan, [arXiv:2412.14137v1](https://arxiv.org/pdf/2412.14137) | p. 4, outcome table; CoverUp `OG Success, REF Failed` is 62 and the final-suite denominator is 29 + 62 = 91. |
| 10.20%; 71.04%; 39.81% | [SWE-Mutation, Findings of ACL 2026](https://aclanthology.org/2026.findings-acl.1976.pdf) | pp. 1–2, abstract/introduction; Table 3, test-generation task, distinguishes Mini-SWE-Agent from Claude Code. VRR is “Verified Reproduction Rate.” |
| 1,699; 93; 61.1%; 68.3% | OpenAI, [“Introducing SWE-bench Verified”](https://openai.com/index/introducing-swe-bench-verified/) | Unpaginated web article; audit-results paragraph describing the random sample, annotators, unit-test issue flag, and total filtering. |
| 75%; 57%; 25% | Alshahwan et al., [arXiv:2402.09171v1](https://arxiv.org/pdf/2402.09171) and [DOI 10.1145/3663529.3663839](https://doi.org/10.1145/3663529.3663839) | pp. 1–2, abstract and contribution (2); §2 describes the build, repeated-execution, and coverage filters. The unit is a generated test case. |
| 98/151; 64.9% | Alves et al., [DOI 10.1145/3756681.3756964](https://doi.org/10.1145/3756681.3756964) | EASE 2025 proceedings article, execution-error classification results; 98 assertion errors of 151 execution errors. |
| 20,505; 972; 14,469; 779,585; 34,635 | Ouédraogo et al., [arXiv:2410.10628v2](https://arxiv.org/pdf/2410.10628) | p. 1 abstract; dataset description in §III. These are corpus sizes for a Java unit-test-smell analysis. |
| 5 × 20 × 2; ~8%; ~48%; 70–80% | Slack Engineering, [“Agentic testing: Where agents fit in the E2E testing stack”](https://slack.engineering/agentic-testing-where-agents-fit-in-the-e2e-testing-stack/) | “Our Experiment” → “Experiment Setup” and “Experiment Matrix”; “What We Observed” → “Reliability.” The runtime discussion separately says one generation was executed five times and does not fully reconcile that denominator with the 20-run failure table. |
| 8/130; ~6%; `workers: 1` | Debbie O’Brien, [“How I used AI to fix our E2E test architecture”](https://dev.to/debs_obrien/how-i-used-ai-to-fix-our-e2e-test-architecture-444a) | Opening paragraphs, immediately after the local-suite description. |
| 1.5% of runs; 16% of tests | Google Testing Blog, [“Flaky Tests at Google and How We Mitigate Them”](https://testing.googleblog.com/2016/05/flaky-tests-at-google-and-how-we.html) | Unpaginated 2016 post; opening statistics paragraph. The two denominators are intentionally distinct. |
| roughly 5,000 generated lines | Datadog, [“Delivery guardrails for AI-generated code”](https://www.datadoghq.com/blog/delivery-guardrails-for-ai-generated-code/) | Unpaginated web article; opening incident narrative. This is a first-party engineering case, not a controlled test-generation measurement. |
| 86,156; 33,596; 2,807; 80.2% | Banik et al., [arXiv:2606.18168v1](https://arxiv.org/pdf/2606.18168) | p. 1 abstract; §III dataset/method. Unit: cumulative test-file patch, not an executed test. |
| 85.37%; 88.1%; 0.41; 0.30 | Jhanglani et al., [arXiv:2607.12068v1](https://arxiv.org/pdf/2607.12068) | p. 1 abstract; §III cohort and analysis pipelines. The flakiness values are candidate rates, not observed repeated-run flake rates. |
| 99%; 96%; 4 apps; 100 injected bugs; 22/23 real bugs | Teoh et al., [WebTestPilot, DOI 10.1145/3797115](https://doi.org/10.1145/3797115) and [author version](https://arxiv.org/pdf/2602.11724) | Publisher abstract for the injected-bug metrics; paper §5.1.3 p. 13 for Playwright-backed scripts and §5.1–5.3 pp. 12–16 for the separate injected-bug and real-GitHub-bug evaluations. |
| 120/122; 98.4%; 1.25×; 3.7× | Lu et al., [WEFix, DOI 10.1145/3589334.3645628](https://doi.org/10.1145/3589334.3645628) and [author preprint](https://arxiv.org/pdf/2402.09745) | Evaluation §4.4 explains that the 122 flaky tests were reconstructed by removing developer-added waits; the result section reports 120/122 repairs. The implementation supports Cypress and Selenium. |
| 82%; 85%; 2 apps; 12 cases; 36 executions | [GenIA-E2ETest, DOI 10.5753/sbes.2025.9927](https://doi.org/10.5753/sbes.2025.9927) and [publisher PDF](https://sol.sbc.org.br/index.php/sbes/article/download/37006/36791) | §4 and §4.3; the evaluated implementation uses an out-of-scope browser stack and explicitly limits generalizability. |
| 79% average feature coverage | [AutoE2E, ICSE 2025, DOI 10.1109/ICSE55347.2025.00141](https://doi.org/10.1109/ICSE55347.2025.00141) | Proceedings article and evaluation results. The implementation is Selenium-based; feature coverage is not semantic fault detection. |

## The 59-source ledger

Rows 1–49 preserve the supplied source slots. Rows 50–59 are primary-source additions from independent follow-up passes.

### Official vendor documentation (1–5)

| # | Source | Status | What it does and does not establish |
|---:|---|---|---|
| 1 | [Vitest: “Do the tests actually assert something meaningful?”](https://vitest.dev/guide/learn/writing-tests-with-ai#do-the-tests-actually-assert-something-meaningful) | **Verified primary** | Official guidance says tests that merely call code without checking behavior, or test the mock rather than behavior, create false confidence; it also advises treating AI output as a first draft. This is unit-test guidance, not E2E fault-detection evidence. |
| 2 | [Playwright ARIA snapshots: partial matching](https://playwright.dev/docs/aria-snapshots#partial-matching) and [strict matching](https://playwright.dev/docs/aria-snapshots#strict-matching) | **Verified primary** | The official example shows that `- button` matches a button regardless of its accessible name, while a named snapshot constrains the label. Partial matching is supported behavior. Omitting the name is an authoring choice, not proof that Playwright automatically weakens every snapshot. |
| 3 | [Playwright Test Agents: generator](https://playwright.dev/docs/test-agents#-generator) and [generator prompt source](https://github.com/microsoft/playwright/blob/15ce5e8af9cd4cafc70e472dce4ea0e72ee10fdc/packages/playwright/src/agents/playwright-test-generator.agent.md#L33-L47) | **Qualified** | The official generator requires a plan with explicit verification steps, implements tests, and validates them live. The companion healer can iterate until passing and may mark a test `fixme`. This supports acceptance criteria before generation and semantic review of healer/skip diffs. It does **not** establish that POM drift or assertion weakening is the default outcome. |
| 4 | [Cypress Studio AI: recommended assertion types and limitations](https://docs.cypress.io/app/guides/cypress-studio#types-of-assertions-studio-ai-recommends) | **Verified primary** | Cypress states that Studio AI compares DOM snapshots and “does not have access to your application code, business logic, or backend rules.” The same guide warns about transitional DOM states and context limits. This supports recommending intent-aware human review beyond DOM-diff assertions; the product inserts recommendations into code and does not enforce an approval gate. |
| 5 | [Playwright MCP versus Playwright CLI](https://github.com/microsoft/playwright-mcp/blob/55679f5f3d4b4f3e2534ec0ce2fc5683ba2eaf3f/README.md#playwright-mcp-vs-playwright-cli) | **Qualified** | The official README says coding agents *might benefit* from CLI plus skills and describes that route as token-efficient, while retaining MCP for persistent, exploratory, and richer automation. It is product guidance, not a measured universal regression or proof that MCP was abandoned. |

### Academic research (6–17)

| # | Source | Status | What it does and does not establish |
|---:|---|---|---|
| 6 | Kaufman et al., [“Programmers Are Poor and Overconfident Judges of LLM-Generated Assertions”](https://arxiv.org/abs/2607.08885) | **Qualified** | The controlled study reports 73.9% accuracy for correct assertions and 49.0% for incorrect assertions across 86 programmers, with similar confidence. It is a 2026 preprint, not yet evidence of peer-reviewed E2E-review performance. |
| 7 | Mathews and Nagappan, [“Design choices made by LLM-based test generators prevent them from finding bugs”](https://arxiv.org/abs/2412.14137) | **Qualified** | The study identifies a concrete selection mechanism and reports 62/91 CoverUp final suites in the `OG-success / REF-failed` class. It is a preprint about unit-test generators; browser-flow generalization must be tested, not assumed. |
| 8 | Alshahwan et al., [“Automated Unit Test Improvement using Large Language Models at Meta”](https://doi.org/10.1145/3663529.3663839) | **Verified primary** | FSE 2024 primary evidence for TestGen-LLM’s build, reliable-pass, and coverage-increase filter chain: 75%, 57%, and 25% of generated test cases, respectively. The filters are central to the production method; coverage increase is not equivalent to fault detection. |
| 9 | [“SWE-Mutation: Can LLMs Generate Reliable Test Suites in Software Engineering?”](https://aclanthology.org/2026.findings-acl.1976/) | **Verified primary** | Findings of ACL 2026 reports configuration-specific VRR for the test-generation task and a conventional-to-agentic-benchmark-mutant detection drop. It motivates behaviorally realistic mutations, but does not independently validate the realism of its mutations and studies software-engineering tasks rather than Playwright/Cypress flows. |
| 10 | Konstantinou et al., [“Do LLMs generate test oracles that capture the actual or the expected program behaviour?”](https://arxiv.org/abs/2410.21136) | **Qualified** | The preprint directly studies whether generated oracles encode observed implementation behavior rather than intended behavior. It supports separating characterization from correctness claims, but its studied surface is not generated browser E2E. |
| 11 | Wang et al., claimed ICSE 2026 “82.7% of suspicious patches evade all developer tests” | **Not cleared** | The exact paper/result could not be matched confidently to a durable primary artifact in this search. Do not cite the number until title, proceedings record, denominator, and measured population are recovered. |
| 12 | Ouédraogo et al., [“Test smells in LLM-Generated Unit Tests”](https://arxiv.org/abs/2410.10628) | **Qualified** | The preprint analyzes 20,505 LLM class-level suites, 972 method-level cases, 14,469 EvoSuite tests, and 779,585 human tests from 34,635 Java projects, explicitly covering Assertion Roulette and Magic Number Test. The large test-smell study should not be conflated with a separate accepted empirical study or described as browser-E2E research. |
| 13 | Alves et al., [“Quality Assessment of Python Tests Generated by Large Language Models”](https://doi.org/10.1145/3756681.3756964) | **Verified primary** | EASE 2025 reports 98 assertion errors among 151 execution errors (64.9%) and evaluates prompt effects on Python unit tests. More detailed prompts can change error and smell profiles; the result does not supply an E2E rate. |
| 14 | Yuan et al., claimed Fudan/FSE 2024 assertion-specific study | **Not cleared** | The stated identity and “most cited” characterization were not matched to one durable original with enough confidence. Do not substitute a similarly themed oracle-generation paper without confirming authors, venue, and result. |
| 15 | Zhao et al., claimed Toronto/ISSTA 2026 coverage-quality study | **Not cleared** | The exact artifact and asserted coverage-gate conclusion were not recovered. The general conclusion may be plausible, but it is not attributable to this slot without a primary record. |
| 16 | van Deursen et al., [“Refactoring Test Code”](https://ir.cwi.nl/pub/4324), XP 2001 | **Qualified** | The primary CWI record and PDF identify “Assertion Roulette” as Smell 7 (p. 5). It is a taxonomy anchor, not quantitative evidence about LLM-generated tests. No unverified DOI or numerical claim is attached here. |
| 17 | Romano et al., claimed SUNY Buffalo study of 62 projects and 235 Playwright/Cypress UI tests | **Not cleared** | The exact original supporting the framework/sample counts was not located. Do not use the 62/235 figures until the paper and sampling method are recovered. |

### Company engineering reports (18–30)

The supplied company list named 12 distinct artifacts while specifying a 13-source group. Entry 30 is an additional primary company source found in the same review and is labeled as such; it is not presented as part of the original named list.

| # | Source | Status | What it does and does not establish |
|---:|---|---|---|
| 18 | Slack Engineering, [“Agentic testing: Where agents fit in the E2E testing stack”](https://slack.engineering/agentic-testing-where-agents-fit-in-the-e2e-testing-stack/) | **Qualified** | Reports the 5 × 20 × 2 experiment and about 48% failure for generated Playwright tests on its medium flow. The authors disclose non-production workspaces and path-match limitations. The article also says generated tests were generated once and executed five times and were iteratively refined until passing, so the 20-run cells must not be treated as 20 independent generation samples. This is execution-reliability evidence, not blind first-pass or hidden-fault detection. |
| 19 | Stripe anecdote in which an agent sees HTTP 400 and declares success | **Not cleared** | No durable first-party Stripe artifact matching the quoted behavior was located. Do not cite a retelling as a Stripe result. |
| 20 | Datadog, [“Delivery guardrails for AI-generated code”](https://www.datadoghq.com/blog/delivery-guardrails-for-ai-generated-code/) | **Verified primary** | Describes roughly 5,000 generated lines that compiled and rendered but were incomplete, unused, unsafe, or subtly wrong. It supports layered static, dynamic, and manual validation; it is not an E2E test-generation experiment. |
| 21 | Uber JUnit migration and claimed conclusion that AI failed, followed by OpenRewrite across 75,000+ classes | **Not cleared** | The exact first-party Uber source and the quoted class count/conclusion were not recovered in this pass. |
| 22 | Airbnb LLM migration of 3,500 files with 97% success | **Not cleared** | The claimed first-party artifact, denominator, and definition of “success” were not recovered. The apparent Uber/Airbnb contrast should not be used without both originals. |
| 23 | Coinbase human-versus-agent comparison claiming lower AI accuracy but higher throughput | **Not cleared** | No durable primary report matching the stated controlled comparison was located. |
| 24 | Meta ACH test-generation case | **Not cleared** | The source acronym and claimed result were not specific enough to map safely to one first-party publication. |
| 25 | Uber DragonCrawl | **Not cleared** | A first-party source tying the named system to the stated LLM test-generation conclusion was not recovered. |
| 26 | Anthropic company case on generated tests | **Not cleared** | No single original was identified from the supplied description. Anthropic’s broader agent guidance must not be relabeled as E2E-generation evidence. |
| 27 | Pinterest company case on generated tests | **Not cleared** | No durable first-party artifact matching the intended claim was located. |
| 28 | Shopify Engineering, [“Introducing Roast: A structured framework for AI workflows”](https://shopify.engineering/introducing-roast) | **Verified primary** | Shopify reports that unconstrained AI workflows were nondeterministic and argues for structured, versioned, testable workflows. This is relevant harness guidance, not a test fault-detection measurement. |
| 29 | OpenAI, [“Introducing SWE-bench Verified”](https://openai.com/index/introducing-swe-bench-verified/) | **Qualified** | The audit supports 61.1%, 68.3%, 1,699 samples, and 93 annotators under the definitions above. It demonstrates that benchmark tests can reject valid fixes; it does not measure generated-test correctness. |
| 30 | Additional source: Shopify Engineering, [“Building an agentic harness that outlasts the model”](https://shopify.engineering/building-an-agentic-harness-that-outlasts-the-model) | **Verified primary** | Describes separating generation from verification and rejecting or downgrading candidates that fail the verifier. It supports independent gates and durable harnesses, but supplies no Playwright/Cypress mutation score. |

### Practitioner reports and field guidance (31–47)

The supplied practitioner summary explicitly named 14 entries. Entries 45–47 are primary artifacts raised elsewhere in the same evidence package: the inherited-suite case study, the corrected Google flake source, and the exact Kent Beck article that replaces an unsupported paraphrase.

| # | Source | Status | What it does and does not establish |
|---:|---|---|---|
| 31 | Birgitta Böckeler: “maintainability sensors,” harness engineering, and AI autonomy | **Not cleared** | The summary combines several themes, but no single durable original containing the stated examples was identified. Attribute only after selecting the exact article or talk. |
| 32 | Gleb Bahmutov, [“Cypress prompt vs record vs code”](https://glebbahmutov.com/blog/cypress-prompt-vs-record-vs-code/) | **Verified primary** | Provides a reproducible case where generated Cypress code asserted only `body.should("be.visible")`, an assertion unlikely to validate the intended behavior. It is one expert demonstration, not a benchmark. |
| 33 | David Adamo Jr.: AI-generated tests as characterization rather than correctness tests | **Not cleared** | The framing is useful, but the original artifact was not recovered. Konstantinou et al. independently support investigating this distinction, but should not be cited as Adamo. |
| 34 | Christie Cosky: practitioner smell list for AI-generated tests | **Not cleared** | No durable original matching the summarized list was verified. |
| 35 | Hector Flores: “vibe testing” and six integrity failures | **Not cleared** | The exact first-person artifact and six-item evidence were not located. |
| 36 | Angie Jones on AI-generated testing | **Not cleared** | The person/topic pair is too broad to support a specific claim without an exact original. |
| 37 | Filip Hric on AI-generated testing | **Not cleared** | No exact primary artifact was verified for the intended claim. |
| 38 | Justin Searls on AI-generated testing | **Not cleared** | No exact primary artifact was verified for the intended claim. |
| 39 | Simon Willison on AI-generated testing | **Not cleared** | No exact primary artifact was verified for the intended claim. |
| 40 | Pandy Knight on AI-generated testing | **Not cleared** | No exact primary artifact was verified for the intended claim. |
| 41 | Luis Garcia on AI-generated testing | **Not cleared** | No exact primary artifact was verified for the intended claim. |
| 42 | Kent Beck interview about agents weakening or deleting tests | **Not cleared** | The named interview and exact wording were not recovered. Use the directly authored article in entry 47 for the narrower claim. |
| 43 | Cypress official social-account post about AI test generation | **Not cleared** | A social post was not treated as durable evidence. The official product documentation in entry 4 is the stronger source. |
| 44 | Thoughtworks Technology Radar, [“Complacency with AI-generated code”](https://www.thoughtworks.com/radar/techniques/complacency-with-ai-generated-code) | **Qualified** | This technique is on **Hold** and supports independent verification of AI-generated code. It is not a “test generation is on Hold” blip. Test-generation guidance elsewhere in the Radar must not be merged into this entry. |
| 45 | Debbie O’Brien, [“How I used AI to fix our E2E test architecture”](https://dev.to/debs_obrien/how-i-used-ai-to-fix-our-e2e-test-architecture-444a) | **Qualified** | First-person evidence for 8/130 local passes and the `workers: 1` CI masking mechanism in one inherited Playwright suite. It is not a representative prevalence estimate. |
| 46 | Google Testing Blog, [“Flaky Tests at Google and How We Mitigate Them”](https://testing.googleblog.com/2016/05/flaky-tests-at-google-and-how-we.html) | **Qualified** | The official 2016 post states that about **1.5% of test runs** are flaky and that **16% of tests** had some flakiness. The 1.5% figure is citeable when attributed to this post and scoped to runs; it should not be attributed to a later paper or described as 1.5% of tests. |
| 47 | Kent Beck, [“Genie Wants to Leap”](https://newsletter.kentbeck.com/p/genie-wants-to-leap) | **Verified primary** | Beck directly describes an agent deleting assertions, deleting tests, or faking an implementation to make checks pass. This supports integrity controls. It does not support the circulating quotation “The genie doesn’t want to do TDD.” |

### Conflicting preprints from the same broad corpus (48–49)

| # | Source | Status | What it does and does not establish |
|---:|---|---|---|
| 48 | Banik et al., [“All Smoke, No Alarm: Oracle Signals in Agent-Authored Test Code”](https://arxiv.org/abs/2606.18168) | **Qualified** | The preprint analyzes 86,156 test-file patches from 33,596 agent-authored PRs across 2,807 repositories and classifies **80.2%** as having weak or no explicit oracle signals. Its taxonomy is syntactic and patch-based; it does not execute tests or measure mutation killing. |
| 49 | Jhanglani et al., [“Beyond Test Presence: Assessing the Quality and Robustness of Agent-Generated Tests in Open-Source Projects”](https://arxiv.org/abs/2607.12068) | **Qualified** | The preprint reports **85.37% strong assertions for agents versus 88.1% for humans**, but a higher static/dynamic flakiness-candidate rate for agents (**0.41 versus 0.30**). Its assertion-strength classifier differs from Banik et al.’s oracle-signal taxonomy. The studies are not directly comparable: they differ in cohort construction, unit of analysis, language/test filtering, and classifiers, as well as taxonomy. |

### Independent follow-up additions (50–59)

| # | Source | Status | What it does and does not establish |
|---:|---|---|---|
| 50 | Teoh et al., [“WebTestPilot: Agentic End-to-End Web Testing against Natural Language Specification by Inferring Oracles with Symbolized GUI Elements”](https://doi.org/10.1145/3797115) | **Verified primary** | PACMSE/FSE 2026 directly evaluates a Playwright-backed LLM browser-oracle system on four open-source apps and 100 manually injected bugs, reporting 99% task completion and 96% precision/recall. A distinct replication study detected 22 of 23 GitHub-issue bugs. These results apply to that system and its benchmarks, not ordinary reusable Playwright/Cypress suites or a sealed production sample. |
| 51 | Lu et al., [“WEFix: Intelligent Automatic Repair of UI Test Flakiness”](https://doi.org/10.1145/3589334.3645628) and [open preprint](https://arxiv.org/pdf/2402.09745) | **Verified primary** | The Web Conference 2024 study removes developer-added waits to reconstruct 122 UI-wait flaky tests from seven open-source projects, then repairs 120. It provides direct repair evidence for Cypress and Selenium under that construction, but it is not LLM generation, does not evaluate Playwright, and does not estimate naturally observed flake prevalence or general repair success. |
| 52 | [“GenIA-E2ETest”](https://doi.org/10.5753/sbes.2025.9927) and [publisher PDF](https://sol.sbc.org.br/index.php/sbes/article/download/37006/36791) | **Verified primary** | SBES 2025 reports supervised natural-language E2E generation on an out-of-scope browser stack across two apps and 12 cases. The 82% precision/85% recall results followed minor human adjustment. “Adaptable” to Playwright/Cypress is not evaluation on those frameworks, and execution success is not mutation killing. |
| 53 | [“Feature-Driven End-to-End Test Generation” (AutoE2E), ICSE 2025](https://doi.org/10.1109/ICSE55347.2025.00141) and [author preprint](https://arxiv.org/abs/2408.01894) | **Verified primary** | The peer-reviewed study reports 79% average feature coverage for Selenium-based AutoE2E on E2EBench. It shows a Cypress example but does not evaluate Playwright/Cypress generated suites. Feature coverage is not behavior-fault detection. |
| 54 | Google Testing Blog, [“Hermetic Servers”](https://testing.googleblog.com/2012/10/hermetic-servers.html) | **Verified primary** | Google describes running hermetic E2E tests on continuous builds for each changelist, with local in-memory/no-network services, seeded data, and request-path logging. This is concrete large-team architecture guidance, not a universal browser-test ratio. |
| 55 | Google Testing Blog, [“Fixing a Test Hourglass”](https://testing.googleblog.com/2020/11/fixing-test-hourglass.html) | **Verified primary** | Google describes retaining a narrower real-backend E2E layer while moving deterministic coverage to hermetic integration tests with fakes and deleting duplicated E2Es. It is an experience report, not a controlled universal prescription. |
| 56 | [Playwright best practices](https://playwright.dev/docs/best-practices) | **Verified primary** | Official guidance recommends testing user-visible behavior and prioritizing user-facing attributes and explicit contracts. It is a design rule, not evidence that those locators or assertions detect the intended fault. |
| 57 | [Playwright test assertions](https://playwright.dev/docs/test-assertions) | **Verified primary** | Official documentation states that async web assertions wait until the expected condition is met. Retryability reduces timing noise; it cannot make an incorrect or weak postcondition semantically meaningful. |
| 58 | [Cypress conditional testing](https://docs.cypress.io/app/guides/conditional-testing) | **Verified primary** | Official guidance says conditional testing is safe only after state has stabilized and recommends anchoring decisions to a non-mutable source of truth. This supports deterministic state controls, not a measured flake rate. |
| 59 | Google Testing Blog, [“Just Say No to More End-to-End Tests”](https://testing.googleblog.com/2015/04/just-say-no-to-more-end-to-end-tests.html) | **Verified primary** | Google describes diagnosis cost and flakiness in an E2E-heavy strategy and advocates a test-pyramid balance. It is a first-party large-team experience report, not a universal numeric prescription for E2E count. |

## Six claims that should not be cited as originally stated

| Circulating claim | Audit result | Safe replacement |
|---|---|---|
| “Google found 1.5% of tests are flaky,” attributed to an ICSE-SEIP 2017 paper | **Incorrect attribution and denominator.** The inspected primary support is Google’s 2016 blog, which says 1.5% of **test runs** and 16% of tests with some flakiness. | Cite entry 46 with both the artifact and denominator. |
| “100% coverage, 4% mutation score” and “$47,000 refund” | **Reject.** The claims circulate among vendor articles without a recovered independent original. | Use an executable mutation benchmark with a committed protocol and raw report. |
| “Ox Security found fake coverage in 40–50% of 300+ repositories” | **Reject as empirical evidence.** The number was not recovered outside a secondary newsletter-style account. | Cite a primary dataset, sampling frame, classifier, and replication package if one becomes available. |
| Kent Beck: “The genie doesn’t want to do TDD” | **Reject as a quotation.** The exact wording was not found in a primary artifact. | Cite entry 47’s documented examples without inventing the quote. |
| Uber AutoCover delivered “2–3×” and “21,000 hours” | **Reject pending a primary Uber source.** Available mentions trace to third-party presentation summaries. | Recover the original talk, slides, or engineering report with definitions and denominator before use. |
| Thoughtworks Radar put “AI test generation” on Hold | **Incorrect.** The Hold entry is “Complacency with AI-generated code.” | Cite entry 44 exactly; do not relabel the blip. |

## Engineering implications

The following are conservative benchmark-design implications of the cited evidence, not direct prevalence estimates or proofs that every browser-E2E workflow needs the same controls:

- Generated tests warrant an independent oracle-strength review in this benchmark. Official Vitest and Cypress guidance identifies weak/intent-unaware assertions; controlled assertion-review research and agent-authored patch studies make a single review pass an insufficient assurance.
- Passing, compiling, rendering, or increasing coverage alone cannot establish fault detection. Meta’s filter chain, the CoverUp study, SWE-Mutation, OpenAI’s benchmark audit, and Datadog’s field report motivate that distinction through different mechanisms.
- Human review should not be the only control. Kaufman et al. found a pronounced asymmetry in recognizing incorrect assertions, while first-party harness reports recommend separate verifiers and executable gates.
- Browser-test claims require browser-test evidence. WebTestPilot supplies direct Playwright-backed fault-detection evidence for one agentic oracle system; AutoE2E measures Selenium-based feature coverage; Slack measures Playwright execution reliability; WEFix measures reconstructed Cypress/Selenium wait-fault repair; Playwright and Cypress document oracle affordances and limitations. These studies answer different questions and cannot be merged into one generic “AI E2E quality” rate.
- Any comparison of the Banik and Jhanglani preprints should present both. They use different cohorts, analysis units, and definitions, so their headline assessments are not directly comparable; both still motivate inspecting assertion quality, and the latter reports more flakiness candidates in agent tests.
- Large-team practice in the Google reports emphasizes a small high-value E2E layer, hermetic disposable dependencies, seeded state, and moving deterministic coverage into integration tests. It does not support maximizing browser-test count.

## The browser-E2E evidence boundary

Direct peer-reviewed evidence is limited but no longer absent. WebTestPilot (PACMSE/FSE 2026) evaluates an LLM-based browser-E2E oracle system using Playwright-backed scripts on four open-source web applications with injected behavior faults and a separate 23-case real-bug replication study. AutoE2E (ICSE 2025) evaluates Selenium-based feature-driven generation. Their results apply to custom systems and author-built benchmarks; they do not establish the fault-detection rate of conventional LLM-authored Playwright/Cypress test files.

The remaining evidence still falls into distinct categories that must not be pooled:

1. one direct Playwright-backed agentic-oracle study with manually injected faults and a separate real-bug replication evaluation;
2. unit-level generated-test and oracle studies in Java or Python;
3. mining of agent-authored test patches across repositories;
4. browser-E2E execution reliability, reconstructed wait-fault repair, locator robustness, feature coverage, and oracle-shape evidence without comparable semantic mutation scoring.

This boundary is a warning against silently converting unit-test findings or one custom agent benchmark into general browser-test rates. In this bounded review, we did not locate an independently sealed, broad multi-repository evaluation of reusable LLM-generated Playwright/Cypress suites under release-like isolation. A relevant adjacent preprint, [ReproBreak](https://arxiv.org/abs/2605.12158), provides a dataset of reproducible web-locator breaks, but it does not answer that broader question.

## Benchmark implications for this repository

The evidence points to a causal benchmark, not a larger pile of source-shape examples:

1. **Pair every weak test with a strong control.** The strong test must pass on the correct app and fail on a behavior-faulted app; the weakened test must remain green against the same fault.
2. **Inject behavior and oracle faults.** Include missing postconditions, permissive response codes, swallowed failures, weak ARIA snapshots, stale state, wrong redirects, and framework-specific retry or sequencing faults.
3. **Report fault detection separately from reviewer detection.** A reviewer can correctly identify a weak assertion even when a generator benchmark has not shown that the repaired test kills the fault.
4. **Balance Playwright and Cypress.** Publish per-framework recall and mutant-kill rates so one framework cannot hide the other.
5. **Measure false confidence.** Track weak-test false-green rate, strong-control kill rate, reviewer TP/FP/FN, assertion weakening, actual-behavior encoding, and repeated-run instability.
6. **Freeze the protocol before model runs.** Fix models, repetitions, thresholds, corpus digest, mutation operators, and adjudication rules before execution.
7. **Keep public and sealed claims separate.** Committed cases are public development evidence. A final generalization claim needs a non-public corpus, independently enforced isolation, and external or human adjudication.
8. **Do not let one model author and judge its own benchmark.** Use model-family-independent and human review for contested labels, and publish disagreements rather than resolving them invisibly.

These controls make the repository’s executable Playwright/Cypress fixtures useful evidence for the presently under-studied browser-E2E surface. They still do not turn a public development corpus into a neutral, sealed benchmark or make unit-test research directly transferable without qualification.
