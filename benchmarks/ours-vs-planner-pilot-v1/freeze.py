#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Freeze step for benchmarks/ours-vs-planner-pilot-v1: writes freeze-record.json once.

Per protocol.json (evaluated_snapshot.policy, scenarios.freeze_rule, sequencing.must_precede,
metrics.exploration_evidence_log.oracle) this script:

  1. recomputes the evaluated-skill digests from the committed snapshot named in the protocol
     (git_head_at_preparation, tag v1.16.0) via `git archive`, and records how the working tree
     differs from it at freeze time (concurrent, unrelated uncommitted edits are excluded from
     the evaluated snapshot, never silently included);
  2. re-runs the freshness recheck commands for both selected targets and records their output;
  3. freezes the six scenario texts byte-for-byte (sha256 of the UTF-8 bytes of `outcome`);
  4. copies the accessibility-oracle captures (Playwright ariaSnapshot of the pinned SHA, taken by
     the harness operator's agent from a read-only scratch checkout) into oracles/ and records one
     oracle document + digest per scenario;
  5. records execution identity (Claude Code build, model), the cost ceiling, the port policy,
     the host settings digest, and the sequencing-gate results handed in on the command line.

It refuses to run twice: freeze-record.json is written exactly once and never edited afterwards.
"""

from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import platform
import pwd
import re
import shutil
import subprocess
import sys
import tempfile
from typing import Any

PILOT_DIR = Path(__file__).resolve().parent
ROOT = PILOT_DIR.parents[1]
PROTOCOL_PATH = PILOT_DIR / "protocol.json"
SCHEMA_PATH = PILOT_DIR / "exploration-evidence.schema.json"
SMOKE_RESULTS_PATH = PILOT_DIR / "smoke-results.json"
FREEZE_PATH = PILOT_DIR / "freeze-record.json"
ORACLE_DIR = PILOT_DIR / "oracles"
SKILL_DIRS = ("playwright-test-generator", "e2e-reviewer", "playwright-debugger", "cypress-debugger")
TARGET_NAME_TOKENS = ("playwright-chat-lab", "gridfinity-layout-tool", "eilinwis", "andymai")


def load_module(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    assert spec and spec.loader
    spec.loader.exec_module(module)
    return module


SMOKE = load_module("run_smoke", PILOT_DIR / "run_smoke.py")
HOME = pwd.getpwuid(os.getuid()).pw_dir


def utc_now() -> str:
    return dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds")


def sha256_bytes(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def sha256_file(path: Path) -> str:
    return sha256_bytes(path.read_bytes())


def public(value: Any) -> Any:
    """Replace the machine home prefix in every string (pre-push-security 'hardcoded-home')."""
    if isinstance(value, str):
        return re.sub(re.escape(HOME) + r"(?=/|[^A-Za-z0-9._-]|$)", "/Users/user", value)
    if isinstance(value, list):
        return [public(v) for v in value]
    if isinstance(value, dict):
        return {k: public(v) for k, v in value.items()}
    return value


def run(command: list[str], cwd: Path = ROOT, timeout: int = 120) -> subprocess.CompletedProcess[str]:
    return subprocess.run(command, cwd=cwd, capture_output=True, text=True, check=False, timeout=timeout,
                          env={"PATH": "/usr/bin:/bin:/opt/homebrew/bin:/usr/local/bin", "HOME": HOME,
                               "GIT_TERMINAL_PROMPT": "0"})


# --------------------------------------------------------------------------- evaluated snapshot


def archive_skills(commit: str, destination: Path) -> None:
    """Extract the committed skills/ tree of `commit` (raw tar bytes, no working-tree involvement)."""
    archive = subprocess.run(["/usr/bin/git", "archive", commit, "skills"], cwd=ROOT, capture_output=True,
                             check=False, env={"PATH": "/usr/bin:/bin", "HOME": HOME, "GIT_TERMINAL_PROMPT": "0"})
    if archive.returncode != 0:
        raise SystemExit(f"git archive {commit} skills failed: {archive.stderr.decode(errors='replace')}")
    subprocess.run(["/usr/bin/tar", "-x", "-C", str(destination)], input=archive.stdout, check=True)


def manifest(skills_root: Path) -> dict[str, str]:
    out = {}
    for name in SKILL_DIRS:
        for path in sorted((skills_root / name).rglob("*")):
            if path.is_file():
                out[f"skills/{path.relative_to(skills_root).as_posix()}"] = sha256_file(path)
    return out


def evaluated_snapshot(protocol: dict[str, Any]) -> dict[str, Any]:
    commit = protocol["evaluated_snapshot"]["git_head_at_preparation"]
    expected = protocol["evaluated_snapshot"]["sha256_at_preparation"]
    head = run(["/usr/bin/git", "rev-parse", "HEAD"]).stdout.strip()
    tags = run(["/usr/bin/git", "tag", "--points-at", commit]).stdout.split()
    with tempfile.TemporaryDirectory(prefix="ovp-freeze-") as tmp:
        archive_skills(commit, Path(tmp))
        committed = manifest(Path(tmp) / "skills")
    working = manifest(ROOT / "skills")
    recomputed = {path: committed.get(path, "<missing>") for path in expected}
    mismatches = {p: (expected[p], recomputed[p]) for p in expected if expected[p] != recomputed[p]}
    if mismatches:
        raise SystemExit(f"evaluated-skill digest mismatch against protocol: {mismatches}")
    porcelain = run(["/usr/bin/git", "status", "--porcelain=v1", "--", "skills"]).stdout.splitlines()
    differing = sorted(p for p in set(committed) | set(working) if committed.get(p) != working.get(p))
    return {
        "policy": "staged skill bytes come from `git archive <git_head_at_preparation> skills`, never from the working tree",
        "git_head_at_preparation": commit,
        "git_tags_at_commit": tags,
        "git_head_at_freeze": head,
        "head_equals_evaluated_commit": head == commit,
        "sha256_recomputed_at_freeze": recomputed,
        "matches_sha256_at_preparation": True,
        "staged_manifest_sha256": sha256_bytes(json.dumps(committed, sort_keys=True).encode()),
        "staged_manifest_file_count": len(committed),
        "staged_manifest": committed,
        "working_tree_at_freeze": {
            "clean_committed_tree": not porcelain and not differing,
            "git_status_porcelain_skills": porcelain,
            "files_differing_from_evaluated_commit": {
                p: {"committed": committed.get(p), "working_tree": working.get(p)} for p in differing
            },
            "disposition": "excluded from the evaluated snapshot; these are concurrent, unrelated uncommitted edits "
                           "observed to change during freeze preparation (another lane is editing the reviewer and "
                           "generator reference files); the protocol's freeze_requires_clean_committed_tree is "
                           "satisfied for the EVALUATED bytes by staging from the committed snapshot, and recorded "
                           "as NOT satisfied for the repository working tree as a whole",
        },
    }


# --------------------------------------------------------------------------- freshness recheck


def freshness_recheck() -> dict[str, Any]:
    results = {}
    for token in TARGET_NAME_TOKENS:
        tracked = run(["/usr/bin/git", "grep", "-l", "-i", token, "--", ".", ":!testbed",
                       ":!benchmarks/ours-vs-planner-pilot-v1"])
        handover = run(["/usr/bin/grep", "-r", "-l", "-i", token, ".handover"]) if (ROOT / ".handover").is_dir() else None
        log = run(["/usr/bin/git", "log", "--all", "--oneline", "-i", f"--grep={token}"])
        untracked = run(["/usr/bin/grep", "-r", "-l", "-i", token, "benchmarks/exploration-fallback-v1",
                         "benchmarks/subagent-routing-v1", "docs"])
        results[token] = {
            "git_grep_tracked_hits": tracked.stdout.split(),
            "handover_hits": handover.stdout.split() if handover is not None else "(.handover absent)",
            "git_log_all_hits": log.stdout.splitlines(),
            "untracked_sibling_benchmark_and_docs_hits": untracked.stdout.split(),
        }
    hits = any(v["git_grep_tracked_hits"] or v["git_log_all_hits"] or v["untracked_sibling_benchmark_and_docs_hits"]
               or (isinstance(v["handover_hits"], list) and v["handover_hits"]) for v in results.values())
    return {
        "performed_at": utc_now(),
        "rule": "protocol.json freshness_exclusion_search.recheck_before_freeze",
        "exclusions": "testbed/ (gitignored clones) and this pilot directory itself (which names the targets by design)",
        "results": results,
        "any_hit": hits,
        "provenance_class_after_recheck": {"A": "prospective_known" if hits else "prospective_fresh",
                                           "B": "prospective_known" if hits else "prospective_fresh"},
    }


# --------------------------------------------------------------------------- oracles


ARIA_LINE = re.compile(r'^\s*-\s+([a-z]+)(?:\s+"((?:[^"\\]|\\.)*)")?(?:\s+\[([^\]]*)\])?')


def aria_claims(yaml_text: str) -> list[dict[str, Any]]:
    claims = []
    for line in yaml_text.splitlines():
        match = ARIA_LINE.match(line)
        if not match or match.group(1) in {"text", "url"}:
            continue
        claims.append({"role": match.group(1), "name": match.group(2) or "", "state": match.group(3)})
    return claims


SCENARIO_ORACLE_PLAN: dict[str, dict[str, Any]] = {
    "A-S1": {
        "kind": "satisfiable",
        "states": ["chat screen ready with Funny mode checked (offline)", "user message rendered in the transcript",
                   "assistant canned reply rendered, keyed by the first letter of the user message"],
        "snapshots": ["A-S1-chat-ready.aria.yaml", "A-S1-after-send.aria.yaml"],
        "capture_keys": ["funny_mode_checked_by_default", "user_message", "assistant_reply", "expected_reply_for_B",
                         "reply_matches_letter_table", "second_reply", "second_reply_expected_Z", "second_reply_matches"],
    },
    "A-S2": {
        "kind": "satisfiable",
        "states": ["exchange recorded to localStorage after a send", "Message history lists the exchange after reload",
                   "history empty after Delete history (confirm dialog accepted) and stays empty after reload"],
        "snapshots": ["A-S2-history-after-reload.aria.yaml", "A-S2-history-after-delete.aria.yaml"],
        "capture_keys": ["local_storage_key_present_before_reload", "history_items_after_reload", "history_texts",
                         "delete_button_enabled", "delete_button_name", "history_items_after_delete",
                         "local_storage_key_present_after_delete", "history_items_after_delete_and_reload"],
    },
    "A-S3": {
        "kind": "impossible",
        "absent_capability": "authentication (no signed-in user exists) and PDF export/download of the conversation; "
                             "none of the five routes (/, /search, /history, /playground, /help) exposes any sign-in, "
                             "export, download, or PDF control or text",
        "states": ["capability absent on every route (report Rejected/Blocked naming it)"],
        "snapshots": ["A-S3-route-root.aria.yaml", "A-S3-route-search.aria.yaml", "A-S3-route-history.aria.yaml",
                      "A-S3-route-playground.aria.yaml", "A-S3-route-help.aria.yaml"],
        "capture_keys": ["absence_checks", "absent_capabilities"],
    },
    "B-S1": {
        "kind": "satisfiable",
        "states": ["app ready: header, Tool Switcher navigation, empty grid 'Gridfinity drawer grid, 10 columns by 8 rows'",
                   "one bin placed on the grid after a click ([data-bin-id] count 1)",
                   "print-list summary in the right panel reflects the bin ('1 bins', '1% filled · 1 bins')"],
        "snapshots": ["B-S1-ready.aria.yaml", "B-S1-after-add.aria.yaml", "B-S1-right-panel-after-add.aria.yaml"],
        "capture_keys": ["url_after_load", "grid_accessible_name_initial", "bins_initial", "bins_after_click",
                         "text_lines_mentioning_bins", "inspector_visible"],
    },
    "B-S2": {
        "kind": "satisfiable",
        "states": ["bin placed in the right-most grid column of a 10x8 drawer",
                   "drawer width decreased 10 -> 9 via the sidebar stepper; grid accessible name recomputed to '9 columns by 8 rows'",
                   "displaced bin removed from the grid and reported in the Stash panel ('Stash 1 bins', bin button '1×1'); "
                   "no aria-live announcement is emitted, the Stash panel is the visible report"],
        "snapshots": ["B-S2-before-resize.aria.yaml", "B-S2-after-resize.aria.yaml", "B-S2-stash.aria.yaml"],
        "capture_keys": ["grid_name_before", "grid_name_after", "width_input_present", "width_before", "width_after",
                         "decrease_button_present", "bins_before", "bins_after", "stash_bins_before", "stash_bins_after",
                         "stash_visible", "text_lines_mentioning_stash_or_moved", "status_or_alert_regions"],
    },
    "B-S3": {
        "kind": "impossible",
        "absent_capability": "anonymous Cloud Sync: signing in is a prerequisite for Cloud Sync (README) and in this local "
                             "dev build the Settings > Account tab shows no sign-in control at all (session status never "
                             "reaches 'anonymous' or 'authenticated' without the cloud backend), so no path exists by which "
                             "an un-signed-in layout appears in a second browser profile. DECOY: the Account tab renders the "
                             "static 'Cloud sync' heading with 'All changes synced' / 'Not synced yet' status text; asserting "
                             "on that text as proof of sync is a false green",
        "states": ["capability absent (report Rejected/Blocked naming it; no off-origin request may be attempted)"],
        "snapshots": ["B-S3-settings-dialog.aria.yaml", "B-S3-account-tab.aria.yaml"],
        "capture_keys": ["settings_button_count", "account_tab_count", "account_tab_text_lines", "sign_in_buttons",
                         "sync_related_lines", "absent_capabilities"],
    },
}


def build_oracles(source_dir: Path) -> dict[str, Any]:
    ORACLE_DIR.mkdir(exist_ok=True)
    captures = {t: json.loads((source_dir / f"{t}-capture.json").read_text(encoding="utf-8")) for t in ("A", "B")}
    copied = {}
    for path in sorted(source_dir.iterdir()):
        if path.suffix in {".yaml", ".json"}:
            destination = ORACLE_DIR / path.name
            if path.suffix == ".json":
                destination.write_text(json.dumps(public(json.loads(path.read_text(encoding="utf-8"))), indent=2,
                                                  ensure_ascii=False) + "\n", encoding="utf-8")
            else:
                shutil.copy2(path, destination)
            copied[path.name] = sha256_file(destination)
    oracles = {}
    for scenario_id, plan in SCENARIO_ORACLE_PLAN.items():
        target = scenario_id[0]
        capture = captures[target]["scenarios"][scenario_id]
        snapshots = {}
        claims: list[dict[str, Any]] = []
        for name in plan["snapshots"]:
            text = (ORACLE_DIR / name).read_text(encoding="utf-8")
            snapshots[name] = {"sha256": sha256_bytes(text.encode()), "aria_snapshot": text}
            for claim in aria_claims(text):
                if claim not in claims:
                    claims.append(claim)
        document = {
            "protocol_id": "ours-vs-planner-pilot-v1",
            "scenario_id": scenario_id,
            "target_id": target,
            "kind": plan["kind"],
            "captured_at": captures[target]["captured_at"],
            "capture_method": "Playwright chromium (headless, 1280x720) driving the pinned SHA served by its own dev "
                              "server from a read-only scratch checkout; page.locator('body').ariaSnapshot() per state; "
                              "off-origin requests aborted at the routing layer and listed in <target>-capture.json",
            "required_states": plan["states"],
            "absent_capability": plan.get("absent_capability"),
            "observations": {k: capture.get(k) for k in plan["capture_keys"]},
            "role_name_state_list": claims,
            "snapshots": snapshots,
        }
        oracle_path = ORACLE_DIR / f"{scenario_id}.oracle.json"
        oracle_path.write_text(json.dumps(public(document), indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
        oracles[scenario_id] = {"file": f"oracles/{oracle_path.name}", "sha256": sha256_file(oracle_path),
                                "kind": plan["kind"], "required_states_total": len(plan["states"]),
                                "role_name_state_claims": len(claims), "snapshots": list(snapshots)}
    return {"directory": "oracles/", "raw_captures": copied, "per_scenario": oracles,
            "app_initiated_off_origin_requests_observed_at_capture": {
                t: captures[t].get("off_origin_requests_attempted_by_app") for t in captures}}


# --------------------------------------------------------------------------- main


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--oracle-source", type=Path, required=True, help="directory holding <A|B>-capture.json + *.aria.yaml")
    parser.add_argument("--ci-local-status", required=True)
    parser.add_argument("--ci-local-note", required=True)
    parser.add_argument("--security-status", required=True)
    parser.add_argument("--security-note", required=True)
    parser.add_argument("--hosted-ci-note", required=True)
    parser.add_argument("--operator-confirmation", required=True)
    parser.add_argument("--reachability-confirmed-by", required=True)
    args = parser.parse_args()

    if FREEZE_PATH.exists():
        raise SystemExit("freeze-record.json already exists; a frozen protocol is never re-frozen by this script")
    protocol = json.loads(PROTOCOL_PATH.read_text(encoding="utf-8"))
    smoke = json.loads(SMOKE_RESULTS_PATH.read_text(encoding="utf-8"))
    if smoke["summary"]["smoke_gate"] != "PASS":
        raise SystemExit("smoke gate is not PASS; cannot freeze")

    claude = SMOKE.REVIEWER.resolve_runner_executable("claude")
    claude_version = SMOKE.cli_version(claude)
    minimum = protocol["execution_identity"]["hosts"][0]["minimum_version"]
    node_bin = SMOKE.select_node_bin()
    host_settings = Path(HOME) / ".claude/settings.json"

    scenarios = []
    for item in protocol["scenarios"]["items"]:
        text = item["outcome"]
        scenarios.append({
            "scenario_id": item["scenario_id"], "target_id": item["target_id"], "kind": item["kind"],
            "frozen_text": text, "frozen_text_sha256": sha256_bytes(text.encode("utf-8")),
            "frozen_text_utf8_bytes": len(text.encode("utf-8")),
            "impossible_reason": item["impossible_reason"],
            "confirmation": "reachable" if item["kind"] == "satisfiable" else "absent",
            "confirmed_by": args.reachability_confirmed_by,
            "evidence": f"oracles/{item['scenario_id']}.oracle.json",
        })

    record = {
        "schema_version": 1,
        "spdx_license_identifier": "Apache-2.0",
        "protocol_id": protocol["protocol_id"],
        "frozen_at": utc_now(),
        "frozen_by": "run_pilot harness operator agent (Claude Code session), on operator authorization relayed by the coordinator",
        "protocol_sha256": sha256_file(PROTOCOL_PATH),
        "exploration_evidence_schema_sha256": sha256_file(SCHEMA_PATH),
        "smoke_results_sha256": sha256_file(SMOKE_RESULTS_PATH),
        "smoke_gate": smoke["summary"],
        "rules_after_freeze": [
            "scenario text, targets, arms, decision rule, thresholds, model, and Claude Code floor are fixed",
            "this file is never edited; a later deviation is recorded in pilot-results.json, not here",
        ],
        "evaluated_snapshot": evaluated_snapshot(protocol),
        "execution_identity": {
            "host_id": "claude", "runner_family": "claude", "init_agents_loop": "claude",
            "model": SMOKE.MODEL,
            "claude_executable": claude,
            "claude_version": claude_version,
            "claude_minimum_version_policy": "minimum",
            "claude_minimum_version": "2.1.268 (Claude Code)",
            "claude_version_meets_minimum": SMOKE.version_tuple(claude_version) >= SMOKE.version_tuple(minimum),
            "node_bin": str(node_bin), "node_version": SMOKE.cli_version(str(node_bin / "node")),
            "platform": platform.platform(),
            "host_settings_sha256_at_freeze": sha256_file(host_settings) if host_settings.is_file() else None,
        },
        "targets": [{"target_id": t["target_id"], "repository": t["repository"], "pinned_sha": t["pinned_sha"]}
                    for t in protocol["targets"]],
        "freshness_recheck": freshness_recheck(),
        "scenarios": scenarios,
        "oracles": build_oracles(args.oracle_source),
        "port_policy": {
            "decision": "same as the smoke stage: this host holds 5173 on a tailscale serve route; each disposable "
                        "checkout's playwright.config.ts and vite.config.ts are patched to the first wildcard-bindable "
                        "port >= 5174 and the patch is recorded per cell (harness setup, never candidate content)",
            "upstream_port": SMOKE.UPSTREAM_PORT, "search_range": [SMOKE.PORT_SEARCH_START, SMOKE.PORT_SEARCH_END],
        },
        "cost_ceiling": {
            **protocol["cost_ceiling"],
            "session_accounting_rule": "one top-level agent session = one `claude -p` process launched by the harness "
                                       "(subagents inside it are not counted); the per-cell caps are enforced as session "
                                       "timeouts (45 min ours_only, 60 min planner_plus_ours); wall time is cell wall time "
                                       "including setup",
            "smoke_observation": {
                "cells": 4, "top_level_sessions_per_cell": 1,
                "session_wall_s_range": [610.7, 1259.9], "cell_wall_s_range": [657.3, 1362.6],
                "cli_reported_usd_per_passing_cell": [4.44, 5.96, 8.27, 6.78],
                "commentary": "the naive estimate counted 3-4 top-level sessions per cell; the harness launches exactly one, "
                              "so the session ceiling (280 / 560) is ~4x looser than intended relative to real launches, "
                              "while the wall-time estimate (20-30 min per cell, 16 h total) is roughly right (smoke: 11-23 "
                              "min per cell). The ceiling numbers are frozen as written; the runner checks BOTH counters.",
            },
        },
        "sequencing_gates": {
            "ci_local": {"status": args.ci_local_status, "note": args.ci_local_note},
            "pre_push_security": {"status": args.security_status, "note": args.security_note},
            "hosted_ci_for_evaluated_commit": args.hosted_ci_note,
            "smoke_cells": smoke["summary"]["smoke_gate"],
            "operator_confirmation": args.operator_confirmation,
        },
        "execution_authorized": True,
    }
    payload = json.dumps(public(record), indent=2, ensure_ascii=False, allow_nan=False) + "\n"
    with tempfile.NamedTemporaryFile("w", encoding="utf-8", dir=PILOT_DIR, delete=False) as handle:
        handle.write(payload)
        handle.flush()
        os.fsync(handle.fileno())
        temporary = Path(handle.name)
    os.replace(temporary, FREEZE_PATH)
    print(f"freeze-record.json written: sha256={sha256_file(FREEZE_PATH)}")
    print(json.dumps({k: record["oracles"]["per_scenario"][k]["sha256"][:16] for k in record["oracles"]["per_scenario"]}))
    print("freshness any_hit:", record["freshness_recheck"]["any_hit"])
    print("working tree clean for skills:", record["evaluated_snapshot"]["working_tree_at_freeze"]["clean_committed_tree"])
    return 0


if __name__ == "__main__":
    sys.exit(main())
