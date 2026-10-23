#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Regression checks for denominators, abstention and report transport."""

import copy
from html.parser import HTMLParser
import json
from pathlib import Path
import subprocess
import sys
import tempfile
from unittest.mock import patch
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parent))
from report import ROOT, finite_measurement, holdout_measurement, metrics, markdown, html_report, load_comparator
from promptfoo import config, project


def fixture():
    return {"schema_version": 1, "study_id": "synthetic-contract-test",
            "setting": "synthetic only, not a model benchmark",
            "unit_definition": "one labeled code location and pattern",
            "positive_definition": "reportable issue",
            "negative_definition": "legitimate code under the rubric",
            "ground_truth_method": "synthetic test labels",
            "units": [{"id": str(i), "positive": i % 2 == 0,
                       "evidence": "synthetic fixture"} for i in range(6)],
            "systems": [{"id": "test-system", "definition": "synthetic predictions",
                         "decision_rule": "positive means final reported issue",
                         "execution_evidence": "test fixture, no model/tools ran",
                         "decisions": {"0": "positive", "1": "positive", "2": "negative",
                                       "3": "negative", "4": "abstain", "5": "error"}}]}


class Measurements(unittest.TestCase):
    def test_taxonomy_uses_documents_without_scanner_and_preserves_custom_severity(self):
        runner = load_comparator().RUNNER
        canonical = runner.canonical_severities()
        self.assertEqual(len(canonical), 45)
        expected = {"#5a": "P0", "#5b": "P1", "#4c-4e": "P1",
                    "#4f": "P0", "#8c": "P0", "#10f": "P1", "#11c": "P2"}
        for key, severity in expected.items():
            self.assertEqual(canonical[key], severity)
        self.assertFalse({"#4c", "#4d", "#4e", "#4", "#5"} & canonical.keys())
        with tempfile.TemporaryDirectory() as directory:
            skill = Path(directory)
            for name in ("SKILL.md", "references/pattern-reference.md", "references/grep-patterns.md"):
                target = skill / name
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_bytes((runner.DEFAULT_SKILL_DIR / name).read_bytes())
            # No launcher or runtime is staged: taxonomy must not read either.
            self.assertEqual(canonical, runner.canonical_severities(skill))
            path = skill / "SKILL.md"
            original = path.read_text()
            old = "| 15 | Missing await on expect | P1 |"
            self.assertIn(old, original)
            path.write_text(original.replace(old, old.replace("P1", "P2"), 1))
            changed = runner.canonical_severities(skill)
            self.assertEqual(changed, {**canonical, "#15": "P2"})
            reference = skill / "references/pattern-reference.md"
            reference.write_text(reference.read_text().replace("(5a P0, 5b P1)", ""))
            with self.assertRaisesRegex(ValueError, "missing documented severity for #5a"):
                runner.canonical_severities(skill)

    def test_load_cases_keeps_strict_unknown_and_wrong_severity_validation(self):
        runner = load_comparator().RUNNER
        path = ROOT / "scripts/evals/reviewer-holdout.json"
        original = path.read_bytes()
        data, cases = runner.load_cases(path)
        self.assertTrue(any(label["pattern_id"] == "#5a"
                            for case in cases for label in case["labels"]))
        for change, message in (({"pattern_id": "#999"}, "unknown pattern_id"),
                                ({"severity": "P2"}, "severity")):
            mutated = copy.deepcopy(data)
            label = next(label for case in mutated["cases"] for label in case["labels"]
                         if label["pattern_id"] == "#5a")
            label.update(change)
            with patch.object(runner, "load_strict", return_value=mutated):
                with self.assertRaisesRegex(ValueError, message):
                    runner.load_cases(path)
        self.assertEqual(path.read_bytes(), original)

    def test_disclosure_cache_is_content_exact_and_bounded(self):
        runner = load_comparator().RUNNER
        normalize = runner.normalize_disclosure_text
        normalize.cache_clear()
        self.assertEqual(normalize("ＦＯＯ_Bar-123!"), "foo bar 123 ")
        self.assertEqual(normalize("ＦＯＯ_Bar-123!"), "foo bar 123 ")
        self.assertEqual(normalize.cache_info().hits, 1)
        self.assertEqual(normalize.cache_info().currsize, 1)
        self.assertEqual(normalize("OTHER"), "other")
        self.assertEqual(normalize.cache_info().currsize, 1)
        before = normalize.cache_info().misses
        self.assertEqual(normalize("ＦＯＯ_Bar-123!"), "foo bar 123 ")
        self.assertEqual(normalize.cache_info().misses, before + 1)
        self.assertEqual(normalize.cache_info().maxsize, 1)

    def test_disclosure_cache_keeps_label_specific_leak_checks(self):
        runner = load_comparator().RUNNER
        first = {"file": "tests/a.spec.ts", "line": 7, "pattern_id": "#22",
                 "severity": "P1", "source_line": "expect(transferBalanceChange);"}
        second = {**first, "file": "tests/b.spec.ts", "line": 9,
                  "source_line": "expect(profileBadgeLabel);"}
        counts = runner.Counter()
        for label in (first, second):
            counts.update(runner.semantic_oracle_words(label["source_line"]))
        content = "Expected finding: transfer balance change"
        runner.normalize_disclosure_text.cache_clear()
        self.assertEqual(runner.answer_leak_description(content, first, counts),
                         "natural-language answer disclosure")
        self.assertIsNone(runner.answer_leak_description(content, second, counts))
        self.assertEqual(runner.normalize_disclosure_text.cache_info().hits, 1)
        changed = "Expected finding: profile badge label"
        self.assertIsNone(runner.answer_leak_description(changed, first, counts))
        self.assertEqual(runner.answer_leak_description(changed, second, counts),
                         "natural-language answer disclosure")
        # Changing file content cannot reuse a prior positive or negative verdict.
        self.assertIsNone(runner.answer_leak_description("ordinary prose", first, counts))
        self.assertEqual(runner.normalize_disclosure_text.cache_info().currsize, 1)

    def test_html_escapes_all_input_surfaces_including_raw_json(self):
        class Tags(HTMLParser):
            def __init__(self):
                super().__init__()
                self.tags = []
                self.values = []

            def handle_starttag(self, tag, attrs):
                self.tags.append((tag, attrs))

            def handle_data(self, value):
                self.values.append(value)

        payload = '</pre><script>alert("x")</script><img src=x onerror="attack()">&'
        data = finite_measurement(fixture())
        for key in ('study_id', 'setting', 'unit_definition', 'positive_definition',
                    'negative_definition', 'ground_truth_method'):
            data[key] = payload
        data['rows'][0].update(system=payload, definition=payload,
                               decision_rule=payload, execution_evidence=payload)
        data['limitations'] = [payload]
        data[payload] = {payload: payload}
        rendered = html_report(data)
        parsed = Tags()
        parsed.feed(rendered)
        self.assertFalse(any(tag in ('script', 'img', 'iframe') for tag, _ in parsed.tags))
        self.assertFalse(any(name.startswith('on') for _, attrs in parsed.tags for name, _ in attrs))
        self.assertNotIn(payload, rendered)
        self.assertIn(payload, ''.join(parsed.values))
        self.assertIn('&lt;/pre&gt;&lt;script&gt;', rendered)

    def test_html_finite_complete_and_missing_decisions(self):
        data = fixture()
        data['systems'][0]['decisions'] = {
            str(i): 'positive' if i % 2 == 0 else 'negative' for i in range(6)}
        rendered = html_report(finite_measurement(data))
        for expected in ('COMPLETE', 'TP: 3', 'TN: 3', 'FP / (FP + TN)',
                         'FP / (TP + FP)', 'ground truth method', 'synthetic test labels',
                         'positive means final reported issue', 'test fixture, no model/tools ran'):
            self.assertIn(expected, rendered)
        self.assertIn('<dt>coverage</dt><dd>1.000</dd>', rendered)
        data['systems'][0]['decisions'] = {'0': 'positive', '1': 'abstain', '2': 'error'}
        rendered = html_report(finite_measurement(data))
        for expected in ('INCOMPLETE', 'TN: 0', '<dt>decided units</dt><dd>1</dd>',
                         '<dt>total units</dt><dd>6</dd>', '<dt>coverage</dt><dd>0.167</dd>',
                         '<dt>abstain count</dt><dd>1</dd>', '<dt>error count</dt><dd>1</dd>',
                         '<dt>missing count</dt><dd>3</dd>'):
            self.assertIn(expected, rendered)
        data['systems'][0]['decisions'] = {}
        rendered = html_report(finite_measurement(data))
        self.assertIn('<td>0</td><td>N/A (unavailable or undefined)</td>', rendered)

    def test_html_open_ended_tn_unknown_and_inconclusive_matrix(self):
        data = finite_measurement(fixture())
        data.update(mode='canonical-holdout', source_status='INCONCLUSIVE',
                    source_status_reasons=['Isolation unproven'], scheduled_runs=3, unscored_runs=1)
        row = {'system': 'full', 'aggregation_unit': 'unique-stable-finding',
               'status': 'FAIL', 'matrix': metrics(2, 1, 1)}
        data['rows'] = [row]
        rendered = html_report(data)
        self.assertIn('TP: 2', rendered)
        self.assertIn('TN: N/A (unavailable or undefined)', rendered)
        self.assertNotIn('TN: 0', rendered)
        self.assertIn('no finite TN universe', rendered)
        self.assertIn('<dt>unresolved counts</dt><dd>N/A', rendered)
        row.update(status='INCONCLUSIVE', matrix=None)
        rendered = html_report(data)
        self.assertIn('TP: N/A (unavailable or undefined)', rendered)
        self.assertIn('No authoritative metric cells', rendered)
        self.assertIn('Isolation unproven', rendered)
        self.assertNotIn('TP: 0', rendered)

    def test_html_precision_and_fpr_use_different_denominators(self):
        data = finite_measurement(fixture())
        data['rows'][0]['matrix'] = metrics(2, 1, 3, 4)
        rendered = html_report(data)
        self.assertIn('TP / (TP + FP)</td><td>3</td><td>0.667</td>', rendered)
        self.assertIn('FP / (FP + TN)</td><td>5</td><td>0.200</td>', rendered)

    def test_html_cli_new_file_and_refuses_overwrite(self):
        with tempfile.TemporaryDirectory() as directory:
            source = Path(directory) / 'decisions.json'
            output = Path(directory) / 'measurement.html'
            original = json.dumps(fixture())
            source.write_text(original)
            command = [sys.executable, str(Path(__file__).with_name('report.py')),
                       '--decisions', str(source), '--format', 'html', '--output', str(output)]
            process = subprocess.run(command, capture_output=True, text=True)
            self.assertEqual(process.returncode, 0, process.stderr)
            rendered = output.read_text()
            self.assertTrue(rendered.startswith('<!doctype html>'))
            self.assertIn('INCOMPLETE', rendered)
            self.assertNotIn('<script', rendered)
            process = subprocess.run(command, capture_output=True, text=True)
            self.assertEqual(process.returncode, 2)
            self.assertEqual(output.read_text(), rendered)
            self.assertEqual(source.read_text(), original)

    def test_four_cells_and_unresolved_denominators(self):
        row = finite_measurement(fixture())["rows"][0]
        self.assertEqual(row["matrix"], metrics(1, 1, 1, 1))
        self.assertEqual(row["coverage"], 4 / 6)
        self.assertEqual(row["status"], "INCOMPLETE")
        self.assertEqual(row["unresolved_positive_units"], 1)
        self.assertEqual(row["unresolved_negative_units"], 1)

    def test_missing_not_tn_and_zero_denominators_unknown(self):
        data = fixture()
        data["systems"][0]["decisions"] = {}
        row = finite_measurement(data)["rows"][0]
        self.assertEqual(row["matrix"], metrics(0, 0, 0, 0))
        self.assertEqual(len(row["unresolved"]["missing"]), 6)
        self.assertIsNone(row["matrix"]["precision"])
        self.assertIsNone(metrics(0, 0, 0)["tn"])

    def test_same_units_multiple_systems_complete_and_no_mutation(self):
        data = fixture()
        before = copy.deepcopy(data)
        system = copy.deepcopy(data["systems"][0])
        system["id"] = "second"
        system["decisions"] = {str(i): "positive" if i % 2 == 0 else "negative" for i in range(6)}
        data["systems"].append(system)
        rows = finite_measurement(data)["rows"]
        self.assertEqual(rows[1]["matrix"], metrics(3, 0, 0, 3))
        self.assertEqual(rows[1]["status"], "COMPLETE")
        self.assertEqual(data["systems"][0], before["systems"][0])

    def test_reject_invalid_labels_decisions_and_duplicates(self):
        for mutation in (
            lambda d: d["units"].append(d["units"][0]),
            lambda d: d["units"][0].update(positive=1),
            lambda d: d["systems"].append(d["systems"][0]),
            lambda d: d["systems"][0]["decisions"].update(unknown="positive"),
            lambda d: d["systems"][0]["decisions"].update({"0": "maybe"}),
            lambda d: d.update(unit_definition=""),
        ):
            data = fixture()
            mutation(data)
            with self.assertRaises(ValueError):
                finite_measurement(data)

    def test_promptfoo_preserves_incomplete_and_detects_tampering(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "measurement.json"
            result = finite_measurement(fixture())
            path.write_text(json.dumps(result))
            view = config(path)
            request = json.loads(view["tests"][0]["vars"]["request"])
            projection = project(request)
            self.assertEqual(projection["row"], result["rows"][0])
            self.assertEqual(projection["row"]["status"], "INCOMPLETE")
            self.assertEqual(projection["model_calls_by_provider"], 0)
            command = [sys.executable, str(Path(__file__).with_name("promptfoo.py")),
                       "provider", json.dumps(request), "{}", "{}"]
            process = subprocess.run(command, capture_output=True, text=True)
            self.assertEqual(process.returncode, 0, process.stderr)
            self.assertEqual(json.loads(process.stdout), projection)
            path.write_text("{}")
            with self.assertRaisesRegex(ValueError, "digest"):
                project(request)

    def test_cli_refuses_overwrite_and_keeps_input(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "decisions.json"
            original = json.dumps(fixture())
            path.write_text(original)
            command = [sys.executable, str(Path(__file__).with_name("report.py")),
                       "--decisions", str(path), "--output", str(path)]
            process = subprocess.run(command, capture_output=True, text=True)
            self.assertEqual(process.returncode, 2)
            self.assertEqual(path.read_text(), original)
            data = finite_measurement(fixture())
            self.assertIn("INCOMPLETE", markdown(data))
            self.assertIn('"error"', markdown(data))

    def test_real_holdout_rescoring_rejects_tampering_and_preserves_inconclusive(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            fake = root / "fake-runner"
            fake.write_text('#!/bin/sh\ncat >/dev/null\nprintf \'%s\\n\' \'{"findings":[]}\'\n')
            fake.chmod(0o700)
            wrapper = root / "wrapper"
            wrapper.write_text('#!/bin/sh\nexec "$@"\n')
            wrapper.chmod(0o700)
            path = root / "source.json"
            process = subprocess.run([
                sys.executable, str(ROOT / "scripts/evals/run-reviewer-holdout.py"),
                "--runner", str(fake), "--isolation-wrapper", str(wrapper),
                "--model", "synthetic-no-model", "--repetitions", "3", "--report-only",
                "--output", str(path)], cwd=ROOT, capture_output=True, text=True, timeout=60)
            self.assertEqual(process.returncode, 2, process.stderr)
            cases = ROOT / "scripts/evals/reviewer-holdout.json"
            protocol = ROOT / "scripts/evals/reviewer-validation-protocol.json"
            result = holdout_measurement(path, cases, protocol)
            self.assertEqual(result["source_status"], "INCONCLUSIVE")
            self.assertTrue(all(row["matrix"] is None for row in result["rows"]))
            self.assertTrue(result["source_status_reasons"])
            self.assertFalse(result["release_eligible"])
            original = path.read_text()
            data = json.loads(original)
            data["summary"]["tp"] += 1
            path.write_text(json.dumps(data))
            with self.assertRaisesRegex(ValueError, "recomputed"):
                holdout_measurement(path, cases, protocol)
            data = json.loads(original)
            data["runs"].pop()
            path.write_text(json.dumps(data))
            with self.assertRaises(ValueError):
                holdout_measurement(path, cases, protocol)


if __name__ == "__main__":
    unittest.main()
