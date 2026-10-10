#!/usr/bin/env python3
"""Replay archived v8 decision and guard evidence bindings. Apache-2.0."""
import hashlib
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
REPORTS = ROOT / "benchmarks/generator-skill-effect-v8/reports"


def read(name):
    return json.loads((REPORTS / name).read_text())


class EvidenceTests(unittest.TestCase):
    def test_archived_matrix_bindings_and_replay(self):
        report, scores, result = (read(name) for name in ("final.json", "scores.json", "results.json"))
        for name, key in (("final.json", "report_sha256"), ("scores.json", "scores_sha256")):
            self.assertEqual(hashlib.sha256((REPORTS / name).read_bytes()).hexdigest(), result[key])
        self.assertEqual(len(report["runs"]), 216)
        self.assertEqual(len(scores["scores"]), 216)
        for row in report["runs"]:
            for name in row["tests_files"]:
                self.assertTrue((REPORTS / "final-artifacts" / row["call_id"] / name).is_file())
        with tempfile.TemporaryDirectory(prefix="gse8-replay-") as directory:
            output = Path(directory) / "replay.json"
            command = [sys.executable, str(ROOT / "scripts/evals/run-generator-skill-effect-v8.py"),
                       "analyze", str(REPORTS / "scores.json"), "--output", str(output)]
            replay = subprocess.run(command, cwd=ROOT, capture_output=True, text=True, timeout=60)
            self.assertEqual(replay.returncode, 0, replay.stderr)
            self.assertEqual(json.loads(output.read_text()), result)

    def test_post_hoc_audit_cannot_hide_retry_or_unknown_indicators(self):
        report, audit = read("final.json"), read("transcript-audit.json")
        self.assertEqual(audit["report_sha256"], hashlib.sha256((REPORTS / "final.json").read_bytes()).hexdigest())
        self.assertEqual(audit["attempts"], sum(len(row["attempts"]) for row in report["runs"]))
        self.assertEqual(audit["attempts"], 217)
        self.assertEqual(audit["infrastructure_error_attempts"], 1)
        self.assertEqual(len(audit["transcripts"]), 217)
        self.assertEqual(audit["arms"]["full-fixed"]["spawn_agent_events"]["calls"], 108)
        self.assertEqual(audit["arms"]["full-fixed"]["invalid_json_lines"]["events"], 2)
        self.assertTrue(any("do not prove" in note for note in audit["limits"]))


if __name__ == "__main__":
    unittest.main()
