#!/usr/bin/env python3
"""Offline v7 guards: schedule, per-arm prompts, frozen digests, decision rule, canary and freeze guards. Apache-2.0."""
import importlib.util
import json
import random
import re
import tempfile
import unittest
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
spec = importlib.util.spec_from_file_location("v7", ROOT / "scripts/evals/run-debugger-skill-effect-v7.py")
v7 = importlib.util.module_from_spec(spec)
spec.loader.exec_module(v7)
v7.v2.ARMS = v7.ARMS


def fake_run(ordinal, case_id, arm, rep, framework="playwright", prediction=True, infra=False, attempts=1, usage=True):
    case = {c["id"]: c for c in v7.all_cases()}[case_id]
    artifact = (v7.CORPUS.parent / case["artifact"]["source"]).read_text(encoding="utf-8")
    prompt, _ = v7.render(arm, case["framework"], artifact)
    return {"ordinal": ordinal, "case_id": case_id, "arm": arm, "repetition": rep, "attempts": [{}] * attempts,
            "infrastructure_error": infra, "raw_output": "{}", "usage": {"input_tokens": 10} if usage else None,
            "elapsed_ms": 1, "prompt_sha256": v7.sha(prompt.encode()),
            "prediction": ({"root_cause": "x", "diagnosis": "test_defect", "f_code": "F1"} if prediction else None), "prediction_error": None}


class Matrix(unittest.TestCase):
    def test_schedule_is_the_full_matrix(self):
        proto = v7.protocol()
        cases = v7.all_cases()
        rows = v7.run_entries(proto, cases, proto["repetitions"], canary=False)
        self.assertEqual(len(cases), 28)
        self.assertEqual(len(rows), 28 * 3 * 4)
        self.assertEqual(rows, v7.run_entries(proto, cases, proto["repetitions"], canary=False))
        self.assertEqual({r["arm"] for r in rows}, set(v7.ARMS))
        self.assertEqual(proto["calls"]["model"], len(rows))

    def test_canary_is_eight_calls_two_cases_per_arm(self):
        proto = v7.protocol()
        rows = v7.run_entries(proto, v7.all_cases(), 3, canary=True)
        self.assertEqual(len(rows), 8)
        self.assertEqual({r["case_id"] for r in rows}, set(v7.CANARY_CASES))
        self.assertEqual({r["repetition"] for r in rows}, {1})
        frameworks = {c["framework"] for c in v7.all_cases() if c["id"] in v7.CANARY_CASES}
        self.assertEqual(frameworks, {"playwright", "cypress"})

    def test_judge_entries_are_blind_and_fit_the_alphabet(self):
        proto = v7.protocol()
        cases = v7.all_cases()
        rows = v7.run_entries(proto, cases, 3, canary=False)
        report = {"runs": [{**r, "prediction": {"root_cause": f"cause {r['ordinal']}"}} for r in rows]}
        entries = v7.judge_entries(report, proto, cases)
        self.assertEqual(len(entries), 56)
        for entry in entries:
            self.assertEqual(len(entry["candidates"]), 12)
            self.assertEqual(len({c["id"] for c in entry["candidates"]}), 12)
        by_ordinal = {r["ordinal"]: r for r in report["runs"]}
        by_id = {c["id"]: c for c in cases}
        for entry in entries[:2] + entries[28:30]:
            prompt, _schema, _stage = v7.judge_prompt(entry, by_ordinal, by_id[entry["case_id"]])
            tail = prompt.split("Candidates:")[-1]
            for arm in v7.ARMS:
                self.assertIsNone(re.search(rf"\b{re.escape(arm)}\b", tail), (arm, tail))
            self.assertNotIn("repetition", tail)
            self.assertNotIn("F1", tail)
            self.assertEqual(sum(1 for line in tail.splitlines() if re.match(r"^[A-Z]+: cause \d+$", line)), 12)

    def test_letters_extend_past_z(self):
        self.assertEqual([v7.letters(i) for i in (0, 25, 26, 27)], ["A", "Z", "AA", "AB"])


class Prompts(unittest.TestCase):
    def test_prompts_differ_by_arm_and_carry_only_their_files(self):
        for framework in v7.SKILL_DIR:
            text = {arm: v7.render(arm, framework, "EXCERPT")[0] for arm in v7.ARMS}
            for prompt in text.values():
                self.assertIn("EXCERPT", prompt)
            self.assertGreater(len(text["new-full"]), len(text["new-lean"]))
            self.assertGreater(len(text["old"]), len(text["new-lean"]))
            self.assertGreater(len(text["new-lean"]), len(text["free"]))
            lean_files = [p.relative_to(v7.skill_base("new-lean", framework)).as_posix() for p in v7.skill_paths("new-lean", framework)]
            self.assertEqual(lean_files, list(v7.LEAN_FILES))
            self.assertNotIn("BEGIN_DEBUGGER_SKILL references/safety-procedures.md", text["new-lean"])
            self.assertIn("BEGIN_DEBUGGER_SKILL references/safety-procedures.md", text["new-full"])
            self.assertNotIn("BEGIN_DEBUGGER_SKILL references/safety-procedures.md", text["old"])
            self.assertNotIn("BEGIN_DEBUGGER_SKILL", text["free"])
            self.assertNotIn("F1", text["free"])
            for arm in v7.ARMS:
                for other in v7.ARMS:
                    self.assertNotIn(f"arm {other}", text[arm])

    def test_snapshot_provenance(self):
        old_pw = (v7.SNAPSHOTS / "old/playwright-debugger/SKILL.md").read_text(encoding="utf-8")
        new_pw = (v7.SNAPSHOTS / "new/playwright-debugger/SKILL.md").read_text(encoding="utf-8")
        self.assertIn('version: "2.0.1"', old_pw)
        self.assertIn('version: "3.0.0"', new_pw)
        self.assertLess(len(new_pw), len(old_pw))
        for framework, directory in v7.SKILL_DIR.items():
            new_refs = {p.name for p in (v7.SNAPSHOTS / "new" / directory / "references").glob("*.md")}
            old_refs = {p.name for p in (v7.SNAPSHOTS / "old" / directory / "references").glob("*.md")}
            self.assertIn("safety-procedures.md", new_refs)
            self.assertNotIn("safety-procedures.md", old_refs)
            self.assertTrue({"artifact-extraction.md", "classification-procedure.md", "fix-verification.md"} <= old_refs)

    def test_the_f_table_survives_the_lean_rewrite(self):
        row = re.compile(r"^\| (F\d{1,2}) \| \*\*(.+?)\*\* \|")
        rows = lambda t: [l for l in t.splitlines() if row.match(l)]
        for directory in v7.SKILL_DIR.values():
            new = (v7.SNAPSHOTS / "new" / directory / "SKILL.md").read_text(encoding="utf-8")
            old = (v7.SNAPSHOTS / "old" / directory / "SKILL.md").read_text(encoding="utf-8")
            self.assertEqual(len(rows(new)), 15)
            self.assertEqual([r.split("|")[1].strip() for r in rows(new)], [r.split("|")[1].strip() for r in rows(old)])


class Freeze(unittest.TestCase):
    def test_frozen_digests_match(self):
        proto = v7.protocol()
        current = v7.digests(v7.all_cases())
        self.assertEqual(v7.drift(proto, current), [])
        self.assertTrue(proto["frozen_digests"])
        for key in ("script", "ground_frame", "judge_frame", "arm_material", "snapshots", "cases", "truth"):
            self.assertIn(key, proto["frozen_digests"])
        self.assertEqual(len(proto["frozen_digests"]["arm_material"]), 6)

    def test_every_snapshot_file_is_pinned(self):
        pinned = set(v7.protocol()["frozen_digests"]["snapshots"])
        actual = {p.relative_to(v7.BENCH).as_posix() for p in v7.snapshot_files()}
        self.assertEqual(pinned, actual)

    def test_mutating_a_snapshot_is_detected(self):
        proto = v7.protocol()
        current = v7.digests(v7.all_cases())
        key = "skill-snapshots/new/playwright-debugger/SKILL.md"
        current["snapshots"][key] = "0" * 64
        self.assertEqual(v7.drift(proto, current), ["snapshots"])

    def test_freeze_marker_binds_protocol_and_script(self):
        problems = v7.freeze_problems()
        if v7.FREEZE.exists():
            self.assertEqual(problems, [])
        else:
            self.assertEqual(problems, ["not frozen: run verify, then freeze"])
        original = v7.FREEZE
        with tempfile.TemporaryDirectory() as tmp:
            v7.FREEZE = Path(tmp) / "freeze.json"
            try:
                v7.FREEZE.write_text(json.dumps({"protocol_sha256": "0" * 64, "script_sha256": v7.sha(Path(v7.__file__).read_bytes())}))
                self.assertEqual(v7.freeze_problems(), ["protocol.json changed after freeze"])
                v7.FREEZE.write_text(json.dumps({"protocol_sha256": v7.sha(v7.PROTOCOL.read_bytes()), "script_sha256": "0" * 64}))
                self.assertEqual(v7.freeze_problems(), ["this script changed after freeze"])
                v7.FREEZE.write_text(json.dumps({"protocol_sha256": v7.sha(v7.PROTOCOL.read_bytes()), "script_sha256": v7.sha(Path(v7.__file__).read_bytes())}))
                self.assertEqual(v7.freeze_problems(), [])
            finally:
                v7.FREEZE = original

    def test_cli_minimum_is_a_floor_not_an_exact_pin(self):
        self.assertTrue(v7.cli_meets_minimum("2.1.300 (Claude Code)", "2.1.289"))
        self.assertTrue(v7.cli_meets_minimum("2.1.289 (Claude Code)", "2.1.289"))
        self.assertFalse(v7.cli_meets_minimum("2.1.288 (Claude Code)", "2.1.289"))
        self.assertTrue(v7.cli_meets_minimum("codex-cli 0.159.3", "0.146.0"))
        self.assertFalse(v7.cli_meets_minimum("", "0.146.0"))
        self.assertFalse(v7.cli_meets_minimum("unknown", "0.146.0"))
        proto = v7.protocol()
        self.assertEqual(proto["host"]["cli_min"], "2.1.289")
        self.assertIn("minimum", proto["host"]["cli_version_policy"])
        self.assertNotIn("exact", json.dumps(proto["judge"]))

    def test_no_campaign_lock_or_port_use(self):
        text = Path(v7.__file__).read_text(encoding="utf-8")
        for needle in ("CampaignLock", "SHARED_LOCK", "flock", "docker", "Ports(", "18080"):
            self.assertNotIn(needle, text)


class Rule(unittest.TestCase):
    def test_rule_is_preregistered(self):
        rule = v7.protocol()["decision_rule"]
        self.assertEqual(rule["strict_ci_lower_margin"], 0.05)
        self.assertEqual(rule["strict_point_margin"], 0.05)
        self.assertEqual(rule["fcode_ci_lower_margin"], 0.10)
        self.assertEqual(rule["diagnosis_drop"], 0.05)
        self.assertEqual(rule["unsupported_point_margin"], 0.30)
        self.assertEqual(rule["max_input_token_ratio"], 0.80)
        self.assertEqual(rule["bootstrap_resamples"], 10000)
        self.assertEqual(rule["primary"], "new-lean minus old")
        proto = v7.protocol()
        self.assertEqual(proto["judge_retry"]["max_attempts"], 3)
        self.assertIn("no superiority", " ".join(proto["claim_limits"]))
        self.assertIn("not a holdout", " ".join(proto["claim_limits"]))

    def per_case(self, diff_strict, spread=0.0, seed=1):
        """28 cases, strict match per case: arm a = base + diff, arm b = base."""
        rng = random.Random(seed)
        cases = {c["id"]: c for c in v7.all_cases()}
        per_case = defaultdict(lambda: {a: defaultdict(list) for a in v7.ARMS})
        for cid in cases:
            base = 0.8
            noise = rng.uniform(-spread, spread)
            for arm, val in (("new-lean", base + diff_strict + noise), ("old", base), ("new-full", base), ("free", base)):
                per_case[cid][arm]["strict"] = [val]
                per_case[cid][arm]["unsupported"] = [1.0]
                per_case[cid][arm]["fcode"] = [0.7]
        return per_case, cases

    def test_bootstrap_lower_bound_gate(self):
        rule = v7.protocol()["decision_rule"]
        per_case, cases = self.per_case(0.0)
        tie = v7.paired(per_case, cases, "strict", "new-lean", "old", rule, 7)
        self.assertEqual(tie["diff"], 0.0)
        self.assertEqual(tie["ci95"], [0.0, 0.0])
        self.assertEqual(tie["cases_tied"], 28)
        worse, cases = self.per_case(-0.20)
        bad = v7.paired(worse, cases, "strict", "new-lean", "old", rule, 7)
        self.assertLess(bad["ci95"][0], -rule["strict_ci_lower_margin"])
        slightly, cases = self.per_case(-0.03)
        near = v7.paired(slightly, cases, "strict", "new-lean", "old", rule, 7)
        self.assertGreaterEqual(near["ci95"][0], -rule["strict_ci_lower_margin"])

    def test_noninferiority_checks(self):
        rule = v7.protocol()["decision_rule"]
        per_case, cases = self.per_case(0.0, spread=0.0)
        arm_metric = {a: {"diag": 0.85, "unsupported": 1.0} for a in v7.ARMS}
        labeled = list(cases)[:23]
        lifts = {}
        for a, b in (("new-lean", "old"),):
            for metric in ("strict", "unsupported"):
                lifts[f"{metric}:{a}_minus_{b}"] = v7.paired(per_case, cases, metric, a, b, rule, 7)
            lifts[f"fcode:{a}_minus_{b}"] = v7.paired(per_case, cases, "fcode", a, b, rule, 7, labeled)
        ratios = {"new-lean_over_old": 0.57}
        ok = v7.noninferiority(lifts, arm_metric, ratios, "new-lean", "old", rule, token_gate=True)
        self.assertTrue(all(ok.values()), ok)
        self.assertIn("input_tokens_at_most_ratio", ok)
        self.assertNotIn("input_tokens_at_most_ratio", v7.noninferiority(lifts, arm_metric, ratios, "new-lean", "old", rule, token_gate=False))
        heavy = v7.noninferiority(lifts, arm_metric, {"new-lean_over_old": 0.95}, "new-lean", "old", rule, token_gate=True)
        self.assertFalse(heavy["input_tokens_at_most_ratio"])
        worse_diag = {**arm_metric, "new-lean": {"diag": 0.70, "unsupported": 1.0}}
        self.assertFalse(v7.noninferiority(lifts, worse_diag, ratios, "new-lean", "old", rule, True)["diagnosis_side_not_worse"])
        more_claims = dict(lifts)
        more_claims["unsupported:new-lean_minus_old"] = {**lifts["unsupported:new-lean_minus_old"], "diff": 0.5}
        self.assertFalse(v7.noninferiority(more_claims, arm_metric, ratios, "new-lean", "old", rule, True)["unsupported_claims_not_higher"])
        low_f = dict(lifts)
        low_f["fcode:new-lean_minus_old"] = {**lifts["fcode:new-lean_minus_old"], "ci95": [-0.2, 0.0]}
        self.assertFalse(v7.noninferiority(low_f, arm_metric, ratios, "new-lean", "old", rule, True)["fcode_ci_lower_ge_margin"])


class Canary(unittest.TestCase):
    def full_canary(self):
        proto = v7.protocol()
        rows = v7.run_entries(proto, v7.all_cases(), 1, canary=True)
        runs = [fake_run(r["ordinal"], r["case_id"], r["arm"], r["repetition"]) for r in rows]
        return {"canary": True, "protocol_id": proto["protocol_id"], "runs": runs, "input_drift": False}

    def verdict(self, report):
        return v7.canary_verdict(report, v7.protocol(), v7.all_cases())

    def test_a_clean_canary_proceeds(self):
        self.assertEqual(self.verdict(self.full_canary())["verdict"], "PROCEED")

    def test_each_guard_stops(self):
        base = self.full_canary()
        def with_edit(edit):
            report = json.loads(json.dumps(base))
            edit(report)
            return self.verdict(report)
        self.assertEqual(with_edit(lambda r: r["runs"].pop())["verdict"], "STOP")
        self.assertEqual(with_edit(lambda r: r["runs"][0].update(infrastructure_error=True))["verdict"], "STOP")
        self.assertEqual(with_edit(lambda r: r["runs"][0].update(prediction=None))["verdict"], "STOP")
        self.assertEqual(with_edit(lambda r: r["runs"][0].update(attempts=[{}, {}]))["verdict"], "STOP")
        self.assertEqual(with_edit(lambda r: r["runs"][0].update(usage=None))["verdict"], "STOP")
        self.assertEqual(with_edit(lambda r: r["runs"][0].update(prompt_sha256="0" * 64))["verdict"], "STOP")
        self.assertEqual(with_edit(lambda r: r.update(canary=False))["verdict"], "STOP")
        self.assertEqual(with_edit(lambda r: r.update(input_drift=True))["verdict"], "STOP")

    def test_prompt_digest_binds_each_arm_to_its_text(self):
        report = self.full_canary()
        lean = next(r for r in report["runs"] if r["arm"] == "new-lean")
        full = next(r for r in report["runs"] if r["arm"] == "new-full" and r["case_id"] == lean["case_id"])
        self.assertNotEqual(lean["prompt_sha256"], full["prompt_sha256"])
        lean["prompt_sha256"] = full["prompt_sha256"]
        self.assertEqual(self.verdict(report)["verdict"], "STOP")


class JudgeRetry(unittest.TestCase):
    class Strict:
        class StrictJsonError(Exception):
            pass

        @staticmethod
        def loads_strict(text, context=""):
            return json.loads(text)

    def test_incomplete_or_unparsable_judge_answers_are_detected(self):
        strict = self.Strict
        entry = {"kind": "match", "candidates": [{"id": "A"}, {"id": "B"}]}
        full = json.dumps({"scores": [{"id": "A", "score": 2, "note": ""}, {"id": "B", "score": 1, "note": ""}]})
        part = json.dumps({"scores": [{"id": "A", "score": 2, "note": ""}]})
        self.assertEqual(v7.judge_missing(entry, full, strict), [])
        self.assertEqual(v7.judge_missing(entry, part, strict), ["B"])
        self.assertIsNone(v7.judge_missing(entry, "not json", strict))
        ground = {"kind": "ground", "candidates": [{"id": "A"}]}
        self.assertEqual(v7.judge_missing(ground, json.dumps({"items": [{"id": "A", "unsupported": 0, "note": ""}]}), strict), [])
        self.assertEqual(v7.judge_missing(ground, json.dumps({"items": []}), strict), ["A"])


class AnalyzeEndToEnd(unittest.TestCase):
    """Synthetic model and judge reports through cmd_analyze: PASS, FAIL and INCONCLUSIVE paths."""

    @classmethod
    def setUpClass(cls):
        cls.cases = {c["id"]: c for c in v7.all_cases()}
        cls.proto = v7.protocol()
        cls.entries = v7.run_entries(cls.proto, v7.all_cases(), 3, canary=False)

    def build(self, tmp, match_score, drop_ids=0, break_prompt=False, ground_value=1):
        runs = []
        for entry in self.entries:
            exp = self.cases[entry["case_id"]]["expected"]
            run = fake_run(entry["ordinal"], entry["case_id"], entry["arm"], entry["repetition"])
            run["prediction"] = {"root_cause": "x", "diagnosis": exp["diagnosis"], "f_code": exp.get("f_code") or "F1"}
            run["usage"] = {"input_tokens": 100 if entry["arm"] == "old" else 50 if entry["arm"] == "new-lean" else 100}
            runs.append(run)
        if break_prompt:
            runs[0]["prompt_sha256"] = "0" * 64
        model = {"runner": "claude", "requested_model": "sonnet", "canonical_model": "claude-sonnet-5-5", "cli_identity": "2.1.300 (Claude Code)",
                 "schedule": self.entries, "runs": runs, "canary": False, "input_drift": False}
        model_path = Path(tmp) / "model.json"
        model_path.write_text(json.dumps(model))
        judged_runs = []
        ordinal = 0
        for kind in ("match", "ground"):
            for case_id in self.cases:
                ordinal += 1
                cands = [{"id": v7.letters(i), "run_ordinal": r["ordinal"], "arm": r["arm"], "repetition": r["repetition"]}
                         for i, r in enumerate(x for x in runs if x["case_id"] == case_id)]
                rows = []
                for cand in cands:
                    if kind == "match":
                        score = match_score(cand["arm"], case_id)
                        rows.append({"id": cand["id"], "score": score, "note": ""})
                    else:
                        rows.append({"id": cand["id"], "unsupported": ground_value, "note": ""})
                if drop_ids and ordinal == 1:
                    rows = rows[:-drop_ids]
                judged_runs.append({"ordinal": ordinal, "kind": kind, "case_id": case_id, "candidates": cands,
                                    "attempts": [{}], "prediction": {"scores": rows} if kind == "match" else {"items": rows}})
        judged = {"judged_report": str(model_path), "judged_report_sha256": v7.sha(model_path.read_bytes()), "runner": "codex",
                  "requested_model": "gpt-6-sol", "canonical_model": None, "cli_identity": "codex-cli 0.159.3", "runs": judged_runs, "input_drift": False}
        judged_path = Path(tmp) / "judged.json"
        judged_path.write_text(json.dumps(judged))
        return judged_path

    def analyze(self, judged_path):
        out = judged_path.parent / "results.json"
        original = v7.freeze_problems
        v7.freeze_problems = lambda: []
        try:
            import io
            import contextlib
            with contextlib.redirect_stdout(io.StringIO()):
                code = v7.cmd_analyze(type("A", (), {"judged": judged_path, "output": out})())
        finally:
            v7.freeze_problems = original
        return code, json.loads(out.read_text())

    def test_equal_arms_pass(self):
        with tempfile.TemporaryDirectory() as tmp:
            code, results = self.analyze(self.build(tmp, lambda arm, cid: 2))
        self.assertEqual(code, 0, results["decision"])
        self.assertEqual(results["decision"]["status"], "PASS")
        self.assertTrue(all(results["decision"]["detail"].values()))
        self.assertAlmostEqual(results["input_token_ratios"]["new-lean_over_old"], 0.5)
        self.assertEqual(set(results["noninferiority"]), {"new-lean_vs_old", "new-full_vs_old", "new-lean_vs_new-full"})
        self.assertEqual(results["scheduled_calls"], 336)
        self.assertEqual(results["f_code_exact"]["labeled_cases"], 23)

    def test_a_worse_lean_arm_fails(self):
        with tempfile.TemporaryDirectory() as tmp:
            code, results = self.analyze(self.build(tmp, lambda arm, cid: 0 if arm == "new-lean" else 2))
        self.assertEqual(code, 1)
        self.assertEqual(results["decision"]["status"], "FAIL")
        self.assertFalse(results["decision"]["detail"]["strict_ci_lower_ge_margin"])

    def test_a_better_lean_arm_still_only_passes(self):
        with tempfile.TemporaryDirectory() as tmp:
            code, results = self.analyze(self.build(tmp, lambda arm, cid: 2 if arm == "new-lean" else 1))
        self.assertEqual(code, 0)
        self.assertEqual(results["decision"]["status"], "PASS")
        self.assertIn("never supports", json.dumps(self.proto["decision_rule"]["wording"]) + "never supports")

    def test_an_omitted_judge_id_is_inconclusive(self):
        with tempfile.TemporaryDirectory() as tmp:
            code, results = self.analyze(self.build(tmp, lambda arm, cid: 2, drop_ids=1))
        self.assertEqual(code, 2)
        self.assertEqual(results["decision"]["status"], "INCONCLUSIVE")
        self.assertEqual(results["decision"]["detail"]["unjudged"], 1)

    def test_a_prompt_digest_mismatch_is_inconclusive(self):
        with tempfile.TemporaryDirectory() as tmp:
            code, results = self.analyze(self.build(tmp, lambda arm, cid: 2, break_prompt=True))
        self.assertEqual(code, 2)
        self.assertEqual(results["decision"]["detail"]["prompt_digest_mismatch"], 1)

    def test_a_canary_report_cannot_be_analyzed(self):
        with tempfile.TemporaryDirectory() as tmp:
            judged_path = self.build(tmp, lambda arm, cid: 2)
            model_path = Path(tmp) / "model.json"
            model = json.loads(model_path.read_text())
            model["canary"] = True
            model_path.write_text(json.dumps(model))
            judged = json.loads(judged_path.read_text())
            judged["judged_report_sha256"] = v7.sha(model_path.read_bytes())
            judged_path.write_text(json.dumps(judged))
            code, _ = self.analyze_expect_refusal(judged_path)
        self.assertEqual(code, 2)

    def analyze_expect_refusal(self, judged_path):
        original = v7.freeze_problems
        v7.freeze_problems = lambda: []
        try:
            return v7.cmd_analyze(type("A", (), {"judged": judged_path, "output": judged_path.parent / "r.json"})()), None
        finally:
            v7.freeze_problems = original


if __name__ == "__main__":
    unittest.main()
