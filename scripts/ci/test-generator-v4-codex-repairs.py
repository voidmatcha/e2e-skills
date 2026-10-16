#!/usr/bin/env python3
"""Offline v4 regressions and inherited v3 contracts. No models, servers or containers. Apache-2.0."""
import importlib.util
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[2]


def load(name, rel):
    spec = importlib.util.spec_from_file_location(name, ROOT / rel)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


m = load("codex_v4_repair", "scripts/evals/run-generator-multimodel-v4-codex.py")
f = load("codex_v4_fixtures", "scripts/ci/test-generator-v3-codex-harness-fixes.py")
# Reuse the predecessor's offline behavior contracts against the successor.
f.m, f.ev = m, m.evidence
smoke = load("codex_v4_smoke", "scripts/ci/test-generator-v3-codex-smoke.py")
smoke.m, smoke.ev, smoke.f = m, m.evidence, f
base = load("codex_v4_protocol", "scripts/ci/test-generator-multimodel-v3-codex.py")
base.m = m


def linked_tree_contract(self):
    """Successor replacement: unrelated child usage is excluded, while grandchildren remain linked."""
    with tempfile.TemporaryDirectory() as tmp:
        f.rollout(tmp, 0, tokens=(1000, 800, 100))
        f.rollout(tmp, 1, parent=f.UUIDS[0], tokens=(5000, 4000, 300),
                  calls=[("playwright-test", "generator_setup_page", "completed"),
                         ("playwright-test", "generator_write_test", "completed")])
        f.rollout(tmp, 2, parent=f.UUIDS[1], tokens=(200, 0, 20),
                  calls=[("playwright-test", "test_list", "completed")])
        f.rollout(tmp, 3, parent=f.UUIDS[7], tokens=(7, 0, 1))
        sess = m.evidence.summarize_sessions(m.evidence.load_sessions(tmp), f.UUIDS[0])
    self.assertEqual((sess["rollouts_found"], sess["root_found"], sess["children_linked"],
                      sess["children_unlinked"], sess["children_total"]), (4, True, 2, 1, 2))
    self.assertEqual((sess["playwright_test_completed"], sess["child_playwright_test_completed"],
                      sess["generator_tool_completed"], sess["generator_write_test_completed"]), (3, 3, 2, 1))
    self.assertEqual(sess["child_usage"]["input_tokens"], 5200)
    self.assertEqual(sess["root_rollout_usage"]["input_tokens"], 1000)
    self.assertEqual(sess["mcp_calls"]["playwright-test.generator_setup_page"], {"completed": 1, "other": 0})


def explicit_root_contract(self):
    """Successor replacement: narration cannot override an explicit contradictory root."""
    out = self.classify(f.stream(mcp=2), [lambda d: f.rollout(d, 0, tokens=(1, 0, 1))])
    self.assertEqual((out["class"], out["evidence"]["primary_signal"]), ("official-tool", "parent-stream"))
    out = self.classify(f.stream(7, messages=["Browser setup succeeded."]),
                        [lambda d: f.rollout(d, 0), lambda d: f.rollout(d, 5)])
    self.assertEqual((out["class"], out["evidence"]["primary_signal_complete"]), ("unverified", False))
    self.assertFalse(m.admits(out))
    self.assertEqual(out["evidence"]["primary_signal"], "identity-conflict")


# These two predecessor expectations encode the repaired defects. Replace them
# explicitly in this isolated imported module; the frozen source stays unchanged.
f.Rollouts.test_tree_root_child_grandchild_unlinked_and_usage = linked_tree_contract
f.FidelityFromRollouts.test_parent_stream_call_is_observed_and_rollout_without_root_is_not_complete = explicit_root_contract


class Repairs(unittest.TestCase):
    def observe(self, events, builds, **overrides):
        with tempfile.TemporaryDirectory() as tmp:
            tdir, _ = f.make_cell_files(tmp, events, builds)
            rec = f.arm_rec(usage=f.usage(300, 200, 20), **overrides)
            fid = m.classify_fidelity(rec, tdir)
            sess = fid["evidence"]["rollouts"]
            return fid, m.evaluate_harness_check(rec, tdir), m.evidence.codex_tokens(rec, sess)

    def assert_rejected(self, observed):
        fid, harness, tokens = observed
        self.assertFalse(m.admits(fid))
        self.assertFalse(fid["evidence"]["primary_signal_complete"])
        self.assertTrue(fid["evidence"]["observation_incomplete"])
        self.assertNotEqual(harness["status"], "pass")
        self.assertFalse(tokens["complete"])

    def test_explicit_root_mismatch_rejects_successful_child_evidence(self):
        self.assert_rejected(self.observe(f.stream(2) + [f.spawn_item(f.UUIDS[1])], f.HarnessCheck.good))

    def test_identity_mismatch_blocks_parent_artifact_and_message_fallbacks(self):
        for extra in ({}, {"out_of_scope_writes": [".playwright-mcp/snapshot.md"]}):
            with self.subTest(extra=extra):
                self.assert_rejected(self.observe(f.stream(2, mcp=1, messages=["Browser setup succeeded."]),
                                                  f.HarnessCheck.good, **extra))

    def test_multiple_transcript_roots_are_rejected(self):
        self.assert_rejected(self.observe(f.stream() + f.stream(2), f.HarnessCheck.good))

    def test_conflicting_stream_roots_reject_fallback_even_without_sessions(self):
        self.assert_rejected(self.observe(f.stream(mcp=1) + f.stream(2), [],
                                          out_of_scope_writes=[".playwright-mcp/snapshot.md"]))

    def test_explicit_root_cannot_be_a_child(self):
        self.assert_rejected(self.observe(f.stream(1), f.HarnessCheck.good))

    def test_matching_identity_still_passes_fidelity_harness_and_cost(self):
        fid, harness, tokens = self.observe(f.stream() + [f.spawn_item(f.UUIDS[1])], f.HarnessCheck.good)
        self.assertTrue(m.admits(fid))
        self.assertTrue(fid["evidence"]["primary_signal_complete"])
        self.assertEqual(harness["status"], "pass")
        self.assertTrue(tokens["complete"])

    def test_only_absent_root_id_permits_unique_parentless_fallback(self):
        events = [e for e in f.stream() if e["type"] != "thread.started"]
        fid, _, tokens = self.observe(events, f.HarnessCheck.good)
        self.assertTrue(m.admits(fid))
        self.assertTrue(fid["evidence"]["primary_signal_complete"])
        self.assertTrue(tokens["complete"])
        two_roots = [lambda d: f.rollout(d, 0), lambda d: f.rollout(d, 2)]
        self.assert_rejected(self.observe(events, two_roots))

    def test_unrelated_roots_and_children_cannot_admit_or_supply_tokens(self):
        for parent in (None, f.UUIDS[2]):
            builds = [lambda d: f.rollout(d, 0, tokens=(300, 200, 20)),
                      lambda d: f.rollout(d, 1, parent=parent, calls=[("playwright-test", "generator_write_test", "completed")],
                                          tokens=(900, 0, 90))]
            fid, _, tokens = self.observe(f.stream(), builds)
            self.assertFalse(m.admits(fid))
            self.assertEqual(fid["evidence"]["generator_surface_calls"], 0)
            self.assertEqual(tokens["child_output"], 0)
            self.assertFalse(tokens["complete"])

    def test_missing_explicit_root_leaves_entry_undecided(self):
        with tempfile.TemporaryDirectory() as tmp, patch.object(m, "BASE", Path(tmp)):
            def call(n, tdir):
                f.jl(tdir / "t.jsonl", f.stream(2, mcp=1))
                for build in f.HarnessCheck.good:
                    build(tdir.parent / "codex-sessions/t")
                return f.arm_rec(transcript_path=str(tdir / "t.jsonl"))
            decision, state = m.run_entry("gpt-6-sol", {"max_attempts": 2, "max_aborted_reruns": 1}, Path(tmp) / "entry", call)
            self.assertIsNone(decision)
            self.assertEqual(len(state["attempts"]), 0)
            self.assertEqual(state["aborted_calls"], 2)

    def test_hostile_git_environment_cannot_redirect_smoke_initialization(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp).resolve()
            project = root / "work/project"
            project.mkdir(parents=True)
            outside = root / "outside"
            config = root / "hostile.conf"
            config.write_text('[init]\n templateDir = ' + str(root / "template") + '\n')
            template = root / "template"
            template.mkdir()
            (template / "unwanted").write_text("ambient template")
            hostile = {"GIT_DIR": str(outside), "GIT_WORK_TREE": str(outside),
                       "GIT_COMMON_DIR": str(outside), "GIT_INDEX_FILE": str(outside / "index"),
                       "GIT_OBJECT_DIRECTORY": str(outside / "objects"), "GIT_CONFIG": str(config),
                       "GIT_CONFIG_GLOBAL": str(config), "GIT_CONFIG_SYSTEM": str(config),
                       "GIT_TEMPLATE_DIR": str(template), "GIT_CONFIG_COUNT": "1",
                       "GIT_CONFIG_KEY_0": "init.templateDir", "GIT_CONFIG_VALUE_0": str(template)}
            with patch.dict(os.environ, hostile):
                m.init_smoke_git(project, root / "work")
            self.assertTrue((project / ".git/HEAD").is_file())
            self.assertFalse(outside.exists())
            self.assertFalse((project / ".git/unwanted").exists())

    def test_actual_smoke_call_uses_safe_initialization(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp).resolve()
            with patch.object(tempfile, "tempdir", str(root)), patch.dict(os.environ, {"GIT_DIR": str(root / "escape")}), \
                    patch.object(m, "smoke_init_agents", return_value={"status": "ready"}), \
                    patch.object(m.engine, "call_model", return_value={"spec_files": []}) as call:
                m.smoke_call("gpt-6-sol", m.ARM_A, 1, root, None, m.protocol())
                self.assertEqual(call.call_count, 1)
            self.assertFalse((root / "escape").exists())

    def test_git_escape_existing_git_and_symlinks_refuse_before_subprocess(self):
        with tempfile.TemporaryDirectory() as tmp, patch("subprocess.run", side_effect=AssertionError("Git ran")):
            root = Path(tmp).resolve()
            work, outside = root / "work", root / "outside"
            work.mkdir()
            outside.mkdir()
            with self.assertRaises(ValueError):
                m.init_smoke_git(outside, work)
            project = work / "project"
            project.mkdir()
            (project / ".git").write_text("gitdir: ../../outside\n")
            with self.assertRaises(ValueError):
                m.init_smoke_git(project, work)
            (project / ".git").unlink()
            (project / ".git").symlink_to(root / "missing")
            with self.assertRaises(ValueError):
                m.init_smoke_git(project, work)
            alias = work / "alias"
            alias.symlink_to(outside, target_is_directory=True)
            with self.assertRaises(ValueError):
                m.init_smoke_git(alias, work)

    def test_successor_and_oss_select_new_identity_and_leave_freeze_absent(self):
        oss = load("codex_v4_oss", "scripts/evals/run-generator-oss-eval-v1.py")
        self.assertEqual(oss.v2.PROTOCOL_ID, m.PROTOCOL_ID)
        self.assertEqual(oss.evidence.__file__, m.evidence.__file__)
        self.assertEqual(m.protocol()["supersedes"], "generator-multimodel-v3-codex")
        self.assertEqual(m.protocol()["prior_admissions"], "INVALID_REQUIRES_FRESH_PREFLIGHT")
        self.assertFalse(m.LOCK.exists())
        self.assertIn("v4 Codex successor", oss.protocol()["codex_configuration_gate"])


def load_tests(loader, tests, pattern):
    return unittest.TestSuite([tests, loader.loadTestsFromModule(base), loader.loadTestsFromModule(f),
                               loader.loadTestsFromModule(smoke)])


if __name__ == "__main__":
    unittest.main()
