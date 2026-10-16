# Zeppelin OSS freeze readiness (offline preparation, 2026-10-15)

Status: NOT FROZEN, NOTHING EXECUTED. This file lists what was prepared offline against the independent review's blockers, what remains an owner or host action, and a smoke plan that has not been run. It changes no frozen file. No model call, container, server, port, network, calibration or freeze occurred; no heldout task content was opened (names and file counts only).

## 1. Calibration expectations for the two DEV tasks

The runner (`calibrate_references`, now using `validate_expectations`) needs `<pool>/tasks/<task>/calibration-expectations.json`: exactly keys `D1`..`D5`, each exactly `failing_test_title` (reporter title chain joined by ` > `) and a nonempty compilable `reason_regex`. The file is grader-only and enters the DEV tree digest, so it must exist before freeze.

Offline candidates, derived only from each task's `defects.md` and `reference.spec.ts` (defect-to-test mapping from the "reference result on mutant" column, reason regexes from the matcher and locator the mutant breaks):

- [zep-sidebar candidate](calibration-candidates/zep-sidebar.calibration-expectations.json)
- [zep-note-rename candidate](calibration-candidates/zep-note-rename.calibration-expectations.json)
- [provenance and pending values](calibration-candidates/PROVENANCE.json) (source digests; the runner schema forbids metadata inside the candidate files)

Status of every value: CANDIDATE, UNVERIFIED. Pending a live run: (a) the file-suite prefix `reference.spec.ts > ` (depends on the scoring testDir); (b) all ten `reason_regex` values, because real mutant error text was never observed (rename D3 is an alternation as the first failing assertion is unknown); (c) that each chosen test really fails on its mutant under the OSS scoring path. A failed `calibrate` writes the observed `failing_test_titles` into `_scorer-calibration.json`, which is the owner's correction input. The owner reviews and copies the files into the DEV-only pool before freeze; a PASS calibration is the only acceptance.

## 2. Guard mismatch: thin-eval CLI guide versus OSS

`benchmarks/generator-thin-eval-v1/CLI-GUIDE.md` assumes (i) the model starts its own app on a free port P, (ii) a CLI config `network.allowedOrigins = [http://127.0.0.1:P]`, (iii) a blocked-origin probe to `127.0.0.1:9` proving the guard. OSS differs on every point:

| Item | thin-eval CLI guide | OSS A/B/C today |
|---|---|---|
| App | model-started, own port, fresh process | one external proxy, `generation_proxy` 127.0.0.1:14210, started by the harness under the machine-global lock, shared for the whole generation call |
| Origin the browser must reach | `http://127.0.0.1:P` | `http://host.docker.internal:14210` from the container (host scoring rewrites it to 127.0.0.1:14210) |
| Network guard | CLI origin allowlist only | official MCP server; container keeps outbound internet (disclosed contamination limit) |
| State | synthetic apps | stateful Zeppelin notes; namespace, note-creation and cleanup rules apply to every note the model touches |

Consequences: the guide cannot be copied. A model-started app on port P would bypass the proxy, the namespace and the single-instance lock, and the allowlist must name `http://host.docker.internal:14210`, not `127.0.0.1:P`. Port 14210 is occupied for the call, so "free port" is wrong; steps 1 and 6 (start/stop app) must be deleted, and the step-4 probe must target a blocked origin that is reachable in the container's network (not `127.0.0.1:9`) and be re-proved live.

Decision: no runner or protocol change was made. Arms A/B/C are unchanged and have no CLI arm, so there is nothing to align in this campaign, and `ZEPPELIN-AMENDMENT-SPEC.md` requires D/E/F to be a new versioned successor with its own freeze, not an append. Successor requirements (precise): (1) re-derive a task-neutral guide of at most 1,000 bytes with step 1 replaced by "the app is already running at `http://host.docker.internal:14210`; do not start another" and the allowlist `{"network":{"allowedOrigins":["http://host.docker.internal:14210"]}}`; (2) the blocked-origin probe must fail with `net::ERR_BLOCKED_BY_CLIENT` inside the container before any model-visible exploration, otherwise the F/G cell is excluded, not retried; (3) the proxy keeps serving the shared namespace and cleanup unchanged; (4) container outbound internet must be separately constrained or disclosed, since in F the allowlist is the only guard; (5) handle `.playwright-cli/` like `.playwright-mcp/`; (6) prove (1)-(5) in a successor live smoke before its freeze.

## 3. Heldout names and ERRATA leak paths

Exposure (names and counts only; contents unopened). In the pool `benchmarks/generator-oss-pool-v1`: `tasks/zep-about-modal` and `tasks/zep-home-links` each hold one file (scope.md per ERRATA); `sealed-eval/` holds 2 task directories (18 files in total); ERRATA leak paths: `harness/author-patches.py`, `harness/defect-meta.json`, `results/mutant-results.md`, `results/mutant-results.txt`, the README "Verified" section, the external `zeppelin-mut` logs, and merged upstream eval specs beside the Zeppelin checkout. `split.json` names a nonexistent sealed directory. The runner itself only reads explicit DEV names, but any worker or loop given the pool root can read all of the above, and the registered final tasks are already disclosed as an exposed design in the README.

Isolation fix, applied in two parts:

1. Offline code change (done): `assert_dev_only_pool` runs inside `bindings()` (so `freeze`, `calibrate`, `smoke`, live admission and every frozen check) and in `runtime()` for the DEV pool. It refuses a `--pool` root containing `tasks/zep-about-modal`, `tasks/zep-home-links`, `sealed-eval` or any ERRATA leak file, using existence checks only. Final evaluation passes the external vault explicitly and is unaffected. A DEV-only export yields identical task digests, because bindings hash only the two DEV task directories.
2. Owner/host action (not done): create a DEV-only export, e.g. `~/.../oss-dev-pool` containing only `tasks/zep-sidebar` and `tasks/zep-note-rename` (plus the reviewed calibration files), copy by explicit names, not recursive pool copy. Move `tasks/zep-about-modal`, `tasks/zep-home-links` and `sealed-eval/` into the 0700 external vault; move or delete the four harness/results leak files from every path an improvement worker can read; the README Verified section and external `zeppelin-mut` logs and upstream eval specs must be moved or access-restricted; do not use the old pool root as `--pool`. Historical exposure is not undone, so no sealed claim is made.

## 4. Smoke plan (not executed)

Preconditions (owner/host): DEV-only pool export exists and calibration files copied (sections 1 and 3); no other benchmark driver running; Docker context and Zeppelin upstream at 127.0.0.1:18080 up; HOME-resident output; `$LOOP_RUNNER` is the owner-supplied generator-loop-v1 runner (its repository root is two directories above `scripts/evals`).

```bash
cd <this worktree>
# 0. offline gates (safe now)
python3 scripts/ci/test-generator-oss-eval-v1.py          # expect: Ran 83 tests ... OK
python3 scripts/evals/run-generator-oss-eval-v1.py plan   # expect: "paid_calls_started": 0, "status": "NOT_RUN"
# 1. refusal check of the guard, expected to FAIL on the old pool root (exit 2, message contains "not isolated")
python3 scripts/evals/run-generator-oss-eval-v1.py calibrate --allow-live --pool <OLD_POOL> \
  --loop-runner "$LOOP_RUNNER" --dists "$DISTS" --source "$SOURCE" --output "$HOME/oss-smoke/refuse"
# 2. non-model plumbing and reference calibration (live, no model)
python3 scripts/evals/run-generator-oss-eval-v1.py calibrate --allow-live --pool <DEV_ONLY_POOL> \
  --loop-runner "$LOOP_RUNNER" --dists "$DISTS" --source "$SOURCE" --output "$HOME/oss-calibration-v1"
# 3. only after step 2 prints PASS: fresh-root smoke with one admitted model (3 uncounted cells A, C, B)
python3 scripts/evals/run-generator-oss-eval-v1.py smoke --allow-live --pool <DEV_ONLY_POOL> \
  --loop-runner "$LOOP_RUNNER" --dists "$DISTS" --source "$SOURCE" --model <model-id> \
  --output "$HOME/oss-smoke/run-1"
```

Expected outputs. Step 1: exit 2 with `DEV pool root is not isolated` on stderr, raised before the output directory, lock or any subprocess exists (offline-tested). Step 2: stdout `{"command": "calibrate", "status": "PASS", "no_freeze_required": true}`, exit 0, and `_scorer-calibration.json` with `status: PASS`, `model_calls: 0`, per task clean 3/3, `refactor_pass`, and each D1..D5 `failed >= 1`, no errors, expected title in `failing_test_titles`, `calibration_reason_matched: true`. Step 3: the same JSON line with `"command": "smoke"`, `NON_DATA_SMOKE.json`, `<model>/non-data-cells.json` with `not_campaign_data: true` and three runs, and per-cell `-smoke-score.json`. Also verify live, per the README: init-agents ready, container reaches `host.docker.internal:14210`, namespace note create then delete with re-list proof, trash cleanup, SIGTERM cleanup, interrupted-score resume, and the A argv/config gate.

Stop conditions (stop, record, do not retry with changed identity): any occupied port 14210 or foreign lock holder; guard refusal from step 1 on the DEV-only pool; `calibrate` status FAIL or any `reason_regex`/title mismatch (correct candidates from observed titles and reasons only after owner review, then rerun a fresh calibration); `preexisting_note_removed`/`preexisting_note_path_changed`/`new_note_outside_namespace` violations; cleanup failure; infrastructure error in any smoke cell; output not under HOME; any mutation of freeze-bound files; spend of weekly limit above the owner's threshold. A passing smoke does not authorize freeze or campaign.

## 5. Owner decisions and host/live actions still open

- Review and install the calibration files; run live calibration to PASS (section 1).
- Create the DEV-only pool export and relocate heldout/leak paths; decide whether the exposed final tasks remain descriptive-only or are replaced by genuinely unexposed tasks (section 3).
- Approve D/E/F as a new versioned OSS successor with the section 2 guard requirements; its guide, probe and containment need their own live smoke and freeze.
- Run the smoke (section 4), then independent exposure review, freeze authorization and campaign authorization.
