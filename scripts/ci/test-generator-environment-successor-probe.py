#!/usr/bin/env python3
"""Offline guards for the model-free successor environment probe. Apache-2.0."""
import importlib.util
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[2]
spec = importlib.util.spec_from_file_location("successor_probe", ROOT / "scripts/evals/generator-environment-successor-probe.py")
probe = importlib.util.module_from_spec(spec)
spec.loader.exec_module(probe)


def passing():
    return {
        "cli_help": {"exit": 0, "stdout": "--browser"},
        "owned_app_ready": {"ready": True},
        "pre_start_health": {"exit": 7},
        "explicit_cli": {"exit": 0, "stdout": "Page URL: about:blank"},
        "browser_identity": {"exit": 0, "stdout": "HeadlessChrome"},
        "guard_fetch": {"exit": 0},
        "guard_requests": {"exit": 0, "stdout": "http://127.0.0.1:9/ net::ERR_BLOCKED_BY_CLIENT"},
        "goto": {"exit": 0, "stdout": "Page URL: http://127.0.0.1:43819/"},
        "snapshot": {"exit": 0, "stdout": "Snapshot"},
        "cli_close": {"exit": 0},
        "owned_app_stopped": {"stopped": True},
        "post_cleanup_health": {"exit": 7},
        "test_after_owned_cleanup": {"exit": 0, "stdout": "3 passed (1s)"},
    }


class Contracts(unittest.TestCase):
    def test_passing_and_each_missing_step(self):
        self.assertEqual(probe.classify(passing())["status"], "PASS")
        for key in passing():
            checks = passing()
            checks.pop(key)
            self.assertEqual(probe.classify(checks)["status"], "INCONCLUSIVE", key)

    def test_failed_browser_or_wrong_count_never_pass(self):
        for value in ({"exit": 1, "stdout": "chromium"}, {"exit": 0, "stdout": "chrome"}):
            checks = passing()
            checks["explicit_cli"] = value
            self.assertEqual(probe.classify(checks)["status"], "INCONCLUSIVE")
        for output in ("13 passed", "0 passed", "3 failed"):
            checks = passing()
            checks["test_after_owned_cleanup"]["stdout"] = output
            self.assertEqual(probe.classify(checks)["status"], "INCONCLUSIVE")

    def test_immutable_container_bounds(self):
        argv = probe.base.docker_command("/usr/local/bin/docker", "colima", "owned-probe")
        for value in ("--pull=never", "--read-only", "--cap-drop", "ALL", "none", "1000:1000", probe.base.IMAGE):
            self.assertIn(value, argv)
        self.assertNotIn("--volume", argv)
        self.assertNotIn("--mount", argv)
        self.assertNotIn("host", argv)
        self.assertNotIn("--privileged", argv)

    def test_connection_error_does_not_prove_guard(self):
        for output in ("http://127.0.0.1:9/ net::ERR_CONNECTION_REFUSED", "http://127.0.0.1:9/ net::ERR_CONNECTION_REFUSED\nhttp://other/ net::ERR_BLOCKED_BY_CLIENT"):
            checks = passing()
            checks["guard_requests"]["stdout"] = output
            self.assertEqual(probe.classify(checks)["status"], "INCONCLUSIVE")
        for key in ("guard_fetch", "guard_requests"):
            checks = passing()
            checks[key]["exit"] = 1
            self.assertEqual(probe.classify(checks)["status"], "INCONCLUSIVE")

    def test_payload_preserves_fixture_and_lifecycle(self):
        payload, hashes = probe.fixture_payload()
        self.assertEqual(len(hashes), 4)
        self.assertNotIn("__FILES__", payload)
        self.assertIn('"--browser", "chromium"', payload)
        self.assertIn('stop(app)', payload)
        self.assertNotIn("killall", payload)
        self.assertNotIn("pkill", payload)
        self.assertNotIn("install", payload)


if __name__ == "__main__":
    unittest.main()
