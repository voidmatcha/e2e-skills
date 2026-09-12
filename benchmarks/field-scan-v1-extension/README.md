# field-scan-v1 completion extension

**Result: the field-scan-v1 sample is now measured at its designed size.** `benchmarks/field-scan-v1/README.md`'s own selection rule sets the sample at 12 repositories ("Take the first 12 surviving repositories"), and its own results section self-declares against that design: **"Incomplete: 10/12 repositories completed with no suppressed rules."** Two rows — `ever-co/ever-gauzy` and `open-mercato/open-mercato` — recorded `status: "timeout"` under the protocol's 1800-second per-repository budget and never produced a measurement. This extension scans exactly those two repositories to a natural, fully reconciled scanner exit:

| repository | exit | duration_s | total hits | P0 | P0 candidate (triage) | suppressed rules | source fingerprint |
| --- | --- | --- | --- | --- | --- | --- | --- |
| `ever-co/ever-gauzy@54b537baf8` | 0 | 6720.5 | 1967 | 0 | 732 | 0 | unchanged |
| `open-mercato/open-mercato@8b492325d3` | 0 | 9025.7 | 3779 | 0 | 1090 | 0 | unchanged |

Both rows are `status: "scanned"` with `unexplained_delta: 0` and `incomplete: []` — the strict completion bar defined below, the same bar the v1 ledger applies. Combined with v1's 10 complete rows, all 12 originally designed repositories now have a completed measurement, split across two disclosed protocols (v1's frozen 30-minute/default-limit protocol for 10, this extension's no-cutoff/hard-ceiling protocol for 2) rather than merged into one. `benchmarks/field-scan-v1/ledger.json` itself was never modified.

## What this is and is not

This is a completion of the two v1 rows that recorded `status: "timeout"`, run under a separate, explicitly different protocol (below). It is **not** a rerun of the v1 pool and it never rewrites the frozen v1 ledger. The v1 record stays exactly as evaluated: 10 complete, 2 timeout, 0 confirmed P0 among complete scans, 0 model calls. This directory holds its own linked ledger (`ledger.json`, `extension_of: benchmarks/field-scan-v1/ledger.json`).

The result is scanner-determinism evidence: the bundled scanner reaches a full, reconciled exit on both repositories given enough time and headroom. It is not reviewer-accuracy evidence and does not change `release_eligible` by itself (see `benchmarks/reviewer-holdout-v3/evidence-status.json`).

## Protocol

Two things differ from v1; everything else is the same scanner on the same pinned commits.

1. **No wall-clock cutoff.** Duration is recorded as evidence, never used to abort a healthy run. Liveness, not a timer, distinguishes ongoing work from deadlock (see "Liveness detector" below).
2. **Bounded rule limits raised to their documented hard ceilings.** `scan.sh` bounds per-rule output (`E2E_SMELL_MAX_RULE_HITS`, default 1000, hard ceiling 10000 at `scan.sh:300`; `E2E_SMELL_MAX_RULE_BYTES`, default 1 MiB, hard ceiling 16 MiB at `scan.sh:302`). A rule that hits a bound is *suppressed*: named in the Summary, forces exit 2, and makes the run non-authoritative by the scanner's own contract. The final `open-mercato` row was produced with both limits at their ceilings so that no rule is suppressed. Raising a bound can only widen coverage; it cannot lower a hit count.

Unchanged from v1:

- Scanner-only, `model_calls: 0`. Current v1.16.0 `skills/e2e-reviewer/scripts/scan.sh`; its sha256 is recorded as `scanner_digest_sha256`.
- Each target is a disposable blobless partial clone (`--depth 1 --filter=blob:none`) pinned to the exact SHA, deleted after the scan regardless of outcome. No mutation of the target repositories.
- Serial execution (`run_extension.py`), one repository to completion before the next.
- Completion bar, per row: `exit_code` 0 or 1; exactly one parsed `Summary:` line; zero `INCOMPLETE:` rule lines; `scanner_counts.total == listed_hits + scanner_counts.ast` (`unexplained_delta == 0`); `source_fingerprint_pre_sha256 == source_fingerprint_post_sha256` (sha256 of `git ls-tree -r HEAD`, proves the checkout was not mutated); `stdout_sha256` / `stderr_sha256` recorded for independent replay. A row meeting all of these is `scanned`. Anything else is `incomplete-evidence` with a `reasons` list, never coerced into a zero-findings result; fetch or scan exceptions are `fetch-failed` / `execution-failed`, never dropped.
- Crash-safe ledger (partial write + atomic rename after every row).

### Liveness detector

A background sampler polls the scanner every 120s and appends a record to `liveness.log`. A run is stopped only for a demonstrated crash or deadlock, resource exhaustion, or external interruption — never for elapsed time.

The detector was strengthened once during execution, after attempt 2 (see "Protocol amendments" below). Its current form sums CPU time and stdout/stderr byte growth across the *entire* scanner process tree (not just the top PID — `scan.sh` runs a helper, `scope-source.sh`, as its own process group, invisible to top-PID-only sampling) every sample; `DEADLOCK_SAMPLES` (6, i.e. 12 minutes) of consecutive samples where neither signal *increases* by more than a small threshold terminates the tree as `status: "deadlock-detected"` with the samples as evidence. Because it compares against the previous sample rather than tracking a running maximum, a short-lived child process exiting between samples can make the summed CPU total read lower than before and count as one non-increasing sample (`liveness.log` has two such single-sample dips during attempts 3-5, neither adjacent to another, so `DEADLOCK_SAMPLES` was never reached); it never actually tripped in any attempt that ran under it.

## Execution history

`ever-gauzy` completed on its first attempt. `open-mercato` took five attempts to reach the completion bar. None of the four earlier attempts indicate a defect in this extension's own code: two hit the scanner's own documented bounded-limit safety valves (working as designed, at whatever limit was configured for that attempt — default for attempt 1, already-raised `HITS` for attempt 3), one was stopped on an operator judgment call that did not reproduce on retry (detail below), and one was killed by the OS for system-wide memory pressure from unrelated processes. Each completed retry also reported *more* hits than the one before it (1901 → 3527 → 3779), consistent with raising a bound rather than picking a favorable run: a wider limit can only add candidates, never remove them. Every attempt started from a fresh clone of the same pinned SHA; the runner keeps only `scanned` rows in `ledger.json`, so `run.log` and `liveness.log` are the record of the four earlier attempts.

| # | repository | config | how it ended |
| --- | --- | --- | --- |
| 1 | ever-gauzy | defaults | `scanned`, exit 0, 6720.5s, 1967 hits, 0 P0 |
| 1 | open-mercato | defaults | `incomplete-evidence`, exit 2, 5181.1s, 1901 hits, `run.log` records `incomplete_rules=13` (12 named rules hit `E2E_SMELL_MAX_RULE_HITS` (1000) plus 1 summary line; rule names seen live, not preserved in `ledger.json`) |
| 2 | open-mercato | `HITS=10000` | stopped by the operator after ~1h30m (see note below) |
| 3 | open-mercato | `HITS=10000` | `incomplete-evidence`, exit 2, 7103.6s, 3527 hits, `run.log` records `incomplete_rules=7` (6 named rules — `#4f` x5, `#5a`, seen live, not preserved — hit `E2E_SMELL_MAX_RULE_BYTES` (1 MiB) plus 1 summary line) |
| 4 | open-mercato | `HITS=10000`, `BYTES=16777216` | ended after ~30min with no exit line in `run.log` (the process stopped writing, consistent with an OS memory-pressure kill observed live at the time; not independently provable from the committed record alone — the same caveat as attempt 2); unrelated processes were the apparent dominant memory consumer; retried once memory recovered |
| 5 | open-mercato | `HITS=10000`, `BYTES=16777216` | `scanned`, exit 0, 9025.7s, 3779 hits, 0 suppressed rules, 0 P0 |

**Note on attempt 2.** The sampler in use at the time only recorded the top-level `/bin/bash` PID (`liveness.log` entries for this attempt, pid 2587, first sample's ELAPSED implies a 09:16:59Z start, last sample 10:47:05Z — about 1h30m), which read 0-2% CPU throughout — that reading is not by itself diagnostic, since the successful `ever-gauzy` run shows the identical top-PID profile in its own `liveness.log` entries (a bash parent waiting on a busy child looks the same either way). The operator's decision to stop the run was based on additional live inspection at the time that is not captured in any committed file: checking the scanner's actual worker processes (`scope-worker.py serve` and its `scope-source.sh` helper, each its own process group) directly, where repeated `ps` samples taken seconds apart showed their cumulative CPU time frozen for over an hour, together with no new IPC files and a system-wide idle check (~74% CPU idle at inspection time). Attempt 3 on identical inputs completed with no stall under the tree-wide detector, and no later attempt tripped it, so the stall did not reproduce; the machine was also running unrelated `scan.sh` processes from other sessions around the time of attempt 2, so contention is the most likely explanation, but this cannot be established conclusively from the committed record alone.

### Protocol amendments during execution

Two changes were made after attempts 1-2 and before attempt 3:

- The liveness sampler was changed from top-PID-only polling to the tree-wide CPU/output tracking described above (visible in `liveness.log` as the change in record shape between pid 2587 and pid 5020). It only affects whether a run is stopped, not what it reports.
- `E2E_SMELL_MAX_RULE_HITS`, and later `E2E_SMELL_MAX_RULE_BYTES`, were raised to their documented hard ceilings because the scanner's default bounds suppressed rules on `open-mercato`. Raising a bound is monotone: it can only add hits, never remove them.

## Reading the result

`status: "scanned"` with `exit_code: 1` and P0 hits would be a real finding, not noise. "0 P0" here means the scanner's confirmed-P0 gate reported zero on both repositories; the P0-candidate and LLM-triage counts in the ledger are candidates that need the same triage the v1 evidence-status document applies, not defect counts and not an accuracy score.

## Scope boundaries carried over from the handoff

- No push, tag, or GitHub Release. No mutation of, or state change on, `ever-co/ever-gauzy` or `open-mercato/open-mercato` (read-only clone, scan, delete).
- This extension's outcome does not change `release_eligible` status by itself; it is scanner-determinism evidence, not reviewer-accuracy evidence (see `benchmarks/reviewer-holdout-v3/evidence-status.json`).
