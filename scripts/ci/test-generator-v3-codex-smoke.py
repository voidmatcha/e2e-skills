#!/usr/bin/env python3
"""Offline smoke refusals and synthetic rollout/token diagnostics. No model, container or freeze. Apache-2.0."""
import argparse
import contextlib
import importlib.util
import io
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[2]
spec = importlib.util.spec_from_file_location("codex_smoke_tests", ROOT / "scripts/ci/test-generator-v3-codex-harness-fixes.py")
f = importlib.util.module_from_spec(spec)
spec.loader.exec_module(f)
m, ev = f.m, f.ev


@contextlib.contextmanager
def canonical_tempdir():
    """Resolve system temp aliases so ordinary fixtures do not test symlink refusal."""
    with tempfile.TemporaryDirectory() as tmp:
        yield str(Path(tmp).resolve())


class Smoke(unittest.TestCase):
    def args(self, output, models=None, live=True):
        return argparse.Namespace(output=output, model=models, allow_live=live)

    def test_flag_path_and_roster_refusals_precede_all_live_work(self):
        with canonical_tempdir() as tmp, patch.object(m, "configure_smoke", side_effect=AssertionError("configured")), \
                patch.object(m, "other_campaign_running", side_effect=AssertionError("process query")), \
                patch("subprocess.Popen", side_effect=AssertionError("model call")):
            with self.assertRaisesRegex(ValueError, "--allow-live"):
                m.smoke_cmd(self.args(Path(tmp) / "not-created", live=False))
            forbidden = [ROOT, ROOT / "results/smoke", Path.home() / ".cache/e2e-skills-bench/smoke"]
            for output in forbidden:
                with self.assertRaisesRegex(ValueError, "outside"):
                    m.smoke_cmd(self.args(output))
            for models in (["gpt-5.5"], ["gpt-5.6-luna"], ["gpt-6-sol", "gpt-6-sol"]):
                with self.assertRaises(ValueError):
                    m.smoke_cmd(self.args(Path(tmp) / "not-created", models))
            self.assertFalse((Path(tmp) / "not-created").exists())

    def test_alias_existing_data_and_main_checkout_are_refused(self):
        with canonical_tempdir() as tmp:
            tmp = Path(tmp)
            alias = tmp / "alias"
            alias.symlink_to(ROOT, target_is_directory=True)
            with self.assertRaisesRegex(ValueError, "symlink"):
                m.smoke_output_guard(alias / "smoke")
            with self.assertRaisesRegex(ValueError, "empty"):
                m.smoke_output_guard(tmp)
            file = tmp / "file"
            file.write_text("keep")
            with self.assertRaises(ValueError):
                m.smoke_output_guard(file)
            self.assertEqual(file.read_text(), "keep")
            gitfile = ROOT / ".git"
            if gitfile.is_file():
                gitdir = (ROOT / gitfile.read_text().strip()[8:]).resolve()
                main = next(p.parent for p in gitdir.parents if p.name == ".git")
                with self.assertRaisesRegex(ValueError, "outside"):
                    m.smoke_output_guard(main / "smoke")

    def test_overridden_campaign_roots_are_refused_before_live_work(self):
        with canonical_tempdir() as tmp, \
                patch.object(m, "configure_smoke", side_effect=AssertionError("configured")), \
                patch.object(m, "other_campaign_running", side_effect=AssertionError("process query")), \
                patch.object(m, "smoke_call", side_effect=AssertionError("model call")):
            for owner in (m, m.v1):
                with self.subTest(owner=owner.__name__):
                    root = Path(tmp) / owner.__name__
                    root.mkdir()
                    output = root / "fresh-smoke"
                    with patch.object(owner, "BASE", root):
                        with self.assertRaisesRegex(ValueError, "outside"):
                            m.smoke_cmd(self.args(output))
                    self.assertFalse(output.exists())

    def test_sibling_worktree_output_is_refused(self):
        """A .git file ancestor rejects output before any directory or live work."""
        with canonical_tempdir() as tmp:
            tmp = Path(tmp)
            current, sibling = tmp / "current", tmp / "sibling"
            current.mkdir()
            sibling.mkdir()
            (sibling / ".git").write_text("gitdir: ../repository/.git/worktrees/sibling\n")
            output = sibling / "fresh-smoke"
            with patch.object(m, "ROOT", current), \
                    patch.object(m, "BASE", tmp / "campaign-v2"), \
                    patch.object(m.v1, "BASE", tmp / "campaign-v1"):
                with self.assertRaisesRegex(ValueError, "outside"):
                    m.smoke_output_guard(output)
                (sibling / ".git").unlink()
                (sibling / ".git").mkdir()
                with self.assertRaisesRegex(ValueError, "outside"):
                    m.smoke_output_guard(output)
            self.assertFalse(output.exists(), "read-only guard must not create output")
            self.assertEqual(list(sibling.iterdir()), [sibling / ".git"])

    def test_synthetic_child_evidence_and_tokens(self):
        with canonical_tempdir() as tmp:
            spawn = {"type": "item.completed", "item": {"type": "collab_tool_call", "tool": "spawn_agent", "status": "completed", "receiver_thread_ids": [f.UUIDS[1]]}}
            tdir, sdir = f.make_cell_files(tmp, f.stream() + [spawn], [
                lambda d: f.rollout(d, 0, tokens=(1000, 800, 100)),
                lambda d: f.rollout(d, 1, parent=f.UUIDS[0], calls=[("playwright-test", "generator_write_test", "completed")], tokens=(500, 200, 50)),
            ])
            rec = f.arm_rec(compliance={"sessions": {"files": 2, "skipped": []}}, usage=f.usage(1000, 800, 100))
            out = m.smoke_observation(rec, tdir)
            self.assertEqual(out["availability"], "available")
            self.assertTrue(out["non_data"] and out["sessions_persisted"] and out["mcp_reachable"])
            self.assertEqual(out["fidelity"]["evidence"]["primary_signal"], "rollout")
            self.assertEqual(out["tokens"]["processed"], 650)
            self.assertEqual(out["tokens"]["child_output"], 50)
            self.assertTrue(out["tokens"]["complete"])
            # A copied or unparseable child record never yields a complete cost denominator.
            for mutate in ("missing", "malformed", "dirty"):
                if mutate == "missing":
                    for p in sdir.rglob("*" + f.UUIDS[1] + ".jsonl"):
                        p.unlink()
                elif mutate == "malformed":
                    f.rollout(sdir, 1, parent=f.UUIDS[0], tokens=(500, 200, 50)).write_text("bad json\n")
                else:
                    rec["compliance"]["sessions"]["skipped"] = ["lost.jsonl"]
                out = m.smoke_observation(rec, tdir)
                self.assertFalse(out["tokens"]["complete"], mutate)
                self.assertTrue(out["observation_gaps"], mutate)

    def test_availability_failure_and_unknown_are_not_quality_data(self):
        with canonical_tempdir() as tmp:
            rec = f.arm_rec(infrastructure_error=True, error="HTTP 400 not supported when using Codex with a ChatGPT account")
            out = m.smoke_observation(rec, tmp)
            self.assertEqual(out["availability"], "unavailable")
            self.assertFalse(out["tokens"]["complete"])
            out = m.smoke_observation(dict(rec, error="usage limit"), tmp)
            self.assertEqual(out["availability"], "unknown")
            self.assertFalse(out["mcp_reachable"])

    def test_bounded_stub_calls_without_freeze_and_non_data_analysis_refusal(self):
        with canonical_tempdir() as tmp, contextlib.redirect_stdout(io.StringIO()):
            output, calls = Path(tmp) / "smoke", []
            def call(model, arm, n, root, args, p):
                calls.append((model, arm, n))
                return f.arm_rec(arm=arm, infrastructure_error=True, error="stub failure", stage="smoke", non_data=True)
            with patch.object(m, "configure_smoke", lambda *a: None), patch.object(m, "smoke_call", call), \
                    patch.object(m, "other_campaign_running", return_value=[]), patch.object(m, "frozen", side_effect=AssertionError("freeze used")), \
                    patch.object(m, "campaign_lock", side_effect=AssertionError("cache lock used")), \
                    patch("subprocess.run", side_effect=AssertionError("live subprocess")):
                self.assertEqual(m.smoke_cmd(self.args(output, ["gpt-6-sol", "gpt-5.6-terra"])), 0)
            self.assertEqual(len(calls), 6)
            for model in ("gpt-6-sol", "gpt-5.6-terra"):
                self.assertEqual([a for mod, a, _ in calls if mod == model], [m.ARM_A, m.ARM_A, m.ARM_C])
            report = json.loads((output / m.SMOKE_MARKER).read_text())
            self.assertTrue(all(r["non_data"] for r in report["runs"]))
            with self.assertRaisesRegex(ValueError, "non-data"):
                m.check_report(report, {}, {}, False)
            with self.assertRaisesRegex(ValueError, "smoke"):
                m.pooled_analysis({"gpt-6-sol": report}, m.protocol())
            with patch.object(m.v1, "model_dir", return_value=output / "gpt-6-sol"):
                for operation in (m.analyze_model, m.score_model):
                    with self.assertRaisesRegex(ValueError, "non-data"):
                        operation("gpt-6-sol")
            self.assertFalse(list(output.rglob("freeze.json")))

    def test_actual_smoke_call_has_no_infrastructure_retry_and_scratch_stays_under_output(self):
        with canonical_tempdir() as tmp:
            tmp = Path(tmp)
            original_temp = tempfile.tempdir
            tempfile.tempdir = str(tmp)
            try:
                root = tmp / "call"
                root.mkdir()
                with patch.object(m, "smoke_init_agents", return_value={"status": "ready"}), \
                        patch.object(m.engine, "call_model", return_value={"infrastructure_error": True, "error": "stub failure"}) as call:
                    def inspect_project(project, *args):
                        self.assertTrue((project / ".git").is_dir())
                        return {"infrastructure_error": True, "error": "stub failure"}
                    call.side_effect = inspect_project
                    rec = m.smoke_call("gpt-6-sol", m.ARM_A, 1, root, self.args(tmp), m.protocol())
                    self.assertEqual(call.call_count, 1)
                    self.assertEqual(rec["stage"], "smoke")
                    self.assertTrue(rec["non_data"])
                    self.assertIn(tmp, call.call_args.args[1].parents)
                    self.assertFalse(list(tmp.glob("smoke-*")))
            finally:
                tempfile.tempdir = original_temp

    def test_initializer_argv_uses_existing_cli_and_confines_host_environment(self):
        with canonical_tempdir() as tmp, patch.object(tempfile, "tempdir", tmp), \
                patch.object(m.shutil, "which", return_value="/usr/bin/node"), \
                patch.object(m.orig, "protocol", return_value={"official_arm": {"init_agents_agent_file_sha256": {}}}), \
                patch("subprocess.run", return_value=argparse.Namespace(returncode=0)) as run:
            project = Path(tmp) / "project"
            agents = project / ".codex/agents"
            agents.mkdir(parents=True)
            (agents / "playwright_test_generator.toml").write_text("synthetic role")
            setup = m.smoke_init_agents(project)
            self.assertEqual(setup["status"], "ready")
            self.assertEqual(run.call_args.args[0][0], "/usr/bin/node")
            self.assertIn("init-agents", run.call_args.args[0])
            self.assertNotIn("npx", run.call_args.args[0])
            env = run.call_args.kwargs["env"]
            for key in ("HOME", "TMPDIR", "NPM_CONFIG_CACHE"):
                self.assertTrue(Path(env[key]).is_relative_to(Path(tmp)))

    def test_legacy_admission_and_harness_pass_require_fresh_evidence(self):
        with canonical_tempdir() as tmp:
            p = dict(m.protocol(), models=[m.protocol()["models"][0]])
            entry = Path(tmp) / "entry.json"
            with patch.object(m, "entry_path", return_value=entry), patch.object(m, "digest", return_value="new-freeze"):
                entry.write_text(json.dumps({"decision": "admitted", "freeze_sha256": "old-freeze"}))
                with self.assertRaisesRegex(ValueError, "not bound"):
                    m.load_entries(p)
                entry.write_text(json.dumps({"decision": "admitted", "freeze_sha256": "new-freeze", "harness_criteria": {"child_called_test_list": True}}))
                with self.assertRaisesRegex(ValueError, "working-child"):
                    m.load_entries(p)
            check = Path(tmp) / "harness-check.json"
            check.write_text(json.dumps({"status": "pass", "freeze_sha256": "new-freeze", "criteria": {"child_called_test_list": True}}))
            with patch.object(m, "harness_check_path", return_value=check), patch.object(m, "digest", return_value="new-freeze"):
                with self.assertRaisesRegex(ValueError, "not a pass"):
                    m.load_harness_check()
            self.assertEqual(m.protocol()["prior_admissions"], "INVALID_REQUIRES_FRESH_PREFLIGHT")

    def test_adapter_refuses_gitless_project_before_any_model_operation(self):
        with canonical_tempdir() as tmp, patch("subprocess.run", side_effect=AssertionError("subprocess")), \
                patch("subprocess.Popen", side_effect=AssertionError("model call")):
            work = Path(tmp) / "work"
            project = work / "project"
            project.mkdir(parents=True)
            with patch.dict(m.compat.ARM_LINES, m.arm_lines()):
                call = m.compat.configure(m.engine)
                with self.assertRaisesRegex(ValueError, "Git repository"):
                    call(project, work, m.ARM_A, "stub", "gpt-6-sol", 1, None)

    def test_never_launched_reviewer_retains_source_cost_in_pipeline(self):
        with canonical_tempdir() as tmp:
            args = argparse.Namespace(model="gpt-6-sol", timeout=1, call_budget=None)
            with patch.object(m.engine, "call_model", side_effect=AssertionError("model call")):
                rec = m.one_call({"case": "v2-06", "arm": m.ARM_B, "repetition": 1, "ordinal": 1},
                                 args, m.engine.Ports(9100), Path(tmp) / "artifacts", {"runner": "codex"}, m.protocol())
            self.assertIs(rec["model_call_launched"], False)
            token = m.tokens_for_record(rec, tmp)
            self.assertTrue(token["complete"])
            self.assertEqual(token["processed"], 0)
            source = dict(ev.skipped_reviewer_tokens(), processed=100, total=100, uncached_input=100)
            a = {"arm": m.ARM_A, "case": "v2-06", "repetition": 1, "tokens": source, "elapsed_s": 10}
            b = dict(arm=m.ARM_B, case="v2-06", repetition=1, tokens=token, elapsed_s=0, refactor_score=0)
            m.add_pipeline([a, b])
            endpoint = m.pooled.cost_endpoint([b])
            self.assertEqual(endpoint["tokens"]["processed"], 100)
            self.assertEqual(endpoint["cells_with_complete_tokens"], 1)
            self.assertEqual(endpoint["elapsed_s_mean"], 10)
            for change in ({"model_call_launched": True}, {"call_skip_reason": None}, {"attempts": [{"error": "timeout"}]},
                           {"transcript_path": "missing.jsonl"}, {"usage": {"input_tokens": 1}}, {"infrastructure_error": True}):
                ambiguous = dict(rec, **change)
                self.assertFalse(m.tokens_for_record(ambiguous, tmp)["complete"], change)

    def test_retry_tokens_and_pipeline_include_each_attempt_once(self):
        with canonical_tempdir() as tmp:
            tdir = Path(tmp) / "transcripts"
            for n in (1, 2):
                f.make_cell_files(tmp, f.stream(), [
                    lambda d: f.rollout(d, 0, tokens=(100, 20, 10)),
                    lambda d: f.rollout(d, 1, parent=f.UUIDS[0], tokens=(50, 10, 5)),
                ], name=f"t{n}")
            tdir = Path(tmp) / "final-transcripts"
            attempts = [f.arm_rec(transcript_path=f"t{n}.jsonl", elapsed_ms=1000) for n in (1, 2)]
            rec = f.arm_rec(transcript_path="t2.jsonl", attempts=attempts, elapsed_ms=1000)
            out = m.cell_extras(rec, tdir, tmp)
            self.assertEqual(out["tokens"]["processed"], 270)
            self.assertEqual(out["tokens"]["child_output"], 10)
            self.assertTrue(out["tokens"]["complete"])
            self.assertEqual(out["elapsed_s"], 2)
            b = {"arm": m.ARM_B, "case": "missing", "repetition": 1, "tokens": out["tokens"], "elapsed_s": 2}
            m.add_pipeline([b])
            self.assertFalse(b["pipeline"]["tokens"]["complete"])

    def test_fatal_stub_stops_without_retry(self):
        with canonical_tempdir() as tmp, patch.object(m, "configure_smoke", lambda *a: None), \
                patch.object(m, "other_campaign_running", return_value=[]), \
                patch.object(m, "smoke_call", return_value=f.arm_rec(infrastructure_error=True, fatal_infrastructure=True)) as call:
            self.assertEqual(m.smoke_cmd(self.args(Path(tmp) / "smoke")), 5)
            self.assertEqual(call.call_count, 1)


if __name__ == "__main__":
    unittest.main()
