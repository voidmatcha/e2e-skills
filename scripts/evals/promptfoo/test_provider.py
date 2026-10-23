#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Guard against promoting a partial verdict or silently changing evidence."""

import hashlib
import json
from pathlib import Path
import tempfile
import unittest

from provider import project


class ProjectionTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.path = Path(self.directory.name) / "report.json"
        self.report = {"status": "INCONCLUSIVE", "complete": False,
                       "status_reasons": ["partial case scope"],
                       "runs": [{"case": "one", "score": {"tp": 1, "fp": 0},
                                 "error": "original error", "output": "original text"}]}

    def request(self):
        data = json.dumps(self.report).encode()
        self.path.write_bytes(data)
        return {"report": str(self.path), "sha256": hashlib.sha256(data).hexdigest(), "case": "one"}

    def test_preserves_failure_and_inconclusive_verdicts_and_entire_cell(self):
        for status in ("INCONCLUSIVE", "FAIL", "PASS"):
            self.report["status"] = status
            result = project(self.request())
            self.assertEqual(result["source_status"], status)
            self.assertEqual(result["cell"], self.report["runs"][0])
            self.assertEqual(result["source_complete"], False)
            self.assertEqual(result["source_status_reasons"], self.report["status_reasons"])
            self.assertEqual(result["model_calls_by_provider"], 0)

    def test_changed_report_rejected(self):
        request = self.request()
        self.path.write_text('{}')
        with self.assertRaisesRegex(ValueError, "digest"):
            project(request)

    def test_wrong_case_rejected(self):
        request = self.request()
        request["case"] = "other"
        with self.assertRaisesRegex(ValueError, "identity"):
            project(request)

    def test_zero_or_multiple_cells_rejected(self):
        for runs in ([], self.report["runs"] * 2):
            self.report["runs"] = runs
            with self.assertRaisesRegex(ValueError, "one recorded"):
                project(self.request())

    def test_unknown_verdict_rejected(self):
        self.report["status"] = "ERROR"
        with self.assertRaisesRegex(ValueError, "verdict"):
            project(self.request())


if __name__ == "__main__":
    unittest.main()
