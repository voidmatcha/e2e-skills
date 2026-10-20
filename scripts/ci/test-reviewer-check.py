#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Focused negative controls for the optional fixed fault pilot boundary."""

import contextlib
import hashlib
import importlib.util
import io
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch


ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "skills/e2e-reviewer/scripts/check.py"
SPEC = importlib.util.spec_from_file_location("reviewer_check", SCRIPT)
assert SPEC and SPEC.loader
CHECK = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(CHECK)


class FakeAdapter:
    ADAPTER_ID = "notepad-playwright-v1"
    PROMISE_ID = "note-content-persists-after-save"
    PROMISE_TEXT = "A saved note persists after reload."
    TEST_SELECTORS = ("weak", "strong")
    runs = 0

    @staticmethod
    def descriptor():
        return {"adapter": FakeAdapter.ADAPTER_ID, "promise_id": FakeAdapter.PROMISE_ID,
                "argv": ["fixed", "--pull=never"], "test": ["weak", "strong"]}

    @staticmethod
    def run(output, selector):
        FakeAdapter.runs += 1
        return {"status": "DETECTED", "test": selector}


class CheckBoundary(unittest.TestCase):
    def setUp(self):
        FakeAdapter.runs = 0
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.source = self.root / "requirement.txt"
        self.source.write_text("A saved note persists after reload.\n")
        self.promise = self.root / "promise.json"
        self.write_promise()
        self.out = self.root / "new-artifacts"
        self.base = ["--adapter", FakeAdapter.ADAPTER_ID, "--promise-file", str(self.promise),
                     "--test", "strong", "--output-dir", str(self.out), "--trust-checkout"]

    def write_promise(self, **changes):
        value = {"id": FakeAdapter.PROMISE_ID, "text": "A saved note persists after reload.",
                 "source": str(self.source), "source_sha256": hashlib.sha256(self.source.read_bytes()).hexdigest()}
        value.update(changes)
        self.promise.write_text(json.dumps(value))

    def invoke(self, extras=()):
        stdout, stderr = io.StringIO(), io.StringIO()
        with patch.object(CHECK, "load_adapter", return_value=(FakeAdapter, SCRIPT)):
            with contextlib.redirect_stdout(stdout), contextlib.redirect_stderr(stderr):
                code = CHECK.main([*self.base, *extras])
        return code, json.loads(stdout.getvalue() or stderr.getvalue())

    def test_preview_and_exact_approval(self):
        code, preview = self.invoke()
        self.assertEqual((code, preview["status"], FakeAdapter.runs), (0, "PREVIEW", 0))
        code, denied = self.invoke(["--execute", "--trust-checkout", "--approve-adapter-sha256", "0" * 64])
        self.assertEqual((code, denied["status"], FakeAdapter.runs), (2, "CANNOT_VERIFY", 0))
        self.base.remove("--trust-checkout")
        code, denied = self.invoke(["--execute", "--approve-adapter-sha256", preview["approval_sha256"]])
        self.assertEqual((code, denied["status"], FakeAdapter.runs), (2, "CANNOT_VERIFY", 0))
        self.base.append("--trust-checkout")
        code, result = self.invoke(["--execute", "--trust-checkout", "--approve-adapter-sha256", preview["approval_sha256"]])
        self.assertEqual((code, result["status"], FakeAdapter.runs), (0, "DETECTED", 1))
        self.assertEqual(result["adapter"], FakeAdapter.ADAPTER_ID)
        self.assertTrue(Path(result["invocation_evidence"]).is_file())

    def test_missing_or_invented_promise_never_runs(self):
        self.source.write_text("A saved note persists after reload.\nUnrelated project fact.\n")
        self.write_promise(text="Unrelated project fact.")
        code, result = self.invoke()
        self.assertEqual((code, result["status"], FakeAdapter.runs), (2, "CANNOT_VERIFY", 0))
        self.write_promise(text="Invented behavior")
        code, result = self.invoke(["--execute", "--trust-checkout"])
        self.assertEqual((code, result["status"], FakeAdapter.runs), (2, "CANNOT_VERIFY", 0))
        self.promise.unlink()
        code, result = self.invoke()
        self.assertEqual((code, result["status"]), (2, "CANNOT_VERIFY"))

    def test_source_drift_and_unregistered_test(self):
        self.source.write_text("Requirement changed.\n")
        code, result = self.invoke()
        self.assertEqual((code, result["status"]), (2, "CANNOT_VERIFY"))
        self.write_promise()
        self.base[self.base.index("strong")] = "other"
        code, result = self.invoke()
        self.assertEqual((code, result["status"], FakeAdapter.runs), (2, "CANNOT_VERIFY", 0))

    def test_existing_output_and_checkout_output_denied(self):
        self.out.mkdir()
        code, result = self.invoke()
        self.assertEqual((code, result["status"]), (2, "CANNOT_VERIFY"))
        self.out = ROOT / "must-never-write-here"
        self.base[self.base.index("--output-dir") + 1] = str(self.out)
        code, result = self.invoke()
        self.assertEqual((code, result["status"], FakeAdapter.runs), (2, "CANNOT_VERIFY", 0))

    def test_both_registered_descriptors_preview_without_execution(self):
        for name in CHECK.ADAPTERS:
            with self.subTest(name=name):
                adapter, path = CHECK.load_adapter(name)
                promise = {"id": adapter.PROMISE_ID, "text": "source-backed", "source_sha256": "0" * 64}
                report = CHECK.preview(adapter, path, promise, "strong")
                self.assertEqual(report["status"], "PREVIEW")
                self.assertEqual(report["adapter"], name)
                self.assertEqual(len(report["approval_sha256"]), 64)


class NotepadV2Admission(unittest.TestCase):
    """Exercise the real adapters after a simulated fixed runner, without Docker."""
    def setUp(self):
        # Real adapters require durable external output; a fresh HOME has no cache yet.
        cache = Path.home() / ".cache"
        cache.mkdir(mode=0o700, parents=True, exist_ok=True)
        self.tmp = tempfile.TemporaryDirectory(prefix="reviewer-check-", dir=cache.resolve())
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.v1, _ = CHECK.load_adapter("notepad-playwright-v1")
        self.v2, _ = CHECK.load_adapter("notepad-playwright-v2")
        self.contradict = False
        self.commands = []

    def runner(self, argv, **kwargs):
        import subprocess
        self.commands.append(argv)
        self.assertEqual(argv[:2], [self.v1.sys.executable, str(self.v1.RUNNER)])
        self.assertEqual(argv[-1], "--execute")
        output = Path(argv[argv.index("--output") + 1]); output.mkdir()
        strength = argv[argv.index("--strength") + 1]
        cells = []
        for name in ["weak-normal-canary"] + [f"{strength}-{phase}" for phase in ("normal", "fault", "recovery")]:
            failed = name == "strong-fault"
            attempt = {"status": "failed" if failed else "passed", "retry": 0, "errors": []}
            if failed:
                error = {"message": "designated persistence assertion", "location": {"line": 42}}
                attempt.update(error=error, errors=[dict(error)])
            test = {"expectedStatus": "passed", "status": "unexpected" if failed else "expected", "results": [attempt]}
            spec = {"ok": not failed, "tests": [test]}
            if failed and self.contradict:
                spec["ok"] = True; test.update(expectedStatus="failed", status="expected")
            report = {"errors": [], "stats": {"expected": int(not failed), "unexpected": int(failed), "skipped": 0, "flaky": 0},
                      "config": {"workers": 1, "projects": [{"retries": 0}]}, "suites": [{"specs": [spec]}]}
            target = output / name / "test-out/report.json"; target.parent.mkdir(parents=True)
            target.write_text(json.dumps(report))
            cells.append({"cell": name, "native": attempt["status"], "hits": int(name.endswith("-fault"))})
        proof = {"status": "DETECTED" if strength == "strong" else "SURVIVED", "selected_test": strength,
                 "canary": 1, "unique_faults": 1, "cells": cells, "model_calls": 0}
        (output / "results.json").write_text(json.dumps(proof))
        manifest = {str(path.relative_to(output)): self.v1.digest(path) for path in output.rglob("*") if path.is_file()}
        (output / "artifacts-sha256.json").write_text(json.dumps(manifest))
        return subprocess.CompletedProcess(argv, 0, "", "")

    @staticmethod
    def legacy_cell(root, name):
        return next(row for row in json.loads((root / "results.json").read_text())["cells"] if row["cell"] == name)

    def test_v1_reproduces_contradiction_v2_returns_cannot_verify(self):
        self.contradict = True
        with patch.object(self.v1.subprocess, "run", self.runner), patch.object(self.v2.STRICT.legacy, "validate_cell", self.legacy_cell):
            old = self.v1.run(self.root / "old", "strong")
            fixed = self.v2.run(self.root / "fixed", "strong")
        self.assertEqual(old["status"], "DETECTED")
        self.assertEqual(fixed["status"], "CANNOT_VERIFY")
        self.assertIn("native outcome consistency", fixed["reason"])
        self.assertNotIn("fault_hit", fixed)
        self.assertEqual(len(self.commands), 2)

    def test_original_weak_and_strong_outcomes_preserved(self):
        with patch.object(self.v1.subprocess, "run", self.runner), patch.object(self.v2.STRICT.legacy, "validate_cell", self.legacy_cell):
            for strength, expected in [("weak", "SURVIVED"), ("strong", "DETECTED")]:
                with self.subTest(strength=strength):
                    result = self.v2.run(self.root / strength, strength)
                    self.assertEqual(result["status"], expected)
                    self.assertEqual(result["adapter"], "notepad-playwright-v2")
                    self.assertEqual(result["native_consistency"]["validated_cells"], 4)

    def test_v2_check_execution_exports_cannot_verify_for_contradiction(self):
        self.contradict = True
        source = self.root / "requirement.txt"; source.write_text(self.v2.PROMISE_TEXT)
        promise = self.root / "promise.json"
        promise.write_text(json.dumps({"id": self.v2.PROMISE_ID, "text": self.v2.PROMISE_TEXT,
                                       "source": str(source), "source_sha256": CHECK.sha256(source)}))
        base = ["--adapter", self.v2.ADAPTER_ID, "--promise-file", str(promise), "--test", "strong",
                "--output-dir", str(self.root / "cli-output"), "--trust-checkout"]
        adapter_path = CHECK.ADAPTERS[self.v2.ADAPTER_ID]
        def invoke(extras):
            stdout = io.StringIO(); stderr = io.StringIO()
            with contextlib.redirect_stdout(stdout), contextlib.redirect_stderr(stderr):
                code = CHECK.main(base + extras)
            return code, json.loads(stdout.getvalue() or stderr.getvalue())
        with patch.object(CHECK, "load_adapter", return_value=(self.v2, adapter_path)), patch.object(self.v1.subprocess, "run", self.runner), patch.object(self.v2.STRICT.legacy, "validate_cell", self.legacy_cell):
            code, preview = invoke([])
            self.assertEqual((code, preview["status"], self.commands), (0, "PREVIEW", []))
            code, result = invoke(["--execute", "--approve-adapter-sha256", preview["approval_sha256"]])
        self.assertEqual((code, result["status"]), (2, "CANNOT_VERIFY"))
        envelope = json.loads(Path(result["invocation_evidence"]).read_text())
        self.assertEqual(envelope["result"]["adapter"], "notepad-playwright-v2")
        self.assertEqual(envelope["status"], "CANNOT_VERIFY")

    def test_v2_unregistered_selector_never_launches(self):
        with patch.object(self.v1.subprocess, "run", self.runner):
            result = self.v2.run(self.root / "arbitrary", "arbitrary-command")
        self.assertEqual(result["status"], "CANNOT_VERIFY")
        self.assertEqual(self.commands, [])

    def test_v2_adds_strict_digest_without_changing_frozen_descriptor(self):
        descriptor = self.v2.descriptor()
        self.assertEqual(descriptor["adapter"], "notepad-playwright-v2")
        self.assertEqual(descriptor["argv"], self.v1.descriptor()["argv"])
        self.assertEqual(descriptor["files_sha256"]["verify_notepad_v2.py"], CHECK.sha256(self.v2.STRICT_PATH))
        self.assertIn("notepad_adapter_v1.py", descriptor["files_sha256"])
        self.assertEqual(self.v1.descriptor()["adapter"], "notepad-playwright-v1")


if __name__ == "__main__":
    unittest.main()
