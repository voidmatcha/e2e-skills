# Pre-remediation audit of the holdout v3 oracle

Freeze time: 2026-07-29 18:34 KST, before the pre-remediation scored model
execution.

## Frozen semantic inputs

| Input | SHA-256 |
|---|---|
| `scripts/evals/reviewer-holdout-v3.json` | `fb7f5eb8560687ee8d8a9fedac24fb0f4b674e54e9c610b76404a30330fc4a2d` |
| `scripts/evals/reviewer-validation-protocol-v3.json` | `860c1207bcfe441e411609cecc1fd0aa287304e192563a737bdb2536a43d7731` |
| `skills/e2e-reviewer/SKILL.md` | `95bae0e3d52b3efccd83c1ef2291654545b3906887b5deaa164474f5a0241ee5` |
| `skills/e2e-reviewer/references/pattern-reference.md` | `a1ce091681a6a4c3dbba55df09b8e61d6b3387753ee850c1f1ad4c1561cac7c4` |

The first audit froze the labels, sources, skill contract, and decision
protocol before scoring. Preflight runs subsequently exposed evaluator
infrastructure faults, and the first complete Codex run plus independent
product review exposed product and corpus defects. Those findings led to a
documented remediation cycle. This file preserves the original audit; it does
not describe the final refrozen snapshot.

## Source-only adjudication

Two fresh Codex-native auditors independently read only:

- `scripts/evals/files/holdout-v3/**`
- `skills/e2e-reviewer/SKILL.md`
- `skills/e2e-reviewer/references/pattern-reference.md`

They were explicitly barred from the labeled corpus, benchmark reports,
mutation notes, prior reviews, and Git history. Neither changed files.

Both reconstructed the same unique gold set:

- 24 non-overlapping findings
- all 24 base pattern families
- 9 P0, 12 P1, 3 P2
- no defensible additional finding at that snapshot

These were two source-only model reconstructions, not blind human annotation.
Both auditors ran on the Codex host and shared the repository's written
taxonomy, so their agreement reduced labeling mistakes but did not remove
model-family or contract-author bias.

Licensed under Apache-2.0 with the repository.
