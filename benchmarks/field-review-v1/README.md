# Field review v1 — upstream outcomes, with a denominator

The reviewer's findings have been submitted upstream as pull requests. Whether each one was right is then judged by someone with no stake in this project: the maintainer of the repository being changed.

That is the strongest evidence this project has, and until now it was reported without a denominator. "14 merged upstream PRs" is not a rate. A rate needs the rejections next to it.

## What changed when the denominator was computed

The roadmap is written by the author of the skill, which makes it the wrong place to read a merge rate from. Sweeping this account's actual pull requests found **seven the roadmap did not list** — and the omissions ran in both directions:

- **Two merged fixes were missing** (`apache/zeppelin#5180`, `#5262`), so the campaign count was *under*-reported.
- **Three rejections were missing** (`QwikDev/qwik#8727`, `calcom/cal.diy#28466`, `n8n-io/n8n#27035`), so the failures were invisible.
- **Two open PRs** (`RocketChat/Rocket.Chat#41792`, `Kong/insomnia#10405`) sat in the roadmap's "Queued" table as if they were still candidates.

A curated list drifts. That is the argument for generating this one.

## Inclusion rule (mechanical)

Every pull request opened by the account, against a repository the account does not own, whose body names `e2e-reviewer` or `e2e-skills`. Outcomes are whatever GitHub reports at the time of the run. Nothing is filtered for how it looks.

## Results

| | |
|---|---:|
| Submitted | **29** |
| Repositories | **26** |
| Merged | **16** |
| Closed without merging | **6** |
| Still open | **7** |
| Merge rate among decided (16 / 22) | **73%** |

Every row is in [`ledger.json`](ledger.json) with a link. Open any of them.

## What this supports, and what it does not

- **Supported:** maintainers of 26 unrelated projects accepted or rejected these specific changes, and each decision is public and checkable.
- **Not supported: reviewer precision.** A merge means a maintainer took a patch. It does not certify that the finding's severity was classified correctly. A rejection is frequently about scope, staleness, or timing rather than the merits — of the six rejections, two were superseded by a later PR from this account that did merge, one was closed under a 60-day staleness policy without review, and one was closed because the maintainer landed the change themselves.
- **Not supported: recall.** Nothing here says what the reviewer missed.

## Stated biases

- **The denominator is a lower bound.** The submission footer is optional, so a PR that carried no marker does not appear. An unmarked *rejection* would bias the merge rate upward. The direction is known; the size is not.
- **The sample is self-selected.** Repositories were chosen by the author, and a fix is only submitted when it looked worth submitting. This measures accepted contributions, not detection accuracy on arbitrary code.
- **The rule admits non-test changes.** One closed entry (`VoltAgent/awesome-agent-skills#836`) is a directory-listing submission, not a test fix. It matches the rule, so it stays: narrowing the rule after seeing the results is how a mechanical sweep turns back into a curated list. Excluding it gives 16 merged of 21 decided (76%).

## Reconciling with the roadmap's count

The two numbers differ on purpose and must not be added together.

| | Count | Why it differs |
|---|---:|---|
| This ledger, merged | 16 | Marker-visible PRs of every kind, including two reviewer-informed maintenance merges (`apache/zeppelin#5262`, `#5348`) that fix no false-green test. |
| [Roadmap](../../docs/roadmap.md), Merged | 15 | False-green campaign only, and it includes `calcom/cal.diy#28486`, which merged without carrying a marker and so is invisible to the sweep. |

That last row is the undercount bias made concrete: one real merge exists that this mechanical rule cannot see.

## Relationship to the other benchmarks

[Field scan v1](../field-scan-v1/README.md) runs the deterministic scanner over pinned public repositories and reports a **null result**: zero P0 hits. This ledger is the other half of the same question, and the contrast is the finding. The deterministic tier is not what produced these 16 merges — the reviewer skill, with a model in the loop, is.

## Reproducing

```bash
python3 scripts/evals/build-field-review-ledger.py \
  --output benchmarks/field-review-v1/ledger.json
```

Requires an authenticated `gh`. It reads public pull-request metadata and writes only to `--output`; it opens nothing, comments nowhere, and changes no upstream repository.
