# Generator unchanged-outcome v6

Status: **COMPLETE; `DIRECTIONAL_SIGNAL`**. The frozen eight-call run and all eight causal browser adjudications completed without retries.

This prospective eight-call experiment corrects one evaluator boundary found after v5's completed eight-call result. V5 formally credited before 0/4 and after 2/4 with all browser and scope guards passing. In the two after misses, the outgoing packet contained the complete exact V1 heading and body but omitted its one final newline at end-of-message. The frozen v5 result remains unchanged.

V6 accepts either the original exact section or that exact section with **one terminal LF removed only when the remaining section ends at end-of-message**. Internal bytes, heading, list markers, spacing and order remain exact. Truncation, CRLF substitution, multiple omitted newlines and suffix text after the trimmed form receive no credit. All approved scenario fields and the same receiver's completed reviewer `PASS` remain required. Scoring and analysis still recompute from the digest-bound transcript.

`packet-boundary-preflight.json` replays all eight v5 transcripts through both rules. Old credit is before 0/4, after 2/4; boundary-corrected credit is before 0/4, after 4/4. This is **posthoc calibration only**, not a revised v5 outcome or v6 evidence. Earlier calls are never pooled. The original v5 runner is immutable and included in the v6 freeze bindings.

The v5 case mechanisms, runtime path classification and transcript resolution remain the baseline. V6 prospectively changes completion labels to `Render N complete` and render delay to 750 ms. Before is the exact v2 after snapshot; after reads the final current `verification-rules.md` at freeze and overlays only that file. Both arms receive identical frozen scenario facts and runtime approvals without an extra handoff reminder.

Runtime paths remain separately listed output, not product writes: standard timestamped `.playwright-cli/page-YYYY-MM-DDTHH-MM-SS-mmmZ.yml`, `test-results/.last-run.json`, and one safe result-directory slug containing `trace.zip` or `error-context.md`. The default trace-on fixture configuration is digest-pinned. Every other non-tests path fails scope. Runtime path membership is a classification, not creator provenance or artifact authenticity. The retained 17-candidate runtime preflight from v5 is also bound.

After must reach at least 3/4, strictly above before without per-case decline, while every candidate passes clean 3/3, markup refactor, zero P0, scope, timeout and causal DOM/sync/disabled guards. Two correlated constructed cases and two repetitions provide bounded development evidence, without release, generalization, statistical significance or cost claims.

```sh
python3 scripts/ci/test-generator-unchanged-outcome-v6.py
python3 scripts/evals/run-generator-unchanged-outcome-v6.py plan
python3 scripts/evals/run-generator-unchanged-outcome-v6.py readiness --output /absolute/external/readiness.json
# Freeze only after final product bytes, model-free readiness and draft review:
python3 scripts/evals/run-generator-unchanged-outcome-v6.py freeze --readiness /absolute/external/readiness.json
python3 scripts/evals/run-generator-unchanged-outcome-v6.py run --allow-live --output /absolute/external/final.json
python3 scripts/evals/run-generator-unchanged-outcome-v6.py score /absolute/external/final.json --output /absolute/external/scores.json
python3 scripts/evals/run-generator-unchanged-outcome-v6.py analyze /absolute/external/scores.json --audit /absolute/external/audit.json --output /absolute/external/results.json
```

The cap is eight sequential calls, one per cell, without retries and above a 4 GiB disk floor. Missing or unverifiable evidence remains incomplete. Browser causal failure attribution still requires a separate bound audit. Original reports and transcripts remain external.

## Frozen result

The preregistered packet score was before **0/4**, after **4/4** (two after credits in each case), above the after ≥3/4 bar with no per-case decline. All eight candidates passed clean 3/3, markup refactor, zero scanner P0, timeout and scope guards. All 24 fault runs were red; independent line-mapped raw JSON and trace review attributed the eight primary failures to the final Async value DOM assertion after the corresponding render completion and committed mutated value `0`. Synchronous and disabled mutants failed at their intended assertions. The frozen analyzer returned `DIRECTIONAL_SIGNAL` with `guards: true`.

The sanitized [result](reports/results.json), [scores](reports/scores.json), [causal audit](reports/audit.json), [generation report](reports/final.json), and generated [spec artifacts](reports/final-artifacts/) are retained here. Original browser JSON, traces and model transcripts remain in the external `gen-unchanged-outcome-v6-run` cache directory; the source-line audit binds their digests. This is directional development evidence for exact reviewer-packet handoff on two correlated constructed fixtures, not an independent release or generalization result. Both arms already killed the DOM fault 4/4, so v6 does not establish an additional fault-detection benefit. Billed USD was not available.
