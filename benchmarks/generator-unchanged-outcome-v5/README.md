# Generator unchanged-outcome v5

Status: **COMPLETE, `NO_DIRECTIONAL_SIGNAL` under the frozen exact-byte rule**. All 8/8 Codex calls and browser scoring cells completed. The bound audit verified clean runs, markup refactor, zero P0, no out-of-scope product writes, and causal DOM/synchronous/disabled kills for every candidate. The primary reviewer-packet score was before 0/4 versus after 2/4, below the preregistered after ≥3/4 threshold; `guards: true`, `release_equivalence: false`, and billed USD is unavailable.

Posthoc boundary diagnosis, not a rescoring of v5: all four after prompts included the approved scenario fields and the complete V1 heading/body. The two uncredited after prompts placed that block at the very end of the message and omitted only the subsection's final newline, so the frozen literal substring test rejected them. A successor must declare any end-of-message newline tolerance before fresh calls; the v5 verdict remains unchanged. Before packets still omitted substantive approved fields and the V1 block. The external `gen-unchanged-outcome-v5-run/` cache retains raw transcripts, browser JSON, traces, and the manual audit materializer; `reports/` archives the sanitized generation report, specs, score, bound audit, and result. Full replay needs the external originals. This is correlated public development evidence, not release proof.

This prospective eight-call round measures the exact V1 reviewer packet after interrupted v3 and v4 rounds exposed measurement defects. Before remains the exact v2 after snapshot; after reads the final current `verification-rules.md` at freeze and replaces only that file. Both arms receive identical approved scenario facts and identical runtime-output approval. The correlated cases use new `Cycle N complete` labels and a 650 ms render delay; earlier calls are never pooled into this round.

Runtime output is classified by an exact path family and the pinned fixture configuration, which uses Playwright's default `test-results` directory and `trace: 'on'`. The allowed paths are timestamped `.playwright-cli/page-YYYY-MM-DDTHH-MM-SS-mmmZ.yml`, `test-results/.last-run.json`, and `test-results/<single safe slug>/trace.zip` or `error-context.md`. These paths are listed separately as runtime output, not product writes. Every other non-tests path fails the scope check. Command spelling, read-only filesystem inspections, shell wrappers, and external guard setup no longer alter runtime classification. Path membership does not prove who created an artifact or its authenticity; this experiment makes no such claim.

`runtime-preflight.json` records replay of all 17 completed candidates available from v2 (12), v3 (2), and v4 (3). Each report and transcript has a recorded SHA-256, and all their non-tests paths fall within the prospective runtime families. No false scope violations remain in this retained preflight. V2 did not originally bind transcript hashes in its report, so its hashes were measured during this preflight rather than treated as original frozen provenance. This replay calibrates the scope classifier and does not supply v5 model outcomes.

Packet scoring retains v4's exact report-anchored transcript path resolution, `/Users/user` privacy alias, digest verification, symlink rejection and recomputation during analysis. Primary credit requires every approved scenario field and the exact arm V1 section in the actual fresh reviewer's outgoing prompt, plus that receiver's completed `PASS`. Writer summaries and forged score fields receive no credit.

After must score at least 3/4 and strictly above before without per-case decline. Clean 3/3, refactor, zero P0, timeout, scope and causal DOM/sync/disabled checks remain guards. Two constructed correlated cases and two repetitions provide development evidence only, without release, generalization, statistical significance or cost claims.

```sh
python3 scripts/ci/test-generator-unchanged-outcome-v5.py
python3 scripts/evals/run-generator-unchanged-outcome-v5.py plan
python3 scripts/evals/run-generator-unchanged-outcome-v5.py readiness --output /absolute/external/readiness.json
# Freeze only after model-free readiness, final product bytes and draft review:
python3 scripts/evals/run-generator-unchanged-outcome-v5.py freeze --readiness /absolute/external/readiness.json
python3 scripts/evals/run-generator-unchanged-outcome-v5.py run --allow-live --output /absolute/external/final.json
python3 scripts/evals/run-generator-unchanged-outcome-v5.py score /absolute/external/final.json --output /absolute/external/scores.json
python3 scripts/evals/run-generator-unchanged-outcome-v5.py analyze /absolute/external/scores.json --audit /absolute/external/audit.json --output /absolute/external/results.json
```

The execution cap is eight sequential calls, one per cell, no retries and a 4 GiB disk floor. Missing or unverifiable evidence stays incomplete. Original reports and transcripts remain external; causal browser failure attribution still requires the separate bound audit.
