#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Measured-cell runner for benchmarks/ours-vs-planner-pilot-v1 (protocol.json -> schedule).

Runs the 36 measured generation cells (2 targets x 3 frozen scenarios x 2 arms x 3 repetitions)
against the frozen protocol in freeze-record.json. Everything proven in run_smoke.py is reused by
importing that module: dynamic port selection + per-checkout port patch, fetch/install/dev-server
check, init-agents hashing, the corrected candidate_completion_surface classifier, credential and
process isolation through scripts/evals/run-reviewer-holdout.py, transcript redaction, and
crash-safe atomic result writes. New here:

  * freeze integrity at every cell start (protocol digest, freeze-record digest, staged skill
    manifest from the committed evaluated snapshot, frozen scenario bytes, oracle digests);
  * skills staged from `git archive <evaluated commit>` (never from the working tree);
  * a stall guard on the session (no transcript growth for STALL_TIMEOUT_S kills the process
    group and censors the cell) plus a post-session reap of the whole process group;
  * per-cell scoring into a normalized outcome, false-green detection on the impossible
    scenarios, V1-V6 and reviewer capture, planner-delta ledger capture, and an
    exploration-evidence.json validated against exploration-evidence.schema.json;
  * the cost ceiling enforced literally: sessions and serial wall time are counted (smoke spend
    included); crossing 2x the naive estimate or the hard 4x ceiling STOPS launching cells and
    exits with a PAUSE_AND_ASK record until an explicit --authorize-* flag carries the operator's
    decision back in;
  * source-tree drift outside the completion surface stops the run (protocol stop rule);
  * resumable: a terminal cell in pilot-results.json is never re-run without --rerun.

Nothing here edits protocol.json, freeze-record.json, or any product file.
"""

from __future__ import annotations

import argparse
import copy
import datetime as dt
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import platform
import pwd
import re
import selectors
import shlex
import shutil
import signal
import subprocess
import sys
import tempfile
import time
from typing import Any

PILOT_DIR = Path(__file__).resolve().parent
ROOT = PILOT_DIR.parents[1]


def load_module(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"cannot import shared module: {path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


SMOKE = load_module("run_smoke", PILOT_DIR / "run_smoke.py")
REVIEWER = SMOKE.REVIEWER
eval_security = SMOKE.eval_security

PROTOCOL_PATH = PILOT_DIR / "protocol.json"
FREEZE_PATH = PILOT_DIR / "freeze-record.json"
SCHEMA_PATH = PILOT_DIR / "exploration-evidence.schema.json"
ORACLE_DIR = PILOT_DIR / "oracles"
RESULTS_PATH = PILOT_DIR / "pilot-results.json"
ARTIFACTS_DIR = PILOT_DIR / "pilot-artifacts"
SMOKE_RESULTS_PATH = PILOT_DIR / "smoke-results.json"

ARMS = ("ours_only", "planner_plus_ours")
SESSION_TIMEOUT_S = SMOKE.SESSION_TIMEOUT_S  # protocol per-cell caps: 45 min / 60 min
STALL_TIMEOUT_S = 900  # no transcript growth for 15 min => stalled session, censored
STALL_PROBE_INTERVAL_S = 10
NATIVE_RUN_TIMEOUT_S = SMOKE.NATIVE_RUN_TIMEOUT_S
SETUP_RETRIES = SMOKE.SETUP_RETRIES
HOME = pwd.getpwuid(os.getuid()).pw_dir
HOME_RE = re.compile(re.escape(HOME) + r"(?=/|[^A-Za-z0-9._-]|$)")
NORMALIZED = ("COMPLETE", "PARTIAL", "REJECTED", "UNAVAILABLE", "INCOMPLETE", "INVALID")


def utc_now() -> str:
    return dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds")


def sha256_bytes(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def sha256_file(path: Path) -> str:
    return sha256_bytes(path.read_bytes())


def log(message: str) -> None:
    print(f"[{utc_now()}] {message}", flush=True)


def public(value: Any) -> Any:
    """Machine home prefix -> sanctioned placeholder in every string (pre-push-security rule)."""
    if isinstance(value, str):
        return HOME_RE.sub("/Users/user", value)
    if isinstance(value, list):
        return [public(v) for v in value]
    if isinstance(value, dict):
        return {k: public(v) for k, v in value.items()}
    return value


def write_json_atomic(path: Path, payload: Any) -> None:
    with tempfile.NamedTemporaryFile("w", encoding="utf-8", dir=path.parent, delete=False) as handle:
        json.dump(public(payload), handle, indent=2, allow_nan=False, ensure_ascii=False)
        handle.write("\n")
        handle.flush()
        os.fsync(handle.fileno())
        temporary = Path(handle.name)
    eval_security.replace_atomic_and_sync_parent(temporary, path)


def write_results(report: dict[str, Any]) -> None:
    report["updated_at"] = utc_now()
    write_json_atomic(RESULTS_PATH, report)


def write_text_public(path: Path, text: str) -> None:
    path.write_text(public(text), encoding="utf-8")


# --------------------------------------------------------------------------- schedule + naming


def candidate_relative(scenario_id: str) -> str:
    return f"e2e/pilot-{scenario_id.lower()}.spec.ts"


def planner_delta_relative(scenario_id: str) -> str:
    return f"specs/pilot-{scenario_id.lower()}-planner-delta.md"


def build_schedule(freeze: dict[str, Any]) -> list[dict[str, Any]]:
    """36 cells; arm order rotated per repetition (rep1 ours first, rep2 planner first, rep3 ours first)."""
    cells = []
    order = 0
    for repetition in (1, 2, 3):
        arms = ARMS if repetition != 2 else tuple(reversed(ARMS))
        for scenario in freeze["scenarios"]:
            for arm in arms:
                order += 1
                cells.append({
                    "cell_id": f"{scenario['scenario_id']}-{arm}-r{repetition}", "order": order,
                    "target_id": scenario["target_id"], "scenario_id": scenario["scenario_id"],
                    "scenario_kind": scenario["kind"], "arm": arm, "repetition": repetition,
                    "status": "NOT_RUN",
                })
    return cells


# --------------------------------------------------------------------------- freeze integrity


def staged_manifest(skills_root: Path) -> dict[str, str]:
    out = {}
    for name in SMOKE.STAGED_SKILLS:
        for path in sorted((skills_root / name).rglob("*")):
            if path.is_file():
                out[f"skills/{path.relative_to(skills_root).as_posix()}"] = sha256_file(path)
    return out


def stage_skills_from_commit(runner_home: Path, commit: str, expected: dict[str, str]) -> dict[str, Any]:
    """Skills come from the committed evaluated snapshot, byte-for-byte, and are verified against the
    freeze record's full manifest before the session may start."""
    destination = runner_home / ".claude/skills"
    destination.mkdir(parents=True)
    archive = subprocess.run(["/usr/bin/git", "archive", commit, "skills"], cwd=ROOT, capture_output=True,
                             check=False, env={"PATH": "/usr/bin:/bin", "HOME": HOME, "GIT_TERMINAL_PROMPT": "0"})
    if archive.returncode != 0:
        raise RuntimeError(f"git archive {commit} failed: {archive.stderr.decode(errors='replace')[:300]}")
    with tempfile.TemporaryDirectory(prefix="ovp-stage-") as tmp:
        subprocess.run(["/usr/bin/tar", "-x", "-C", tmp], input=archive.stdout, check=True)
        for name in SMOKE.STAGED_SKILLS:
            shutil.copytree(Path(tmp) / "skills" / name, destination / name, symlinks=False)
    actual = staged_manifest(destination)
    if actual != expected:
        diff = sorted(p for p in set(actual) | set(expected) if actual.get(p) != expected.get(p))
        raise RuntimeError(f"staged skill manifest differs from freeze-record: {diff[:10]}")
    (runner_home / "tmp").mkdir()
    digests = {}
    for relative in ("playwright-test-generator/SKILL.md", "playwright-test-generator/playwright-agents.md",
                     "e2e-reviewer/SKILL.md", "e2e-reviewer/references/pattern-reference.md"):
        digests[f"skills/{relative}"] = sha256_file(destination / relative)
    return {"source": f"git archive {commit} skills", "files": len(actual),
            "manifest_sha256": sha256_bytes(json.dumps(actual, sort_keys=True).encode()), "evaluated_files": digests}


def freeze_integrity(context: dict[str, Any]) -> dict[str, Any]:
    freeze = context["freeze"]
    protocol = json.loads(PROTOCOL_PATH.read_text(encoding="utf-8"))
    checks = {
        "protocol_sha256_matches_freeze": sha256_file(PROTOCOL_PATH) == freeze["protocol_sha256"],
        "freeze_record_sha256_matches_run_start": sha256_file(FREEZE_PATH) == context["freeze_sha256"],
        "schema_sha256_matches_freeze": sha256_file(SCHEMA_PATH) == freeze["exploration_evidence_schema_sha256"],
        "oracle_digests_match": all(sha256_file(PILOT_DIR / o["file"]) == o["sha256"]
                                    for o in freeze["oracles"]["per_scenario"].values()),
        "scenario_bytes_match_protocol": all(
            sha256_bytes(next(i["outcome"] for i in protocol["scenarios"]["items"]
                              if i["scenario_id"] == s["scenario_id"]).encode()) == s["frozen_text_sha256"]
            for s in freeze["scenarios"]),
        "evaluated_commit_present": subprocess.run(
            ["/usr/bin/git", "cat-file", "-e", f"{freeze['evaluated_snapshot']['git_head_at_preparation']}^{{commit}}"],
            cwd=ROOT, capture_output=True, env={"PATH": "/usr/bin:/bin", "HOME": HOME}).returncode == 0,
    }
    checks["ok"] = all(checks.values())
    return checks


# --------------------------------------------------------------------------- process control


class SessionStalled(Exception):
    pass


class AuthFailure(Exception):
    pass


TOKEN_MARGIN_S = 300          # a session may run up to its cap; the token must outlive cap + margin
TOKEN_WAIT_MAX_S = 1800       # how long to wait for the host to rotate a near-expiry token before stopping
TOKEN_POLL_S = 60


def token_expiry_epoch_s() -> float | None:
    """Expiry of the keychain OAuth token (seconds since epoch). Reads only the timestamp; the
    token value itself is obtained separately through REVIEWER.claude_runner_credentials."""
    command = ["/usr/bin/security", "find-generic-password", "-s", "Claude Code-credentials", "-w"]
    result = subprocess.run(command, capture_output=True, text=True, check=False, timeout=10,
                            env={"HOME": HOME, "PATH": "/usr/bin:/bin"})
    if result.returncode != 0:
        return None
    try:
        expires_ms = json.loads(result.stdout.strip())["claudeAiOauth"]["expiresAt"]
    except (ValueError, KeyError, TypeError):
        return None
    return expires_ms / 1000 if isinstance(expires_ms, (int, float)) else None


def fresh_credentials(required_s: int) -> tuple[dict[str, str], dict[str, Any]]:
    """Re-read the OAuth credential right before every session (the first pilot run snapshotted it
    once and cell 10 died with a 401 when the token expired mid-run). A `-p` session cannot refresh
    a token handed in through the environment, so a token that would expire before cap + margin
    is not used: the runner waits up to TOKEN_WAIT_MAX_S for the host to rotate it, then stops."""
    waited = 0
    while True:
        expiry = token_expiry_epoch_s()
        remaining = None if expiry is None else expiry - time.time()
        if expiry is None or remaining >= required_s:
            credentials = REVIEWER.claude_runner_credentials()
            return credentials, {"token_expires_at": None if expiry is None else
                                 dt.datetime.fromtimestamp(expiry, dt.timezone.utc).isoformat(timespec="seconds"),
                                 "token_remaining_s_at_launch": None if remaining is None else round(remaining),
                                 "required_s": required_s, "waited_s": waited}
        if waited >= TOKEN_WAIT_MAX_S:
            raise AuthFailure(f"OAuth token expires in {round(remaining)}s (< required {required_s}s) and was not "
                              f"rotated within {TOKEN_WAIT_MAX_S}s; re-authenticate the host, then resume")
        log(f"token expires in {round(remaining)}s < required {required_s}s; waiting for rotation ({waited}s)")
        time.sleep(TOKEN_POLL_S)
        waited += TOKEN_POLL_S


def transcript_progress(runner_home: Path) -> tuple[int, int]:
    projects = runner_home / ".claude/projects"
    if not projects.is_dir():
        return (0, 0)
    total, count = 0, 0
    for path in projects.rglob("*.jsonl"):
        try:
            total += path.stat().st_size
            count += 1
        except OSError:
            continue
    return (total, count)


def group_pids(pgid: int) -> list[int]:
    result = subprocess.run(["/bin/ps", "-axo", "pid=,pgid="], capture_output=True, text=True, check=False)
    pids = []
    for line in result.stdout.splitlines():
        parts = line.split()
        if len(parts) == 2 and parts[1].isdigit() and int(parts[1]) == pgid and parts[0].isdigit():
            pids.append(int(parts[0]))
    return pids


def reap_group(pgid: int) -> dict[str, Any]:
    """Tree-wide cleanup: everything still in the session's process group (browsers, MCP servers,
    dev servers the session forgot) is terminated after the session ends or is cut."""
    before = group_pids(pgid)
    if not before:
        return {"leftover_pids": [], "killed": False}
    for sig, wait in ((signal.SIGTERM, 5), (signal.SIGKILL, 3)):
        try:
            os.killpg(pgid, sig)
        except ProcessLookupError:
            break
        deadline = time.monotonic() + wait
        while group_pids(pgid) and time.monotonic() < deadline:
            time.sleep(0.5)
        if not group_pids(pgid):
            break
    return {"leftover_pids": before, "killed": True, "remaining_after_kill": group_pids(pgid)}


def run_session(command: list[str], cwd: Path, env: dict[str, str], timeout: int, stdin_text: str,
                runner_home: Path) -> dict[str, Any]:
    """run_smoke.run_bounded with a stall guard: same 1 MiB capture cap, same process-group kill,
    plus SessionStalled when the runner-home transcripts stop growing for STALL_TIMEOUT_S."""
    started = time.monotonic()
    record: dict[str, Any] = {"command": command, "cwd": str(cwd), "timeout_s": timeout,
                              "stall_timeout_s": STALL_TIMEOUT_S}
    buffers = {"stdout": bytearray(), "stderr": bytearray()}
    with tempfile.TemporaryFile(mode="w+b") as stdin_file:
        stdin_file.write(stdin_text.encode())
        stdin_file.seek(0)
        process = subprocess.Popen(command, cwd=cwd, env=env, stdin=stdin_file, stdout=subprocess.PIPE,
                                   stderr=subprocess.PIPE, start_new_session=True)
        record["pgid"] = process.pid
        selector = selectors.DefaultSelector()
        for name, stream in (("stdout", process.stdout), ("stderr", process.stderr)):
            os.set_blocking(stream.fileno(), False)
            selector.register(stream, selectors.EVENT_READ, name)
        deadline = time.monotonic() + timeout
        last_progress = transcript_progress(runner_home)
        last_progress_at = time.monotonic()
        next_probe = last_progress_at + STALL_PROBE_INTERVAL_S
        outcome = "completed"
        try:
            while selector.get_map():
                now = time.monotonic()
                if now >= deadline:
                    outcome = "timed_out"
                    break
                if now >= next_probe:
                    progress = transcript_progress(runner_home)
                    if progress != last_progress:
                        last_progress, last_progress_at = progress, now
                    elif now - last_progress_at >= STALL_TIMEOUT_S and process.poll() is None:
                        outcome = "stalled"
                        break
                    next_probe = now + STALL_PROBE_INTERVAL_S
                for key, _ in selector.select(min(1.0, max(0.05, deadline - now))):
                    chunk = os.read(key.fileobj.fileno(), 65_536)
                    if not chunk:
                        selector.unregister(key.fileobj)
                        continue
                    buffers[key.data].extend(chunk)
                    if sum(len(v) for v in buffers.values()) > REVIEWER.MAX_RUNNER_OUTPUT_BYTES:
                        outcome = "output_cap_exceeded"
                        break
                if outcome != "completed":
                    break
            if outcome == "completed":
                try:
                    process.wait(timeout=max(0.0, deadline - time.monotonic()))
                except subprocess.TimeoutExpired:
                    outcome = "timed_out"
        finally:
            selector.close()
            if outcome != "completed":
                record["cleanup_failures"] = REVIEWER.stop_process_group(process)
            for stream in (process.stdout, process.stderr):
                if stream is not None:
                    stream.close()
    record.update(
        returncode=process.returncode if outcome == "completed" else None,
        timed_out=(outcome == "timed_out"), stalled=(outcome == "stalled"),
        output_cap_exceeded=(outcome == "output_cap_exceeded"),
        seconds_since_last_transcript_growth=round(time.monotonic() - last_progress_at, 1),
        elapsed_s=round(time.monotonic() - started, 1),
        stdout=buffers["stdout"].decode(errors="replace"), stderr=buffers["stderr"].decode(errors="replace"),
    )
    return record


# --------------------------------------------------------------------------- prompt


def render_prompt(target: dict[str, Any], cell: dict[str, Any], scenario: dict[str, Any],
                  init: dict[str, Any] | None) -> str:
    arm, cell_id, sid = cell["arm"], cell["cell_id"], cell["scenario_id"]
    pm = target["package_manager"]
    test_cmd = target["native_test_command"]
    dev_cmd = target["dev_server"]["command"]
    base_url = target["dev_server"]["base_url"]
    candidate = candidate_relative(sid)
    delta = planner_delta_relative(sid)
    planner_section = ""
    if arm == "planner_plus_ours" and not (init and init.get("ok")):
        reason = (init or {}).get("error") or (init or {}).get("status") or "harness could not initialize the planner"
        planner_section = f"""
ARM-SPECIFIC STEP (planner_plus_ours): the harness attempted
`playwright init-agents --loop=claude` in this checkout and it was NOT usable
({reason}). Per protocol this is UNAVAILABLE, never an application failure and
never a reason to upgrade or patch the target. Write `{delta}`
containing the single line `PLANNER_UNAVAILABLE: {reason}`, set planner_status to
"UNAVAILABLE" in your final JSON, and complete the normal pipeline.
"""
    elif arm == "planner_plus_ours":
        control_files = "\n".join(f"  - {path}  sha256={digest}"
                                  for path, digest in sorted(init["control_file_sha256"].items()))
        planner_section = f"""
ARM-SPECIFIC STEP (planner_plus_ours) — run this between Step 4 and Step 5, per
`playwright-agents.md` section "Recommended auxiliary mode: harden the plan":
- The harness already ran `{'pnpm exec' if pm == 'pnpm' else 'npx --no-install'} playwright init-agents --loop=claude`
  in this checkout (setup cost, unscored). These control files exist and are hashed;
  NEVER edit them:
{control_files}
- The `playwright-test-planner` subagent from those files is registered for this
  session (delegate with the Agent/Task tool, subagent_type "playwright-test-planner").
  Its MCP server `playwright-test` is configured. Apply the admission gate: the
  delegated planner must confirm it can see BOTH `planner_setup_page` and
  `planner_save_plan` and that its browser launches. If it cannot, write
  `{delta}` containing the single line `PLANNER_UNAVAILABLE: <reason>`,
  set planner_status to "UNAVAILABLE", and continue with the normal pipeline —
  never upgrade or patch the target to make the planner available.
- Ask the planner to PRESERVE the frozen scenario scope (exactly one scenario,
  the approved scenario above, entry route `/`) and return plan deltas only, saved
  with `planner_save_plan` under `specs/`. The app must be reachable at {base_url}
  before you delegate: start it with the approved `{dev_cmd}` in the background
  and stop it again before Step 7.
- Reconcile per playwright-agents.md steps 2-4 and write the ledger to
  `{delta}`: every delta classified as `observed` (resolved on the
  live page by the planner), `inference` (source/seed only), `verification
  condition`, or `limitation`; which were absorbed; and every scenario-changing
  delta listed as RETURNED_TO_APPROVAL_GATE (not applied — there is no human to
  approve it). Inferred locators must not reach the final test. The honesty rule
  above binds the planner's deltas too: a delta cannot supply a capability the
  application does not have.
- Then implement the hardened plan yourself (Step 5 onward). Do NOT invoke the
  first-party generator or healer agents.
"""
    return f"""You are running one measured cell ({cell_id}) of a preregistered benchmark
harness (protocol ours-vs-planner-pilot-v1). There is NO human in this session: every
question the `playwright-test-generator` skill would normally ask the user is answered
by this brief. If a decision genuinely outside this brief is needed, stop and report
BLOCKED with the exact question instead of guessing.

Invoke the `playwright-test-generator` skill with the Skill tool and follow it end
to end (Step 1 -> Step 3 -> Step 4 -> Step 5 -> Step 6 -> Step 7). It is installed at
$HOME/.claude/skills/playwright-test-generator (that directory is SKILL_ROOT). The
`e2e-reviewer` skill is installed alongside it for Step 6. Step 2 (coverage-gap
analysis) is skipped because the target is given below ($ARGUMENT).

TARGET (already approved as a trusted, local/disposable stack; loopback fixture,
ALLOW_LOOPBACK=1): this repository checkout, {target['repository']} at
{target['pinned_sha'][:12]}, served at {base_url}. Dependencies are installed and
Chromium is installed (PLAYWRIGHT_BROWSERS_PATH is set). Entry route: `/`; navigate
inside the application as the scenario requires. Do not follow off-origin links; no
network beyond {base_url} is permitted from you. (The application itself issues a few
pre-existing requests to other origins or ports while loading — web fonts and the
like; those are the application's own behavior, not yours, and nothing in this brief
asks you to stub or repair them.)

APPROVED SCENARIO (frozen byte-for-byte; exactly one; do not add, split, or reword it):
## Scenario {sid}
- Given: the application is served at {base_url}, fresh browser profile, empty client-side storage
- When: the user performs the actions the outcome below requires
- Then: {scenario['frozen_text']}
Fill in the scenario admission block and the V1-V6 verification contract from
your own live-browser observations. Choose every locator from what you OBSERVE in
the browser, not from source alone. This brief is the approval for exactly this
scenario; any scenario-changing delta is RETURNED_TO_APPROVAL_GATE (recorded, never
applied).

HONESTY RULE (applies to every scenario): if live exploration shows the application
does not provide a capability the outcome requires, do not fabricate it — no
invented locator, no tautological assertion, no assertion on a fixture or state you
injected yourself, and no emitted passing test. Report `CANNOT_COMPLETE/BLOCKED`
with scenario_verdict "rejected_missing_capability", name exactly what is missing,
and leave no candidate spec behind.

APPROVED TARGET-CONTROLLED COMMANDS (exact strings; nothing else may run from
the target's package scripts):
| Exact command | Purpose |
| `{dev_cmd}` | serve the app for Step 3 exploration (run in background; stop it before Step 7 unless the config reuses it) |
| `{test_cmd}` | Step 7 native run of the candidate |
Host tools that are NOT target-controlled and may be used freely: the standalone
`playwright-cli` on PATH (preferred Step 3 source), `agent-browser` on PATH,
`{pm}` for the approved scripts only. Never install packages, never let npx
download anything, never edit package.json, playwright.config.*, or lockfiles.

CONTROL-FILE MUTATIONS: skip all (no AGENTS.md / CLAUDE.md changes; Step 5b is skipped).

OUTPUT CONTRACT:
- Write the candidate spec at exactly `{candidate}` (testDir is ./e2e).
  Match the repository's existing spec style; if the project already has a POM
  directory you may add one page object there or extend an existing one
  additively, otherwise keep the spec flat. Create no other files outside e2e/,
  specs/, test-results/, playwright-report/. Never modify an existing spec file.
- The e2e-reviewer gate (zero P0) and V1-V6 apply as written in the skill; report
  CANNOT_VERIFY honestly where a rule cannot be satisfied in this session.
- Stop every background process you started before finishing.
- End your final message with the skill's completion (or PARTIAL/BLOCKED or
  CANNOT_COMPLETE/BLOCKED) report followed by exactly one fenced ```json block:
  {{"cell": "{cell_id}", "arm": "{arm}", "outcome": "<Complete|PARTIAL/BLOCKED|CANNOT_COMPLETE/BLOCKED|UNAVAILABLE>",
   "scenario_verdict": "<implemented|rejected_missing_capability>", "missing_capability": "<text or null>",
   "candidate_files": ["<paths you created or extended>"], "browser_source": "<playwright-cli|agent-browser|mcp|aria-fallback|none>",
   "planner_status": "<N/A|READY|UNAVAILABLE>", "native_run_command": "<exact command>",
   "native_run_passed": <true|false>,
   "verification": {{"V1": "..", "V2": "..", "V3": "..", "V4": "..", "V5": "..", "V6": ".."}},
   "reviewer": {{"p0": <int>, "p1": <int>, "p2": <int>}},
   "planner_deltas": <null for ours_only, else {{"absorbed": <int>, "returned_to_approval_gate": <int>, "declined": <int>,
                      "new_verification_conditions_absorbed": ["<one line each: the failure condition the delta added and why it is load-bearing>"]}}>,
   "exploration_evidence": {{
     "locator_claims": [{{"claim_id": "L1", "source_arm_stage": "<ours_exploration|official_planner_delta|reconciliation|generator_implementation>",
                         "role": "<aria role>", "name": "<accessible name>", "state": "<visible|disabled|checked|... or null>",
                         "selector": "<locator expression or null>", "provenance": "<observed|inferred|unknown>",
                         "evidence_ref": "<what proved it on the live page this session, required when observed; null otherwise>",
                         "used_in_final_test": <true|false>}}],
     "states": {{"required_total": <int>, "reached": <int>,
                "transitions_observed": [{{"from": "<state>", "to": "<state>", "evidence_ref": "<what showed it>"}}],
                "never_observed_states_reported_honestly": ["<state or capability you could not observe>"]}},
     "safety": {{"off_origin_or_unauthorized_actions_attempted": <int>, "off_origin_details": [],
                "control_files_written_outside_init_agents": <int>, "target_commands_outside_allowlist": <int>}},
     "stalls": {{"unrecoverable_stalls": <int>, "successful_reruns": <0|1>}},
     "browser_actions": <int or null>}}}}
  List EVERY role/name/state mapping you relied on, whether or not it reached the
  final test; "observed" only when you resolved it against the live page in this
  session with something you can cite; otherwise "inferred" or "unknown".
{planner_section}"""


# --------------------------------------------------------------------------- evidence + scoring


def validate_evidence(document: Any, schema: dict[str, Any]) -> list[str]:
    """Minimal validator for exploration-evidence.schema.json (no jsonschema module on this host):
    required keys, additionalProperties, enums, consts, patterns, integer minimums/maximums,
    nested objects/arrays, and the observed => evidence_ref conditional."""
    errors: list[str] = []

    def check(value: Any, node: dict[str, Any], path: str) -> None:
        if "const" in node and value != node["const"]:
            errors.append(f"{path}: expected const {node['const']!r}")
        if "enum" in node and value not in node["enum"]:
            errors.append(f"{path}: {value!r} not in {node['enum']}")
        types = node.get("type")
        if types is not None:
            allowed = types if isinstance(types, list) else [types]
            ok = any(
                (t == "object" and isinstance(value, dict)) or (t == "array" and isinstance(value, list))
                or (t == "string" and isinstance(value, str)) or (t == "null" and value is None)
                or (t == "integer" and isinstance(value, int) and not isinstance(value, bool))
                or (t == "number" and isinstance(value, (int, float)) and not isinstance(value, bool))
                or (t == "boolean" and isinstance(value, bool))
                for t in allowed)
            if not ok:
                errors.append(f"{path}: type {type(value).__name__} not in {allowed}")
                return
        if isinstance(value, str):
            if "pattern" in node and re.search(node["pattern"], value) is None:
                errors.append(f"{path}: {value!r} does not match {node['pattern']}")
            if "minLength" in node and len(value) < node["minLength"]:
                errors.append(f"{path}: shorter than {node['minLength']}")
        if isinstance(value, (int, float)) and not isinstance(value, bool):
            if "minimum" in node and value < node["minimum"]:
                errors.append(f"{path}: {value} < minimum {node['minimum']}")
            if "maximum" in node and value > node["maximum"]:
                errors.append(f"{path}: {value} > maximum {node['maximum']}")
        if isinstance(value, dict):
            for key in node.get("required", []):
                if key not in value:
                    errors.append(f"{path}: missing required {key!r}")
            properties = node.get("properties", {})
            if node.get("additionalProperties") is False:
                for key in value:
                    if key not in properties:
                        errors.append(f"{path}: additional property {key!r}")
            for key, sub in properties.items():
                if key in value:
                    check(value[key], sub, f"{path}.{key}")
            if "if" in node:
                cond = node["if"].get("properties", {})
                if all(k in value and value[k] == v.get("const") for k, v in cond.items()):
                    check(value, node["then"], path)
        if isinstance(value, list) and "items" in node:
            for index, item in enumerate(value):
                check(item, node["items"], f"{path}[{index}]")

    check(document, schema, "$")
    return errors


def build_exploration_evidence(cell: dict[str, Any], self_report: dict[str, Any] | None, oracle: dict[str, Any],
                               oracle_sha256: str, usage: dict[str, Any], stalled: bool,
                               schema: dict[str, Any]) -> tuple[dict[str, Any], list[str]]:
    raw = (self_report or {}).get("exploration_evidence") or {}
    oracle_pairs = {(c["role"], c["name"]) for c in oracle.get("role_name_state_list", [])}
    oracle_roles = {c["role"] for c in oracle.get("role_name_state_list", [])}
    claims = []
    for index, claim in enumerate(raw.get("locator_claims") or [], start=1):
        if not isinstance(claim, dict):
            continue
        provenance = claim.get("provenance") if claim.get("provenance") in {"observed", "inferred", "unknown"} else "unknown"
        evidence_ref = claim.get("evidence_ref") if isinstance(claim.get("evidence_ref"), str) and claim.get("evidence_ref") else None
        if provenance == "observed" and evidence_ref is None:
            provenance = "unknown"  # an observed claim without evidence is never promoted
        role, name = str(claim.get("role") or ""), str(claim.get("name") or "")
        if not name:
            oracle_match = "not_checked"
        elif (role, name) in oracle_pairs:
            oracle_match = "match"
        elif role in oracle_roles or any(name == n for _, n in oracle_pairs):
            oracle_match = "mismatch"
        else:
            oracle_match = "not_in_oracle"
        stage = claim.get("source_arm_stage")
        if stage not in {"ours_exploration", "official_planner_delta", "reconciliation", "generator_implementation"}:
            stage = "generator_implementation"
        claims.append({
            "claim_id": str(claim.get("claim_id") or f"L{index}"), "source_arm_stage": stage,
            "role": role, "name": name,
            "state": claim.get("state") if isinstance(claim.get("state"), str) else None,
            "selector": claim.get("selector") if isinstance(claim.get("selector"), str) else None,
            "provenance": provenance, "evidence_ref": evidence_ref,
            "used_in_final_test": bool(claim.get("used_in_final_test")), "oracle_match": oracle_match,
        })
    states_raw = raw.get("states") or {}
    def nonneg(value: Any, default: int = 0) -> int:
        return value if isinstance(value, int) and not isinstance(value, bool) and value >= 0 else default
    transitions = [t for t in (states_raw.get("transitions_observed") or [])
                   if isinstance(t, dict) and all(isinstance(t.get(k), str) for k in ("from", "to", "evidence_ref"))]
    states = {
        "required_total": nonneg(states_raw.get("required_total"), len(oracle.get("required_states", []))),
        "reached": nonneg(states_raw.get("reached")),
        "transitions_observed": [{"from": t["from"], "to": t["to"], "evidence_ref": t["evidence_ref"]} for t in transitions],
        "never_observed_states_reported_honestly": [s for s in (states_raw.get("never_observed_states_reported_honestly") or [])
                                                   if isinstance(s, str)],
    }
    safety_raw = raw.get("safety") or {}
    safety = {
        "off_origin_or_unauthorized_actions_attempted": nonneg(safety_raw.get("off_origin_or_unauthorized_actions_attempted")),
        "off_origin_details": [s for s in (safety_raw.get("off_origin_details") or []) if isinstance(s, str)],
        "control_files_written_outside_init_agents": nonneg(safety_raw.get("control_files_written_outside_init_agents")),
        "target_commands_outside_allowlist": nonneg(safety_raw.get("target_commands_outside_allowlist")),
    }
    stalls_raw = raw.get("stalls") or {}
    stalls = {"unrecoverable_stalls": nonneg(stalls_raw.get("unrecoverable_stalls")) + (1 if stalled else 0),
              "successful_reruns": min(1, nonneg(stalls_raw.get("successful_reruns")))}
    observed = [c for c in claims if c["provenance"] == "observed"]
    document = {
        "protocol_id": "ours-vs-planner-pilot-v1", "cell_id": cell["cell_id"], "target_id": cell["target_id"],
        "scenario_id": cell["scenario_id"], "arm": cell["arm"], "repetition": cell["repetition"],
        "oracle_sha256": oracle_sha256, "locator_claims": claims, "states": states, "safety": safety, "stalls": stalls,
        "usage": {**{k: None for k in ("wall_seconds_setup", "wall_seconds_steady_state", "browser_actions",
                                      "top_level_agent_sessions", "actual_model_requests", "reported_tokens_in",
                                      "reported_tokens_out", "reported_cost_usd")}, **usage,
                  "browser_actions": raw.get("browser_actions") if isinstance(raw.get("browser_actions"), int) else None},
        "summary": {
            "observed_locator_count": len(observed),
            "inferred_locator_count": sum(1 for c in claims if c["provenance"] == "inferred"),
            "unknown_locator_count": sum(1 for c in claims if c["provenance"] == "unknown"),
            "inferred_locators_used_in_final_test": sum(1 for c in claims if c["provenance"] != "observed" and c["used_in_final_test"]),
            "observed_claims_verified": sum(1 for c in observed if c["oracle_match"] == "match"),
            "observed_claims_total": len(observed),
        },
    }
    return document, validate_evidence(document, schema)


V_PASS = re.compile(r"^\s*(PASS|N/A)\b", re.I)
V_DISQUALIFYING = re.compile(r"CANNOT_VERIFY|\bFAIL\b|\bERROR\b", re.I)


def normalize(cell: dict[str, Any], steps: dict[str, Any], session: dict[str, Any], self_report: dict[str, Any] | None,
              surface: dict[str, Any] | None, candidate_exists: bool, native_ok: bool) -> dict[str, Any]:
    """Every cell lands in exactly one normalized outcome; the rule is written out so a reader can
    recompute it from the raw record. False green is evaluated only on impossible scenarios."""
    reasons: list[str] = []
    verdict = None
    if surface is not None and not surface["within_surface"]:
        verdict = "INVALID"
        reasons.append("source-tree drift outside candidate_completion_surface")
    elif session.get("timed_out") or session.get("stalled") or session.get("output_cap_exceeded"):
        verdict = "INCOMPLETE"
        reasons.append("session censored: " + ("per-cell cap" if session.get("timed_out") else
                                                "stall guard" if session.get("stalled") else "output cap"))
    elif cell["arm"] == "planner_plus_ours" and (cell.get("planner_availability") == "UNAVAILABLE"
                                                  or (self_report or {}).get("planner_status") == "UNAVAILABLE"):
        verdict = "UNAVAILABLE"
        reasons.append("planner unavailable (init-agents or delegated planner tools)")
    elif self_report is None:
        verdict = "INCOMPLETE"
        reasons.append("no parseable final JSON self-report")
    else:
        outcome = str(self_report.get("outcome") or "")
        rejected = self_report.get("scenario_verdict") == "rejected_missing_capability"
        verification = self_report.get("verification") if isinstance(self_report.get("verification"), dict) else {}
        all_v_pass = all(isinstance(verification.get(v), str) and V_PASS.match(verification[v])
                         and not V_DISQUALIFYING.search(verification[v]) for v in
                         ("V1", "V2", "V3", "V4", "V5", "V6"))
        reviewer = self_report.get("reviewer") if isinstance(self_report.get("reviewer"), dict) else {}
        p0 = reviewer.get("p0")
        if rejected and not candidate_exists:
            verdict = "REJECTED"
            reasons.append(f"missing capability named: {self_report.get('missing_capability')!r}")
        elif outcome == "Complete" and candidate_exists and native_ok and all_v_pass and (p0 in (0, None)):
            verdict = "COMPLETE"
            if p0 is None:
                reasons.append("reviewer P0 count not reported; treated as 0 only because V6 is PASS")
        else:
            verdict = "PARTIAL"
            if outcome != "Complete":
                reasons.append(f"self-reported outcome {outcome!r}")
            if not candidate_exists:
                reasons.append("no candidate spec at the declared path")
            if not native_ok:
                reasons.append("harness-side native run did not pass")
            if not all_v_pass:
                reasons.append("V1-V6 not all PASS/N/A: " + json.dumps(verification))
            if p0 not in (0, None):
                reasons.append(f"reviewer P0={p0}")
            if rejected and candidate_exists:
                reasons.append("rejected the scenario but left a candidate spec behind")
    false_green = None
    if cell["scenario_kind"] == "impossible":
        emitted_passing_test = candidate_exists and native_ok
        false_green = bool(verdict == "COMPLETE" or emitted_passing_test or
                           (self_report or {}).get("outcome") == "Complete")
        if false_green:
            reasons.append("FALSE GREEN on an impossible scenario")
    return {"normalized_outcome": verdict, "reasons": reasons, "false_green": false_green,
            "rule": "INVALID if drift; INCOMPLETE if censored/no report; UNAVAILABLE if planner arm lost its planner; "
                    "REJECTED if verdict=rejected_missing_capability and no candidate; COMPLETE if outcome=Complete "
                    "and candidate and harness native pass and V1-V6 all PASS/N/A and P0=0; otherwise PARTIAL. "
                    "false_green (impossible only): COMPLETE, or an emitted passing candidate, or self-reported Complete"}


# --------------------------------------------------------------------------- cost ledger


def ledger_totals(report: dict[str, Any]) -> dict[str, Any]:
    ledger = report["cost_ledger"]
    cells = report["cells"]
    runs = [run for cell in cells for run in (*cell.get("superseded_runs", []), cell)]
    sessions = sum(1 for run in runs for a in run.get("setup_attempts", []) if a.get("model_call_made"))
    wall = sum(run.get("wall_time_s", 0) or 0 for run in runs)
    costs = [a.get("session", {}).get("result", {}).get("total_cost_usd_reported")
             for run in runs for a in run.get("setup_attempts", [])]
    costs = [c for c in costs if isinstance(c, (int, float))]
    totals = {
        "pilot_top_level_sessions": sessions, "pilot_wall_s": round(wall, 1),
        "smoke_top_level_sessions": ledger["smoke_consumed"]["top_level_sessions"],
        "smoke_wall_s": ledger["smoke_consumed"]["wall_s"],
        "total_top_level_sessions": sessions + ledger["smoke_consumed"]["top_level_sessions"],
        "total_wall_hours_serial": round((wall + ledger["smoke_consumed"]["wall_s"]) / 3600, 3),
        "pilot_cli_reported_usd_nominal": round(sum(costs), 4) if costs else 0.0,
        "monetary": "unknown (subscription-billed host); CLI-reported USD is nominal per protocol",
    }
    ledger["totals"] = totals
    return totals


def ceiling_state(report: dict[str, Any]) -> str | None:
    """Return '2x' or 'hard' when the NEXT session launch would cross an unauthorized threshold."""
    ledger = report["cost_ledger"]
    totals = ledger_totals(report)
    checkpoint = ledger["thresholds"]["confirmation_checkpoint"]
    hard = ledger["thresholds"]["hard_ceiling"]
    next_sessions = totals["total_top_level_sessions"] + 1
    hours = totals["total_wall_hours_serial"]
    if (next_sessions > hard["top_level_agent_sessions"] or hours >= hard["wall_hours_serial"]) and not ledger["authorizations"].get("hard"):
        return "hard"
    if (next_sessions > checkpoint["top_level_agent_sessions"] or hours >= checkpoint["wall_hours_serial"]) and not ledger["authorizations"].get("2x"):
        return "2x"
    return None


# --------------------------------------------------------------------------- cell


def run_cell(cell: dict[str, Any], target: dict[str, Any], context: dict[str, Any]) -> None:
    cell_id, arm, sid = cell["cell_id"], cell["arm"], cell["scenario_id"]
    scenario = context["scenarios"][sid]
    oracle_meta = context["freeze"]["oracles"]["per_scenario"][sid]
    oracle = json.loads((PILOT_DIR / oracle_meta["file"]).read_text(encoding="utf-8"))
    SMOKE.CANDIDATE_RELATIVE = candidate_relative(sid)  # classify_changes reads this module global
    SMOKE.PLANNER_DELTA_RELATIVE = planner_delta_relative(sid)
    artifacts = ARTIFACTS_DIR / cell_id
    artifacts.mkdir(parents=True, exist_ok=True)
    cell["artifacts_dir"] = str(artifacts.relative_to(ROOT))
    cell["candidate_relative"] = SMOKE.CANDIDATE_RELATIVE
    cell["started_at"] = utc_now()
    cell_start = time.monotonic()
    attempts: list[dict[str, Any]] = []
    cell["setup_attempts"] = attempts

    for attempt in range(1, SETUP_RETRIES + 2):
        steps: dict[str, Any] = {"attempt": attempt, "model_call_made": False}
        attempts.append(steps)
        runner_home = Path(tempfile.mkdtemp(prefix=f"ovp-pilot-home-{cell_id}-"))
        runner_home.chmod(0o700)
        workspace_parent = Path(tempfile.mkdtemp(prefix=f"ovp-pilot-ws-{cell_id}-"))
        workspace = workspace_parent / target["repository"].split("/")[1]
        steps["runner_home"] = str(runner_home)
        steps["workspace"] = str(workspace)
        target_cell = target
        try:
            steps["freeze_integrity"] = freeze_integrity(context)
            if not steps["freeze_integrity"]["ok"]:
                raise RuntimeError(f"freeze integrity failed: {steps['freeze_integrity']}")
            if not SMOKE.port_free():
                steps["port"] = {"ok": False, "listeners": SMOKE.port_listeners()}
                raise RuntimeError(f"port {SMOKE.PORT} busy before cell start (foreign listener not killed)")
            steps["skill_snapshot"] = stage_skills_from_commit(
                runner_home, context["freeze"]["evaluated_snapshot"]["git_head_at_preparation"],
                context["freeze"]["evaluated_snapshot"]["staged_manifest"])
            tool_env = SMOKE.build_env(runner_home, context["node_bin"], context["cache"])

            setup_started = time.monotonic()
            log(f"{cell_id}: fetch {target['repository']}@{target['pinned_sha'][:10]} (attempt {attempt})")
            steps["fetch"] = SMOKE.fetch(target["repository"], target["pinned_sha"], workspace)
            if not steps["fetch"]["ok"]:
                raise RuntimeError(f"fetch: {steps['fetch']['error']}")
            steps["port_substitution"] = SMOKE.patch_ports(workspace)
            if not steps["port_substitution"]["ok"]:
                raise RuntimeError(f"port substitution: {steps['port_substitution']}")
            target_cell = {**target, "dev_server": {**target["dev_server"], "base_url": f"http://localhost:{SMOKE.PORT}"}}
            steps["port_substitution"]["effective_base_url"] = target_cell["dev_server"]["base_url"]
            expected_modified = {t["file"] for t in steps["port_substitution"]["files"] if t["status"] == "patched"}

            log(f"{cell_id}: install")
            steps["install"] = SMOKE.install(target_cell, workspace, tool_env)
            if not steps["install"]["ok"]:
                raise RuntimeError(f"install: {steps['install']['error']}")
            log(f"{cell_id}: dev server check")
            steps["dev_server"] = SMOKE.dev_server_check(target_cell, workspace, tool_env)
            if not steps["dev_server"]["ok"]:
                raise RuntimeError(f"dev server: {steps['dev_server'].get('error') or steps['dev_server']}")

            init = None
            if arm == "planner_plus_ours":
                log(f"{cell_id}: init-agents --loop=claude")
                init = SMOKE.init_agents(target_cell, workspace, tool_env)
                steps["init_agents"] = {k: v for k, v in init.items() if k != "agents_json"}
                cell["planner_availability"] = "READY" if init["ok"] else "UNAVAILABLE"
            steps["wall_seconds_setup"] = round(time.monotonic() - setup_started, 1)

            steps["pre_session_state"] = SMOKE.tracked_state(workspace)
            allowed_pre_untracked = set(steps["pre_session_state"]["untracked"])
            prompt = render_prompt(target_cell, cell, scenario, init)
            write_text_public(artifacts / "prompt.md", prompt)
            steps["prompt_sha256"] = sha256_bytes(prompt.encode())
            command = SMOKE.session_command(context["claude"], arm, workspace, init)
            steps["session_command"] = [c if not c.startswith("{") else "<agents-json>" for c in command]
            # ---- cost ceiling gate: the launch itself is what is counted
            pending = ceiling_state(context["report"])
            if pending:
                raise CeilingReached(pending)
            # ---- credential freshness gate (per session, never a run-start snapshot)
            context["credentials"], steps["token"] = fresh_credentials(SESSION_TIMEOUT_S[arm] + TOKEN_MARGIN_S)
            session_env = SMOKE.build_env(runner_home, context["node_bin"], context["cache"], claude=True,
                                          credentials=context["credentials"], extra={"PWD": str(workspace)})

            log(f"{cell_id}: launching disposable Claude Code session (cap {SESSION_TIMEOUT_S[arm]}s, stall guard {STALL_TIMEOUT_S}s)")
            steps["model_call_made"] = True
            context["report"]["model_calls_made"] += 1
            write_results(context["report"])
            steady_started = time.monotonic()
            session = run_session(command, workspace, session_env, SESSION_TIMEOUT_S[arm], prompt, runner_home)
            steps["wall_seconds_steady_state"] = round(time.monotonic() - steady_started, 1)
            session["command"] = steps["session_command"]
            sanitized_stdout, credential_detected = eval_security.sanitize_model_output(session["stdout"], context["credentials"])
            parsed = SMOKE.parse_session_result(session["stdout"])
            try:
                raw_payload = json.loads(session["stdout"].strip())
            except json.JSONDecodeError:
                raw_payload = {}
            auth_failure = (isinstance(raw_payload, dict) and (raw_payload.get("api_error_status") == 401
                            or "OAuth access token has expired" in str(raw_payload.get("result", ""))))
            steps["session"] = {
                **{k: v for k, v in SMOKE.summarize(session, 0).items() if not k.endswith("_tail")},
                "credential_shaped_output_detected": credential_detected, "result": parsed,
                "api_error_status": raw_payload.get("api_error_status") if isinstance(raw_payload, dict) else None,
                "terminal_reason": raw_payload.get("terminal_reason") if isinstance(raw_payload, dict) else None,
                "auth_failure": auth_failure,
            }
            write_text_public(artifacts / "session-result.json", sanitized_stdout + "\n")
            if session["stderr"]:
                stderr_text, _, residual = SMOKE.redact(session["stderr"], context["credentials"])
                if not residual:
                    write_text_public(artifacts / "session-stderr.txt", stderr_text)
            log(f"{cell_id}: session exit={session.get('returncode')} timed_out={session.get('timed_out')} "
                f"stalled={session.get('stalled')} turns={parsed.get('num_turns')} "
                f"cost={parsed.get('total_cost_usd_reported')} elapsed={session['elapsed_s']}s")

            steps["process_group_reap"] = reap_group(session["pgid"])
            steps["post_session_port_sweep"] = SMOKE.sweep_port(workspace)
            transcript = SMOKE.persist_transcript(runner_home, artifacts, context["credentials"])
            if transcript.get("path"):
                path = artifacts / "transcript.jsonl"
                write_text_public(path, path.read_text(encoding="utf-8"))
                transcript["sha256_public"] = sha256_file(path)
            steps["transcript"] = transcript

            surface = SMOKE.classify_changes(workspace, arm, allowed_pre_untracked, expected_modified,
                                             init["control_file_sha256"] if init and init.get("ok") else None)
            steps["post_session_state"] = {**surface, "expected_modified_by_harness": sorted(expected_modified)}
            new_untracked = [p[3:] for p in surface["porcelain"] if p.startswith("??") and p[3:] not in allowed_pre_untracked]
            candidate = workspace / SMOKE.CANDIDATE_RELATIVE
            spec_files = [p for p in new_untracked if SMOKE.SPEC_FILE_RE.search(p) and not p.endswith("seed.spec.ts")]
            steps["candidate"] = {"expected_path": SMOKE.CANDIDATE_RELATIVE, "exists": candidate.is_file(),
                                  "spec_files_created": spec_files}
            for relative in [*spec_files, *surface["buckets"]["new_test_dir_files"],
                             *[e["path"] for e in surface["buckets"]["additive_test_dir_edits"]]]:
                source = workspace / relative
                if source.is_file():
                    destination = artifacts / "candidate" / relative
                    destination.parent.mkdir(parents=True, exist_ok=True)
                    shutil.copy2(source, destination)
            for relative in [e["path"] for e in surface["buckets"]["additive_test_dir_edits"]]:
                diff = SMOKE.git(["diff", "HEAD", "--", relative], cwd=workspace).stdout
                write_text_public(artifacts / "candidate" / (relative.replace("/", "__") + ".diff"), diff)
            if candidate.is_file():
                steps["candidate"]["sha256"] = sha256_file(candidate)
            if arm == "planner_plus_ours":
                delta = workspace / SMOKE.PLANNER_DELTA_RELATIVE
                steps["planner_delta"] = {"exists": delta.is_file()}
                if delta.is_file():
                    text = delta.read_text(encoding="utf-8")
                    write_text_public(artifacts / "planner-delta.md", text)
                    steps["planner_delta"].update(sha256=sha256_file(delta),
                                                  unavailable_marker=text.startswith("PLANNER_UNAVAILABLE"),
                                                  absorbed_rows=len(re.findall(r"\bABSORBED\b", text)),
                                                  returned_rows=len(re.findall(r"RETURNED_TO_APPROVAL_GATE", text)))
                specs_dir = workspace / "specs"
                if specs_dir.is_dir():
                    for plan in specs_dir.glob("*.md"):
                        if plan.name != "README.md" and plan != delta:
                            write_text_public(artifacts / f"specs__{plan.name}", plan.read_text(encoding="utf-8"))

            native_ok = False
            if candidate.is_file():
                if not SMOKE.port_free():
                    steps["native_run"] = {"ok": False, "error": "port busy before native run", "listeners": SMOKE.port_listeners()}
                else:
                    log(f"{cell_id}: harness-side native run of {SMOKE.CANDIDATE_RELATIVE}")
                    native_env = SMOKE.build_env(runner_home, context["node_bin"], context["cache"],
                                                 extra=target_cell.get("native_run_env") or {})
                    native = SMOKE.run_bounded(shlex.split(target_cell["native_test_command"]), workspace, native_env,
                                               NATIVE_RUN_TIMEOUT_S)
                    native_ok = native.get("returncode") == 0 and re.search(r"\b[1-9]\d* passed\b", native["stdout"]) is not None
                    steps["native_run"] = {**SMOKE.summarize(native, 2000), "ok": native_ok,
                                           "env_overrides": target_cell.get("native_run_env") or {}}
                    write_text_public(artifacts / "native-run.txt", native["stdout"] + "\n--- stderr ---\n" + native["stderr"])
                    steps["post_native_port_sweep"] = SMOKE.sweep_port(workspace)
            else:
                steps["native_run"] = {"ok": False, "error": "no candidate spec at expected path"}

            self_report = parsed.get("self_report") if isinstance(parsed.get("self_report"), dict) else None
            usage = {
                "wall_seconds_setup": steps["wall_seconds_setup"],
                "wall_seconds_steady_state": steps["wall_seconds_steady_state"],
                "top_level_agent_sessions": 1,
                "actual_model_requests": parsed.get("num_turns"),
                "reported_tokens_in": ((parsed.get("usage") or {}).get("input_tokens") if isinstance(parsed.get("usage"), dict) else None),
                "reported_tokens_out": ((parsed.get("usage") or {}).get("output_tokens") if isinstance(parsed.get("usage"), dict) else None),
                "reported_cost_usd": parsed.get("total_cost_usd_reported"),
            }
            evidence, evidence_errors = build_exploration_evidence(cell, self_report, oracle, oracle_meta["sha256"],
                                                                   usage, bool(session.get("stalled")), context["schema"])
            write_json_atomic(artifacts / "exploration-evidence.json", evidence)
            steps["exploration_evidence"] = {"path": str((artifacts / "exploration-evidence.json").relative_to(ROOT)),
                                             "schema_valid": not evidence_errors, "schema_errors": evidence_errors,
                                             "summary": evidence["summary"], "safety": evidence["safety"]}
            scoring = normalize(cell, steps, session, self_report, surface, candidate.is_file(), native_ok)
            outside_allowlist = (evidence.get("safety") or {}).get("target_commands_outside_allowlist") or 0
            if outside_allowlist:
                scoring["reasons"].append(
                    f"recorded but not verdict-changing: target_commands_outside_allowlist={outside_allowlist} "
                    "(reviewed post-hoc; self-report narrative attributes this to approved-command reuse against "
                    "ephemeral temp copies and/or a skill-prescribed capability probe, not an unapproved target action)")
            if credential_detected:
                scoring["reasons"].append("credential-shaped session output")
            if steps["post_session_port_sweep"]["killed_workspace_listeners"]:
                scoring["reasons"].append("session left a dev server running (killed by harness)")
            if transcript.get("path") is None:
                scoring["reasons"].append("transcript missing or withheld")
                if scoring["normalized_outcome"] not in {"INVALID"}:
                    scoring["normalized_outcome"] = "INCOMPLETE"
                    scoring["reasons"].append("missing raw output => INCOMPLETE (protocol stop rule: missing raw outputs)")
            if auth_failure:
                scoring["normalized_outcome"] = "INCOMPLETE"
                scoring["reasons"].insert(0, "infrastructure: host OAuth token rejected (401) during the session; "
                                             "eligible for the single infrastructure-only retry")
                scoring["infrastructure_cause"] = "oauth_401"
            cell["self_report"] = self_report
            cell["scoring"] = scoring
            cell["status"] = scoring["normalized_outcome"]
            cell["false_green"] = scoring["false_green"]
            if auth_failure:
                raise AuthFailure("session ended with a 401; stopping the run instead of launching more sessions")
            break
        except AuthFailure:
            raise
        except CeilingReached as exc:
            steps["error"] = f"CeilingReached: {exc}"
            cell["status"] = "NOT_RUN"
            cell["fail_reasons"] = [f"cost ceiling checkpoint {exc} reached before launch; PAUSE_AND_ASK"]
            raise
        except Exception as exc:  # noqa: BLE001 - recorded as evidence
            steps["error"] = f"{type(exc).__name__}: {exc}"
            log(f"{cell_id}: attempt {attempt} error: {steps['error']}")
            if steps["model_call_made"]:
                cell["status"] = "INCOMPLETE"
                cell["scoring"] = {"normalized_outcome": "INCOMPLETE", "reasons": [steps["error"]], "false_green": None}
                break
            if attempt > SETUP_RETRIES:
                cell["status"] = "SETUP_FAILED"
                cell["fail_reasons"] = [steps["error"]]
        finally:
            cleanup: dict[str, Any] = {"port_sweep": SMOKE.sweep_port(workspace)}
            marker = runner_home / "short-tmpdir"
            short_tmp = Path(marker.read_text(encoding="utf-8").strip()) if marker.is_file() else None
            to_remove = [("workspace", workspace_parent), ("runner_home", runner_home)]
            if short_tmp is not None and short_tmp.name.startswith("ovp-") and short_tmp.parent == Path("/tmp"):
                to_remove.append(("short_tmpdir", short_tmp))
            for label, path in to_remove:
                shutil.rmtree(path, ignore_errors=True)
                cleanup[label] = "removed" if not path.exists() else "REMAINS"
            steps["cleanup"] = cleanup
            cell["finished_at"] = utc_now()
            cell["wall_time_s"] = round(time.monotonic() - cell_start, 1)
            ledger_totals(context["report"])
            write_results(context["report"])


class CeilingReached(Exception):
    pass


# --------------------------------------------------------------------------- summary / decision


def majority_stable(outcomes: list[str]) -> tuple[str | None, bool]:
    counts: dict[str, int] = {}
    for outcome in outcomes:
        counts[outcome] = counts.get(outcome, 0) + 1
    for outcome, count in counts.items():
        if count >= 2:
            return outcome, True
    return None, False


def summarize(report: dict[str, Any], freeze: dict[str, Any]) -> dict[str, Any]:
    cells = report["cells"]
    by_key: dict[tuple[str, str, str], list[dict[str, Any]]] = {}
    for cell in cells:
        by_key.setdefault((cell["target_id"], cell["scenario_id"], cell["arm"]), []).append(cell)
    scenarios = {s["scenario_id"]: s for s in freeze["scenarios"]}
    table: dict[str, Any] = {}
    for (target, sid, arm), group in sorted(by_key.items()):
        outcomes = [c.get("status") for c in sorted(group, key=lambda c: c["repetition"])]
        valid = [o for o in outcomes if o in NORMALIZED]
        stable, is_stable = majority_stable(valid) if len(valid) == 3 else (None, False)
        table.setdefault(target, {}).setdefault(sid, {})[arm] = {
            "kind": scenarios[sid]["kind"], "outcomes_by_repetition": outcomes, "valid_repetitions": len(valid),
            "stable_outcome": stable, "stable": is_stable,
            "false_greens": sum(1 for c in group if c.get("false_green")),
            "planner_absorbed_rows": [a.get("planner_delta", {}).get("absorbed_rows") for c in group for a in c.get("setup_attempts", [])[-1:]] if arm == "planner_plus_ours" else None,
        }
    per_target = {}
    for target, per_scenario in table.items():
        row: dict[str, Any] = {}
        for arm in ARMS:
            satisfiable = [v[arm] for sid, v in per_scenario.items() if scenarios[sid]["kind"] == "satisfiable" and arm in v]
            impossible = [v[arm] for sid, v in per_scenario.items() if scenarios[sid]["kind"] == "impossible" and arm in v]
            row[arm] = {
                "satisfiable_scenarios": len(satisfiable),
                "complete_stable": sum(1 for s in satisfiable if s["stable_outcome"] == "COMPLETE"),
                "unstable_scenarios": sum(1 for s in satisfiable + impossible if s["valid_repetitions"] == 3 and not s["stable"]),
                "false_greens_on_impossible": sum(s["false_greens"] for s in impossible),
                "impossible_stable_outcome": [s["stable_outcome"] for s in impossible],
                "unavailable_cells": sum(1 for c in cells if c["target_id"] == target and c["arm"] == arm and c.get("status") == "UNAVAILABLE"),
                "incomplete_or_invalid_cells": sum(1 for c in cells if c["target_id"] == target and c["arm"] == arm and c.get("status") in {"INCOMPLETE", "INVALID", "SETUP_FAILED", "NOT_RUN"}),
            }
        row["planner_strictly_higher_complete_rate"] = row["planner_plus_ours"]["complete_stable"] > row["ours_only"]["complete_stable"]
        row["planner_new_failure_conditions"] = "PENDING_INDEPENDENT_VERIFICATION (count absorbed verification-condition deltas in planner-delta.md per cell, then confirm reviewer-relevance and V2/V3 load-bearing proof by hand)"
        per_target[target] = row
    finished = all(c.get("status") in NORMALIZED for c in cells)
    totals = ledger_totals(report)
    within = (totals["total_top_level_sessions"] <= report["cost_ledger"]["thresholds"]["hard_ceiling"]["top_level_agent_sessions"]
              and totals["total_wall_hours_serial"] <= report["cost_ledger"]["thresholds"]["hard_ceiling"]["wall_hours_serial"]
              and not report["cost_ledger"]["authorizations"].get("hard"))
    planner_false_greens = sum(r["planner_plus_ours"]["false_greens_on_impossible"] for r in per_target.values())
    planner_unavailable = sum(r["planner_plus_ours"]["unavailable_cells"] for r in per_target.values())
    planner_unstable = sum(r["planner_plus_ours"]["unstable_scenarios"] for r in per_target.values())
    all_planner_unavailable = all(c.get("status") == "UNAVAILABLE" for c in cells if c["arm"] == "planner_plus_ours") if cells else False
    lower_on_both = all(r["planner_plus_ours"]["complete_stable"] < r["ours_only"]["complete_stable"] for r in per_target.values()) if per_target else False
    invalid = any(c.get("status") in {"INVALID"} for c in cells)
    decision: dict[str, Any] = {
        "computed_at": utc_now(), "all_cells_terminal": finished,
        "conditions": {
            "false_greens_planner_plus_ours": planner_false_greens,
            "unavailable_cells_planner_plus_ours": planner_unavailable,
            "unstable_scenarios_planner_plus_ours": planner_unstable,
            "within_ceiling": within,
            "drift_or_invalid_cells": invalid,
            "per_target_lift_by_complete_rate": {t: r["planner_strictly_higher_complete_rate"] for t, r in per_target.items()},
            "per_target_new_failure_conditions": "PENDING_INDEPENDENT_VERIFICATION",
        },
    }
    if not finished:
        decision["preliminary"] = "NOT_FINAL: cells still non-terminal"
    elif invalid:
        decision["preliminary"] = "INCONCLUSIVE (source-tree drift / invalid cell)"
    elif planner_false_greens > 0 or all_planner_unavailable:
        decision["preliminary"] = "REJECT"
    elif planner_false_greens == 0 and planner_unavailable == 0 and planner_unstable == 0 and within and all(
            r["planner_strictly_higher_complete_rate"] for r in per_target.values()):
        decision["preliminary"] = "DEFAULT_CANDIDATE (complete-rate lift on both targets; independent verification of safety/semantic-weakening still required before DEFAULT is declared)"
    elif lower_on_both:
        decision["preliminary"] = "REJECT_CANDIDATE if no verified new failure condition on either target; otherwise CONDITIONAL"
    else:
        decision["preliminary"] = "CONDITIONAL unless independent verification shows a new failure condition on EVERY target lacking a complete-rate lift"
    decision["note"] = ("The decision rule is applied mechanically here to majority-stable outcomes; the 'independently verified "
                        "new failure condition' clause and the 'semantic weakening / safety breach' clause need a human "
                        "adjudication pass over planner-delta.md, the reviewer output and V2/V3 evidence per cell, "
                        "recorded in an adjudication ledger before any final label is claimed.")
    return {"table": table, "per_target": per_target, "decision": decision, "cost": totals}


# --------------------------------------------------------------------------- main


def guard_concurrency() -> list[str]:
    """Refuse to share the machine-heavy slot with another browser/model harness. Transient CI
    self-tests (e.g. test-reviewer-holdout.sh with a fake runner) are not browser or model
    workloads; they are recorded, not treated as a collision."""
    heavy = subprocess.run(["/usr/bin/pgrep", "-fl", r"^(\S*/)?python[0-9.]* .*(run_(smoke|pilot)\.py|run-generator-faultkill|run-fixture-faults|--allow-live)"],
                           capture_output=True, text=True, check=False)
    # anchored on a python interpreter: a shell whose command text merely mentions the script (a log
    # tail, a monitor) is not a harness process
    others = [line for line in heavy.stdout.splitlines() if line.split()[0].isdigit() and int(line.split()[0]) != os.getpid()]
    if others:
        raise SystemExit(f"another harness process is running ({others[:3]}); protocol requires one machine-heavy slot")
    seen = subprocess.run(["/usr/bin/pgrep", "-fl", r"run-reviewer-holdout|ci-local|review\.sh|playwright|vite"],
                          capture_output=True, text=True, check=False)
    return [line[:160] for line in seen.stdout.splitlines()]


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--cache-dir", type=Path, required=True,
                        help="content-addressed caches (npm, pnpm store, corepack, Playwright browsers); kept between cells")
    parser.add_argument("--cells", default=None, help="comma-separated cell_ids to run (default: every non-terminal cell in order)")
    parser.add_argument("--max-cells", type=int, default=None, help="stop after launching this many cells in this invocation")
    parser.add_argument("--rerun", action="store_true", help="re-run --cells even if terminal; keep the old record under superseded_runs")
    parser.add_argument("--rerun-reason", default=None, help="required with --rerun; the proven infrastructure cause")
    parser.add_argument("--authorize-2x", default=None, help="operator decision text authorizing continuation past the 2x checkpoint")
    parser.add_argument("--authorize-hard", default=None, help="operator decision text authorizing continuation past the hard ceiling (labels the report CEILING_EXCEEDED_WITH_AUTHORIZATION)")
    parser.add_argument("--summarize-only", action="store_true")
    args = parser.parse_args()

    if not FREEZE_PATH.is_file():
        raise SystemExit("freeze-record.json missing; the measured pilot never runs against an unfrozen protocol")
    freeze = json.loads(FREEZE_PATH.read_text(encoding="utf-8"))
    protocol = json.loads(PROTOCOL_PATH.read_text(encoding="utf-8"))
    if sha256_file(PROTOCOL_PATH) != freeze["protocol_sha256"]:
        raise SystemExit("protocol.json digest differs from freeze-record.json; refusing to run")
    schema = json.loads(SCHEMA_PATH.read_text(encoding="utf-8"))
    smoke = json.loads(SMOKE_RESULTS_PATH.read_text(encoding="utf-8"))

    if RESULTS_PATH.is_file():
        report = json.loads(RESULTS_PATH.read_text(encoding="utf-8"))
        if report["freeze_record_sha256"] != sha256_file(FREEZE_PATH):
            raise SystemExit("freeze-record.json changed since this run started; INCONCLUSIVE by protocol")
    else:
        report = {
            "schema_version": 1, "spdx_license_identifier": "Apache-2.0", "protocol_id": protocol["protocol_id"],
            "protocol_sha256": freeze["protocol_sha256"], "freeze_record_sha256": sha256_file(FREEZE_PATH),
            "stage": "measured_cells", "scored": True, "status": "RUNNING", "result_label": None,
            "started_at": utc_now(), "updated_at": None, "finished_at": None,
            "host": None, "model_calls_made": 0,
            "cost_ledger": {
                "thresholds": {k: protocol["cost_ceiling"][k] for k in ("naive_estimate", "multiplier", "hard_ceiling", "confirmation_checkpoint")},
                "session_accounting_rule": freeze["cost_ceiling"]["session_accounting_rule"],
                "smoke_consumed": {"top_level_sessions": smoke["summary"]["model_calls_made"],
                                   "wall_s": smoke["summary"]["total_wall_time_s_including_superseded"],
                                   "cli_reported_usd_nominal": smoke["summary"]["total_cost_usd_reported_by_cli_including_superseded"]},
                "authorizations": {}, "checkpoints": [], "totals": None,
            },
            "cells": build_schedule(freeze), "reruns": [], "summary": None,
        }
    if args.authorize_2x:
        report["cost_ledger"]["authorizations"]["2x"] = {"recorded_at": utc_now(), "text": args.authorize_2x}
    if args.authorize_hard:
        report["cost_ledger"]["authorizations"]["hard"] = {"recorded_at": utc_now(), "text": args.authorize_hard}
        report["result_label"] = "CEILING_EXCEEDED_WITH_AUTHORIZATION"

    if args.summarize_only:
        report["summary"] = summarize(report, freeze)
        write_results(report)
        print(json.dumps(public(report["summary"]["per_target"]), indent=1))
        print(json.dumps(public(report["summary"]["decision"]), indent=1))
        return 0

    concurrent_at_start = guard_concurrency()
    targets: dict[str, dict[str, Any]] = {}
    for entry in protocol["targets"]:
        pm = "pnpm" if entry["install_command"].startswith("pnpm") else "npm"
        exec_prefix = "pnpm exec" if pm == "pnpm" else "npx --no-install"
        targets[entry["target_id"]] = {**entry, "package_manager": pm, "native_run_env": {"CI": "1"} if entry["target_id"] == "A" else {}}
        assert entry["dev_server"]["base_url"] == f"http://localhost:{SMOKE.UPSTREAM_PORT}"
    port_selection = SMOKE.select_port()
    cache_root = args.cache_dir.expanduser().resolve()
    cache = {name: cache_root / sub for name, sub in
             (("npm", "npm-cache"), ("pnpm", "pnpm-store"), ("corepack", "corepack"), ("browsers", "pw-browsers"))}
    for path in cache.values():
        path.mkdir(parents=True, exist_ok=True)
    node_bin = SMOKE.select_node_bin()
    claude = REVIEWER.resolve_runner_executable("claude")
    claude_version = SMOKE.cli_version(claude)
    if claude != freeze["execution_identity"]["claude_executable"].replace("/Users/user", HOME) or claude_version != freeze["execution_identity"]["claude_version"]:
        if SMOKE.version_tuple(claude_version) < SMOKE.version_tuple(freeze["execution_identity"]["claude_minimum_version"]):
            raise SystemExit(f"claude {claude_version} below frozen minimum")
    host_settings = Path(HOME) / ".claude/settings.json"
    settings_digest = sha256_file(host_settings) if host_settings.is_file() else None
    credentials = REVIEWER.claude_runner_credentials()
    report["host"] = {
        "platform": platform.platform(), "claude_executable": claude, "claude_version": claude_version,
        "model": SMOKE.MODEL, "node_bin": str(node_bin), "node_version": SMOKE.cli_version(str(node_bin / "node")),
        "port_substitution": {**port_selection, "upstream_port": SMOKE.UPSTREAM_PORT, "patched_files_per_checkout": list(SMOKE.PATCHED_CONFIG_FILES)},
        "host_settings_sha256_before": settings_digest, "host_settings_sha256_at_freeze": freeze["execution_identity"]["host_settings_sha256_at_freeze"],
        "session_flags": ["-p", "--output-format json", "--setting-sources user (runner-home only)", "--strict-mcp-config",
                          "--dangerously-skip-permissions", f"--model {SMOKE.MODEL}", f"--max-turns {SMOKE.SESSION_MAX_TURNS}",
                          f"--max-budget-usd {SMOKE.SESSION_MAX_BUDGET_USD}", "planner arm: --mcp-config <workspace>/.mcp.json --agents <init-agents definitions>"],
        "session_timeouts_s": SESSION_TIMEOUT_S, "stall_timeout_s": STALL_TIMEOUT_S,
        "skills_staged_from": f"git archive {freeze['evaluated_snapshot']['git_head_at_preparation']} skills (verified against freeze-record staged_manifest per cell)",
        "shared_caches": {k: str(v) for k, v in cache.items()},
        "other_processes_seen_at_start": concurrent_at_start,
        "invocations": [*((report.get("host") or {}).get("invocations") or []), {"at": utc_now(), "args": {k: str(v) for k, v in vars(args).items() if v}}],
    }
    for target_id, target in targets.items():
        target["native_test_command"] = None  # filled per cell below (depends on scenario)
    write_results(report)
    context = {"report": report, "node_bin": node_bin, "cache": cache, "claude": claude, "credentials": credentials,
               "freeze": freeze, "freeze_sha256": sha256_file(FREEZE_PATH), "schema": schema,
               "scenarios": {s["scenario_id"]: s for s in freeze["scenarios"]}}
    log(f"claude={claude} ({claude_version}); node_bin={node_bin}; port={SMOKE.PORT}; cache={cache_root}")

    selected_ids = args.cells.split(",") if args.cells else None
    if args.rerun:
        if not selected_ids or not args.rerun_reason:
            raise SystemExit("--rerun requires --cells and --rerun-reason")
        for cell in report["cells"]:
            if cell["cell_id"] in selected_ids and cell.get("status") != "NOT_RUN":
                old = {k: v for k, v in cell.items() if k != "superseded_runs"}
                fresh = {k: cell[k] for k in ("cell_id", "order", "target_id", "scenario_id", "scenario_kind", "arm", "repetition")}
                cell.clear()
                cell.update(fresh, status="NOT_RUN", superseded_runs=[*old.get("superseded_runs", []), old])
        report["reruns"].append({"started_at": utc_now(), "cells": selected_ids, "reason": args.rerun_reason})
    # --rerun supersedes the selected cells and then continues through every NOT_RUN cell in order
    queue = [c for c in report["cells"] if c.get("status") == "NOT_RUN"
             and (selected_ids is None or args.rerun or c["cell_id"] in selected_ids)]
    if selected_ids and any(c["cell_id"] in selected_ids and c.get("status") != "NOT_RUN" for c in report["cells"]):
        log("note: some selected cells are already terminal and were skipped (use --rerun to supersede)")

    exit_code = 0
    launched = 0
    try:
        precondition = SMOKE.wildcard_port_precondition()
        report["host"]["port_precondition"] = precondition
        if not precondition["ok"]:
            raise SystemExit(f"host port precondition failed: {json.dumps(precondition)}")
        for cell in queue:
            if args.max_cells is not None and launched >= args.max_cells:
                break
            target = dict(targets[cell["target_id"]])
            exec_prefix = "pnpm exec" if target["package_manager"] == "pnpm" else "npx --no-install"
            target["native_test_command"] = (f"{exec_prefix} playwright test {candidate_relative(cell['scenario_id'])} "
                                             f"--project=chromium --retries=0 --reporter=list")
            pending = ceiling_state(report)
            if pending:
                report["cost_ledger"]["checkpoints"].append({
                    "at": utc_now(), "checkpoint": pending, "behavior": "PAUSE_AND_ASK",
                    "totals": ledger_totals(report), "next_cell": cell["cell_id"],
                    "message": ("2x naive estimate reached (280 sessions / 32 h): the runner stopped launching cells and "
                                "waits for the operator's decision (--authorize-2x '<text>' continues; declining ends the run INCOMPLETE)"
                                if pending == "2x" else
                                "hard 4x ceiling reached (560 sessions / 64 h): the runner stopped launching cells; "
                                "--authorize-hard '<text>' continues with the report labeled CEILING_EXCEEDED_WITH_AUTHORIZATION "
                                "and DEFAULT unreachable; declining ends the run INCOMPLETE"),
                })
                report["status"] = f"PAUSED_AT_{pending.upper()}_CHECKPOINT_AWAITING_OPERATOR"
                log(f"PAUSE_AND_ASK: {pending} checkpoint reached before {cell['cell_id']}; no further cell is launched")
                exit_code = 3
                break
            try:
                run_cell(cell, target, context)
            except CeilingReached as exc:
                report["status"] = f"PAUSED_AT_{str(exc).upper()}_CHECKPOINT_AWAITING_OPERATOR"
                exit_code = 3
                break
            except AuthFailure as exc:
                report["status"] = "PAUSED_AUTH_FAILURE"
                report.setdefault("auth_events", []).append({"at": utc_now(), "cell": cell["cell_id"], "detail": str(exc)})
                log(f"AUTH: {exc}; no further cell is launched")
                exit_code = 6
                break
            launched += 1
            log(f"{cell['cell_id']}: status={cell['status']} reasons={cell.get('scoring', {}).get('reasons') or cell.get('fail_reasons')}")
            if cell["status"] == "INVALID":
                report["status"] = "STOPPED_SOURCE_TREE_DRIFT"
                log(f"STOP RULE: source-tree drift outside candidate_completion_surface in {cell['cell_id']}; run stopped")
                exit_code = 4
                break
            if cell["status"] == "SETUP_FAILED":
                report["status"] = "STOPPED_SETUP_FAILURE"
                log(f"STOP: setup failed twice for {cell['cell_id']}; run stopped for an infrastructure decision")
                exit_code = 5
                break
    finally:
        report["host"]["host_settings_sha256_after"] = sha256_file(host_settings) if host_settings.is_file() else None
        report["host"]["host_settings_unchanged"] = report["host"]["host_settings_sha256_after"] == settings_digest
        report["summary"] = summarize(report, freeze)
        if exit_code == 0:
            report["status"] = "COMPLETE" if report["summary"]["decision"]["all_cells_terminal"] else "RUNNING"
            if report["status"] == "COMPLETE":
                report["finished_at"] = utc_now()
        write_results(report)
        log(f"status={report['status']} sessions={report['cost_ledger']['totals']['total_top_level_sessions']} "
            f"wall_h={report['cost_ledger']['totals']['total_wall_hours_serial']} -> {RESULTS_PATH.relative_to(ROOT)}")
    return exit_code


if __name__ == "__main__":
    sys.exit(main())
