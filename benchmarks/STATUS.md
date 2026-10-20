# Benchmark results

The historical evidence is preserved on [Hugging Face](https://huggingface.co/datasets/voidmatcha/e2e-skills-benchmarks). This page summarizes the 3.0.0 evidence; the [immutable manifest](external-evidence.json) pins the complete pre-cleanup Git snapshot: 4,726 original files, 116,282,107 bytes. Original protocols, reports, adjudications and negative outcomes remain unchanged.

## Results and scope

| Component | Observed result | What the result covers |
| --- | --- | --- |
| Reviewer | Full stable F1: 0.987654 on `gpt-6-sol`, 1.000000 on `gpt-6.1-sol`; both passed their frozen gates. `gpt-6-luna` scored 0.886076 and failed. | Same 36 previously observed public cases, three sequential arms, five repetitions; 540 tool-free calls per model. Not unseen-project accuracy or scanner benefit. |
| Generator | Earlier comparison: official 6/6 versus current 5/6 completed workflows; a later successful replay is separate. Complex comparison: all four arms detected 9/9 selected faults, passed 9/9 healthy repetitions and 3/3 recoveries, survived 2/3 markup refactors. | Three authored tasks, 96 phases. No incremental detection or refactor-survival gain from extra review was observed; extra review cost more. |
| Debuggers | Public-case diagnosis met its declared noninferiority checks. | 107 public cases; tool-free diagnosis does not establish autonomous repair advantage. |
| Scanner and integration | Current regressions cover ESLint configuration/import handling, scanner tiers, installation collisions, probe safety and host routing. Selected native host and browser checks are preserved separately. | Offline CI proves current contracts; selected live runs prove their recorded snapshots and environments. |
| Portable probes | Requested V2/V3 probes completed on Tags; requested V3 completed on Flashcards. | Two known authored apps. Initial failures, setup correction and two `CANNOT_VERIFY` controls are retained. Assertion sensitivity and app-fault detection are separate verdicts. |
| Independent review pilot | On Choices and SensitivityUtils, generic and frozen-reviewer edits both detected the selected defects: 2 ties. | Confirmation cohort not launched. Reviewer used more actor time and input tokens in both pairs. |

Reviewer results use frozen skill SHA-256 `7ff53a2999b80f2f777679fe8dd80941f6ad84b74d36ada43084573f3eeb3c10`. Later scanner/configuration changes are outside that snapshot. These runs do not evaluate every final 3.0.0 byte or establish a controlled ranking of models.

Findings have contributed to **15 merged upstream PRs**. These are self-selected adoption case studies, not a representative accuracy sample.

## Read the evidence

- Reviewer: [v22, Sol](https://huggingface.co/datasets/voidmatcha/e2e-skills-benchmarks/blob/2992d57564bb5b0d7eae0650a64f392481211d41/snapshots/git-93afd3b105b869b15589634c88676230c7d92254/benchmarks/reviewer-holdout-v22/README.md), [v23, Luna](https://huggingface.co/datasets/voidmatcha/e2e-skills-benchmarks/blob/2992d57564bb5b0d7eae0650a64f392481211d41/snapshots/git-93afd3b105b869b15589634c88676230c7d92254/benchmarks/reviewer-holdout-v23/README.md), [v24, 6.1 Sol](https://huggingface.co/datasets/voidmatcha/e2e-skills-benchmarks/blob/2992d57564bb5b0d7eae0650a64f392481211d41/snapshots/git-93afd3b105b869b15589634c88676230c7d92254/benchmarks/reviewer-holdout-v24/README.md).
- [Installation, native hosts, generator comparisons and probe closeout](https://huggingface.co/datasets/voidmatcha/e2e-skills-benchmarks/blob/2992d57564bb5b0d7eae0650a64f392481211d41/snapshots/git-93afd3b105b869b15589634c88676230c7d92254/benchmarks/release-readiness-v1/README.md).
- [Complete historical status and qualifications](https://huggingface.co/datasets/voidmatcha/e2e-skills-benchmarks/blob/2992d57564bb5b0d7eae0650a64f392481211d41/snapshots/git-93afd3b105b869b15589634c88676230c7d92254/benchmarks/STATUS.md).
- [Full archive and restoration metadata](https://huggingface.co/datasets/voidmatcha/e2e-skills-benchmarks/blob/2992d57564bb5b0d7eae0650a64f392481211d41/snapshots/git-93afd3b105b869b15589634c88676230c7d92254/README.md).

- [Independent OSS comparison and requested probe studies](https://huggingface.co/datasets/voidmatcha/e2e-skills-benchmarks/blob/8d059d6d1399e91c22349b696c9fac129ebb75cf/raw/reviewer-probe-studies-20261020/README.md).

## Restore or reproduce

Normal CI runs current product and shared harness regressions without downloading historical evidence. To audit a past result, restore outside the checkout:

```bash
bash scripts/dev/fetch-benchmark-evidence.sh --dry-run
bash scripts/dev/fetch-benchmark-evidence.sh --output /absolute/new/evidence-root
bash scripts/dev/fetch-benchmark-evidence.sh --verify-only --output /absolute/new/evidence-root
```

The fetcher refuses an existing destination and verifies archive and metadata SHA-256, every original file, Git blob ID and executable mode. `bash scripts/ci/ci-evidence.sh /absolute/new/evidence-root` downloads the pinned source archive and replays that commit's historical CI in a temporary workspace. It does not evaluate the current product. Read each study's frozen protocol before running live models or browsers.

Removing evidence from the current Git tree reduces checkout size, not existing Git history. Local originals are preserved; the migration does not rewrite commits.
