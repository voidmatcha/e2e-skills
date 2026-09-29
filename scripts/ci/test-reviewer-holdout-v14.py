#!/usr/bin/env python3
"""Validate the preregistered v14 protocol: v13 plus single-JSON-fence output normalization."""

from __future__ import annotations

import copy
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import tempfile
import unittest
from unittest import mock


ROOT = Path(__file__).resolve().parents[2]
V5_CASES_PATH = ROOT / "scripts/evals/reviewer-holdout-v5.json"
V8_CASES_PATH = ROOT / "scripts/evals/reviewer-holdout-v8.json"
V9_CASES_PATH = ROOT / "scripts/evals/reviewer-holdout-v9.json"
V10_CASES_PATH = ROOT / "scripts/evals/reviewer-holdout-v10.json"
V8_PROTOCOL_PATH = ROOT / "scripts/evals/reviewer-validation-protocol-v8.json"
V9_PROTOCOL_PATH = ROOT / "scripts/evals/reviewer-validation-protocol-v9.json"
V10_PROTOCOL_PATH = ROOT / "scripts/evals/reviewer-validation-protocol-v10.json"
V11_PROTOCOL_PATH = ROOT / "scripts/evals/reviewer-validation-protocol-v11.json"
V12_PROTOCOL_PATH = ROOT / "scripts/evals/reviewer-validation-protocol-v12.json"
V13_PROTOCOL_PATH = ROOT / "scripts/evals/reviewer-validation-protocol-v13.json"
V14_PROTOCOL_PATH = ROOT / "scripts/evals/reviewer-validation-protocol-v14.json"
V10_FILES_PATH = ROOT / "scripts/evals/files/holdout-v10"
RUNNER_PATH = ROOT / "scripts/evals/run-reviewer-holdout.py"
COMPARATOR_PATH = ROOT / "scripts/evals/compare-reviewer-holdouts.py"
V5_TEST_PATH = ROOT / "scripts/ci/test-reviewer-holdout-v5.py"
README_PATH = ROOT / "benchmarks/reviewer-holdout-v14/README.md"
BENCHMARK_DOC_PATH = ROOT / "docs/ai-reviewer-benchmark.md"
CHANGELOG_PATH = ROOT / "CHANGELOG.md"
CONTRIBUTING_PATH = ROOT / "CONTRIBUTING.md"
CI_LOCAL_PATH = ROOT / "scripts/ci/ci-local.sh"

# v14 reuses the frozen v10 corpus: these are v10's digests, unchanged.
EXPECTED_CASES_FILE_SHA256 = "6db718fe63001f987901a68ee230809c56fda2df5e97d3f0b83ab382b953cc5e"
EXPECTED_CORPUS_SHA256 = "672f99fc323cf72cb9946483b01f7df314ee12000bcc40b5aa3eb1efb2f8cb8d"
EXPECTED_V10_PROTOCOL_SHA256 = "186680ad624f9ae40ff0b652ee4949322fb6ccfac5e5426a4b7c182278f33c39"
EXPECTED_V11_PROTOCOL_SHA256 = "5676b452de7d6fce7ae7292bf21248b2dbeef3eeb493175cf85024299dee1bf1"
EXPECTED_V12_PROTOCOL_SHA256 = "ec42df85e7161ca96a807cbd0079eb9c406b926ae0c40bb4214f2b88280a5d20"
EXPECTED_V13_PROTOCOL_SHA256 = "6803125914bd03ff07e724614636b2e8a040e6a13932f2af6b187a87ed78ff7b"
EXPECTED_PROTOCOL_SHA256 = "c668d7308c4ec841998c26c052a8900a1da99d2057955e79b39d76848a20c679"
PROTOCOL_ID = "reviewer-holdout-v14"
V10_ID = "reviewer-holdout-v10"
V11_ID = "reviewer-holdout-v11"
V12_ID = "reviewer-holdout-v12"
V13_ID = "reviewer-holdout-v13"
V15_ID = "reviewer-holdout-v15"
HOST = {"runner": "claude", "model": "claude-sonnet-5"}
IDENTITY = {"claude": "Claude Code 2.1.281"}
REUSERS = {V11_ID, V12_ID, V13_ID, PROTOCOL_ID, V15_ID}

# v16 carries the same retry policy on the reused v9 corpus.
V16_ID = "reviewer-holdout-v16"
V17_ID = "reviewer-holdout-v17"
V18_ID = "reviewer-holdout-v18"
V19_ID = "reviewer-holdout-v19"
V20_ID = "reviewer-holdout-v20"
V21_ID = "reviewer-holdout-v21"
V9_OWNER_ID = "reviewer-holdout-v9"
V9_OWNER_PROTOCOL_PATH = ROOT / "scripts/evals/reviewer-validation-protocol-v9.json"
STUB_CASE = "v10-pw-01"
STUB_TIMEOUT_SECONDS = 10  # headroom for a loaded machine; the timeout stub sleeps 30 s
EMPTY = '{"findings":[]}'
WRONG = '{"findings":[{"pattern_id":"#9","severity":"P1","file":"tests/unrelated.spec.ts","line":1}]}'

# The v13 stub runner plus fenced answers. It reads the next action from PLAN,
# counts itself in COUNT, and never calls a model.
STUB_TEMPLATE = """#!/bin/sh
/bin/cat >/dev/null
n=$(/bin/cat '{count}' 2>/dev/null || echo 0)
n=$((n + 1))
echo "$n" > '{count}'
action=$(/usr/bin/sed -n "${{n}}p" '{plan}')
case "$action" in
  timeout) /bin/sleep 30 ;;
  ok) printf '%s' '{{"findings":[]}}' ;;
  wrong) printf '%s' '{{"findings":[{{"pattern_id":"#9","severity":"P1","file":"tests/unrelated.spec.ts","line":1}}]}}' ;;
  malformed) printf '%s' '{{"findings":[' ;;
  fenced_json) printf '%s\\n' '```json' '{{"findings":[]}}' '```' ;;
  fenced_bare) printf '%s\\n' '```' '{{"findings":[{{"pattern_id":"#9","severity":"P1","file":"tests/unrelated.spec.ts","line":1}}]}}' '```' ;;
  fenced_prose) printf '%s\\n' 'Here are the findings:' '```json' '{{"findings":[]}}' '```' ;;
  fenced_nonjson) printf '%s\\n' '```json' 'no findings' '```' ;;
  usage_stderr) echo "Error: You've hit your usage limit. Try again later." >&2; exit 1 ;;
  crash) echo "internal failure" >&2; exit 3 ;;
  *) echo "unplanned invocation $n" >&2; exit 9 ;;
esac
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


def fence(body: str, info: str = "json") -> str:
    return f"```{info}\n{body}\n```"


class ReviewerHoldoutV14Test(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.runner = load_module("reviewer_holdout_v14_runner", RUNNER_PATH)
        cls.comparator = load_module("reviewer_holdout_v14_comparator", COMPARATOR_PATH)
        cls.v5_helpers = load_module("reviewer_holdout_v14_v5_helpers", V5_TEST_PATH)
        cls.v8 = read_json(V8_PROTOCOL_PATH)
        cls.v9 = read_json(V9_PROTOCOL_PATH)
        cls.v10 = read_json(V10_PROTOCOL_PATH)
        cls.v13 = read_json(V13_PROTOCOL_PATH)
        cls.v14 = read_json(V14_PROTOCOL_PATH)
        cls.v5_metadata, _ = cls.runner.load_cases(V5_CASES_PATH)
        cls.v8_metadata, _ = cls.runner.load_cases(V8_CASES_PATH)
        cls.v9_metadata, cls.v9_cases = cls.runner.load_cases(V9_CASES_PATH)
        cls.v10_metadata, cls.v10_cases = cls.runner.load_cases(V10_CASES_PATH)

    def load_mutated(self, temp: str, data: dict, name: str = "protocol.json") -> dict:
        path = Path(temp) / name
        path.write_text(json.dumps(data), encoding="utf-8")
        return self.runner.load_protocol(path)

    # Frozen inputs -------------------------------------------------------

    def test_frozen_inputs_and_runner_registration(self) -> None:
        self.assertEqual(
            EXPECTED_CASES_FILE_SHA256,
            hashlib.sha256(V10_CASES_PATH.read_bytes()).hexdigest(),
        )
        self.assertEqual(
            EXPECTED_CORPUS_SHA256,
            self.runner.corpus_digest(V10_CASES_PATH, self.v10_cases),
        )
        self.assertEqual(
            EXPECTED_PROTOCOL_SHA256,
            hashlib.sha256(V14_PROTOCOL_PATH.read_bytes()).hexdigest(),
        )
        # v10-v13 protocols are untouched, v13 included while it runs.
        for path, digest in (
            (V10_PROTOCOL_PATH, EXPECTED_V10_PROTOCOL_SHA256),
            (V11_PROTOCOL_PATH, EXPECTED_V11_PROTOCOL_SHA256),
            (V12_PROTOCOL_PATH, EXPECTED_V12_PROTOCOL_SHA256),
            (V13_PROTOCOL_PATH, EXPECTED_V13_PROTOCOL_SHA256),
        ):
            self.assertEqual(digest, hashlib.sha256(path.read_bytes()).hexdigest(), path)
        self.assertEqual(
            EXPECTED_V13_PROTOCOL_SHA256,
            self.runner.PINNED_LIVE_INPUTS[(V10_CASES_PATH, V13_PROTOCOL_PATH)][
                "protocol_sha256"
            ],
        )
        self.assertEqual(self.v14, self.runner.load_protocol(V14_PROTOCOL_PATH))
        self.assertEqual(V14_PROTOCOL_PATH, self.runner.V14_PROTOCOL)
        self.assertEqual(
            {
                "cases_file_sha256": EXPECTED_CASES_FILE_SHA256,
                "corpus_sha256": EXPECTED_CORPUS_SHA256,
                "protocol_sha256": EXPECTED_PROTOCOL_SHA256,
            },
            self.runner.PINNED_LIVE_INPUTS[(V10_CASES_PATH, V14_PROTOCOL_PATH)],
        )
        self.assertEqual(
            [(V10_CASES_PATH, V14_PROTOCOL_PATH)],
            [key for key in self.runner.PINNED_LIVE_INPUTS if key[1] == V14_PROTOCOL_PATH],
        )
        self.assertEqual(self.v10["corpus"], self.v14["corpus"])
        for id_set in (
            "SUPPORTED_PROTOCOL_IDS",
            "STRICT_MAJORITY_PROTOCOL_IDS",
            "PROMPT_ARM_PROTOCOL_IDS",
            "ARM_COMPARISON_PROTOCOL_IDS",
            "CODEX_ONLY_PROTOCOL_IDS",
            "NUMBERED_SOURCE_PROTOCOL_IDS",
            "REVISED_LABEL_PROTOCOL_IDS",
            "DESIGNED_LABEL_PROTOCOL_IDS",
            "INFRASTRUCTURE_RETRY_PROTOCOL_IDS",
            "USAGE_CAPTURE_PROTOCOL_IDS",
            "OUTPUT_NORMALIZATION_PROTOCOL_IDS",
        ):
            self.assertIn(PROTOCOL_ID, getattr(self.runner, id_set), id_set)
        for id_set in (
            "PROVIDER_BALANCED_PROTOCOL_IDS",
            "FULL_ONLY_PROTOCOL_IDS",
            "SUPERSEDED_PROTOCOL_IDS",
            "HISTORICAL_DIAGNOSTIC_PROTOCOL_IDS",
            "SPECIFICITY_PROTOCOL_IDS",
        ):
            self.assertNotIn(PROTOCOL_ID, getattr(self.runner, id_set), id_set)
        # v14 is the only protocol with output normalization.
        self.assertEqual({PROTOCOL_ID}, self.runner.OUTPUT_NORMALIZATION_PROTOCOL_IDS)
        self.assertEqual(
            {V13_ID, PROTOCOL_ID, V15_ID, V16_ID, V17_ID, V18_ID, V19_ID, V20_ID, V21_ID}, self.runner.USAGE_CAPTURE_PROTOCOL_IDS
        )
        self.assertEqual(REUSERS | {V16_ID, V17_ID, V18_ID, V19_ID, V20_ID, V21_ID}, self.runner.INFRASTRUCTURE_RETRY_PROTOCOL_IDS)
        self.assertEqual(V10_CASES_PATH, self.runner.REVISED_LABEL_CORPORA[PROTOCOL_ID])
        self.assertEqual(
            {**{reuser: V10_ID for reuser in REUSERS}, V16_ID: V9_OWNER_ID, V18_ID: V17_ID, V19_ID: V17_ID},
            self.runner.SHARED_CORPUS_PROTOCOLS,
        )
        self.assertEqual(
            {V9_OWNER_ID: V9_OWNER_PROTOCOL_PATH, V10_ID: V10_PROTOCOL_PATH,
             V17_ID: ROOT / "scripts/evals/reviewer-validation-protocol-v17.json"},
            self.runner.SHARED_CORPUS_OWNER_PROTOCOLS,
        )
        self.assertEqual("minimum", self.runner.FROZEN_EXECUTION_IDENTITY_POLICIES[PROTOCOL_ID])
        self.assertEqual(IDENTITY, self.runner.FROZEN_EXECUTION_IDENTITIES[PROTOCOL_ID])
        self.assertEqual(HOST, self.runner.REVISED_LABEL_HOSTS[PROTOCOL_ID])
        self.assertEqual(
            {V13_ID: "off", PROTOCOL_ID: "off", V15_ID: "off"},
            self.runner.REQUIRED_CLAUDE_PERMISSION_MODES,
        )

    def test_protocol_is_v13_plus_output_normalization(self) -> None:
        v13 = copy.deepcopy(self.v13)
        v14 = copy.deepcopy(self.v14)
        self.assertEqual(PROTOCOL_ID, v14.pop("protocol_id"))
        v13.pop("protocol_id")
        disclosure = v14["schedule"].pop("design_disclosure")
        v13["schedule"].pop("design_disclosure")
        for phrase in (
            "Reviewer holdout v14 is v13 plus one preregistered output-normalization rule",
            "often wrapped its answer in one Markdown code fence",
            "the retry policy re-invoked the call once, and the model fenced its answer again",
            "6 of 150 full-arm calls and 21 of 150 catalog-only calls ended unscoreable",
            "v13 was stopped or finished without a counted result",
            "no v13 skill-lift result is claimed",
            "v13's results are described separately",
            "was fixed in this protocol before any v14 call",
            "exactly one fenced block",
            "optional json info string",
            "the unchanged strict parser",
            "Prose before or after a fence, two fenced blocks, a fence without a "
            "closing line, or a fence around non-JSON is judged by the strict parser "
            "as before",
            "applies identically to every arm (full, catalog-only, and no-skill)",
            "each run records output_normalized",
            "count normalized runs per arm",
            "v13's reports are not rescored",
            "Claude Code 2.1.281 floor",
            "claude_permission_mode off",
            "a scoreable output is never retried",
            "reused unchanged by path and digest",
            "five repetitions",
            "public development evidence",
            "not a fresh-corpus test for the author",
            "those runs do not train models",
        ):
            self.assertIn(phrase, disclosure)
        self.assertNotIn("is being run", disclosure)
        normalization = v14.pop("output_normalization")
        self.assertEqual(self.runner.EXPECTED_OUTPUT_NORMALIZATION, normalization)
        self.assertEqual({"strip_single_json_fence", "contract"}, set(normalization))
        self.assertIs(True, normalization["strip_single_json_fence"])
        # Everything else is v13's byte for byte: host, identity, permission
        # mode, retry policy, usage capture, corpus, arms, thresholds, seed.
        self.assertEqual(v13, v14)
        v13_keys = list(self.v13)
        v13_keys.insert(v13_keys.index("usage_capture") + 1, "output_normalization")
        self.assertEqual(v13_keys, list(self.v14))
        self.assertEqual(
            self.runner.EXPECTED_INFRASTRUCTURE_RETRY, self.v14["infrastructure_retry"]
        )
        self.assertEqual({"enabled": True}, self.v14["usage_capture"])
        self.assertEqual("off", self.v14["execution_identity"]["claude_permission_mode"])
        self.assertEqual(IDENTITY, self.v14["execution_identity"]["expected_cli_versions"])
        self.assertEqual([HOST], self.v14["host_matrix"])
        self.assertEqual(5, self.v14["schedule"]["default_repetitions"])
        self.assertEqual(20260801, self.v14["schedule"]["seed"])

    def test_protocol_validation_pins_v14_fields(self) -> None:
        other_order = [
            {**step, "model": "claude-opus-5"}
            for step in self.v14["arm_comparison"]["execution_order"]
        ]
        mutations = {
            "three repetitions": lambda data: data["schedule"].update(
                {"default_repetitions": 3, "release_repetitions": 3}
            ),
            "scoring drift": lambda data: data["scoring"].update(
                {"label_semantics": "exact"}
            ),
            "continuity claude model": lambda data: data.update(
                {"host_matrix": [{"runner": "claude", "model": "claude-opus-5"}]}
            ),
            "codex host": lambda data: data.update(
                {"host_matrix": [{"runner": "codex", "model": "gpt-6-sol"}]}
            ),
            "execution order model": lambda data: data["arm_comparison"].update(
                {"execution_order": other_order}
            ),
            "older claude floor": lambda data: data["execution_identity"].update(
                {"expected_cli_versions": {"claude": "Claude Code 2.1.239"}}
            ),
            "plan permission mode": lambda data: data["execution_identity"].update(
                {"claude_permission_mode": "plan"}
            ),
            "missing permission mode": lambda data: data["execution_identity"].pop(
                "claude_permission_mode"
            ),
            "exact policy": lambda data: data["execution_identity"].update(
                {"version_policy": "exact"}
            ),
            "missing disclosure": lambda data: data["schedule"].update(
                {"design_disclosure": " "}
            ),
            "missing retry policy": lambda data: data.pop("infrastructure_retry"),
            "three attempts": lambda data: data["infrastructure_retry"].update(
                {"max_attempts_per_call": 3}
            ),
            "missing usage capture": lambda data: data.pop("usage_capture"),
            "usage capture disabled": lambda data: data["usage_capture"].update(
                {"enabled": False}
            ),
            "missing output normalization": lambda data: data.pop("output_normalization"),
            "normalization disabled": lambda data: data["output_normalization"].update(
                {"strip_single_json_fence": False}
            ),
            "normalization integer": lambda data: data["output_normalization"].update(
                {"strip_single_json_fence": 1}
            ),
            "normalization extra key": lambda data: data["output_normalization"].update(
                {"strip_prose": True}
            ),
            "normalization missing contract": lambda data: data[
                "output_normalization"
            ].pop("contract"),
            "normalization contract drift": lambda data: data[
                "output_normalization"
            ].update({"contract": "Recover any JSON found anywhere in the answer."}),
            "normalization not an object": lambda data: data.update(
                {"output_normalization": True}
            ),
            "stricter thresholds": lambda data: data["arm_comparison"]["decision"][
                "thresholds"
            ].update({"stable_f1_delta_min": 0.02}),
            "other seed": lambda data: data["arm_comparison"]["uncertainty"].update(
                {"seed": 1}
            ),
        }
        with tempfile.TemporaryDirectory() as temp:
            for name, mutate in mutations.items():
                data = copy.deepcopy(self.v14)
                mutate(data)
                with self.subTest(name), self.assertRaises(ValueError):
                    self.load_mutated(temp, data)

    def test_output_normalization_is_limited_to_v14(self) -> None:
        self.assertEqual(
            self.v14["output_normalization"],
            self.runner.output_normalization_policy(self.v14),
        )
        for protocol_id in sorted(self.runner.SUPPORTED_PROTOCOL_IDS - {PROTOCOL_ID}):
            self.assertIsNone(
                self.runner.output_normalization_policy(
                    {
                        "protocol_id": protocol_id,
                        "output_normalization": self.v14["output_normalization"],
                    }
                ),
                protocol_id,
            )
        # No earlier protocol may declare the block, v13 included.
        with tempfile.TemporaryDirectory() as temp:
            for name, protocol in (("v13", self.v13), ("v10", self.v10), ("v9", self.v9)):
                data = copy.deepcopy(protocol)
                data["output_normalization"] = copy.deepcopy(
                    self.runner.EXPECTED_OUTPUT_NORMALIZATION
                )
                with self.subTest(name), self.assertRaisesRegex(ValueError, "unknown="):
                    self.load_mutated(temp, data, f"{name}.json")

    # Normalization grammar ---------------------------------------------------

    def test_single_fence_is_accepted_with_or_without_json_info(self) -> None:
        strip = self.runner.strip_single_json_fence
        parse = self.runner.parse_normalized_findings
        wrong = json.loads(WRONG)["findings"]
        for name, answer, expected in (
            ("json info string", fence(EMPTY), []),
            ("bare fence", fence(WRONG, info=""), wrong),
            ("leading and trailing whitespace", f" \n\t\n{fence(EMPTY)}\n\n  ", []),
            ("trailing newline only", fence(WRONG) + "\n", wrong),
            ("multi-line body", fence('{\n  "findings": []\n}'), []),
        ):
            with self.subTest(name):
                self.assertIsNotNone(strip(answer))
                self.assertEqual(expected, parse(answer))
                # The same answer is refused by v13's strict parser.
                with self.assertRaisesRegex(ValueError, "exactly one strict JSON payload"):
                    self.runner.parse_findings(answer)
        self.assertEqual(EMPTY, strip(fence(EMPTY)))
        self.assertEqual(WRONG, strip(f"  {fence(WRONG, info='')}\n"))
        # An unfenced answer is parsed exactly as the strict parser parses it.
        self.assertIsNone(strip(EMPTY))
        self.assertEqual([], parse(EMPTY))
        self.assertEqual(self.runner.parse_findings(WRONG), parse(WRONG))

    def test_every_other_form_goes_to_the_strict_parser_and_fails(self) -> None:
        strip = self.runner.strip_single_json_fence
        parse = self.runner.parse_normalized_findings
        rejected = {
            "prose before the fence": "Here are the findings:\n" + fence(EMPTY),
            "prose after the fence": fence(EMPTY) + "\nNo other issues.",
            "prose on both sides": "Result:\n" + fence(EMPTY) + "\nDone.",
            "two fenced blocks": fence(EMPTY) + "\n" + fence(EMPTY),
            "two blocks back to back": f"```json\n{EMPTY}\n```\n```json\n{EMPTY}\n```",
            "unclosed fence": f"```json\n{EMPTY}",
            "unclosed fence with trailing newline": f"```json\n{EMPTY}\n",
            "closing fence on the body line": f"```json\n{EMPTY}```",
            "opening fence on the body line": f"```json {EMPTY}\n```",
            "fence around non-JSON": fence("no findings"),
            "fence around two payloads": fence(EMPTY + EMPTY),
            "fence around an empty body": "```json\n\n```",
            "other info string": fence(EMPTY, info="javascript"),
            "uppercase info string": fence(EMPTY, info="JSON"),
            "info string with trailing space": f"```json \n{EMPTY}\n```",
            "four backticks": f"````json\n{EMPTY}\n````",
            "tilde fence": f"~~~json\n{EMPTY}\n~~~",
            "CRLF line endings": f"```json\r\n{EMPTY}\r\n```",
            "indented closing fence": f"```json\n{EMPTY}\n  ```",
            "body containing a fence": fence(f"{EMPTY}\n```\n```json\n{EMPTY}"),
        }
        for name, answer in rejected.items():
            with self.subTest(name):
                with self.assertRaises(ValueError):
                    parse(answer)
                with self.assertRaises(ValueError):
                    self.runner.parse_findings(answer)
        # Only the malformed-body fences are unwrapped; the rest are not fences.
        unwrapped = {
            "fence around non-JSON",
            "fence around two payloads",
            "fence around an empty body",
        }
        for name, answer in rejected.items():
            with self.subTest(f"strip {name}"):
                if name in unwrapped:
                    self.assertIsNotNone(strip(answer))
                else:
                    self.assertIsNone(strip(answer))
        # A fenced answer whose body is JSON of the wrong shape is refused by
        # the unchanged findings validator, not repaired.
        with self.assertRaisesRegex(ValueError, "exactly the findings field"):
            parse(fence('{"findings":[],"notes":"x"}'))

    def test_output_normalized_flag_is_derived_from_the_stored_run(self) -> None:
        applied = self.runner.output_normalization_applied
        prefix = self.runner.STRICT_JSON_FAILURE_PREFIX
        self.assertTrue(applied({"exit_code": 0, "error": None, "output": fence(EMPTY)}))
        self.assertFalse(applied({"exit_code": 0, "error": None, "output": EMPTY}))
        # Refused by the strict parser after the fence was removed.
        self.assertTrue(
            applied({"exit_code": 1, "error": f"{prefix}: x", "output": fence("no")})
        )
        # Not a fence: refused by the strict parser untouched.
        self.assertFalse(
            applied({"exit_code": 1, "error": f"{prefix}: x", "output": "x\n" + fence(EMPTY)})
        )
        # A run that was never parsed is never normalized.
        for error in ("timeout", "runner exited 3", "staged workspace mutated during runner execution"):
            self.assertFalse(applied({"exit_code": 1, "error": error, "output": fence(EMPTY)}))

    # Corpus binding --------------------------------------------------------

    def test_corpus_reuse_is_limited_to_the_v10_reusers(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            for corpus in (
                "scripts/evals/reviewer-holdout-v9.json",
                "scripts/evals/reviewer-holdout-v8.json",
                "scripts/evals/reviewer-holdout-v5.json",
            ):
                data = copy.deepcopy(self.v14)
                data["corpus"]["path"] = corpus
                with self.subTest(corpus), self.assertRaisesRegex(
                    ValueError, "must be the v10 corpus"
                ):
                    self.load_mutated(temp, data)
            for key in ("cases_file_sha256", "corpus_sha256"):
                data = copy.deepcopy(self.v14)
                data["corpus"][key] = "0" * 64
                with self.subTest(key), self.assertRaisesRegex(ValueError, "frozen digests"):
                    self.load_mutated(temp, data)
            with mock.patch.dict(
                self.runner.REVISED_LABEL_CORPORA, {"reviewer-holdout-v9": V10_CASES_PATH}
            ):
                data = copy.deepcopy(self.v9)
                data["corpus"] = copy.deepcopy(self.v10["corpus"])
                with self.assertRaisesRegex(ValueError, "may not share its corpus"):
                    self.load_mutated(temp, data, "v9-shared.json")
                with self.assertRaisesRegex(ValueError, "may not share its corpus"):
                    self.runner.load_protocol(V14_PROTOCOL_PATH)
            reusers = dict(self.runner.SHARED_CORPUS_PROTOCOLS)
            reusers.pop(PROTOCOL_ID)
            with mock.patch.object(self.runner, "SHARED_CORPUS_PROTOCOLS", reusers):
                with self.assertRaisesRegex(ValueError, "may not share its corpus"):
                    self.runner.load_protocol(V14_PROTOCOL_PATH)
        for path in (V10_PROTOCOL_PATH, V11_PROTOCOL_PATH, V12_PROTOCOL_PATH, V13_PROTOCOL_PATH):
            self.assertEqual(read_json(path), self.runner.load_protocol(path))

    def test_corpus_and_protocol_pairing(self) -> None:
        for pairing in (
            self.runner.validate_corpus_protocol_pairing,
            self.comparator.RUNNER.validate_corpus_protocol_pairing,
        ):
            pairing(self.v10_metadata, self.v14, EXPECTED_CORPUS_SHA256)
            v9_digest = self.runner.corpus_digest(V9_CASES_PATH, self.v9_cases)
            with self.assertRaisesRegex(ValueError, "corpus digest"):
                pairing(self.v9_metadata, self.v14, v9_digest)
            with self.assertRaisesRegex(ValueError, "corpus digest"):
                pairing(self.v10_metadata, self.v14, "0" * 64)
            with self.assertRaisesRegex(ValueError, "requires a corpus that declares labeling"):
                pairing(self.v8_metadata, self.v14)
            with self.assertRaisesRegex(ValueError, "requires a corpus that declares labeling"):
                pairing(self.v5_metadata, self.v14)

    # Prompt rendering --------------------------------------------------------

    def test_prompts_are_numbered_and_never_leak_labels(self) -> None:
        numbered = PROTOCOL_ID in self.runner.NUMBERED_SOURCE_PROTOCOL_IDS
        self.assertTrue(numbered)
        with tempfile.TemporaryDirectory() as temp:
            for case in self.v10_cases:
                workspace = Path(temp) / case["id"]
                shutil.copytree(self.runner.DEFAULT_SKILL_DIR, workspace / ".skill/e2e-reviewer")
                for source in case["source_files"]:
                    target = workspace / source["path"]
                    target.parent.mkdir(parents=True, exist_ok=True)
                    shutil.copy2(V10_CASES_PATH.parent / source["source"], target)
                for profile in ("full", "catalog-only", "no-skill"):
                    prompt = self.runner.render_prompt(
                        case, workspace, profile, numbered_source_lines=numbered
                    )
                    self.assertIn("Cite that displayed number as the line", prompt)
                    # The prompt still asks for no fences; normalization is
                    # scoring-side only and is never announced to the model.
                    self.assertIn("Do not include prose, Markdown fences", prompt)
                    self.assertNotIn(case["design_note"], prompt)
                    self.assertNotIn(case["id"], prompt)
                    for marker in (
                        "V10-", "holdout-v10", "holdout-v13", "holdout-v14",
                        "infrastructure_retry", "output_normalization",
                        "strip_single_json_fence", "output_normalized",
                        "claude-sonnet-5",
                    ):
                        self.assertNotIn(marker, prompt)
                    for label in case["labels"]:
                        self.assertNotIn(label["reason"], prompt)
        for path in V10_FILES_PATH.rglob("*"):
            if path.is_file():
                text = path.read_text(encoding="utf-8")
                for marker in ("V10-", "fp_guard", "design_note", "holdout"):
                    self.assertNotIn(marker, text, path)

    def test_prompts_and_schedule_match_v13(self) -> None:
        for profile in ("full", "catalog-only", "no-skill"):
            self.assertEqual(
                self.runner.prompt_set_digest(
                    self.v10_cases, EXPECTED_CORPUS_SHA256,
                    self.runner.DEFAULT_SKILL_DIR, profile,
                    numbered_source_lines=V13_ID in self.runner.NUMBERED_SOURCE_PROTOCOL_IDS,
                ),
                self.runner.prompt_set_digest(
                    self.v10_cases, EXPECTED_CORPUS_SHA256,
                    self.runner.DEFAULT_SKILL_DIR, profile,
                    numbered_source_lines=PROTOCOL_ID
                    in self.runner.NUMBERED_SOURCE_PROTOCOL_IDS,
                ),
            )
        v13_schedule = self.runner.build_schedule(
            self.v10_cases, 5, self.v13["schedule"]["seed"]
        )
        v14_schedule = self.runner.build_schedule(
            self.v10_cases, 5, self.v14["schedule"]["seed"]
        )
        self.assertEqual(v13_schedule, v14_schedule)
        self.assertEqual(150, len(v14_schedule))

    # Stub-runner calls -------------------------------------------------------

    def run_stub(self, temp: Path, plan: list[str], protocol_path: Path = V14_PROTOCOL_PATH):
        protocol = read_json(protocol_path)
        count = temp / "count"
        plan_path = temp / "plan"
        plan_path.write_text("\n".join(plan) + "\n", encoding="utf-8")
        stub = temp / "stub-runner"
        stub.write_text(STUB_TEMPLATE.format(count=count, plan=plan_path), encoding="utf-8")
        stub.chmod(0o755)
        wrapper = temp / "isolation-wrapper"
        wrapper.write_text('#!/bin/sh\nexec "$@"\n', encoding="utf-8")
        wrapper.chmod(0o755)
        output = temp / "report.json"
        result = subprocess.run(
            [
                "python3", str(RUNNER_PATH),
                "--cases", str(V10_CASES_PATH),
                "--protocol", str(protocol_path),
                "--case", STUB_CASE,
                "--runner", str(stub),
                "--isolation-wrapper", str(wrapper),
                "--repetitions", "1",
                "--timeout", str(STUB_TIMEOUT_SECONDS),
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
        report = read_json(output)
        invocations = int(count.read_text(encoding="utf-8").strip())
        self.assertEqual(1, len(report["runs"]), result.stdout)
        self.comparator.load_report(output)
        self.assertEqual(protocol["protocol_id"], report["protocol_id"])
        self.assertEqual(protocol["infrastructure_retry"], report["infrastructure_retry"])
        self.assertEqual(
            self.runner.infrastructure_retry_summary(report["runs"]),
            report["infrastructure_retry_summary"],
        )
        self.comparator.validate_retry_records(report, protocol["infrastructure_retry"])
        # A custom stub runner prints plain text, so usage is recorded as null
        # on the run and on every attempt, and the summary still appears.
        self.assertEqual(protocol["usage_capture"], report["usage_capture"])
        self.comparator.validate_usage_records(report, protocol["usage_capture"])
        self.assertEqual(self.runner.usage_summary(report["runs"]), report["usage_summary"])
        self.assertIsNone(report["runs"][0]["usage"])
        self.assertTrue(
            all(attempt["usage"] is None for attempt in report["runs"][0]["attempts"])
        )
        policy = self.runner.output_normalization_policy(protocol)
        self.comparator.validate_output_normalization_records(report, policy)
        run = report["runs"][0]
        if policy is None:
            # v13 reports keep their schema exactly: no normalization fields.
            self.assertNotIn("output_normalized", run)
            self.assertNotIn("output_normalization", report)
            self.assertNotIn("output_normalization_summary", report)
        else:
            self.assertEqual(policy, report["output_normalization"])
            self.assertEqual(
                self.runner.output_normalization_applied(run), run["output_normalized"]
            )
            self.assertEqual(
                self.runner.output_normalization_summary(report["runs"]),
                report["output_normalization_summary"],
            )
            if run["error"] is None:
                self.assertEqual(
                    self.runner.parse_normalized_findings(run["output"]), run["findings"]
                )
        return report, run, invocations

    def test_fenced_answer_is_scored_once_under_v14(self) -> None:
        for action, findings in (("fenced_json", []), ("fenced_bare", json.loads(WRONG)["findings"])):
            with self.subTest(action), tempfile.TemporaryDirectory() as temp:
                report, run, invocations = self.run_stub(Path(temp), [action, "ok"])
                self.assertEqual(1, invocations)
                self.assertIsNone(run["error"])
                self.assertIsNotNone(run["score"])
                self.assertEqual(findings, run["findings"])
                self.assertTrue(run["output"].startswith("```"))
                self.assertTrue(run["output_normalized"])
                self.assertEqual([None], [attempt["reason"] for attempt in run["attempts"]])
                self.assertEqual(
                    {
                        "unit": "one-report-one-arm",
                        "scheduled_calls": 1,
                        "normalized_runs": 1,
                        "normalized_scored_runs": 1,
                        "normalized_unscoreable_runs": 0,
                    },
                    report["output_normalization_summary"],
                )

    def test_v13_rejects_the_fence_that_v14_accepts(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            report, run, invocations = self.run_stub(
                Path(temp), ["fenced_json", "fenced_json"], V13_PROTOCOL_PATH
            )
        self.assertEqual(2, invocations)
        self.assertEqual(
            ["malformed_json_output", "malformed_json_output"],
            [attempt["reason"] for attempt in run["attempts"]],
        )
        self.assertIsNone(run["score"])
        self.assertTrue(run["error"].startswith(self.runner.STRICT_JSON_FAILURE_PREFIX))
        self.assertEqual(1, report["infrastructure_retry_summary"]["unscoreable_with_retryable_reason"])
        with tempfile.TemporaryDirectory() as temp:
            _, run, invocations = self.run_stub(Path(temp), ["fenced_json", "fenced_json"])
        self.assertEqual(1, invocations)
        self.assertIsNotNone(run["score"])
        self.assertTrue(run["output_normalized"])

    def test_unrecoverable_fences_are_still_malformed_and_retried(self) -> None:
        for action, normalized in (("fenced_prose", False), ("fenced_nonjson", True)):
            with self.subTest(action), tempfile.TemporaryDirectory() as temp:
                report, run, invocations = self.run_stub(Path(temp), [action, action])
                self.assertEqual(2, invocations)
                self.assertEqual(
                    ["malformed_json_output", "malformed_json_output"],
                    [attempt["reason"] for attempt in run["attempts"]],
                )
                self.assertIsNone(run["score"])
                self.assertEqual(normalized, run["output_normalized"])
                self.assertEqual(
                    int(normalized),
                    report["output_normalization_summary"]["normalized_unscoreable_runs"],
                )
            with self.subTest(f"{action} then ok"), tempfile.TemporaryDirectory() as temp:
                _, run, invocations = self.run_stub(Path(temp), [action, "ok"])
                self.assertEqual(2, invocations)
                self.assertEqual(
                    ["malformed_json_output", None],
                    [attempt["reason"] for attempt in run["attempts"]],
                )
                self.assertIsNotNone(run["score"])
                self.assertFalse(run["output_normalized"])

    def test_retryable_failures_are_retried_once(self) -> None:
        for first, reason in (
            ("timeout", "timeout"),
            ("malformed", "malformed_json_output"),
            ("usage_stderr", "runner_nonzero_exit_with_usage_limit_text"),
        ):
            with self.subTest(first), tempfile.TemporaryDirectory() as temp:
                report, run, invocations = self.run_stub(Path(temp), [first, "ok"])
                self.assertEqual(2, invocations)
                self.assertEqual(
                    [reason, None], [attempt["reason"] for attempt in run["attempts"]]
                )
                self.assertIsNone(run["error"])
                self.assertIsNotNone(run["score"])
                self.assertFalse(run["output_normalized"])
                self.assertEqual(
                    1, report["infrastructure_retry_summary"]["retries_by_reason"][reason]
                )

    def test_scoreable_or_unrecognized_output_is_never_retried(self) -> None:
        for first in ("wrong", "crash"):
            with self.subTest(first), tempfile.TemporaryDirectory() as temp:
                report, run, invocations = self.run_stub(Path(temp), [first, "ok"])
                self.assertEqual(1, invocations)
                self.assertEqual([None], [attempt["reason"] for attempt in run["attempts"]])
                self.assertEqual(0, report["infrastructure_retry_summary"]["retries"])
                self.assertFalse(run["output_normalized"])

    # Comparator ------------------------------------------------------------

    def test_comparator_refuses_normalization_fields_outside_v14(self) -> None:
        run = {"exit_code": 0, "error": None, "output": fence(EMPTY), "score": {}}
        for report in (
            {"runs": [dict(run, output_normalized=True)]},
            {"runs": [dict(run)], "output_normalization": self.v14["output_normalization"]},
            {"runs": [dict(run)], "output_normalization_summary": {}},
        ):
            with self.assertRaisesRegex(ValueError, "no output normalization"):
                self.comparator.validate_output_normalization_records(report, None)
        self.comparator.validate_output_normalization_records({"runs": [dict(run)]}, None)
        policy = self.v14["output_normalization"]
        valid = {
            "runs": [dict(run, output_normalized=True)],
            "output_normalization": policy,
            "output_normalization_summary": {},
        }
        self.comparator.validate_output_normalization_records(valid, policy)
        for name, mutate in {
            "missing flag": lambda report: report["runs"][0].pop("output_normalized"),
            "non-boolean flag": lambda report: report["runs"][0].update(
                {"output_normalized": 1}
            ),
            "missing summary": lambda report: report.pop("output_normalization_summary"),
            "policy drift": lambda report: report.update(
                {"output_normalization": {"strip_single_json_fence": True}}
            ),
        }.items():
            report = copy.deepcopy(valid)
            mutate(report)
            with self.subTest(name), self.assertRaises(ValueError):
                self.comparator.validate_output_normalization_records(report, policy)

    def test_single_host_comparator_surfaces_normalized_counts_per_arm(self) -> None:
        cases = self.v5_helpers.synthetic_arm_cases()
        reports = [
            self.v5_helpers.synthetic_arm_report(
                self.comparator,
                profile,
                HOST["runner"],
                HOST["model"],
                "strong" if profile == "full" else "weak",
                cases,
            )
            for profile in ("full", "catalog-only", "no-skill")
        ]
        for index, report in enumerate(reports):
            report["runner_identity"] = "Claude Code 2.1.281"
            for number, run in enumerate(report["runs"]):
                run["output_normalized"] = number < index
        by_profile = {report["prompt_profile"]: report for report in reports}
        for step in self.v14["arm_comparison"]["execution_order"]:
            report = by_profile[step["prompt_profile"]]
            report["started_at"] = f"2026-10-01T00:00:0{step['ordinal'] - 1}+00:00"
            report["created_at"] = f"2026-10-01T00:00:0{step['ordinal']}+00:00"
        with (
            mock.patch.object(
                self.comparator,
                "recompute_report",
                side_effect=lambda report, *_args, **_kwargs: report,
            ),
            mock.patch.object(
                self.comparator,
                "compare_reports",
                return_value={"status": "PASS", "status_reasons": [], "metrics": {}},
            ),
        ):
            result = self.comparator.compare_arm_reports(
                reports, cases, "a" * 64, self.v14, "b" * 64,
                "public-development", "development",
            )
        self.assertEqual("PASS", result["status"])
        self.assertEqual(
            "exact-three-profiles-by-one-host", result["metrics"]["comparison_unit"]
        )
        sections = self.comparator.per_report_sections(self.v14, reports)
        self.assertEqual(
            {"infrastructure_retry", "usage_capture", "output_normalization"}, set(sections)
        )
        self.assertEqual(self.v14["output_normalization"], sections["output_normalization"]["policy"])
        rows = sections["output_normalization"]["reports"]
        self.assertEqual(
            ["full", "catalog-only", "no-skill"], [row["prompt_profile"] for row in rows]
        )
        self.assertEqual(
            [0, 1, 2],
            [row["output_normalization_summary"]["normalized_runs"] for row in rows],
        )
        # v13 comparisons carry no normalization section.
        self.assertNotIn(
            "output_normalization", self.comparator.per_report_sections(self.v13, reports)
        )

    # Documentation ---------------------------------------------------------

    def test_readme_documents_preregistration_and_exact_rerun(self) -> None:
        readme = README_PATH.read_text(encoding="utf-8")
        self.assertIn("# Reviewer holdout v14", readme.splitlines()[0])
        self.assertIn("arm comparison `FAIL`, so no skill-lift claim", readme)
        calls = len(self.v10_cases) * 5 * 3
        self.assertEqual(450, calls)
        for contract in (
            f"{calls} scheduled model calls",
            "scripts/evals/reviewer-holdout-v10.json",
            "scripts/evals/reviewer-validation-protocol-v14.json",
            EXPECTED_CASES_FILE_SHA256,
            EXPECTED_CORPUS_SHA256,
            EXPECTED_PROTOCOL_SHA256,
            "Claude Code 2.1.281",
            'claude_permission_mode: "off"',
            "claude-sonnet-5",
            "--compare-arms",
            'test -z "$(git status --porcelain)"',
            "## Why v14 exists",
            "## Output-normalization rule",
            "## Infrastructure-retry policy",
            "## Claim limits",
            "6 of 150 full-arm calls",
            "21 of 150 catalog-only calls",
            "fixed before any v14 call",
            "every arm",
            "v13 was stopped or finished without a counted result",
            "output_normalized",
            '"strip_single_json_fence": true',
            '"max_attempts_per_call": 2',
            "never retried",
        ):
            self.assertIn(contract, readme)
        self.assertNotIn("is being run", readme)
        self.assertEqual(3, readme.count("--repetitions 5"))
        self.assertEqual(0, readme.count("--repetitions 3"))
        self.assertEqual(4, readme.count('--output "$OUT/'))
        self.assertEqual(3, len(re.findall(r"--arm (full|catalog-only|no-skill) ", readme)))
        self.assertEqual(3, readme.count("--allow-live"))
        self.assertEqual(3, readme.count("--model claude-sonnet-5"))
        self.assertEqual(3, readme.count('--runner claude --runner-path "$CLAUDE_RUNNER"'))
        self.assertEqual(4, readme.count("--protocol scripts/evals/reviewer-validation-protocol-v14.json"))
        self.assertEqual(4, readme.count("--cases scripts/evals/reviewer-holdout-v10.json"))
        self.assertFalse((README_PATH.parent / "attempts").exists())
        self.assertIn(
            "benchmarks/reviewer-holdout-v14/README.md",
            BENCHMARK_DOC_PATH.read_text(encoding="utf-8"),
        )
        changelog = CHANGELOG_PATH.read_text(encoding="utf-8")
        release_section = changelog.split("## [2.0.0]", 1)[1].split("\n## [", 1)[0]
        added = release_section.split("### Added", 1)[1].split("\n### ", 1)[0]
        self.assertIn(PROTOCOL_ID, added)
        self.assertIn("scripts/ci/test-reviewer-holdout-v14.py", added)
        for path in (CI_LOCAL_PATH, CONTRIBUTING_PATH):
            self.assertIn(
                "scripts/ci/test-reviewer-holdout-v14.py", path.read_text(encoding="utf-8")
            )

    def test_run_reports(self) -> None:
        reports = README_PATH.parent / "reports"
        comparison = read_json(reports / "arm-comparison.json")
        self.assertEqual("FAIL", comparison["status"])
        self.assertFalse(comparison["skill_lift_claim_eligible"])
        readme = README_PATH.read_text(encoding="utf-8")
        for arm, normalized in (("full", 31), ("catalog-only", 62), ("no-skill", 17)):
            report = read_json(reports / f"{arm}-claude.json")
            self.assertEqual(EXPECTED_PROTOCOL_SHA256, report["protocol_sha256"], arm)
            self.assertEqual("FAIL", report["status"], arm)
            self.assertEqual(0, report["summary"]["infrastructure_errors"], arm)
            self.assertEqual(normalized, report["output_normalization_summary"]["normalized_runs"], arm)
            self.assertIn(f"| {normalized} / 150 |", readme)
            unique = report["primary_metrics"]["unique"]
            self.assertIn(f"{unique['precision']:.3f} / {unique['recall']:.3f} / {unique['f1']:.3f}", readme)


if __name__ == "__main__":
    unittest.main(verbosity=2)
