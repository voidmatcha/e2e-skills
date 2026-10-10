# Generator skill-effect v3: does the generator's locator discipline survive a markup refactor, and which layer carries it?

Status: **Historical design record.** The protocol was frozen before model calls and ended `INCONCLUSIVE` (thin pool): 9 of 36 tasks qualified after the preregistered extension, below the minimum of 12. See [`README.md`](README.md) and [`protocol.json`](protocol.json) for the executed contract and result.

## Why v3, and why the primary metric changes

[v1](../generator-skill-effect-v1/README.md) was `INCONCLUSIVE`: `claude-sonnet-5-5` without the skill already killed 0.927 of the seeded faults on criteria-listed apps. [v2](../generator-skill-effect-v2/README.md) was `INCONCLUSIVE` again, this time on a thin pool: of 24 harder brief-style tasks only 3 had a no-skill fault-kill in the keep band `[0.40, 0.80]`; 20 sat at the ceiling. Two runs now say the same thing: **on author-written small apps this model verifies nearly every stated behavior without help, so fault-kill has no headroom and cannot separate the arms.** What did separate them, descriptively, in both runs is **behavior-preserving markup-refactor survival**: v1 skill 23/30 versus no-skill 12/28; v2 no-skill screen about 0.50 over 48 calls. Every v1 refactor failure was an id or class selector on an element that kept its role, label and text. v3 therefore makes refactor survival the primary metric and asks two questions: does `full-fixed` (the current skill with its reachability fixes, [`arms/full-fixed/`](arms/full-fixed/CHANGES.md)) deliver it, and does the value sit in the written locator and assertion rules rather than in the process layers around them.

## Arms

| Arm | Text staged | Question it answers |
|---|---|---|
| `full-fixed` | `arms/full-fixed/playwright-test-generator/` plus `e2e-reviewer` (scripts staged from `skills/`) | the current product with items 1–6 applied |
| `full` | the `2.0.0` `skills/playwright-test-generator/` snapshot as frozen for v2, plus `e2e-reviewer` | the shipped product before the fixes |
| `lean` | v2's byte-frozen `arms/lean/SKILL.md`, plus `e2e-reviewer` for its `scan.sh` step | the rules plus a run-and-fix loop, without exploration, approval, V1–V6 or the reviewer |
| `rules-only` (optional) | a benchmark-only text holding only `code-rules.md` § Selector Priority (with the item 4 text-only rule), § Hard rules, § Spec Rules' forbidden table, and `best-practices.md` § Locators and § Assertions; no steps, no run loop, no scanner | whether the written rules alone are the active ingredient |
| `no-skill` | nothing | baseline and headroom screen |

Same host, model, tools (`Read,Grep,Glob,Bash,Write,Edit,Agent`), prompt frame, pre-granted approvals and staging as v2. `rules-only` is derived from the real skill by deletion only, like `lean`; its derivation is listed in `protocol.json` sentence by sentence.

## Metrics

- **Primary: refactor survival score** per call, 1 when the delivered specs are green 3/3 on the correct app **and** green on the behavior-preserving markup refactor, else 0 (v2's preregistered secondary, promoted). A deliverable that is not clean scores 0, so the metric cannot be gamed by brittle tests that happen to pass once.
- **Guard: clean-run pass rate** (green 3/3) of every skilled arm not more than 0.05 below `no-skill`.
- **Guard: fault-kill non-inferiority.** Effective fault-kill rate (v1/v2 primary) of every skilled arm not more than 0.10 below `no-skill` (mean and paired CI lower bound above -0.10). Reported, never a source of lift claims: it has no headroom here.
- **Secondary:** process compliance from the stream-json transcript (v2 indicators plus the v3 "V6 verbatim verdict rate" and the heuristic "legitimate Complete rate", both only for `full` and `full-fixed`); scanner P0 and P1/P2 counts on the delivered files; locator census on the delivered files (`#id`/`.class` selectors, `.nth()/.first()/.last()`, `getByRole/Label/Text/TestId` counts per call), which is the mechanism the primary is supposed to move; cost and wall-time multiples over `no-skill`.

Self-reported status is always cross-tabulated against compliance, never read alone.

## Tasks and headroom screen

**Candidate pool:** the 24 v2 pool tasks (their 48 screen calls are spent as data but the tasks themselves are not: v2's skilled arms never ran on them, and v2's screen measured fault-kill, not the primary here) plus new tasks whose markup and locator surface is richer: text-only counters and status lines, lists and tables of repeated components, conditionally rendered regions, nested interactive items (a card with its own buttons), dialogs, and forms whose inputs have labels only through `aria-labelledby`. Each new task ships the same artifacts as v2 (brief, five faults with `brief_phrase`, refactor variant, author strong/naive specs) plus a **refactor manifest** listing which ids and classes the refactor renames and asserting that no role, label, name or visible text changes; `validate` checks the manifest against the two DOMs. The author strong spec must survive the refactor and the author naive spec (id-based) must fail it, which fixes the refactor's discriminating power before any model call.

**Screen on the primary metric, `no-skill` only:** two repetitions per pool task, shuffled with the screen seed. Keep band for the mean no-skill refactor survival `[0.25, 0.75]` (a proportion over two calls takes values in {0, 0.5, 1}, so with two repetitions the band keeps exactly the tasks at 0.5; if fewer than 12 qualify, raise the screen to three repetitions on the near-band tasks before falling back, never keep a task at 0 or 1 by fallback alone). Freeze the kept set, screen digests and spend before any skilled call; screening repetitions are never reused as comparison data. Selection effect stated in advance: keeping tasks on which no-skill scored in the middle makes its fresh repetitions regress toward the pool mean in either direction; reported, not corrected.

## Decision rule (to be frozen in `protocol.json` before any call)

- **Primary comparison: `full-fixed` versus `no-skill` on refactor survival.** `PASS` needs paired lift (per-task means) >= +0.20, case-cluster bootstrap 95% CI lower bound > 0, the clean-pass guard met, the fault-kill guard met, and a kept-set `no-skill` primary < 0.85 (ceiling rule on the primary). `INCONCLUSIVE` on any unscored call, drift, spend-cap stop, incomplete schedule or ceiling; otherwise `FAIL`.
- **Preregistered secondaries, each with its own PASS/FAIL:**
  1. `full` versus `no-skill`, same rule: confirms v1's descriptive 23/30 versus 12/28 under a preregistered rule.
  2. `lean` versus `full-fixed` and `rules-only` versus `full-fixed`: non-inferiority on the primary with margin 0.10 (mean within 0.10, paired CI lower bound of the difference above -0.10), plus the clean-pass guard.
  3. `lean` and `rules-only` versus `no-skill`, same rule as the primary comparison.
  4. `full-fixed` versus `full` on the heuristic legitimate-Complete rate and on the V6 verbatim verdict rate: +0.30 with CI lower bound > 0 each (the item 2/5 hypotheses).
  5. Cost and wall-time multiples per arm, reported plainly.
- Locator census and scanner counts are reported without thresholds.

## Spend and power

Screen: up to 36 pool tasks x 2 (plus a possible third repetition on near-band tasks) x `no-skill` at about $0.06 = $5 to $8. Final: 12 kept tasks x 3 repetitions x arms; per-call estimates from v1/v2 (`no-skill` $0.06, `rules-only` about $0.08, `lean` about $0.15, `full` $0.34, `full-fixed` about $0.40): about $37 with five arms, $34 with four. Scoring is model-free. **Spend cap $120** across both stages, $4 per call, 1500 s per call, two workers; the cap is ample, so no repetition is cut for cost. Power: the primary is a per-task mean of a 0/1 outcome over three repetitions; with 12 kept tasks and an assumed paired-difference SD of 0.35, the standard error is about 0.10 and the minimum detectable lift about 0.28 at 80% power (two-sided 0.05). v1's descriptive gap was 0.34 (0.767 versus 0.429), so the design can see an effect of that size and cannot see a 0.10 one; a `FAIL` means "no large effect shown". The 0.10 non-inferiority margin sits inside the noise, so a non-inferiority `PASS` means "no large deficit shown", not "equivalent".

## What each outcome means for the product

| Outcome | Reading | Product consequence |
|---|---|---|
| `full-fixed` >> `no-skill` and `rules-only` ~ `full-fixed` (non-inferior) | the written locator and assertion rules are the active ingredient; the process layers add cost, not refactor robustness | ship a lean or rules-first generator; move verification of generated specs to `e2e-reviewer` (which already owns the rules' semantics) and keep V1–V6 as an opt-in heavy tier |
| `full-fixed` >> `no-skill`, `lean` ~ `full-fixed`, `rules-only` worse | the rules need the run-and-fix loop and scanner to land | ship `lean` as the default tier; heavy verification opt-in |
| `full-fixed` >> `lean` and `rules-only` | exploration, approval tables or V1–V6 contribute to robustness | keep the full pipeline; apply items 1–6 (already in 2.0.0) and measure cost |
| `full-fixed` ~ `no-skill` on the primary with the ceiling rule met | the skill does not move locator robustness on these tasks | do not claim it; revisit the rules (the locator census says which selectors the no-skill arm used) |
| `full-fixed` > `full` on completion rates but equal on the primary | items 1–6 fixed reachability without changing the tests | keep the fixes for honesty of the completion report; make no quality claim from them |
| ceiling on the primary (kept-set `no-skill` >= 0.85) | the richer-markup tasks did not produce brittle no-skill locators | `INCONCLUSIVE`; the next design needs apps whose accessible names are scarce by construction |

## Limits stated in advance

- One host and model family; three repetitions; author-written apps with in-memory state; one author-written refactor per task, so the primary measures survival of that rename, not general locator robustness.
- The refactor variant renames ids and classes and keeps roles, labels, names and text. A generator that uses `getByText` on a renamed id survives by construction, so the metric rewards exactly the discipline the rules teach; it says nothing about locators that break when visible text changes.
- `rules-only` and `lean` are deletions of the real skill; a null difference between them and `full-fixed` is bounded by the design's power, not proof of equivalence.
- Headless skill behavior with pre-granted approvals is what is measured; the interactive approval gate is not.
- The legitimate-Complete indicator is a transcript heuristic, kept as such.

## Decisions made before the freeze

1. No spend cap; every cost is recorded.
2. Include `rules-only` in the frozen final schedule if the screen qualifies enough tasks.
3. Use 22 repaired v2 tasks plus 14 new richer-markup tasks, for a validated pool of 36.
4. Freeze distinct `full` and `full-fixed` snapshots before any call. The benchmark ran before the unpushed 2.0.0 branch was published; snapshot bytes, not release labels, define the arms.

## Reproduce (once the runner exists)

The runner will be `scripts/evals/run-generator-skill-effect-v3.py` with v2's `validate`, `freeze --stage pool`, `screen`, `score`, `select`, `run`, `score`, `analyze` stages, the arms above, refactor survival as the screened and primary metric, the locator census, and the two added compliance indicators. `run` refuses to start on digest drift or an unfrozen prior stage; `select` refuses scores that did not come from a `no-skill` screen; delivered files are archived under `reports/*-artifacts/` so `score` can rerun without model calls.
