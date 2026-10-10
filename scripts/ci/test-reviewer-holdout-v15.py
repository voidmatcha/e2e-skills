#!/usr/bin/env python3
"""Validate the preregistered v15 protocol: v13 plus an enforced native output schema."""

from __future__ import annotations

import argparse
import copy
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import tempfile
import unittest
from unittest import mock


ROOT = Path(__file__).resolve().parents[2]
V5_CASES_PATH = ROOT / "scripts/evals/reviewer-holdout-v5.json"
V9_CASES_PATH = ROOT / "scripts/evals/reviewer-holdout-v9.json"
V10_CASES_PATH = ROOT / "scripts/evals/reviewer-holdout-v10.json"
V9_PROTOCOL_PATH = ROOT / "scripts/evals/reviewer-validation-protocol-v9.json"
V10_PROTOCOL_PATH = ROOT / "scripts/evals/reviewer-validation-protocol-v10.json"
V11_PROTOCOL_PATH = ROOT / "scripts/evals/reviewer-validation-protocol-v11.json"
V12_PROTOCOL_PATH = ROOT / "scripts/evals/reviewer-validation-protocol-v12.json"
V13_PROTOCOL_PATH = ROOT / "scripts/evals/reviewer-validation-protocol-v13.json"
V14_PROTOCOL_PATH = ROOT / "scripts/evals/reviewer-validation-protocol-v14.json"
V15_PROTOCOL_PATH = ROOT / "scripts/evals/reviewer-validation-protocol-v15.json"
RUNNER_PATH = ROOT / "scripts/evals/run-reviewer-holdout.py"
COMPARATOR_PATH = ROOT / "scripts/evals/compare-reviewer-holdouts.py"
TAXONOMY_PATH = ROOT / "scripts/ci/lib/reviewer_taxonomy_contract.py"
README_PATH = ROOT / "benchmarks/reviewer-holdout-v15/README.md"
V15_FULL_REPORT_PATH = ROOT / "benchmarks/reviewer-holdout-v15/reports/full-claude.json"


sys.path.insert(0, str(ROOT / "scripts/ci/lib"))
from frozen_reviewer_inputs import stage_v15_skill  # noqa: E402

# v15's enforced schema enum is the output legend of the skill it evaluated. The
# live skill may grow sub-IDs later (2.0.0 added #8c), which rightly makes the
# runner refuse a v15 run on the live skill; the checks below therefore stage the
# evaluated skill from its committed snapshot (benchmarks/reviewer-holdout-v15/
# frozen/), verified against the digest the frozen report records, instead of
# pinning the checkout or reading git history.
BENCHMARK_DOC_PATH = ROOT / "docs/ai-reviewer-benchmark.md"
CHANGELOG_PATH = ROOT / "CHANGELOG.md"
CONTRIBUTING_PATH = ROOT / "CONTRIBUTING.md"
CI_LOCAL_PATH = ROOT / "scripts/ci/ci-local.sh"

# v15 reuses the frozen v10 corpus: these are v10's digests, unchanged.
EXPECTED_CASES_FILE_SHA256 = "6db718fe63001f987901a68ee230809c56fda2df5e97d3f0b83ab382b953cc5e"
EXPECTED_CORPUS_SHA256 = "672f99fc323cf72cb9946483b01f7df314ee12000bcc40b5aa3eb1efb2f8cb8d"
EXPECTED_V10_PROTOCOL_SHA256 = "186680ad624f9ae40ff0b652ee4949322fb6ccfac5e5426a4b7c182278f33c39"
EXPECTED_V11_PROTOCOL_SHA256 = "5676b452de7d6fce7ae7292bf21248b2dbeef3eeb493175cf85024299dee1bf1"
EXPECTED_V12_PROTOCOL_SHA256 = "ec42df85e7161ca96a807cbd0079eb9c406b926ae0c40bb4214f2b88280a5d20"
EXPECTED_V13_PROTOCOL_SHA256 = "6803125914bd03ff07e724614636b2e8a040e6a13932f2af6b187a87ed78ff7b"
EXPECTED_V14_PROTOCOL_SHA256 = "c668d7308c4ec841998c26c052a8900a1da99d2057955e79b39d76848a20c679"
EXPECTED_PROTOCOL_SHA256 = "0e79b040aab2b47865ca13a6a484fb3bcad617ef16bcc38b4de7a49b12498d93"
EXPECTED_SCHEMA_SHA256 = "9bfd806c73c083a2b8af13a2199523651567d4fe4442c392c09174a122139aa3"
EXPECTED_PATTERN_IDS = [
    "#1", "#10", "#10a", "#10b", "#10c", "#10d", "#10e", "#10f", "#11",
    "#11c", "#12", "#13", "#14", "#15", "#16", "#17", "#18", "#19", "#2",
    "#20", "#21", "#22", "#23", "#3", "#3b", "#4a", "#4b", "#4c-4e", "#4f",
    "#4g", "#4h", "#4i", "#4j", "#4k", "#5a", "#5b", "#6", "#7", "#8", "#8a",
    "#8b", "#9", "#9b", "#9c",
]
PROTOCOL_ID = "reviewer-holdout-v15"
V10_ID = "reviewer-holdout-v10"
V11_ID = "reviewer-holdout-v11"
V12_ID = "reviewer-holdout-v12"
V13_ID = "reviewer-holdout-v13"
V14_ID = "reviewer-holdout-v14"
HOST = {"runner": "claude", "model": "claude-sonnet-5"}
IDENTITY = {"claude": "Claude Code 2.1.283"}
REUSERS = {V11_ID, V12_ID, V13_ID, V14_ID, PROTOCOL_ID}

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
FAKE_CLAUDE_TOKEN = "stub-oauth-token-not-a-credential"
# The labeled #4f P0 finding of v10-pw-01, as the model would report it.
FINDING = {"pattern_id": "#4f", "severity": "P0", "file": "tests/recipe-box.spec.ts", "line": 10}
ANSWER_OBJECT = {"findings": [FINDING]}
COMPACT_ANSWER = json.dumps(ANSWER_OBJECT, separators=(",", ":"))
FENCED_ANSWER = "```json\n" + json.dumps(ANSWER_OBJECT) + "\n```"
CLAUDE_USAGE = {
    "input_tokens": 2,
    "cache_creation_input_tokens": 5889,
    "cache_read_input_tokens": 0,
    "output_tokens": 529,
}
CODEX_USAGE = {
    "input_tokens": 16382,
    "cached_input_tokens": 0,
    "output_tokens": 70,
    "reasoning_output_tokens": 30,
}
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

# Records its argv and stdin, copies the file named after --output-schema (the
# runner deletes it with its private home), then replays a canned response.
STUB_TEMPLATE = """#!/bin/sh
: > '{argv}'
previous=''
for arg in "$@"; do
  printf '%s\\n' "$arg" >> '{argv}'
  if [ "$previous" = '--output-schema' ]; then /bin/cat "$arg" > '{schema_copy}'; fi
  previous="$arg"
done
/bin/cat > '{stdin}'
/bin/cat '{response}'
exit "$(/bin/cat '{status}')"
"""

# A plain-text custom runner for whole-run stubs: reads the next action from
# PLAN and counts itself in COUNT. It never calls a model.
PLAN_STUB_TEMPLATE = """#!/bin/sh
/bin/cat >/dev/null
printf '%s\\n' "$#" > '{argc}'
n=$(/bin/cat '{count}' 2>/dev/null || echo 0)
n=$((n + 1))
echo "$n" > '{count}'
action=$(/usr/bin/sed -n "${{n}}p" '{plan}')
case "$action" in
  ok) printf '%s' '{{"findings":[]}}' ;;
  fenced_json) printf '%s\\n' '```json' '{{"findings":[]}}' '```' ;;
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


def claude_envelope(result: str, **overrides) -> str:
    """A Claude Code 2.1.283 `--json-schema` envelope, as probed live."""
    envelope = {
        "type": "result",
        "subtype": "success",
        "is_error": False,
        "num_turns": 2,
        "result": result,
        "stop_reason": "tool_use",
        "session_id": "00000000-0000-4000-8000-000000000000",
        "usage": CLAUDE_USAGE,
        "permission_denials": [],
        "structured_output": json.loads(result) if result.startswith("{") else None,
        "uuid": "00000000-0000-4000-8000-000000000001",
    }
    envelope.update(overrides)
    return json.dumps(envelope)


def codex_events(answer: str) -> str:
    events = [
        {"type": "thread.started", "thread_id": "0199a000-0000-7000-8000-000000000000"},
        {"type": "turn.started"},
        {"type": "item.completed", "item": {"id": "item_0", "type": "agent_message", "text": answer}},
        {"type": "turn.completed", "usage": CODEX_USAGE},
    ]
    return "".join(json.dumps(event) + "\n" for event in events)


def schema_errors(schema: dict, value: object, path: str = "$") -> list[str]:
    """Validate the JSON-schema subset the output schema uses."""
    errors: list[str] = []
    kind = schema.get("type")
    if kind == "object":
        if not isinstance(value, dict):
            return [f"{path}: not an object"]
        for key in schema.get("required", []):
            if key not in value:
                errors.append(f"{path}: missing {key}")
        if schema.get("additionalProperties") is False:
            for key in value:
                if key not in schema["properties"]:
                    errors.append(f"{path}: unexpected {key}")
        for key, child in schema.get("properties", {}).items():
            if key in value:
                errors.extend(schema_errors(child, value[key], f"{path}.{key}"))
    elif kind == "array":
        if not isinstance(value, list):
            return [f"{path}: not an array"]
        for index, item in enumerate(value):
            errors.extend(schema_errors(schema["items"], item, f"{path}[{index}]"))
    elif kind == "string":
        if not isinstance(value, str):
            return [f"{path}: not a string"]
    elif kind == "integer":
        if isinstance(value, bool) or not isinstance(value, int):
            return [f"{path}: not an integer"]
        if "minimum" in schema and value < schema["minimum"]:
            errors.append(f"{path}: below minimum")
    else:
        errors.append(f"{path}: unsupported schema type {kind!r}")
    if "enum" in schema and value not in schema["enum"]:
        errors.append(f"{path}: {value!r} not in enum")
    return errors


def corpus_label_findings(cases: list[dict]) -> list[dict]:
    """Every tuple a v10 label or accepted alternative can be matched by."""
    findings = []
    for case in cases:
        for label in case["labels"]:
            for item in (label, *label.get("accepted_alternatives", ())):
                findings.append(
                    {key: item[key] for key in ("pattern_id", "severity", "file", "line")}
                )
    return findings


class ReviewerHoldoutV15Test(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.runner = load_module("reviewer_holdout_v15_runner", RUNNER_PATH)
        cls.comparator = load_module("reviewer_holdout_v15_comparator", COMPARATOR_PATH)
        cls.taxonomy = load_module("reviewer_holdout_v15_taxonomy", TAXONOMY_PATH)
        cls.v9 = read_json(V9_PROTOCOL_PATH)
        cls.v10 = read_json(V10_PROTOCOL_PATH)
        cls.v13 = read_json(V13_PROTOCOL_PATH)
        cls.v14 = read_json(V14_PROTOCOL_PATH)
        cls.v15 = read_json(V15_PROTOCOL_PATH)
        cls.v10_metadata, cls.v10_cases = cls.runner.load_cases(V10_CASES_PATH)
        cls.case = next(case for case in cls.v10_cases if case["id"] == STUB_CASE)
        cls._skill_temp = tempfile.TemporaryDirectory(prefix="reviewer-holdout-v15-skill-")
        cls.skill_dir = stage_v15_skill(Path(cls._skill_temp.name), cls.runner.skill_digest)
        cls.skill_sha256 = cls.runner.skill_digest(cls.skill_dir)
        # The staged snapshot must be the skill the frozen v15 reports record.
        assert cls.skill_sha256 == read_json(V15_FULL_REPORT_PATH)["skill_sha256"]
        cls.schema = cls.v15["output_schema"]["schema"]

    @classmethod
    def tearDownClass(cls) -> None:
        cls._skill_temp.cleanup()

    def load_mutated(self, temp: str, data: dict, name: str = "protocol.json") -> dict:
        path = Path(temp) / name
        path.write_text(json.dumps(data), encoding="utf-8")
        return self.runner.load_protocol(path)

    # Frozen inputs -------------------------------------------------------

    def test_frozen_inputs_and_runner_registration(self) -> None:
        self.assertEqual(
            EXPECTED_CASES_FILE_SHA256, hashlib.sha256(V10_CASES_PATH.read_bytes()).hexdigest()
        )
        self.assertEqual(
            EXPECTED_CORPUS_SHA256, self.runner.corpus_digest(V10_CASES_PATH, self.v10_cases)
        )
        self.assertEqual(
            EXPECTED_PROTOCOL_SHA256, hashlib.sha256(V15_PROTOCOL_PATH.read_bytes()).hexdigest()
        )
        # v10-v14 protocols are untouched.
        for path, digest in (
            (V10_PROTOCOL_PATH, EXPECTED_V10_PROTOCOL_SHA256),
            (V11_PROTOCOL_PATH, EXPECTED_V11_PROTOCOL_SHA256),
            (V12_PROTOCOL_PATH, EXPECTED_V12_PROTOCOL_SHA256),
            (V13_PROTOCOL_PATH, EXPECTED_V13_PROTOCOL_SHA256),
            (V14_PROTOCOL_PATH, EXPECTED_V14_PROTOCOL_SHA256),
        ):
            self.assertEqual(digest, hashlib.sha256(path.read_bytes()).hexdigest(), path)
        self.assertEqual(self.v15, self.runner.load_protocol(V15_PROTOCOL_PATH))
        self.assertEqual(V15_PROTOCOL_PATH, self.runner.V15_PROTOCOL)
        self.assertEqual(
            {
                "cases_file_sha256": EXPECTED_CASES_FILE_SHA256,
                "corpus_sha256": EXPECTED_CORPUS_SHA256,
                "protocol_sha256": EXPECTED_PROTOCOL_SHA256,
            },
            self.runner.PINNED_LIVE_INPUTS[(V10_CASES_PATH, V15_PROTOCOL_PATH)],
        )
        self.assertEqual(
            [(V10_CASES_PATH, V15_PROTOCOL_PATH)],
            [key for key in self.runner.PINNED_LIVE_INPUTS if key[1] == V15_PROTOCOL_PATH],
        )
        self.assertEqual(self.v10["corpus"], self.v15["corpus"])
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
            "OUTPUT_SCHEMA_PROTOCOL_IDS",
        ):
            self.assertIn(PROTOCOL_ID, getattr(self.runner, id_set), id_set)
        for id_set in (
            "PROVIDER_BALANCED_PROTOCOL_IDS",
            "FULL_ONLY_PROTOCOL_IDS",
            "SUPERSEDED_PROTOCOL_IDS",
            "HISTORICAL_DIAGNOSTIC_PROTOCOL_IDS",
            "SPECIFICITY_PROTOCOL_IDS",
            "OUTPUT_NORMALIZATION_PROTOCOL_IDS",
        ):
            self.assertNotIn(PROTOCOL_ID, getattr(self.runner, id_set), id_set)
        # v15 and later holdouts use an enforced schema, and v14
        # stays the only protocol with fence normalization.
        self.assertEqual({PROTOCOL_ID, V16_ID, V17_ID, V18_ID, V19_ID, V20_ID, V21_ID}, self.runner.OUTPUT_SCHEMA_PROTOCOL_IDS)
        self.assertEqual({V14_ID}, self.runner.OUTPUT_NORMALIZATION_PROTOCOL_IDS)
        self.assertEqual(
            {V13_ID, V14_ID, PROTOCOL_ID, V16_ID, V17_ID, V18_ID, V19_ID, V20_ID, V21_ID}, self.runner.USAGE_CAPTURE_PROTOCOL_IDS
        )
        self.assertEqual(REUSERS | {V16_ID, V17_ID, V18_ID, V19_ID, V20_ID, V21_ID}, self.runner.INFRASTRUCTURE_RETRY_PROTOCOL_IDS)
        self.assertEqual(V10_CASES_PATH, self.runner.REVISED_LABEL_CORPORA[PROTOCOL_ID])
        self.assertEqual(
            {**{reuser: V10_ID for reuser in REUSERS}, V16_ID: V9_OWNER_ID, V18_ID: V17_ID, V19_ID: V17_ID},
            self.runner.SHARED_CORPUS_PROTOCOLS,
        )
        self.assertEqual("minimum", self.runner.FROZEN_EXECUTION_IDENTITY_POLICIES[PROTOCOL_ID])
        self.assertEqual(IDENTITY, self.runner.FROZEN_EXECUTION_IDENTITIES[PROTOCOL_ID])
        self.assertEqual(HOST, self.runner.REVISED_LABEL_HOSTS[PROTOCOL_ID])
        self.assertEqual(
            {V13_ID: "off", V14_ID: "off", PROTOCOL_ID: "off"},
            self.runner.REQUIRED_CLAUDE_PERMISSION_MODES,
        )

    def test_protocol_is_v13_plus_output_schema(self) -> None:
        v13 = copy.deepcopy(self.v13)
        v15 = copy.deepcopy(self.v15)
        self.assertEqual(PROTOCOL_ID, v15.pop("protocol_id"))
        v13.pop("protocol_id")
        disclosure = v15["schedule"].pop("design_disclosure")
        v13["schedule"].pop("design_disclosure")
        for phrase in (
            "Reviewer holdout v15 is v13 plus one preregistered enforced output schema",
            "carries no output normalization",
            "6 of 150 full-arm calls, 21 of 150 catalog-only calls, and 4 of 150 no-skill calls",
            "v13 ended INCONCLUSIVE",
            "no v13 skill-lift result is claimed",
            "was fixed in this protocol before any v15 call",
            "--output-format json with --json-schema",
            "Codex --output-schema",
            "structured_output object, serialized as compact JSON",
            "the unchanged strict parser and findings validator",
            "no fence or other normalization is applied",
            "a missing or non-object structured_output is malformed output",
            "covers every v10 corpus label",
            "applies identically to every arm (full, catalog-only, and no-skill)",
            "the prompt text is v13's unchanged",
            "schema_sha256",
            "never which findings the model reports",
            "raised to 2.1.283",
            "claude_permission_mode off",
            "a scoreable output is never retried",
            "reused unchanged by path and digest",
            "five repetitions",
            "public development evidence",
            "not a fresh-corpus test for the author",
            "those runs do not train models",
            "v13's and v14's reports are not rescored",
        ):
            self.assertIn(phrase, disclosure)
        self.assertNotIn("is being run", disclosure)
        output_schema = v15.pop("output_schema")
        self.assertEqual(self.runner.EXPECTED_OUTPUT_SCHEMA, output_schema)
        self.assertEqual(["mode", "schema", "schema_sha256", "contract"], list(output_schema))
        self.assertEqual("enforced", output_schema["mode"])
        self.assertEqual(IDENTITY, v15["execution_identity"].pop("expected_cli_versions"))
        self.assertEqual(
            {"claude": "Claude Code 2.1.281"},
            v13["execution_identity"].pop("expected_cli_versions"),
        )
        # Everything else is v13's byte for byte: host, permission mode, retry
        # policy, usage capture, corpus, arms, thresholds, seed.
        self.assertEqual(v13, v15)
        self.assertNotIn("output_normalization", self.v15)
        v13_keys = list(self.v13)
        v13_keys.insert(v13_keys.index("usage_capture") + 1, "output_schema")
        self.assertEqual(v13_keys, list(self.v15))
        self.assertEqual(
            self.runner.EXPECTED_INFRASTRUCTURE_RETRY, self.v15["infrastructure_retry"]
        )
        self.assertEqual({"enabled": True}, self.v15["usage_capture"])
        self.assertEqual("off", self.v15["execution_identity"]["claude_permission_mode"])
        self.assertEqual([HOST], self.v15["host_matrix"])
        self.assertEqual(5, self.v15["schedule"]["default_repetitions"])
        self.assertEqual(20260801, self.v15["schedule"]["seed"])

    def test_protocol_validation_pins_v15_fields(self) -> None:
        def items(data: dict) -> dict:
            return data["output_schema"]["schema"]["properties"]["findings"]["items"]

        def enum(data: dict) -> list:
            return items(data)["properties"]["pattern_id"]["enum"]

        mutations = {
            "three repetitions": lambda data: data["schedule"].update(
                {"default_repetitions": 3, "release_repetitions": 3}
            ),
            "codex host": lambda data: data.update(
                {"host_matrix": [{"runner": "codex", "model": "gpt-6-sol"}]}
            ),
            "v13 claude floor": lambda data: data["execution_identity"].update(
                {"expected_cli_versions": {"claude": "Claude Code 2.1.281"}}
            ),
            "plan permission mode": lambda data: data["execution_identity"].update(
                {"claude_permission_mode": "plan"}
            ),
            "exact policy": lambda data: data["execution_identity"].update(
                {"version_policy": "exact"}
            ),
            "missing retry policy": lambda data: data.pop("infrastructure_retry"),
            "missing usage capture": lambda data: data.pop("usage_capture"),
            "added output normalization": lambda data: data.update(
                {"output_normalization": copy.deepcopy(self.v14["output_normalization"])}
            ),
            "missing output schema": lambda data: data.pop("output_schema"),
            "schema not an object": lambda data: data.update({"output_schema": True}),
            "advisory mode": lambda data: data["output_schema"].update({"mode": "advisory"}),
            "extra key": lambda data: data["output_schema"].update({"normalize": True}),
            "missing contract": lambda data: data["output_schema"].pop("contract"),
            "contract drift": lambda data: data["output_schema"].update(
                {"contract": "Use the schema when convenient."}
            ),
            "digest drift": lambda data: data["output_schema"].update(
                {"schema_sha256": "0" * 64}
            ),
            "enum missing a label ID": lambda data: enum(data).remove("#4c-4e"),
            "enum with an extra ID": lambda data: enum(data).append("#99"),
            "enum reordered": lambda data: enum(data).reverse(),
            "open finding object": lambda data: items(data).update(
                {"additionalProperties": True}
            ),
            "optional line": lambda data: items(data)["required"].remove("line"),
            "line zero allowed": lambda data: items(data)["properties"]["line"].update(
                {"minimum": 0}
            ),
            "constrained file": lambda data: items(data)["properties"]["file"].update(
                {"pattern": "^tests/"}
            ),
            "severity P3": lambda data: items(data)["properties"]["severity"]["enum"].append(
                "P3"
            ),
            "open top level": lambda data: data["output_schema"]["schema"].update(
                {"additionalProperties": True}
            ),
        }
        with tempfile.TemporaryDirectory() as temp:
            for name, mutate in mutations.items():
                data = copy.deepcopy(self.v15)
                mutate(data)
                with self.subTest(name), self.assertRaises(ValueError):
                    self.load_mutated(temp, data)
            # A digest recomputed for a drifted schema is still refused.
            data = copy.deepcopy(self.v15)
            enum(data).remove("#9c")
            data["output_schema"]["schema_sha256"] = self.runner.output_schema_sha256(
                data["output_schema"]["schema"]
            )
            with self.assertRaisesRegex(ValueError, "output_schema must be exact"):
                self.load_mutated(temp, data)

    def test_output_schema_is_limited_to_v15(self) -> None:
        self.assertEqual(
            self.v15["output_schema"], self.runner.output_schema_policy(self.v15)
        )
        # v16 carries the same block, byte for byte.
        self.assertEqual(
            self.v15["output_schema"],
            self.runner.output_schema_policy(
                {"protocol_id": V16_ID, "output_schema": self.v15["output_schema"]}
            ),
        )
        for protocol_id in sorted(self.runner.SUPPORTED_PROTOCOL_IDS - {PROTOCOL_ID, V16_ID, V17_ID, V18_ID, V19_ID, V20_ID, V21_ID}):
            self.assertIsNone(
                self.runner.output_schema_policy(
                    {"protocol_id": protocol_id, "output_schema": self.v15["output_schema"]}
                ),
                protocol_id,
            )
        self.assertIsNone(self.runner.output_normalization_policy(self.v15))
        with tempfile.TemporaryDirectory() as temp:
            for name, protocol in (
                ("v14", self.v14), ("v13", self.v13), ("v10", self.v10), ("v9", self.v9)
            ):
                data = copy.deepcopy(protocol)
                data["output_schema"] = copy.deepcopy(self.runner.EXPECTED_OUTPUT_SCHEMA)
                with self.subTest(name), self.assertRaisesRegex(ValueError, "unknown="):
                    self.load_mutated(temp, data, f"{name}.json")
        for path in (
            V10_PROTOCOL_PATH, V11_PROTOCOL_PATH, V12_PROTOCOL_PATH,
            V13_PROTOCOL_PATH, V14_PROTOCOL_PATH,
        ):
            self.assertEqual(read_json(path), self.runner.load_protocol(path))

    # Schema --------------------------------------------------------------

    def test_schema_is_strict_and_digest_is_recorded(self) -> None:
        schema = self.schema
        self.assertEqual(
            EXPECTED_SCHEMA_SHA256,
            hashlib.sha256(self.runner.canonical_schema_text(schema).encode("ascii")).hexdigest(),
        )
        self.assertEqual(EXPECTED_SCHEMA_SHA256, self.v15["output_schema"]["schema_sha256"])
        self.assertEqual(EXPECTED_SCHEMA_SHA256, self.runner.output_schema_sha256(schema))
        # OpenAI strict schemas: every object is closed and requires every property.
        objects = [schema, schema["properties"]["findings"]["items"]]
        for node in objects:
            self.assertEqual("object", node["type"])
            self.assertIs(False, node["additionalProperties"])
            self.assertEqual(sorted(node["properties"]), sorted(node["required"]))
        self.assertEqual(["findings"], schema["required"])
        self.assertEqual("array", schema["properties"]["findings"]["type"])
        properties = schema["properties"]["findings"]["items"]["properties"]
        self.assertEqual(["pattern_id", "severity", "file", "line"], list(properties))
        self.assertEqual({"type": "string", "enum": ["P0", "P1", "P2"]}, properties["severity"])
        self.assertEqual({"type": "integer", "minimum": 1}, properties["line"])
        self.assertEqual({"type": "string"}, properties["file"])
        self.assertEqual(
            {"type": "string", "enum": EXPECTED_PATTERN_IDS}, properties["pattern_id"]
        )
        # The schema accepts exactly what the strict findings validator accepts
        # on these shapes, and rejects the malformed ones.
        self.assertEqual([], schema_errors(schema, ANSWER_OBJECT))
        self.assertEqual([], schema_errors(schema, {"findings": []}))
        for bad in (
            {"findings": [], "notes": ""},
            {"findings": [{**FINDING, "fix": "x"}]},
            {"findings": [{key: FINDING[key] for key in ("pattern_id", "severity", "file")}]},
            {"findings": [{**FINDING, "line": 0}]},
            {"findings": [{**FINDING, "line": "10"}]},
            {"findings": [{**FINDING, "severity": "P3"}]},
            {"findings": [{**FINDING, "pattern_id": "#4"}]},
            {"findings": [{**FINDING, "pattern_id": "4f"}]},
            [],
        ):
            with self.subTest(bad):
                self.assertNotEqual([], schema_errors(schema, bad))

    def test_schema_enum_is_the_prompt_legend_and_covers_every_label(self) -> None:
        enum = self.schema["properties"]["findings"]["items"]["properties"]["pattern_id"]["enum"]
        self.assertEqual(list(self.runner.OUTPUT_SCHEMA_PATTERN_IDS), enum)
        legend = [
            row.split(" | ", 1)[0]
            for row in self.runner.pattern_output_legend(self.skill_dir).splitlines()
        ]
        self.assertEqual(legend, enum)
        self.assertEqual(
            sorted(self.runner.canonical_severities(self.skill_dir)), enum
        )
        # The live skill's legend is a superset at most: v15 stays runnable only on
        # the evaluated revision, never on a skill whose legend the schema cannot express.
        live_legend = [
            row.split(" | ", 1)[0]
            for row in self.runner.pattern_output_legend(self.runner.DEFAULT_SKILL_DIR).splitlines()
        ]
        self.assertEqual([], sorted(set(enum) - set(live_legend)))
        self.assertEqual(len(enum), len(set(enum)))
        # Every label and accepted alternative of the v10 corpus is expressible,
        # so the schema cannot bias a result by forbidding a correct answer.
        label_findings = corpus_label_findings(self.v10_cases)
        self.assertGreater(len(label_findings), 30)
        missing = sorted({item["pattern_id"] for item in label_findings} - set(enum))
        self.assertEqual([], missing)
        for item in label_findings:
            self.assertEqual([], schema_errors(self.schema, {"findings": [item]}), item)
        # Every reviewer taxonomy family is present as itself or as sub-IDs.
        for pattern_id, _title, _severity in self.taxonomy.REVIEWER_TAXONOMY:
            family = re.compile(rf"#{re.escape(pattern_id)}(?:[a-z](?:-[0-9]+[a-z])?)?")
            with self.subTest(pattern_id):
                self.assertTrue(any(family.fullmatch(item) for item in enum))
        # And every enum member passes the unchanged findings validator.
        for pattern_id in enum:
            finding = {**FINDING, "pattern_id": pattern_id}
            self.assertEqual([finding], self.runner.normalize_findings({"findings": [finding]}))

    def test_schema_findings_are_validated_by_runner_and_comparator(self) -> None:
        policy = self.v15["output_schema"]
        for name, finding in (
            ("unknown pattern", {**FINDING, "pattern_id": "#999"}),
            ("invalid severity", {**FINDING, "severity": "P3"}),
            ("line zero", {**FINDING, "line": 0}),
            ("boolean line", {**FINDING, "line": True}),
        ):
            answer = json.dumps({"findings": [finding]})
            with self.subTest(name):
                with self.assertRaises(ValueError):
                    self.runner.parse_findings(answer, self.schema)
                with self.assertRaises(ValueError):
                    self.comparator.parse_report_findings(answer, policy)
        unknown = json.dumps({"findings": [{**FINDING, "pattern_id": "#999"}]})
        # Protocols without output_schema retain the earlier syntactic parser.
        self.assertEqual("#999", self.runner.parse_findings(unknown)[0]["pattern_id"])
        self.assertEqual("#999", self.comparator.parse_report_findings(unknown, None)[0]["pattern_id"])
        self.assertEqual([FINDING], self.runner.parse_findings(COMPACT_ANSWER, self.schema))
        self.assertEqual([FINDING], self.comparator.parse_report_findings(COMPACT_ANSWER, policy))

    def test_run_refuses_a_skill_whose_legend_differs(self) -> None:
        policy = self.v15["output_schema"]
        self.runner.require_output_schema_vocabulary(policy, self.skill_dir)
        legend = self.runner.pattern_output_legend(self.skill_dir)
        # The live checkout is refused as soon as its legend differs from the
        # evaluated revision's (it does since #8c), not silently scored.
        if self.runner.pattern_output_legend(self.runner.DEFAULT_SKILL_DIR) != legend:
            with self.assertRaisesRegex(ValueError, "does not match the evaluated skill"):
                self.runner.require_output_schema_vocabulary(
                    policy, self.runner.DEFAULT_SKILL_DIR
                )
        for name, changed in (
            ("new sub-ID", legend + "\n#4l | Vacuous / Retry-Weakening Assertions | P1"),
            ("dropped ID", "\n".join(legend.splitlines()[1:])),
        ):
            with self.subTest(name), mock.patch.object(
                self.runner, "pattern_output_legend", return_value=changed
            ), self.assertRaisesRegex(ValueError, "does not match the evaluated skill"):
                self.runner.require_output_schema_vocabulary(
                    policy, self.skill_dir
                )

    # Invocation and answer extraction ------------------------------------

    def attempt(
        self, runner: str, response: str, *, schema: bool = True, status: int = 0,
    ) -> tuple[dict, str | None, list[str], str, str | None]:
        """Run execute_scheduled_attempt against a stub; return record and I/O."""
        model = {"claude": "claude-sonnet-5", "codex": "gpt-6-sol"}[runner]
        with tempfile.TemporaryDirectory() as temp:
            temp_path = Path(temp)
            paths = {
                name: temp_path / name
                for name in ("argv", "stdin", "response", "status", "schema_copy")
            }
            paths["response"].write_text(response, encoding="utf-8")
            paths["status"].write_text(str(status), encoding="utf-8")
            stub = temp_path / "stub-runner"
            stub.write_text(STUB_TEMPLATE.format(**paths), encoding="utf-8")
            stub.chmod(0o755)
            codex_home = temp_path / "codex-home"
            codex_home.mkdir()
            args = argparse.Namespace(
                runner=runner, arm="full", timeout=20, model=model, reasoning_effort=None,
            )
            credentials = (
                {"CLAUDE_CODE_OAUTH_TOKEN": FAKE_CLAUDE_TOKEN} if runner == "claude" else {}
            )
            with (
                mock.patch.object(
                    self.runner, "inherited_runner_credentials", return_value=credentials,
                ),
                mock.patch.object(self.runner, "stage_codex_auth", return_value=codex_home),
            ):
                record, reason = self.runner.execute_scheduled_attempt(
                    self.case,
                    {"ordinal": 1, "case": STUB_CASE, "repetition": 1},
                    V10_CASES_PATH,
                    self.skill_dir,
                    self.skill_sha256,
                    args,
                    [],
                    str(stub),
                    "off",
                    True,
                    True,
                    capture_stderr=True,
                    capture_usage=True,
                    **({"output_schema": self.schema} if schema else {}),
                )
            schema_copy = (
                paths["schema_copy"].read_text(encoding="ascii")
                if paths["schema_copy"].exists()
                else None
            )
            return (
                record,
                reason,
                paths["argv"].read_text(encoding="utf-8").split("\n")[:-1],
                paths["stdin"].read_text(encoding="utf-8"),
                schema_copy,
            )

    def test_claude_command_passes_the_schema_and_reads_structured_output(self) -> None:
        canonical = self.runner.canonical_schema_text(self.schema)
        # The host returns structured_output even when result is fenced text.
        response = claude_envelope(FENCED_ANSWER, structured_output=ANSWER_OBJECT)
        record, reason, argv, stdin, _ = self.attempt("claude", response)
        self.assertEqual(
            [*CLAUDE_OFF_TEXT_COMMAND, "--output-format", "json", "--json-schema", canonical],
            argv,
        )
        self.assertEqual(EXPECTED_SCHEMA_SHA256, hashlib.sha256(canonical.encode()).hexdigest())
        self.assertIsNone(record["error"])
        self.assertIsNone(reason)
        self.assertEqual(COMPACT_ANSWER, record["output"])
        self.assertEqual([FINDING], record["findings"])
        self.assertEqual(1, record["score"]["tp"])
        self.assertEqual("claude-json-envelope", record["usage"]["source"])
        self.assertNotIn("output_normalized", record)
        # The comparator re-parses the stored output with the strict parser.
        self.assertEqual(record["findings"], self.runner.parse_findings(record["output"]))
        # The prompt is the unchanged v13 prompt: it still asks for bare JSON.
        text, _, text_argv, text_stdin, _ = self.attempt(
            "claude", claude_envelope(COMPACT_ANSWER), schema=False
        )
        self.assertEqual(text_stdin, stdin)
        self.assertEqual([*CLAUDE_OFF_TEXT_COMMAND, "--output-format", "json"], text_argv)
        self.assertIn("Do not include prose, Markdown fences", stdin)
        for marker in ("json-schema", "structured_output", "output_schema", "holdout-v15"):
            self.assertNotIn(marker, stdin)

    def test_missing_or_invalid_structured_output_is_malformed_and_retryable(self) -> None:
        for name, structured in (
            ("missing", None),
            ("null", "null"),
            ("array", [ANSWER_OBJECT]),
            ("string", COMPACT_ANSWER),
            ("number", 1),
        ):
            with self.subTest(name):
                if structured is None:
                    envelope = json.loads(claude_envelope(COMPACT_ANSWER))
                    envelope.pop("structured_output")
                    response = json.dumps(envelope)
                else:
                    response = claude_envelope(
                        COMPACT_ANSWER,
                        structured_output=None if structured == "null" else structured,
                    )
                record, reason, _, _, _ = self.attempt("claude", response)
                # The valid-looking free-text result is never scored instead.
                self.assertEqual(self.runner.MISSING_STRUCTURED_OUTPUT_ERROR, record["error"])
                self.assertTrue(record["error"].startswith(self.runner.STRICT_JSON_FAILURE_PREFIX))
                self.assertEqual("malformed_json_output", reason)
                self.assertIsNone(record["score"])
                self.assertEqual([], record["findings"])
                self.assertEqual(COMPACT_ANSWER, record["output"])
                self.assertEqual(2, record["usage"]["input_tokens"])

    def test_structured_output_goes_through_the_unchanged_validator(self) -> None:
        # An object of the wrong shape (the host should never return one) is
        # refused by the strict findings validator, not repaired, and like any
        # wrong-shape JSON payload it is not a retryable reason.
        for name, structured, message in (
            ("extra top-level key", {"findings": [], "notes": "x"}, "exactly the findings field"),
            ("extra finding key", {"findings": [{**FINDING, "fix": "x"}]}, "exactly the required"),
            ("line zero", {"findings": [{**FINDING, "line": 0}]}, "invalid values"),
        ):
            with self.subTest(name):
                record, reason, _, _, _ = self.attempt(
                    "claude", claude_envelope(COMPACT_ANSWER, structured_output=structured)
                )
                self.assertIn(message, record["error"])
                self.assertIsNone(record["score"])
                self.assertIsNone(reason)
        # A malformed envelope stays the unscoreable, non-retryable envelope error.
        record, reason, _, _, _ = self.attempt("claude", "Here: " + COMPACT_ANSWER)
        self.assertTrue(record["error"].startswith(self.runner.MALFORMED_CLAUDE_ENVELOPE_PREFIX))
        self.assertIsNone(reason)
        # A non-zero exit keeps the usage-limit retry.
        record, reason, _, _, _ = self.attempt(
            "claude",
            claude_envelope("You've hit your usage limit.", is_error=True),
            status=1,
        )
        self.assertEqual("runner exited 1", record["error"])
        self.assertEqual("runner_nonzero_exit_with_usage_limit_text", reason)

    def test_out_of_enum_structured_answer_is_unscoreable(self) -> None:
        answer = json.dumps({"findings": [{**FINDING, "pattern_id": "#999"}]})
        for runner, response in (
            ("claude", claude_envelope(COMPACT_ANSWER, structured_output=json.loads(answer))),
            ("codex", codex_events(answer)),
        ):
            with self.subTest(runner):
                record, reason, _, _, _ = self.attempt(runner, response)
                self.assertIn("violates output schema", record["error"])
                self.assertIsNone(record["score"])
                self.assertEqual([], record["findings"])
                self.assertIsNone(reason)

    def test_codex_command_passes_a_private_schema_file_and_reads_the_final_message(self) -> None:
        record, reason, argv, _, schema_copy = self.attempt("codex", codex_events(COMPACT_ANSWER))
        self.assertEqual("--output-schema", argv[-3])
        self.assertEqual("-", argv[-1])
        self.assertEqual(
            [CODEX_TEXT_COMMAND[0], "--json", *CODEX_TEXT_COMMAND[1:-1]], argv[:-3]
        )
        schema_path = Path(argv[-2])
        self.assertEqual("output-schema.json", schema_path.name)
        self.assertTrue(schema_path.parent.name.startswith("e2e-reviewer-runner-home-"))
        # The file lived in the runner-private home and is gone with it.
        self.assertFalse(schema_path.exists())
        self.assertEqual(self.runner.canonical_schema_text(self.schema), schema_copy)
        self.assertIsNone(record["error"])
        self.assertIsNone(reason)
        self.assertEqual(COMPACT_ANSWER, record["output"])
        self.assertEqual(1, record["score"]["tp"])
        self.assertEqual("codex-json-events", record["usage"]["source"])
        # No normalization: a fenced final message is malformed and retried.
        record, reason, _, _, _ = self.attempt("codex", codex_events(FENCED_ANSWER))
        self.assertTrue(record["error"].startswith(self.runner.STRICT_JSON_FAILURE_PREFIX))
        self.assertEqual("malformed_json_output", reason)
        # Without the schema the Codex command is the usage-capture command.
        _, _, argv, _, schema_copy = self.attempt(
            "codex", codex_events(COMPACT_ANSWER), schema=False
        )
        self.assertEqual([CODEX_TEXT_COMMAND[0], "--json", *CODEX_TEXT_COMMAND[1:]], argv)
        self.assertIsNone(schema_copy)

    def test_earlier_protocol_commands_are_unchanged(self) -> None:
        command, stdin = self.runner.runner_invocation(
            "claude", "claude", "PROMPT", "claude-sonnet-5", None, "off"
        )
        self.assertEqual(["claude", *CLAUDE_OFF_TEXT_COMMAND], command)
        self.assertEqual("PROMPT", stdin)
        command, _ = self.runner.runner_invocation("codex", "codex", "PROMPT", "gpt-6-sol")
        self.assertEqual(["codex", *CODEX_TEXT_COMMAND], command)

    # Whole-run stubs -------------------------------------------------------

    def run_stub(self, temp: Path, plan: list[str], protocol_path: Path = V15_PROTOCOL_PATH):
        protocol = read_json(protocol_path)
        paths = {name: temp / name for name in ("count", "plan", "argc")}
        paths["plan"].write_text("\n".join(plan) + "\n", encoding="utf-8")
        stub = temp / "stub-runner"
        stub.write_text(PLAN_STUB_TEMPLATE.format(**paths), encoding="utf-8")
        stub.chmod(0o755)
        wrapper = temp / "isolation-wrapper"
        wrapper.write_text('#!/bin/sh\nexec "$@"\n', encoding="utf-8")
        wrapper.chmod(0o755)
        output = temp / "report.json"
        result = subprocess.run(
            [
                sys.executable, str(RUNNER_PATH),
                "--cases", str(V10_CASES_PATH),
                "--protocol", str(protocol_path),
                "--skill-dir", str(self.skill_dir),
                "--case", STUB_CASE,
                "--runner", str(stub),
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
        report = read_json(output)
        self.comparator.load_report(output)
        self.assertEqual(protocol["protocol_id"], report["protocol_id"])
        # A custom runner receives exactly its path: no schema flag.
        self.assertEqual("0", paths["argc"].read_text(encoding="utf-8").strip())
        self.comparator.validate_retry_records(report, protocol["infrastructure_retry"])
        self.comparator.validate_usage_records(report, protocol["usage_capture"])
        self.comparator.validate_output_schema_records(
            report, self.runner.output_schema_policy(protocol)
        )
        invocations = int(paths["count"].read_text(encoding="utf-8").strip())
        return report, report["runs"][0], invocations

    def test_v15_report_records_the_schema_and_never_normalizes(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            report, run, invocations = self.run_stub(Path(temp), ["ok"])
        self.assertEqual(1, invocations)
        self.assertEqual(self.v15["output_schema"], report["output_schema"])
        self.assertEqual(EXPECTED_SCHEMA_SHA256, report["output_schema"]["schema_sha256"])
        self.assertIsNotNone(run["score"])
        for key in ("output_normalization", "output_normalization_summary"):
            self.assertNotIn(key, report)
        self.assertNotIn("output_normalized", run)
        self.assertEqual(self.comparator.RETRY_RUN_KEYS | {"usage"}, set(run))
        # The fence v14 would unwrap is malformed under v15, retried, and unscoreable.
        with tempfile.TemporaryDirectory() as temp:
            report, run, invocations = self.run_stub(
                Path(temp), ["fenced_json", "fenced_json"]
            )
        self.assertEqual(2, invocations)
        self.assertEqual(
            ["malformed_json_output", "malformed_json_output"],
            [attempt["reason"] for attempt in run["attempts"]],
        )
        self.assertIsNone(run["score"])
        self.assertNotIn("output_normalized", run)
        with tempfile.TemporaryDirectory() as temp:
            _, run, invocations = self.run_stub(Path(temp), ["fenced_json", "ok"])
        self.assertEqual(2, invocations)
        self.assertIsNotNone(run["score"])

    def test_v14_report_carries_no_schema(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            report, run, _ = self.run_stub(Path(temp), ["fenced_json"], V14_PROTOCOL_PATH)
        self.assertNotIn("output_schema", report)
        self.assertTrue(run["output_normalized"])
        self.assertIsNotNone(run["score"])

    # Comparator ------------------------------------------------------------

    def test_comparator_validates_output_schema_records(self) -> None:
        policy = self.v15["output_schema"]
        self.comparator.validate_output_schema_records({"runs": []}, None)
        with self.assertRaisesRegex(ValueError, "no enforced output schema"):
            self.comparator.validate_output_schema_records(
                {"runs": [], "output_schema": policy}, None
            )
        self.comparator.validate_output_schema_records(
            {"runs": [], "output_schema": copy.deepcopy(policy)}, policy
        )
        drifted = copy.deepcopy(policy)
        drifted["schema"]["properties"]["findings"]["items"]["properties"]["pattern_id"][
            "enum"
        ].remove("#9c")
        for name, report in {
            "missing": {"runs": []},
            "mode drift": {"runs": [], "output_schema": {**policy, "mode": "advisory"}},
            "schema drift": {"runs": [], "output_schema": drifted},
        }.items():
            with self.subTest(name), self.assertRaisesRegex(ValueError, "output_schema"):
                self.comparator.validate_output_schema_records(report, policy)
        # A self-consistent but different block is refused against the protocol,
        # and a digest that does not match the embedded schema is refused even
        # when the protocol copy carries the same wrong digest.
        wrong_digest = {**policy, "schema_sha256": "0" * 64}
        with self.assertRaisesRegex(ValueError, "digest does not match"):
            self.comparator.validate_output_schema_records(
                {"runs": [], "output_schema": wrong_digest}, wrong_digest
            )
        self.assertIn("output_schema", self.comparator.REPORT_OPTIONAL_KEYS)
        self.assertIsNone(self.runner.output_schema_policy(self.v14))
        self.assertIsNone(self.runner.output_schema_policy(self.v13))

    # Prompts and schedule --------------------------------------------------

    def test_prompts_and_schedule_match_v13(self) -> None:
        for profile in ("full", "catalog-only", "no-skill"):
            self.assertEqual(
                self.runner.prompt_set_digest(
                    self.v10_cases, EXPECTED_CORPUS_SHA256,
                    self.skill_dir, profile,
                    numbered_source_lines=V13_ID in self.runner.NUMBERED_SOURCE_PROTOCOL_IDS,
                ),
                self.runner.prompt_set_digest(
                    self.v10_cases, EXPECTED_CORPUS_SHA256,
                    self.skill_dir, profile,
                    numbered_source_lines=PROTOCOL_ID
                    in self.runner.NUMBERED_SOURCE_PROTOCOL_IDS,
                ),
            )
        self.assertEqual(
            self.runner.build_schedule(self.v10_cases, 5, self.v13["schedule"]["seed"]),
            self.runner.build_schedule(self.v10_cases, 5, self.v15["schedule"]["seed"]),
        )

    # Documentation ---------------------------------------------------------

    def test_readme_documents_preregistration_and_exact_rerun(self) -> None:
        readme = README_PATH.read_text(encoding="utf-8")
        self.assertIn("# Reviewer holdout v15", readme.splitlines()[0])
        self.assertIn("arm comparison `INCONCLUSIVE`, so no skill-lift claim", readme)
        calls = len(self.v10_cases) * 5 * 3
        self.assertEqual(450, calls)
        for contract in (
            f"{calls} scheduled model calls",
            "scripts/evals/reviewer-holdout-v10.json",
            "scripts/evals/reviewer-validation-protocol-v15.json",
            EXPECTED_CASES_FILE_SHA256,
            EXPECTED_CORPUS_SHA256,
            EXPECTED_PROTOCOL_SHA256,
            EXPECTED_SCHEMA_SHA256,
            "Claude Code 2.1.283",
            'claude_permission_mode: "off"',
            "claude-sonnet-5",
            "--compare-arms",
            'test -z "$(git status --porcelain)"',
            "## Why v15 exists",
            "## Enforced output schema",
            "## Infrastructure-retry policy",
            "## Claim limits",
            "6 of 150 full-arm calls",
            "21 of 150 catalog-only calls",
            "4 of 150 no-skill calls",
            "fixed before any v15 call",
            "every arm",
            "structured_output",
            "--json-schema",
            "--output-schema",
            '"max_attempts_per_call": 2',
            "never retried",
        ):
            self.assertIn(contract, readme)
        self.assertNotIn("is being run", readme)
        self.assertEqual(3, readme.count("--repetitions 5"))
        self.assertEqual(4, readme.count('--output "$OUT/'))
        self.assertEqual(3, len(re.findall(r"--arm (full|catalog-only|no-skill) ", readme)))
        self.assertEqual(3, readme.count("--allow-live"))
        self.assertEqual(3, readme.count("--model claude-sonnet-5"))
        self.assertEqual(3, readme.count('--runner claude --runner-path "$CLAUDE_RUNNER"'))
        self.assertEqual(4, readme.count("--protocol scripts/evals/reviewer-validation-protocol-v15.json"))
        self.assertEqual(4, readme.count("--cases scripts/evals/reviewer-holdout-v10.json"))
        self.assertIn(
            "benchmarks/reviewer-holdout-v15/README.md",
            BENCHMARK_DOC_PATH.read_text(encoding="utf-8"),
        )
        changelog = CHANGELOG_PATH.read_text(encoding="utf-8")
        release_section = changelog.split("## [2.0.0]", 1)[1].split("\n## [", 1)[0]
        added = release_section.split("### Added", 1)[1].split("\n### ", 1)[0]
        self.assertIn(PROTOCOL_ID, added)
        self.assertIn("scripts/ci/test-reviewer-holdout-v15.py", added)
        for path in (CI_LOCAL_PATH, CONTRIBUTING_PATH):
            self.assertIn(
                "scripts/ci/test-reviewer-holdout-v15.py", path.read_text(encoding="utf-8")
            )


    def test_run_reports(self) -> None:
        reports = README_PATH.parent / "reports"
        comparison = read_json(reports / "arm-comparison.json")
        self.assertEqual("INCONCLUSIVE", comparison["status"])
        self.assertEqual(
            [("arm_input_incomplete", "catalog-only")],
            [(reason["code"], reason["profile"]) for reason in comparison["status_reasons"]],
        )
        readme = README_PATH.read_text(encoding="utf-8")
        for arm, status, errors in (
            ("full", "FAIL", 0), ("catalog-only", "INCONCLUSIVE", 1), ("no-skill", "FAIL", 0)
        ):
            report = read_json(reports / f"{arm}-claude.json")
            self.assertEqual(EXPECTED_PROTOCOL_SHA256, report["protocol_sha256"], arm)
            self.assertEqual(status, report["status"], arm)
            self.assertEqual(errors, report["summary"]["infrastructure_errors"], arm)
            retry = report["infrastructure_retry_summary"]
            self.assertEqual(0, retry["retries_by_reason"]["malformed_json_output"], arm)
            unique = report["primary_metrics"]["unique"]
            self.assertIn(f"{unique['precision']:.3f} / {unique['recall']:.3f} / {unique['f1']:.3f}", readme)


if __name__ == "__main__":
    unittest.main(verbosity=2)
