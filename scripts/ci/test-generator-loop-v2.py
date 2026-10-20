#!/usr/bin/env python3
"""Offline regression tests for the dev-only generator restart. Apache-2.0.

No model, browser, container, network, stored campaign outcome, or held-out task
is needed. All scored observations below are synthetic test data.
"""

import copy
import contextlib
import importlib.util
import itertools
import json
import re
import sys
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

sys.dont_write_bytecode = True
ROOT = Path(__file__).resolve().parents[2]
RUNNER = ROOT / "scripts/evals/run-generator-loop-v2.py"
SPEC = importlib.util.spec_from_file_location("generator_loop_v2_under_test", RUNNER)
m = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(m)


def batch(prefix="baseline", quality=0, tokens=100, seconds=100, kill=1):
    """Exactly two independent repetitions of each permitted development task."""
    return [
        {"case": task, "repetition": rep, "call_id": f"{prefix}-{task}-{rep}",
         "clean": True, "refactor_score": quality, "kill_rate": kill,
         "scan_p0": 0, "scan_p1p2": 0, "tokens": tokens, "generation_s": seconds}
        for task in m.DEV for rep in (1, 2)
    ]


def decide(candidate, incumbent=None, history=None):
    incumbent = incumbent if incumbent is not None else batch()
    history = history if history is not None else [batch("aa1"), batch("aa2")]
    return m.decide(candidate, incumbent, history)


class DevelopmentBoundaryTests(unittest.TestCase):
    def test_task_and_model_scope_is_exact(self):
        self.assertEqual(m.DEV_SYNTH, ("v2-11", "v3-08", "v2-18"))
        self.assertEqual(m.DEV_OSS, ("zep-sidebar", "zep-note-rename"))
        self.assertEqual(tuple(m.DEV), m.DEV_SYNTH + m.DEV_OSS)
        self.assertEqual(m.MODEL, "gpt-6-luna")
        for task in m.DEV:
            m.assert_dev(task)
        for task in ("unknown", "sealed-eval", "../eval", "zep-sidebar/../other"):
            with self.subTest(task=task), self.assertRaises((ValueError, SystemExit)):
                m.assert_dev(task)

    def test_interleaving_has_equal_size_adjacent_pairs(self):
        for iteration, slots in ((0, {"aa1", "aa2"}), (1, {"incumbent", "candidate"}),
                                 (8, {"incumbent", "candidate"})):
            rows = m.schedule(iteration)
            self.assertEqual(len(rows), 20)
            self.assertEqual({r["slot"] for r in rows}, slots)
            self.assertEqual({r["arm"] for r in rows}, {"ours-2.0.1"})
            expected = {(task, rep) for task in m.DEV for rep in (1, 2)}
            for slot in slots:
                actual = [(r["case"], r["repetition"]) for r in rows if r["slot"] == slot]
                self.assertEqual(len(actual), len(set(actual)))
                self.assertEqual(set(actual), expected)
            for left, right in zip(rows[::2], rows[1::2]):
                self.assertEqual((left["case"], left["repetition"]),
                                 (right["case"], right["repetition"]))
                self.assertEqual({left["slot"], right["slot"]}, slots)
            self.assertEqual(rows, m.schedule(iteration))
        for invalid in (-1, 9):
            with self.subTest(invalid=invalid), self.assertRaises((ValueError, SystemExit)):
                m.schedule(invalid)

    def test_prompt_scrubbing_keeps_behavior_and_removes_provenance(self):
        text = ("Test that a renamed item remains visible.\n"
                "PR #123 introduced this behavior.\n"
                "Source: src/sidebar.ts:42\n"
                "https://github.com/example/repo/pull/456\n"
                "Preserve the item text after reload.\n")
        result = m.scrub_prompt(text)
        self.assertIn("renamed item remains visible", result)
        self.assertIn("Preserve the item text", result)
        for leak in ("123", "sidebar.ts:42", "/pull/456"):
            self.assertNotIn(leak, result)

    def test_runtime_scrub_preserves_application_and_approval_boundaries(self):
        text = ("Use http://host.docker.internal:14210 as the approved disposable application.\n"
                "Safety: operate only on the approved application namespace.\n"
                "Approvals: writing the test directory is approved.\n"
                "PR #345 describes the upstream change.\n"
                "Source: src/component.ts:78\n"
                "Public reference https://example.org/project/pull/345\n")
        result = m.scrub_runtime_prompt(text)
        for kept in ("http://host.docker.internal:14210", "Safety:", "Approvals:",
                     "approved application namespace", "writing the test directory"):
            self.assertIn(kept, result)
        for removed in ("345", "component.ts:78", "example.org"):
            self.assertNotIn(removed, result)


class ObservationIntegrityTests(unittest.TestCase):
    def test_complete_batch_is_accepted_without_mutation(self):
        cells = batch()
        original = copy.deepcopy(cells)
        self.assertIsInstance(m.summarize(cells), dict)
        self.assertEqual(cells, original)

    def test_missing_duplicate_and_foreign_cells_are_refused(self):
        malformed = [batch()[:-1], batch() + [copy.deepcopy(batch()[0])]]
        foreign = batch()
        foreign[0]["case"] = "unapproved-task"
        malformed.append(foreign)
        duplicate = batch()
        duplicate[-1]["call_id"] = duplicate[0]["call_id"]
        malformed.append(duplicate)
        repeated = batch()
        repeated[-1]["case"] = repeated[-2]["case"]
        repeated[-1]["repetition"] = repeated[-2]["repetition"]
        malformed.append(repeated)
        for index, cells in enumerate(malformed):
            with self.subTest(index=index), self.assertRaises((ValueError, SystemExit)):
                m.summarize(cells)

    def test_cost_and_score_fields_are_complete_finite_and_typed(self):
        for field, value in (("tokens", None), ("tokens", -1), ("tokens", float("nan")),
                             ("generation_s", None), ("generation_s", float("inf")),
                             ("generation_s", -1), ("clean", "true"),
                             ("refactor_score", .5), ("kill_rate", 1.01),
                             ("kill_rate", -.01), ("scan_p0", -1)):
            cells = batch()
            cells[0][field] = value
            with self.subTest(field=field, value=value), self.assertRaises((ValueError, SystemExit)):
                m.summarize(cells)
        for field in ("tokens", "generation_s", "refactor_score", "kill_rate"):
            cells = batch()
            del cells[0][field]
            with self.subTest(missing=field), self.assertRaises((ValueError, KeyError, SystemExit)):
                m.summarize(cells)


class ExactPermutationTests(unittest.TestCase):
    def test_extreme_contrast_uses_within_task_reallocations(self):
        result = m.permutation(batch("candidate", 1), batch())
        self.assertEqual(result["tasks"], 5)
        self.assertAlmostEqual(result["observed_mean_task_difference"], 1)
        self.assertAlmostEqual(result["p_one_sided"], (1 / 6) ** 5)

    def test_mixed_outcomes_match_independent_label_enumeration(self):
        candidate, incumbent = batch("candidate"), batch()
        for index, cell in enumerate(candidate):
            cell["refactor_score"] = int(index % 3 != 0)
        for index, cell in enumerate(incumbent):
            cell["refactor_score"] = int(index % 4 == 0)
        distributions = []
        observed = 0
        for task in m.DEV:
            c = [cell["refactor_score"] for cell in candidate if cell["case"] == task]
            b = [cell["refactor_score"] for cell in incumbent if cell["case"] == task]
            observed += sum(c) - sum(b)
            pooled = c + b
            distributions.append([2 * sum(pooled[i] for i in selected) - sum(pooled)
                                  for selected in itertools.combinations(range(4), 2)])
        allocation_sums = [sum(x) for x in itertools.product(*distributions)]
        exact = sum(x >= observed for x in allocation_sums) / len(allocation_sums)
        result = m.permutation(candidate, incumbent)
        self.assertAlmostEqual(result["p_one_sided"], exact)
        self.assertAlmostEqual(result["observed_mean_task_difference"], observed / 10)

    def test_identical_outcomes_have_no_one_sided_signal(self):
        self.assertEqual(m.permutation(batch("candidate"), batch())["p_one_sided"], 1)


class AdoptionGuardTests(unittest.TestCase):
    def test_quality_token_cap_includes_boundary_only(self):
        self.assertEqual(decide(batch("candidate", 1, tokens=110))["verdict"], "ADOPT_QUALITY")
        self.assertEqual(decide(batch("candidate", 1, tokens=111))["verdict"], "REJECT")

    def test_cost_path_requires_reduction_and_other_cost_cap(self):
        self.assertEqual(decide(batch("candidate", tokens=85, seconds=110))["verdict"], "ADOPT_COST")
        self.assertEqual(decide(batch("candidate", tokens=86))["verdict"], "REJECT")
        self.assertEqual(decide(batch("candidate", tokens=85, seconds=111))["verdict"], "REJECT")

    def test_composition_cannot_hide_a_clean_cell_kill_regression(self):
        incumbent = batch(kill=0)
        for cell in incumbent[:5]:
            cell["clean"] = False
        for cell in incumbent[5:]:
            cell["kill_rate"] = 1
        candidate = batch("candidate", 1, kill=.75)
        # Overall kill rises from .5 to .75, but clean-cell kill falls 1 -> .75.
        outcome = decide(candidate, incumbent)
        self.assertEqual(outcome["verdict"], "REJECT")
        self.assertIn(False, outcome["guards"].values())

    def test_overall_kill_regression_is_also_rejected(self):
        outcome = decide(batch("candidate", 1, kill=.9))
        self.assertEqual(outcome["verdict"], "REJECT")

    def test_scanner_and_clean_rate_regressions_block_adoption(self):
        for field, value in (("scan_p0", 1), ("scan_p1p2", 1), ("clean", False)):
            candidate = batch("candidate", 1)
            candidate[0][field] = value
            if field == "clean":
                candidate[0]["refactor_score"] = 0
            with self.subTest(field=field):
                self.assertEqual(decide(candidate)["verdict"], "REJECT")

    def test_two_complete_baseline_batches_are_mandatory(self):
        for history in ([], [batch("aa1")], [batch("aa1"), batch("aa2")[:-1]]):
            with self.subTest(count=len(history)), self.assertRaises((ValueError, SystemExit)):
                decide(batch("candidate", 1), history=history)

    def test_noise_and_permutation_are_reported_on_rejection_too(self):
        outcome = decide(batch("candidate"))
        self.assertEqual(outcome["verdict"], "REJECT")
        self.assertIn("noise", outcome)
        self.assertIn("within_batch_width", outcome)
        self.assertEqual(outcome["task_stratified_exact_permutation"]["tasks"], 5)


class LiveBoundaryTests(unittest.TestCase):
    def test_live_commands_refuse_before_loading_or_launching_machinery(self):
        for command in ("run", "researcher", "score", "freeze", "calibrate"):
            with self.subTest(command=command), tempfile.TemporaryDirectory() as directory:
                with patch("subprocess.run", side_effect=AssertionError("subprocess launched")), \
                     patch("subprocess.Popen", side_effect=AssertionError("process launched")), \
                     patch("importlib.util.spec_from_file_location", side_effect=AssertionError("machinery imported")):
                    try:
                        result = m.main([command, "--campaign", directory])
                    except (SystemExit, ValueError) as refusal:
                        if isinstance(refusal, SystemExit):
                            self.assertNotEqual(refusal.code, 0)
                    else:
                        self.assertIsInstance(result, int)
                        self.assertNotEqual(result, 0)
                self.assertEqual(list(Path(directory).iterdir()), [])


class StopRuleTests(unittest.TestCase):
    def test_three_consecutive_nonadoptions_stop(self):
        decisions = [{"verdict": "ADOPT_QUALITY"}] + [{"verdict": "REJECT"}] * 3
        self.assertEqual(m.stop_reason(decisions), "three consecutive non-adoptions")

    def test_adoption_resets_consecutive_nonadoptions(self):
        decisions = [{"verdict": "REJECT"}, {"verdict": "REJECT"},
                     {"verdict": "ADOPT_COST"}, {"verdict": "REJECT"}]
        self.assertIsNone(m.stop_reason(decisions))
        self.assertIsNone(m.stop_reason([]))

    def test_eighth_iteration_stops_even_if_every_iteration_adopts(self):
        self.assertIsNone(m.stop_reason([{"verdict": "ADOPT_QUALITY"}] * 7))
        self.assertEqual(m.stop_reason([{"verdict": "ADOPT_QUALITY"}] * 8), "iteration cap")


class CandidateBoundaryTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        root = Path(temporary.name)
        self.before = root / "incumbent"
        self.directory = root / "iteration"
        self.candidate = self.directory / "candidate"
        self.before.mkdir()
        self.candidate.mkdir(parents=True)
        (self.before / "SKILL.md").write_text("Check the visible outcome.\n")
        (self.candidate / "SKILL.md").write_text("Check the visible outcome after each action.\n")
        self.write_json("packet.json", {"failures": [{"call_id": "bad"}]})
        self.hypothesis = {"hypotheses": [{
            "mechanism": "A missing outcome check leaves failures undetected.",
            "evidence_call_ids": ["bad"],
            "expected_effect": "Outcome checks detect a failed action.",
            "falsification": "The same failure persists after adding the outcome check.",
        }]}
        self.write_json("hypothesis.json", self.hypothesis)
        (self.directory / "hypothesis.md").write_text("One general hypothesis supported by the failing call.\n")
        self.refresh_diff_and_reviews()

    def write_json(self, name, value):
        (self.directory / name).write_text(json.dumps(value))

    def refresh_diff_and_reviews(self):
        (self.directory / "diff").write_text(m.candidate_diff(self.before, self.candidate))
        digest = m.sha(self.directory / "diff")
        self.write_json("wording-review.json", {
            "diff_sha256": digest, "verdict": "PASS", "reviewer": "independent",
            "reason": "The added instruction describes general observable behavior.",
        })
        self.write_json("repository-review.json", {
            "diff_sha256": digest, "command": "/bin/bash -p scripts/ci/review.sh", "exit": 0,
        })

    def test_one_evidenced_general_change_with_bound_reviews_is_valid(self):
        result = m.validate_candidate(self.directory, self.before)
        self.assertEqual(result["candidate"], m.tree_id(self.candidate))
        self.assertEqual(result["incumbent"], m.tree_id(self.before))
        self.assertEqual(result["diff"], m.sha(self.directory / "diff"))

    def test_two_hypotheses_are_refused(self):
        self.hypothesis["hypotheses"].append(copy.deepcopy(self.hypothesis["hypotheses"][0]))
        self.write_json("hypothesis.json", self.hypothesis)
        with self.assertRaises(ValueError):
            m.validate_candidate(self.directory, self.before)

    def test_hypothesis_requires_actual_failing_evidence(self):
        for evidence, failures in (([], [{"call_id": "bad"}]), (["unknown"], [{"call_id": "bad"}]),
                                   (["bad"], [])):
            self.hypothesis["hypotheses"][0]["evidence_call_ids"] = evidence
            self.write_json("hypothesis.json", self.hypothesis)
            self.write_json("packet.json", {"failures": failures})
            with self.subTest(evidence=evidence, failures=failures), self.assertRaises(ValueError):
                m.validate_candidate(self.directory, self.before)

    def test_task_literals_and_locator_examples_are_refused_even_with_reviews(self):
        for added in ("Use zep-sidebar as the example.\n", "Use locator('.x') to find the state.\n"):
            (self.candidate / "SKILL.md").write_text(added)
            self.refresh_diff_and_reviews()
            with self.subTest(added=added), self.assertRaises(ValueError):
                m.validate_candidate(self.directory, self.before)

    def test_changed_candidate_cannot_reuse_recorded_diff(self):
        (self.candidate / "SKILL.md").write_text("Check persistence after an action.\n")
        with self.assertRaises(ValueError):
            m.validate_candidate(self.directory, self.before)

    def test_stale_or_self_attested_wording_review_is_refused(self):
        original = json.loads((self.directory / "wording-review.json").read_text())
        for change in ({"diff_sha256": "stale"}, {"reviewer": "researcher"}, {"verdict": "FAIL"}):
            self.write_json("wording-review.json", {**original, **change})
            with self.subTest(change=change), self.assertRaises(ValueError):
                m.validate_candidate(self.directory, self.before)

    def test_repository_review_is_bound_to_diff_and_successful_command(self):
        original = json.loads((self.directory / "repository-review.json").read_text())
        for change in ({"diff_sha256": "stale"}, {"exit": 1}, {"command": "true"}):
            self.write_json("repository-review.json", {**original, **change})
            with self.subTest(change=change), self.assertRaises(ValueError):
                m.validate_candidate(self.directory, self.before)

    def test_symlink_candidate_tree_is_refused(self):
        (self.candidate / "SKILL.md").unlink()
        self.candidate.rmdir()
        self.candidate.symlink_to(self.before, target_is_directory=True)
        with self.assertRaises(ValueError):
            m.validate_candidate(self.directory, self.before)

    def test_full_interleaved_run_keeps_candidate_snapshot_separate_from_outputs(self):
        campaign = self.directory.parent / "campaign"
        campaign.mkdir()
        # A synthetic binding fixture, never a freeze command or real campaign.
        (campaign / "freeze.json").write_text(json.dumps({"bindings": {}}))
        original = m.tree(self.candidate)
        observed = []
        skill_inputs = []

        def record(row, route):
            observed.append((route, dict(row)))
            return dict(row, call_id=f"{row['slot']}-{row['case']}-{row['repetition']}",
                        infrastructure_error=False, attempts=[])

        def oss_generate(row, args, runtime, model, target, tasks):
            self.assertEqual(model, m.MODEL)
            self.assertEqual(tasks, list(m.DEV_OSS))
            self.assertEqual(target, m.batch_dir(self.directory, row["slot"]))
            return record(row, "oss")

        def synthetic_generate(row, args, active_campaign, target, active):
            self.assertEqual(active_campaign, campaign)
            self.assertEqual(target, m.batch_dir(self.directory, row["slot"]))
            return record(row, "synthetic")

        runtime = SimpleNamespace(campaign=lambda: contextlib.nullcontext())
        oss = SimpleNamespace(
            engine=SimpleNamespace(Ports=lambda start: {"unused_start": start}),
            runtime=lambda args: runtime,
            SHARED_LOCK=campaign / "unused-lock",
            generate=oss_generate,
        )

        def context(active_campaign, config, skill):
            self.assertEqual(active_campaign, campaign)
            skill_inputs.append(skill)
            self.assertEqual(m.tree(self.candidate), original)
            return contextlib.nullcontext(oss)

        config = {name: str(campaign / name) for name in ("pool", "dists", "source", "loop_runner")}
        config["campaign_id"] = "offline-fixture"

        with patch.object(m, "iteration_dir", return_value=self.directory), \
             patch.object(m, "incumbent", return_value=self.before), \
             patch.object(m, "machinery", return_value=(None, oss)), \
             patch.object(m, "bindings", return_value={}), \
             patch.object(m, "live_context", side_effect=context), \
             patch.object(m, "synthetic_generate", side_effect=synthetic_generate), \
             patch("subprocess.run", side_effect=AssertionError("subprocess launched")), \
             patch("subprocess.Popen", side_effect=AssertionError("process launched")):
            m.run_batch(SimpleNamespace(iteration=1), campaign, config)

        self.assertEqual(len(observed), 20)
        self.assertEqual(sum(route == "synthetic" for route, _ in observed), 12)
        self.assertEqual(sum(route == "oss" for route, _ in observed), 8)
        self.assertEqual([row for _, row in observed], m.schedule(1))
        self.assertEqual(skill_inputs.count(self.candidate), 10)
        self.assertEqual(skill_inputs.count(self.before), 10)
        for slot in ("incumbent", "candidate"):
            output = m.batch_dir(self.directory, slot)
            report = json.loads((output / "final.json").read_text())
            self.assertEqual(len(report["runs"]), 10)
            self.assertEqual(len({row["call_id"] for row in report["runs"]}), 10)
            expected_skill = self.candidate if slot == "candidate" else self.before
            self.assertEqual(report["skill_sha256"], m.tree_id(expected_skill))
            self.assertEqual(len(list(output.glob("*.json"))), 11)
        self.assertEqual(m.tree(self.candidate), original)
        self.assertEqual(list(self.candidate.iterdir()), [self.candidate / "SKILL.md"])
        self.assertFalse((self.directory / "VOID.json").exists())
        generated = json.loads((self.directory / "generated.json").read_text())
        self.assertEqual(generated, {"status": "COMPLETED", "reports": {
            slot: m.sha(m.batch_dir(self.directory, slot) / "final.json")
            for slot in ("incumbent", "candidate")}})


class RolloutIdentityTests(unittest.TestCase):
    def test_explicit_root_cannot_fall_back_to_different_parentless_rollout(self):
        for rollouts in ([{"thread_id": "different"}],
                         [{"thread_id": "requested", "parent_thread_id": "parent"}],
                         [{"thread_id": "requested"}, {"thread_id": "requested"}]):
            evidence = SimpleNamespace(
                root_thread_of=lambda events: "requested",
                sessions_dir_for=lambda rec, transcripts: "unused-synthetic-directory",
                load_sessions=lambda directory: rollouts,
            )
            with self.subTest(rollouts=rollouts), self.assertRaisesRegex(ValueError, "root identity mismatch"):
                m.reject_root_mismatch(evidence, {"call_id": "synthetic"}, None, [{"thread_id": "requested"}])

    def test_one_matching_parentless_root_is_accepted(self):
        evidence = SimpleNamespace(
            root_thread_of=lambda events: "requested",
            sessions_dir_for=lambda rec, transcripts: "unused-synthetic-directory",
            load_sessions=lambda directory: [{"thread_id": "requested"},
                                             {"thread_id": "child", "parent_thread_id": "requested"}],
        )
        m.reject_root_mismatch(evidence, {"call_id": "synthetic"}, None, [{"thread_id": "requested"}])


class GeneratedEvidenceTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        self.directory = self.root / "iterations/01"
        self.target = self.directory / "batches/candidate"
        self.files = []
        for relative in ("final-artifacts/call/tests/generated.spec.ts", "final-transcripts/call.jsonl",
                         "codex-sessions/call/session.jsonl"):
            path = self.target / relative
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text("original synthetic evidence\n")
            self.files.append(path)
        self.report = {"runs": [], "generation_inputs": m.generation_inputs(self.target)}
        (self.target / "final.json").write_text(json.dumps(self.report))
        (self.directory / "generated.json").write_text(json.dumps({
            "status": "COMPLETED", "reports": {"candidate": m.sha(self.target / "final.json")},
        }))

    def test_recorded_generated_bytes_are_verified_without_mutation(self):
        self.assertEqual(m.verify_report(self.target), self.report)

    def test_each_spec_transcript_and_session_change_is_refused(self):
        for path in self.files:
            original = path.read_text()
            path.write_text("changed synthetic evidence\n")
            with self.subTest(kind=path.relative_to(self.target).parts[0]), self.assertRaisesRegex(ValueError, "drift"):
                m.verify_report(self.target)
            path.write_text(original)
            self.assertEqual(m.verify_report(self.target), self.report)

    def test_final_report_cannot_be_changed_against_generation_mapping(self):
        (self.target / "final.json").write_text(json.dumps({**self.report, "runs": [{"call_id": "changed"}]}))
        with self.assertRaisesRegex(ValueError, "report changed"):
            m.verify_report(self.target)

    def test_moved_canonical_campaign_root_refuses_before_machinery(self):
        (self.root / "config.json").write_text(json.dumps({"campaign_root": str(self.root / "old-location")}))
        with patch.object(m, "bindings", side_effect=AssertionError("bindings inspected")), \
             patch.object(m, "machinery", side_effect=AssertionError("machinery imported")), \
             self.assertRaisesRegex(ValueError, "canonical root drift"):
            m.verify_campaign(self.root)


class ImportedMachineryTests(unittest.TestCase):
    def test_real_lazy_import_and_pure_helpers_need_no_runtime_or_task_data(self):
        previous = m.MACHINERY
        original_text, original_bytes = Path.read_text, Path.read_bytes

        def check(path):
            parts = Path(path).parts
            if (any(part in ("e2e-skills-bench", "sealed-eval", "tasks", "cases") for part in parts)
                    or any(re.fullmatch(r"(?:v\d+-\d+|zep-[\w-]+)", part) for part in parts)):
                raise AssertionError("import attempted to read task or cached campaign material")

        def read_text(path, *args, **kwargs):
            check(path)
            return original_text(path, *args, **kwargs)

        def read_bytes(path, *args, **kwargs):
            check(path)
            return original_bytes(path, *args, **kwargs)

        try:
            m.MACHINERY = None
            with patch("subprocess.run", side_effect=AssertionError("subprocess launched")), \
                 patch("subprocess.Popen", side_effect=AssertionError("process launched")), \
                 patch("socket.socket", side_effect=AssertionError("socket opened")), \
                 patch.object(Path, "read_text", read_text), patch.object(Path, "read_bytes", read_bytes):
                base, oss = m.machinery()
                for module, names in ((base, ("generation_staging", "scoring_guard", "generation_config_text")),
                                      (oss, ("generate", "score_rows", "codex_context", "score_measurements"))):
                    for name in names:
                        self.assertTrue(callable(getattr(module, name)))
                scoring = "webServer: { reuseExistingServer: false }"
                self.assertEqual(base.generation_config_text(scoring),
                                 "webServer: { reuseExistingServer: true }")
                for invalid in ("webServer: {}", scoring + scoring, "reuseExistingServer: true"):
                    with self.subTest(config=invalid), self.assertRaises(ValueError):
                        base.generation_config_text(invalid)
                passing = {"ok": True, "passed": 1, "failed": 0, "errors": []}
                zero_tests = {**passing, "passed": 0}
                faults = {str(index): {"failed": 0, "errors": []} for index in range(5)}
                zero = oss.score_measurements([zero_tests] * 3, faults, passing)
                self.assertFalse(zero["clean"])
                self.assertEqual(zero["refactor_score"], 0)
                unknown_faults = {str(index): {"failed": 1, "errors": []} for index in range(5)}
                unknown = oss.score_measurements([passing] * 3, unknown_faults, passing)
                self.assertTrue(unknown["clean"])
                self.assertIsNone(unknown["kill_rate"])
                self.assertFalse(unknown["fault_attribution_complete"])
        finally:
            m.MACHINERY = previous


class ScoringFlowTests(unittest.TestCase):
    def test_mixed_scoring_preserves_unknowns_and_slot_scoped_offline_attribution(self):
        previous = m.MACHINERY
        original_text, original_bytes = Path.read_text, Path.read_bytes

        def safe_read(original, path, *args, **kwargs):
            parts = Path(path).parts
            if (any(p in ("tasks", "cases", "sealed-eval", "e2e-skills-bench") for p in parts)
                    or any(re.fullmatch(r"(?:v\d+-\d+|zep-[\w-]+)", p) for p in parts)):
                raise AssertionError("task or campaign read during import")
            return original(path, *args, **kwargs)

        try:
            m.MACHINERY = None
            with patch("subprocess.run", side_effect=AssertionError("process launched")), \
                 patch("subprocess.Popen", side_effect=AssertionError("process launched")), \
                 patch("socket.socket", side_effect=AssertionError("socket opened")), \
                 patch.object(Path, "read_text", lambda path, *a, **kw: safe_read(original_text, path, *a, **kw)), \
                 patch.object(Path, "read_bytes", lambda path, *a, **kw: safe_read(original_bytes, path, *a, **kw)):
                _, real_oss = m.machinery()
                score_measurements = real_oss.score_measurements
        finally:
            m.MACHINERY = previous

        with tempfile.TemporaryDirectory() as temporary:
            campaign = Path(temporary)
            directory = m.iteration_dir(campaign, 1)
            directory.mkdir(parents=True)
            (campaign / "freeze.json").write_text(json.dumps({"bindings": {}}))
            annotations, reports = {}, {}
            defects = [f"D{index}" for index in range(1, 6)]
            for slot in ("incumbent", "candidate"):
                target = m.batch_dir(directory, slot)
                runs = []
                annotations[slot] = {}
                for task in m.DEV:
                    for repetition in (1, 2):
                        # IDs intentionally repeat across the two separate slot directories.
                        call_id = f"{task}-{repetition}"
                        spec = target / "final-artifacts" / call_id / "tests/example.spec.ts"
                        spec.parent.mkdir(parents=True)
                        spec.write_text("synthetic delivered spec\n")
                        runs.append(dict(case=task, repetition=repetition, call_id=call_id,
                                         arm=m.ARM, spec_files=["tests/example.spec.ts"],
                                         tests_files=["tests/example.spec.ts"], attempts=[{"elapsed_ms": 1000}]))
                        annotations[slot][call_id] = {"D1": slot == "candidate"}
                report = dict(model=m.MODEL, runs=runs, freeze_sha256=m.sha(campaign / "freeze.json"),
                              skill_sha256="synthetic-" + slot, generation_inputs=m.generation_inputs(target))
                (target / "final.json").write_text(json.dumps(report))
                reports[slot] = m.sha(target / "final.json")
            (directory / "generated.json").write_text(json.dumps({"status": "COMPLETED", "reports": reports}))
            annotation_path = campaign / "synthetic-attributions.json"
            annotation_path.write_text(json.dumps(annotations))
            passing = {"ok": True, "passed": 1, "failed": 0, "errors": []}

            def measurements():
                return dict(clean_runs=[copy.deepcopy(passing) for _ in range(3)],
                            faults={defect: {"failed": 1, "errors": []} for defect in defects},
                            refactor=copy.deepcopy(passing))

            oss_calls = []

            def score_rows(target, runtime, report, slot_annotations):
                rec = report["runs"][0]
                oss_calls.append((target.name, rec["call_id"]))
                self.assertIs(slot_annotations[rec["call_id"]]["D1"], target.name == "candidate")
                raw = measurements()
                for defect, value in slot_annotations[rec["call_id"]].items():
                    raw["faults"][defect]["valid_detection"] = value
                return [score_measurements(raw["clean_runs"], raw["faults"], raw["refactor"], {"p0": 0, "p1p2": 0})]

            runtime = SimpleNamespace(campaign=lambda: contextlib.nullcontext())
            oss = SimpleNamespace(
                score_measurements=score_measurements, score_rows=score_rows,
                engine=SimpleNamespace(Ports=lambda port: port, CASES=campaign / "unused-cases",
                                       evaluate_specs=lambda *args: measurements(),
                                       scan_smells=lambda *args: {"p0": 0, "p1p2": 0}),
                runtime=lambda args: runtime, SHARED_LOCK=campaign / "unused-lock",
                v2=SimpleNamespace(transcript_events=lambda *args: [], rollout_summary=lambda *args: {},
                                   cell_extras=lambda *args: {"treatment": "synthetic"}),
                evidence=SimpleNamespace(root_thread_of=lambda events: "root",
                                         sessions_dir_for=lambda *args: "unused-session-directory",
                                         load_sessions=lambda directory: [{"thread_id": "root"}],
                                         cell_tokens=lambda *args: {"complete": True, "processed": 100, "total": 120}),
            )
            config = {key: str(campaign / key) for key in ("pool", "dists", "source", "loop_runner", "campaign_id")}
            base = SimpleNamespace(scoring_guard=lambda tasks: self.assertEqual(tasks, list(m.DEV_SYNTH)))
            with patch.object(m, "machinery", return_value=(base, oss)), \
                 patch.object(m, "live_context", return_value=contextlib.nullcontext(oss)), \
                 patch.object(m, "verify_campaign", return_value=None), \
                 patch("subprocess.run", side_effect=AssertionError("process launched")), \
                 patch("subprocess.Popen", side_effect=AssertionError("process launched")), \
                 patch("socket.socket", side_effect=AssertionError("socket opened")):
                m.score_batch(SimpleNamespace(iteration=1, adjudications=annotation_path), campaign, config)
                self.assertEqual(len(oss_calls), 8)
                for slot in ("incumbent", "candidate"):
                    raw = m.read(m.batch_dir(directory, slot) / "scores.json")["scores"]
                    self.assertEqual(len(raw), 10)
                    self.assertTrue(all(row["kill_rate"] is None for row in raw))
                    self.assertTrue(all(row["faults"]["D1"]["valid_detection"] is (slot == "candidate") for row in raw))
                with self.assertRaisesRegex(ValueError, "kill[ _]rate"):
                    m.analyze_batch(campaign, 1)
                complete = {slot: {call_id: {defect: slot == "candidate" for defect in defects}
                                   for call_id in calls} for slot, calls in annotations.items()}
                m.adjudicate_batch(campaign, 1, complete)
                m.analyze_batch(campaign, 1)
            for slot in ("incumbent", "candidate"):
                result = m.read(m.batch_dir(directory, slot) / "results.json")
                self.assertEqual(len(result["cells"]), 10)
                self.assertEqual(result["summary"]["effective_kill_clean_cells"], int(slot == "candidate"))
                self.assertEqual(result["summary"]["tokens_mean"], 100)
                self.assertTrue(all(row["cached_tokens"] == 20 for row in result["cells"]))
                self.assertEqual(result["score_file"], "adjudicated-scores.json")


if __name__ == "__main__":
    unittest.main()
