#!/usr/bin/env python3
"""Offline environment diagnostic contracts. Apache-2.0."""
import importlib.util
from pathlib import Path
import subprocess
import sys
import unittest

PATH = Path(__file__).resolve().parents[1] / "evals/generator-environment-probe.py"
spec = importlib.util.spec_from_file_location("environment_probe", PATH)
probe = importlib.util.module_from_spec(spec)
spec.loader.exec_module(probe)


def checks():
    return {
        "pre_start": {"exit": 7},
        "default_cli": {"exit": 1, "stderr": "Chromium distribution 'chrome' is not found"},
        "explicit_chromium": {"exit": 0},
        "owned_app_ready": {"ready": True},
        "duplicate_app": {"exit": 1, "stderr": "EADDRINUSE"},
        "test_with_external_owner": {"exit": 1, "stdout": "URL is already used"},
        "test_after_owned_cleanup": {"exit": 0, "stdout": "3 passed (1.2s)"},
    }


class ProbeTests(unittest.TestCase):
    def test_expected_failures_and_safe_setup_pass(self):
        self.assertEqual(probe.classify(checks())["status"], "PASS")

    def test_generic_failures_do_not_prove_controls(self):
        for name in ("default_cli", "duplicate_app", "test_with_external_owner"):
            case = checks()
            case[name] = {"exit": 1, "stderr": "unrelated error"}
            self.assertEqual(probe.classify(case)["status"], "INCONCLUSIVE", name)

    def test_zero_exit_alone_does_not_prove_three_passes(self):
        for text in ("0 passed", "13 passed"):
            case = checks()
            case["test_after_owned_cleanup"] = {"exit": 0, "stdout": text}
            self.assertEqual(probe.classify(case)["status"], "INCONCLUSIVE")

    def test_safe_browser_failure_is_not_a_pass(self):
        case = checks()
        case["explicit_chromium"]["exit"] = 1
        self.assertEqual(probe.classify(case)["status"], "INCONCLUSIVE")

    def test_no_mount_credentials_or_download(self):
        cmd = probe.docker_command("/usr/bin/docker", "colima", "owned")
        self.assertIn("--pull=never", cmd)
        self.assertEqual(cmd[cmd.index("--network") + 1], "none")
        self.assertNotIn("--mount", cmd)
        self.assertNotIn("--privileged", cmd)
        self.assertNotIn("auth.json", " ".join(cmd))
        self.assertIn(probe.IMAGE, cmd)

    def test_relative_docker_rejected(self):
        with self.assertRaises(ValueError):
            probe.docker_command("docker", "colima", "owned")

    def test_payload_is_exact_selected_fixture_without_source_edits(self):
        payload, digests = probe.fixture_payload()
        compile(payload, "probe-container", "exec")
        self.assertEqual(set(digests), {"app.mjs", "playwright.config.mjs", "package.json", "tests/smoke.spec.mjs"})
        self.assertIn("__PORT__", (probe.CASE / "app.mjs").read_text())
        self.assertNotIn("pkill", payload)

    def test_execution_opt_in(self):
        result = subprocess.run([sys.executable, str(PATH)], capture_output=True, text=True)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("requires --allow-browser", result.stderr)


if __name__ == "__main__":
    unittest.main()
