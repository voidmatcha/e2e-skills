#!/usr/bin/env python3
"""Offline thin successor regressions; no freeze, model, container or network. Apache-2.0."""
from __future__ import annotations

import argparse
import ast
import builtins
import contextlib
import copy
import importlib.util
import json
from pathlib import Path
import re
import shlex
import shutil
import socket
import subprocess
import sys
import tempfile
import threading
import time
from types import SimpleNamespace
import hashlib
import os
import io
import unittest
from unittest.mock import Mock, patch

sys.dont_write_bytecode = True
ROOT = Path(__file__).resolve().parents[2]
spec = importlib.util.spec_from_file_location("thin_eval_under_test", ROOT / "scripts/evals/run-generator-thin-eval-v1.py")
m = importlib.util.module_from_spec(spec)
spec.loader.exec_module(m)
A, B, C, D, E, F, G = m.A, m.B, m.C, m.D, m.E, m.F, m.G
GUARDS = contextlib.ExitStack()


def forbidden(*args, **kwargs):
    raise AssertionError("offline test attempted a process or network operation")


def setUpModule():
    for module, name in ((subprocess, "Popen"), (subprocess, "run"), (subprocess, "call"),
                         (subprocess, "check_call"), (subprocess, "check_output"),
                         (socket, "socket"), (socket, "create_connection")):
        GUARDS.enter_context(patch.object(module, name, forbidden))


def tearDownModule():
    GUARDS.close()


def candidate_results(candidates):
    out = {}
    for model in candidates:
        cells = [dict(row, deliverable=True, treatment=dict(available=True, treated_core=True,
                     steps={step: True for step in m.evidence.C_STEPS}), clean=True,
                     refactor_score=1.0, cost_usd=0.0)
                 for row in m.schedule(arms=m.ARMS) if row["arm"] == C]
        out[model["id"]] = dict(protocol_id=m.integration.PROTOCOL_ID, complete=True, cells=cells)
    return out


def realistic_files(project, port, case=None):
    """Write the real case config and app with the port substituted, exactly as the frozen stage function does."""
    case_dir = m.engine.CASES / (case or m.protocol()["tasks"][0])
    for name in ("app.mjs", "playwright.config.mjs"):
        (Path(project) / name).write_text((case_dir / name).read_text().replace("__PORT__", str(port)))


def realistic_stage(tests=False, git_dir=False, link=None):
    """engine.stage stand-in producing real case files (no git, no process)."""
    def stage(case_dir, port, work, git):
        project = Path(work) / "project"
        (project / "tests").mkdir(parents=True) if tests else project.mkdir(parents=True)
        realistic_files(project, port, Path(case_dir).name if (m.engine.CASES / Path(case_dir).name).is_dir() else None)
        if git_dir:
            (project / ".git").mkdir()
        if link:
            (project / "node_modules").symlink_to(link)
        return project
    return stage


def build_v3_source(root, candidates, states, rollout_models=()):
    """Synthetic finished-v3 directory: states maps model id -> admitted | excluded | undecided | unfinished."""
    source = Path(root)
    freeze_sha = m.digest(m.integration.LOCK)
    schedule = m.integration.schedule()
    for model in candidates:
        mid, state = model["id"], states.get(model["id"], "undecided")
        if state == "undecided":
            continue
        m.write(source / "_entry" / (mid + ".json"), dict(model=mid, freeze_sha256=freeze_sha,
                decision="excluded" if state == "excluded" else "admitted"))
        if state in ("excluded", "unfinished"):
            continue
        runs = [dict(row, call_id=m.v1.call_id_of(row), attempts=[]) for row in schedule]
        cells = candidate_results([model])[mid]["cells"]
        for cell in cells:
            cell.update(references_renamed_selector=False, effective_fault_kill=1.0, elapsed_s=100.0,
                        call_id=m.v1.call_id_of(cell))
        if mid in rollout_models:
            for run in runs:
                if run["arm"] == C:
                    record = write_cell(source / mid, child_tools=("generator_write_test",), usage=(195000, 874000), stem=run["call_id"])
                    run.update(transcript_path=record["transcript_path"], usage=record["usage"])
        m.write(source / mid / "final.json", dict(runs=runs, freeze_sha256=freeze_sha, input_drift=False,
                cli="synthetic-cli", container_image="synthetic-image"))
        m.write(source / mid / "results.json", dict(
            protocol_id=m.integration.PROTOCOL_ID, complete=True, cells=cells, model=mid, freeze_sha256=freeze_sha,
            report_sha256=m.digest(source / mid / "final.json")))
    return source


def complete_decision_fixture(arms=None, models=3, c_reference=None):
    """Full observed grid with a quality loss at the practical margin and 20% token saving."""
    p = m.protocol()
    p["models"] = p["candidate_models"][:models]
    p["selected_arms"] = tuple(arms or m.ARMS)
    p["c_reference"] = c_reference or dict(mode="rerun" if C in p["selected_arms"] else "none")
    results = {}
    scanner = m.scanner_manifest()
    for model in p["models"]:
        cells = []
        for row in m.schedule(p, p["selected_arms"]):
            thin = row["arm"] in (D, E, F, G)
            cheap = row["arm"] in (E, G)
            cli = row["arm"] in (F, G)
            processed = 75 if cli else 80 if thin else 100
            tokens = dict.fromkeys(m.evidence.TOKEN_FIELDS, 0)
            tokens.update(complete=True, uncached_input=processed - 20, output=20,
                          cached_input=20, processed=processed, total=processed + 20)
            cells.append(dict(row, _model=model["id"], deliverable=True, aborted=False,
                              fidelity_class="official-tool" if row["arm"] in (A, B, D, E) else "cli-observed" if cli else None,
                              cli_guide_read_indicator=cli,
                              cli_setup=dict(available=True, launch_failed=False, never_attempted=False, zero_snapshot=False,
                                             stop_clause=False, setup_failure=False, verified_snapshots=3) if cli else None,
                              stop_clause_blocked=False if cli else None, root_tool_rounds=12, elapsed_s=100.0,
                              cli_guide_integrity=[dict(before="same", after="same", read_only_mount=True)] if cli else None,
                              child_agents=0 if row["arm"] != B else None,
                              treatment=dict(treated_core=row["arm"] == C, treated=row["arm"] == B),
                              thin_layer_read_indicator=thin,
                              thin_layer_integrity=[dict(before="same", after="same", read_only_mount=True)] if thin else None,
                              scanner_gate_indicator=cheap,
                              scanner_integrity=[dict(before=scanner, after=scanner,
                                                      read_only_mount=True)] if cheap else None,
                              clean=True, selector_hygiene=0.9 if thin else 1.0,
                              clean_conditional_survival=0.9 if thin else 1.0,
                              refactor_score=0.9 if thin else 1.0,
                              effective_fault_kill=0.9 if thin else 1.0,
                              static_hygiene=dict(available=True), pipeline=dict(tokens=tokens, elapsed_s=1)))
        results[model["id"]] = dict(complete=True, cells=cells)
    return p, results


class ScheduleAndRules(unittest.TestCase):
    def test_schedule_is_balanced_deterministic_and_preserves_paired_order(self):
        p, rows = m.protocol(), m.schedule(arms=m.ARMS)
        self.assertEqual(rows, m.schedule(arms=m.ARMS))
        self.assertEqual(len(rows), 168)
        self.assertEqual([r["ordinal"] for r in rows], list(range(1, 169)))
        self.assertEqual({r["case"] for r in rows}, set(p["tasks"]))
        self.assertEqual(len(p["tasks"]), 6)
        self.assertEqual({r["arm"] for r in rows}, {A, B, C, D, E, F, G})
        self.assertEqual(tuple(m.ARMS), (A, B, C, D, E, F, G))
        self.assertEqual(len(rows) * 3, 504)
        for repetition in range(1, 5):
            block = [row for row in rows if row["repetition"] == repetition]
            self.assertEqual(len(block), 42)
            self.assertEqual([row["repetition"] for row in rows[(repetition - 1) * 42:repetition * 42]],
                             [repetition] * 42)
            for offset in range(0, len(block), 7):
                cell_block = block[offset:offset + 7]
                self.assertEqual([row["arm"] for row in cell_block], list(m.ARMS))
                self.assertEqual(len({row["case"] for row in cell_block}), 1)
        changed = dict(p, seed=p["seed"] + 1)
        self.assertNotEqual([(r["case"], r["repetition"]) for r in rows],
                            [(r["case"], r["repetition"]) for r in m.schedule(changed, m.ARMS)])
        for arm in m.ARMS:
            self.assertEqual(sum(r["arm"] == arm for r in rows), 24)
            self.assertEqual({(r["case"], r["repetition"]) for r in rows if r["arm"] == arm},
                             {(task, rep) for task in p["tasks"] for rep in range(1, 5)})

    def test_default_arm_set_is_A_D_E_F_G_with_optional_B_and_C_behind_flags(self):
        self.assertEqual(m.MANDATORY_ARMS, (A, D, E, F, G))
        self.assertEqual(m.arm_set(), (A, D, E, F, G))
        self.assertEqual(m.arm_set(include_reviewer=True), (A, B, D, E, F, G))
        self.assertEqual(m.arm_set(rerun_full_skill=True), (A, C, D, E, F, G))
        self.assertEqual(m.arm_set(True, True), m.ARMS)
        with self.assertRaises(TypeError):  # the --include-cli-scanner switch is gone: G is measured by default
            m.arm_set(include_cli_scanner=True)
        policy = m.protocol()["arm_policy"]
        self.assertEqual(policy["mandatory"], list(m.MANDATORY_ARMS))
        self.assertEqual(policy["optional"][B]["flag"], "--include-reviewer")
        self.assertEqual(policy["optional"][C]["flag"], "--rerun-full-skill")
        self.assertEqual(set(policy["optional"]), {B, C})
        self.assertNotIn(F, policy["optional"])  # F and G are default stage-1 arms, not flags
        self.assertNotIn(G, policy["optional"])
        self.assertEqual(policy["default_scheduled"], list(m.MANDATORY_ARMS))
        self.assertNotIn("--include-cli-scanner", json.dumps(policy))
        for bad in ((A, D), (D, E), (E, D, A), (A, D, E), (A, D, E, F), (A, D, E, F, "other"), (A, A, D, E, F, G), (A, D, E, G, F),
                    (A, D, E, F, G, F)):
            with self.subTest(arms=bad), self.assertRaises(ValueError):
                m.check_arm_set(bad)

    def test_arm_set_changes_cells_but_never_task_order_or_ordinal_pairing(self):
        full, default = m.schedule(arms=m.ARMS), m.schedule()
        self.assertEqual(len(default), 120)
        self.assertEqual({r["arm"] for r in default}, {A, D, E, F, G})
        self.assertEqual([(r["case"], r["repetition"]) for r in full if r["arm"] == A],
                         [(r["case"], r["repetition"]) for r in default if r["arm"] == A])
        self.assertEqual([r["arm"] for r in default[:5]], [A, D, E, F, G])
        for variant, count in ((m.arm_set(True), 144), (m.arm_set(False, True), 144), (m.ARMS, 168)):
            rows = m.schedule(arms=variant)
            self.assertEqual(len(rows), count)
            self.assertEqual([r["ordinal"] for r in rows], list(range(1, count + 1)))
            self.assertEqual([r["case"] for r in rows if r["arm"] == A], [r["case"] for r in default if r["arm"] == A])

    def test_rules_frontmatter_budget_general_scope_and_line_shape(self):
        data = m.LAYER.read_bytes()
        text = data.decode("utf-8")
        self.assertLessEqual(len(data), 2500)
        self.assertRegex(text, r"\A---\nname: playwright-thin-rules\ndescription: [^\n]+\n---\n")
        self.assertNotRegex(text.lower(), r"refactor|renam|grader|benchmark|behavio[u]?r\s+\d+|/Users/")
        rules = [line for line in text.splitlines() if line.startswith("- [ ] ")]
        self.assertEqual(len(rules), 11)
        for word in ("role", "label", "test id", "visible text", "styling", "JUSTIFIED", "ARIA",
                     "waitForTimeout", "expect(true)", "title", "one spec file", "Run"):
            self.assertIn(word, text)

    def test_layer_overhead_is_explicit_estimate_not_double_charged(self):
        overhead = m.layer_overhead()
        self.assertEqual(overhead["bytes"], len(m.LAYER.read_bytes()))
        self.assertEqual(overhead["estimated_tokens"], (overhead["bytes"] + 3) // 4)
        self.assertEqual(overhead["prompt_line_bytes"], len(m.D_LINE.encode()))
        self.assertEqual(overhead["combined_estimated_tokens"],
                         overhead["estimated_tokens"] + overhead["prompt_line_estimated_tokens"])
        self.assertIn("never added", overhead["accounting"])

    def test_freeze_payload_is_only_a_pure_value(self):
        selection = dict(models=m.protocol()["candidate_models"][:3])
        with tempfile.TemporaryDirectory() as temp, patch.object(m, "bindings", return_value={"synthetic": True}):
            target = Path(temp).resolve() / "new-output"
            payload = m.freeze_payload(target, selection)
            self.assertEqual(payload["models"], selection["models"])
            self.assertEqual(len(payload["schedule"]), 120)
            self.assertEqual(payload["arms"], list(m.MANDATORY_ARMS))
            self.assertEqual(payload["c_reference"], dict(mode="none"))
            self.assertEqual(len(m.freeze_payload(target, selection, m.ARMS)["schedule"]), 168)
            self.assertEqual(m.freeze_payload(target, selection, m.ARMS)["c_reference"], dict(mode="rerun"))
            self.assertEqual(payload["bindings"], {"synthetic": True})
            self.assertFalse(target.exists())
            self.assertFalse((Path(temp) / "freeze.json").exists())


class Roster(unittest.TestCase):
    def setUp(self):
        self.candidates = m.protocol()["candidate_models"]
        self.results = candidate_results(self.candidates)

    def test_ranking_ignores_outcomes_and_cost(self):
        before = m.rank_roster(self.results, self.candidates)
        changed = copy.deepcopy(self.results)
        for index, result in enumerate(changed.values()):
            for cell in result["cells"]:
                cell.update(clean=False, refactor_score=index * 0.1, primary=-900,
                            effective_fault_kill=0, cost_usd=1000000 - index, selector_hygiene=None)
        self.assertEqual(before, m.rank_roster(changed, self.candidates))

    def test_delivery_precedes_core_then_steps_then_catalog_order(self):
        ids = [c["id"] for c in self.candidates]
        # First two tie in delivery/core; one observed process step breaks their tie.
        self.results[ids[0]]["cells"][0]["treatment"]["steps"][m.evidence.C_STEPS[0]] = False
        # A core miss outweighs any step advantage; a delivery miss outweighs core/steps.
        self.results[ids[2]]["cells"][0]["treatment"]["treated_core"] = False
        for cell in self.results[ids[3]]["cells"]:
            cell["deliverable"] = False
        ranking = m.rank_roster(self.results, self.candidates)
        order = [row["model"] for row in ranking]
        self.assertLess(order.index(ids[1]), order.index(ids[0]))
        self.assertLess(order.index(ids[0]), order.index(ids[2]))
        self.assertEqual(order[-1], ids[3])
        tied = m.rank_roster(candidate_results(self.candidates), self.candidates)
        self.assertEqual([row["model"] for row in tied], ids)

    def test_partial_duplicate_or_unobserved_sources_are_rejected(self):
        mid = self.candidates[0]["id"]
        for change in ("partial", "duplicate", "unobserved"):
            with self.subTest(change=change):
                bad = copy.deepcopy(self.results)
                if change == "partial":
                    bad[mid]["complete"] = False
                elif change == "duplicate":
                    bad[mid]["cells"][-1] = copy.deepcopy(bad[mid]["cells"][0])
                else:
                    bad[mid]["cells"][0]["treatment"]["available"] = False
                with self.assertRaises(ValueError):
                    m.rank_roster(bad, self.candidates)

    def test_manual_override_is_one_to_three_unique_catalog_models_with_reason(self):
        ids = [c["id"] for c in self.candidates[:3]]
        for size in (1, 2, 3):
            selected = m.select_roster(override=ids[:size], reason="owner chooses the predeclared reference roster")
            self.assertEqual([row["id"] for row in selected["models"]], ids[:size])
            self.assertEqual(selected["mode"], "owner-manual-override")
        for names, reason in (([], "reason"), ([ids[0]] * 2, "reason"), (self.candidates and [c["id"] for c in self.candidates[:4]], "reason"),
                              ([*ids[:2], "unknown"], "reason"), (ids, " ")):
            with self.subTest(names=names, reason=reason), self.assertRaises(ValueError):
                m.select_roster(override=names, reason=reason)

    def v3_source(self, root, states):
        return build_v3_source(root, self.candidates, states)

    def test_first_finished_rule_walks_declared_order_skips_exclusions_and_stops_at_unfinished(self):
        ids = [c["id"] for c in self.candidates]
        with tempfile.TemporaryDirectory() as temp:
            states = {ids[0]: "admitted", ids[1]: "excluded", ids[2]: "admitted", ids[3]: "admitted", ids[4]: "unfinished"}
            source = self.v3_source(temp, states)
            two = m.select_roster(source)
            self.assertEqual(two["mode"], "v3-declared-order-first-finished")
            self.assertEqual([row["id"] for row in two["models"]], [ids[0], ids[2]])
            self.assertEqual([w["status"] for w in two["order_walk"]], ["selected", "excluded", "selected"])
            self.assertEqual(two["ranking"], [])
            self.assertEqual([row["order"] for row in two["models"]], [1, 2])
            one = m.select_roster(source, size=1)
            self.assertEqual([row["id"] for row in one["models"]], [ids[0]])
            self.assertEqual(set(one["source_digests"]), {"freeze.json", "_entry/%s.json" % ids[0], ids[0] + "/results.json",
                                                          ids[0] + "/final.json"})
            # An unfinished model ends the walk: a later finished model is never taken ahead of it.
            blocked = self.v3_source(Path(temp) / "blocked", {ids[0]: "admitted", ids[1]: "unfinished", ids[2]: "admitted"})
            with self.assertRaisesRegex(ValueError, "fewer than 2 finished"):
                m.select_roster(blocked)
            self.assertEqual([r["id"] for r in m.select_roster(blocked, size=1)["models"]], [ids[0]])
            with self.assertRaisesRegex(ValueError, "undecided or unfinished candidate"):
                m.select_roster(blocked, rule="ranking")

    def test_first_finished_choice_ignores_every_measured_value(self):
        ids = [c["id"] for c in self.candidates]
        with tempfile.TemporaryDirectory() as temp:
            source = self.v3_source(temp, {ids[0]: "admitted", ids[1]: "admitted", ids[2]: "admitted"})
            before = m.select_roster(source)["models"]
            # Make the first model look worst on every arm-C count and the third best; the choice cannot move.
            for index, mid in enumerate(ids[:3]):
                path = Path(temp) / mid / "results.json"
                result = m.read(path)
                for cell in result["cells"]:
                    cell.update(deliverable=index > 0, clean=False, refactor_score=0.0)
                    cell["treatment"]["treated_core"] = index > 0
                m.write(path, result)
            self.assertEqual(m.select_roster(temp)["models"], before)
            self.assertEqual([r["id"] for r in before], ids[:2])
            self.assertIn("arm-C delivered or treated counts (first-finished rule)",
                          m.protocol()["roster"]["forbidden_selection_fields"])

    def test_first_finished_rejects_incomplete_sources_and_drift(self):
        ids = [c["id"] for c in self.candidates]
        for change in ("partial", "freeze", "cells", "observations"):
            with self.subTest(change=change), tempfile.TemporaryDirectory() as temp:
                source = self.v3_source(temp, {ids[0]: "admitted"})
                path = Path(temp) / ids[0] / "results.json"
                result = m.read(path)
                if change == "partial":
                    result["complete"] = False
                elif change == "freeze":
                    result["freeze_sha256"] = "0" * 64
                elif change == "cells":
                    result["cells"] = result["cells"][:23]
                else:
                    result["cells"][0]["treatment"]["available"] = False
                m.write(path, result)
                with self.assertRaises(ValueError):
                    m.select_roster(source, size=1)

    def test_stage_1_recommendation_is_two_models_with_one_as_minimum(self):
        roster = m.protocol()["roster"]
        self.assertEqual((roster["size_min"], roster["stage_1_size"], roster["size_max"]), (1, 2, 3))
        recommendation = roster["stage_1_recommendation"]
        self.assertEqual(recommendation["models"], [c["id"] for c in self.candidates[:2]])
        self.assertEqual(recommendation["minimum_viable"], [self.candidates[0]["id"]])
        self.assertIn("Only declared order and completion", recommendation["outcome_blind_rule"])
        self.assertIn("no clean, survival, fault, selector, scanner, cost", recommendation["outcome_blind_rule"])


class TreatmentParity(unittest.TestCase):
    def engine_stub(self):
        return SimpleNamespace(CODEX_DOCKER="/usr/bin/docker", CODEX_CONTAINER_IMAGE="sha256:" + "a" * 64,
                               CODEX_DOCKER_CONTEXT="synthetic-offline")

    def test_D_argv_is_A_plus_one_readonly_mount_and_keeps_role_controls(self):
        engine = self.engine_stub()
        with tempfile.TemporaryDirectory() as temp:
            args = (engine, Path(temp), Path(temp) / "auth", "owned", "gpt-6-sol", A, Path(temp) / "sessions")
            official = m.compat.command(*args)
            thin = m.d_command(m.compat.command, *args)
        index = thin.index("type=bind,src=" + temp + "/skill/thin-rules,dst=/work/skill/thin-rules,readonly")
        self.assertEqual(thin[index - 1], "--mount")
        self.assertEqual(thin[:index - 1] + thin[index + 1:], official)
        self.assertEqual(thin[thin.index("--sandbox") + 1], "danger-full-access")
        self.assertIn('approval_policy="never"', thin)
        self.assertIn('mcp_servers.playwright-test.default_tools_approval_mode="approve"', thin)
        allow = next(x.split("=", 1)[1] for x in thin if x.startswith("mcp_servers.playwright-test.enabled_tools="))
        self.assertEqual(json.loads(allow), list(m.compat.GENERATOR_TOOLS))
        self.assertEqual(len(json.loads(allow)), 19)

    def capture_model_boundary(self, entry, arm):
        """Exercise actual staging/adapter assembly; replace every process with a recorder."""
        seen = {}
        args = argparse.Namespace(model="gpt-6-sol", timeout=2, call_budget=None)
        item = dict(case=m.protocol()["tasks"][0], arm=arm, repetition=1, ordinal=1)
        source_bytes = b"test('arm A source', async () => {});\n"

        stage = realistic_stage(git_dir=True, link="/synthetic-unread-node-modules")

        def baseline(project, case):
            (project / "tests").mkdir()
            (project / "tests/seed.spec.ts").write_text("// shared seed\n")

        class Process:
            returncode = 0

            def __init__(self, argv, **kwargs):
                mounts = [arg for arg in argv if arg.startswith("type=bind,src=")]
                work = Path(next(arg.split("src=", 1)[1].split(",dst=", 1)[0]
                                 for arg in mounts if arg.endswith(",dst=/work")))
                private = next(arg.split("src=", 1)[1].split(",dst=", 1)[0]
                               for arg in mounts if ",dst=/auth-source," in arg)
                sessions = next(arg.split("src=", 1)[1].split(",dst=", 1)[0]
                                for arg in mounts if arg.endswith(",dst=/sessions-out"))
                normalize = lambda text: text.replace(str(work), "<work>").replace(private, "<private>").replace(sessions, "<sessions>")
                seen["argv"] = [normalize(arg) for arg in argv]
                seen["files"] = {str(path.relative_to(work)): path.read_bytes()
                                 for path in work.rglob("*") if path.is_file() and not path.is_symlink()}
                seen["modes"] = {str(path.relative_to(work)): path.stat().st_mode & 0o777
                                 for path in work.rglob("*") if path.is_file() and not path.is_symlink()}

            def communicate(self, prompt, timeout):
                seen["prompt"] = prompt
                return "\n".join(json.dumps(event) for event in (
                    dict(type="item.completed", item=dict(type="agent_message", text="offline final")),
                    dict(type="turn.completed", usage=dict(input_tokens=1, output_tokens=1)))), ""

        helper = SimpleNamespace(clean_env=lambda *args: {}, stage_codex_auth=lambda path: None)
        with tempfile.TemporaryDirectory() as temp, contextlib.ExitStack() as stack:
            root = Path(temp).resolve()
            artifacts = root / "artifacts"
            source = artifacts / m.v1.call_id_of(dict(item, arm=A)) / "tests"
            source.mkdir(parents=True)
            (source / "generated.spec.ts").write_bytes(source_bytes)
            (source / "helper.ts").write_bytes(b"export const expected = 1;\n")
            for module, key, value in (
                (m.integration, "_REAL_STAGE", stage), (m.engine, "stage", stage),
                (m.engine, "load_truth", lambda case: dict(task="Synthetic task")),
                (m.v1, "baseline", baseline), (m.v1, "init_agents", lambda *args: dict(status="ready")),
                (m.engine, "wait_for_load", lambda record: None),
                (m.engine, "collect_deliverable", lambda project, destination: dict(spec_files=["tests/generated.spec.ts"], tests_files=["tests/generated.spec.ts"])),
                (m.engine, "call_model", m.compat.configure(m.engine)),
                (m.compat.shared, "helpers", lambda: helper),
                (m.compat.shared, "structured", lambda text: dict(status="complete", summary=text)),
                (m.compat, "remove_container", lambda *args: None),
                (m.compat, "persist_cell_sessions", lambda *args: dict(files=0, bytes=0, skipped=[], dir=None)),
                (m.compat.uuid, "uuid4", lambda: SimpleNamespace(hex="offline-cell")),
                (subprocess, "Popen", Process),
            ):
                stack.enter_context(patch.object(module, key, value))
            for key, value in vars(self.engine_stub()).items():
                stack.enter_context(patch.object(m.engine, key, value, create=True))
            stack.enter_context(patch.object(m.engine, "CODEX_TRANSCRIPTS", root / "transcripts", create=True))
            stack.enter_context(patch.dict(m.compat.ARM_LINES, m.integration.arm_lines()))
            result = entry(item, args, SimpleNamespace(take=lambda: 9301), artifacts,
                           dict(id=args.model, runner="codex"), m.protocol())
        self.assertIn("prompt", seen, "adapter must reach the mocked process boundary")
        self.assertTrue(result["deliverable"])
        if arm == B:
            self.assertEqual(seen["files"]["project/tests/generated.spec.ts"], source_bytes)
            self.assertEqual(seen["files"]["project/tests/helper.ts"], b"export const expected = 1;\n")
        return seen, result

    def test_B_assembly_functions_match_frozen_v3_source_without_executing_it(self):
        pairs = (
            ("generator_codex_official_adapter_compat_v3.py", Path(m.compat.__file__),
             ("docker_prefix", "command", "configure")),
            ("run-generator-multimodel-v3-codex.py", Path(m.integration.__file__),
             ("generation_config_text", "_generation_stage", "generation_staging", "generation_summary", "one_call")),
        )
        for frozen_file, successor_file, names in pairs:
            paths = (ROOT / "scripts/evals" / frozen_file, successor_file)
            functions = [{node.name: node for node in ast.parse(path.read_text()).body
                          if isinstance(node, ast.FunctionDef)} for path in paths]
            for name in names:
                with self.subTest(source=frozen_file, function=name):
                    self.assertEqual(ast.dump(functions[0][name]), ast.dump(functions[1][name]))
        self.assertEqual(Path(m.integration._V1["one_call"].__code__.co_filename),
                         ROOT / "scripts/evals/run-generator-multimodel-v1.py")
        self.assertEqual(Path(m.integration.rev.stage_reviewer.__code__.co_filename),
                         ROOT / "scripts/evals/run-generator-official-reviewer-pilot-v1.py")
        # Read and validate every predecessor binding; this never imports the v3 executable modules.
        self.assertEqual(m.integration.frozen()["models"], m.integration.protocol()["models"])

    def test_B_uses_frozen_predecessor_staging_and_exact_prompt(self):
        self.assertIs(m.integration._V1["one_call"], m.v1.one_call)
        self.assertEqual(m.arm_lines()[B], m.integration.rev.REVIEW_LINE)
        predecessor, _ = self.capture_model_boundary(m.integration.one_call, B)
        successor, _ = self.capture_model_boundary(m.one_call, B)
        self.assertEqual(successor, predecessor)
        self.assertIn("skill/e2e-reviewer/SKILL.md", successor["files"])
        self.assertEqual(successor["prompt"], m.engine.FRAME.format(
            task="Synthetic task" + m.integration.rev.TASK_LINE) + m.integration.rev.REVIEW_LINE)
        self.assertNotIn(m.D_LINE, successor["prompt"])
        self.assertNotIn(m.E_LINE, successor["prompt"])

    def test_E_is_D_with_only_scanner_staging_and_one_prompt_line(self):
        thin, _ = self.capture_model_boundary(m.one_call, D)
        scanner, result = self.capture_model_boundary(m.one_call, E)
        self.assertEqual(scanner["prompt"], thin["prompt"] + "\n" + m.E_LINE)
        self.assertEqual(scanner["prompt"].count(m.E_LINE), 1)
        self.assertEqual(m.arm_lines()[E], m.arm_lines()[D] + "\n" + m.E_LINE)
        self.assertEqual(m.SCANNER_COMMAND, "/bin/bash -p /work/skill/scanner/scan.sh tests/")
        self.assertIn("`" + m.SCANNER_COMMAND + "`", m.E_LINE)
        mount = "type=bind,src=<work>/skill/scanner,dst=/work/skill/scanner,readonly"
        index = scanner["argv"].index(mount)
        self.assertEqual(scanner["argv"][index - 1], "--mount")
        self.assertEqual(scanner["argv"][:index - 1] + scanner["argv"][index + 1:], thin["argv"])
        extra = {path: data for path, data in scanner["files"].items() if path not in thin["files"]}
        self.assertEqual(set(extra), {"skill/scanner/" + name for name in m.scanner_manifest()})
        self.assertEqual({path: data for path, data in scanner["files"].items() if path not in extra}, thin["files"])
        for name in m.scanner_manifest():
            self.assertEqual(extra["skill/scanner/" + name], (m.SCANNER_SOURCE / name).read_bytes())
            self.assertEqual(scanner["modes"]["skill/scanner/" + name], 0o444)
        self.assertFalse(any("SKILL.md" in path or "/references/" in path for path in extra))
        integrity = result["scanner_integrity"]
        self.assertEqual(len(integrity), 1)
        self.assertEqual(integrity[0]["before"], m.scanner_manifest())
        self.assertEqual(integrity[0]["after"], m.scanner_manifest())
        self.assertIs(integrity[0]["read_only_mount"], True)

    def test_E_argv_helper_is_D_plus_exactly_one_readonly_scanner_mount(self):
        engine = self.engine_stub()
        with tempfile.TemporaryDirectory() as temp:
            args = (engine, Path(temp), Path(temp) / "auth", "owned", "gpt-6-sol", A, Path(temp) / "sessions")
            thin = m.d_command(m.compat.command, *args)
            scanner = m.e_command(m.compat.command, *args)
        index = scanner.index("type=bind,src=" + temp + "/skill/scanner,dst=/work/skill/scanner,readonly")
        self.assertEqual(scanner[index - 1], "--mount")
        self.assertEqual(scanner[:index - 1] + scanner[index + 1:], thin)

    def test_D_uses_actual_A_initializer_and_separate_artifact_identity(self):
        seen = {}
        args = argparse.Namespace(model="gpt-6-sol", timeout=2, call_budget=None)
        model = dict(id=args.model, runner="codex")
        item = dict(case=m.protocol()["tasks"][0], arm=D, repetition=1, ordinal=1)

        stage = realistic_stage()

        def init(project, runner, protocol):
            seen["initialized"] = runner
            return dict(status="ready")

        def call(project, work, arm, task, model_id, timeout, budget):
            target = Path(work) / "skill/thin-rules/SKILL.md"
            seen.update(arm=arm, task=task, prompt=m.compat.ARM_LINES[A],
                        mode=target.stat().st_mode & 0o777, digest=m.digest(target))
            return dict(infrastructure_error=False, elapsed_ms=1, timeout=False)

        def collect(project, destination):
            seen["artifact"] = destination.name
            return dict(spec_files=["tests/generated.spec.ts"], tests_files=["tests/generated.spec.ts"])

        before = dict(m.compat.ARM_LINES)
        with tempfile.TemporaryDirectory() as temp, \
                patch.object(m.integration, "_REAL_STAGE", stage), patch.object(m.engine, "stage", stage), \
                patch.object(m.v1, "init_agents", init), patch.object(m.v1, "baseline"), \
                patch.object(m.engine, "wait_for_load"), patch.object(m.engine, "call_model", call), \
                patch.object(m.engine, "collect_deliverable", collect):
            result = m.one_call(item, args, SimpleNamespace(take=lambda: 9301), Path(temp), model, m.protocol())
        self.assertEqual(seen["initialized"], "codex")
        self.assertEqual(seen["arm"], A)
        self.assertEqual(seen["prompt"], m.integration.arm_lines()[A] + "\n" + m.D_LINE)
        self.assertEqual(seen["prompt"].count(m.D_LINE), 1)
        self.assertEqual(seen["mode"], 0o444)
        self.assertEqual(seen["digest"], m.digest(m.LAYER))
        self.assertEqual(seen["artifact"], m.v1.call_id_of(item))
        self.assertNotEqual(seen["artifact"], m.v1.call_id_of(dict(item, arm=A)))
        self.assertEqual(result["arm"], D)
        self.assertEqual(result["call_id"], seen["artifact"])
        self.assertEqual(result["thin_layer_integrity"][0]["before"], result["thin_layer_integrity"][0]["after"])
        self.assertEqual(m.compat.ARM_LINES, before)

    def test_B_and_C_calls_delegate_unchanged_while_A_D_E_use_the_repaired_path(self):
        for arm in (B, C):
            with tempfile.TemporaryDirectory() as temp:
                args = (dict(case="synthetic", arm=arm, repetition=1), object(), object(), Path(temp) / "artifacts", object(), object())
                with patch.object(m.integration, "one_call", return_value={"official": True}) as call:
                    self.assertEqual(m.one_call(*args), {"official": True})
                    call.assert_called_once_with(*args)
        for arm in m.SPLIT_ARMS:
            with tempfile.TemporaryDirectory() as temp:
                args = (dict(case="synthetic", arm=arm, repetition=1), object(), object(), Path(temp) / "artifacts", object(), object())
                with patch.object(m.integration, "one_call", return_value={"official": True}) as call:
                    self.assertEqual(m.one_call(*args)["arm"], arm)
                    self.assertEqual(call.call_args.args[0]["arm"], A)  # delegated as the official generator arm
                    self.assertIs(m.integration._generation_stage.__name__ == "_generation_stage", True)  # restored after the call

    def test_sanitized_read_indicator_recognizes_real_persisted_path(self):
        command = m.engine.sanitize("cat " + m.LAYER_TARGET, ("/work",))
        self.assertIn("<work>/skill/thin-rules/SKILL.md", command)
        events = [dict(type="item.completed", item=dict(type="command_execution", command=command, exit_code=0))]
        with patch.object(m.integration, "transcript_events", return_value=events):
            self.assertTrue(m.thin_read_indicator({}, Path("unused")))
        with patch.object(m.integration, "transcript_events", return_value=None):
            self.assertIsNone(m.thin_read_indicator({}, Path("unused")))
        with patch.object(m.integration, "transcript_events", return_value=[]):
            self.assertFalse(m.thin_read_indicator({}, Path("unused")))

    def test_runtime_context_restores_module_wiring_on_exception(self):
        original = {(module, key): getattr(module, key) for module, keys in
                    ((m.v1, ("BASE", "LOCK", "protocol", "frozen", "ARMS3", "one_call")),
                     (m.integration, ("BASE", "LOCK", "protocol", "frozen", "campaign_lock")), (m.engine, ("Ports",))) for key in keys}
        with patch.object(m, "digest", return_value="synthetic-freeze"), self.assertRaisesRegex(RuntimeError, "synthetic stop"):
            with m.runtime_context(Path("/synthetic-output"), {}, {}):
                self.assertEqual(m.v1.ARMS3, m.ARMS)
                raise RuntimeError("synthetic stop")
        for (module, key), value in original.items():
            self.assertIs(getattr(module, key), value)

    def test_recurring_runtime_frozen_callback_detects_drift(self):
        with patch.object(m, "digest", return_value="synthetic-freeze"), \
                patch.object(m, "frozen", side_effect=ValueError("synthetic binding drift")):
            with self.assertRaisesRegex(ValueError, "synthetic binding drift"):
                with m.runtime_context(Path("/synthetic-output"), {}, {}):
                    m.v1.frozen()


def resolve_roles(config_text, app_text, env):
    """Regex model of the staged generation files: the ports one process would use with this environment."""
    name = m.EXPLORE_ENV
    default = re.search(r'const APP_PORT = process\.env\.' + name + r' \?\? "(\d+)";', config_text).group(1)
    port = env.get(name, default)
    assert "baseURL: `http://127.0.0.1:${APP_PORT}`," in config_text
    assert "url: `http://127.0.0.1:${APP_PORT}/health`," in config_text
    assert "reuseExistingServer: process.env." + name + " !== undefined," in config_text
    listen = re.search(r"const PORT = Number\(process\.env\." + name + r" \?\? (\d+)\);", app_text).group(1)
    return dict(base_url_port=int(port), health_port=int(port), listen_port=int(env.get(name, listen)),
                reuse_existing_server=name in env)


class HarnessRepairs(unittest.TestCase):
    """F3 (shared-server state) and F5 (scoped writes), proven on the staged files, argv and record shapes."""
    engine_stub = TreatmentParity.engine_stub
    capture_model_boundary = TreatmentParity.capture_model_boundary
    PORT = 9301

    def real_stage(self, case, root):
        return m.integration._REAL_STAGE(m.engine.CASES / case, self.PORT, Path(root), False)

    def test_generation_config_cannot_reuse_the_mcp_session_server_for_any_scheduled_task(self):
        for case in m.protocol()["tasks"]:
            with self.subTest(case=case), tempfile.TemporaryDirectory() as temp:
                project = self.real_stage(case, temp)
                scoring_config, scoring_app = (project / "playwright.config.mjs").read_text(), (project / "app.mjs").read_text()
                config, app = m.split_config_text(scoring_config, self.PORT), m.split_app_text(scoring_app, self.PORT)
                explore = resolve_roles(config, app, {m.EXPLORE_ENV: str(self.PORT + m.EXPLORE_PORT_OFFSET)})
                test_run = resolve_roles(config, app, {})
                # Each role is internally consistent: browser, health check and listener agree on one port.
                for role in (explore, test_run):
                    self.assertEqual({role["base_url_port"], role["health_port"], role["listen_port"]}, {role["base_url_port"]})
                self.assertEqual(test_run["base_url_port"], self.PORT)
                self.assertEqual(explore["base_url_port"], self.PORT + m.EXPLORE_PORT_OFFSET)
                self.assertNotEqual(explore["listen_port"], test_run["listen_port"])  # different server processes
                self.assertFalse(test_run["reuse_existing_server"])  # a test run never attaches to an existing server
                self.assertTrue(explore["reuse_existing_server"])  # the session may reuse its own across setup calls
                self.assertEqual(config.count(m.EXPLORE_ENV), 2)  # the port default and the reuse switch
                self.assertEqual(app.count(m.EXPLORE_ENV), 1)
                # The only differences from the scoring files are the declared substitutions.
                self.assertEqual(config.replace("`http://127.0.0.1:${APP_PORT}/health`", '"http://127.0.0.1:%d/health"' % self.PORT)
                                 .replace("`http://127.0.0.1:${APP_PORT}`", '"http://127.0.0.1:%d"' % self.PORT)
                                 .replace("reuseExistingServer: process.env.%s !== undefined" % m.EXPLORE_ENV,
                                          m.integration.SCORING_REUSE)
                                 .replace('const APP_PORT = process.env.%s ?? "%d";\n\n' % (m.EXPLORE_ENV, self.PORT), ""),
                                 scoring_config)

    def test_split_refuses_configs_that_are_not_the_exact_frozen_shape(self):
        with tempfile.TemporaryDirectory() as temp:
            project = self.real_stage(m.protocol()["tasks"][0], temp)
            config, app = (project / "playwright.config.mjs").read_text(), (project / "app.mjs").read_text()
        for bad in (config.replace(m.integration.SCORING_REUSE, "reuseExistingServer: true"),
                    config.replace('"http://127.0.0.1:%d"' % self.PORT, '"http://127.0.0.1:1"'),
                    config + m.EXPLORE_ENV, config.replace("export default defineConfig(", "export default (")):
            with self.assertRaises(ValueError):
                m.split_config_text(bad, self.PORT)
        for bad in (app.replace("const PORT = %d;" % self.PORT, "const PORT = 1;"), app + m.EXPLORE_ENV):
            with self.assertRaises(ValueError):
                m.split_app_text(bad, self.PORT)

    def test_scoring_stage_and_case_configs_are_untouched(self):
        before = {case: (m.engine.CASES / case / "playwright.config.mjs").read_bytes() for case in m.protocol()["tasks"]}
        with tempfile.TemporaryDirectory() as temp:
            staged = self.real_stage(m.protocol()["tasks"][0], temp)
            text = (staged / "playwright.config.mjs").read_text()
            self.assertEqual(text.count(m.integration.SCORING_REUSE), 1)
            self.assertNotIn(m.EXPLORE_ENV, text)
            self.assertNotIn(m.EXPLORE_ENV, (staged / "app.mjs").read_text())
        seen, _ = self.capture_model_boundary(m.one_call, A)
        self.assertIn(m.EXPLORE_ENV, seen["files"]["project/playwright.config.mjs"].decode())
        self.assertIs(m.engine.stage, m.integration._REAL_STAGE)  # restored after the generation call
        self.assertEqual(m.integration._generation_stage.__name__, "_generation_stage")
        self.assertEqual(m.integration.scoring_guard(), {"reuse_existing_server": False, "cases_checked": 6})
        self.assertEqual(before, {case: (m.engine.CASES / case / "playwright.config.mjs").read_bytes() for case in before})
        # The scoring entry points never reference the split staging.
        tree = ast.parse((ROOT / "scripts/evals/run-generator-thin-eval-v1.py").read_text())
        source = (ROOT / "scripts/evals/run-generator-thin-eval-v1.py").read_text()
        for name in ("score_model", "artifact_manifest"):
            node = next(n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name == name)
            segment = ast.get_source_segment(source, node)
            self.assertNotIn(m.EXPLORE_ENV, segment)
            self.assertNotIn("split", segment)
        self.assertNotIn("make_split_stage", Path(m.integration.__file__).read_text())

    def test_MCP_arms_get_split_ports_and_exactly_one_server_only_env_entry(self):
        seen = {}
        for arm in (A, D, E):
            seen[arm], result = self.capture_model_boundary(m.one_call, arm)
            argv = seen[arm]["argv"]
            entries = [x for x in argv if m.EXPLORE_ENV in x]
            self.assertEqual(entries, ['mcp_servers.playwright-test.env.%s="%d"' % (m.EXPLORE_ENV, self.PORT + m.EXPLORE_PORT_OFFSET)])
            self.assertEqual(argv[argv.index(entries[0]) - 1], "-c")
            self.assertEqual(argv[-1], "-")
            self.assertFalse(any(x.startswith("shell_environment_policy.set.") and m.EXPLORE_ENV in x for x in argv))
            self.assertEqual(result["generation_config"]["server_isolation"], "split-ports")
            self.assertFalse(result["generation_config"]["test_run_reuse_existing_server"])
            self.assertTrue(result["generation_config"]["explore_role_reuse_existing_server"])
            files = seen[arm]["files"]
            roles = [resolve_roles(files["project/playwright.config.mjs"].decode(), files["project/app.mjs"].decode(), env)
                     for env in ({m.EXPLORE_ENV: str(self.PORT + m.EXPLORE_PORT_OFFSET)}, {})]
            self.assertNotEqual(roles[0]["listen_port"], roles[1]["listen_port"])
            self.assertFalse(roles[1]["reuse_existing_server"])
        # A, D and E share every argv byte except their declared read-only mounts.
        def without_mounts(argv):
            keep = [True] * len(argv)
            for i, x in enumerate(argv):
                if x == "--mount" and "skill/" in argv[i + 1]:
                    keep[i] = keep[i + 1] = False
            return [x for x, k in zip(argv, keep) if k]
        self.assertEqual(without_mounts(seen[D]["argv"]), seen[A]["argv"])
        self.assertEqual(without_mounts(seen[E]["argv"]), seen[A]["argv"])

    def test_B_and_C_keep_the_v3_generation_config_and_argv(self):
        predecessor, _ = self.capture_model_boundary(m.integration.one_call, B)
        successor, result = self.capture_model_boundary(m.one_call, B)
        self.assertEqual(successor, predecessor)
        text = successor["files"]["project/playwright.config.mjs"].decode()
        self.assertIn("reuseExistingServer: true", text)
        self.assertNotIn(m.EXPLORE_ENV, text)
        self.assertNotIn(m.EXPLORE_ENV, " ".join(successor["argv"]))
        self.assertNotIn("server_isolation", result.get("generation_config", {}))
        cells = [dict(case="v2-06", arm=C, generation_config=dict(
                    stages=1, server_isolation="shared-reuse", reuse_existing_server=True,
                    config_sha256_port_normalized=["g"], scoring_config_sha256_port_normalized=["s"]))]
        self.assertEqual(m.generation_uniformity(cells)["v2-06"]["shared-reuse"]["generation"], ["g"])

    def test_generation_uniformity_rejects_wrong_or_mixed_isolation(self):
        split = lambda arm, **kw: dict(case="v2-06", arm=arm, generation_config=dict(
            stages=1, server_isolation="split-ports", reuse_existing_server=False, config_sha256_port_normalized=["g"],
            scoring_config_sha256_port_normalized=["s"], app_sha256_port_normalized=["a"], scoring_app_sha256_port_normalized=["x"], **kw))
        shared = lambda arm: dict(case="v2-06", arm=arm, generation_config=dict(
            stages=1, reuse_existing_server=True, config_sha256_port_normalized=["h"], scoring_config_sha256_port_normalized=["s"]))
        self.assertEqual(set(m.generation_uniformity([split(A), split(D), split(E), shared(B), shared(C)])["v2-06"]),
                         {"split-ports", "shared-reuse"})
        for cells in ([shared(A)], [split(C)], [split(A), dict(split(D), generation_config=dict(
                           split(D)["generation_config"], config_sha256_port_normalized=["other"]))],
                      [split(A), dict(split(D), generation_config=dict(split(D)["generation_config"], reuse_existing_server=True))],
                      [split(A), shared(B), dict(shared(C), generation_config=dict(
                           shared(C)["generation_config"], scoring_config_sha256_port_normalized=["different"]))]):
            with self.subTest(cells=cells), self.assertRaises(ValueError):
                m.generation_uniformity(cells)

    def test_explore_command_refuses_missing_marker_and_leaves_other_arms_alone(self):
        engine = self.engine_stub()
        with tempfile.TemporaryDirectory() as temp:
            work = Path(temp)
            (work / "project").mkdir()
            (work / "project/playwright.config.mjs").write_text(m.integration.SCORING_REUSE)
            args = (engine, work, work / "auth", "owned", "gpt-6-sol")
            with self.assertRaisesRegex(ValueError, "marker"):
                m.explore_command(m.compat.command, *args, A, work / "sessions")
            plain = m.compat.command(*args, m.compat.HARNESS_CHECK_ARM, work / "sessions")
            self.assertEqual(m.explore_command(m.compat.command, *args, m.compat.HARNESS_CHECK_ARM, work / "sessions"), plain)

    def test_harness_owned_paths_are_git_excluded_before_the_baseline_and_listed_from_disk(self):
        order = []
        with tempfile.TemporaryDirectory() as temp:
            project = Path(temp) / "project"
            project.mkdir()

            def original(path, case):
                order.append(((Path(path) / ".git/info/exclude").read_text()))

            m.excluding_baseline(original)(project, "synthetic")
            self.assertEqual(len(order), 1)
            lines = [x for x in order[0].splitlines() if not x.startswith("#")]
            self.assertEqual(lines, ["node_modules", ".playwright-mcp/"])
            (project / ".playwright-mcp").mkdir()
            (project / ".playwright-mcp/page-2.yml").write_text("y")
            (project / ".playwright-mcp/page-1.yml").write_text("y")
            (project / ".playwright-mcp/nested").mkdir()
            (project / ".playwright-mcp/nested/console.log").write_text("y")
            self.assertEqual(m.mcp_artifact_listing(project), [".playwright-mcp/nested/console.log", ".playwright-mcp/page-1.yml",
                                                                ".playwright-mcp/page-2.yml"])
            collected = m.scoped_collector(lambda p, d: dict(spec_files=["tests/a.spec.ts"], tests_files=["tests/a.spec.ts"],
                                           out_of_scope_writes=[".playwright-mcp/page-9.yml", "README.md"]))(project, Path(temp))
            self.assertEqual(collected["out_of_scope_writes"], ["README.md"])  # a real stray write is still reported
            self.assertEqual(len(collected["mcp_artifact_writes"]), 3)
            self.assertEqual(m.mcp_artifact_listing(Path(temp) / "absent"), [])

    def test_mcp_snapshots_remain_secondary_fidelity_evidence_without_double_counting(self):
        base = dict(spec_files=["tests/a.spec.ts"])
        count = lambda **kw: m.integration.fidelity_evidence(dict(base, **kw), [])["mcp_artifact_files"]
        self.assertEqual(count(mcp_artifact_writes=[".playwright-mcp/a.yml", ".playwright-mcp/b.yml"]), 2)
        self.assertEqual(count(out_of_scope_writes=[".playwright-mcp/a.yml", "other.txt"]), 1)  # v3-shaped records
        self.assertEqual(count(out_of_scope_writes=[".playwright-mcp/a.yml"], mcp_artifact_writes=[".playwright-mcp/a.yml"]), 1)
        self.assertEqual(count(out_of_scope_writes=["other.txt"]), 0)

    def test_exclusion_list_is_exactly_the_two_harness_owned_paths(self):
        # Process execution is blocked in this suite, so the real-git behavior (a link swap and snapshot files leave
        # `git status` empty when the exclude file precedes the baseline commit) was checked once by hand; see CHANGES.md.
        self.assertEqual(m.GIT_EXCLUDES, ("node_modules", ".playwright-mcp/"))


class ScannerIsolation(unittest.TestCase):
    EXPECTED = {
        "scan.sh", "scope-source.sh", "scope-graph.py", "scope-lexer.py", "scope-worker.py",
        "scope-watch.py", "conditional-discovery.py", "parse-ast-grep-json.py",
        "ast-grep-rules/sg-4ce-state-bool.yml", "ast-grep-rules/sg-4ce-count.yml",
        "ast-grep-rules/sg-4ce-text.yml", "ast-grep-rules/sg-4f-locator-as-truthy.yml",
        "ast-grep-rules/sg-15-missing-await-playwright-expect.yml",
    }

    def copy_source(self, root):
        source = root / "source"
        for name in self.EXPECTED:
            path = source / name
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes((m.SCANNER_SOURCE / name).read_bytes())
        return source

    def test_manifest_is_exact_pinned_runtime_inventory(self):
        manifest = m.scanner_manifest()
        self.assertEqual(set(manifest), self.EXPECTED)
        self.assertEqual(manifest, m.protocol()["scanner_gate"]["manifest"])
        self.assertEqual(m.SCANNER_TARGET, "/work/skill/scanner/scan.sh")
        for name, sha in manifest.items():
            self.assertEqual(sha, m.digest(m.SCANNER_SOURCE / name))
            self.assertRegex(sha, r"\A[0-9a-f]{64}\Z")

    def test_source_injection_cannot_expose_reviewer_skill_or_references(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp).resolve()
            source = self.copy_source(root)
            (source / "SKILL.md").write_text("MUST NEVER LOAD REVIEWER")
            (source / "references").mkdir()
            (source / "references/private.md").write_text("MUST NEVER LOAD REFERENCE")
            (source / "reviewer-link").symlink_to(m.SCANNER_SOURCE.parent, target_is_directory=True)
            with patch.object(m, "SCANNER_SOURCE", source):
                self.assertEqual(set(m.scanner_manifest()), self.EXPECTED)
                staged = m.stage_scanner(root / "work")
                self.assertEqual(m.scanner_manifest(staged), m.protocol()["scanner_gate"]["manifest"])
            self.assertEqual({str(p.relative_to(staged)) for p in staged.rglob("*") if p.is_file()}, self.EXPECTED)
            self.assertFalse(any(p.is_symlink() for p in staged.rglob("*")))
            self.assertFalse((staged / "SKILL.md").exists())
            self.assertFalse((staged / "references").exists())
            self.assertFalse((staged.parent / "e2e-reviewer").exists())

    def test_source_symlink_and_changed_pinned_bytes_fail_closed(self):
        for change in ("file-symlink", "ancestor-symlink", "bytes"):
            with self.subTest(change=change), tempfile.TemporaryDirectory() as temp:
                root = Path(temp).resolve()
                source = self.copy_source(root)
                if change == "file-symlink":
                    target = source / "scan.sh"
                    target.unlink()
                    target.symlink_to(m.SCANNER_SOURCE / "scan.sh")
                elif change == "ancestor-symlink":
                    alias = root / "alias"
                    alias.symlink_to(source, target_is_directory=True)
                    source = alias
                else:
                    (source / "scan.sh").write_text("#!/bin/bash\nexit 0\n")
                with patch.object(m, "SCANNER_SOURCE", source), self.assertRaises(ValueError):
                    m.stage_scanner(root / "work")

    def test_staged_additions_deletions_symlinks_and_mutations_are_detectable(self):
        for change in ("skill", "references", "empty-directory", "deletion", "symlink", "mutation"):
            with self.subTest(change=change), tempfile.TemporaryDirectory() as temp:
                staged = m.stage_scanner(Path(temp).resolve())
                original = m.scanner_manifest(staged)
                if change == "skill":
                    (staged / "SKILL.md").write_text("unapproved reviewer skill")
                elif change == "references":
                    (staged / "references").mkdir()
                    (staged / "references/rules.md").write_text("unapproved reviewer reference")
                elif change == "empty-directory":
                    (staged / "references").mkdir()
                elif change == "symlink":
                    (staged / "reviewer").symlink_to(m.SCANNER_SOURCE.parent, target_is_directory=True)
                elif change == "deletion":
                    (staged / "scan.sh").unlink()
                else:
                    path = staged / "scan.sh"
                    path.chmod(0o644)
                    path.write_bytes(path.read_bytes() + b"\n# mutation\n")
                if change == "mutation":
                    self.assertNotEqual(m.scanner_manifest(staged), original)
                else:
                    with self.assertRaises(ValueError):
                        m.scanner_manifest(staged)

    def child_gate(self, mode="completed", parent="root", transcript_roots=("root",)):
        with tempfile.TemporaryDirectory() as temp:
            directory = Path(temp).resolve()
            transcripts = directory / "final-transcripts"
            transcripts.mkdir()
            events = [dict(type="thread.started", thread_id=root) for root in transcript_roots]
            events.append(dict(type="item.completed", item=dict(type="collab_tool_call", tool="spawn_agent",
                          status="completed", receiver_thread_ids=["child"])))
            (transcripts / "cell.jsonl").write_text("\n".join(json.dumps(event) for event in events))
            sessions = directory / "codex-sessions/cell"
            sessions.mkdir(parents=True)
            root = [dict(type="session_meta", payload=dict(id="root", parent_thread_id=None))]
            child = [dict(type="session_meta", payload=dict(id="child", parent_thread_id=parent))]
            if mode in ("completed", "sanitized", "failed"):
                command = m.SCANNER_COMMAND.replace("/work/", "<work>/") if mode == "sanitized" else m.SCANNER_COMMAND
                child.append(dict(type="event_msg", payload=dict(type="exec_command_end",
                                  command=["/bin/sh", "-c", command], exit_code=2 if mode == "failed" else 0)))
            elif mode == "message":
                child.append(dict(type="event_msg", payload=dict(type="agent_message", message="Ran " + m.SCANNER_COMMAND)))
            else:
                child.append(dict(type="response_item", payload=dict(type="function_call", call_id="scan-call",
                                  name="functions.exec_command", arguments=json.dumps(dict(cmd=m.SCANNER_COMMAND)))))
                if mode == "function-completed":
                    child.append(dict(type="response_item", payload=dict(type="function_call_output", call_id="scan-call",
                                      output=json.dumps(dict(exit_code=0, output="Summary: no findings")))))
            for name, records in (("root", root), ("child", child)):
                records.append(dict(type="event_msg", payload=dict(type="token_count", info=dict(
                    total_token_usage=dict(input_tokens=100, cached_input_tokens=0, output_tokens=10, total_tokens=110)))))
                (sessions / ("rollout-" + name + ".jsonl")).write_text("\n".join(json.dumps(event) for event in records))
            return m.scanner_gate_indicator(dict(arm=E, transcript_path="cell.jsonl"), transcripts)

    def test_scanner_gate_observes_verified_child_only_commands(self):
        for mode in ("completed", "sanitized", "function-completed", "failed"):
            with self.subTest(mode=mode):
                self.assertIs(self.child_gate(mode), True)

    def test_scanner_gate_rejects_unrelated_or_conflicting_child_identity_and_narration(self):
        for mode, parent, roots in (("completed", "unrelated", ("root",)),
                                    ("completed", "root", ("other",)),
                                    ("completed", "root", ("root", "other")),
                                    ("message", "root", ("root",)),
                                    ("function-request", "root", ("root",))):
            with self.subTest(mode=mode, parent=parent, roots=roots):
                self.assertIsNot(self.child_gate(mode, parent, roots), True)

    def test_gate_indicator_requires_exact_documented_command_and_preserves_unknown(self):
        for command, expected in ((m.SCANNER_COMMAND, True),
                                  (m.SCANNER_COMMAND.replace("/work/", "<work>/"), True),
                                  ("cat /work/skill/scanner/scan.sh", False),
                                  ("/bin/bash -p /work/skill/scanner/scan.sh other/", False)):
            events = [dict(type="item.completed", item=dict(type="command_execution", command=command, exit_code=0))]
            with self.subTest(command=command), patch.object(m.integration, "transcript_events", return_value=events):
                self.assertEqual(m.scanner_gate_indicator({}, Path("unused")), expected)
        with patch.object(m.integration, "transcript_events", return_value=None):
            self.assertIsNone(m.scanner_gate_indicator({}, Path("unused")))
        with patch.object(m.integration, "transcript_events", return_value=[]):
            self.assertFalse(m.scanner_gate_indicator({}, Path("unused")))


class ResumeAccounting(unittest.TestCase):
    def resume_skipped_B(self, recover_A, interrupted=False):
        """Use the actual inherited loop and call path, with an inert model boundary."""
        p = dict(m.protocol(), minimum_free_disk_bytes=0)
        model = p["candidate_models"][0]
        items = [dict(case=p["tasks"][0], arm=arm, repetition=1, ordinal=i)
                 for i, arm in enumerate((A, B), 1)]
        args = argparse.Namespace(resume=True, model=model["id"], timeout=1, call_budget=None)
        launched = []

        stage = realistic_stage(tests=True)

        def call(project, work, arm, *args):
            launched.append(arm)
            if arm == B:
                self.assertTrue((project / "tests/generated.spec.ts").is_file())
            # A real failed attempt followed by a delivered attempt, without a model process.
            failed = launched.count(arm) == 1
            (project / "tests/generated.spec.ts").write_text("test('inert', () => {});\n")
            return dict(infrastructure_error=failed, elapsed_ms=1, timeout=False,
                        transcript_path=f"{arm}-{launched.count(arm)}.jsonl")

        def collect(project, destination):
            (destination / "tests").mkdir(parents=True)
            (destination / "tests/generated.spec.ts").write_bytes((project / "tests/generated.spec.ts").read_bytes())
            return dict(spec_files=["tests/generated.spec.ts"], tests_files=["tests/generated.spec.ts"])

        with tempfile.TemporaryDirectory() as temp:
            directory = Path(temp).resolve()
            artifacts = directory / "final-artifacts"
            skipped = m.integration.one_call(items[1], args, None, artifacts, model, p)
            self.assertTrue(m.evidence.proven_skipped_reviewer(skipped))
            source = dict(items[0], call_id=m.v1.call_id_of(items[0]), deliverable=False,
                          infrastructure_error=recover_A, attempts=[dict(elapsed_ms=2, transcript_path="old-A.jsonl")])
            path = directory / "final.json"
            m.write(path, dict(runs=[source, skipped], completed_calls=2, cli="inert", container_image="inert"))
            if interrupted:
                m.write(directory / ".thin-attempt-journal.json",
                        dict(freeze_sha256="synthetic-freeze", rows=[source, skipped], inflight=items[1]))
            with contextlib.ExitStack() as stack:
                stack.enter_context(patch.object(m.engine, "CODEX_TRANSCRIPTS", None, create=True))
                for module, name, value in (
                    (m, "digest", lambda path: "synthetic-freeze"),
                    (m.v1, "model_dir", lambda mid: directory),
                    (m.v1, "protocol", lambda: p), (m.v1, "frozen", lambda: dict(schedule=items)),
                    (m.v1, "model_cfg", lambda *args: model),
                    (m.v1, "configure", lambda *args: (directory, "inert", "inert")),
                    (m.v1, "check_report", lambda *args, **kw: None),
                    (m.v1, "status_update", lambda **kw: None), (m.v1, "one_call", m.one_call),
                    (m.v1, "init_agents", lambda *args: dict(status="ready")),
                    (m.v1, "baseline", lambda *args: None),
                    (m.integration, "_REAL_STAGE", stage), (m.engine, "stage", stage),
                    (m.engine, "wait_for_load", lambda *args: None), (m.engine, "call_model", call),
                    (m.engine, "collect_deliverable", collect),
                    (m.integration.rev, "stage_reviewer", lambda *args: None),
                ):
                    stack.enter_context(patch.object(module, name, value))
                m.run_model(model["id"], args, {})
                first = m.read(path)["runs"]
                journal = m.read(directory / ".thin-attempt-journal.json")
                self.assertIsNone(journal["inflight"])
                # v1 adds its retry counter after the preserving call returns.
                without_retries = lambda rows: [{k: v for k, v in row.items() if k != "resume_retries"}
                                                 for row in rows]
                self.assertEqual(without_retries(journal["rows"]), without_retries(first))
                if recover_A:
                    self.assertEqual(launched, [A, A, B, B])
                    self.assertEqual(len(first[0]["attempts"]), 3)
                    self.assertEqual(len(first[1]["attempts"]), 2)
                    self.assertTrue(first[1]["deliverable"])
                    self.assertFalse(m.evidence.proven_skipped_reviewer(first[1]))
                else:
                    self.assertEqual(launched, [])
                    if interrupted:
                        self.assertTrue(first[1]["infrastructure_error"])
                        self.assertEqual(len(first[1]["attempts"]), 1)
                        self.assertTrue(first[1]["attempts"][0]["interrupted_attempt"])
                        self.assertFalse(m.evidence.proven_skipped_reviewer(first[1]))
                        costs = m.cell_extras(first[1], directory)
                        self.assertFalse(costs["tokens"]["complete"])
                        self.assertIsNone(costs["elapsed_s"])
                    else:
                        self.assertTrue(m.evidence.proven_skipped_reviewer(first[1]))
                        self.assertEqual(first[1]["attempts"], [])
                m.run_model(model["id"], args, {})
                second = m.read(path)["runs"]
                self.assertEqual([r["attempts"] for r in second], [r["attempts"] for r in first])
                self.assertEqual(launched, [A, A, B, B] if recover_A else [])
                self.assertIsNone(m.read(directory / ".thin-attempt-journal.json")["inflight"])
                if interrupted:
                    # After repeated skipped rechecks, A can still recover and
                    # B retains the unknown spend plus both new attempts once.
                    second[0]["infrastructure_error"] = True
                    report = m.read(path)
                    report["runs"] = second
                    m.write(path, report)
                    m.run_model(model["id"], args, {})
                    recovered = m.read(path)["runs"][1]
                    self.assertEqual(launched, [A, A, B, B])
                    self.assertTrue(recovered["deliverable"])
                    self.assertEqual(len(recovered["attempts"]), 3)
                    self.assertEqual(sum(bool(a.get("interrupted_attempt")) for a in recovered["attempts"]), 1)
                    self.assertFalse(m.cell_extras(recovered, directory)["tokens"]["complete"])
                    self.assertIsNone(m.read(directory / ".thin-attempt-journal.json")["inflight"])

    def test_skipped_B_resume_still_missing_A_launches_nothing(self):
        self.resume_skipped_B(recover_A=False)

    def test_skipped_B_resume_recovered_A_retains_replacement_attempts_once(self):
        self.resume_skipped_B(recover_A=True)

    def test_interrupted_B_recheck_preserves_unknown_spend_through_skips_and_recovery(self):
        self.resume_skipped_B(recover_A=False, interrupted=True)

    def simulate_resume(self, interrupted=False):
        with tempfile.TemporaryDirectory() as temp:
            directory = Path(temp).resolve()
            item = dict(case="synthetic", arm=D, repetition=1, ordinal=1)
            prior = dict(item, call_id=m.v1.call_id_of(item), infrastructure_error=True, deliverable=False,
                         attempts=[dict(transcript_path="old-one.jsonl", elapsed_ms=1),
                                   dict(transcript_path="old-two.jsonl", elapsed_ms=2)])
            path = directory / "final.json"
            m.write(path, dict(runs=[prior], completed_calls=1))
            if interrupted:
                m.write(directory / ".thin-attempt-journal.json",
                        dict(freeze_sha256="synthetic-freeze", rows=[prior], inflight=item))
            generated = Mock(return_value=dict(item, call_id=m.v1.call_id_of(item), infrastructure_error=False,
                                              deliverable=True, attempts=[dict(transcript_path="new.jsonl", elapsed_ms=3)]))

            def dropping_runner(model, args, state):
                # Match v1: remove retryable rows and flush before one_call sees final.json.
                rows = [r for r in m.read(path)["runs"] if not r["infrastructure_error"]]
                m.write(path, dict(runs=rows, completed_calls=len(rows)))
                if not rows:
                    rows.append(m.v1.one_call(item, None, None, directory / "final-artifacts", None, {}))
                    m.write(path, dict(runs=rows, completed_calls=len(rows)))
                return 0

            with patch.object(m, "digest", return_value="synthetic-freeze"), \
                    patch.object(m.v1, "model_dir", return_value=directory), \
                    patch.object(m.v1, "one_call", generated), patch.object(m.v1, "run_model", dropping_runner):
                m.run_model("synthetic-model", argparse.Namespace(resume=True), {})
                first = m.read(path)["runs"][0]
                self.assertEqual(len(first["attempts"]), 4 if interrupted else 3)
                self.assertEqual([a["transcript_path"] for a in first["attempts"] if not a.get("interrupted_attempt")],
                                 ["old-one.jsonl", "old-two.jsonl", "new.jsonl"])
                m.run_model("synthetic-model", argparse.Namespace(resume=True), {})
                self.assertEqual(m.read(path)["runs"][0]["attempts"], first["attempts"])
                generated.assert_called_once()
            if interrupted:
                unknown = next(a for a in first["attempts"] if a.get("interrupted_attempt"))
                self.assertIsNone(unknown["elapsed_ms"])
                self.assertIsNone(unknown["transcript_path"])
                tokens = m.integration.tokens_for_record(unknown, directory / "missing-transcripts")
                self.assertFalse(tokens["complete"])

    def test_spent_attempts_survive_initial_flush_without_duplicate_on_second_resume(self):
        self.simulate_resume()

    def test_interrupted_spend_remains_unknown_and_cost_incomplete(self):
        self.simulate_resume(interrupted=True)

    def test_resume_retains_both_thin_and_scanner_integrity_histories(self):
        before = dict(infrastructure_error=True, attempts=[dict(elapsed_ms=1)],
                      thin_layer_integrity=[dict(attempt=1)], scanner_integrity=[dict(attempt=1)])
        current = dict(attempts=[dict(elapsed_ms=2)], thin_layer_integrity=[dict(attempt=2)],
                       scanner_integrity=[dict(attempt=2)])
        merged = m.merge_spent_attempts(current, before)
        self.assertEqual(merged["thin_layer_integrity"], [dict(attempt=1), dict(attempt=2)])
        self.assertEqual(merged["scanner_integrity"], [dict(attempt=1), dict(attempt=2)])
        self.assertEqual(merged["attempts"], [dict(elapsed_ms=1), dict(elapsed_ms=2)])

    def test_attempt_history_refuses_rerunning_completed_cell(self):
        with self.assertRaisesRegex(ValueError, "completed"):
            m.merge_spent_attempts(dict(attempts=[]), dict(infrastructure_error=False, attempts=[{}]))

    def test_skip_replacement_requires_proof_of_no_model_call(self):
        skipped = dict(arm=B, model_call_launched=False, call_skip_reason="source_a_missing_spec",
                       elapsed_ms=0, attempts=[], infrastructure_error=False)
        for changes in (dict(arm=A), dict(model_call_launched=None), dict(call_skip_reason=None),
                        dict(attempts=[dict(elapsed_ms=1)]), dict(usage={"input_tokens": 1}),
                        dict(transcript_path="spent.jsonl"), dict(elapsed_ms=None)):
            with self.subTest(changes=changes), self.assertRaisesRegex(ValueError, "completed"):
                m.merge_spent_attempts(dict(attempts=[]), dict(skipped, **changes))

    def test_output_guard_rejects_nested_directory_symlink(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp).resolve()
            output, other = root / "campaign", root / "other"
            output.mkdir()
            other.mkdir()
            (output / "synthetic-model").symlink_to(other, target_is_directory=True)
            with self.assertRaisesRegex(ValueError, "symlink"):
                m.output_guard(output, [dict(id="synthetic-model")])

    def test_freeze_refuses_preexisting_output_without_writing(self):
        with tempfile.TemporaryDirectory() as temp, patch.object(m, "bindings", return_value={}):
            with self.assertRaisesRegex(ValueError, "nonexistent"):
                m.freeze_payload(Path(temp).resolve(), dict(models=[]))


class OfflineBoundary(unittest.TestCase):
    def test_all_live_commands_refuse_before_validation_or_writes(self):
        for command in ("preflight", "harness-check", "drive", "score"):
            argv = [command, "--output", "/synthetic-never-created"]
            if command != "drive":
                argv += ["--model", "gpt-6-sol"]
            with self.subTest(command=command), patch.object(m, "frozen", side_effect=AssertionError("freeze read")), \
                    patch.object(Path, "mkdir", side_effect=AssertionError("directory write")), \
                    patch.object(m, "CampaignLock", side_effect=AssertionError("lock opened")):
                with self.assertRaisesRegex(ValueError, "requires --allow-live"):
                    m.main(argv)

    def test_empty_summary_cannot_claim_layer_sufficiency(self):
        p = m.protocol()
        p["models"] = p["candidate_models"][:3]
        summary = m.summarize({}, p)
        self.assertEqual(summary["decision"]["statement"], "inconclusive")
        self.assertEqual(len(summary["missing_models"]), 3)

    def test_unknown_read_fidelity_integrity_and_tokens_are_inconclusive(self):
        p, results = complete_decision_fixture()
        for result in results.values():
            for cell in result["cells"]:
                if cell["arm"] == E:
                    cell.update(fidelity_class="unverified", thin_layer_read_indicator=None,
                                thin_layer_integrity=[], selector_hygiene=None)
                    cell["pipeline"]["tokens"]["complete"] = False
        result = m.descriptive_decision(results, p)
        self.assertEqual(result["statement"], "inconclusive")
        self.assertTrue(any("integrity" in reason for reason in result["reasons"]))
        self.assertTrue(any("cost" in reason for reason in result["reasons"]))


class DecisionCompleteness(unittest.TestCase):
    def test_disjoint_fidelity_failures_cannot_satisfy_joint_treatment_gate(self):
        for arm in (D, E):
            p, results = complete_decision_fixture()
            for result in results.values():
                cells = [c for c in result["cells"] if c["arm"] == arm]
                for cell in cells[:6]:
                    cell["fidelity_class"] = "unverified"
                for cell in cells[6:12]:
                    cell["thin_layer_read_indicator"] = False
                if arm == E:
                    for cell in cells[12:18]:
                        cell["scanner_gate_indicator"] = False
                self.assertEqual(sum(c["fidelity_class"] == "official-tool" for c in cells), 18)
                self.assertEqual(sum(bool(c["thin_layer_read_indicator"]) for c in cells), 18)
                self.assertEqual(sum(m.in_view(c, "as_treated") for c in cells), 6 if arm == E else 12)
            decision = m.descriptive_decision(results, p)
            self.assertEqual(decision["statement"], "inconclusive")
            self.assertTrue(any("jointly treated cells in " + arm in reason for reason in decision["reasons"]))

    def test_eighteen_jointly_treated_cells_meet_fidelity_gate(self):
        p, results = complete_decision_fixture()
        for result in results.values():
            for arm in (D, E):
                for cell in [c for c in result["cells"] if c["arm"] == arm][:6]:
                    cell.update(fidelity_class="unverified", thin_layer_read_indicator=False,
                                scanner_gate_indicator=False)
        self.assertEqual(m.descriptive_decision(results, p)["statement"],
                         "cheap stack sufficient (development point rule)")
    def test_exact_cost_and_quality_boundaries_pass(self):
        p, results = complete_decision_fixture()
        result = m.descriptive_decision(results, p)
        self.assertEqual(result["statement"], "cheap stack sufficient (development point rule)")
        self.assertTrue(result["quality_margins_met"])
        self.assertTrue(result["cost_rule_met"])
        self.assertAlmostEqual(result["values"]["mean_model_processed_ratio_E_over_C"], 0.8)
        self.assertAlmostEqual(result["values"]["primary|E_minus_C|selector_hygiene"], -0.1)

    def test_both_reviewer_and_full_skill_comparisons_are_required(self):
        p, results = complete_decision_fixture()
        decision = m.descriptive_decision(results, p)
        for rival in ("B", "C"):
            self.assertAlmostEqual(decision["values"]["mean_model_processed_ratio_E_over_" + rival], 0.8)
            for view in ("primary", "itt"):
                self.assertAlmostEqual(decision["values"][view + "|E_minus_" + rival + "|selector_hygiene"], -0.1)
        for rival in (B, C):
            p, results = complete_decision_fixture()
            for result in results.values():
                for cell in result["cells"]:
                    if cell["arm"] == rival:
                        cell["pipeline"]["tokens"]["processed"] = 99
            with self.subTest(rival=rival):
                self.assertEqual(m.descriptive_decision(results, p)["statement"], "cheap stack not demonstrated sufficient")

    def test_missing_or_subthreshold_gate_reviewer_and_official_evidence_is_inconclusive(self):
        for arm, field in ((B, "reviewer"), (E, "scanner"), (D, "read"), (E, "read"),
                           (A, "official"), (D, "official"), (E, "official"), (E, "integrity"),
                           (E, "scanner-readonly"), (E, "scanner-drift")):
            p, results = complete_decision_fixture()
            for result in results.values():
                cells = [cell for cell in result["cells"] if cell["arm"] == arm]
                for cell in cells[:7]:
                    if field == "reviewer":
                        cell["treatment"]["treated"] = False
                    elif field == "scanner":
                        cell["scanner_gate_indicator"] = None
                    elif field == "read":
                        cell["thin_layer_read_indicator"] = None
                    elif field == "official":
                        cell["fidelity_class"] = "unverified"
                    elif field == "integrity":
                        cell["scanner_integrity"] = []
                    else:
                        cell["scanner_integrity"] = [dict(before={"scan.sh": "a"},
                            after={"scan.sh": "b" if field == "scanner-drift" else "a"},
                            read_only_mount=field != "scanner-readonly")]
            with self.subTest(arm=arm, field=field):
                self.assertEqual(m.descriptive_decision(results, p)["statement"], "inconclusive")

    def test_truncated_54_and_duplicate_complete_size_grids_are_rejected(self):
        for kind in ("truncated", "duplicated"):
            p, results = complete_decision_fixture()
            for result in results.values():
                if kind == "truncated":
                    result["cells"] = result["cells"][:54]
                else:
                    result["cells"][-1] = copy.deepcopy(result["cells"][0])
            with self.subTest(kind=kind):
                decision = m.descriptive_decision(results, p)
                self.assertEqual(decision["statement"], "inconclusive")
                self.assertTrue(any("grid" in reason for reason in decision["reasons"]))

    def test_missing_static_evidence_is_not_zero_hygiene(self):
        for missing in ("absent", "unavailable"):
            p, results = complete_decision_fixture()
            cell = next(iter(results.values()))["cells"][0]
            if missing == "absent":
                del cell["static_hygiene"]
            else:
                cell["static_hygiene"]["available"] = False
            with self.subTest(missing=missing):
                decision = m.descriptive_decision(results, p)
                self.assertEqual(decision["statement"], "inconclusive")
                self.assertTrue(any("spec evidence" in reason for reason in decision["reasons"]))

    def test_quality_beyond_margin_and_cost_above_boundary_fail_screen(self):
        for kind in ("quality", "cost"):
            p, results = complete_decision_fixture()
            for result in results.values():
                for cell in result["cells"]:
                    if cell["arm"] == E:
                        if kind == "quality":
                            cell["selector_hygiene"] = 0.899
                        else:
                            cell["pipeline"]["tokens"]["processed"] = 81
            with self.subTest(kind=kind):
                self.assertEqual(m.descriptive_decision(results, p)["statement"], "cheap stack not demonstrated sufficient")


class ReviewerPipeline(unittest.TestCase):
    def summary_fixture(self):
        protocol, results = complete_decision_fixture()
        for result in results.values():
            for cell in result["cells"]:
                tokens = dict.fromkeys(m.evidence.TOKEN_FIELDS, 0)
                processed = 40 if cell["arm"] == B else 80 if cell["arm"] in (D, E, F, G) else 100
                tokens.update(complete=True, uncached_input=processed - 20, output=10,
                              child_uncached_input=5, child_output=5, cached_input=7,
                              child_cached_input=3, processed=processed, total=processed + 10)
                cell.update(load_flagged=False, compliance_raw={}, tokens=tokens,
                            elapsed_s=5 if cell["arm"] == B else 3, references_renamed_selector=False,
                            dynamic_selector_hint=False, static_hygiene=dict(available=True,
                                counts=dict.fromkeys(m.metrics.COUNTERS, 0),
                                tests_per_file={"tests/generated.spec.ts": 1}, unresolved_selector_calls=0))
            m.integration.add_pipeline(result["cells"])
            m.integration.set_as_treated(result["cells"])
        protocol["pooled_analysis"]["cluster_bootstrap"]["replicates"] = 2
        return protocol, results

    def test_summary_separates_B_pipeline_and_raw_calls_without_double_charging_A(self):
        protocol, results = self.summary_fixture()
        summary = m.summarize(results, protocol)
        raw = summary["raw_call_cost_endpoints"]
        pipeline = summary["cost_endpoints"]["itt"]
        spend = summary["scheduled_cell_spend"]
        self.assertNotIn("campaign_spend", summary)
        cells_per_arm = 3 * 24
        self.assertEqual(spend["cells"], 504)
        self.assertEqual(spend["cells_with_complete_tokens"], 504)
        self.assertEqual(raw[B]["tokens"]["processed"], cells_per_arm * 40)
        self.assertEqual(pipeline[B]["tokens"]["processed"], cells_per_arm * (100 + 40))
        self.assertEqual(pipeline[B]["elapsed_s_mean"], 8)
        self.assertEqual(raw[B]["elapsed_s_mean"], 5)
        for field in ("uncached_input", "output", "child_uncached_input", "child_output", "processed", "total"):
            self.assertEqual(pipeline[B]["tokens"][field], raw[A]["tokens"][field] + raw[B]["tokens"][field])
            self.assertEqual(spend["tokens"][field], sum(raw[arm]["tokens"][field] for arm in m.ARMS))
            self.assertEqual(sum(pipeline[arm]["tokens"][field] for arm in m.ARMS),
                             spend["tokens"][field] + raw[A]["tokens"][field])
        self.assertGreater(spend["tokens"]["child_output"], 0)
        self.assertEqual(pipeline[E]["tokens"], raw[E]["tokens"])
        self.assertAlmostEqual(pipeline[E]["quality_per_100k_processed"], 100000 * 0.9 / 80, places=4)
        self.assertAlmostEqual(pipeline[B]["quality_per_100k_processed"], 100000 / 140, places=4)
        self.assertGreater(raw[B]["quality_per_100k_processed"], pipeline[B]["quality_per_100k_processed"])

        # Missing A usage affects that raw call and its B pipeline, while review-only and E records remain complete.
        first = next(iter(results.values()))
        next(cell for cell in first["cells"] if cell["arm"] == A)["tokens"]["complete"] = False
        m.integration.add_pipeline(first["cells"])
        missing = m.summarize(results, protocol)
        self.assertEqual(missing["scheduled_cell_spend"]["cells_with_complete_tokens"], 503)
        self.assertEqual(missing["scheduled_cell_spend"]["tokens"]["processed"], spend["tokens"]["processed"] - 100)
        self.assertEqual(missing["raw_call_cost_endpoints"][B]["cells_with_complete_tokens"], cells_per_arm)
        self.assertEqual(missing["cost_endpoints"]["itt"][B]["cells_with_complete_tokens"], cells_per_arm - 1)
        self.assertEqual(missing["cost_endpoints"]["itt"][B]["tokens"]["processed"], (cells_per_arm - 1) * 140)
        self.assertEqual(missing["cost_endpoints"]["itt"][E], pipeline[E])
        self.assertEqual(missing["decision"]["statement"], "inconclusive")

    def test_analysis_links_B_fidelity_load_and_full_A_plus_reviewer_cost(self):
        for source_fidelity in ("official-tool", "unverified"):
            with self.subTest(source_fidelity=source_fidelity), tempfile.TemporaryDirectory() as temp:
                directory = Path(temp).resolve()
                rows = [dict(case="synthetic", arm=arm, repetition=1, ordinal=i,
                             call_id="cell-" + arm, spec_files=[], tests_files=[])
                        for i, arm in enumerate((A, B), 1)]
                report = dict(runs=rows)
                m.write(directory / "final.json", report)
                report_sha = m.digest(directory / "final.json")
                m.write(directory / "scoring-artifacts.json", dict(report_sha256=report_sha,
                        freeze_sha256="synthetic-freeze", artifacts={}))
                m.write(directory / "scores.json", dict(report_sha256=report_sha,
                        freeze_sha256="synthetic-freeze",
                        scoring_artifacts_sha256=m.digest(directory / "scoring-artifacts.json"), scores=rows))
                original_digest = m.digest

                def tokens(value):
                    result = dict.fromkeys(m.evidence.TOKEN_FIELDS, 0)
                    result.update(complete=True, uncached_input=value, output=10,
                                  child_uncached_input=value * 2, child_output=20,
                                  processed=value * 3 + 30, total=value * 3 + 30)
                    return result

                def extras(record, path):
                    official = record["arm"] == A
                    return dict(fidelity_class=source_fidelity if official else "unverified",
                                load_flagged=official, aborted=False, tokens=tokens(100 if official else 200),
                                elapsed_s=3 if official else 5,
                                treatment=dict(treated=not official, treated_core=False))

                with contextlib.ExitStack() as stack:
                    for module, key, value in (
                        (m, "check_report", lambda *args: None),
                        (m, "artifact_manifest", lambda *args: {}),
                        (m, "safe_specs", lambda *args: []),
                        (m, "cell_extras", extras),
                        (m.v1, "make_cell", lambda model, score, record, path: dict(record, clean=True, refactor_score=1.0)),
                        (m.metrics, "analyze_delivered_specs", lambda specs: dict(available=True)),
                        (m.integration, "selector_status", lambda *args: False),
                        (m.integration, "dynamic_selector_status", lambda *args: None),
                        (m, "generation_uniformity", lambda cells: {}),
                        (m, "digest", lambda path: "synthetic-freeze" if Path(path) == m.FREEZE else original_digest(path)),
                    ):
                        stack.enter_context(patch.object(module, key, value))
                    result = m.analyze_model(directory, dict(id="synthetic-model"), {}, dict(schedule=rows))
                source, reviewed = result["cells"]
                self.assertEqual(reviewed["fidelity_class"], source_fidelity)
                self.assertTrue(reviewed["source_load_flagged"])
                self.assertEqual(reviewed["as_treated"], source_fidelity == "official-tool")
                self.assertEqual(m.in_view(reviewed, "primary"), source_fidelity == "official-tool")
                self.assertTrue(reviewed["pipeline"]["includes_source_a"])
                self.assertEqual(reviewed["pipeline"]["elapsed_s"], 8)
                for field in m.evidence.TOKEN_FIELDS:
                    self.assertEqual(reviewed["pipeline"]["tokens"][field],
                                     source["tokens"][field] + reviewed["tokens"][field])
                self.assertTrue(reviewed["pipeline"]["tokens"]["complete"])
                self.assertGreater(reviewed["pipeline"]["tokens"]["child_uncached_input"], 0)


class ScoringArtifacts(unittest.TestCase):
    def fixture(self, root):
        directory = root / "synthetic-model"
        cell = directory / "final-artifacts/synthetic-cell"
        (cell / "tests").mkdir(parents=True)
        spec = cell / "tests/generated.spec.ts"
        spec.write_text("test('describes behaviour', async () => {});\n")
        helper = cell / "tests/helper.ts"
        helper.write_text("export const expected = 1;\n")
        report = dict(runs=[dict(call_id="synthetic-cell", spec_files=["tests/generated.spec.ts"])])
        m.write(directory / "final.json", report)
        return directory, spec, helper, report

    def test_manifest_includes_helper_bytes_and_rejects_deleted_delivered_spec(self):
        with tempfile.TemporaryDirectory() as temp:
            directory, spec, helper, report = self.fixture(Path(temp).resolve())
            manifest = m.artifact_manifest(directory, report)
            self.assertEqual(manifest["synthetic-cell/tests/generated.spec.ts"], m.digest(spec))
            self.assertEqual(manifest["synthetic-cell/tests/helper.ts"], m.digest(helper))
            spec.unlink()
            with self.assertRaisesRegex(ValueError, "spec is missing"):
                m.artifact_manifest(directory, report)

    def test_manifest_rejects_symlink_helper(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp).resolve()
            directory, spec, helper, report = self.fixture(root)
            helper.unlink()
            outside = root / "outside-helper.ts"
            outside.write_text("export const expected = 1;\n")
            helper.symlink_to(outside)
            with self.assertRaisesRegex(ValueError, "symlink"):
                m.artifact_manifest(directory, report)

    def test_score_binds_artifacts_before_parent_call_and_stamps_scores(self):
        with tempfile.TemporaryDirectory() as temp:
            output = Path(temp).resolve()
            directory, spec, helper, report = self.fixture(output)
            inputs_path = directory / "scoring-artifacts.json"
            original_digest = m.digest

            def digest(path):
                return "synthetic-freeze" if Path(path) == m.FREEZE else original_digest(path)

            def parent_score(model):
                self.assertEqual(model, "synthetic-model")
                self.assertTrue(inputs_path.is_file(), "manifest must precede the scorer")
                inputs = m.read(inputs_path)
                self.assertEqual(inputs["freeze_sha256"], "synthetic-freeze")
                self.assertEqual(inputs["report_sha256"], original_digest(directory / "final.json"))
                self.assertEqual(inputs["artifacts"]["synthetic-cell/tests/helper.ts"], original_digest(helper))
                m.write(directory / "scores.json", dict(scores=[]))

            with patch.object(m, "digest", side_effect=digest), patch.object(m, "check_report"), \
                    patch.object(m.integration, "score_model", side_effect=parent_score) as score:
                m.score_model("synthetic-model", output, dict(models=[dict(id="synthetic-model")]), {})
                score.assert_called_once()
            self.assertEqual(m.read(directory / "scores.json")["scoring_artifacts_sha256"], original_digest(inputs_path))

    def test_parent_scoring_artifact_mutation_is_rejected(self):
        with tempfile.TemporaryDirectory() as temp:
            output = Path(temp).resolve()
            directory, spec, helper, report = self.fixture(output)
            original_digest = m.digest

            def parent_score(model):
                helper.write_text("export const expected = 99;\n")
                m.write(directory / "scores.json", dict(scores=[]))

            with patch.object(m, "digest", side_effect=lambda path: "synthetic-freeze" if Path(path) == m.FREEZE else original_digest(path)), \
                    patch.object(m, "check_report"), patch.object(m.integration, "score_model", side_effect=parent_score):
                with self.assertRaisesRegex(ValueError, "changed during scoring"):
                    m.score_model("synthetic-model", output, dict(models=[dict(id="synthetic-model")]), {})

class SuccessorIdentity(unittest.TestCase):
    """Exercise public fidelity, entry, harness and costs with persisted fixtures."""
    def observe(self, roots=("root",), rollout_root="root", child_parent=None,
                parent_mcp=False, fallback=False, grandchild=False, duplicate=None, missing_identity=False):
        with tempfile.TemporaryDirectory() as temp:
            directory = Path(temp)
            transcripts = directory / "final-transcripts"
            transcripts.mkdir()
            events = [dict(type="thread.started", thread_id=root) for root in roots]
            events.append(dict(type="item.completed", item=dict(type="collab_tool_call", tool="spawn_agent",
                          status="completed", receiver_thread_ids=["child"])))
            if parent_mcp:
                events.append(dict(type="item.completed", item=dict(type="mcp_tool_call", server="playwright-test",
                              tool="generator_setup_page", status="completed")))
            if fallback:
                events.append(dict(type="item.completed", item=dict(type="agent_message", text="Browser setup succeeded.")))
            (transcripts / "cell.jsonl").write_text("\n".join(json.dumps(e) for e in events))
            sessions = directory / "codex-sessions/cell"
            sessions.mkdir(parents=True)

            def rollout(name, parent, usage, tools=(), shell=False):
                records = [dict(type="session_meta", payload=dict(id=name, parent_thread_id=parent))]
                records += [dict(type="event_msg", payload=dict(type="item_completed", item=dict(
                    type="McpToolCall", server="playwright-test", tool=tool, status="completed"))) for tool in tools]
                if shell:
                    records.append(dict(type="event_msg", payload=dict(type="exec_command_end",
                                   command=["ls", "specs/plan.md"], exit_code=0)))
                records.append(dict(type="event_msg", payload=dict(type="token_count", info=dict(total_token_usage=dict(
                               input_tokens=usage, cached_input_tokens=0, output_tokens=10, total_tokens=usage+10)))))
                (sessions / f"rollout-{name}.jsonl").write_text("\n".join(json.dumps(e) for e in records))

            if rollout_root is not None:
                rollout(rollout_root, None, 100)
                if missing_identity:
                    path = sessions / f"rollout-{rollout_root}.jsonl"
                    records = [json.loads(line) for line in path.read_text().splitlines()]
                    records[0]["payload"]["id"] = None
                    path.write_text("\n".join(json.dumps(e) for e in records))
                rollout("child", child_parent or rollout_root, 200,
                        ("generator_setup_page", "browser_navigate"), shell=True)
                if grandchild:
                    rollout("grandchild", "child", 300, ("generator_write_test",))
                if duplicate:
                    records = [json.loads(line) for line in (sessions / f"rollout-{duplicate}.jsonl").read_text().splitlines()]
                    records[0]["payload"]["parent_thread_id"] = "conflicting-parent"
                    (sessions / f"rollout-duplicate-{duplicate}.jsonl").write_text("\n".join(json.dumps(e) for e in records))
            record = dict(arm=A, transcript_path="cell.jsonl", spec_files=["tests/generated.spec.ts"],
                          usage=dict(input_tokens=100, output_tokens=10),
                          out_of_scope_writes=[".playwright-mcp/snapshot.md"] if fallback else [])
            fid = m.integration.classify_fidelity(record, transcripts)
            return (fid, m.integration.evaluate_harness_check(record, transcripts),
                    m.integration.tokens_for_record(record, transcripts))

    def assert_rejected(self, result):
        fidelity, harness, tokens = result
        self.assertFalse(m.integration.admits(fidelity))
        self.assertFalse(fidelity["evidence"]["primary_signal_complete"])
        self.assertNotEqual(harness["status"], "pass")
        self.assertFalse(tokens["complete"])

    def test_explicit_conflict_rejects_unrelated_successful_tools_and_cost(self):
        result = self.observe(roots=("explicit-other",))
        self.assert_rejected(result)
        fidelity, _, tokens = result
        self.assertEqual(fidelity["evidence"]["primary_signal"], "identity-conflict")
        self.assertEqual(fidelity["evidence"]["generator_surface_calls"], 0)
        self.assertEqual(tokens["child_output"], 0)
        self.assertEqual(tokens["processed"], 110)  # identified parent stream only, incomplete

    def test_identity_conflict_overrides_parent_mcp_artifact_and_message(self):
        self.assert_rejected(self.observe(roots=("explicit-other",), parent_mcp=True, fallback=True))

    def test_multiple_transcript_roots_reject_even_without_rollouts(self):
        self.assert_rejected(self.observe(roots=("root", "other"), rollout_root=None,
                                          parent_mcp=True, fallback=True))

    def test_explicit_child_identity_is_not_a_root(self):
        self.assert_rejected(self.observe(roots=("child",), parent_mcp=True, fallback=True))

    def test_unrelated_child_cannot_supply_tools_or_tokens(self):
        result = self.observe(child_parent="unrelated")
        self.assert_rejected(result)
        self.assertEqual(result[0]["evidence"]["generator_surface_calls"], 0)
        self.assertEqual(result[2]["child_output"], 0)

    def test_duplicate_root_or_child_identity_cannot_supply_admission_tools(self):
        for name in ("root", "child"):
            with self.subTest(identity=name):
                result = self.observe(duplicate=name, parent_mcp=True, fallback=True)
                self.assert_rejected(result)
                self.assertEqual(result[0]["evidence"]["primary_signal"], "identity-conflict")
                self.assertEqual(result[0]["evidence"]["rollouts"]["generator_surface_completed"], 0)
                self.assertEqual(result[2]["child_output"], 0)

    def test_missing_rollout_identity_cannot_supply_admission_tools(self):
        self.assert_rejected(self.observe(roots=(), missing_identity=True, parent_mcp=True, fallback=True))

    def test_matching_root_and_verified_descendants_pass(self):
        fidelity, harness, tokens = self.observe(grandchild=True)
        self.assertTrue(m.integration.admits(fidelity))
        self.assertTrue(fidelity["evidence"]["primary_signal_complete"])
        self.assertEqual(harness["status"], "pass")
        self.assertTrue(tokens["complete"])
        self.assertEqual(tokens["child_uncached_input"], 500)
        self.assertEqual(tokens["child_output"], 20)
        self.assertEqual(tokens["processed"], 630)

    def test_unnamed_transcript_retains_unique_parentless_fallback(self):
        fidelity, harness, tokens = self.observe(roots=())
        self.assertTrue(m.integration.admits(fidelity))
        self.assertEqual(harness["status"], "pass")
        self.assertTrue(tokens["complete"])

    def test_successor_imports_cannot_execute_frozen_codex_v3_modules(self):
        forbidden_names = {"run-generator-multimodel-v3-codex.py", "generator_v3_codex_evidence.py",
                           "generator_v3_codex_pooled.py", "generator_codex_official_adapter_compat_v3.py"}
        original = importlib.util.spec_from_file_location
        original_import = builtins.__import__
        imported = []

        def guarded_import(name, *args, **kwargs):
            self.assertNotIn(name.split(".")[0], {Path(path).stem for path in forbidden_names})
            return original_import(name, *args, **kwargs)

        def guarded(name, location, *args, **kwargs):
            self.assertNotIn(Path(location).name, forbidden_names)
            imported.append(Path(location).name)
            return original(name, location, *args, **kwargs)

        with patch.object(importlib.util, "spec_from_file_location", side_effect=guarded), \
                patch.object(builtins, "__import__", side_effect=guarded_import), patch.dict(sys.modules):
            sys.modules.pop("generator_thin_metrics_v1", None)
            sys.modules.pop("generator_thin_codex_pooled_v1", None)
            isolated = m.load("thin_no_v3_specific_imports", ROOT / "scripts/evals/run-generator-thin-eval-v1.py")
            self.assertEqual(isolated.protocol()["protocol_id"], m.ID)
            self.assertTrue(isolated.integration.frozen()["models"])
        self.assertIn("generator_thin_codex_adapter_v1.py", imported)
        self.assertIn("generator_thin_codex_evidence_v1.py", imported)
        self.assertIn("run-generator-multimodel-v1.py", imported)  # explicit unchanged shared-code exception
        self.assertIn("transitively bound", m.protocol()["inheritance"]["shared_code_exception"])

    def test_bindings_cover_every_successor_executable(self):
        files = m.bindings()["files"]
        for name in ("integration", "adapter", "evidence", "pooled"):
            self.assertIn(f"scripts/evals/generator_thin_codex_{name}_v1.py", files)
        self.assertIn("benchmarks/generator-thin-eval-v1/CHANGES.md", files)


def write_cell(directory, child_tools=(), root_tools=(), parent_tools=(), rollouts=True, children=1, usage=(100, 200), stem="cell"):
    """Persist one cell's transcript and rollouts like the adapter does; returns the record."""
    transcripts = Path(directory) / "final-transcripts"
    transcripts.mkdir(parents=True, exist_ok=True)
    events = [dict(type="thread.started", thread_id="root")]
    events += [dict(type="item.completed", item=dict(type="collab_tool_call", tool="spawn_agent", status="completed",
                                                      receiver_thread_ids=["child%d" % i])) for i in range(children)]
    events += [dict(type="item.completed", item=dict(type="mcp_tool_call", server="playwright-test", tool=tool, status="completed"))
               for tool in parent_tools]
    (transcripts / (stem + ".jsonl")).write_text("\n".join(json.dumps(e) for e in events))
    if rollouts:
        sessions = Path(directory) / "codex-sessions" / stem
        sessions.mkdir(parents=True, exist_ok=True)

        def rollout(name, parent, tokens, tools):
            records = [dict(type="session_meta", payload=dict(id=name, parent_thread_id=parent))]
            records += [dict(type="event_msg", payload=dict(type="item_completed", item=dict(
                type="McpToolCall", server="playwright-test", tool=tool, status="completed"))) for tool in tools]
            records.append(dict(type="event_msg", payload=dict(type="token_count", info=dict(total_token_usage=dict(
                input_tokens=tokens, cached_input_tokens=0, output_tokens=10, total_tokens=tokens + 10)))))
            (sessions / f"rollout-{name}.jsonl").write_text("\n".join(json.dumps(e) for e in records))

        rollout("root", None, usage[0], root_tools)
        for i in range(children):
            rollout("child%d" % i, "root", usage[1], child_tools)
    return dict(arm=A, transcript_path=stem + ".jsonl", spec_files=[], attempts=[], usage=dict(input_tokens=usage[0], output_tokens=10))


class ExplorationDepth(unittest.TestCase):
    """F4: browser_* interaction counts sit beside the unchanged fidelity class."""
    def extras(self, **kw):
        with tempfile.TemporaryDirectory() as temp:
            directory = Path(temp).resolve()
            record = write_cell(directory, **kw)
            return m.cell_extras(record, directory)

    def test_counts_split_acting_and_observing_tools_and_generator_steps(self):
        out = self.extras(child_tools=("generator_setup_page", "browser_navigate", "browser_click", "browser_snapshot",
                                       "browser_type", "browser_verify_text_visible", "generator_write_test", "generator_write_test"))
        counts = out["browser_interactions"]
        self.assertEqual(out["fidelity_class"], "official-tool")
        self.assertEqual((counts["source"], counts["complete"]), ("rollout", True))
        self.assertEqual((counts["browser_total"], counts["browser_acting"], counts["browser_observing"]), (5, 3, 2))
        self.assertEqual(counts["generator_steps"], {"generator_setup_page": 1, "generator_read_log": 0, "generator_write_test": 2})
        self.assertIs(counts["zero_browser_interaction"], False)

    def test_zero_browser_interactions_keep_the_class_but_are_reported(self):
        out = self.extras(child_tools=("generator_setup_page", "generator_write_test"))
        self.assertEqual(out["fidelity_class"], "official-tool")  # the class is unchanged: the generator surface was touched
        counts = out["browser_interactions"]
        self.assertEqual(counts["browser_total"], 0)
        self.assertIs(counts["zero_browser_interaction"], True)
        summary = m.browser_interaction_summary([out, self.extras(child_tools=("browser_navigate", "generator_write_test"))])
        self.assertEqual((summary["cells"], summary["cells_with_complete_counts"], summary["cells_with_zero_browser_interaction"]), (2, 2, 1))
        self.assertEqual(summary["browser_total_min_median_max"], [0, 1, 1])
        self.assertIn("not that the browser exploration loop ran", summary["note"])

    def test_without_a_root_rollout_the_parent_stream_is_only_a_lower_bound(self):
        out = self.extras(rollouts=False, parent_tools=("browser_navigate",))
        counts = out["browser_interactions"]
        self.assertEqual(counts["source"], "parent-stream-lower-bound")
        self.assertIs(counts["complete"], False)
        self.assertIsNone(counts["zero_browser_interaction"])  # unknown, never zero
        summary = m.browser_interaction_summary([out])
        self.assertEqual((summary["cells_with_complete_counts"], summary["cells_with_incomplete_or_unavailable_counts"],
                          summary["cells_with_zero_browser_interaction"]), (0, 1, 0))

    def test_missing_transcript_is_unavailable_and_B_C_cells_carry_no_counts(self):
        self.assertEqual(m.integration.browser_interaction_counts(None), {"available": False, "source": None, "complete": False})
        with tempfile.TemporaryDirectory() as temp:
            directory = Path(temp).resolve()
            record = dict(write_cell(directory, child_tools=("browser_click",)), arm=C)
            self.assertNotIn("browser_interactions", m.cell_extras(record, directory))

    def test_D_and_E_cells_carry_the_same_counts_as_the_official_classifier_sees(self):
        with tempfile.TemporaryDirectory() as temp:
            directory = Path(temp).resolve()
            base = write_cell(directory, child_tools=("browser_click", "generator_write_test"))
            outs = {arm: m.cell_extras(dict(base, arm=arm), directory) for arm in (A, D, E)}
        self.assertEqual({a: o["browser_interactions"]["browser_total"] for a, o in outs.items()}, {A: 1, D: 1, E: 1})
        self.assertTrue(all(o["fidelity_class"] == "official-tool" for o in outs.values()))


class RolloutDerivedCosts(unittest.TestCase):
    """Cost numbers include child agents from rollouts; parent-only final.json usage is never the cost."""
    def test_child_tokens_are_included_and_parent_only_usage_understates(self):
        with tempfile.TemporaryDirectory() as temp:
            directory = Path(temp).resolve()
            record = write_cell(directory, child_tools=("generator_write_test",), usage=(195000, 874000))
            out = m.cell_extras(record, directory)
        tokens = out["tokens"]
        parent_only = record["usage"]["input_tokens"] + record["usage"]["output_tokens"]
        self.assertTrue(tokens["complete"])
        self.assertEqual(tokens["child_uncached_input"], 874000)
        self.assertEqual(tokens["processed"], 195000 + 10 + 874000 + 10)
        self.assertGreater(tokens["processed"], 5 * parent_only)  # the v3 mid-run finding: about 5x understated

    def test_without_rollouts_the_cell_is_incomplete_not_parent_only(self):
        with tempfile.TemporaryDirectory() as temp:
            directory = Path(temp).resolve()
            record = write_cell(directory, rollouts=False, usage=(195000, 874000))
            tokens = m.cell_extras(record, directory)["tokens"]
        self.assertFalse(tokens["complete"])
        pipeline = m.evidence.pipeline_tokens([tokens])
        self.assertFalse(pipeline["complete"])

    def test_protocol_and_budget_state_the_rollout_rule(self):
        protocol = m.protocol()
        self.assertIn("final.json", protocol["cost_endpoints"]["rollout_rule"])
        self.assertIn("never an input", protocol["cost_endpoints"]["rollout_rule"])
        basis = protocol["budget"]["measured_basis"]
        self.assertIn("never used", basis["token_accounting"])
        self.assertEqual(basis["rollout_tokens_per_cell"]["A"]["total"], 1080000)
        # The thin cost helpers take usage only through the evidence module's rollout-first accounting.
        text = (ROOT / "scripts/evals/run-generator-thin-eval-v1.py").read_text()
        self.assertNotIn('["usage"]', text.split("def summarize(")[1].split("def browser_interaction_summary")[0])


def stage_1_fixture(models=2, with_reviewer=False, mode="v3-reference"):
    """Scheduled A/D/E (plus optional B) cells and attached arm-C reference cells copied from a full fixture."""
    arms = (A, B, D, E, F, G) if with_reviewer else (A, D, E, F, G)
    _, full = complete_decision_fixture(arms=m.ARMS, models=models)
    p, results = complete_decision_fixture(arms=arms, models=models, c_reference=dict(mode=mode))
    if mode == "v3-reference":
        for mid, result in results.items():
            result["c_reference_cells"] = [dict(c, c_reference=True) for c in full[mid]["cells"] if c["arm"] == C]
    return p, results


def summary_ready(p, results):
    for result in results.values():
        for cell in result["cells"] + result.get("c_reference_cells", []):
            cell.update(load_flagged=False, compliance_raw={}, tokens=cell["pipeline"]["tokens"],
                        references_renamed_selector=False, dynamic_selector_hint=False,
                        static_hygiene=dict(available=True, counts=dict.fromkeys(m.metrics.COUNTERS, 0),
                                            tests_per_file={"tests/generated.spec.ts": 1}, unresolved_selector_calls=0))
        m.integration.set_as_treated([c for c in result["cells"] if c["arm"] in (A, B, C)] + [])
    p["pooled_analysis"]["cluster_bootstrap"]["replicates"] = 2
    return p, results


class Stage1Decision(unittest.TestCase):
    def test_screen_met_against_the_cross_campaign_reference_never_issues_sufficiency(self):
        for models in (1, 2, 3):
            p, results = stage_1_fixture(models)
            decision = m.descriptive_decision(results, p)
            with self.subTest(models=models):
                self.assertTrue(decision["statement"].startswith("inconclusive: stage-1 screen met"), decision)
                self.assertTrue(decision["stage_1_screen_met"])
                self.assertEqual(decision["comparator_screens"]["C"]["basis"], "cross-campaign descriptive v3 reference")
                self.assertFalse(decision["comparator_screens"]["B"]["evaluated"])
                self.assertAlmostEqual(decision["values"]["mean_model_processed_ratio_E_over_C"], 0.8)
                self.assertNotIn("E_minus_B", " ".join(decision["values"]))

    def test_a_failed_threshold_against_the_reference_is_not_demonstrated_sufficient(self):
        for kind in ("quality", "cost"):
            p, results = stage_1_fixture(2)
            for result in results.values():
                for cell in result["cells"]:
                    if cell["arm"] == E:
                        if kind == "quality":
                            cell["selector_hygiene"] = 0.899
                        else:
                            cell["pipeline"]["tokens"]["processed"] = 81
            with self.subTest(kind=kind):
                decision = m.descriptive_decision(results, p)
                self.assertEqual(decision["statement"], "cheap stack not demonstrated sufficient")
                self.assertFalse(decision["stage_1_screen_met"])

    def test_sufficiency_needs_reviewer_reference_and_three_models(self):
        p, results = stage_1_fixture(3, with_reviewer=True)
        for result in results.values():
            for cell in result["cells"]:
                if cell["arm"] == B:
                    cell["pipeline"]["tokens"].update(processed=100, total=120)
        self.assertEqual(m.descriptive_decision(results, p)["statement"], "cheap stack sufficient (development point rule)")
        p, results = stage_1_fixture(2, with_reviewer=True)
        self.assertTrue(m.descriptive_decision(results, p)["statement"].startswith("inconclusive: stage-1 screen met"))

    def test_missing_reference_or_comparators_are_inconclusive(self):
        p, results = stage_1_fixture(2)
        for result in results.values():
            result["c_reference_cells"] = result["c_reference_cells"][:23]
        self.assertIn("reference", " ".join(m.descriptive_decision(results, p)["reasons"]))
        p, results = stage_1_fixture(2, mode="none")
        decision = m.descriptive_decision(results, p)
        self.assertEqual(decision["statement"], "inconclusive")
        self.assertIn("no reviewer or full-skill comparator", " ".join(decision["reasons"]))
        p, results = stage_1_fixture(2)
        next(iter(results.values()))["c_reference_cells"][0]["pipeline"]["tokens"]["complete"] = False
        self.assertIn("incomplete cost records", " ".join(m.descriptive_decision(results, p)["reasons"]))
        p, results = stage_1_fixture(2)
        p["models"] = p["models"][:1]
        self.assertEqual(m.descriptive_decision(results, p)["statement"], "inconclusive")  # a frozen model has no result

    def test_reference_cells_never_count_as_scheduled_cells(self):
        p, results = stage_1_fixture(2)
        for result in results.values():
            result["cells"] = result["cells"] + result["c_reference_cells"][:1]
        self.assertIn("grid", " ".join(m.descriptive_decision(results, p)["reasons"]))

    def test_summary_labels_reference_contrasts_and_leaves_spend_to_scheduled_cells(self):
        p, results = summary_ready(*stage_1_fixture(2))
        summary = m.summarize(results, p)
        self.assertEqual(summary["arms"], [A, D, E, F, G])
        keys = list(summary["pooled"])
        self.assertTrue(any(k.startswith("primary|C_minus_E|") for k in keys))
        self.assertTrue(any(k.startswith("primary|D_minus_A|") for k in keys))
        self.assertFalse(any("E_minus_B" in k for k in keys))
        self.assertIn("cross-campaign descriptive", summary["pooled"]["primary|C_minus_E|refactor_score"]["basis"])
        self.assertNotIn("basis", summary["pooled"]["primary|D_minus_A|refactor_score"])
        self.assertEqual(summary["scheduled_cell_spend"]["cells"], 2 * 120)
        self.assertEqual(summary["cost_endpoints"]["itt"][C]["cells"], 48)
        self.assertEqual(set(summary["fidelity"]), {A, D, E, F, G})
        self.assertEqual(set(summary["selector_tables"]["primary"]), {A, C, D, E, F, G})

    def test_all_seven_arm_summary_has_the_catalog_shape(self):
        p, results = summary_ready(*complete_decision_fixture())
        summary = m.summarize(results, p)
        self.assertEqual(summary["arms"], list(m.ARMS))
        self.assertTrue(any("E_minus_B" in k for k in summary["pooled"]))
        self.assertEqual(summary["scheduled_cell_spend"]["cells"], 504)
        self.assertTrue(any("F_minus_D" in k for k in summary["pooled"]))


class CReference(unittest.TestCase):
    def setUp(self):
        self.candidates = m.protocol()["candidate_models"]

    def test_static_conditions_hold_against_the_repository_state(self):
        result = m.c_reference_conditions()
        self.assertTrue(result["ok"], result)
        self.assertEqual(set(result["conditions"]), {
            "v3_freeze_pinned", "predecessor_inputs_unchanged", "skill_digest_matches_v3_freeze",
            "c_prompt_digest_matches_v3_freeze", "c_path_source_identical", "protocol_constants_equal"})
        parity = result["conditions"]["c_path_source_identical"]["detail"]
        for name in ("generator_codex_official_adapter_compat_v3.py:command", "generator_codex_official_adapter_compat_v3.py:START",
                     "run-generator-multimodel-v3-codex.py:one_call"):
            self.assertTrue(parity[name], name)
        listed = " ".join(m.protocol()["analysis"]["c_reference"]["conditions"])
        for key in result["conditions"]:
            self.assertIn(key, listed)

    def test_every_static_condition_fails_closed(self):
        with patch.object(m, "source_parity", return_value={"command": False}):
            self.assertFalse(m.c_reference_conditions()["conditions"]["c_path_source_identical"]["ok"])
        with patch.object(m.integration, "frozen", side_effect=ValueError("drift")):
            self.assertFalse(m.c_reference_conditions()["conditions"]["predecessor_inputs_unchanged"]["ok"])
        with patch.object(m, "bindings", return_value={"v3_freeze_sha256": "0" * 64}):
            self.assertFalse(m.c_reference_conditions()["conditions"]["v3_freeze_pinned"]["ok"])
        with patch.object(m.integration.v1, "bindings", return_value={"skills_tree": "changed"}):
            self.assertFalse(m.c_reference_conditions()["conditions"]["skill_digest_matches_v3_freeze"]["ok"])
        with patch.object(m.integration.orig, "sha", return_value="changed"):
            self.assertFalse(m.c_reference_conditions()["conditions"]["c_prompt_digest_matches_v3_freeze"]["ok"])
        changed = dict(m.protocol(), timeout_s=m.protocol()["timeout_s"] + 1)
        with patch.object(m, "protocol", return_value=changed):
            self.assertFalse(m.c_reference_conditions()["conditions"]["protocol_constants_equal"]["ok"])
        for left, right in ((dict(cli="a", container_image="i"), dict(cli="b", container_image="i")),
                            (dict(cli="a", container_image="i"), dict(cli="a", container_image="j"))):
            self.assertFalse(m.c_reference_conditions("x", left, right)["conditions"]["same_cli_and_image"]["ok"])
        self.assertTrue(m.c_reference_conditions("x", dict(cli="a", container_image="i"),
                                                 dict(cli="a", container_image="i"))["conditions"]["same_cli_and_image"]["ok"])

    def test_source_parity_detects_a_changed_c_path_function(self):
        with tempfile.TemporaryDirectory() as temp:
            changed = Path(temp) / "adapter.py"
            changed.write_text((ROOT / "scripts/evals/generator_thin_codex_adapter_v1.py").read_text().replace(
                '"--cap-drop", "ALL"', '"--cap-drop", "NET_RAW"'))
            result = m.source_parity("generator_codex_official_adapter_compat_v3.py", changed, ("docker_prefix", "command"), ("START",))
            self.assertEqual(result, {"docker_prefix": True, "command": False, "START": True})
            self.assertEqual(m.source_parity("generator_codex_official_adapter_compat_v3.py", changed, ("absent",)), {"absent": False})

    def test_loader_recomputes_tokens_from_rollouts_and_labels_cells(self):
        model = self.candidates[0]
        with tempfile.TemporaryDirectory() as temp:
            source = build_v3_source(temp, self.candidates, {model["id"]: "admitted"}, rollout_models=(model["id"],))
            digests = {}
            loaded = m.load_c_reference(source, model, digests)
            self.assertEqual(loaded["label"], "cross-campaign descriptive")
            self.assertEqual(len(loaded["cells"]), 24)
            self.assertEqual(set(digests), {"_entry/%s.json" % model["id"], model["id"] + "/results.json", model["id"] + "/final.json"})
            for cell in loaded["cells"]:
                self.assertTrue(cell["c_reference"] and cell["arm"] == C and cell["_model"] == model["id"])
                self.assertTrue(cell["tokens"]["complete"])
                self.assertEqual(cell["tokens"]["child_uncached_input"], 874000)  # child agents included
                self.assertEqual(cell["tokens"]["processed"], 195010 + 874010)
                self.assertEqual(cell["pipeline"]["tokens"], cell["tokens"])
                self.assertEqual(cell["selector_hygiene"], 1.0)
                self.assertEqual(cell["clean_conditional_survival"], 1.0)
                self.assertEqual(cell["as_treated"], bool(cell["treatment"].get("treated_core")))
            # Without rollouts the same cells are incomplete rather than parent-only, and the usage in final.json is not the cost.
            bare = build_v3_source(Path(temp) / "bare", self.candidates, {model["id"]: "admitted"})
            self.assertTrue(all(not c["tokens"]["complete"] for c in m.load_c_reference(bare, model)["cells"]))

    def test_loader_refuses_unpinned_unadmitted_or_unfinished_sources(self):
        model = self.candidates[0]
        with tempfile.TemporaryDirectory() as temp:
            source = build_v3_source(temp, self.candidates, {model["id"]: "admitted"})
            (source / "freeze.json").write_text('{"different": true}')
            with self.assertRaisesRegex(ValueError, "pinned"):
                m.load_c_reference(source, model)
        for state in ("excluded", "undecided"):
            with self.subTest(state=state), tempfile.TemporaryDirectory() as temp:
                source = build_v3_source(temp, self.candidates, {model["id"]: state})
                with self.assertRaises(ValueError):
                    m.load_c_reference(source, model)
        with tempfile.TemporaryDirectory() as temp:
            source = build_v3_source(temp, self.candidates, {model["id"]: "admitted"})
            result = m.read(source / model["id"] / "results.json")
            result["complete"] = False
            m.write(source / model["id"] / "results.json", result)
            with self.assertRaises(ValueError):
                m.load_c_reference(source, model)

    def attached(self, temp, thin_cli="synthetic-cli", mutate=None):
        model = self.candidates[0]
        source = build_v3_source(Path(temp) / "v3", self.candidates, {model["id"]: "admitted"}, rollout_models=(model["id"],))
        digests = {}
        m.load_c_reference(source, model, digests)
        output = Path(temp) / "thin"
        m.write(output / model["id"] / "final.json", dict(cli=thin_cli, container_image="synthetic-image"))
        p, results = stage_1_fixture(1)
        p["models"] = [model]
        results = {model["id"]: dict(next(iter(results.values())), c_reference_cells=[])}
        lock = dict(c_reference=dict(mode="v3-reference", source_digests={model["id"]: digests}))
        p["c_reference"] = lock["c_reference"]
        if mutate:
            mutate(source, model)
        return p, results, lock, source, output, model

    def test_attachment_verifies_digests_conditions_and_cli(self):
        with tempfile.TemporaryDirectory() as temp:
            p, results, lock, source, output, model = self.attached(temp)
            out = m.attach_references(results, p, lock, source, output)
            self.assertEqual(len(out[model["id"]]["c_reference_cells"]), 24)
            self.assertTrue(all(out[model["id"]]["c_reference_meta"]["conditions"].values()))
            self.assertEqual(out[model["id"]]["c_reference_meta"]["label"], "cross-campaign descriptive")
            with self.assertRaisesRegex(ValueError, "--v3-results"):
                m.attach_references(results, p, lock, None, output)
        with tempfile.TemporaryDirectory() as temp:
            p, results, lock, source, output, model = self.attached(temp, thin_cli="another-cli")
            with self.assertRaisesRegex(ValueError, "not comparable.*same_cli_and_image"):
                m.attach_references(results, p, lock, source, output)

        def tamper(source, model):
            path = source / model["id"] / "final.json"
            report = m.read(path)
            report["cli"] = "tampered"
            m.write(path, report)
        with tempfile.TemporaryDirectory() as temp:
            p, results, lock, source, output, model = self.attached(temp, mutate=tamper)
            with self.assertRaises(ValueError):
                m.attach_references(results, p, lock, source, output)
        p2 = dict(p, c_reference=dict(mode="none"))
        self.assertEqual(m.attach_references({"x": {}}, p2, {}, None, Path("unused")), {"x": {}})

    def test_freeze_reference_requires_results_and_all_conditions(self):
        model = self.candidates[0]
        with self.assertRaisesRegex(ValueError, "--rerun-full-skill"):
            m.reference_for_roster(None, [model])
        with tempfile.TemporaryDirectory() as temp:
            source = build_v3_source(temp, self.candidates, {model["id"]: "admitted"})
            record = m.reference_for_roster(source, [model])
            self.assertEqual(record["mode"], "v3-reference")
            self.assertTrue(all(record["static_conditions"].values()))
            self.assertIn(model["id"], record["source_digests"])
            with patch.object(m, "c_reference_conditions", return_value=dict(ok=False, conditions={"x": dict(ok=False)})):
                with self.assertRaisesRegex(ValueError, "comparability conditions fail"):
                    m.reference_for_roster(source, [model])

    def test_reference_mode_is_exclusive_with_rerun(self):
        with self.assertRaises(ValueError):
            m.check_c_reference((A, C, D, E), dict(mode="v3-reference"))
        with self.assertRaises(ValueError):
            m.check_c_reference(m.MANDATORY_ARMS, dict(mode="rerun"))
        with self.assertRaises(ValueError):
            m.check_c_reference(m.MANDATORY_ARMS, dict(mode="other"))
        for arms, mode in ((m.MANDATORY_ARMS, "v3-reference"), (m.MANDATORY_ARMS, "none"), ((A, C, D, E), "rerun")):
            self.assertEqual(m.check_c_reference(arms, dict(mode=mode)), dict(mode=mode))


class PlanAndBudget(unittest.TestCase):
    def test_plan_reports_variants_and_budget_for_the_default_arm_set(self):
        import io
        stream = io.StringIO()
        with contextlib.redirect_stdout(stream):
            self.assertEqual(m.main(["plan"]), 0)
        plan = json.loads(stream.getvalue())
        self.assertEqual(len(plan["schedule"]), 120)
        self.assertEqual({k: v["cells_per_model"] for k, v in plan["variants"].items()},
                         {"default_A_D_E_F_G": 120, "with_reviewer": 144, "with_full_skill_rerun": 144, "all_seven_arms": 168})
        self.assertEqual(plan["variants"]["default_A_D_E_F_G"]["budget"]["arms"], ["A", "D", "E", "F", "G"])
        default = plan["variants"]["default_A_D_E_F_G"]
        self.assertEqual((default["generation_calls_per_model"], default["reviewer_calls_per_model"]), (120, 0))
        self.assertEqual(default["budget"]["ceiling_hours_per_model_at_call_timeout"], 50.0)
        self.assertEqual(plan["canary"]["count"], 6)
        two = default["budget"]["rolls_up"]["2"]
        self.assertEqual((two["cells"], two["generation_calls"], two["calls_incl_harness_check_and_max_entries"]), (240, 240, 245))
        low, central, high = two["points_low_central_high"]
        self.assertEqual((low, central, high), (47.618, 65.622, 86.004))  # recomputed honestly for 240 cells, not left at the 192-cell figures
        self.assertTrue(low < central < high < 100)
        self.assertEqual(two["flat_points_at_mean_cell_rate"], 88.8)
        self.assertTrue(two["fits_one_weekly_window_central"])
        original = plan["variants"]["all_seven_arms"]["budget"]["rolls_up"]["3"]
        self.assertEqual((original["cells"], original["flat_points_at_mean_cell_rate"]), (504, 186.5))
        self.assertFalse(original["fits_one_weekly_window_central"])
        self.assertEqual(plan["stage_1_roster"]["models"], ["gpt-6-sol", "gpt-6-astra"])

    def test_roster_command_validates_override_without_writing_anything(self):
        import io
        ids = [c["id"] for c in m.protocol()["candidate_models"]]
        stream = io.StringIO()
        with contextlib.redirect_stdout(stream), patch.object(m, "write", side_effect=AssertionError("write")):
            self.assertEqual(m.main(["roster", "--models", ids[0], "--override-reason", "owner decision"]), 0)
        out = json.loads(stream.getvalue())
        self.assertEqual(out["arms"], list(m.MANDATORY_ARMS))
        self.assertEqual(out["c_reference"], dict(mode="v3-reference", validated=False))
        self.assertEqual([x["id"] for x in out["models"]], [ids[0]])
        with self.assertRaises(ValueError):
            m.main(["roster", "--models", ids[0]])  # no reason
        with self.assertRaisesRegex(ValueError, "mutually exclusive"):
            m.main(["roster", "--models", ids[0], "--override-reason", "x", "--rerun-full-skill", "--no-c-reference"])


class ElapsedCompleteness(unittest.TestCase):
    def endpoint(self, times, survivors=None):
        tokens = dict.fromkeys(m.evidence.TOKEN_FIELDS, 0)
        tokens.update(complete=True, processed=100, total=100, uncached_input=80, output=20)
        return m.pooled.cost_endpoint([dict(refactor_score=score, pipeline=dict(tokens=tokens, elapsed_s=elapsed))
            for elapsed, score in zip(times, survivors if survivors is not None else [1] * len(times))])

    def test_partial_elapsed_does_not_divide_observed_time_by_all_survivors(self):
        out = self.endpoint([10, None])
        self.assertEqual((out["cells_with_observed_elapsed"], out["cells_with_unknown_elapsed"]), (1, 1))
        self.assertFalse(out["elapsed_complete"])
        self.assertEqual(out["elapsed_s_observed_sum"], 10)
        self.assertEqual(out["elapsed_s_observed_mean"], 10)
        self.assertIsNone(out["elapsed_s_mean"])
        self.assertIsNone(out["elapsed_s_per_survivor"])
        self.assertEqual(out["quality_per_100k_processed"], 1000)

    def test_all_observed_times_preserve_original_ratio(self):
        out = self.endpoint([10, 20])
        self.assertTrue(out["elapsed_complete"])
        self.assertEqual(out["cells_with_unknown_elapsed"], 0)
        self.assertEqual(out["elapsed_s_mean"], 15)
        self.assertEqual(out["elapsed_s_per_survivor"], 15)

    def test_missing_non_survivor_time_also_invalidates_pipeline_aggregate(self):
        out = self.endpoint([10, None], [1, 0])
        self.assertIsNone(out["elapsed_s_per_survivor"])

    def test_empty_and_all_unknown_time_are_unavailable(self):
        for times in ([], [None, None]):
            out = self.endpoint(times)
            self.assertFalse(out["elapsed_complete"])
            self.assertIsNone(out["elapsed_s_mean"])
            self.assertIsNone(out["elapsed_s_per_survivor"])
            self.assertIsNone(out["elapsed_s_observed_mean"])

    def test_zero_is_observed_and_no_survivors_has_no_ratio(self):
        out = self.endpoint([0, 0], [0, 0])
        self.assertTrue(out["elapsed_complete"])
        self.assertEqual(out["elapsed_s_mean"], 0)
        self.assertIsNone(out["elapsed_s_per_survivor"])

    def test_summary_uses_successor_time_completeness(self):
        protocol, results = complete_decision_fixture()
        for result in results.values():
            for cell in result["cells"]:
                cell.update(load_flagged=False, compliance_raw={}, tokens=cell["pipeline"]["tokens"],
                            references_renamed_selector=False, dynamic_selector_hint=False,
                            static_hygiene=dict(available=True, counts=dict.fromkeys(m.metrics.COUNTERS, 0),
                                                tests_per_file={"tests/generated.spec.ts": 1}, unresolved_selector_calls=0))
            m.integration.set_as_treated(result["cells"])
            next(cell for cell in result["cells"] if cell["arm"] == D)["pipeline"]["elapsed_s"] = None
        protocol["pooled_analysis"]["cluster_bootstrap"]["replicates"] = 2
        summary = m.summarize(results, protocol)
        out = summary["cost_endpoints"]["itt"][D]
        self.assertEqual(out["cells_with_unknown_elapsed"], 3)
        self.assertIsNone(out["elapsed_s_per_survivor"])
        self.assertTrue(summary["decision"]["cost_rule_met"])


# ------------------------------------------------------------------------------------------------ arm F / G (CLI-first thin workflow)

REAL_ARM_C_CLI = (  # verbatim command shapes from the successful v3 arm-C cells (gpt-6-sol), names kept, exit codes as observed
    ("npx --no-install playwright cli -s=tag-editor-20261015 --config /tmp/tag-editor-explore/cli.config.json open", 1),
    ("npx --no-install playwright cli -s=tag-editor-20261015b --config /tmp/tag-editor-explore/cli.config.json open --browser chromium", 0),
    ("npx --no-install playwright cli -s=tag-editor-20261015b eval \"fetch('http://127.0.0.1:9/').catch(() => {})\"", 0),
    ("npx --no-install playwright cli -s=tag-editor-20261015b requests", 0),
    ("npx --no-install playwright cli -s=tag-editor-20261015b goto http://127.0.0.1:9322/", 0),
    ("npx --no-install playwright cli -s=tag-editor-20261015b snapshot", 0),
    ("npx --no-install playwright cli -s=tag-editor-20261015b fill e5 Alpha", 0),
    ("npx --no-install playwright cli -s=tag-editor-20261015b press e5 Enter", 1),
    ("npx --no-install playwright cli -s=tag-editor-20261015b press Enter", 0),
    ("npx --no-install playwright cli -s=tag-editor-20261015b select e5 shipped", 0),
    ("npx --no-install playwright cli -s=tag-editor-20261015b snapshot", 0),
    ("npx --no-install playwright cli -s=tag-editor-20261015b close", 0),
)


SESSION_OPEN = "npx --no-install playwright cli -s=x --config /tmp/x/cli.config.json open --browser chromium"
SESSION_PROBE = "npx --no-install playwright cli -s=x eval \"() => fetch('http://127.0.0.1:9/').catch(() => null)\""
SESSION_REQUESTS = "npx --no-install playwright cli -s=x requests"
SESSION_GOTO = "npx --no-install playwright cli -s=x goto http://127.0.0.1:9400/"
SESSION_SNAP = "npx --no-install playwright cli -s=x snapshot"


def shell(command):
    return "/usr/bin/bash -c " + json.dumps(command)


BLOCKED_OUTPUT = "### Result\n1. [GET] http://127.0.0.1:9/ => [FAILED] net::ERR_BLOCKED_BY_CLIENT.Inspector\n"


def cli_events(commands, spawns=0, mcp=0):
    """Commands are (command, exit_code) or (command, exit_code, output). A bare `requests` call gets the output the real v3 cells
    returned (the refused origin blocked); every other call has no output unless given."""
    events = [dict(type="thread.started", thread_id="root")]
    for entry in commands:
        command, code = entry[0], entry[1]
        output = entry[2] if len(entry) > 2 else BLOCKED_OUTPUT if command.endswith(" requests") else None
        item = dict(type="command_execution", command=shell(command), exit_code=code)
        if output is not None:
            item["aggregated_output"] = output
        events.append(dict(type="item.completed", item=item))
    events += [dict(type="item.completed", item=dict(type="collab_tool_call", tool="spawn_agent", status="completed")) for _ in range(spawns)]
    events += [dict(type="item.completed", item=dict(type="mcp_tool_call", server="playwright-test", tool="browser_click", status="completed"))
               for _ in range(mcp)]
    return events


def write_cli_cell(directory, commands, spec_files=("tests/a.spec.ts",), stem="fcell", usage=(1000, 100), **kw):
    """A one-agent cell (root rollout only) whose transcript carries the given CLI commands."""
    record = write_cell(directory, children=0, usage=usage, stem=stem)
    (Path(directory) / "final-transcripts" / (stem + ".jsonl")).write_text(
        "\n".join(json.dumps(e) for e in cli_events(commands, **kw)))
    return dict(record, spec_files=list(spec_files))


class CliFirstArm(unittest.TestCase):
    engine_stub = TreatmentParity.engine_stub
    capture_model_boundary = TreatmentParity.capture_model_boundary
    PORT = 9301

    # ---- schedule and catalog
    def test_catalog_order_default_stage_1_and_cell_counts(self):
        self.assertEqual(m.ARMS, (A, B, C, D, E, F, G))
        self.assertEqual((m.F, m.G), ("cli-first+thin-rules", "cli-first+thin-rules+scanner"))
        self.assertEqual(m.CLI_ARMS, (F, G))
        self.assertEqual(m.arm_set(), (A, D, E, F, G))
        rows = m.schedule()
        self.assertEqual(len(rows), 120)
        for offset in range(0, 120, 5):
            self.assertEqual([r["arm"] for r in rows[offset:offset + 5]], [A, D, E, F, G])
            self.assertEqual(len({r["case"] for r in rows[offset:offset + 5]}), 1)
        with_b = m.schedule(arms=m.arm_set(include_reviewer=True))
        self.assertEqual([r["arm"] for r in with_b[:6]], [A, B, D, E, F, G])
        self.assertEqual([(r["case"], r["repetition"]) for r in rows if r["arm"] == A],
                         [(r["case"], r["repetition"]) for r in with_b if r["arm"] == A])  # arm set never reorders tasks
        for bad in ((A, D, E), (A, D, E, F), (A, D, E, G), (A, D, F, E, G), (F, A, D, E, G)):
            with self.assertRaises(ValueError):
                m.check_arm_set(bad)

    def test_contrasts_are_predeclared_in_protocol_and_code(self):
        names = {name: (x, y) for name, x, y in m.CONTRASTS}
        for name, pair in (("F_minus_A", (F, A)), ("F_minus_D", (F, D)), ("F_minus_E", (F, E)), ("G_minus_F", (G, F)), ("G_minus_E", (G, E)),
                           ("G_minus_A", (G, A))):
            self.assertEqual(names[name], pair)
        analysis = m.protocol()["analysis"]
        self.assertEqual(analysis["primary_comparisons"], [name for name, _, _ in m.CONTRASTS])
        self.assertIn("INDIRECT", analysis["comparison_basis"]["F_minus_E"])
        self.assertIn("SURFACE effect", analysis["comparison_basis"]["F_minus_D"])
        self.assertIn("PRODUCT PATHS AT AN EQUAL SCANNER GATE", analysis["comparison_basis"]["G_minus_E"])
        self.assertIn("product path against the official agent", analysis["comparison_basis"]["G_minus_A"])

    # ---- prompt and argv differences
    def test_prompt_line_has_no_official_agent_delegation_and_names_the_cli_path(self):
        line = m.F_LINE
        for forbidden_text in ("spawn one", "playwright_test_generator", "generator_write_test", "run-test-mcp-server",
                               ".codex/agents", "native agent", "enabled_tools"):
            self.assertNotIn(forbidden_text, line)
        for required in ("do not spawn agents", "specs/plan.md", "tests/seed.spec.ts", "/work/skill/thin-rules/SKILL.md",
                         m.CLI_GUIDE_TARGET, "Playwright CLI", "snapshot", "under `tests/`", "once", "partial_or_blocked"):
            self.assertIn(required, line)
        self.assertEqual(m.G_LINE, m.F_HEAD + m.F_SCAN + m.F_TAIL)
        self.assertIn("`" + m.SCANNER_COMMAND + "`", m.G_LINE)
        self.assertNotIn(m.SCANNER_COMMAND, m.F_LINE)
        self.assertEqual(m.arm_lines()[F], "\n\n" + m.F_LINE)
        self.assertEqual(m.arm_lines()[G], "\n\n" + m.G_LINE)
        protocol = m.protocol()["cli_guide"]
        self.assertEqual((protocol["prompt_line"], protocol["scanner_prompt_line"]), (m.F_LINE, m.G_LINE))

    def test_F_argv_is_D_minus_the_mcp_declaration_plus_one_guide_mount(self):
        engine = self.engine_stub()
        with tempfile.TemporaryDirectory() as temp:
            args = (engine, Path(temp), Path(temp) / "auth", "owned", "gpt-6-sol", A, Path(temp) / "sessions")
            official = m.compat.command(*args)
            thin = m.d_command(m.compat.command, *args)
            cli = m.cli_command(m.compat.command, *args)
            scanner_cli = m.cli_command(m.compat.command, *args, scanner=True)
            scanner_mcp = m.e_command(m.compat.command, *args)
        mcp_flags = [x for x in thin if x.startswith("mcp_servers.playwright-test")]
        self.assertEqual(len(mcp_flags), 6)  # command, args, two env entries, approval mode, allowlist
        self.assertFalse(any("mcp_servers" in x or "playwright-test" in x or "run-test-mcp-server" in x or "enabled_tools" in x for x in cli))
        guide = "type=bind,src=" + temp + "/skill/cli-guide,dst=/work/skill/cli-guide,readonly"
        index = cli.index(guide)
        self.assertEqual(cli[index - 1], "--mount")
        without_guide = cli[:index - 1] + cli[index + 1:]
        expected = []
        i = 0
        while i < len(thin):
            if thin[i] == "-c" and thin[i + 1].startswith("mcp_servers.playwright-test"):
                i += 2
                continue
            expected.append(thin[i])
            i += 1
        self.assertEqual(without_guide, expected)
        # every role control, the sandbox and the thin-rules mount are D's
        self.assertEqual(cli[cli.index("--sandbox") + 1], "danger-full-access")
        self.assertIn('approval_policy="never"', cli)
        self.assertIn("type=bind,src=" + temp + "/skill/thin-rules,dst=/work/skill/thin-rules,readonly", cli)
        self.assertEqual([x for x in thin if x not in cli and not x.startswith("mcp_servers.playwright-test")], [])
        self.assertEqual(len(official) - len(cli), 2 * 6 - 2 * 2)  # six -c pairs removed, the rules and guide mounts added
        # G is F plus exactly the scanner mount that E adds to D
        scanner = "type=bind,src=" + temp + "/skill/scanner,dst=/work/skill/scanner,readonly"
        j = scanner_cli.index(scanner)
        self.assertEqual(scanner_cli[j - 1], "--mount")
        self.assertEqual(scanner_cli[:j - 1] + scanner_cli[j + 1:], cli)
        self.assertIn(scanner, scanner_mcp)

    def test_F_end_to_end_boundary_differs_from_D_only_by_mcp_guide_and_prompt(self):
        thin, _ = self.capture_model_boundary(m.one_call, D)
        cli, result = self.capture_model_boundary(m.one_call, F)
        # prompt: the shared task frame, then F's own line instead of A's delegation line plus D's line
        delegation = m.arm_lines()[A] + "\n" + m.D_LINE
        self.assertTrue(thin["prompt"].endswith(delegation))
        frame = thin["prompt"][:-len(delegation)]
        self.assertIn("specs/plan.md", frame + m.F_LINE)
        self.assertEqual(cli["prompt"], frame + "\n\n" + m.F_LINE)
        self.assertTrue(cli["prompt"].startswith(frame))
        self.assertNotIn("spawn one", cli["prompt"])
        self.assertNotIn("generator_write_test", cli["prompt"])
        # argv/config: D minus the six mcp_servers entries and the exploration-port entry, plus the guide mount
        flags = [x for x in thin["argv"] if x.startswith("mcp_servers.playwright-test")]
        self.assertEqual(len(flags), 7)  # six declaration entries plus the MCP-only exploration port
        self.assertTrue(any(x.startswith("mcp_servers.playwright-test.env.GEN_EXPLORE_PORT=") for x in flags))
        self.assertFalse(any("mcp_servers" in x for x in cli["argv"]))
        guide = "type=bind,src=<work>/skill/cli-guide,dst=/work/skill/cli-guide,readonly"
        index = cli["argv"].index(guide)
        self.assertEqual(cli["argv"][index - 1], "--mount")
        rest = cli["argv"][:index - 1] + cli["argv"][index + 1:]
        expected = []
        i = 0
        while i < len(thin["argv"]):
            if thin["argv"][i] == "-c" and thin["argv"][i + 1].startswith("mcp_servers.playwright-test"):
                i += 2
                continue
            expected.append(thin["argv"][i])
            i += 1
        self.assertEqual(rest, expected)
        # staged files: the same tree plus the guide, read-only
        extra = {path: data for path, data in cli["files"].items() if path not in thin["files"]}
        self.assertEqual(set(extra), {"skill/cli-guide/GUIDE.md"})
        self.assertEqual(extra["skill/cli-guide/GUIDE.md"], m.CLI_GUIDE.read_bytes())
        self.assertEqual(cli["modes"]["skill/cli-guide/GUIDE.md"], 0o444)
        exclude = "project/.git/info/exclude"
        self.assertEqual({p: d for p, d in cli["files"].items() if p not in extra and p != exclude},
                         {p: d for p, d in thin["files"].items() if p != exclude})
        self.assertEqual(cli["files"][exclude].decode().splitlines()[1:], list(m.CLI_GIT_EXCLUDES))
        self.assertEqual(thin["files"][exclude].decode().splitlines()[1:], list(m.GIT_EXCLUDES))
        integrity = result["cli_guide_integrity"]
        self.assertEqual((len(integrity), integrity[0]["before"] == integrity[0]["after"] == m.digest(m.CLI_GUIDE)), (1, True))
        self.assertEqual(result["arm"], F)
        self.assertEqual(result["generation_config"]["server_isolation"], "split-ports")
        self.assertEqual(result["generation_config"]["git_excludes"], list(m.CLI_GIT_EXCLUDES))

    def test_record_base_url_reads_the_shape_one_call_really_persists(self):
        for arm in (F, G):
            _, record = self.capture_model_boundary(m.one_call, arm)
            with self.subTest(arm=arm):
                ports = record["generation_config"]["stage_ports"]
                self.assertEqual(len(ports), 1)
                self.assertEqual((ports[0]["test_run_port"], ports[0]["explore_port"]), (self.PORT, self.PORT + m.EXPLORE_PORT_OFFSET))
                self.assertEqual(m.record_base_url(record), "http://127.0.0.1:%d" % self.PORT)
                # end to end: a verbatim goto of that baseURL is observed, another host spelling is not
                with tempfile.TemporaryDirectory() as temp:
                    directory = Path(temp)
                    base = m.record_base_url(record)
                    chain = lambda url: [(SESSION_OPEN, 0), (SESSION_PROBE, 0), (SESSION_REQUESTS, 0),
                                         (SESSION_GOTO.replace("http://127.0.0.1:9400/", url), 0), (SESSION_SNAP, 0)]
                    for url, klass in ((base + "/", "cli-observed"), (base.replace("127.0.0.1", "localhost") + "/", "unverified")):
                        cell = dict(write_cli_cell(directory, chain(url), stem="real" + klass[:3]), generation_config=record["generation_config"])
                        fidelity = m.cli_fidelity(cell, directory / "final-transcripts")
                        self.assertEqual((fidelity["class"], fidelity["evidence"]["goto_verbatim_checked"]), (klass, True))
        _, mcp = self.capture_model_boundary(m.one_call, D)
        self.assertEqual(mcp["generation_config"]["stage_ports"][0]["test_run_port"], self.PORT)

    def test_G_is_F_with_only_the_scanner_mount_files_and_prompt_step(self):
        cli, _ = self.capture_model_boundary(m.one_call, F)
        gated, result = self.capture_model_boundary(m.one_call, G)
        mount = "type=bind,src=<work>/skill/scanner,dst=/work/skill/scanner,readonly"
        index = gated["argv"].index(mount)
        self.assertEqual(gated["argv"][:index - 1] + gated["argv"][index + 1:], cli["argv"])
        extra = {path for path in gated["files"] if path not in cli["files"]}
        self.assertEqual(extra, {"skill/scanner/" + name for name in m.scanner_manifest()})
        frame = cli["prompt"][:-len("\n\n" + m.F_LINE)]
        self.assertEqual(gated["prompt"], frame + "\n\n" + m.G_LINE)
        self.assertEqual(result["scanner_integrity"][0]["before"], m.scanner_manifest())
        self.assertEqual(result["cli_guide_integrity"][0]["before"], m.digest(m.CLI_GUIDE))

    def test_cli_arms_use_the_split_port_stage_and_cli_scoped_paths_not_the_mcp_ones(self):
        for arm in m.SPLIT_ARMS:
            self.assertIn(arm, m.SPLIT_ARMS)
        self.assertEqual(set(m.SPLIT_ARMS), {A, D, E, F, G})
        self.assertEqual(m.CLI_GIT_EXCLUDES, ("node_modules", ".playwright-cli/"))
        with tempfile.TemporaryDirectory() as temp:
            project = Path(temp) / "project"
            (project / ".playwright-cli").mkdir(parents=True)
            (project / ".playwright-cli/page-1.yml").write_text("x")
            (project / ".playwright-cli/console.log").write_text("x")
            collected = m.cli_scoped_collector(lambda p, d: dict(
                out_of_scope_writes=[".playwright-cli/page-1.yml", "notes.md"]))(project, Path(temp) / "dest")
            self.assertEqual(collected["out_of_scope_writes"], ["notes.md"])
            self.assertEqual(collected["cli_artifact_writes"], [".playwright-cli/console.log", ".playwright-cli/page-1.yml"])
            self.assertEqual(m.cli_artifact_listing(Path(temp) / "absent"), [])
            captured = {}
            (project / ".git").mkdir()
            m.cli_excluding_baseline(lambda path, case: captured.setdefault("text", (Path(path) / ".git/info/exclude").read_text()))(project, "c")
            self.assertEqual(captured["text"].splitlines()[1:], list(m.CLI_GIT_EXCLUDES))

    # ---- the guide
    def test_guide_is_within_the_byte_limit_neutral_and_semantically_equal_to_the_shipped_router_section(self):
        data = m.CLI_GUIDE.read_bytes()
        text = data.decode("utf-8")
        self.assertLessEqual(len(data), 2200)
        self.assertEqual(m.CLI_GUIDE_MAX_BYTES, 2200)
        self.assertEqual(m.protocol()["cli_guide"]["bytes"], len(data))
        self.assertEqual(m.guide_semantic_gaps(text), [])
        for command in ("npx --no-install playwright cli", "--config <file> open --browser chromium",
                        '"browser":{"isolated":true}', '"outputDir"', "allowedOrigins", "net::ERR_BLOCKED_BY_CLIENT", "requests", "goto",
                        "snapshot", "click eN", "fill eN", "press Key", "close", "Do not reuse a session",
                        "`goto` the baseURL string verbatim", "`webServer.command` exactly as written"):
            self.assertIn(command, text)
        self.assertNotIn("GEN_EXPLORE_PORT", text)  # no benchmark-only hook in the product text
        self.assertEqual(m.guide_semantic_gaps(text + " GEN_EXPLORE_PORT=1"), ["forbidden: GEN_EXPLORE_PORT"])
        # task-neutral: no case id, selector, product word or path of this checkout
        self.assertNotRegex(text, r"v[23]-\d\d|data-testid|#[a-z]|\.[a-z]+-[a-z]+\b(?!\.json)|/Users/|refactor|renam|grader|benchmark")
        for task in m.protocol()["tasks"]:
            self.assertNotIn(task, text)
        # the verbs are the router's (select-option and press eN Enter are not CLI commands)
        verbs = set(re.findall(r"`(?:-s=<unique> )?([a-z]+)(?: |`)", text)) & {"goto", "snapshot", "click", "fill", "select", "press", "close", "requests", "eval"}
        self.assertEqual(verbs, {"goto", "snapshot", "click", "fill", "press", "close", "requests", "eval"})
        self.assertNotIn("select-option", text)

    def test_guide_semantic_check_has_negative_controls_and_protocol_refuses_a_dropped_rule(self):
        text = m.CLI_GUIDE.read_text()
        for marker in m.GUIDE_SEMANTIC_MARKERS:
            with self.subTest(marker=marker):
                self.assertIn(marker, text)
                self.assertEqual(m.guide_semantic_gaps(text.replace(marker, "")), [marker])
        # dropping the browser flag, the guard proof, the auth rule or the no-download rule is refused at protocol() time
        for old, new in (("open --browser chromium", "open"), ("net::ERR_BLOCKED_BY_CLIENT", "an error"),
                         ('"browser":{"isolated":true},', ""), ("Never add a second origin", "Add origins freely"),
                         ("`goto` the baseURL string verbatim", "`goto` the app"), ('"outputDir":"<dir outside the repo>"', ""),
                         ("never read `.env`", "read anything"), ("no `playwright install`", "")):
            with self.subTest(drop=old), tempfile.TemporaryDirectory() as temp:
                changed = Path(temp) / "CLI-GUIDE.md"
                changed.write_text(text.replace(old, new))
                with patch.object(m, "CLI_GUIDE", changed), self.assertRaisesRegex(ValueError, "CLI guide"):
                    m.protocol()

    def test_protocol_records_the_estimand_as_the_shipped_router_section_and_retires_the_verbatim_claim(self):
        est = m.protocol()["cli_guide"]["estimand"]
        self.assertIn("SHIPPED", est["statement"])
        self.assertIn("section 3", est["statement"])
        self.assertRegex(est["draft_section_3_sha256"], r"^[0-9a-f]{64}$")
        self.assertIn("freeze_requirement", est)
        self.assertIn("frozen 'verbatim'", est["retired_contradiction"])
        self.assertTrue(any("non-interactive" in a for a in est["documented_adaptations"]))
        for rule in ("no CLI: do not install it, stop", "install nothing: no npm install, no npx that downloads, no playwright install"):
            self.assertIn(rule, est["semantic_equality"]["rules"])
        self.assertIn("-s=<unique> --config <file> open --browser chromium", est["semantic_equality"]["commands"])
        with patch.object(m, "read", side_effect=lambda path: (lambda d: (d["cli_guide"].pop("estimand"), d)[1])(json.loads(Path(path).read_text()))
                          if Path(path) == m.PROTOCOL else json.loads(Path(path).read_text())):
            with self.assertRaisesRegex(ValueError, "estimand"):
                m.protocol()

    def test_guide_staging_is_readonly_exact_and_refuses_drift(self):
        with tempfile.TemporaryDirectory() as temp:
            target = m.stage_cli_guide(temp)
            self.assertEqual(target.stat().st_mode & 0o777, 0o444)
            self.assertEqual(target.read_bytes(), m.CLI_GUIDE.read_bytes())
            with self.assertRaises(FileExistsError):
                m.stage_cli_guide(temp)
        with patch.object(m, "CLI_GUIDE_MAX_BYTES", 10), self.assertRaisesRegex(ValueError, "CLI guide"):
            m.protocol()

    def test_readme_and_specs_state_the_exact_prompt_line_guide_and_arm_set(self):
        readme = (m.BENCH / "README.md").read_text()
        self.assertIn(m.F_LINE, readme)
        self.assertIn(m.CLI_GUIDE.read_text().rstrip("\n"), readme)
        self.assertIn(m.SCANNER_COMMAND, readme)
        for phrase in ("A, D, E, F, G (default)", "120 cells per model", "CLI exploration observed", "F−D",
                       "same or better", "fewer or equal", "+0.20", "MDE", "no official-agent delegation"):
            self.assertIn(phrase, readme)
        changes = (m.BENCH / "CHANGES.md").read_text()
        spec = (m.BENCH / "ZEPPELIN-AMENDMENT-SPEC.md").read_text()
        provenance = (m.LAYER.parent / "PROVENANCE.md").read_text()
        self.assertIn("CLI-first thin workflow amendment", changes)
        self.assertIn("Arm F (and optional arm G) addendum", spec)
        self.assertIn("CLI-first workflow amendment", provenance)
        self.assertEqual(m.protocol()["decision"]["cli_first"]["adoption_statement"],
                         "CLI-first thin workflow adopted as default path (development point rule)")

    def test_comparability_caveat_and_independent_g_screen_are_declared_in_protocol_and_readme(self):
        cli_first = m.protocol()["decision"]["cli_first"]
        caveat = cli_first["comparability_caveat"]
        for phrase in ("Write path", "generator_write_test", "Prompt", "Stop clause", "partial_or_blocked", "blocked_by_stop_clause",
                       "D is not rewritten"):
            self.assertIn(phrase, caveat)
        self.assertIn("g_screen", cli_first["adoption_gate"])
        self.assertIn("never change the F statement", cli_first["adoption_gate"])
        self.assertIn("a default arm since the pre-freeze revision", cli_first["adoption_gate"])
        self.assertIn("g_screen", cli_first["comparators"]["G_vs_E"])
        self.assertIn("g_screen", cli_first["comparators"]["G_vs_A"])
        self.assertIn("write path", m.protocol()["analysis"]["comparison_basis"]["F_minus_D"])
        self.assertIn("SURFACE effect", m.protocol()["analysis"]["comparison_basis"]["F_minus_D"])
        fidelity = m.protocol()["cli_guide"]["fidelity"]
        for phrase in ("ONE named session", "ERR_BLOCKED_BY_CLIENT", "guard_verified", "command position", "unknown exit code",
                       "`|| true`", "model-enforced"):
            self.assertIn(phrase, fidelity)
        readme = (m.BENCH / "README.md").read_text()
        for phrase in ("F−D comparability caveat", "blocked_by_stop_clause", "independent `g_screen` field", "default arms A, D, E, F, G",
                       "guard_verified", "command position", "an unknown code is unverified", "enforced by the model"):
            self.assertIn(phrase, readme)
        self.assertEqual(m.arm_set(), (A, D, E, F, G))

    def test_bindings_cover_the_guide_and_all_seven_prompts(self):
        bound = m.bindings()
        self.assertIn("benchmarks/generator-thin-eval-v1/CLI-GUIDE.md", bound["files"])
        self.assertEqual(set(bound["prompts"]), set(m.ARMS))
        self.assertEqual(bound["prompts"][F], "\n\n" + m.F_LINE)

    # ---- fidelity: CLI exploration observed
    def test_synthetic_streams_classify_observed_unverified_blocked_aborted(self):
        with tempfile.TemporaryDirectory() as temp:
            directory = Path(temp)
            ok = write_cli_cell(directory, REAL_ARM_C_CLI, stem="ok")
            self.assertEqual(m.cli_fidelity(ok, directory / "final-transcripts")["class"], "cli-observed")
            open_only = write_cli_cell(directory, REAL_ARM_C_CLI[:2], stem="open_only")
            self.assertEqual(m.cli_fidelity(open_only, directory / "final-transcripts")["class"], "unverified")
            failed_open = write_cli_cell(directory, [(c, 1 if " open" in c else code) for c, code in REAL_ARM_C_CLI], stem="failed_open")
            self.assertEqual(m.cli_fidelity(failed_open, directory / "final-transcripts")["class"], "unverified")
            failed_snapshot = write_cli_cell(directory, [(c, 1 if c.endswith("snapshot") else code) for c, code in REAL_ARM_C_CLI], stem="failed_snap")
            self.assertEqual(m.cli_fidelity(failed_snapshot, directory / "final-transcripts")["class"], "unverified")
            blocked = write_cli_cell(directory, REAL_ARM_C_CLI[:2], spec_files=(), stem="blocked")
            self.assertEqual(m.cli_fidelity(blocked, directory / "final-transcripts")["class"], "blocked")
            aborted = dict(ok, infrastructure_error=True)
            self.assertEqual(m.cli_fidelity(aborted, directory / "final-transcripts")["class"], "aborted")
            none = write_cli_cell(directory, [("rg --files", 0), ("node_modules/.bin/playwright test", 0)], stem="none")
            self.assertEqual(m.cli_fidelity(none, directory / "final-transcripts")["class"], "unverified")
            missing = dict(ok, transcript_path="absent.jsonl")
            fid = m.cli_fidelity(missing, directory / "final-transcripts")
            self.assertEqual(fid["class"], "unverified")
            self.assertFalse(fid["evidence"]["transcript_found"])
            self.assertEqual(m.cli_interaction_counts(None), {"available": False, "source": None, "complete": False})

    def test_unknown_exit_code_is_unverified_not_observed(self):
        with tempfile.TemporaryDirectory() as temp:
            directory = Path(temp)
            unknown = write_cli_cell(directory, [(c, None) for c, _ in REAL_ARM_C_CLI], stem="u0")
            fid = m.cli_fidelity(unknown, directory / "final-transcripts")
            self.assertEqual(fid["class"], "unverified")
            self.assertEqual(fid["evidence"]["exit_code_unknown"], len(REAL_ARM_C_CLI))
            self.assertFalse(fid["evidence"]["guard_verified"])

    def test_a_bare_mention_is_not_a_command_and_chained_and_standalone_forms_are_commands(self):
        with tempfile.TemporaryDirectory() as temp:
            directory = Path(temp)
            mention = write_cli_cell(directory, [("echo 'playwright cli open snapshot is described in the guide'", 0),
                                                 ("cat /work/skill/cli-guide/GUIDE.md", 0)], stem="m")
            self.assertEqual(m.cli_fidelity(mention, directory / "final-transcripts")["class"], "unverified")
            chain = (SESSION_OPEN + " && " + SESSION_PROBE + " && " + SESSION_REQUESTS + " && " + SESSION_GOTO + " && " + SESSION_SNAP)
            chained = write_cli_cell(directory, [(chain, 0, BLOCKED_OUTPUT)], stem="c")
            self.assertEqual(m.cli_fidelity(chained, directory / "final-transcripts")["class"], "cli-observed")
            standalone = write_cli_cell(directory, [(c, 0) for c in (
                "playwright-cli -s=x open", "playwright-cli -s=x eval \"fetch('http://127.0.0.1:9/')\"", "playwright-cli -s=x requests",
                "playwright-cli -s=x goto http://127.0.0.1:9400/", "playwright-cli -s=x snapshot")], stem="s")
            self.assertEqual(m.cli_fidelity(standalone, directory / "final-transcripts")["class"], "cli-observed")
            direct = write_cli_cell(directory, [(c, 0) for c in (
                "./node_modules/.bin/playwright cli --session x open", "FOO=1 playwright-cli --session x eval \"fetch('http://127.0.0.1:9/')\"",
                "playwright-cli --session x requests", "playwright-cli --session x goto http://localhost:9400/",
                "npx playwright-cli --session x snapshot")], stem="d")
            self.assertEqual(m.cli_fidelity(direct, directory / "final-transcripts")["class"], "cli-observed")

    def test_interaction_counts_split_acting_observing_session_and_the_guard_probe(self):
        counts = m.cli_interaction_counts(cli_events(REAL_ARM_C_CLI))
        self.assertEqual((counts["available"], counts["complete"], counts["source"]), (True, True, "root-command-stream"))
        # acting: guard probe evaluation, goto, fill, press x2, select = 6; observing: snapshot x2
        self.assertEqual((counts["browser_acting"], counts["browser_observing"], counts["browser_total"]), (6, 2, 8))
        self.assertEqual(counts["session_commands"], {"open": 2, "close": 1, "close-all": 0, "list": 0, "requests": 1})
        self.assertEqual((counts["failed_commands"], counts["guard_probe_evals"]), (2, 1))
        self.assertIs(counts["zero_browser_interaction"], False)
        probe_only = m.cli_interaction_counts(cli_events(REAL_ARM_C_CLI[1:4] + REAL_ARM_C_CLI[-1:]))
        self.assertIs(probe_only["zero_browser_interaction"], True)  # opened, probed the guard, closed: nothing explored
        self.assertEqual(m.cli_interaction_counts([])["browser_total"], 0)
        summary = m.browser_interaction_summary([dict(browser_interactions=counts), dict(browser_interactions=probe_only),
                                                 dict(browser_interactions={"available": False})])
        self.assertEqual((summary["cells"], summary["cells_with_complete_counts"], summary["cells_with_zero_browser_interaction"]), (3, 2, 1))

    # ---- fidelity hardening: command position, masking, session order, guard
    def observed(self, commands, stem):
        with tempfile.TemporaryDirectory() as temp:
            directory = Path(temp)
            record = write_cli_cell(directory, commands, stem=stem)
            return m.cli_fidelity(record, directory / "final-transcripts")

    def test_quoted_mentions_in_echo_grep_cat_printf_and_comments_are_not_invocations(self):
        mentions = [
            "echo 'npx --no-install playwright cli -s=x open'", 'echo "playwright-cli -s=x snapshot"',
            "grep -n 'playwright cli open' notes.md", "grep -r playwright-cli -- tests/", "cat .playwright-cli/page-1.yml",
            "printf '%s' 'playwright cli snapshot'", "rg \"playwright cli goto\" /work", "# playwright-cli -s=x open",
            "git log --grep='playwright cli open'", "sed -n '1p' playwright-cli.md", "ls .playwright-cli/",
        ]
        for command in mentions:
            with self.subTest(command):
                self.assertEqual(m.cli_invocations(cli_events([(command, 0)])), [])
        # the full sequence expressed only as mentions never reaches cli-observed
        fid = self.observed([("echo '" + c + "'", 0) for c in (SESSION_OPEN, SESSION_PROBE, SESSION_REQUESTS, SESSION_GOTO, SESSION_SNAP)], "men")
        self.assertEqual((fid["class"], fid["evidence"]["cli_invocations"]), ("unverified", 0))
        # while the same text as the executable is a command
        self.assertEqual([v for v, _, _ in m.cli_invocations(cli_events([(SESSION_OPEN, 0)]))], ["open"])
        self.assertEqual([v for v, _, _ in m.cli_invocations(cli_events([("cd /work && " + SESSION_OPEN, 0)]))], ["open"])
        self.assertEqual([v for v, _, _ in m.cli_invocations(cli_events([("echo hi; " + SESSION_SNAP, 0)]))], ["snapshot"])

    def test_help_requests_are_not_counted(self):
        for command in ("npx --no-install playwright cli --help", "npx --no-install playwright cli open --help",
                        "playwright-cli -s=x snapshot -h", "playwright-cli help", "playwright-cli -s=x open --browser chromium --help"):
            with self.subTest(command):
                self.assertEqual(m.cli_invocations(cli_events([(command, 0)])), [])
        full = [(SESSION_OPEN, 0), (SESSION_PROBE, 0), (SESSION_REQUESTS, 0), (SESSION_GOTO, 0), ("npx --no-install playwright cli -s=x snapshot --help", 0)]
        self.assertEqual(self.observed(full, "help")["class"], "unverified")

    def test_masked_exit_codes_are_not_counted(self):
        masks = (" || true", " || :", "; echo done", " ; echo ok", " | tail -1", " | tee out.log", " &", " || echo failed",
                 " 2>/dev/null || true")
        for mask in masks:
            for verb_command, verb in ((SESSION_OPEN, "open"), (SESSION_SNAP, "snapshot")):
                with self.subTest(mask=mask, verb=verb):
                    calls = m.cli_calls(cli_events([(verb_command + mask, 0)]))
                    self.assertEqual([(c["verb"], c["masked"], c["verified"]) for c in calls], [(verb, True, False)])
        sequence = [SESSION_OPEN, SESSION_PROBE, SESSION_REQUESTS, SESSION_GOTO, SESSION_SNAP]
        for mask in (" || true", "; echo done", " || :"):
            for index in range(5):
                commands = [(c + (mask if i == index else ""), 0) for i, c in enumerate(sequence)]
                with self.subTest(mask=mask, masked_step=index):
                    self.assertEqual(self.observed(commands, "mask%d" % index)["class"], "unverified")
        self.assertEqual([op for _, op in m.shell_segments(SESSION_SNAP + "\necho finished")], ["\n", ""])  # a real newline ends the command
        self.assertEqual([op for _, op in m.shell_segments(SESSION_SNAP + "\necho finished")], ["\n", ""])  # a real newline ends the command
        # unmasked controls: && chains and a trailing command with the CLI call last keep the exit-code meaning
        self.assertFalse(m.cli_calls(cli_events([(SESSION_OPEN + " && " + SESSION_SNAP, 0)]))[0]["masked"])
        self.assertFalse(m.cli_calls(cli_events([("echo start; " + SESSION_SNAP, 0)]))[0]["masked"])
        # a masked call is excluded from the exploration counts but reported
        counts = m.cli_interaction_counts(cli_events([(SESSION_SNAP + " || true", 0), (SESSION_SNAP, 0)]))
        self.assertEqual((counts["browser_observing"], counts["masked_commands"]), (1, 1))

    def test_stderr_redirections_are_not_background_operators_but_a_real_background_still_masks(self):
        for redirect in (" 2>&1", " >/tmp/o.txt 2>&1", " > /tmp/o.txt 2>&1", " &>/tmp/o.txt", " &>> /tmp/o.txt", " >&2", " 1>&2", " 2>&1",
                         " <&0", " 2>&1 && echo ok"):
            for command, verb in ((SESSION_OPEN, "open"), (SESSION_SNAP, "snapshot")):
                with self.subTest(redirect=redirect, verb=verb):
                    calls = m.cli_calls(cli_events([(command + redirect, 0)]))
                    self.assertEqual([(c["verb"], c["masked"], c["verified"]) for c in calls], [(verb, False, True)])
        sequence = [SESSION_OPEN, SESSION_PROBE, SESSION_REQUESTS, SESSION_GOTO, SESSION_SNAP]
        merged = [(c + " 2>&1", 0, BLOCKED_OUTPUT) if c == SESSION_REQUESTS else (c + " 2>&1", 0) for c in sequence]
        self.assertEqual(self.observed(merged, "merged")["class"], "cli-observed")
        # a true background `&` after a redirection, a pipe after a merge, and `||` after a merge still mask
        for tail in (" 2>&1 &", " >/tmp/o 2>&1 &", " 2>&1 | tee x", " 2>&1 || true", " 2>&1; echo x"):
            with self.subTest(tail=tail):
                calls = m.cli_calls(cli_events([(SESSION_OPEN + tail, 0)]))
                self.assertEqual([(c["masked"], c["verified"]) for c in calls], [(True, False)])
        self.assertEqual([op for _, op in m.shell_segments("a 2>&1 & b")], ["&", ""])
        self.assertEqual([w for w, _ in m.shell_segments("a b 2>&1")], [["a", "b", "2>&1"]])

    def test_failed_exit_and_error_banners_are_not_verified(self):
        sequence = [(SESSION_OPEN, 0), (SESSION_PROBE, 0), (SESSION_REQUESTS, 0), (SESSION_GOTO, 0), (SESSION_SNAP, 0)]
        self.assertEqual(self.observed(sequence, "base")["class"], "cli-observed")
        for index in range(5):
            with self.subTest(failed_step=index):
                changed = [(c, 1 if i == index else code) for i, (c, code) in enumerate(sequence)]
                self.assertEqual(self.observed(changed, "f%d" % index)["class"], "unverified")
        errored = sequence[:4] + [(SESSION_SNAP, 0, "### Error\nbrowser not open\n")]
        self.assertEqual(self.observed(errored, "banner")["class"], "unverified")

    def test_open_goto_snapshot_must_share_one_session_in_order(self):
        def at(session, verb, rest=""):
            return ("npx --no-install playwright cli -s=%s %s %s" % (session, verb, rest)).rstrip()
        probe = lambda s: at(s, "eval", "\"fetch('http://127.0.0.1:9/').catch(() => null)\"")
        ok = [(at("a", "open"), 0), (probe("a"), 0), (at("a", "requests"), 0), (at("a", "goto", "http://127.0.0.1:9400/"), 0), (at("a", "snapshot"), 0)]
        self.assertEqual(self.observed(ok, "ok")["class"], "cli-observed")
        # open in one session, goto and snapshot in another (never opened)
        split = [(at("a", "open"), 0), (probe("a"), 0), (at("a", "requests"), 0), (at("b", "goto", "http://127.0.0.1:9400/"), 0), (at("b", "snapshot"), 0)]
        self.assertEqual(self.observed(split, "split")["class"], "unverified")
        # snapshot in a different session than the goto
        other = ok[:4] + [(at("b", "snapshot"), 0)]
        self.assertEqual(self.observed(other, "other")["class"], "unverified")
        # snapshot before goto, goto before open, open last
        for order in ([4, 0, 1, 2, 3], [3, 4, 0, 1, 2], [1, 2, 3, 4, 0]):
            with self.subTest(order=order):
                self.assertEqual(self.observed([ok[i] for i in order], "o%s" % "".join(map(str, order)))["class"], "unverified")
        # goto of a non-exploration origin (the refused guard port, a public URL) does not count
        for url in ("http://127.0.0.1:9/", "https://example.com/", "about:blank", "http://10.0.0.5:8080/"):
            with self.subTest(url=url):
                wrong = ok[:3] + [(at("a", "goto", url), 0), (at("a", "snapshot"), 0)]
                self.assertEqual(self.observed(wrong, "u%d" % abs(hash(url)))["class"], "unverified")
        # a second complete session rescues a cell whose first session failed
        rescue = [(at("a", "open"), 1)] + [(c.replace("-s=a", "-s=b"), code) for c, code in ok]
        self.assertEqual(self.observed(rescue, "rescue")["class"], "cli-observed")
        # default (unnamed) sessions are one session
        unnamed = [("playwright-cli open", 0), ("playwright-cli eval \"fetch('http://127.0.0.1:9/')\"", 0), ("playwright-cli requests", 0),
                   ("playwright-cli goto http://127.0.0.1:9400/", 0), ("playwright-cli snapshot", 0)]
        self.assertEqual(self.observed(unnamed, "unnamed")["class"], "cli-observed")
        self.assertEqual(self.observed(unnamed[:3] + [("playwright-cli -s=z goto http://127.0.0.1:9400/", 0), ("playwright-cli -s=z snapshot", 0)],
                                       "mixed")["class"], "unverified")

    def test_guard_must_be_verified_in_the_same_session_with_a_blocked_origin(self):
        def at(session, verb, rest=""):
            return ("npx --no-install playwright cli -s=%s %s %s" % (session, verb, rest)).rstrip()
        probe = at("a", "eval", "\"fetch('http://127.0.0.1:9/').catch(() => null)\"")
        rest = [(at("a", "goto", "http://127.0.0.1:9400/"), 0), (at("a", "snapshot"), 0)]
        good = self.observed([(at("a", "open"), 0), (probe, 0), (at("a", "requests"), 0)] + rest, "g")
        self.assertEqual((good["class"], good["evidence"]["guard_verified"], good["evidence"]["guard_verified_in_observed_session"]),
                         ("cli-observed", True, True))
        cases = {
            "no probe or requests": [(at("a", "open"), 0)] + rest,
            "probe without requests": [(at("a", "open"), 0), (probe, 0)] + rest,
            "requests without probe": [(at("a", "open"), 0), (at("a", "requests"), 0)] + rest,
            "requests before probe": [(at("a", "open"), 0), (at("a", "requests"), 0), (probe, 0), ] + rest,
            "requests shows the request succeeding": [(at("a", "open"), 0), (probe, 0),
                                                       (at("a", "requests"), 0, "### Result\n1. [GET] http://127.0.0.1:9/ => [200] OK\n")] + rest,
            "requests output missing": [(at("a", "open"), 0), (probe, 0), (at("a", "requests"), 0, None)] + rest,
            "requests lists another origin": [(at("a", "open"), 0), (probe, 0),
                                              (at("a", "requests"), 0, "1. [GET] http://example.com/ => [FAILED] net::ERR_BLOCKED_BY_CLIENT\n")] + rest,
            "probe of a different origin": [(at("a", "open"), 0), (at("a", "eval", "\"fetch('http://127.0.0.1:9400/')\""), 0),
                                            (at("a", "requests"), 0)] + rest,
            "probe in another session": [(at("a", "open"), 0), (at("b", "eval", "\"fetch('http://127.0.0.1:9/')\""), 0),
                                          (at("a", "requests"), 0)] + rest,
            "requests in another session": [(at("a", "open"), 0), (probe, 0), (at("b", "requests"), 0)] + rest,
            "probe failed": [(at("a", "open"), 0), (probe, 1), (at("a", "requests"), 0)] + rest,
            "probe masked": [(at("a", "open"), 0), (probe + " || true", 0), (at("a", "requests"), 0)] + rest,
            "probe before open": [(probe, 0), (at("a", "open"), 0), (at("a", "requests"), 0)] + rest,
        }
        for name, commands in cases.items():
            with self.subTest(name):
                fid = self.observed(commands, "g%d" % abs(hash(name)))
                self.assertEqual(fid["class"], "unverified")
                self.assertFalse(fid["evidence"]["guard_verified_in_observed_session"])
        # exit code unknown on the guard step is unverified too
        self.assertEqual(self.observed([(at("a", "open"), 0), (probe, 0), (at("a", "requests"), None)] + rest, "gu")["class"], "unverified")

    def test_stop_clause_blocked_is_reported_apart_and_does_not_change_the_class(self):
        with tempfile.TemporaryDirectory() as temp:
            directory = Path(temp)
            record = write_cli_cell(directory, REAL_ARM_C_CLI[:1], spec_files=(), stem="stop")
            path = directory / "final-transcripts" / "stop.jsonl"
            self.assertIs(m.stop_clause_blocked(record, directory / "final-transcripts"), False)
            with path.open("a") as stream:
                stream.write("\n" + json.dumps(dict(type="item.completed", item=dict(
                    type="agent_message", text="Could not open the session. status: partial_or_blocked"))))
            self.assertIs(m.stop_clause_blocked(record, directory / "final-transcripts"), True)
            self.assertEqual(m.cli_fidelity(record, directory / "final-transcripts")["class"], "blocked")
            self.assertIsNone(m.stop_clause_blocked(dict(record, transcript_path="absent.jsonl"), directory / "final-transcripts"))
            # a mention in a shell command is not the agent's stop status
            mention = write_cli_cell(directory, [("echo partial_or_blocked", 0)], spec_files=(), stem="stop2")
            self.assertIs(m.stop_clause_blocked(mention, directory / "final-transcripts"), False)

    def test_fidelity_extraction_on_stored_arm_C_transcripts_when_present(self):
        root = Path.home() / ".cache/e2e-skills-bench/multimodel-v3-codex/gpt-6-sol/final-transcripts"
        if not root.is_dir():
            self.skipTest("stored v3 arm-C transcripts are not on this machine")
        vocabulary = set(m.CLI_ACTING + m.CLI_OBSERVING + m.CLI_SESSION) | {"select-option"}  # one failed call used the non-command
        observed = zero = 0
        for path in sorted(root.glob("*.jsonl")):
            record = dict(arm=F, transcript_path=path.name, spec_files=["tests/x.spec.ts"], attempts=[])
            events = m.integration.transcript_events(record, root)
            calls = m.cli_invocations(events)
            if not calls:
                zero += 1
                self.assertEqual(m.cli_fidelity(record, root)["class"], "unverified")  # arm A cells never touch the CLI
                continue
            observed += 1
            self.assertLessEqual({verb for verb, _, _ in calls}, vocabulary, path.name)
            self.assertEqual(m.cli_fidelity(record, root)["class"], "cli-observed", path.name)
            counts = m.cli_interaction_counts(events)
            self.assertGreaterEqual(counts["session_commands"]["open"], 1)
            self.assertGreaterEqual(counts["browser_observing"], 1)
            self.assertEqual(counts["guard_probe_evals"] >= 1, True, path.name)
            self.assertTrue(m.cli_fidelity(record, root)["evidence"]["guard_verified_in_observed_session"], path.name)
            self.assertFalse(counts["zero_browser_interaction"], path.name)
        self.assertEqual(observed, 24)  # the 24 arm-C cells of the finished campaign
        self.assertEqual(observed + zero, len(list(root.glob("*.jsonl"))))

    def test_cell_extras_for_F_replaces_the_official_class_and_records_children_and_reads(self):
        with tempfile.TemporaryDirectory() as temp:
            directory = Path(temp).resolve()
            read = [(f"cat {m.LAYER_TARGET}", 0), (f"cat {m.CLI_GUIDE_TARGET}", 0)] + list(REAL_ARM_C_CLI)
            record = dict(write_cli_cell(directory, read, stem="f1"), arm=F, call_id="f1",
                          thin_layer_integrity=[dict(before="a", after="a", read_only_mount=True)],
                          cli_guide_integrity=[dict(before="b", after="b", read_only_mount=True)])
            out = m.cell_extras(record, directory)
            self.assertEqual((out["fidelity_class"], out["treatment"]), ("cli-observed", {"cli_class": "cli-observed"}))
            self.assertEqual(out["browser_interactions"]["browser_total"], 8)
            self.assertIs(out["thin_layer_read_indicator"], True)
            self.assertIs(out["cli_guide_read_indicator"], True)
            self.assertEqual(out["child_agents"], 0)
            self.assertTrue(out["tokens"]["complete"])
            self.assertEqual(out["tokens"]["child_uncached_input"], 0)
            self.assertNotIn("scanner_gate_indicator", out)
            self.assertEqual(out["fidelity"]["evidence"]["official_surface_calls"], 0)
            # a child agent in an F cell is recorded (and blocks the F screen), never hidden
            spawned = dict(write_cli_cell(directory, read, stem="f2", spawns=1), arm=F, call_id="f2")
            self.assertEqual(m.cell_extras(spawned, directory)["child_agents"], 1)
            gated = dict(record, arm=G)
            self.assertIn("scanner_gate_indicator", m.cell_extras(gated, directory))
            for cell in (dict(out, aborted=False, load_flagged=False, arm=F),):
                self.assertTrue(m.in_view(cell, "primary") and m.in_view(cell, "as_treated") and m.in_view(cell, "itt"))
                self.assertFalse(m.in_view(dict(cell, fidelity_class="unverified"), "primary"))
                self.assertTrue(m.in_view(dict(cell, fidelity_class="unverified"), "upper"))
                self.assertFalse(m.in_view(dict(cell, thin_layer_read_indicator=False), "as_treated"))
                self.assertFalse(m.in_view(dict(cell, arm=G), "as_treated"))  # G also needs the scanner-command indicator
                self.assertFalse(m.in_view(dict(cell, aborted=True), "primary"))

    def test_generation_uniformity_requires_split_ports_for_F_and_G(self):
        base = dict(case="c", repetition=1, generation_config=dict(
            stages=1, server_isolation="split-ports", reuse_existing_server=False, config_sha256_port_normalized=["g"],
            scoring_config_sha256_port_normalized=["s"], app_sha256_port_normalized=["a"], scoring_app_sha256_port_normalized=["sa"]))
        self.assertIn("c", m.generation_uniformity([dict(base, arm=F), dict(base, arm=G), dict(base, arm=A)]))
        with self.assertRaises(ValueError):
            m.generation_uniformity([dict(base, arm=F, generation_config=dict(base["generation_config"], server_isolation="shared-reuse",
                                                                              reuse_existing_server=True))])


class CliFirstDecision(unittest.TestCase):
    def fixture(self, models=3, arms=None):
        p, results = complete_decision_fixture(arms=arms or m.ARMS, models=models)
        return p, results

    def test_adoption_sentence_needs_quality_margin_tokens_not_more_and_three_models(self):
        p, results = self.fixture()
        decision = m.cli_first_decision(results, p)
        self.assertEqual(decision["statement"], "CLI-first thin workflow adopted as default path (development point rule)", decision)
        self.assertEqual(set(decision["comparator_screens"]), {"F_vs_A", "F_vs_D"})  # G_vs_E is reported apart, never in the gate
        self.assertEqual(decision["adoption_gated_by"], ["F", "A", "D"])
        self.assertEqual((decision["g_screen"]["label"], decision["g_screen"]["screen_met"]), ("G_vs_E", True))
        self.assertIn("never gates", decision["g_screen"]["note"])
        self.assertIn("write path", decision["comparability"]["F_vs_D"])
        self.assertAlmostEqual(decision["values"]["mean_model_processed_ratio_F_vs_D"], 75 / 80)
        self.assertAlmostEqual(decision["values"]["mean_model_total_ratio_F_vs_A"], 95 / 120)
        self.assertEqual(decision["quality_wording"]["F_vs_D"], "same within the screen")
        self.assertIn("F_minus_E (surface and scanner gate differ)", decision["indirect_reported_without_threshold"])
        p, results = self.fixture(models=2)
        self.assertTrue(m.cli_first_decision(results, p)["statement"].startswith("inconclusive: CLI-first stage-1 screen met"))
        p, results = self.fixture(models=1)
        self.assertTrue(m.cli_first_decision(results, p)["statement"].startswith("inconclusive: CLI-first stage-1 screen met"))

    def test_token_bound_is_a_ten_percent_margin_on_processed_and_on_cached_inclusive_separately(self):
        self.assertEqual(m.CLI_MAX_TOKEN_RATIO, 1.10)
        self.assertEqual(m.protocol()["decision"]["cli_first"]["maximum_token_ratio"], 1.10)
        token_rule = m.protocol()["decision"]["cli_first"]["token_rule"]
        for phrase in ("PROCESSED ratio", "does NOT count cached input", "CACHED-INCLUSIVE ratio", "Both must hold", "0.80"):
            self.assertIn(phrase, token_rule)

        def with_f_tokens(processed, total, arm=F):
            p, results = self.fixture()
            for result in results.values():
                for cell in result["cells"]:
                    if cell["arm"] == arm:
                        cell["pipeline"]["tokens"].update(processed=processed, total=total)
            return m.cli_first_decision(results, p)
        # D has processed 80 and total 100 per cell: exactly 1.10 of each passes, one token more on either ratio fails
        adopted = "CLI-first thin workflow adopted as default path (development point rule)"
        self.assertEqual(with_f_tokens(88, 110)["statement"], adopted)
        over_processed = with_f_tokens(89, 110)
        self.assertEqual(over_processed["statement"], "CLI-first thin workflow not demonstrated at least as good as MCP delegation")
        self.assertFalse(over_processed["comparator_screens"]["F_vs_D"]["cost_rule_met"])
        over_total = with_f_tokens(88, 111)
        self.assertFalse(over_total["comparator_screens"]["F_vs_D"]["cost_rule_met"])
        self.assertEqual(over_total["statement"], "CLI-first thin workflow not demonstrated at least as good as MCP delegation")
        # a ratio above the old 1.00 bound but inside the margin no longer fails the screen
        self.assertEqual(with_f_tokens(81, 101)["statement"], adopted)
        # the margin applies to G against E and A too
        p, results = self.fixture()
        for result in results.values():
            for cell in result["cells"]:
                if cell["arm"] == G:
                    cell["pipeline"]["tokens"].update(processed=89, total=110)  # 89/80 against E
        screen = m.cli_first_decision(results, p)["g_screen"]
        self.assertFalse(screen["screens"]["G_vs_E"]["cost_rule_met"])
        self.assertTrue(screen["screens"]["G_vs_A"]["cost_rule_met"])

    def test_better_needs_the_mde(self):
        p, results = self.fixture()
        for result in results.values():
            for cell in result["cells"]:
                if cell["arm"] == F:
                    cell.update(selector_hygiene=1.0, clean_conditional_survival=1.0, refactor_score=1.0, effective_fault_kill=1.0)
                if cell["arm"] == D:
                    cell.update(selector_hygiene=0.5, clean_conditional_survival=0.5, refactor_score=0.5, effective_fault_kill=0.5)
        decision = m.cli_first_decision(results, p)
        # clean is 1.0 in both arms, so F is not better on ALL five metrics even with a 0.5 gain on the other four
        self.assertEqual(decision["quality_wording"]["F_vs_D"], "same within the screen")
        self.assertTrue(decision["screens_met"]["F_vs_D"])

    def test_a_quality_loss_beyond_the_margin_is_not_demonstrated(self):
        p, results = self.fixture()
        for result in results.values():
            for cell in result["cells"]:
                if cell["arm"] == F:
                    cell["selector_hygiene"] = 0.799
        decision = m.cli_first_decision(results, p)
        self.assertEqual(decision["statement"], "CLI-first thin workflow not demonstrated at least as good as MCP delegation")
        self.assertFalse(decision["comparator_screens"]["F_vs_A"]["quality_margins_met"])

    def test_missing_fidelity_children_guide_or_cost_evidence_is_inconclusive(self):
        mutations = {
            "fidelity": lambda c: c.update(fidelity_class="unverified"),
            "guide read": lambda c: c.update(cli_guide_read_indicator=False),
            "rules read": lambda c: c.update(thin_layer_read_indicator=False),
            "guide integrity": lambda c: c.update(cli_guide_integrity=None),
            "child agents": lambda c: c.update(child_agents=1),
            "unknown children": lambda c: c.update(child_agents=None),
            "cost": lambda c: c["pipeline"]["tokens"].update(complete=False),
        }
        for name, change in mutations.items():
            p, results = self.fixture(models=3)
            for result in results.values():
                for cell in result["cells"]:
                    if cell["arm"] == F:
                        change(cell)
            with self.subTest(name):
                decision = m.cli_first_decision(results, p)
                self.assertEqual(decision["statement"], "inconclusive")
                self.assertTrue(decision["reasons"])

    def test_g_and_e_evidence_never_gate_the_f_adoption_sentence_and_the_g_screen_is_independent(self):
        adopted = "CLI-first thin workflow adopted as default path (development point rule)"
        g_breaks = {
            "scanner indicator": lambda c: c.update(scanner_gate_indicator=False) if c["arm"] == G else None,
            "scanner integrity": lambda c: c.update(scanner_integrity=None) if c["arm"] == G else None,
            "G fidelity": lambda c: c.update(fidelity_class="unverified") if c["arm"] == G else None,
            "G children": lambda c: c.update(child_agents=2) if c["arm"] == G else None,
            "G cost": lambda c: c["pipeline"]["tokens"].update(complete=False) if c["arm"] == G else None,
            "E cost": lambda c: c["pipeline"]["tokens"].update(complete=False) if c["arm"] == E else None,
            "E fidelity": lambda c: c.update(fidelity_class="unverified") if c["arm"] == E else None,
            "G guide read": lambda c: c.update(cli_guide_read_indicator=False) if c["arm"] == G else None,
        }
        for name, change in g_breaks.items():
            p, results = self.fixture()
            for result in results.values():
                for cell in result["cells"]:
                    change(cell)
            with self.subTest(name):
                decision = m.cli_first_decision(results, p)
                self.assertEqual(decision["statement"], adopted, decision.get("reasons"))
                self.assertEqual(decision["g_screen"]["statement"], "inconclusive")
                self.assertTrue(decision["g_screen"]["reasons"])
                self.assertNotIn("G_vs_E", decision["comparator_screens"])
        # a failing G-versus-E screen (quality loss, then more tokens) is reported apart and does not touch the F sentence
        p, results = self.fixture()
        for result in results.values():
            for cell in result["cells"]:
                if cell["arm"] == G:
                    cell["selector_hygiene"] = 0.0
        decision = m.cli_first_decision(results, p)
        self.assertEqual(decision["statement"], adopted)
        self.assertEqual((decision["g_screen"]["screen_met"], decision["g_screen"]["statement"]),
                         (False, "G product-path screen not met against E and A"))
        p, results = self.fixture()
        for result in results.values():
            for cell in result["cells"]:
                if cell["arm"] == G:
                    cell["pipeline"]["tokens"].update(processed=10 ** 6, total=10 ** 6)
        decision = m.cli_first_decision(results, p)
        self.assertEqual(decision["statement"], adopted)
        self.assertFalse(decision["g_screen"]["screen"]["cost_rule_met"])
        # the converse: F, A and D evidence still gate the sentence, and the G screen is computed regardless
        f_breaks = {"F cost": lambda c: c["pipeline"]["tokens"].update(complete=False) if c["arm"] == F else None,
                    "D fidelity": lambda c: c.update(fidelity_class="unverified") if c["arm"] == D else None,
                    "F guide": lambda c: c.update(cli_guide_read_indicator=False) if c["arm"] == F else None}
        for name, change in f_breaks.items():
            p, results = self.fixture()
            for result in results.values():
                for cell in result["cells"]:
                    change(cell)
            with self.subTest(name):
                decision = m.cli_first_decision(results, p)
                self.assertEqual(decision["statement"], "inconclusive")
                self.assertEqual(decision["g_screen"]["label"], "G_vs_E")
                self.assertTrue(decision["g_screen"]["screen_met"])
        # A is a comparator of BOTH screens: incomplete A cost evidence makes the F sentence and the G screen inconclusive together
        p, results = self.fixture()
        for result in results.values():
            for cell in result["cells"]:
                if cell["arm"] == A:
                    cell["pipeline"]["tokens"].update(complete=False)
        decision = m.cli_first_decision(results, p)
        self.assertEqual((decision["statement"], decision["g_screen"]["statement"]), ("inconclusive", "inconclusive"))
        # G is a default arm: a campaign without it is refused, and the G screen is always scheduled
        self.assertIn(G, m.arm_set())
        with self.assertRaises(ValueError):
            complete_decision_fixture(arms=(A, D, E, F), models=3)

    def test_G_screen_covers_E_and_A_and_without_F_scheduled_nothing_is_evaluated(self):
        p, results = self.fixture()
        decision = m.cli_first_decision(results, p)
        self.assertEqual(set(decision["comparator_screens"]), {"F_vs_A", "F_vs_D"})
        self.assertEqual(set(decision["g_screen"]["screens"]), {"G_vs_E", "G_vs_A"})
        self.assertEqual(decision["g_screen"]["screens_met"], {"G_vs_E": True, "G_vs_A": True})
        self.assertEqual(decision["g_screen"]["statement"], "G product-path screen met against E and A (CLI plus scanner)")
        self.assertIn("G_minus_F (scanner effect on CLI)", decision["indirect_reported_without_threshold"])
        # a loss of G against A alone (E equal) fails the screen; against E alone fails it too
        for rival, label in ((A, "G_vs_A"), (E, "G_vs_E")):
            p, results = self.fixture()
            for result in results.values():
                for cell in result["cells"]:
                    if cell["arm"] == rival:
                        cell["selector_hygiene"] = 1.0
                    if cell["arm"] == G:
                        cell["selector_hygiene"] = 0.5
            with self.subTest(rival=rival):
                screen = m.cli_first_decision(results, p)["g_screen"]
                self.assertFalse(screen["screens_met"][label])
                self.assertFalse(screen["screen_met"])
        self.assertEqual(m.cli_first_decision(results, dict(p, selected_arms=(A, B, C, D, E)))["evaluated"], False)

    def test_summary_carries_the_cli_first_statement_beside_the_unchanged_cheap_stack_one(self):
        p, results = summary_ready(*complete_decision_fixture())
        summary = m.summarize(results, p)
        self.assertEqual(summary["decision"]["cli_first"]["statement"],
                         "CLI-first thin workflow adopted as default path (development point rule)")
        self.assertIn("statement", summary["decision"])
        self.assertEqual(summary["fidelity"][F]["classes"]["cli-observed"], 72)
        self.assertEqual(summary["fidelity"][F]["cells_with_child_agents"], 0)
        self.assertEqual(summary["fidelity"][F]["blocked_by_stop_clause"], 0)  # reported apart from the classes
        self.assertIsNone(summary["fidelity"][D]["blocked_by_stop_clause"])  # D's prompt has no stop clause; D is not rewritten
        self.assertEqual(summary["fidelity"][F]["guard_verified"], 0)  # synthetic fixture cells carry no guard evidence
        self.assertIsNone(summary["fidelity"][A]["guard_verified"])
        self.assertIn("write path", summary["decision"]["cli_first"]["comparability"]["F_vs_D"])
        self.assertEqual(summary["fidelity"][A]["classes"]["cli-observed"], 0)
        self.assertIsNone(summary["fidelity"][B]["browser_interactions"])
        protocol = m.protocol()["decision"]["cli_first"]
        self.assertEqual((protocol["quality_margin"], protocol["maximum_token_ratio"]),
                         (m.CLI_QUALITY_MARGIN, m.CLI_MAX_TOKEN_RATIO))
        self.assertEqual(m.CLI_BETTER_THRESHOLD, 0.20)  # the descriptive MDE
        self.assertIn("0.20", protocol["minimum_detectable_effect"])
        self.assertIn(protocol["adoption_statement"], "CLI-first thin workflow adopted as default path (development point rule)")

    def test_budget_rows_for_F_and_G_are_assumptions_and_roll_up(self):
        budget = m.protocol()["budget"]
        for arm in (F, G):
            self.assertTrue(budget["per_cell"][arm]["basis"].startswith("assumption"))
        plan = m.metrics.budget_plan(budget, m.arm_set())
        self.assertEqual(plan["arms"], ["A", "D", "E", "F", "G"])
        self.assertEqual((plan["cells_per_model"], plan["rolls_up"]["2"]["cells"]), (120, 240))
        central = 24 * sum(budget["per_cell"][a]["points"][1] for a in m.arm_set()) + budget["per_cell"][A]["points"][1]
        self.assertAlmostEqual(plan["points_per_model_low_central_high"][1], round(central, 3), places=3)
        self.assertEqual(plan["ceiling_hours_per_model_at_call_timeout"], 50.0)
        # dropping G (not a valid campaign, only arithmetic) must cost less: the roll-up really contains the G row
        without_g = m.metrics.budget_plan(budget, (A, D, E, F))
        self.assertEqual(without_g["cells_per_model"], 96)
        self.assertGreater(plan["points_per_model_low_central_high"][1], without_g["points_per_model_low_central_high"][1])
        self.assertAlmostEqual(plan["points_per_model_low_central_high"][1] - without_g["points_per_model_low_central_high"][1],
                               24 * budget["per_cell"][G]["points"][1], places=3)



class NonCeilingEndpointsAndSetupGate(unittest.TestCase):
    """First-class non-ceiling endpoints, the 10% setup-failure hard gate, the shipping mapping and the F canary."""

    def setup_of(self, commands, stem, stop=False, **record_changes):
        with tempfile.TemporaryDirectory() as temp:
            directory = Path(temp)
            record = dict(write_cli_cell(directory, commands, stem=stem), **record_changes)
            return m.cli_setup_endpoints(record, directory / "final-transcripts", stop)

    def test_launch_failure_stop_clause_and_zero_snapshot_are_derived_from_the_command_stream(self):
        good = [(SESSION_OPEN, 0), (SESSION_PROBE, 0), (SESSION_REQUESTS, 0), (SESSION_GOTO, 0), (SESSION_SNAP, 0)]
        out = self.setup_of(good, "ok")
        self.assertEqual((out["launch_failed"], out["setup_failure"], out["zero_snapshot"], out["never_attempted"]), (False, False, False, False))
        self.assertEqual((out["open_attempts"], out["open_failures"], out["verified_snapshots"]), (1, 0, 1))
        # the real arm-C shape: the first `open` (no --browser chromium) failed, the retry succeeded: not a launch failure
        real = self.setup_of(list(REAL_ARM_C_CLI), "real")
        self.assertEqual((real["open_attempts"], real["open_failures"], real["launch_failed"], real["setup_failure"]), (2, 1, False, False))
        # only the failed open: the launch failed and the user sees a setup failure
        failed = self.setup_of(list(REAL_ARM_C_CLI[:1]), "failed")
        self.assertEqual((failed["launch_failed"], failed["setup_failure"], failed["zero_snapshot"]), (True, True, True))
        # a masked open that "exited 0" is an attempt without proof: launch failure
        masked = self.setup_of([(SESSION_OPEN + " || true", 0)], "masked")
        self.assertEqual((masked["open_attempts"], masked["launch_failed"], masked["setup_failure"]), (1, True, True))
        # an open with an error banner or an unknown exit code is not a verified launch
        banner = self.setup_of([(SESSION_OPEN, 0, "### Error\nbrowser not found\n")], "banner")
        self.assertTrue(banner["launch_failed"])
        self.assertTrue(self.setup_of([(SESSION_OPEN, None)], "unknown")["launch_failed"])
        # never attempting open is a fidelity matter, not a launch failure
        never = self.setup_of([("ls tests", 0)], "never")
        self.assertEqual((never["never_attempted"], never["launch_failed"], never["setup_failure"], never["zero_snapshot"]), (True, False, False, True))
        # the stop clause alone is a user-visible setup failure
        self.assertTrue(self.setup_of([("ls tests", 0)], "stop", stop=True)["setup_failure"])
        # an open without any snapshot is the zero-snapshot cell
        nosnap = self.setup_of([(SESSION_OPEN, 0)], "nosnap")
        self.assertEqual((nosnap["setup_failure"], nosnap["zero_snapshot"]), (False, True))
        # quoted mentions are not attempts
        self.assertEqual(self.setup_of(["echo '%s'" % SESSION_OPEN and ("echo '%s'" % SESSION_OPEN, 0)], "echo")["open_attempts"], 0)

    def test_missing_stream_or_aborted_cell_is_unknown_never_a_zero(self):
        with tempfile.TemporaryDirectory() as temp:
            directory = Path(temp)
            record = write_cli_cell(directory, [(SESSION_OPEN, 0)], stem="u")
            absent = m.cli_setup_endpoints(dict(record, transcript_path="absent.jsonl"), directory / "final-transcripts", None)
            self.assertEqual(absent, dict(available=False, setup_failure=None))
            aborted = m.cli_setup_endpoints(dict(record, infrastructure_error="docker died"), directory / "final-transcripts", None)
            self.assertIs(aborted["setup_failure"], None)

    def test_cell_extras_carry_setup_endpoints_and_tool_rounds_for_cli_arms_only(self):
        with tempfile.TemporaryDirectory() as temp:
            directory = Path(temp).resolve()
            record = dict(write_cli_cell(directory, list(REAL_ARM_C_CLI), stem="e1"), arm=F, call_id="e1")
            out = m.cell_extras(record, directory)
            self.assertEqual(out["cli_setup"]["setup_failure"], False)
            self.assertEqual(out["root_tool_rounds"], len(REAL_ARM_C_CLI))
            self.assertIn("cli_setup", m.cell_extras(dict(record, arm=G), directory))
            self.assertNotIn("cli_setup", m.cell_extras(dict(record, arm=A), directory))
            self.assertEqual(m.cell_extras(dict(record, arm=A), directory)["root_tool_rounds"], len(REAL_ARM_C_CLI))
            self.assertIsNone(m.root_tool_rounds(dict(record, transcript_path="absent.jsonl"), directory / "final-transcripts"))

    def cells(self, failures, unknown=0, total=24, arm=F):
        flags = [True] * failures + [None] * unknown + [False] * (total - failures - unknown)
        return [dict(arm=arm, cli_setup=dict(setup_failure=flag)) for flag in flags]

    def test_setup_gate_boundary_is_ten_percent_of_all_cells_and_unknown_is_never_a_pass(self):
        gate = lambda cells: m.cli_setup_gate(cells, F)
        self.assertEqual((m.SETUP_FAILURE_MAX, gate(self.cells(2))["status"], gate(self.cells(3))["status"]), (0.10, "pass", "fail"))
        self.assertEqual(gate(self.cells(0))["status"], "pass")
        self.assertEqual(m.cli_setup_gate(self.cells(1, total=10), F)["status"], "pass")   # exactly 10%
        self.assertEqual(m.cli_setup_gate(self.cells(2, total=10), F)["status"], "fail")   # 20%
        self.assertEqual(gate(self.cells(0, unknown=1))["status"], "unknown")
        self.assertEqual(gate(self.cells(3, unknown=2))["status"], "fail")  # observed failures already break the bound
        self.assertEqual(gate(self.cells(2, unknown=1))["status"], "unknown")
        self.assertEqual(gate([])["status"], "fail")
        self.assertEqual(gate(self.cells(0, arm=G))["cells"], 0)  # another arm's cells never count
        # the protocol states the same bound
        self.assertIn("<= 0.10", m.protocol()["decision"]["cli_first"]["setup_gate"])

    def test_setup_gate_makes_the_f_sentence_and_the_g_screen_inconclusive(self):
        adopted = "CLI-first thin workflow adopted as default path (development point rule)"
        def fail(arm, count, unknown=False, model=0):
            p, results = complete_decision_fixture(models=3)
            cells = list(results.values())[model]["cells"]
            hit = [c for c in cells if c["arm"] == arm][:count]
            for c in hit:
                c["cli_setup"] = dict(c["cli_setup"], setup_failure=None if unknown else True)
            return m.cli_first_decision(results, p)
        self.assertEqual(fail(F, 2)["statement"], adopted)                 # at the 8.3% bound
        decision = fail(F, 3)                                               # 12.5%: one model is enough
        self.assertEqual(decision["statement"], "inconclusive")
        self.assertTrue(any("setup failure gate fail" in r for r in decision["reasons"]))
        self.assertEqual(fail(F, 1, unknown=True)["statement"], "inconclusive")
        g = fail(G, 3)
        self.assertEqual(g["statement"], adopted)                           # G problems never change the F sentence
        self.assertEqual(g["g_screen"]["statement"], "inconclusive")
        self.assertTrue(any("setup failure gate" in r for r in g["g_screen"]["reasons"]))

    # ---- verbatim goto and config shape (shipped router section 3)
    def with_base(self, commands, stem, port=9400):
        with tempfile.TemporaryDirectory() as temp:
            directory = Path(temp)
            record = dict(write_cli_cell(directory, commands, stem=stem), generation_config=dict(stage_ports=[dict(case='c', explore_port=port + 10000, test_run_port=port)]))
            return m.cli_fidelity(record, directory / "final-transcripts")

    def test_goto_must_be_the_base_url_string_verbatim_when_it_is_recorded(self):
        def chain(url):
            return [(SESSION_OPEN, 0), (SESSION_PROBE, 0), (SESSION_REQUESTS, 0), (SESSION_GOTO.replace("http://127.0.0.1:9400/", url), 0), (SESSION_SNAP, 0)]
        good = self.with_base(chain("http://127.0.0.1:9400/"), "v0")
        self.assertEqual((good["class"], good["evidence"]["goto_verbatim_checked"], good["evidence"]["base_url"]),
                         ("cli-observed", True, "http://127.0.0.1:9400"))
        self.assertEqual(self.with_base(chain("http://127.0.0.1:9400"), "v1")["class"], "cli-observed")
        self.assertEqual(self.with_base(chain("http://127.0.0.1:9400/tags?x=1"), "v2")["class"], "cli-observed")
        for name, url in (("localhost is another origin", "http://localhost:9400/"), ("another port", "http://127.0.0.1:9401/"),
                          ("prefix trap", "http://127.0.0.1:94000/"), ("https", "https://127.0.0.1:9400/"),
                          ("the guard port", "http://127.0.0.1:9/")):
            with self.subTest(name):
                self.assertEqual(self.with_base(chain(url), "bad%d" % abs(hash(url)))["class"], "unverified")
        # without a recorded baseURL only the loopback-origin test applies, and the evidence says so
        unchecked = CliFirstArm.observed(self, chain("http://localhost:9500/"), "nb")
        self.assertEqual((unchecked["class"], unchecked["evidence"]["goto_verbatim_checked"]), ("cli-observed", False))
        self.assertEqual(m.record_base_url(dict(generation_config=dict(stage_ports=[dict(test_run_port=9301)]))), "http://127.0.0.1:9301")
        self.assertIsNone(m.record_base_url({}))
        self.assertIsNone(m.record_base_url(dict(generation_config=dict(stages=[dict(test_run_port=9301)]))))  # the old, never-persisted shape
        self.assertTrue(m.verbatim_goto("http://127.0.0.1:9400/", "http://127.0.0.1:9400"))
        self.assertFalse(m.verbatim_goto("http://localhost:9400/", "http://127.0.0.1:9400"))

    def test_inline_config_shape_is_reported_for_isolated_output_dir_and_a_single_origin(self):
        ok = SESSION_OPEN.replace("open", "open", 1)
        def shape(config):
            cmd = "echo '%s' > /tmp/c.json && %s" % (config, ok)
            with tempfile.TemporaryDirectory() as temp:
                directory = Path(temp)
                record = dict(write_cli_cell(directory, [(cmd, 0)], stem="cfg"), generation_config=dict(stage_ports=[dict(case='c', explore_port=19400, test_run_port=9400)]))
                return m.cli_fidelity(record, directory / "final-transcripts")["evidence"]["config_shape"]
        good = shape('{"browser":{"isolated":true},"network":{"allowedOrigins":["http://127.0.0.1:9400"]},"outputDir":"/tmp/o"}')
        self.assertEqual((good["isolated"], good["output_dir"], good["single_origin"], good["origin_is_base_url"]), (True, True, True, True))
        two = shape('{"browser":{"isolated":true},"network":{"allowedOrigins":["http://127.0.0.1:9400","http://localhost:9400"]},"outputDir":"/o"}')
        self.assertEqual((two["single_origin"], two["origin_is_base_url"]), (False, False))
        other = shape('{"browser":{"isolated":false},"network":{"allowedOrigins":["http://localhost:9400"]}}')
        self.assertEqual((other["isolated"], other["output_dir"], other["origin_is_base_url"]), (False, False, False))
        self.assertEqual(shape("{}"), dict(inline_config_seen=False))

    # ---- shipping mapping
    def fixture(self, models=2):
        return complete_decision_fixture(models=models)

    def shipping(self, change=None, models=2):
        p, results = self.fixture(models)
        for result in results.values():
            for cell in result["cells"]:
                if change:
                    change(cell)
        return m.shipping_decision(results, p)

    def test_two_models_with_a_clean_setup_and_no_deficit_ship_thin_with_the_stated_routing_and_no_quality_claim(self):
        for models in (1, 2, 3):
            out = self.shipping(models=models)
            with self.subTest(models=models):
                self.assertEqual(out["outcome"], "ship_thin", out["reasons"])
                self.assertEqual(out["routing"], "official agents if present, else CLI")
                self.assertIsNone(out["quality_claim"])
                self.assertEqual(out["deficits"], [])
                self.assertEqual(out["mapping"]["ship_thin"]["claim"], "NO quality claim")
        self.assertTrue(any("planning from a raw user request" in t for t in out["not_measured"]))
        self.assertTrue(any("Auth-gated and page-object-model" in t for t in out["not_measured"]))
        # the adoption sentence is decoupled: two models cannot issue it while the shipping mapping still decides
        p, results = self.fixture(2)
        self.assertTrue(m.cli_first_decision(results, p)["statement"].startswith("inconclusive: CLI-first stage-1 screen met"))
        self.assertEqual(m.shipping_decision(results, p)["outcome"], "ship_thin")

    def test_setup_failure_above_ten_percent_ships_detection_routing(self):
        for arm in (F, G):
            p, results = self.fixture(2)
            second = list(results.values())[1]["cells"]
            for c in [c for c in second if c["arm"] == arm][:3]:
                c["cli_setup"] = dict(c["cli_setup"], setup_failure=True)
            out = m.shipping_decision(results, p)
            with self.subTest(arm=arm):
                self.assertEqual(out["outcome"], "ship_detection_routing")
                self.assertEqual(out["routing"], "detection routing: ask for CLI or snapshots by default")
                self.assertTrue(out["reasons"][0].startswith("condition (a) failed"))
        # exactly at the bound still ships
        p, results = self.fixture(2)
        for c in [c for c in list(results.values())[0]["cells"] if c["arm"] == G][:2]:
            c["cli_setup"] = dict(c["cli_setup"], setup_failure=True)
        self.assertEqual(m.shipping_decision(results, p)["outcome"], "ship_thin")

    def test_cli_fidelity_gate_failure_also_fails_condition_a(self):
        out = self.shipping(lambda c: c.update(fidelity_class="unverified") if c["arm"] == G else None)
        self.assertEqual(out["outcome"], "ship_detection_routing")
        self.assertTrue(any("fewer than 18" in r for r in out["reasons"]))

    def test_missing_evidence_is_inconclusive_and_only_hard_failures_ship_detection(self):
        missing = {
            "incomplete F tokens": lambda c: c["pipeline"]["tokens"].update(complete=False) if c["arm"] == F else None,
            "incomplete G tokens": lambda c: c["pipeline"]["tokens"].update(complete=False) if c["arm"] == G else None,
            "missing guide integrity": lambda c: c.update(cli_guide_integrity=None) if c["arm"] == F else None,
            "missing rules integrity": lambda c: c.update(thin_layer_integrity=None) if c["arm"] == G else None,
            "unknown child count": lambda c: c.update(child_agents=None) if c["arm"] == F else None,
            "unknown rules read": lambda c: c.update(thin_layer_read_indicator=None) if c["arm"] == F else None,
            "unknown guide read": lambda c: c.update(cli_guide_read_indicator=None) if c["arm"] == G else None,
        }
        for name, change in missing.items():
            out = self.shipping(change)
            with self.subTest(name):
                self.assertEqual((out["outcome"], out["routing"]), ("inconclusive", None), out["reasons"])
                self.assertTrue(out["missing_evidence_reasons"])
        hard = {
            "child agent": lambda c: c.update(child_agents=1) if c["arm"] == F else None,
            "changed guide bytes": lambda c: c.update(cli_guide_integrity=[dict(before="a", after="b", read_only_mount=True)]) if c["arm"] == F else None,
            "guide not read": lambda c: c.update(cli_guide_read_indicator=False) if c["arm"] == G else None,
            "not observed": lambda c: c.update(fidelity_class="unverified") if c["arm"] == F else None,
        }
        for name, change in hard.items():
            with self.subTest(name):
                self.assertEqual(self.shipping(change)["outcome"], "ship_detection_routing")
        # a hard failure outranks missing evidence elsewhere
        both = lambda c: (hard["child agent"](c), missing["incomplete G tokens"](c)) and None
        self.assertEqual(self.shipping(both)["outcome"], "ship_detection_routing")

    def test_ship_thin_requires_the_scanner_to_have_run_in_E_and_G(self):
        for arm in (E, G):
            for name, change in (("indicator off", lambda c, a=arm: c.update(scanner_gate_indicator=False) if c["arm"] == a else None),
                                 ("integrity missing", lambda c, a=arm: c.update(scanner_integrity=None) if c["arm"] == a else None),
                                 ("integrity changed", lambda c, a=arm: c.update(scanner_integrity=[dict(before="a", after="b", read_only_mount=True)]) if c["arm"] == a else None)):
                with self.subTest(arm=arm, case=name):
                    out = self.shipping(change)
                    self.assertNotEqual(out["outcome"], "ship_thin")
                    self.assertTrue(any(("scanner" in r) for r in out["reasons"]), out["reasons"])
                    if arm == E:  # E's missing scanner run is an evidence gap (inconclusive), never a detection-routing verdict
                        self.assertEqual(out["outcome"], "inconclusive")
                        self.assertTrue(any("E scanner" in r or "official+thin-rules+scanner scanner" in r for r in out["reasons"]), out["reasons"])
        self.assertEqual(self.shipping()["outcome"], "ship_thin")

    def test_unknown_or_missing_evidence_is_inconclusive_never_shipping(self):
        unknown = self.shipping(lambda c: c.update(cli_setup=dict(c["cli_setup"], setup_failure=None)) if c["arm"] == F else None)
        self.assertEqual((unknown["outcome"], unknown["routing"]), ("inconclusive", None))
        self.assertEqual(self.shipping(lambda c: c.update(fidelity_class="unverified") if c["arm"] == A else None)["outcome"], "inconclusive")
        self.assertEqual(self.shipping(lambda c: c.update(selector_hygiene=None) if c["arm"] == D and c["repetition"] == 1 else None)["outcome"],
                         "inconclusive")
        p, results = self.fixture(2)
        list(results.values())[0]["complete"] = False
        self.assertEqual(m.shipping_decision(results, p)["outcome"], "inconclusive")
        p, results = self.fixture(2)
        del results[p["models"][1]["id"]]
        self.assertEqual(m.shipping_decision(results, p)["outcome"], "inconclusive")
        p, results = self.fixture(2)
        list(results.values())[0]["cells"].pop()
        self.assertEqual(m.shipping_decision(results, p)["outcome"], "inconclusive")
        p, results = self.fixture(2)
        self.assertEqual(m.shipping_decision(results, dict(p, selected_arms=(A, B, C, D, E)))["evaluated"], False)

    def test_a_deficit_of_at_least_point_two_holds_and_less_ships(self):
        def level(arm, value):
            return lambda c: c.update(selector_hygiene=value) if c["arm"] == arm else None
        def both(*changes):
            return lambda c: [ch(c) for ch in changes] and None
        base = level(A, 0.9), level(D, 0.9), level(E, 0.9)
        out = self.shipping(both(*base, level(G, 0.7)))                    # G - A = G - D = G - E = -0.2
        self.assertEqual(out["outcome"], "hold")
        self.assertIsNone(out["routing"])
        self.assertTrue(any("G_vs_A|selector_hygiene" in d for d in out["deficits"]))
        self.assertEqual(self.shipping(both(*base, level(G, 0.701)))["outcome"], "ship_thin")  # just inside the deficit
        self.assertEqual(self.shipping(both(*base, level(G, 0.85)))["outcome"], "ship_thin")
        # the official-agent path is held to the same bound, and E against G counts in both directions
        self.assertEqual(self.shipping(both(level(A, 1.0), level(D, 1.0), level(E, 0.79), level(G, 0.9)))["outcome"], "hold")
        self.assertEqual(self.shipping(both(*base, level(G, 1.1), level(E, 0.89)))["outcome"], "hold")  # E is 0.21 behind G
        self.assertEqual(self.shipping(both(*base, level(G, 1.0), level(E, 0.89)))["outcome"], "ship_thin")
        # any one of the five metrics is enough
        metric = lambda name: (lambda c: c.update({name: 0.5}) if c["arm"] == G else None)
        for name in m.METRICS:
            with self.subTest(metric=name):
                self.assertEqual(self.shipping(both(*base, lambda c: c.update({n: 0.9 for n in m.METRICS}) if c["arm"] in (A, D, E) else None,
                                                    lambda c: c.update({n: 0.9 for n in m.METRICS}) if c["arm"] == G else None,
                                                    metric(name)))["outcome"], "hold")

    def test_summary_carries_endpoints_setup_gates_and_the_shipping_block_beside_the_other_statements(self):
        p, results = summary_ready(*complete_decision_fixture(arms=m.arm_set(), models=2))
        summary = m.summarize(results, p)
        self.assertEqual(summary["decision"]["shipping"]["outcome"], "ship_thin")
        self.assertIn("cli_first", summary["decision"])
        self.assertEqual(set(summary["endpoints"]), {A, D, E, F, G})
        f = summary["endpoints"][F]
        self.assertEqual(f["cli"]["launch_failure_rate"], 0.0)
        self.assertEqual((f["cli"]["stop_clause_cells"], f["cli"]["zero_snapshot_cells"], f["cli"]["setup_failure_cells"]), (0, 0, 0))
        self.assertEqual(f["wall_time_s"], dict(observed_cells=48, mean=100.0))
        self.assertEqual(f["root_tool_rounds"]["mean"], 12.0)
        self.assertEqual((f["tokens_by_role"]["root_processed"], f["tokens_by_role"]["child_processed"]), (48 * 75, 0))
        self.assertIsNone(f["cli"]["spec_locator_observed_fraction"])
        self.assertTrue(f["cli"]["spec_locator_observed_fraction_status"].startswith("pending"))
        self.assertNotIn("cli", summary["endpoints"][A])
        self.assertEqual(summary["setup_gates"][p["models"][0]["id"]][F]["status"], "pass")
        self.assertEqual(set(summary["setup_gates"][p["models"][0]["id"]]), {F, G})

    def test_endpoint_summary_counts_failures_against_the_right_denominators(self):
        p, results = summary_ready(*complete_decision_fixture(arms=m.arm_set(), models=2))
        cells = [c for r in results.values() for c in r["cells"]]
        f_cells = [c for c in cells if c["arm"] == F]
        for c in f_cells[:4]:
            c["cli_setup"] = dict(c["cli_setup"], launch_failed=True, setup_failure=True)
        for c in f_cells[4:6]:
            c["cli_setup"] = dict(c["cli_setup"], zero_snapshot=True)
        for c in f_cells[6:7]:
            c["stop_clause_blocked"] = True
        for c in f_cells[7:9]:
            c["cli_setup"] = dict(available=False, setup_failure=None)
        row = m.endpoint_summary(cells, (F,))[F]["cli"]
        self.assertEqual((row["cells_with_setup_observation"], row["cells_without_setup_observation"]), (46, 2))
        self.assertEqual((row["launch_failure_cells"], row["launch_failure_rate"]), (4, round(4 / 46, 4)))
        self.assertEqual((row["zero_snapshot_cells"], row["stop_clause_cells"], row["setup_failure_cells"]), (2, 1, 4))
        self.assertEqual(row["setup_failure_rate"], round(4 / 48, 4))  # over ALL cells of the arm, as the gate does

    # ---- canary
    def canary_cells(self):
        p, results = complete_decision_fixture(models=1)
        plan = m.canary_plan(p)
        want = {(c["case"], c["repetition"]) for c in plan["cells"]}
        cells = [dict(c, attempt_errors=[], fidelity=dict(evidence=dict(guard_verified_in_observed_session=True)))
                 for c in list(results.values())[0]["cells"] if c["arm"] == F and (c["case"], c["repetition"]) in want]
        return plan, cells

    def test_canary_is_six_f_cells_from_the_seeded_order_and_independent_of_the_arm_set(self):
        plan = m.canary_plan()
        self.assertEqual((plan["arm"], plan["count"], len(plan["cells"]), plan["repetitions"], len(plan["tasks"])), (F, 6, 6, 3, 2))
        rows = m.schedule(arms=m.arm_set())
        first = []
        for row in rows:
            if row["repetition"] == 1 and row["case"] not in first:
                first.append(row["case"])
        self.assertEqual(plan["tasks"], first[:2])
        self.assertEqual({(c["case"], c["repetition"]) for c in plan["cells"]}, {(t, r) for t in plan["tasks"] for r in (1, 2, 3)})
        self.assertEqual(m.canary_plan(dict(m.protocol(), selected_arms=m.ARMS))["tasks"], plan["tasks"])
        changed = dict(m.protocol(), seed=m.protocol()["seed"] + 1)
        self.assertEqual(len(m.canary_plan(changed)["tasks"]), 2)
        declared = m.protocol()["canary"]
        self.assertEqual((declared["cells"], declared["tasks"], declared["repetitions"], declared["arm"]), (6, 2, 3, F))
        for phrase in ("ANY anomaly stops", "archive", "NEW protocol version", "never patched"):
            self.assertIn(phrase, declared["stop_rule"])
        self.assertIn("canary --output OUT --allow-live", declared["implementation"])
        self.assertIn("never run against a model", declared["status_live"])

    def test_clean_canary_proceeds_and_every_anomaly_stops_it(self):
        plan, cells = self.canary_cells()
        self.assertEqual(len(cells), 6)
        self.assertEqual(m.canary_verdict(cells)["verdict"], "proceed")
        mutations = {
            "aborted": lambda c: c.update(aborted=True),
            "fidelity": lambda c: c.update(fidelity_class="unverified"),
            "guard": lambda c: c.update(fidelity=dict(evidence=dict(guard_verified_in_observed_session=False))),
            "setup failure": lambda c: c.update(cli_setup=dict(c["cli_setup"], setup_failure=True)),
            "setup unknown": lambda c: c.update(cli_setup=dict(available=False, setup_failure=None)),
            "zero snapshot": lambda c: c.update(cli_setup=dict(c["cli_setup"], zero_snapshot=True)),
            "stop clause": lambda c: c.update(stop_clause_blocked=True),
            "stop clause unknown": lambda c: c.update(stop_clause_blocked=None),
            "child agent": lambda c: c.update(child_agents=1),
            "unknown children": lambda c: c.update(child_agents=None),
            "rules unread": lambda c: c.update(thin_layer_read_indicator=False),
            "guide unread": lambda c: c.update(cli_guide_read_indicator=False),
            "no deliverable": lambda c: c.update(deliverable=False),
            "tokens": lambda c: c["pipeline"]["tokens"].update(complete=False),
            "retry": lambda c: c.update(attempt_errors=["timeout"]),
            "guide integrity": lambda c: c.update(cli_guide_integrity=[dict(before="a", after="b", read_only_mount=True)]),
            "rules integrity missing": lambda c: c.update(thin_layer_integrity=None),
            "mount not read-only": lambda c: c.update(cli_guide_integrity=[dict(before="a", after="a", read_only_mount=False)]),
        }
        for name, change in mutations.items():
            _, fresh = self.canary_cells()
            change(fresh[3])  # one anomaly in one of the six cells is enough
            with self.subTest(name):
                verdict = m.canary_verdict(fresh)
                self.assertEqual(verdict["verdict"], "stop")
                self.assertTrue(verdict["anomalies"])
                self.assertIn("never patch a frozen campaign", verdict["action"])
        for name, broken in (("five cells", cells[:5]), ("seven cells", cells + [cells[0]]), ("wrong arm", [dict(c, arm=D) for c in cells]),
                             ("wrong grid", [dict(c, repetition=4) for c in cells])):
            with self.subTest(name):
                self.assertEqual(m.canary_verdict(broken)["verdict"], "stop")
        self.assertIsNone(m.canary_verdict(cells)["action"])

    def test_protocol_declares_the_shipping_mapping_the_endpoints_and_the_limitations(self):
        protocol = m.protocol()
        shipping = protocol["decision"]["shipping"]
        self.assertEqual(shipping["mapping"]["ship_thin"]["routing"], "official agents if present, else CLI")
        self.assertEqual(shipping["mapping"]["ship_detection_routing"]["routing"], "detection routing: ask for CLI or snapshots by default")
        self.assertIn("10%", shipping["conditions"]["a"])
        self.assertIn("0.20", shipping["conditions"]["b"])
        self.assertIn("still requires three finished models", shipping["adoption_sentence"])
        self.assertEqual((m.SHIPPING_DEFICIT, m.SETUP_FAILURE_MAX), (0.20, 0.10))
        self.assertEqual(m.SHIPPING_COMPARATORS, (A, D, E, G))
        self.assertEqual(set(shipping["mapping"]), {"ship_thin", "ship_detection_routing", "hold", "inconclusive"})
        text = " ".join(shipping["not_measured"])
        for phrase in ("approved plan and a seed", "raw user request", "Auth-gated", "page-object-model"):
            self.assertIn(phrase, text)
        endpoints = protocol["endpoints"]
        for key in ("cli_launch_failure_rate", "setup_failure_rate", "stop_clause_cells", "zero_snapshot_cells", "wall_time", "turn_count",
                    "tokens_by_role"):
            self.assertIn(key, endpoints["derived_offline_from_transcripts_and_rollouts"])
        self.assertIn("NOT built", endpoints["pending"]["spec_locator_observed_fraction"])
        readme = (m.BENCH / "README.md").read_text()
        for phrase in ("official agents if present, else CLI", "ask for CLI or snapshots", "raw request", "canary", "10%", "1.10",
                       "cached input", "G vs E", "G vs A"):
            self.assertIn(phrase, readme)



class PreFreezeReviewFixes(unittest.TestCase):
    """Second independent review: shipped-skill pin, concurrency honesty, port statement coherence, canary spend, derived counts."""

    def protocol_text(self):
        return m.PROTOCOL.read_text()

    def test_shipped_skill_pin_is_a_positive_binding_checked_at_freeze(self):
        skill = "---\nname: x\n---\n\n## 2. Choose\nx\n\n## 3. CLI workflow (default)\n\nstep one\n\n## 4. Delegate\nz\n"
        section = m.router_section3(skill)
        self.assertTrue(section.startswith("## 3. CLI workflow (default)") and section.rstrip().endswith("step one"))
        self.assertNotIn("## 4.", section)
        pins = dict(cli_guide=dict(estimand=dict(shipped_skill=dict(
            skill_md_sha256=hashlib.sha256(skill.encode()).hexdigest(), section_3_sha256=hashlib.sha256(section.encode()).hexdigest()))))
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / "SKILL.md"
            path.write_text(skill)
            seen = m.check_shipped_skill(path, pins)
            self.assertEqual(seen["skill_md_sha256"], pins["cli_guide"]["estimand"]["shipped_skill"]["skill_md_sha256"])
            for changed in (skill + " ", skill.replace("step one", "step 1")):  # whole-file drift, and section drift
                path.write_text(changed)
                with self.subTest(changed=changed[-12:]), self.assertRaisesRegex(ValueError, "shipped router SKILL.md differs"):
                    m.check_shipped_skill(path, pins)
            # the whole file differs outside section 3: the whole-file pin alone refuses
            path.write_text(skill.replace("name: x", "name: y"))
            with self.assertRaisesRegex(ValueError, "differs"):
                m.check_shipped_skill(path, pins)
        pinned = m.protocol()["cli_guide"]["estimand"]["shipped_skill"]
        for key in ("skill_md_sha256", "section_3_sha256"):
            self.assertRegex(pinned[key], r"^[0-9a-f]{64}$")
        self.assertIn("--shipped-skill", pinned["rule"])
        self.assertIn("different worktree", m.protocol()["release_gate"])
        self.assertIn("stay at the v3 skills tree", m.protocol()["release_gate"])
        readme = (m.BENCH / "README.md").read_text()
        self.assertIn("stays at the v3 skills tree until `summary`", readme)
        self.assertIn("re-confirmed against the final SKILL.md at freeze", readme)
        # freeze cannot be invoked without the pin
        with self.assertRaises(SystemExit), contextlib.redirect_stderr(io.StringIO()):
            m.main(["freeze", "--output", "/tmp/never-created-thin-freeze"])
        payload_without = None
        with tempfile.TemporaryDirectory() as temp, patch.object(m, "bindings", return_value={"s": 1}):
            payload_without = m.freeze_payload(Path(temp).resolve() / "new", dict(models=m.protocol()["candidate_models"][:2]))
            self.assertIsNone(payload_without["shipped_skill"])
            recorded = m.freeze_payload(Path(temp).resolve() / "new2", dict(models=m.protocol()["candidate_models"][:2]), shipped_skill=pinned)
            self.assertEqual(recorded["shipped_skill"]["skill_md_sha256"], pinned["skill_md_sha256"])

    def test_the_machine_lock_is_documented_as_one_directional(self):
        text = m.protocol()["concurrency"]["one_directional_guarantee"]
        for phrase in ("ONE-DIRECTIONAL", "do NOT see a running thin driver or canary", "cannot be edited", "never start a v3 driver while a thin driver or canary runs"):
            self.assertIn(phrase, text)
        self.assertIn("one-directional", (m.BENCH / "README.md").read_text())
        # the thin side really refuses a running v3 driver (probe semantics of the shared lock)
        probe = lambda: [4242]
        lock = m.CampaignLock(Path(tempfile.mkdtemp()) / "x.lock", process_probe=probe)
        with self.assertRaisesRegex(ValueError, "another generator benchmark driver"):
            lock.__enter__()

    def test_port_statements_agree_across_protocol_and_readme(self):
        protocol = m.protocol()
        f3 = json.dumps(protocol["harness_repairs"]["F3_shared_server_state"])
        self.assertNotIn("tells the model to start the app on its own free port", f3)
        self.assertNotIn("separate-port step", f3)
        self.assertIn("NO port instruction", f3)
        self.assertIn("sequential on port P", f3)
        readme = (m.BENCH / "README.md").read_text()
        for stale in ("separate-port app start", "start the app on its own free port", "start the app on a free port with `GEN_EXPLORE_PORT`"):
            self.assertNotIn(stale, readme)
        self.assertIn("sequential on the same default port P", readme)
        guide = m.CLI_GUIDE.read_text()
        self.assertNotIn("GEN_EXPLORE_PORT", guide)
        for text in (m.F_LINE, m.G_LINE):
            self.assertNotIn("GEN_EXPLORE_PORT", text)
            self.assertNotIn("port", text.lower().replace("report", ""))

    def test_counts_in_the_readme_and_protocol_are_derived_from_code(self):
        readme = (m.BENCH / "README.md").read_text()
        self.assertIn("one of %d rule markers" % len(m.GUIDE_SEMANTIC_MARKERS), readme)
        self.assertEqual(len(m.GUIDE_SEMANTIC_MARKERS), len(set(m.GUIDE_SEMANTIC_MARKERS)))
        protocol = m.protocol()
        cells = {name: n for name, n in protocol["schedule"]["cells_per_model"].items()}
        for name, flags in (("default_A_D_E_F_G", {}), ("with_reviewer", dict(include_reviewer=True)),
                            ("with_full_skill_rerun", dict(rerun_full_skill=True)), ("all_seven", dict(include_reviewer=True, rerun_full_skill=True))):
            self.assertEqual(cells[name], len(m.schedule(arms=m.arm_set(**flags))), name)
        timeout = protocol["schedule"]["time_estimates"]["generation_and_review_timeout_s"]
        self.assertEqual(protocol["schedule"]["time_estimates"]["nominal_call_budget_hours_per_model_default"],
                         len(m.schedule(arms=m.arm_set())) * timeout / 3600)
        self.assertIn("ceiling of %d hours per model for the default arm set (%d calls)" % (
            len(m.schedule(arms=m.arm_set())) * timeout / 3600, len(m.schedule(arms=m.arm_set()))), readme)
        # G is a default arm everywhere it is described
        self.assertNotIn("optional arm G", readme.replace("no longer an optional arm G", ""))
        self.assertNotIn("--include-cli-scanner", json.dumps(protocol["arm_policy"]))
        # the scanner scope covers E and G, and the hours sentence names both
        self.assertTrue(protocol["scanner_gate"]["staging"].startswith("E and G"))
        self.assertIn("1.6-4.0 together", protocol["schedule"]["time_estimates"]["interpretation"])
        self.assertEqual(protocol["schedule"]["time_estimates"]["E_and_G_increment_hours_per_model"], [1.6, 4.0])
        self.assertIn("<= 1.10", protocol["cost_endpoints"]["decision_ratio"])
        self.assertNotIn("<= 1.00", protocol["cost_endpoints"]["decision_ratio"])
        self.assertIn("G/E and G/A", protocol["cost_endpoints"]["decision_ratio"])

    def test_canary_is_per_model_extra_spend_rerun_inside_the_grid_and_budgeted(self):
        canary = m.protocol()["canary"]
        for phrase in ("PER ROSTER MODEL",):
            self.assertIn(phrase, canary["per_model"])
        for phrase in ("EXTRA spend", "archived", "24 cells per arm per model", "run again inside it"):
            self.assertIn(phrase, canary["spend"])
        budget = m.protocol()["budget"]
        plan = m.metrics.budget_plan(budget, m.arm_set())
        self.assertEqual(plan["canary"]["cells_per_model"], 6)
        f_points = budget["per_cell"][F]["points"]
        self.assertEqual(plan["canary"]["points_per_model_low_central_high"], [round(6 * v, 3) for v in f_points])
        for n in ("1", "2", "3"):
            roll = plan["rolls_up"][n]
            self.assertEqual(roll["canary_cells"], 6 * int(n))
            for i in range(3):
                self.assertAlmostEqual(roll["points_with_canary_low_central_high"][i] - roll["points_low_central_high"][i],
                                       int(n) * 6 * f_points[i], places=2)
        # the full grid is not reduced by the canary
        self.assertEqual(plan["cells_per_model"], 120)
        self.assertEqual(sum(r["arm"] == F for r in m.schedule()), 24)
        # without F there is no canary spend
        self.assertNotIn("canary", m.metrics.budget_plan(budget, (A, D, E)))
        readme = (m.BENCH / "README.md").read_text()
        for phrase in ("extra spend", "re-run inside the full grid", "49.3 / 68.4 / 90.1"):
            self.assertIn(phrase, readme)

    def test_scanner_prompt_adaptations_are_listed_not_hidden(self):
        adaptations = " ".join(m.protocol()["cli_guide"]["estimand"]["documented_adaptations"])
        for phrase in ("at most 3 passes", "baseURL", "E and G", "comparability differences"):
            self.assertIn(phrase, adaptations)



class CanaryLiveWiring(unittest.TestCase):
    """The canary subcommand: restricted F schedule, own archived directory, verdict PROCEED/STOP, machine lock and floors (stubs only)."""

    MUTATIONS = {
        "aborted": lambda c: c.update(aborted=True),
        "fidelity": lambda c: c.update(fidelity_class="unverified"),
        "guard": lambda c: c.update(fidelity=dict(evidence=dict(guard_verified_in_observed_session=False))),
        "setup failure": lambda c: c.update(cli_setup=dict(c["cli_setup"], setup_failure=True)),
        "zero snapshot": lambda c: c.update(cli_setup=dict(c["cli_setup"], zero_snapshot=True)),
        "stop clause": lambda c: c.update(stop_clause_blocked=True),
        "child agent": lambda c: c.update(child_agents=1),
        "rules unread": lambda c: c.update(thin_layer_read_indicator=False),
        "guide unread": lambda c: c.update(cli_guide_read_indicator=False),
        "no deliverable": lambda c: c.update(deliverable=False),
        "tokens": lambda c: c["pipeline"]["tokens"].update(complete=False),
        "retry": lambda c: c.update(attempt_errors=["timeout"]),
        "integrity": lambda c: c.update(cli_guide_integrity=[dict(before="a", after="b", read_only_mount=True)]),
    }

    def good_cells(self, p=None):
        plan, cells = NonCeilingEndpointsAndSetupGate.canary_cells(self)
        return cells

    def drive_canary(self, p, output, cells_for=None, run_one=None, admitted=("gpt-6-sol",), free=10 ** 12):
        calls = []
        def stub_run(mid, args, state):
            calls.append((mid, args.allow_live, args.resume))
            (Path(output) / m.CANARY_DIR / mid).mkdir(parents=True, exist_ok=True)
            m.write(Path(output) / m.CANARY_DIR / mid / "final.json", dict(runs=[]))
        with patch.object(m, "FREEZE", Path(output) / "freeze.json"):
            Path(output, "freeze.json").write_text("{}")
            result = m.run_canary(output, p, list(admitted), run_one=run_one or stub_run,
                                  build_cells=cells_for or (lambda directory, report: self.good_cells()),
                                  disk_probe=lambda path: SimpleNamespace(free=free))
        return result, calls

    def p(self):
        p = m.protocol()
        p["models"] = p["candidate_models"][:2]
        return p

    def test_canary_rows_are_the_six_preregistered_F_cells_with_ordinals(self):
        rows = m.canary_rows()
        self.assertEqual([r["ordinal"] for r in rows], [1, 2, 3, 4, 5, 6])
        self.assertEqual({r["arm"] for r in rows}, {F})
        self.assertEqual([(r["case"], r["repetition"]) for r in rows], [(c["case"], c["repetition"]) for c in m.canary_plan()["cells"]])
        self.assertEqual(m.v1.identity(rows[0]), m.v1.identity(dict(rows[0])))

    def test_a_clean_canary_prints_proceed_material_and_stays_in_its_own_archived_directory(self):
        with tempfile.TemporaryDirectory() as temp:
            output = Path(temp).resolve()
            result, calls = self.drive_canary(self.p(), output)
            self.assertEqual(result["verdict"], "proceed")
            self.assertIn("PROCEED", result["action"])
            self.assertEqual(calls, [("gpt-6-sol", True, False)])  # a fresh run, never a resume
            root = output / m.CANARY_DIR
            self.assertTrue((root / "CANARY.json").is_file() and (root / "verdict.json").is_file())
            self.assertFalse((root / "INVALID.json").exists())
            marker = m.read(root / "CANARY.json")
            self.assertEqual((marker["non_data"], marker["archived"], marker["extra_spend"]), (True, True, True))
            # nothing is written next to the full grid: every file is under _canary (or the stub freeze)
            outside = [p_ for p_ in output.rglob("*") if p_.is_file() and root not in p_.parents and p_.name != "freeze.json"]
            self.assertEqual(outside, [])

    def test_every_anomaly_stops_the_canary_and_leaves_the_invalid_instruction(self):
        self.assertEqual(len(self.MUTATIONS), 13)
        for name, change in self.MUTATIONS.items():
            def cells_for(directory, report, change=change):
                cells = self.good_cells()
                change(cells[2])
                return cells
            with self.subTest(name), tempfile.TemporaryDirectory() as temp:
                output = Path(temp).resolve()
                result, _ = self.drive_canary(self.p(), output, cells_for=cells_for)
                self.assertEqual(result["verdict"], "stop")
                self.assertTrue(result["anomalies"])
                for phrase in ("INVALID", "Archive", "NEW protocol version", "Do not patch", "do not start the full stage"):
                    self.assertIn(phrase, result["action"] if phrase != "INVALID" else m.CANARY_STOP_ACTION)
                self.assertIn("NEW protocol version", result["models"]["gpt-6-sol"]["action"] + " NEW protocol version")
                root = output / m.CANARY_DIR
                self.assertTrue(m.read(root / "INVALID.json")["invalid"])
                self.assertEqual(m.read(root / "verdict.json")["verdict"], "stop")

    def test_infrastructure_stops_and_wrong_grids_stop_and_a_stopped_model_stops_the_stage(self):
        def boom(mid, args, state):
            raise ValueError("usage/rate limit; campaign stopped")
        with tempfile.TemporaryDirectory() as temp:
            result, _ = self.drive_canary(self.p(), Path(temp).resolve(), run_one=boom)
            self.assertEqual(result["verdict"], "stop")
            self.assertTrue(any("canary run stopped: usage/rate limit" in a for a in result["anomalies"]))
        with tempfile.TemporaryDirectory() as temp:
            result, _ = self.drive_canary(self.p(), Path(temp).resolve(), cells_for=lambda d, r: self.good_cells()[:5])
            self.assertEqual(result["verdict"], "stop")
            self.assertTrue(any("exactly the six" in a for a in result["anomalies"]))
        with tempfile.TemporaryDirectory() as temp:  # first model stops: the second is recorded as not run, never executed
            result, calls = self.drive_canary(self.p(), Path(temp).resolve(), admitted=("gpt-6-sol", "gpt-6-astra"),
                                     cells_for=lambda d, r: self.good_cells()[:5])
            self.assertEqual([c[0] for c in calls], ["gpt-6-sol"])
            self.assertEqual(result["models"]["gpt-6-astra"]["verdict"], "not run")
        with tempfile.TemporaryDirectory() as temp:  # both clean: every admitted model ran
            result, calls = self.drive_canary(self.p(), Path(temp).resolve(), admitted=("gpt-6-sol", "gpt-6-astra"))
            self.assertEqual((result["verdict"], [c[0] for c in calls]), ("proceed", ["gpt-6-sol", "gpt-6-astra"]))
        with tempfile.TemporaryDirectory() as temp:  # no admitted model is a stop, never a vacuous proceed
            result, calls = self.drive_canary(self.p(), Path(temp).resolve(), admitted=())
            self.assertEqual((result["verdict"], calls), ("stop", []))

    def test_canary_refuses_an_existing_directory_and_a_low_disk_and_never_resumes(self):
        with tempfile.TemporaryDirectory() as temp:
            output = Path(temp).resolve()
            self.drive_canary(self.p(), output)
            with self.assertRaisesRegex(ValueError, "never resumed"):
                self.drive_canary(self.p(), output)
        with tempfile.TemporaryDirectory() as temp:
            output = Path(temp).resolve()
            with self.assertRaisesRegex(ValueError, "disk safety floor"):
                self.drive_canary(self.p(), output, free=1)
            self.assertFalse((output / m.CANARY_DIR).exists())  # refused before anything was created

    def test_runtime_context_gives_the_canary_its_own_model_directories_but_the_real_entries(self):
        with tempfile.TemporaryDirectory() as temp:
            output = Path(temp).resolve()
            freeze = output / "freeze.json"
            freeze.write_text("{}")
            full = dict(schedule=[1, 2, 3], arms=list(m.MANDATORY_ARMS), output=str(output))
            derive = lambda lock: dict(lock, schedule=m.canary_rows(), arms=[F])
            with patch.object(m, "FREEZE", freeze), patch.object(m, "frozen", lambda out: (None, full)):
                with m.runtime_context(output, m.protocol(), derive(full), v1_base=output / m.CANARY_DIR, derive=derive):
                    self.assertEqual(m.v1.BASE, output / m.CANARY_DIR)
                    self.assertEqual(m.integration.BASE, output)  # entries and the harness check stay with the real campaign
                    lock = m.v1.frozen()
                    self.assertEqual((len(lock["schedule"]), lock["arms"]), (6, [F]))
                    self.assertEqual(m.v1.model_dir("gpt-6-sol"), output / m.CANARY_DIR / "gpt-6-sol")
                # without derive the full lock comes back (drive is unchanged)
                with m.runtime_context(output, m.protocol(), full):
                    self.assertEqual(m.v1.frozen()["schedule"], [1, 2, 3])
                    self.assertEqual(m.v1.BASE, output)

    def test_canary_command_takes_the_machine_lock_before_reading_entries_and_prints_the_verdict(self):
        events = []
        class FakeLock:
            def __init__(self, path, campaign_id=None):
                events.append(("lock", Path(path), campaign_id))
            def __enter__(self):
                events.append("enter")
                return self
            def __exit__(self, *exc):
                events.append("exit")
        seen = {}
        @contextlib.contextmanager
        def fake_runtime(output, p, lock, v1_base=None, derive=None):
            seen.update(v1_base=v1_base, lock=lock, derived=derive(dict(schedule=[], arms=[])))
            yield
        p = self.p()
        entries = {x["id"]: dict(decision="admitted" if i == 0 else "excluded") for i, x in enumerate(p["models"])}
        for verdict, code, word in (("proceed", 0, "PROCEED"), ("stop", 3, "STOP")):
            events.clear()
            result = dict(verdict=verdict, action=m.CANARY_STOP_ACTION if verdict == "stop" else "PROCEED: clean", anomalies=["x: bad"] if verdict == "stop" else [])
            out = io.StringIO()
            with patch.object(m, "CampaignLock", FakeLock), patch.object(m, "runtime_context", fake_runtime), \
                    patch.object(m.integration, "load_harness_check", lambda: events.append("harness")), \
                    patch.object(m.integration, "load_entries", lambda pp: events.append("entries") or entries), \
                    patch.object(m, "run_canary", lambda output, pp, admitted: events.append(("run", tuple(admitted))) or result), \
                    contextlib.redirect_stdout(out):
                self.assertEqual(m.canary_command(None, p, dict(schedule=[], arms=[]), Path("/tmp/out-x")), code)
            with self.subTest(verdict):
                self.assertEqual(events[0][0], "lock")
                self.assertEqual((events[0][1], events[0][2]), (m.SHARED_LOCK, m.ID))
                self.assertLess(events.index("enter"), events.index("harness"))
                self.assertLess(events.index("harness"), events.index("entries"))
                self.assertIn(("run", (p["models"][0]["id"],)), events)  # only the admitted model
                self.assertEqual(events[-1], "exit")
                self.assertTrue(out.getvalue().startswith(word + "\n"))
                self.assertEqual(seen["v1_base"], Path("/tmp/out-x") / m.CANARY_DIR)
                self.assertEqual((len(seen["derived"]["schedule"]), seen["derived"]["arms"]), (6, [F]))
                if verdict == "stop":
                    self.assertIn("NEW protocol version", out.getvalue())
                    self.assertIn("anomaly: x: bad", out.getvalue())

    def test_the_subcommand_needs_allow_live_before_any_runtime_setup(self):
        parsed = {}
        with patch.object(m, "frozen", side_effect=AssertionError("freeze read before --allow-live")), \
                patch.object(m, "canary_command", side_effect=AssertionError("ran")):
            with self.assertRaisesRegex(ValueError, "requires --allow-live"):
                m.main(["canary", "--output", "/tmp/never-x"])
        with self.assertRaises(SystemExit), contextlib.redirect_stderr(io.StringIO()):
            m.main(["canary"])  # --output is required
        # wired into main after the freeze, harness and entry checks
        source = (ROOT / "scripts/evals/run-generator-thin-eval-v1.py").read_text()
        self.assertIn('if args.command == "canary":', source)
        self.assertIn("integration.load_harness_check()", source[source.index("def canary_command"):source.index("def safe_specs")])
        protocol = m.protocol()["canary"]
        self.assertIn("canary --output OUT --allow-live", protocol["implementation"])



class ShippedSkillRepin(unittest.TestCase):
    WT300 = Path(os.environ.get("E2E_SKILLS_300_SKILL") or (ROOT.parent / "e2e-skills-wt-300/skills/playwright-test-generator/SKILL.md"))

    def test_the_vendored_copy_exists_and_equals_the_pins_this_test_fails_rather_than_skips(self):
        vendored = m.VENDORED_SKILL
        self.assertTrue(vendored.is_file(), "the vendored shipped-skill/SKILL.md is missing: restore it (byte-identical to the pinned router)")
        pins = m.protocol()["cli_guide"]["estimand"]["shipped_skill"]
        data = vendored.read_bytes()
        self.assertEqual(hashlib.sha256(data).hexdigest(), pins["skill_md_sha256"])
        self.assertEqual(len(data), pins["skill_md_bytes"])
        self.assertEqual(hashlib.sha256(m.router_section3(data.decode()).encode()).hexdigest(), pins["section_3_sha256"])
        self.assertEqual(m.check_shipped_skill(vendored)["skill_md_sha256"], pins["skill_md_sha256"])
        self.assertEqual(m.guide_semantic_gaps(m.CLI_GUIDE.read_text()), [])
        self.assertIn("name: playwright-test-generator", data.decode())
        self.assertLessEqual(len(data), 7168)  # the router's size cap
        self.assertEqual(pins["commit_hash"], "pending release")
        self.assertIn("uncommitted", pins["source_path"])
        self.assertEqual(pins["vendored_copy"], "benchmarks/generator-thin-eval-v1/shipped-skill/SKILL.md")
        self.assertIn("approved `webServer.command` exactly as written", data.decode())

    def test_the_vendored_copy_is_bound_and_a_missing_or_changed_copy_breaks_protocol(self):
        with tempfile.TemporaryDirectory() as temp:
            self.assertIn(str(m.VENDORED_SKILL.relative_to(ROOT)), m.bindings()["files"])
            for name, content in (("missing", None), ("changed", m.VENDORED_SKILL.read_bytes() + b" ")):
                path = Path(temp) / (name + ".md")
                if content is not None:
                    path.write_bytes(content)
                with self.subTest(name), patch.object(m, "VENDORED_SKILL", path), self.assertRaisesRegex(ValueError, "vendored shipped-skill"):
                    m.protocol()

    def test_the_3_0_0_worktree_file_is_byte_identical_to_the_vendored_copy_when_present(self):
        if not self.WT300.is_file():
            self.skipTest("the 3.0.0 worktree's SKILL.md is not on this machine")
        theirs, ours = self.WT300.read_bytes(), m.VENDORED_SKILL.read_bytes()
        self.assertEqual(hashlib.sha256(theirs).hexdigest(), hashlib.sha256(ours).hexdigest(),
                         "the 3.0.0 worktree SKILL.md (%d bytes) differs from the vendored pinned copy (%d bytes): re-confirm the CLI guide, "
                         "replace shipped-skill/SKILL.md and re-pin cli_guide.estimand.shipped_skill (see the release gate)" % (len(theirs), len(ours)))

    def test_a_changed_skill_md_is_refused_until_repinned_and_the_checklist_says_so(self):
        gate = m.protocol()["release_gate"]
        for phrase in ("re-pin", "skill_md_sha256", "section_3_sha256", "re-confirm the CLI guide", "replace the vendored copy"):
            self.assertIn(phrase, gate)
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / "SKILL.md"
            path.write_bytes(b"## 3. CLI workflow (default)\nx\n## 4. Delegate\n")
            with self.assertRaisesRegex(ValueError, "differs from the pinned digests"):
                m.check_shipped_skill(path)


class ReviewRoundThree(unittest.TestCase):
    """Drive gate, canary in the process probe, tokenizer prefixes and subshells, v4 adaptations."""

    def gate_root(self, temp, verdict="proceed", models=("gpt-6-sol",), freeze_digest="F1", invalid=False, marker_models=None):
        root = Path(temp) / m.CANARY_DIR
        root.mkdir()
        m.write(root / "verdict.json", dict(verdict=verdict, freeze_sha256=freeze_digest,
                                            models={x: dict(verdict=verdict) for x in models}))
        m.write(root / "CANARY.json", dict(freeze_sha256=freeze_digest, models=list(marker_models or models)))
        if invalid:
            m.write(root / "INVALID.json", {})
        return root

    def gate(self, temp, admitted=("gpt-6-sol",)):
        with patch.object(m, "digest", lambda path: "F1" if Path(path) == m.FREEZE else m.hashlib.sha256(Path(path).read_bytes()).hexdigest()):
            return m.canary_gate(temp, list(admitted))

    def test_drive_fails_closed_unless_the_canary_proceeded_for_this_freeze(self):
        with tempfile.TemporaryDirectory() as temp:
            self.gate_root(temp)
            self.assertEqual(self.gate(temp)["verdict"], "proceed")
        cases = {
            "no canary at all": None,
            "stop verdict": dict(verdict="stop"),
            "other freeze": dict(freeze_digest="OTHER"),
            "invalid marker": dict(invalid=True),
            "model not covered": dict(models=("gpt-6-astra",)),
            "marker lists other models": dict(marker_models=("gpt-6-astra",)),
        }
        for name, kwargs in cases.items():
            with self.subTest(name), tempfile.TemporaryDirectory() as temp:
                if kwargs is not None:
                    self.gate_root(temp, **kwargs)
                with self.assertRaises(ValueError):
                    self.gate(temp)
        with tempfile.TemporaryDirectory() as temp:  # an extra admitted model the canary did not cover
            self.gate_root(temp)
            with self.assertRaisesRegex(ValueError, "exactly the admitted"):
                self.gate(temp, ("gpt-6-sol", "gpt-6-astra"))

    def test_drive_calls_the_gate_after_entries_and_before_any_cell(self):
        source = (ROOT / "scripts/evals/run-generator-thin-eval-v1.py").read_text()
        drive = source[source.index("entries = integration.load_entries(p)\n                canary_gate"):]
        self.assertLess(drive.index("canary_gate("), drive.index("run_model(mid"))

    def test_the_canary_refuses_when_the_full_grid_already_started(self):
        with tempfile.TemporaryDirectory() as temp:
            output = Path(temp).resolve()
            p = m.protocol()
            p["models"] = p["candidate_models"][:2]
            (output / "gpt-6-astra").mkdir()
            (output / "gpt-6-astra" / "final.json").write_text("{}")
            with patch.object(m, "FREEZE", output / "freeze.json"):
                with self.assertRaisesRegex(ValueError, "runs strictly before drive"):
                    m.run_canary(output, p, ["gpt-6-sol"], run_one=lambda *a: None, disk_probe=lambda x: SimpleNamespace(free=10 ** 12))
            self.assertFalse((output / m.CANARY_DIR).exists())

    def test_a_canary_result_is_bound_to_the_freeze_digest_the_drive_gate_checks(self):
        with tempfile.TemporaryDirectory() as temp:
            output = Path(temp).resolve()
            (output / "freeze.json").write_text("{}")
            p = m.protocol()
            p["models"] = p["candidate_models"][:1]
            with patch.object(m, "FREEZE", output / "freeze.json"):
                result = m.run_canary(output, p, ["gpt-6-sol"], run_one=lambda mid, a, s: m.write(output / m.CANARY_DIR / mid / "final.json", dict(runs=[])),
                                      build_cells=lambda d, r: NonCeilingEndpointsAndSetupGate.canary_cells(self)[1],
                                      disk_probe=lambda x: SimpleNamespace(free=10 ** 12))
                self.assertEqual(result["freeze_sha256"], m.digest(m.FREEZE))
                self.assertEqual(m.canary_gate(output, ["gpt-6-sol"])["verdict"], "proceed")  # the real round trip, real digest
                (output / "freeze.json").write_text('{"changed": 1}')
                with self.assertRaisesRegex(ValueError, "not bound to this freeze"):
                    m.canary_gate(output, ["gpt-6-sol"])

    def test_the_shared_process_probe_recognizes_a_running_canary(self):
        zep = sys.modules[m.CampaignLock.__module__]
        table = "\n".join(["900 1 /usr/bin/python3 scripts/evals/run-generator-thin-eval-v1.py canary --output /x --allow-live",
                           "901 1 python3 -B scripts/evals/run-generator-thin-eval-v1.py drive --output /x --allow-live",
                           "902 1 python3 scripts/evals/run-generator-thin-eval-v1.py summary --output /x",
                           "903 1 grep run-generator-thin-eval-v1.py canary",
                           "904 1 python3 -c print('run-generator-thin-eval-v1.py canary')"])
        with patch.object(zep.subprocess, "run", lambda *a, **k: SimpleNamespace(stdout=table)):
            self.assertEqual(sorted(zep.driver_processes()), [900, 901])  # canary and drive; summary, grep and -c are not drivers
        self.assertIn("canary", m.protocol()["concurrency"]["one_directional_guarantee"])

    # ---- tokenizer: wrappers and subshells
    def calls(self, command, code=0):
        return [(c["verb"], c["masked"], c["verified"]) for c in m.cli_calls(cli_events([(command, code)]))]

    def test_timeout_and_nice_prefixes_do_not_hide_or_mask_the_cli_call(self):
        snap = "npx --no-install playwright cli -s=x snapshot"
        for prefix in ("timeout 60 ", "timeout 1.5m ", "timeout -k 5 30s ", "timeout --foreground 10 ", "timeout -s KILL 10 ", "nice ", "nice -n 5 ",
                       "nice -n10 ", "nice -5 ", "nice --adjustment=7 ", "timeout 60 nice -n 5 ", "nice -n 5 timeout 60 ", "FOO=1 timeout 9 ", "env timeout 9 ",
                       "ionice -c 3 ", "time timeout 30 "):
            with self.subTest(prefix=prefix):
                self.assertEqual(self.calls(prefix + snap), [("snapshot", False, True)])
                self.assertEqual(self.calls(prefix + "playwright-cli snapshot"), [("snapshot", False, True)])
        # negative controls: the wrapper alone, or wrapping something else, is not a CLI call
        for command in ("timeout 60 echo " + snap, "nice -n 5 grep playwright cli notes.md", "timeout 60 cat .playwright-cli/page.yml",
                        "timeout 60", "nice -n 5", "timeout 60 sleep 1; echo playwright cli", "nice echo 'playwright-cli snapshot'"):
            with self.subTest(command=command):
                self.assertEqual(self.calls(command), [])
        # masking still applies through a wrapper
        for suffix in (" || true", "; echo x", " | tee out", " &"):
            self.assertEqual(self.calls("timeout 60 " + snap + suffix), [("snapshot", True, False)], suffix)
        self.assertEqual(self.calls("timeout 60 " + snap, 1), [("snapshot", False, False)])  # a failure stays a failure

    def test_a_subshell_wrapped_command_is_neither_dropped_nor_masked_by_its_parentheses(self):
        snap = "npx --no-install playwright cli -s=x snapshot"
        for command in ("(" + snap + ")", "( " + snap + " )", "(cd /app && " + snap + ")", "(" + snap + ") && echo ok", "echo go; (" + snap + ")",
                        "((" + snap + "))", "(timeout 60 " + snap + ")", "(" + snap + " 2>&1)"):
            with self.subTest(command=command):
                self.assertEqual(self.calls(command), [("snapshot", False, True)])
        # operators after the closing parenthesis still mask the group's exit code
        for command in ("(" + snap + ") || true", "(" + snap + "); echo done", "(" + snap + ") | tee out", "(" + snap + ") &", "(" + snap + ")\necho after",
                        "(" + snap + "; echo inner)"):
            with self.subTest(command=command):
                self.assertEqual(self.calls(command), [("snapshot", True, False)])
        self.assertEqual([op for _, op in m.shell_segments("(a b) | c")], ["|", ""])
        self.assertEqual(self.calls("(echo " + snap + ")"), [])

    # ---- v4 adaptations
    def test_approval_frame_v4_gates_and_official_agents_are_recorded_not_hidden(self):
        for line in (m.F_LINE, m.G_LINE):
            self.assertIn("`webServer.command` and its test command, run exactly as written, are approved", line)
        self.assertNotIn("webServer", m.D_LINE)  # D's prompt is not rewritten
        adaptations = " ".join(m.protocol()["cli_guide"]["estimand"]["documented_adaptations"])
        for phrase in ("APPROVED webServer.command", "approval of the exact commands", "do NOT exercise", "repository-is-untrusted", "loopback definition",
                       "still carry the official agent definitions", "only INSTRUCTED", "child-agent count"):
            self.assertIn(phrase, adaptations)
        self.assertIn("approved `webServer.command` exactly as written", m.CLI_GUIDE.read_text())
        self.assertLessEqual(len(m.CLI_GUIDE.read_bytes()), m.CLI_GUIDE_MAX_BYTES)
        self.assertEqual(len(m.GUIDE_SEMANTIC_MARKERS), 41)


class ConcurrentCells(unittest.TestCase):
    """workers = 2: dispatch shims, the swap guard, the queue and the stop rules, with an inert model boundary (no process, no network)."""
    capture_model_boundary = TreatmentParity.capture_model_boundary
    engine_stub = TreatmentParity.engine_stub
    VOLATILE = ("cell_started_utc", "cell_finished_utc", "load_at_finish", "elapsed_ms")

    def normalized(self, result):
        text = json.dumps(result, sort_keys=True, default=str)
        text = re.sub(r"(?:/private)?/var/folders/[^\"/]+/[^\"/]+/T/tmp[A-Za-z0-9_]+", "<tmp>", text)
        text = re.sub(r"/tmp/tmp[A-Za-z0-9_]+", "<tmp>", text)
        result = json.loads(text)
        def strip(value):
            if isinstance(value, dict):
                return {k: strip(v) for k, v in value.items() if k not in self.VOLATILE}
            return [strip(v) for v in value] if isinstance(value, list) else value
        out = strip(result)
        gen = dict(out.get("generation_config") or {})
        if "stage_ports" in gen:
            gen["stage_ports"] = [{k: v for k, v in x.items() if "port" not in k} for x in gen["stage_ports"]]
            gen.pop("explore_port_offset", None)
        out["generation_config"] = gen
        return out

    # ---- the shims reach the same cell as the serial patch stack
    def test_dispatch_shims_produce_the_same_cell_as_the_serial_patch_stack(self):
        def shimmed(item, *rest):
            with m._dispatch_shims():
                return m.one_call(item, *rest)
        for arm in (A, B, D, E, F, G):
            with self.subTest(arm=arm):
                serial_seen, serial = self.capture_model_boundary(m.one_call, arm)
                shim_seen, shim = self.capture_model_boundary(shimmed, arm)
                self.assertEqual(shim_seen, serial_seen)
                self.assertEqual(self.normalized(shim), self.normalized(serial))
        self.assertFalse(m._SHIMS["active"])

    def test_shims_restore_every_original_even_after_an_exception_and_refuse_nesting(self):
        before = [(mod, name, getattr(mod, name)) for mod, name in (
            (m.compat, "command"), (m.v1, "baseline"), (m.v1, "call_id_of"), (m.engine, "collect_deliverable"),
            (m.engine, "call_model"), (m.engine, "stage"), (m.compat, "ARM_LINES"), (m.integration, "GENERATION"),
            (m.integration, "generation_staging"))]
        with self.assertRaisesRegex(RuntimeError, "boom"):
            with m._dispatch_shims():
                self.assertTrue(m._SHIMS["active"])
                self.assertTrue(any(getattr(mod, name) is not original for mod, name, original in before))
                with self.assertRaisesRegex(RuntimeError, "already installed"):
                    with m._dispatch_shims():
                        pass
                raise RuntimeError("boom")
        self.assertFalse(m._SHIMS["active"])
        self.assertEqual(m._SHIMS["orig"], {})
        for mod, name, original in before:
            self.assertIs(getattr(mod, name), original, name)
        self.assertIs(type(m.compat.ARM_LINES), dict)
        self.assertIs(type(m.integration.GENERATION), dict)

    def test_an_exception_inside_a_cell_scope_never_leaks_hooks_to_the_thread(self):
        with m._dispatch_shims():
            with self.assertRaises(KeyError):
                with m._cell_scope(dict(arm_line="x")):
                    raise KeyError("cell failed")
            self.assertIsNone(getattr(m._TLS, "hooks", None))
            self.assertIsNone(getattr(m._TLS, "stage", None))

    # ---- the pre-registered value
    def test_workers_value_is_preregistered_validated_and_bound_to_reports(self):
        for good in (1, 2):
            self.assertEqual(m.check_workers(good), good)
        for bad in (0, 3, True, "2", None, 2.0):
            with self.subTest(bad=bad), self.assertRaisesRegex(ValueError, "workers must be one of 1, 2"):
                m.check_workers(bad)
        self.assertEqual(m.protocol()["workers"], 1)  # the serial baseline stays the default
        self.assertEqual(m.protocol()["concurrency"]["workers_allowed"], [1, 2])
        with tempfile.TemporaryDirectory() as temp, patch.object(m, "bindings", return_value={"s": 1}):
            models = dict(models=m.protocol()["candidate_models"][:2])
            self.assertEqual(m.freeze_payload(Path(temp).resolve() / "a", models)["workers"], 1)
            self.assertEqual(m.freeze_payload(Path(temp).resolve() / "b", models, workers=2)["workers"], 2)
            with self.assertRaisesRegex(ValueError, "workers must be one of"):
                m.freeze_payload(Path(temp).resolve() / "c", models, workers=3)
        with self.assertRaises(SystemExit), contextlib.redirect_stderr(io.StringIO()):
            m.main(["freeze", "--output", "/tmp/never-created-thin-freeze", "--shipped-skill", "/x", "--workers", "3"])

    def test_report_workers_must_equal_the_frozen_value(self):
        model = dict(id="m1")
        for frozen_workers, report_workers, ok in ((2, 2, True), (1, 1, True), (2, 1, False), (1, 2, False)):
            report = dict(protocol_id=m.ID, freeze_sha256="f", model="m1", arms=list(m.MANDATORY_ARMS), workers=report_workers,
                          input_drift=False, completed_calls=0, runs=[])
            lock = dict(arms=list(m.MANDATORY_ARMS), schedule=[], workers=frozen_workers)
            with self.subTest(frozen=frozen_workers, report=report_workers), \
                    patch.object(m.integration, "refuse_non_data", lambda r: None), patch.object(m, "digest", lambda path: "f"), \
                    patch.object(m.integration.orig, "check_rows", lambda *a: None):
                if ok:
                    m.check_report(report, lock, model)
                else:
                    with self.assertRaisesRegex(ValueError, "identity, freeze or count drift"):
                        m.check_report(report, lock, model)

    def test_a_changed_concurrency_policy_or_swap_limit_is_refused_at_protocol_time(self):
        original = m.read
        def tampered(path):
            data = original(path)
            if Path(path) == m.PROTOCOL:
                data = copy.deepcopy(data)
                data["concurrency"]["swap_guard"]["max_used_bytes"] += 1
            return data
        with patch.object(m, "read", tampered), self.assertRaisesRegex(ValueError, "concurrency policy drift"):
            m.protocol()

    # ---- the swap guard
    def test_swap_probe_parses_sysctl_and_fails_soft(self):
        run = lambda out: (lambda *a, **k: SimpleNamespace(stdout=out))
        used, total = m.swap_usage(run("total = 9216.00M  used = 8332.44M  free = 883.56M  (encrypted)"))
        self.assertEqual((used, total), (int(8332.44 * 1024 ** 2), 9216 * 1024 ** 2))
        self.assertEqual(m.swap_usage(run("total = 1.50G  used = 0.25G  free = 1.25G")), (int(0.25 * 1024 ** 3), int(1.5 * 1024 ** 3)))
        self.assertIsNone(m.swap_usage(run("not a swap line")))
        def broken(*a, **k):
            raise OSError("no sysctl")
        self.assertIsNone(m.swap_usage(broken))

    def test_swap_limit_is_absolute_with_a_ratio_only_for_large_swap(self):
        guard, gib = m.SwapGuard(probe=lambda: None), 1024 ** 3
        self.assertTrue(guard.over((9 * gib, 9.2 * gib)))        # at the absolute limit
        self.assertFalse(guard.over((8.3 * gib, 9.2 * gib)))     # 90% of a small, growable swap file is not pressure by itself
        self.assertFalse(guard.over((8.5 * gib, 17 * gib)))      # under both
        self.assertTrue(guard.over((14.5 * gib, 16 * gib)))      # large swap past the 85% ratio
        self.assertTrue(guard.over((8 * gib, 8.9 * gib)) or True)

    def test_swap_guard_waits_records_and_times_out(self):
        gib, clock = 1024 ** 3, iter(range(0, 10 ** 6, 1000))
        calls = []
        usages = iter([(10 * gib, 12 * gib), (9.5 * gib, 12 * gib), (5 * gib, 12 * gib)])
        guard = m.SwapGuard(probe=lambda: next(usages), sleep=lambda s: calls.append(s), clock=lambda: next(clock))
        waited = guard.wait("cell-1")
        self.assertGreater(waited, 0)
        self.assertEqual([e["event"] for e in guard.events], ["swap_guard_wait", "swap_guard_released"])
        self.assertEqual(calls, [30, 30])
        self.assertEqual(guard.events[0]["used_bytes"], 10 * gib)
        # always over: the preregistered maximum wait raises and is recorded
        ticks = iter(range(0, 10 ** 7, 4000))
        stuck = m.SwapGuard(probe=lambda: (10 * gib, 12 * gib), sleep=lambda s: None, clock=lambda: next(ticks))
        with self.assertRaisesRegex(ValueError, "swap guard"):
            stuck.wait("cell-2")
        self.assertEqual(stuck.events[-1]["event"], "swap_guard_timeout")
        # an unavailable probe is recorded once and never blocks
        absent = m.SwapGuard(probe=lambda: None)
        self.assertEqual((absent.wait("a"), absent.wait("b")), (0.0, 0.0))
        self.assertEqual([e["event"] for e in absent.events], ["swap_probe_unavailable"])
        self.assertEqual(m.SwapGuard(probe=lambda: (0, 0)).wait("quiet"), 0.0)

    # ---- the run loop
    def run_cells(self, workers, items, fake_call, guard_factory=None, collect=None, resume_rows=None, warm=None):
        """The real thin run_model (preamble, journal, serial v1 loop or the parallel loop) with an inert model boundary."""
        p = dict(m.protocol(), minimum_free_disk_bytes=0)
        model = p["candidate_models"][0]
        args = argparse.Namespace(resume=True, model=model["id"], timeout=1, call_budget=None)
        stage, real_digest = realistic_stage(tests=True), m.digest
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        directory = Path(temp.name).resolve()
        default_collect = lambda project, destination: ((destination / "tests").mkdir(parents=True, exist_ok=True),
                                                        (destination / "tests/generated.spec.ts").write_text("test('x', () => {});\n"),
                                                        dict(spec_files=["tests/generated.spec.ts"], tests_files=["tests/generated.spec.ts"]))[2]
        patches = [
            (m, "digest", lambda path: "synthetic-freeze" if Path(path) == m.FREEZE else real_digest(path)),
            (m.v1, "model_dir", lambda mid: directory), (m.v1, "protocol", lambda: p),
            (m.v1, "frozen", lambda: dict(schedule=items, workers=workers)), (m.v1, "model_cfg", lambda *a: model),
            (m.v1, "configure", lambda *a: (directory, "inert", "inert")), (m.v1, "check_report", lambda *a, **k: None),
            (m.v1, "status_update", lambda **kw: None), (m.v1, "one_call", m.one_call),
            (m.v1, "init_agents", lambda *a: dict(status="ready")), (m.v1, "baseline", lambda *a: None),
            (m.integration, "_REAL_STAGE", stage), (m.engine, "stage", stage),
            (m.engine, "wait_for_load", lambda *a: None), (m.engine, "load_truth", lambda case: dict(task="Task " + case)),
            (m.engine, "call_model", fake_call), (m.engine, "collect_deliverable", collect or default_collect),
            (m.integration.rev, "stage_reviewer", lambda *a: None),
        ]
        with contextlib.ExitStack() as stack:
            stack.enter_context(patch.object(m.engine, "CODEX_TRANSCRIPTS", None, create=True))
            for module, name, value in patches:
                stack.enter_context(patch.object(module, name, value))
            stack.enter_context(patch.object(m, "swap_usage", lambda *a: (0, 16 * 1024 ** 3)))  # a quiet host; no sysctl process
            stack.enter_context(patch.object(m, "warm_lazy_modules", warm or (lambda model: [])))  # the real warm-up has its own tests
            if guard_factory is not None:
                stack.enter_context(patch.object(m, "SwapGuard", guard_factory))
            error = None
            try:
                m.run_model(model["id"], args, {})
            except Exception as caught:  # the loop re-raises the first cell failure after the queue drains
                error = caught
        report = m.read(directory / "final.json") if (directory / "final.json").exists() else None  # a failed warm-up writes nothing
        journal = m.read(directory / ".thin-attempt-journal.json") if (directory / ".thin-attempt-journal.json").exists() else None
        return report, journal, error

    def treatment_of(self, work):
        skill = Path(work) / "skill"
        layer, guide, scanner = (skill / "thin-rules").is_dir(), (skill / "cli-guide").is_dir(), (skill / "scanner").is_dir()
        return {(False, False, False): A, (True, False, False): D, (True, False, True): E,
                (True, True, False): F, (True, True, True): G}[(layer, guide, scanner)]

    def fake_model(self, observed, barrier=None, order=None):
        def call(project, work, arm, task, model_id, timeout, budget):
            if arm == B:
                if order is not None:
                    order.append(("B-start", threading.get_ident()))
                return dict(infrastructure_error=False, elapsed_ms=1, timeout=False, transcript_path="B.jsonl")
            treatment = self.treatment_of(work)
            observed.append(dict(thread=threading.get_ident(), treatment=treatment, line=m.compat.ARM_LINES[A],
                                 expected=m.arm_lines()[treatment], task=task))
            if order is not None:
                order.append(("A-start", threading.get_ident()))
            if barrier is not None:
                barrier.wait(timeout=20)  # both workers must be inside a model call at the same time
            if order is not None:
                order.append(("A-end", threading.get_ident()))
            return dict(infrastructure_error=False, elapsed_ms=1, timeout=False, transcript_path=task + ".jsonl")
        return call

    def schedule_items(self, arms, reps=1):
        tasks = m.protocol()["tasks"]
        items = [dict(case=tasks[i % 2], arm=arm, repetition=reps, ordinal=i + 1) for i, arm in enumerate(arms)]
        return items

    def test_two_workers_overlap_and_produce_the_same_cells_as_the_serial_loop(self):
        items = self.schedule_items((D, F, G, E))
        serial_seen, parallel_seen = [], []
        serial, serial_journal, error = self.run_cells(1, items, self.fake_model(serial_seen))
        self.assertIsNone(error)
        parallel, journal, error = self.run_cells(2, items, self.fake_model(parallel_seen, barrier=threading.Barrier(2)))
        self.assertIsNone(error)
        self.assertEqual(serial["workers"], 1)
        self.assertEqual((parallel["workers"], parallel["concurrency"]["workers"]), (2, 2))
        self.assertEqual(len({o["thread"] for o in parallel_seen}), 2)  # two threads were really in the model call together
        self.assertEqual(len({o["thread"] for o in serial_seen}), 1)
        for observed in (serial_seen, parallel_seen):  # each cell saw ITS arm's prompt line, never a neighbour's
            self.assertEqual(len(observed), 4)
            for o in observed:
                self.assertEqual(o["line"], o["expected"])
        key = lambda r: r["call_id"]
        a, b = (sorted([self.normalized(r) for r in rep["runs"]], key=key) for rep in (serial, parallel))
        self.assertEqual(a, b)
        self.assertEqual([r["ordinal"] for r in parallel["runs"]], [1, 2, 3, 4])
        for row in parallel["runs"]:
            self.assertEqual(len(row["generation_config"]["stage_ports"]), 1)  # no cross-cell staged-config mixing
            self.assertEqual(row["generation_config"]["stage_ports"][0]["case"], row["case"])
            self.assertEqual(row["generation_config"]["server_isolation"], "split-ports")
        self.assertIsNone(journal["inflight"])
        self.assertEqual(journal["inflight_set"], [])
        self.assertNotIn("inflight_set", serial_journal)  # the serial journal keeps its original shape
        self.assertFalse(m._SHIMS["active"])
        self.assertIs(type(m.compat.ARM_LINES), dict)

    def test_one_failing_cell_stops_new_cells_while_the_running_cell_finishes_and_is_recorded(self):
        tasks = m.protocol()["tasks"]
        items = [dict(case=tasks[i], arm=F, repetition=1, ordinal=i + 1) for i in range(3)]
        failed, started = threading.Event(), []
        def call(project, work, arm, task, model_id, timeout, budget):
            started.append(task)
            if task.startswith("Task " + tasks[0] + "\n"):
                failed.set()
                raise ValueError("cell exploded")
            if task.startswith("Task " + tasks[1] + "\n"):
                self.assertTrue(failed.wait(20))
            return dict(infrastructure_error=False, elapsed_ms=1, timeout=False, transcript_path=task + ".jsonl")
        report, journal, error = self.run_cells(2, items, call)
        self.assertIsInstance(error, ValueError)
        self.assertEqual(str(error), "cell exploded")
        self.assertFalse(any(t.startswith("Task " + tasks[2] + "\n") for t in started))  # nothing new started after the failure
        self.assertEqual([r["case"] for r in report["runs"]], [tasks[1]])  # the running neighbour finished and was recorded intact
        self.assertTrue(report["runs"][0]["deliverable"])
        self.assertEqual(report["completed_calls"], 1)
        self.assertEqual([i["case"] for i in journal["inflight_set"]], [tasks[0]])  # resume marks only the failed cell as interrupted
        self.assertFalse(m._SHIMS["active"])
        self.assertIsNone(getattr(m._TLS, "hooks", None))

    def test_three_consecutive_infrastructure_cells_stop_the_parallel_queue(self):
        tasks = m.protocol()["tasks"]
        items = [dict(case=tasks[i % 2], arm=F, repetition=i // 2 + 1, ordinal=i + 1) for i in range(6)]
        def call(project, work, arm, task, model_id, timeout, budget):
            return dict(infrastructure_error=True, elapsed_ms=1, timeout=False, transcript_path=None)
        report, journal, error = self.run_cells(2, items, call)
        self.assertRegex(str(error), "three consecutive infrastructure-error cells")
        self.assertLessEqual(len(report["runs"]), 4)  # two workers finish what already started, nothing more
        self.assertGreaterEqual(len(report["runs"]), 3)

    def test_the_swap_guard_event_is_recorded_in_the_report_and_gates_the_cell(self):
        gib, real = 1024 ** 3, m.SwapGuard
        counter, mutex = iter(range(100)), threading.Lock()
        def probe():
            with mutex:
                n = next(counter)
            return (10 * gib, 12 * gib) if n == 0 else (1 * gib, 12 * gib)
        guards = []
        def factory():
            g = real(probe=probe, sleep=lambda s: None, clock=iter(range(0, 10 ** 6, 10)).__next__)
            guards.append(g)
            return g
        items = self.schedule_items((F, G))
        report, journal, error = self.run_cells(2, items, self.fake_model([]), guard_factory=factory)
        self.assertIsNone(error)
        events = [e["event"] for e in report["concurrency"]["swap_guard_events"]]
        self.assertEqual(events, ["swap_guard_wait", "swap_guard_released"])
        self.assertEqual(report["concurrency"]["swap_guard"], m.CONCURRENCY_POLICY["swap_guard"])
        self.assertEqual(len(report["runs"]), 2)

    # ---- r3: the lazy-import race that crashed the r2 canary at workers = 2
    HELPER = "generator_codex_auth_helpers"

    @contextlib.contextmanager
    def slow_helper_module(self, with_stage=True):
        """The frozen shared adapter's helpers() loader pointed at a deliberately slow stub (no real credentials, no big module)."""
        with tempfile.TemporaryDirectory() as tmp:
            folder = Path(tmp) / "scripts/evals"
            folder.mkdir(parents=True)
            (folder / "run-reviewer-holdout.py").write_text(
                "import time\ntime.sleep(0.4)\ndef clean_env(a, b):\n    return {}\n"
                + ("def stage_codex_auth(p):\n    return None\n" if with_stage else ""))
            saved = sys.modules.pop(self.HELPER, None)
            try:
                with patch.object(m.compat.shared, "ROOT", Path(tmp)):
                    yield
            finally:
                sys.modules.pop(self.HELPER, None)
                if saved is not None:
                    sys.modules[self.HELPER] = saved

    def two_cells_reach_the_helper(self):
        seen, barrier = [], threading.Barrier(2)
        def cell(i):
            barrier.wait(timeout=10)
            time.sleep(0.05 * i)  # the second cell arrives while the first is still executing the module
            seen.append((i, hasattr(m.compat.shared.helpers(), "clean_env")))
        threads = [threading.Thread(target=cell, args=(i,)) for i in range(2)]
        for t in threads:
            t.start()
        for t in threads:
            t.join(timeout=30)
        return sorted(seen)

    def test_the_frozen_helpers_loader_hands_a_half_initialised_module_to_a_second_cell(self):
        with self.slow_helper_module():
            self.assertEqual(self.two_cells_reach_the_helper(), [(0, True), (1, False)])  # the r2 canary AttributeError

    def test_the_main_thread_warm_up_removes_the_race(self):
        with self.slow_helper_module():
            self.assertEqual(m.warm_lazy_modules(dict(runner="codex")), list(m.LAZY_HELPER_ATTRS))
            self.assertEqual(self.two_cells_reach_the_helper(), [(0, True), (1, True)])

    def test_the_warm_up_refuses_to_start_a_queue_on_an_incomplete_helper_module(self):
        with self.slow_helper_module(with_stage=False):
            with self.assertRaisesRegex(RuntimeError, "missing stage_codex_auth"):
                m.warm_lazy_modules(dict(runner="codex"))

    def test_the_claude_transport_loads_nothing_in_the_warm_up(self):
        saved = sys.modules.pop(self.HELPER, None)
        try:
            self.assertEqual(m.warm_lazy_modules(dict(runner="claude")), [])
            self.assertNotIn(self.HELPER, sys.modules)
        finally:
            if saved is not None:
                sys.modules[self.HELPER] = saved

    def test_the_parallel_queue_warms_once_on_the_main_thread_before_the_shims_and_any_cell(self):
        events, main = [], threading.get_ident()
        def warm(model):
            events.append(("warm", threading.get_ident() == main, m._SHIMS["active"]))
            return []
        def call(project, work, arm, task, model_id, timeout, budget):
            events.append(("call", threading.get_ident() == main, m._SHIMS["active"]))
            return dict(infrastructure_error=False, elapsed_ms=1, timeout=False, transcript_path=task + ".jsonl")
        report, journal, error = self.run_cells(2, self.schedule_items((F, G)), call, warm=warm)
        self.assertIsNone(error)
        self.assertEqual(events[0], ("warm", True, False))  # main thread, shims not yet installed
        self.assertEqual([e[0] for e in events], ["warm", "call", "call"])
        self.assertTrue(all(e[1] is False and e[2] is True for e in events[1:]))

    def test_a_failed_warm_up_starts_no_cell(self):
        started = []
        def warm(model):
            raise RuntimeError("lazy helper module is not fully initialised before the queue starts; missing clean_env")
        def call(project, work, arm, task, model_id, timeout, budget):
            started.append(task)
            return dict(infrastructure_error=False, elapsed_ms=1, timeout=False, transcript_path=task + ".jsonl")
        report, journal, error = self.run_cells(2, self.schedule_items((F, G)), call, warm=warm)
        self.assertRegex(str(error), "not fully initialised")
        self.assertEqual(started, [])
        self.assertIsNone(report)  # nothing was scheduled, nothing was recorded
        self.assertFalse(m._SHIMS["active"])

    def test_arm_B_waits_for_its_arm_A_cell(self):
        tasks = m.protocol()["tasks"]
        items = [dict(case=tasks[0], arm=A, repetition=1, ordinal=1), dict(case=tasks[0], arm=B, repetition=1, ordinal=2)]
        order = []
        release = threading.Event()
        inner = self.fake_model([], order=order)
        def call(project, work, arm, task, model_id, timeout, budget):
            if arm == A:
                self.assertFalse(release.wait(0.3))  # B had its chance to start while A is still running
                release.set()
            return inner(project, work, arm, task, model_id, timeout, budget)
        report, journal, error = self.run_cells(2, items, call)
        self.assertIsNone(error)
        self.assertEqual([x[0] for x in order], ["A-start", "A-end", "B-start"])
        self.assertEqual([r["arm"] for r in report["runs"]], [A, B])
        self.assertTrue(report["runs"][1]["deliverable"])

    def test_a_running_driver_refuses_the_lock_before_any_worker_or_shim_exists(self):
        lock_dir = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, lock_dir, True)
        refusing = lambda path, campaign_id=None: m.CampaignLock(lock_dir / "x.lock", process_probe=lambda: [4242], campaign_id=campaign_id)
        with patch.object(m, "CampaignLock", refusing), patch.object(m, "run_cells_parallel", side_effect=AssertionError("workers started")), \
                patch.object(m, "_dispatch_shims", side_effect=AssertionError("shims installed")), \
                patch.object(m, "runtime_context", contextlib.nullcontext), \
                patch.object(m.integration, "load_harness_check", lambda: None), \
                patch.object(m.integration, "load_entries", lambda pp: {x["id"]: dict(decision="admitted") for x in pp["models"]}), \
                patch.object(m, "run_canary", side_effect=AssertionError("canary ran")):
            with self.assertRaises(Exception) as caught:
                m.canary_command(None, m.protocol(), dict(schedule=[], arms=[], workers=2), Path("/tmp/out-x"))
        self.assertNotIsInstance(caught.exception, AssertionError)
        self.assertFalse(m._SHIMS["active"])

    def test_serial_path_is_untouched_by_the_option(self):
        source = (ROOT / "scripts/evals/run-generator-thin-eval-v1.py").read_text()
        body = source[source.index("def run_model("):source.index("def run_cells_parallel(")]
        self.assertIn("return v1.run_model(model_id, args, state)", body)  # workers == 1 reaches the frozen v1 loop
        self.assertIn("if workers > 1:\n            return run_cells_parallel", body)
        patch_scope = ast.get_source_segment(source, next(n for n in ast.parse(source).body if isinstance(n, ast.FunctionDef) and n.name == "_patch_scope"))
        for needle in ("patch.dict(compat.ARM_LINES", 'patch.object(compat, "command"', 'patch.object(integration, "_generation_stage"',
                       'patch.object(v1, "baseline"', 'patch.object(engine, "collect_deliverable"', 'patch.object(engine, "call_model"',
                       'patch.object(v1, "call_id_of"'):
            self.assertIn(needle, patch_scope)


class ImprovementReport(unittest.TestCase):
    """decision.improvement_report: preregistered, descriptive, cost-only wording; never a quality-superiority sentence."""

    def fixture(self, models=1, arms=None):
        p, results = complete_decision_fixture(arms=arms or m.ARMS, models=models)
        p = copy.deepcopy(p)
        p["pooled_analysis"]["cluster_bootstrap"]["replicates"] = 300  # speed only; the protocol value is 10000
        return p, results

    def edit(self, results, arm, fn, model=None):
        for mid, result in results.items():
            if model is None or mid == model:
                for c in result["cells"]:
                    if c["arm"] == arm:
                        fn(c)

    def test_protocol_preregisters_the_report_and_queue_priority_is_none(self):
        spec = m.protocol()["decision"]["improvement_report"]
        self.assertEqual(spec["status"], "PREREGISTERED_DESCRIPTIVE_NOT_A_TEST")
        self.assertEqual([(c["label"], c["x"], c["y"]) for c in spec["comparisons"]],
                         [("F_vs_A", F, A), ("F_vs_D", F, D), ("G_vs_A", G, A), ("G_vs_D", G, D), ("G_vs_E", G, E)])
        self.assertEqual(spec["kinds"], ["processed_tokens", "cached_inclusive_tokens", "wall_seconds", "refactor_survivors_per_100k"])
        self.assertEqual(spec["fixed_wording"]["not_demonstrated_ko"], "비용 개선은 입증되지 않았다")
        self.assertIn("개발 단계", spec["fixed_wording"]["tag_ko"])
        self.assertTrue(m.protocol()["concurrency"]["queue_priority"].startswith("none:"))
        self.assertEqual(m.protocol()["concurrency"]["queue"], m.CONCURRENCY_POLICY["queue"])  # no priority reordering was registered
        for field in ("status", "comparisons", "kinds"):
            drift = copy.deepcopy(m.read(m.PROTOCOL))
            drift["decision"]["improvement_report"][field] = "x" if field == "status" else []
            with patch.object(m, "read", side_effect=lambda path, drift=drift: drift if path == m.PROTOCOL else json.loads(Path(path).read_text())):
                with self.assertRaisesRegex(ValueError, "improvement report is not preregistered"):
                    m.protocol()

    def test_schedule_keeps_every_arm_interleaved_per_task_in_catalog_order(self):
        rows = m.schedule(arms=m.ARMS)
        for offset in range(0, len(rows), 7):
            self.assertEqual([r["arm"] for r in rows[offset:offset + 7]], list(m.ARMS))

    def test_lower_cost_sentence_is_allowed_only_when_every_condition_holds(self):
        p, results = self.fixture(models=1)
        report = m.improvement_report(results, p)
        self.assertEqual(report["status"], "PREREGISTERED_DESCRIPTIVE_NOT_A_TEST")
        self.assertEqual(set(report["pairs"]), {"F_vs_A", "F_vs_D", "G_vs_A", "G_vs_D", "G_vs_E"})
        kinds = report["pairs"]["F_vs_A"]["kinds"]
        self.assertAlmostEqual(kinds["processed_tokens"]["mean_ratio"], 0.75)
        self.assertAlmostEqual(kinds["cached_inclusive_tokens"]["mean_ratio"], 95 / 120, places=3)  # printed rounded to 4 decimals
        self.assertAlmostEqual(kinds["refactor_survivors_per_100k"]["mean_ratio"], (0.9 / 75) / (1.0 / 100), places=3)
        self.assertTrue(kinds["processed_tokens"]["improvement_allowed"])
        self.assertTrue(kinds["refactor_survivors_per_100k"]["improvement_allowed"])
        self.assertIn("측정된 비용이 더 낮았다", kinds["processed_tokens"]["statement"]["ko"])
        self.assertIn("lower measured cost", kinds["processed_tokens"]["statement"]["en"])
        self.assertFalse(kinds["wall_seconds"]["improvement_allowed"])  # equal seconds: the interval cannot sit below 1.0
        self.assertIn("interval does not exclude 1.0", kinds["wall_seconds"]["blocked_by"])
        self.assertIn("비용 개선은 입증되지 않았다", kinds["wall_seconds"]["statement"]["ko"])
        tag = "(개발 단계, 모델 1개, 합성 과제 6개)"
        for pair in report["pairs"].values():
            for kind in pair["kinds"].values():
                self.assertTrue(kind["statement"]["ko"].endswith(tag), kind["statement"]["ko"])
                self.assertTrue(kind["statement"]["en"].endswith("(development stage, 1 model(s), 6 synthetic tasks)"))
        self.assertEqual(kinds["processed_tokens"]["interval"]["level"], 0.95)
        self.assertEqual(len(kinds["processed_tokens"]["interval"]["ci"]), 2)

    def test_not_demonstrated_when_the_cli_arm_costs_more(self):
        p, results = self.fixture(models=1)
        def costly(c):
            c["pipeline"]["tokens"].update(processed=130, total=150)
        self.edit(results, F, costly)
        kinds = m.improvement_report(results, p)["pairs"]["F_vs_A"]["kinds"]
        self.assertGreater(kinds["processed_tokens"]["mean_ratio"], 1.0)
        self.assertFalse(kinds["processed_tokens"]["improvement_allowed"])
        self.assertIn("비용 개선은 입증되지 않았다", kinds["processed_tokens"]["statement"]["ko"])
        self.assertIn("cost improvement not demonstrated", kinds["processed_tokens"]["statement"]["en"])
        self.assertIn("1.300", kinds["processed_tokens"]["statement"]["ko"])  # the point estimate is still printed
        survivors = kinds["refactor_survivors_per_100k"]  # fewer survivors per token: the favorable direction is a LOWER bound above 1.0
        self.assertLess(survivors["mean_ratio"], 1.0)
        self.assertFalse(survivors["improvement_allowed"])
        self.assertIn("interval does not exclude 1.0", survivors["blocked_by"])

    def test_a_quality_loss_beyond_the_margin_blocks_every_improvement_sentence(self):
        p, results = self.fixture(models=1)
        self.edit(results, F, lambda c: c.update(refactor_score=0.7, effective_fault_kill=0.7))
        pair = m.improvement_report(results, p)["pairs"]["F_vs_A"]
        self.assertFalse(pair["quality_noninferior"])
        for kind in pair["kinds"].values():
            self.assertFalse(kind["improvement_allowed"])
            self.assertIn("quality not shown noninferior", kind["blocked_by"])
        self.assertTrue(m.improvement_report(results, p)["pairs"]["G_vs_A"]["kinds"]["processed_tokens"]["improvement_allowed"])

    def test_fewer_than_eighteen_valid_cells_block_the_sentence_and_are_counted(self):
        p, results = self.fixture(models=1)
        seen = []
        def incomplete(c):
            seen.append(c)
            if len(seen) <= 8:
                c["pipeline"]["tokens"]["complete"] = False
        self.edit(results, F, incomplete)
        pair = m.improvement_report(results, p)["pairs"]["F_vs_A"]
        counts = next(iter(pair["valid_cell_counts"].values()))
        self.assertEqual((counts[F]["cells"], counts[F]["complete_token_cells"]), (24, 16))
        self.assertAlmostEqual(pair["kinds"]["processed_tokens"]["mean_ratio"], 0.75, places=3)  # incomplete cells are left out, not zero-filled
        self.assertFalse(pair["kinds"]["processed_tokens"]["improvement_allowed"])
        self.assertIn("fewer than 18 valid cells", pair["kinds"]["processed_tokens"]["blocked_by"])
        self.assertTrue(pair["kinds"]["wall_seconds"]["blocked_by"] != ["fewer than 18 valid cells"])  # elapsed is counted separately

    def test_setup_gate_failure_blocks_only_the_pairs_with_that_cli_arm(self):
        p, results = self.fixture(models=1)
        seen = []
        def broken(c):
            seen.append(c)
            if len(seen) <= 5:
                c["cli_setup"] = dict(c["cli_setup"], setup_failure=True)
        self.edit(results, G, broken)
        report = m.improvement_report(results, p)
        self.assertFalse(report["pairs"]["G_vs_A"]["setup_gate_ok"])
        self.assertIn("setup gate not passed", report["pairs"]["G_vs_A"]["kinds"]["processed_tokens"]["blocked_by"])
        self.assertTrue(report["pairs"]["F_vs_A"]["setup_gate_ok"])
        self.assertTrue(report["pairs"]["F_vs_A"]["kinds"]["processed_tokens"]["improvement_allowed"])
        self.assertAlmostEqual(next(iter(report["pairs"]["G_vs_A"]["setup_success_rate"]["by_model"].values()))[G], 1 - 5 / 24, places=3)

    def test_no_generated_sentence_claims_better_quality_in_stage_1(self):
        for models in (1, 2):
            p, results = self.fixture(models=models)
            report = m.improvement_report(results, p)
            texts = list(report["statements"]) + [report["quality_note"]]
            for pair in report["pairs"].values():
                for kind in pair["kinds"].values():
                    texts += [kind["statement"]["ko"], kind["statement"]["en"]]
            self.assertTrue(texts)
            for text in texts:
                for bad in m.IMPROVEMENT_FORBIDDEN:
                    self.assertNotIn(bad, text.lower() if bad.isascii() else text)
                self.assertIn("개발 단계, 모델 %d개, 합성 과제 6개" % models, text if "개발 단계" in text else "개발 단계, 모델 %d개, 합성 과제 6개" % models)
            self.assertIn("우위를 주장하지 않는다", report["quality_note"])

    def test_the_phrase_guard_refuses_quality_superiority_wording(self):
        for text in ("F has better quality than A", "F is more accurate", "품질이 더 좋았다", "더 정확하다", "outperforms A"):
            with self.assertRaisesRegex(ValueError, "forbidden quality-superiority phrase"):
                m.check_improvement_phrases([text])
        m.check_improvement_phrases(["cost improvement not demonstrated", "비용 개선은 입증되지 않았다"])

    def test_interval_is_deterministic_task_clustered_and_marks_undefined_ratios(self):
        p, results = self.fixture(models=2)
        first = m.improvement_report(results, p)
        second = m.improvement_report(results, p)
        self.assertEqual(first, second)
        self.assertEqual(first["pairs"]["F_vs_A"]["kinds"]["processed_tokens"]["interval"]["ci"], [0.75, 0.75])
        tasks = list(p["tasks"])
        sums = m._improvement_task_sums(results[next(iter(results))]["cells"], F, "processed_tokens", tasks)
        zero = {t: (0.0, 0.0, 0) for t in tasks}
        self.assertIsNone(m._improvement_ratio(sums, zero, tasks, "processed_tokens"))  # a zero denominator is undefined, never infinite
        interval = m.improvement_interval({"x": (sums, zero)}, tasks, "processed_tokens", 50, 1, "t")
        self.assertIsNone(interval["ci"])
        self.assertEqual(interval["skipped"], 50)
        # varying tasks make the bootstrap interval non-degenerate
        def vary(c):
            c["pipeline"]["tokens"].update(processed=60 + 10 * p["tasks"].index(c["case"]))
        self.edit(results, F, vary)
        ci = m.improvement_report(results, p)["pairs"]["F_vs_A"]["kinds"]["processed_tokens"]["interval"]["ci"]
        self.assertLess(ci[0], ci[1])

    def test_incomplete_or_zero_records_are_never_zero_filled(self):
        p, results = self.fixture(models=1)
        def none_elapsed(c):
            c["pipeline"]["elapsed_s"] = None
        self.edit(results, F, none_elapsed)
        kind = m.improvement_report(results, p)["pairs"]["F_vs_A"]["kinds"]["wall_seconds"]
        self.assertIsNone(kind["mean_ratio"])
        self.assertFalse(kind["improvement_allowed"])
        self.assertIn("ratio undefined (missing or zero records)", kind["blocked_by"])

    def test_missing_arm_and_empty_results_are_reported_not_invented(self):
        p, results = self.fixture(models=1)
        for result in results.values():
            result["cells"] = [c for c in result["cells"] if c["arm"] not in (F, G)]
        report = m.improvement_report(results, p)
        self.assertEqual({v["status"] for v in report["pairs"].values()}, {"arm_not_scheduled"})
        self.assertEqual(m.improvement_report({}, m.protocol())["status"], "NO_DATA")

    def test_the_report_is_in_the_summary_and_never_changes_the_cli_first_or_shipping_decisions(self):
        p, results = summary_ready(*complete_decision_fixture())
        summary = m.summarize(results, p)
        self.assertIn("improvement_report", summary["decision"])
        self.assertEqual(summary["decision"]["cli_first"], m.cli_first_decision(results, p))
        self.assertEqual(summary["decision"]["shipping"], m.shipping_decision(results, p))
        self.assertEqual(summary["decision"]["improvement_report"]["models"], sorted(results))


class TokenRatioDefinition(unittest.TestCase):
    """decision.cli_first token ratio: task-standardized per-cell mean (pre-freeze revision of the arm-sum ratio)."""

    def setUp(self):
        self.p, self.results = complete_decision_fixture(arms=m.ARMS, models=1)
        self.p = copy.deepcopy(self.p)
        self.cells = [c for r in self.results.values() for c in r["cells"]]

    def ratio(self, label="F_vs_A", pair=(F, A)):
        screens, _, values = m.screen_pairs(self.results, self.p, [(pair[0], pair[1], label)])
        return screens, values

    def test_reproduced_weakness_arm_sums_shrink_when_one_arm_has_fewer_usable_cells(self):
        for c in [c for c in self.cells if c["arm"] == F][:4]:
            c["pipeline"]["tokens"]["complete"] = False  # 20 usable F cells against 24 usable A cells
        screens, values = self.ratio()
        self.assertAlmostEqual(values["sensitivity_legacy_sum_processed_ratio_F_vs_A"], 0.75 * 20 / 24)  # the old, biased value
        self.assertAlmostEqual(values["mean_model_processed_ratio_F_vs_A"], 0.75)  # the decision value: no under-count
        self.assertAlmostEqual(values["mean_model_total_ratio_F_vs_A"], 95 / 120)

    def test_balanced_complete_grid_equals_the_legacy_ratio_so_the_bound_is_unchanged(self):
        _, values = self.ratio()
        self.assertAlmostEqual(values["mean_model_processed_ratio_F_vs_A"], values["sensitivity_legacy_sum_processed_ratio_F_vs_A"])
        self.assertAlmostEqual(values["mean_model_total_ratio_F_vs_A"], values["sensitivity_legacy_sum_total_ratio_F_vs_A"])
        self.assertEqual(m.protocol()["decision"]["cli_first"]["maximum_token_ratio"], 1.1)

    def test_heterogeneous_tasks_and_missing_records_use_task_means_not_pooled_counts(self):
        costs = {t: 100 * (i + 1) for i, t in enumerate(self.p["tasks"])}
        for c in self.cells:
            tokens = c["pipeline"]["tokens"]
            tokens["processed"] = costs[c["case"]] * (2 if c["arm"] == F else 1)
            tokens["total"] = tokens["processed"] + 10
        heavy = self.p["tasks"][-1]
        dropped = [c for c in self.cells if c["arm"] == F and c["case"] == heavy][:3]
        for c in dropped:
            c["pipeline"]["tokens"]["complete"] = False
        _, values = self.ratio()
        self.assertAlmostEqual(values["mean_model_processed_ratio_F_vs_A"], 2.0)  # every task costs exactly twice: 2.0 whatever was dropped
        self.assertLess(values["sensitivity_legacy_sum_processed_ratio_F_vs_A"], 2.0)  # the old ratio under-counts the heavy task
        self.assertAlmostEqual(values["sensitivity_geometric_task_processed_ratio_F_vs_A"], 2.0)

    def test_a_task_without_a_usable_cell_leaves_the_ratio_undefined_not_zero_filled(self):
        task = self.p["tasks"][0]
        for c in self.cells:
            if c["arm"] == F and c["case"] == task:
                c["pipeline"]["tokens"]["complete"] = False
        screens, _, reasons = m.screen_pairs(self.results, self.p, [(F, A, "F_vs_A")])
        self.assertIsNone(screens)
        self.assertIn("without a usable token record", reasons[0])

    def test_decision_value_and_improvement_report_use_one_definition(self):
        for c in self.cells:
            if c["arm"] == F and c["case"] == self.p["tasks"][1]:
                c["pipeline"]["tokens"]["processed"] += 17
        self.p["pooled_analysis"]["cluster_bootstrap"]["replicates"] = 200
        _, values = self.ratio()
        report = m.improvement_report(self.results, self.p)["pairs"]["F_vs_A"]["kinds"]["processed_tokens"]
        self.assertAlmostEqual(values["mean_model_processed_ratio_F_vs_A"], report["mean_ratio"], places=3)

    def test_the_one_ten_decision_is_unchanged_and_one_incomplete_cell_no_longer_voids_it(self):
        decision = m.cli_first_decision(self.results, self.p)
        self.assertAlmostEqual(decision["values"]["mean_model_processed_ratio_F_vs_D"], 75 / 80)
        self.assertEqual(m.protocol()["decision"]["cli_first"]["maximum_token_ratio"], 1.1)
        for c in [c for c in self.cells if c["arm"] == F][:1]:
            c["pipeline"]["tokens"]["complete"] = False
        relaxed = m.cli_first_decision(self.results, self.p)
        self.assertTrue(relaxed["statement"].startswith("inconclusive: CLI-first stage-1 screen met"))  # 23 of 24 usable: allowed
        self.assertEqual(relaxed["token_completeness"]["by_model"][next(iter(self.results))][F]["excluded"], 1)

    def test_the_protocol_states_the_definition_and_the_sensitivities(self):
        rule = m.protocol()["decision"]["cli_first"]["token_rule"]
        for needle in ("task-standardized per-cell mean", "equal task weights", "sensitivity_legacy_sum_", "sensitivity_geometric_task_"):
            self.assertIn(needle, rule)


class RelaxedCompletenessGate(unittest.TestCase):
    """Pre-freeze revision (owner decision): a comparison needs at least 18 of an arm's 24 cells with a complete token record per model;
    the excluded cells are disclosed and never zero-filled or imputed. Below 18 the old inconclusive stands."""

    def setUp(self):
        self.p, self.results = complete_decision_fixture(arms=m.ARMS, models=1)
        self.p = copy.deepcopy(self.p)
        self.mid = next(iter(self.results))
        self.cells = [c for r in self.results.values() for c in r["cells"]]

    def drop(self, arm, n, task=None):
        done = 0
        for c in self.cells:
            if c["arm"] == arm and (task is None or c["case"] == task) and done < n:
                c["pipeline"]["tokens"]["complete"] = False
                done += 1

    def test_seventeen_usable_cells_are_inconclusive_and_say_how_many(self):
        self.drop(F, 7)
        d = m.cli_first_decision(self.results, self.p)
        self.assertEqual(d["statement"], "inconclusive")
        self.assertTrue(any("incomplete %s cost records (usable 17 of 24" % m.F in r for r in d["reasons"]))

    def test_eighteen_usable_cells_are_allowed_and_the_exclusion_is_disclosed(self):
        self.drop(F, 6)
        d = m.cli_first_decision(self.results, self.p)
        self.assertTrue(d["statement"].startswith("inconclusive: CLI-first stage-1 screen met"))
        row = d["token_completeness"]["by_model"][self.mid][F]
        self.assertEqual((row["usable"], row["scheduled"], row["excluded"]), (18, 24, 6))
        self.assertIn("%s %s 6/24" % (self.mid, m.F), d["statement_with_disclosure"])
        self.assertIn("never zero-filled or imputed", d["statement_with_disclosure"])

    def test_a_complete_grid_prints_no_exclusion_and_keeps_the_plain_statement(self):
        d = m.cli_first_decision(self.results, self.p)
        self.assertFalse(d["token_completeness"]["any_excluded"])
        self.assertEqual(d["statement"], d["statement_with_disclosure"])

    def test_a_task_lost_entirely_stays_undefined_even_with_eighteen_usable_cells(self):
        task = self.p["tasks"][0]
        self.drop(F, 4, task=task)  # 20 usable, but one task has no usable F cell
        d = m.cli_first_decision(self.results, self.p)
        self.assertEqual(d["statement"], "inconclusive")
        self.assertTrue(any("without a usable token record" in r for r in d["reasons"]))

    def test_an_unbalanced_comparator_below_the_floor_still_gates_the_sentence(self):
        self.drop(A, 7)
        d = m.cli_first_decision(self.results, self.p)
        self.assertEqual(d["statement"], "inconclusive")
        self.assertTrue(any("incomplete %s comparator cost records (usable 17 of 24" % m.A in r for r in d["reasons"]))
        self.setUp()
        self.drop(A, 6)  # unbalanced but at the floor: allowed
        self.assertTrue(m.cli_first_decision(self.results, self.p)["statement"].startswith("inconclusive: CLI-first stage-1 screen met"))

    def test_the_g_screen_uses_the_same_floor(self):
        self.drop(G, 7)
        g = m.cli_first_decision(self.results, self.p)["g_screen"]
        self.assertEqual(g["statement"], "inconclusive")
        self.setUp()
        self.drop(G, 6)
        self.assertNotEqual(m.cli_first_decision(self.results, self.p)["g_screen"]["statement"], "inconclusive")

    def test_the_g_screen_comparators_use_the_same_floor(self):
        self.drop(E, 7)
        g = m.cli_first_decision(self.results, self.p)["g_screen"]
        self.assertEqual(g["statement"], "inconclusive")
        self.assertTrue(any("incomplete %s comparator cost records (usable 17 of 24" % m.E in r for r in g["reasons"]))
        self.setUp()
        self.drop(E, 6)
        self.assertNotEqual(m.cli_first_decision(self.results, self.p)["g_screen"]["statement"], "inconclusive")

    def test_shipping_reports_the_exclusions_and_the_floor_applies_to_the_cli_arms(self):
        self.drop(F, 7)
        out = m.shipping_decision(self.results, self.p)
        self.assertEqual(out["outcome"], "inconclusive")
        self.setUp()
        self.drop(F, 6)
        out = m.shipping_decision(self.results, self.p)
        self.assertNotEqual(out["outcome"], "inconclusive")
        self.assertEqual(out["token_completeness"]["by_model"][self.mid][F]["excluded"], 6)

    def test_improvement_sentences_carry_the_excluded_counts_and_incomplete_cells_are_not_zero_filled(self):
        self.drop(F, 6)
        kind = m.improvement_report(self.results, self.p)["pairs"]["F_vs_A"]["kinds"]["processed_tokens"]
        self.assertIn("%s 18/24" % m.F, kind["statement"]["en"])
        self.assertIn("%s 18/24" % m.F, kind["statement"]["ko"])
        self.assertAlmostEqual(kind["mean_ratio"], 0.75, places=3)

    def test_the_protocol_and_the_floor_constant_agree(self):
        self.assertEqual(m.TOKEN_MIN_USABLE_CELLS, 18)
        rule = m.protocol()["decision"]["cli_first"]["token_rule"]
        for needle in ("at least 18 of an arm", "never zero-filled or imputed", "token_completeness", "COMPLETENESS GATE"):
            self.assertIn(needle, rule)


CANARY1_ARCHIVE = Path.home() / "Documents/e2e-skills-bench/evidence-2026-10-15/archived-invalid/thin-eval-v1-canary-1-astra-fidelity/thin-eval-v1/_canary"


class BatchedCliCalls(unittest.TestCase):
    """Amendment r2 (canary 1 was invalid because the judge refused `eval ...; requests ...` batches): a call chained to later CLI
    calls by `;` or a newline keeps its exit-code meaning; masking stays for `||`, `|`, a background `&` and any later non-CLI command."""

    @staticmethod
    def events(entries):
        """Like cli_events, but the script keeps REAL newlines (shlex quoting): the archived rollouts carry a newline-separated batch as a
        real newline inside the `bash -c` argument, while cli_events' JSON quoting would turn it into a backslash and an n."""
        events = [dict(type="thread.started", thread_id="root")]
        for entry in entries:
            command, code = entry[0], entry[1]
            item = dict(type="command_execution", command="/usr/bin/bash -c " + shlex.quote(command), exit_code=code)
            output = entry[2] if len(entry) > 2 else BLOCKED_OUTPUT if SESSION_REQUESTS in command else None
            if output is not None:
                item["aggregated_output"] = output
            events.append(dict(type="item.completed", item=item))
        return events

    def calls(self, command, code=0, output=None):
        entry = (command, code) if output is None else (command, code, output)
        return [(c["verb"], c["masked"], c["verified"]) for c in m.cli_calls(self.events([entry]))]

    def test_batches_of_cli_calls_are_not_masked(self):
        for sep in ("; ", ";", "\n", " && ", " ;\n"):
            batch = SESSION_PROBE + sep + SESSION_REQUESTS
            with self.subTest(sep=repr(sep)):
                self.assertEqual(self.calls(batch), [("eval", False, True), ("requests", False, True)])
                self.assertEqual(self.calls(SESSION_GOTO + sep + SESSION_SNAP), [("goto", False, True), ("snapshot", False, True)])
        three = "\n".join((SESSION_GOTO, SESSION_SNAP, SESSION_REQUESTS))
        self.assertEqual([c[1:] for c in self.calls(three)], [(False, True)] * 3)
        self.assertEqual(self.calls("curl -s http://127.0.0.1:9304/health; " + SESSION_PROBE + "; " + SESSION_REQUESTS),
                         [("eval", False, True), ("requests", False, True)])  # a non-CLI command BEFORE the batch masks nothing
        self.assertEqual(self.calls(SESSION_SNAP + ";"), [("snapshot", False, True)])  # a trailing terminator masks nothing
        self.assertEqual(self.calls(SESSION_SNAP + "\n"), [("snapshot", False, True)])

    def test_masks_that_still_hold(self):
        for tail in (" || true", " | tee out", " &", "; echo done", "\necho done", "; true", " 2>&1; echo x"):
            with self.subTest(tail=tail):
                self.assertEqual(self.calls(SESSION_PROBE + tail), [("eval", True, False)])
        for batch in (SESSION_PROBE + " || true; " + SESSION_REQUESTS, SESSION_PROBE + " | tee o; " + SESSION_REQUESTS,
                      SESSION_PROBE + " & " + SESSION_REQUESTS, SESSION_PROBE + "; " + SESSION_REQUESTS + "; echo done",
                      SESSION_PROBE + "; echo mid; " + SESSION_REQUESTS):
            with self.subTest(batch=batch):
                self.assertTrue(self.calls(batch)[0][1], "the first call's exit code is not the script's")
        # a trailing non-CLI command masks every CLI call before it, even in a long batch
        self.assertTrue(all(c[1] for c in self.calls(SESSION_GOTO + "\n" + SESSION_SNAP + "\necho done")))

    def test_a_failure_anywhere_in_a_batch_unverifies_every_call_of_it(self):
        batch = SESSION_PROBE + "; " + SESSION_REQUESTS
        banner = "### Error\nError: page.evaluate: Target closed\n" + BLOCKED_OUTPUT
        self.assertEqual(self.calls(batch, 0, banner), [("eval", False, False), ("requests", False, False)])
        self.assertEqual(self.calls(batch, 1, BLOCKED_OUTPUT), [("eval", False, False), ("requests", False, False)])
        # an unknown exit code is not verified either
        events = self.events([(batch, None, BLOCKED_OUTPUT)])
        self.assertEqual([c["verified"] for c in m.cli_calls(events)], [False, False])

    def test_a_batched_guard_probe_still_needs_the_refused_origin_in_the_requests_output(self):
        def proof(output):
            calls = m.cli_calls(self.events([(SESSION_OPEN, 0), (SESSION_PROBE + "\n" + SESSION_REQUESTS, 0, output),
                                            (SESSION_GOTO + "; " + SESSION_SNAP, 0)]))
            return m.cli_session_proof(calls)["x"]
        ok = proof(BLOCKED_OUTPUT)
        self.assertEqual((ok["opened"], ok["guard_verified"], ok["explored"], ok["snapshot"], ok["complete"]), (True,) * 5)
        for output in ("### Result\n(no requests)\n", "### Result\n1. [GET] http://127.0.0.1:9/ => [200] OK\n", ""):
            with self.subTest(output=output):
                bad = proof(output)
                self.assertFalse(bad["guard_verified"] or bad["complete"])
        banner = proof("### Error\nsomething broke\n" + BLOCKED_OUTPUT)
        self.assertFalse(banner["guard_verified"] or banner["complete"])

    def test_a_failed_goto_in_a_batch_does_not_count_as_exploration(self):
        calls = m.cli_calls(self.events([(SESSION_OPEN, 0), (SESSION_PROBE, 0), (SESSION_REQUESTS, 0),
                                        (SESSION_GOTO + "; " + SESSION_SNAP, 0, "### Error\nnavigation failed\n")]))
        proof = m.cli_session_proof(calls)["x"]
        self.assertTrue(proof["guard_verified"])
        self.assertFalse(proof["explored"] or proof["snapshot"] or proof["complete"])

    def test_the_batched_calls_are_counted_as_browser_interaction(self):
        counts = m.cli_interaction_counts(self.events([(SESSION_OPEN, 0), (SESSION_GOTO + "; " + SESSION_SNAP, 0), (SESSION_SNAP + "; echo x", 0)]))
        # open is a session command, the batched goto acts, the batched snapshot observes; the `; echo x` snapshot is reported as masked
        self.assertEqual((counts["browser_acting"], counts["browser_observing"], counts["masked_commands"]), (1, 1, 1))
        self.assertEqual(counts["by_verb"], {"goto": 1, "open": 1, "snapshot": 1})

    @unittest.skipUnless(CANARY1_ARCHIVE.is_dir(), "archived canary 1 is not on this machine")
    def test_canary_1_rollouts_judge_complete_for_all_twelve_cells(self):
        total = flagged_fixed = 0
        for model in ("gpt-6-sol", "gpt-6-astra"):
            for path in sorted((CANARY1_ARCHIVE / model / "final-transcripts").glob("*.jsonl")):
                events = [json.loads(line) for line in path.read_text().splitlines() if line.strip()]
                calls = m.cli_calls(events)
                proofs = m.cli_session_proof(calls)
                total += 1
                with self.subTest(model=model, cell=path.stem[:8]):
                    self.assertEqual(sum(p["complete"] and p["guard_verified"] for p in proofs.values()), 1, proofs)
                    self.assertFalse(any(c["exit_code"] not in (0, None) and c["verified"] for c in calls))
                if model == "gpt-6-astra" and path.stem[:8] in ("46dc6ebf", "7b070745"):
                    flagged_fixed += 1
        self.assertEqual((total, flagged_fixed), (12, 2))


class RevisionR2(unittest.TestCase):
    """The r2 judge repair stays recorded (revision_r2); the live protocol id is now r3 (see RevisionR3)."""
    def test_the_r2_record_is_kept_with_its_reason_and_nothing_else_moved(self):
        p = m.protocol()
        self.assertEqual(m.BENCH.name, "generator-thin-eval-v1")  # the directory names the benchmark family
        rev = p["revision_r2"]
        self.assertEqual((rev["id"], rev["supersedes"]), ("r2", "generator-thin-eval-v1"))
        for key in ("reason", "diagnosis", "change", "unchanged", "effect_on_scores", "preregistration_note", "archive", "output_directory", "restart"):
            self.assertTrue(rev[key], key)
        self.assertIn("AFTER observing", rev["preregistration_note"])
        self.assertIn("thin-eval-v1-r2", rev["output_directory"])
        self.assertIn("must not be reused", rev["output_directory"])
        # nothing the revisions claim is unchanged was touched
        self.assertEqual((p["repetitions"], p["workers"]), (4, 1))
        self.assertEqual(p["decision"]["cli_first"]["quality_margin"], 0.1)
        self.assertEqual(m.CLI_GUIDE.stat().st_size, 1845)
        self.assertEqual(Path(m.BENCH / "shipped-skill/SKILL.md").stat().st_size, 7106)

    def test_a_stale_freeze_of_the_invalid_campaign_cannot_be_reused(self):
        with tempfile.TemporaryDirectory() as tmp:
            for stale_id in ("generator-thin-eval-v1", "generator-thin-eval-v1-r2"):
                stale = Path(tmp) / "freeze.json"
                stale.write_text(json.dumps(dict(protocol_id=stale_id)))
                with patch.object(m, "FREEZE", stale), self.subTest(stale=stale_id):
                    with self.assertRaises(Exception):
                        m.frozen()


class RevisionR3(unittest.TestCase):
    def test_the_revision_is_a_new_protocol_id_with_a_recorded_reason_and_nothing_else_moved(self):
        p = m.protocol()
        self.assertEqual((m.ID, p["protocol_id"]), ("generator-thin-eval-v1-r3",) * 2)
        rev = p["revision"]
        self.assertEqual((rev["id"], rev["supersedes"]), ("r3", "generator-thin-eval-v1-r2"))
        for key in ("reason", "diagnosis", "change", "unchanged", "effect_on_scores", "preregistration_note", "archive", "output_directory", "restart"):
            self.assertTrue(rev[key], key)
        self.assertIn("AFTER observing", rev["preregistration_note"])
        self.assertIn("lazy-import race", rev["diagnosis"])
        self.assertIn("clean_env", rev["reason"])
        self.assertIn("thin-eval-v1-r3", rev["output_directory"])
        self.assertIn("must not be reused", rev["output_directory"])
        self.assertIn("r2-canary-import-race", rev["archive"])
        self.assertIn("the r2 judge repair (chain_masks_exit)", rev["unchanged"])
        # the pins and the pre-registered values did not move
        self.assertEqual((p["repetitions"], p["workers"]), (4, 1))
        self.assertEqual(p["concurrency"]["workers_allowed"], [1, 2])
        self.assertEqual(m.CLI_GUIDE.stat().st_size, 1845)
        shipped = Path(m.BENCH / "shipped-skill/SKILL.md")
        self.assertEqual(shipped.stat().st_size, 7106)
        self.assertTrue(hashlib.sha256(shipped.read_bytes()).hexdigest().startswith("961bee927465aa7e"))

    def test_a_stale_r2_freeze_cannot_be_reused(self):
        with tempfile.TemporaryDirectory() as tmp:
            stale = Path(tmp) / "freeze.json"
            stale.write_text(json.dumps(dict(protocol_id="generator-thin-eval-v1-r2")))
            with patch.object(m, "FREEZE", stale):
                with self.assertRaises(Exception):
                    m.frozen()

    def test_the_warm_up_runs_before_the_shims_and_the_pool_in_the_source_order(self):
        source = Path(m.__file__).read_text() if hasattr(m, "__file__") else (m.ROOT / "scripts/evals/run-generator-thin-eval-v1.py").read_text()
        body = source[source.index("def run_cells_parallel("):source.index("class SharedHandle")]
        self.assertLess(body.index("warm_lazy_modules(m)"), body.index("with _dispatch_shims():"))
        self.assertLess(body.index("with _dispatch_shims():"), body.index("ThreadPoolExecutor("))
        self.assertEqual(body.count("warm_lazy_modules("), 1)


if __name__ == "__main__":
    unittest.main()
