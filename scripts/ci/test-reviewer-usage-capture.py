#!/usr/bin/env python3
"""Validate opt-in token-usage capture in the reviewer holdout runner.

Every runner here is a stub shell script that prints a realistic Claude JSON
envelope, a Codex JSONL event stream, or plain text. No model is called.
"""

from __future__ import annotations

import argparse
import copy
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest import mock


ROOT = Path(__file__).resolve().parents[2]
RUNNER_PATH = ROOT / "scripts/evals/run-reviewer-holdout.py"
COMPARATOR_PATH = ROOT / "scripts/evals/compare-reviewer-holdouts.py"
V10_CASES_PATH = ROOT / "scripts/evals/reviewer-holdout-v10.json"
V12_PROTOCOL_PATH = ROOT / "scripts/evals/reviewer-validation-protocol-v12.json"
V13_PROTOCOL_PATH = ROOT / "scripts/evals/reviewer-validation-protocol-v13.json"
CI_LOCAL_PATH = ROOT / "scripts/ci/ci-local.sh"
CONTRIBUTING_PATH = ROOT / "CONTRIBUTING.md"
CHANGELOG_PATH = ROOT / "CHANGELOG.md"
EXPECTED_V12_PROTOCOL_SHA256 = "ec42df85e7161ca96a807cbd0079eb9c406b926ae0c40bb4214f2b88280a5d20"
STUB_CASE = "v10-pw-01"
FAKE_CLAUDE_TOKEN = "stub-oauth-token-not-a-credential"
# The labeled #4f P0 finding of v10-pw-01, as the model would report it.
ANSWER = json.dumps(
    {
        "findings": [
            {
                "pattern_id": "#4f",
                "severity": "P0",
                "file": "tests/recipe-box.spec.ts",
                "line": 10,
            }
        ]
    }
)
CLAUDE_USAGE = {
    "input_tokens": 12,
    "cache_creation_input_tokens": 3461,
    "cache_read_input_tokens": 14200,
    "output_tokens": 187,
    "server_tool_use": {"web_search_requests": 0, "web_fetch_requests": 0},
    "service_tier": "standard",
}
CODEX_USAGE = {
    "input_tokens": 24310,
    "cached_input_tokens": 3072,
    "output_tokens": 912,
    "reasoning_output_tokens": 704,
}

# Frozen text-mode commands every protocol without the opt-in runs today.
CODEX_TEXT_COMMAND = [
    "exec", "--ephemeral", "--ignore-user-config", "--ignore-rules",
    "--strict-config", "--skip-git-repo-check", "--sandbox", "read-only",
    "--disable", "shell_tool", "--disable", "multi_agent",
    "--disable", "image_generation", "--disable", "apps",
    "-c", "tools.web_search=false",
    "-c", "shell_environment_policy.inherit='none'",
    "--model", "gpt-6-sol", "-",
]
CLAUDE_OFF_TEXT_COMMAND = [
    "-p", "--safe-mode", "--setting-sources", "", "--strict-mcp-config",
    "--no-session-persistence", "--tools", "", "--model", "claude-sonnet-5",
]
CLAUDE_PLAN_TEXT_COMMAND = [
    "-p", "--safe-mode", "--setting-sources", "", "--strict-mcp-config",
    "--no-session-persistence", "--tools", "", "--permission-mode", "plan",
    "--model", "claude-opus-5",
]

# Records its argv and stdin, then replays a canned response and exit status.
STUB_TEMPLATE = """#!/bin/sh
: > '{argv}'
for arg in "$@"; do printf '%s\\n' "$arg" >> '{argv}'; done
/bin/cat > '{stdin}'
/bin/cat '{response}'
exit "$(/bin/cat '{status}')"
"""


def read_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def load_module(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"cannot load {path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def claude_envelope(answer: str, **overrides) -> str:
    envelope = {
        "type": "result",
        "subtype": "success",
        "is_error": False,
        "duration_ms": 8123,
        "duration_api_ms": 7990,
        "num_turns": 1,
        "result": answer,
        "stop_reason": "end_turn",
        "session_id": "00000000-0000-4000-8000-000000000000",
        "total_cost_usd": 0.0421,
        "usage": CLAUDE_USAGE,
        "modelUsage": {
            "claude-sonnet-5": {
                "inputTokens": 12,
                "outputTokens": 187,
                "cacheReadInputTokens": 14200,
                "cacheCreationInputTokens": 3461,
                "costUSD": 0.0421,
            }
        },
        "permission_denials": [],
        "uuid": "00000000-0000-4000-8000-000000000001",
    }
    envelope.update(overrides)
    return json.dumps(envelope)


def codex_events(answer: str, *, extra_item: dict | None = None) -> str:
    events = [
        {"type": "thread.started", "thread_id": "0199a000-0000-7000-8000-000000000000"},
        {"type": "turn.started"},
        {"type": "item.completed", "item": {"id": "item_0", "type": "reasoning", "text": "**Reviewing the spec**"}},
    ]
    if extra_item is not None:
        events.append({"type": "item.completed", "item": extra_item})
    events.extend([
        {"type": "item.completed", "item": {"id": "item_1", "type": "agent_message", "text": answer}},
        {"type": "turn.completed", "usage": CODEX_USAGE},
    ])
    return "".join(json.dumps(event) + "\n" for event in events)


class UsageCaptureTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.runner = load_module("reviewer_usage_capture_runner", RUNNER_PATH)
        cls.comparator = load_module("reviewer_usage_capture_comparator", COMPARATOR_PATH)
        cls.v12 = read_json(V12_PROTOCOL_PATH)
        cls.v13 = read_json(V13_PROTOCOL_PATH)
        _, cases = cls.runner.load_cases(V10_CASES_PATH)
        cls.case = next(case for case in cases if case["id"] == STUB_CASE)
        cls.skill_sha256 = cls.runner.skill_digest(cls.runner.DEFAULT_SKILL_DIR)

    # Stub plumbing ---------------------------------------------------------

    def make_stub(self, temp: Path, response: str, status: int = 0) -> dict:
        paths = {name: temp / name for name in ("argv", "stdin", "response", "status")}
        paths["response"].write_text(response, encoding="utf-8")
        paths["status"].write_text(str(status), encoding="utf-8")
        stub = temp / "stub-runner"
        stub.write_text(
            STUB_TEMPLATE.format(**{name: path for name, path in paths.items()}),
            encoding="utf-8",
        )
        stub.chmod(0o755)
        paths["stub"] = stub
        return paths

    def argv(self, paths: dict) -> list[str]:
        return paths["argv"].read_text(encoding="utf-8").split("\n")[:-1]

    def attempt(
        self, runner: str, response: str, *, capture_usage: bool,
        status: int = 0, model: str | None = None,
        permission_mode: str = "off",
    ) -> tuple[dict, str | None, list[str], str]:
        """Run execute_scheduled_attempt against a stub; return record and I/O."""
        model = model or {"claude": "claude-sonnet-5", "codex": "gpt-6-sol"}[runner]
        with tempfile.TemporaryDirectory() as temp:
            temp_path = Path(temp)
            paths = self.make_stub(temp_path, response, status)
            codex_home = temp_path / "codex-home"
            codex_home.mkdir()
            args = argparse.Namespace(
                runner=runner, arm="full", timeout=20, model=model,
                reasoning_effort=None,
            )
            credentials = (
                {"CLAUDE_CODE_OAUTH_TOKEN": FAKE_CLAUDE_TOKEN}
                if runner == "claude"
                else {}
            )
            with (
                mock.patch.object(
                    self.runner, "inherited_runner_credentials",
                    return_value=credentials,
                ),
                mock.patch.object(
                    self.runner, "stage_codex_auth", return_value=codex_home,
                ),
            ):
                record, reason = self.runner.execute_scheduled_attempt(
                    self.case,
                    {"ordinal": 1, "case": STUB_CASE, "repetition": 1},
                    V10_CASES_PATH,
                    self.runner.DEFAULT_SKILL_DIR,
                    self.skill_sha256,
                    args,
                    [],
                    str(paths["stub"]),
                    permission_mode,
                    True,
                    True,
                    capture_stderr=True,
                    **({"capture_usage": True} if capture_usage else {}),
                )
            return (
                record,
                reason,
                self.argv(paths),
                paths["stdin"].read_text(encoding="utf-8"),
            )

    def assert_same_scoring(self, text_record: dict, usage_record: dict) -> None:
        stripped = {
            key: value for key, value in usage_record.items()
            if key not in {"usage", "duration_ms"}
        }
        expected = {
            key: value for key, value in text_record.items() if key != "duration_ms"
        }
        self.assertEqual(expected, stripped)

    # Claude ----------------------------------------------------------------

    def test_claude_usage_is_recorded_and_the_answer_scored_identically(self) -> None:
        text, text_reason, text_argv, text_stdin = self.attempt(
            "claude", ANSWER, capture_usage=False
        )
        usage, usage_reason, usage_argv, usage_stdin = self.attempt(
            "claude", claude_envelope(ANSWER), capture_usage=True
        )
        self.assertNotIn("usage", text)
        self.assertEqual(CLAUDE_OFF_TEXT_COMMAND, text_argv)
        self.assertEqual([*CLAUDE_OFF_TEXT_COMMAND, "--output-format", "json"], usage_argv)
        self.assertEqual(text_stdin, usage_stdin)
        self.assertIsNone(text["error"])
        self.assertEqual(1, text["score"]["tp"])
        self.assert_same_scoring(text, usage)
        self.assertEqual(ANSWER, usage["output"])
        self.assertIsNone(text_reason)
        self.assertIsNone(usage_reason)
        self.assertEqual(
            {
                "source": "claude-json-envelope",
                "input_tokens": 12,
                "cached_input_tokens": 14200,
                "cache_write_tokens": 3461,
                "output_tokens": 187,
                "reasoning_output_tokens": None,
            },
            usage["usage"],
        )
        self.runner.validate_usage_record(usage["usage"], "claude")
        # The comparator re-parses the stored output; it must be the answer.
        self.assertEqual(usage["findings"], self.runner.parse_findings(usage["output"]))

    def test_claude_answer_is_judged_like_text_output(self) -> None:
        # A malformed answer inside a valid envelope is the same retryable
        # malformed_json_output as malformed text output, and keeps its usage.
        for answer in ('{"findings":[', ANSWER + "\nDone.", '```json\n{"findings":[]}\n```'):
            with self.subTest(answer):
                text, text_reason, _, _ = self.attempt("claude", answer, capture_usage=False)
                usage, usage_reason, _, _ = self.attempt(
                    "claude", claude_envelope(answer), capture_usage=True
                )
                self.assertTrue(text["error"].startswith(self.runner.STRICT_JSON_FAILURE_PREFIX))
                self.assert_same_scoring(text, usage)
                self.assertEqual("malformed_json_output", text_reason)
                self.assertEqual(text_reason, usage_reason)
                self.assertEqual(12, usage["usage"]["input_tokens"])

    def test_malformed_claude_envelope_is_unscoreable(self) -> None:
        bad_envelopes = {
            "not json": "Here are the findings: " + ANSWER,
            "truncated": claude_envelope(ANSWER)[:-5],
            "two objects": claude_envelope(ANSWER) + "\n" + claude_envelope(ANSWER),
            "text answer only": ANSWER,
            "array": json.dumps([json.loads(claude_envelope(ANSWER))]),
            "error subtype": claude_envelope(ANSWER, subtype="error_max_turns"),
            "is_error": claude_envelope(ANSWER, is_error=True),
            "missing result": json.dumps({
                key: value for key, value in json.loads(claude_envelope(ANSWER)).items()
                if key != "result"
            }),
            "non-string result": claude_envelope(ANSWER, result={"findings": []}),
            "missing usage": claude_envelope(ANSWER, usage=None),
            "negative tokens": claude_envelope(
                ANSWER, usage={**CLAUDE_USAGE, "output_tokens": -1}
            ),
            "boolean tokens": claude_envelope(
                ANSWER, usage={**CLAUDE_USAGE, "input_tokens": True}
            ),
            "missing cache field": claude_envelope(
                ANSWER,
                usage={
                    key: value for key, value in CLAUDE_USAGE.items()
                    if key != "cache_read_input_tokens"
                },
            ),
        }
        for name, response in bad_envelopes.items():
            with self.subTest(name):
                record, reason, _, _ = self.attempt("claude", response, capture_usage=True)
                self.assertIsNone(record["score"])
                self.assertEqual([], record["findings"])
                self.assertTrue(
                    record["error"].startswith(
                        self.runner.MALFORMED_CLAUDE_ENVELOPE_PREFIX
                    ),
                    record["error"],
                )
                self.assertIsNone(record["usage"])
                self.assertIsNone(reason)

    def test_claude_nonzero_exit_keeps_usage_limit_retry(self) -> None:
        response = claude_envelope(
            "You've hit your usage limit. Try again later.",
            subtype="success", is_error=True,
        )
        record, reason, _, _ = self.attempt(
            "claude", response, capture_usage=True, status=1
        )
        self.assertEqual("runner exited 1", record["error"])
        self.assertIsNone(record["usage"])
        self.assertEqual("runner_nonzero_exit_with_usage_limit_text", reason)

    # Codex -----------------------------------------------------------------

    def test_codex_usage_is_recorded_and_the_answer_scored_identically(self) -> None:
        text, _, text_argv, text_stdin = self.attempt("codex", ANSWER, capture_usage=False)
        usage, reason, usage_argv, usage_stdin = self.attempt(
            "codex", codex_events(ANSWER), capture_usage=True
        )
        self.assertNotIn("usage", text)
        self.assertEqual(CODEX_TEXT_COMMAND, text_argv)
        self.assertEqual(
            [CODEX_TEXT_COMMAND[0], "--json", *CODEX_TEXT_COMMAND[1:]], usage_argv
        )
        self.assertEqual(text_stdin, usage_stdin)
        self.assertIsNone(text["error"])
        self.assert_same_scoring(text, usage)
        self.assertIsNone(reason)
        self.assertEqual(
            {
                "source": "codex-json-events",
                "input_tokens": 24310,
                "cached_input_tokens": 3072,
                "cache_write_tokens": None,
                "output_tokens": 912,
                "reasoning_output_tokens": 704,
            },
            usage["usage"],
        )

    def test_malformed_codex_stream_is_unscoreable(self) -> None:
        streams = {
            "plain text": (ANSWER, None),
            "no turn.completed": (
                "".join(codex_events(ANSWER).splitlines(keepends=True)[:-1]),
                None,
            ),
            "tool item": (
                codex_events(
                    ANSWER,
                    extra_item={"id": "item_9", "type": "command_execution", "command": "ls"},
                ),
                CODEX_USAGE["input_tokens"],
            ),
        }
        for name, (response, input_tokens) in streams.items():
            with self.subTest(name):
                record, reason, _, _ = self.attempt("codex", response, capture_usage=True)
                self.assertIsNone(record["score"])
                self.assertIsNotNone(record["error"])
                self.assertIsNone(reason)
                if input_tokens is None:
                    self.assertIsNone(record["usage"])
                else:
                    # The turn completed and spent tokens; the answer is refused.
                    self.assertEqual(input_tokens, record["usage"]["input_tokens"])

    # Opt-out protocols -----------------------------------------------------

    def test_opt_out_commands_are_unchanged(self) -> None:
        command, stdin = self.runner.runner_invocation(
            "codex", "codex", "PROMPT", "gpt-6-sol"
        )
        self.assertEqual(["codex", *CODEX_TEXT_COMMAND], command)
        self.assertEqual("PROMPT", stdin)
        command, _ = self.runner.runner_invocation(
            "claude", "claude", "PROMPT", "claude-sonnet-5", None, "off"
        )
        self.assertEqual(["claude", *CLAUDE_OFF_TEXT_COMMAND], command)
        command, _ = self.runner.runner_invocation(
            "claude", "claude", "PROMPT", "claude-opus-5"
        )
        self.assertEqual(["claude", *CLAUDE_PLAN_TEXT_COMMAND], command)
        # Only v13-v21 opt in; v2-v12 have no usage-capture policy.
        self.assertEqual(
            {"reviewer-holdout-v13", "reviewer-holdout-v14", "reviewer-holdout-v15",
             "reviewer-holdout-v16", "reviewer-holdout-v17", "reviewer-holdout-v18", "reviewer-holdout-v19", "reviewer-holdout-v20", "reviewer-holdout-v21"},
            self.runner.USAGE_CAPTURE_PROTOCOL_IDS,
        )
        for protocol_id in sorted(self.runner.SUPPORTED_PROTOCOL_IDS):
            expected = (
                self.v13["usage_capture"]
                if protocol_id
                in {"reviewer-holdout-v13", "reviewer-holdout-v14", "reviewer-holdout-v15",
                    "reviewer-holdout-v16", "reviewer-holdout-v17", "reviewer-holdout-v18", "reviewer-holdout-v19", "reviewer-holdout-v20", "reviewer-holdout-v21"}
                else None
            )
            self.assertEqual(
                expected,
                self.runner.usage_capture_policy(
                    {"protocol_id": protocol_id, "usage_capture": {"enabled": True}}
                ),
                protocol_id,
            )
        self.assertEqual(
            EXPECTED_V12_PROTOCOL_SHA256,
            hashlib.sha256(V12_PROTOCOL_PATH.read_bytes()).hexdigest(),
        )
        with tempfile.TemporaryDirectory() as temp:
            data = copy.deepcopy(self.v12)
            data["usage_capture"] = {"enabled": True}
            path = Path(temp) / "v12.json"
            path.write_text(json.dumps(data), encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "unknown="):
                self.runner.load_protocol(path)

    def run_protocol_stub(self, temp: Path, protocol: Path) -> dict:
        paths = self.make_stub(temp, ANSWER)
        wrapper = temp / "isolation-wrapper"
        wrapper.write_text('#!/bin/sh\nexec "$@"\n', encoding="utf-8")
        wrapper.chmod(0o755)
        output = temp / "report.json"
        result = subprocess.run(
            [
                "python3", str(RUNNER_PATH),
                "--cases", str(V10_CASES_PATH),
                "--protocol", str(protocol),
                "--case", STUB_CASE,
                "--runner", str(paths["stub"]),
                "--isolation-wrapper", str(wrapper),
                "--repetitions", "1",
                "--timeout", "20",
                "--output", str(output),
            ],
            cwd=ROOT,
            env={**os.environ, "LC_ALL": "C", "LANG": "C"},
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            check=False,
        )
        self.assertTrue(output.is_file(), result.stdout)
        # A custom runner receives exactly its path; no output-format flag.
        self.assertEqual([], self.argv(paths))
        return read_json(output)

    def test_v12_report_schema_is_unchanged(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            report = self.run_protocol_stub(Path(temp), V12_PROTOCOL_PATH)
        self.assertNotIn("usage_capture", report)
        self.assertNotIn("usage_summary", report)
        self.assertLessEqual(
            set(report),
            self.comparator.REPORT_KEYS
            | self.comparator.REPORT_OPTIONAL_KEYS - {"usage_capture", "usage_summary"},
        )
        run = report["runs"][0]
        self.assertEqual(self.comparator.RETRY_RUN_KEYS, set(run))
        self.assertEqual(
            [self.comparator.ATTEMPT_KEYS], [set(attempt) for attempt in run["attempts"]]
        )
        self.comparator.validate_usage_records(report, None)
        for mutate in (
            lambda data: data.update({"usage_capture": {"enabled": True}}),
            lambda data: data.update({"usage_summary": {}}),
            lambda data: data["runs"][0].update({"usage": None}),
            lambda data: data["runs"][0]["attempts"][0].update({"usage": None}),
        ):
            data = copy.deepcopy(report)
            mutate(data)
            with self.assertRaisesRegex(ValueError, "no usage capture"):
                self.comparator.validate_usage_records(data, None)

    def test_v13_report_carries_usage_fields(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            report = self.run_protocol_stub(Path(temp), V13_PROTOCOL_PATH)
            path = Path(temp) / "report.json"
            path.write_text(json.dumps(report), encoding="utf-8")
            self.comparator.load_report(path)
        self.assertEqual({"enabled": True}, report["usage_capture"])
        self.assertIsNone(report["runs"][0]["usage"])
        self.assertEqual(self.runner.usage_summary(report["runs"]), report["usage_summary"])
        self.comparator.validate_usage_records(report, report["usage_capture"])
        self.comparator.validate_retry_records(report, self.v13["infrastructure_retry"])

    # Report totals ---------------------------------------------------------

    def usage(self, source: str, **tokens) -> dict:
        fields = self.runner.USAGE_SOURCE_FIELDS[source]
        return {
            "source": source,
            **{
                field: (None if raw is None else tokens.get(field, 0))
                for field, raw in fields.items()
            },
        }

    def test_usage_summary_totals_and_means(self) -> None:
        first = self.usage("claude-json-envelope", input_tokens=10, cached_input_tokens=100,
                           cache_write_tokens=50, output_tokens=20)
        retried = self.usage("claude-json-envelope", input_tokens=4, cached_input_tokens=0,
                             cache_write_tokens=0, output_tokens=6)
        second = self.usage("claude-json-envelope", input_tokens=30, cached_input_tokens=300,
                            cache_write_tokens=0, output_tokens=40)
        runs = [
            {"usage": first, "attempts": [{"usage": first}]},
            {"usage": second, "attempts": [{"usage": retried}, {"usage": second}]},
            {"usage": None, "attempts": [{"usage": None}]},
        ]
        summary = self.runner.usage_summary(runs)
        self.assertEqual("one-report-one-arm", summary["unit"])
        final = summary["final_attempts"]
        self.assertEqual(
            (3, 2, 1, ["claude-json-envelope"]),
            (final["records"], final["records_with_usage"],
             final["records_without_usage"], final["sources"]),
        )
        self.assertEqual(
            {"input_tokens": 40, "cached_input_tokens": 400, "cache_write_tokens": 50,
             "output_tokens": 60, "reasoning_output_tokens": None},
            final["totals"],
        )
        self.assertEqual(
            {"input_tokens": 20.0, "cached_input_tokens": 200.0, "cache_write_tokens": 25.0,
             "output_tokens": 30.0, "reasoning_output_tokens": None},
            final["means_per_record_with_usage"],
        )
        every = summary["all_attempts"]
        self.assertEqual((4, 3), (every["records"], every["records_with_usage"]))
        self.assertEqual(44, every["totals"]["input_tokens"])
        self.assertEqual(66, every["totals"]["output_tokens"])
        # Runs without attempt records count once each.
        no_retry = self.runner.usage_summary([{"usage": first}, {"usage": None}])
        self.assertEqual(no_retry["final_attempts"], no_retry["all_attempts"])
        codex = self.usage("codex-json-events", input_tokens=100, cached_input_tokens=10,
                           output_tokens=30, reasoning_output_tokens=20)
        codex_summary = self.runner.usage_summary([{"usage": codex}])["final_attempts"]
        self.assertEqual(20, codex_summary["totals"]["reasoning_output_tokens"])
        self.assertIsNone(codex_summary["totals"]["cache_write_tokens"])

    # Comparator ------------------------------------------------------------

    def test_comparator_surfaces_each_arm_usage_summary(self) -> None:
        usage = self.usage("claude-json-envelope", input_tokens=5, cached_input_tokens=7,
                           cache_write_tokens=1, output_tokens=9)
        reports = [
            {
                "prompt_profile": profile,
                "runner": "claude",
                "model": "claude-sonnet-5",
                "runs": [{"usage": usage, "attempts": [{"usage": usage}]}] * count,
            }
            for profile, count in (("full", 1), ("catalog-only", 2), ("no-skill", 3))
        ]
        sections = self.comparator.per_report_sections(self.v13, reports)
        self.assertEqual({"infrastructure_retry", "usage_capture"}, set(sections))
        self.assertEqual({"enabled": True}, sections["usage_capture"]["policy"])
        rows = sections["usage_capture"]["reports"]
        self.assertEqual(
            ["full", "catalog-only", "no-skill"], [row["prompt_profile"] for row in rows]
        )
        self.assertEqual(
            [5, 10, 15],
            [row["usage_summary"]["final_attempts"]["totals"]["input_tokens"] for row in rows],
        )
        # A protocol without the opt-in gets no usage section and needs no usage.
        v12_sections = self.comparator.per_report_sections(
            self.v12, [{**report, "runs": []} for report in reports]
        )
        self.assertEqual({"infrastructure_retry"}, set(v12_sections))
        v10_sections = self.comparator.per_report_sections(
            {"protocol_id": "reviewer-holdout-v10"}, reports
        )
        self.assertEqual({}, v10_sections)

    def test_comparator_validates_usage_records(self) -> None:
        usage = self.usage("claude-json-envelope", input_tokens=5, cached_input_tokens=7,
                           cache_write_tokens=1, output_tokens=9)
        policy = self.v13["usage_capture"]
        report = {
            "usage_capture": policy,
            "usage_summary": {},
            "runs": [{"usage": usage, "attempts": [{"usage": None}, {"usage": usage}]}],
        }
        self.comparator.validate_usage_records(report, policy)
        failures = {
            "policy mismatch": (lambda d: d.update({"usage_capture": {"enabled": False}}),
                                "does not match the protocol"),
            "missing summary": (lambda d: d.pop("usage_summary"), "missing its usage_summary"),
            "missing run usage": (lambda d: d["runs"][0].pop("usage"), "missing its usage"),
            "missing attempt usage": (lambda d: d["runs"][0]["attempts"][0].pop("usage"),
                                      "missing its usage"),
            "final mismatch": (lambda d: d["runs"][0].update({"usage": None}),
                               "final attempt"),
            "bad record": (lambda d: d["runs"][0].update({"usage": {"source": "x"}}),
                           "usage record keys differ"),
            "unreported field": (
                lambda d: d["runs"][0].update(
                    {"usage": {**usage, "reasoning_output_tokens": 3}}
                ),
                "not reported by",
            ),
        }
        for name, (mutate, message) in failures.items():
            data = copy.deepcopy(report)
            mutate(data)
            with self.subTest(name), self.assertRaisesRegex(ValueError, message):
                self.comparator.validate_usage_records(data, policy)

    # Registration ----------------------------------------------------------

    def test_suite_is_registered(self) -> None:
        for path in (CI_LOCAL_PATH, CONTRIBUTING_PATH):
            self.assertTrue(
                "scripts/ci/test-reviewer-usage-capture.py"
                in path.read_text(encoding="utf-8"),
                path,
            )
        changelog = CHANGELOG_PATH.read_text(encoding="utf-8")
        release_section = changelog.split("## [2.0.0]", 1)[1].split("\n## [", 1)[0]
        added = release_section.split("### Added", 1)[1].split("\n### ", 1)[0]
        self.assertIn("usage_capture", added)


if __name__ == "__main__":
    unittest.main(verbosity=2)
