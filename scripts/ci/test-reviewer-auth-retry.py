#!/usr/bin/env python3
"""Offline auth-retry opt-in checks using local stub runners."""

from __future__ import annotations

import argparse
import copy
import importlib.util
import json
from pathlib import Path
import sys
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts/ci/lib"))
from frozen_reviewer_inputs import stage_v17_formal_model  # noqa: E402

RUNNER_PATH = ROOT / "scripts/evals/run-reviewer-holdout.py"
spec = importlib.util.spec_from_file_location("auth_retry_runner", RUNNER_PATH)
assert spec and spec.loader
runner = importlib.util.module_from_spec(spec)
spec.loader.exec_module(runner)
# v17's frozen protocol pins the Lean model of its own revision; stage that copy
# so the frozen-policy loop below loads v17 without requiring the live model to
# stay byte-identical to that release.
_V17_LEAN_TEMP = tempfile.TemporaryDirectory(prefix="auth-retry-v17-lean-")
runner.V17_FORMAL_MODEL = stage_v17_formal_model(Path(_V17_LEAN_TEMP.name))
comparator_path = ROOT / "scripts/evals/compare-reviewer-holdouts.py"
comparator_spec = importlib.util.spec_from_file_location("auth_retry_comparator", comparator_path)
assert comparator_spec and comparator_spec.loader
comparator = importlib.util.module_from_spec(comparator_spec)
comparator_spec.loader.exec_module(comparator)
AUTH_POLICY = {
    **runner.EXPECTED_INFRASTRUCTURE_RETRY,
    "retryable": [*runner.INFRASTRUCTURE_RETRY_REASONS, runner.AUTH_RETRY_REASON],
}
TOKEN = "test-only-secret-token-should-never-appear"


class AuthRetryTest(unittest.TestCase):
    def test_frozen_policies_reject_auth_reason(self) -> None:
        for version in range(11, 18):
            path = ROOT / f"scripts/evals/reviewer-validation-protocol-v{version}.json"
            protocol = runner.load_protocol(path)
            self.assertEqual(runner.EXPECTED_INFRASTRUCTURE_RETRY,
                             protocol["infrastructure_retry"])
            self.assertNotIn("runner_auth_error", protocol["infrastructure_retry"]["retryable"])
            changed = copy.deepcopy(protocol)
            changed["infrastructure_retry"]["retryable"].append("runner_auth_error")
            with tempfile.TemporaryDirectory() as temp:
                trial = Path(temp) / "protocol.json"
                trial.write_text(json.dumps(changed))
                with self.assertRaises(ValueError):
                    runner.load_protocol(trial)
            self.assertIsNone(runner.retryable_failure_reason(
                1, 1, "runner exited 1", '{"api_error_status":401}', "",
                allow_auth_error="runner_auth_error" in protocol["infrastructure_retry"]["retryable"]))

    def test_auth_classification_is_opt_in_and_conservative(self) -> None:
        reason = runner.retryable_failure_reason
        for status in (401, 403):
            self.assertEqual("runner_auth_error", reason(
                1, 1, "runner exited 1", json.dumps({"api_error_status": status}),
                "", allow_auth_error=True))
        self.assertEqual("runner_auth_error", reason(
            1, 1, "runner exited 1",
            '{"api_error_status":401}\n[stderr omitted sha256=abc bytes=3]',
            "", allow_auth_error=True))
        for text in ("Failed to authenticate", "OAuth access token has been revoked",
                     "invalid x-api-key", "401 Unauthorized", "not logged in"):
            self.assertEqual("runner_auth_error", reason(
                1, 1, "runner exited 1", "", text, allow_auth_error=True))
        for args in ((1, 1, "runner exited 1", "internal error", ""),
                     (0, 0, None, '{"api_error_status":401}', ""),
                     (1, 126, "runner output contained credential-shaped data and was redacted",
                      '{"api_error_status":401}', "")):
            self.assertIsNone(reason(*args, allow_auth_error=True))
        runner.validate_future_infrastructure_retry(AUTH_POLICY, Path("future.json"))

    def test_native_codex_429_capacity_envelope_and_exhausted_stop(self) -> None:
        message = "exceeded retry limit, last status: 429 Too Many Requests"
        reason = runner.retryable_failure_reason
        expected = "runner_nonzero_exit_with_usage_limit_text"
        events = [
            {"type": "thread.started", "thread_id": "test-thread"},
            {"type": "turn.started"},
            {"type": "error", "message": message},
            {"type": "turn.failed", "error": {"message": message}},
        ]
        output = "\n".join(json.dumps(event) for event in events)
        for value in (output, json.dumps(events[2]), json.dumps(events[3])):
            self.assertEqual(expected, reason(1, 1, "runner exited 1", value, ""))
        record = {"score": None, "attempts": [{"reason": expected}, {"reason": expected}]}
        self.assertTrue(runner.stop_v22_after_exhausted_identity_failure("reviewer-holdout-v23", record))
        record["score"] = {"tp": 0, "fp": 0, "fn": 0}
        self.assertFalse(runner.stop_v22_after_exhausted_identity_failure("reviewer-holdout-v23", record))
        negatives = (
            (0, 0, None, output, ""),
            (1, 1, "staged workspace mutated during runner execution", output, ""),
            (1, 126, "runner output contained credential-shaped data and was redacted", output, ""),
            (1, 1, "runner exited 1", message, ""),
            (1, 1, "runner exited 1", "", message),
            (1, 1, "runner exited 1", json.dumps({"message": message}), ""),
            (1, 1, "runner exited 1", json.dumps({"type": "item.completed", "item": {"type": "agent_message", "text": message}}), ""),
            (1, 1, "runner exited 1", output + "\nnot-json", ""),
            (1, 1, "runner exited 1", output.replace("429", "500"), ""),
        )
        for args in negatives:
            with self.subTest(args=args):
                self.assertIsNone(reason(*args))

    def test_stub_auth_failure_retries_once_and_scores_without_secret(self) -> None:
        cases_path = ROOT / "scripts/evals/reviewer-holdout-v10.json"
        _, cases = runner.load_cases(cases_path)
        case = next(case for case in cases if case["id"] == "v10-pw-01")
        skill = runner.DEFAULT_SKILL_DIR
        with tempfile.TemporaryDirectory() as temp:
            base = Path(temp)
            count = base / "count"
            stub = base / "stub"
            stub.write_text(
                "#!/bin/sh\n/bin/cat >/dev/null\n"
                f"n=$(/bin/cat '{count}' 2>/dev/null || echo 0)\n"
                f"n=$((n + 1))\necho \"$n\" > '{count}'\n"
                "if [ \"$n\" -eq 1 ]; then\n"
                f"  printf '%s' '{{\"api_error_status\":401,\"result\":\"Failed to authenticate {TOKEN}\"}}'\n"
                f"  echo '{TOKEN}' >&2\n  exit 1\nfi\n"
                "printf '%s' '{\"findings\":[]}'\n"
            )
            stub.chmod(0o755)
            args = argparse.Namespace(arm="no-skill", runner=str(stub), timeout=5,
                                      model=None, reasoning_effort=None)
            scheduled = {"ordinal": 1, "repetition": 1}
            attempts = []
            for number in (1, 2):
                record, reason = runner.execute_scheduled_attempt(
                    case, scheduled, cases_path, skill, runner.skill_digest(skill),
                    args, [], str(stub), "off", True, True,
                    capture_stderr=True, allow_auth_error=True,
                    credential_snapshot={},
                )
                attempts.append({"attempt": number, "reason": reason,
                                 "exit_code": record["exit_code"], "error": record["error"]})
                if number == 1:
                    self.assertEqual("[authentication error output omitted]", record["output"])
                if reason not in AUTH_POLICY["retryable"]:
                    break
            record["attempts"] = attempts
            report = {"runs": [record], "infrastructure_retry": AUTH_POLICY,
                      "infrastructure_retry_summary": runner.infrastructure_retry_summary(
                          [record], tuple(AUTH_POLICY["retryable"]))}
            self.assertEqual("2", count.read_text().strip())
            self.assertEqual("runner_auth_error", attempts[0]["reason"])
            self.assertIsNone(attempts[1]["reason"])
            self.assertIsNotNone(record["score"])
            self.assertEqual(1, report["infrastructure_retry_summary"]["retries_by_reason"]["runner_auth_error"])
            comparator.validate_retry_records(report, AUTH_POLICY)
            self.assertNotIn(TOKEN, json.dumps(report))

            exhausted_stub = base / "always-auth"
            exhausted_stub.write_text(
                "#!/bin/sh\n/bin/cat >/dev/null\n"
                f"printf '%s' '{{\"api_error_status\":403,\"result\":\"{TOKEN}\"}}'\n"
                "exit 1\n"
            )
            exhausted_stub.chmod(0o755)
            args.runner = str(exhausted_stub)
            exhausted_attempts = []
            for number in (1, 2):
                failed, reason = runner.execute_scheduled_attempt(
                    case, scheduled, cases_path, skill, runner.skill_digest(skill),
                    args, [], str(exhausted_stub), "off", True, True,
                    capture_stderr=True, allow_auth_error=True,
                    credential_snapshot={},
                )
                exhausted_attempts.append({"attempt": number, "reason": reason,
                                           "exit_code": failed["exit_code"],
                                           "error": failed["error"]})
            failed["attempts"] = exhausted_attempts
            exhausted_report = {"runs": [failed], "infrastructure_retry": AUTH_POLICY,
                                "infrastructure_retry_summary": runner.infrastructure_retry_summary(
                                    [failed], tuple(AUTH_POLICY["retryable"]))}
            comparator.validate_retry_records(exhausted_report, AUTH_POLICY)
            self.assertEqual("[authentication error output omitted]", failed["output"])
            self.assertNotIn(TOKEN, json.dumps(exhausted_report))


if __name__ == "__main__":
    unittest.main()
