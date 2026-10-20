#!/usr/bin/env python3
"""Unchanged-outcome guidance and deterministic stale-state controls. Apache-2.0."""
import asyncio
import json
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[2]
# These guidance checks cover the 2.x pipeline text, archived byte-for-byte in 3.0.0.
SKILL = ROOT / "benchmarks/generator-skill-v2.0.1-archive"


def contract(text):
    start = text.index("## V1 — Primary Outcome")
    end = text.index("## V2 — Assertion Falsification", start)
    rule = " ".join(text[start:end].split())
    for required in (
        "already true before the action",
        "action-specific settled-state evidence",
        "request observation alone",
        "response arrival alone",
        "post-action re-read",
        "transient or fully stubbed state",
        "disabled control",
        "force a click",
        "invent an API call",
        "`CANNOT_VERIFY`",
        "not broaden the approved scenario",
    ):
        if required not in rule:
            raise AssertionError("missing unchanged-outcome safeguard: " + required)


class GuidanceTests(unittest.TestCase):
    def test_rule_and_each_safeguard_removal(self):
        text = (SKILL / "verification-rules.md").read_text()
        contract(text)
        for fragment in ("action-specific settled-state evidence", "response arrival alone", "disabled control", "not broaden the approved scenario"):
            with self.subTest(fragment=fragment), self.assertRaises(AssertionError):
                contract(text.replace(fragment, "", 1))

    def test_evals_cover_race_and_legitimate_no_request(self):
        cases = json.loads((SKILL / "evals/evals.json").read_text())["evals"]
        case = next((c for c in cases if c["id"] == 50), None)
        self.assertIsNotNone(case)
        self.assertTrue(any(a.startswith("True positive:") for a in case["assertions"]))
        self.assertTrue(any(a.startswith("False-positive guard:") for a in case["assertions"]))
        self.assertIn("response arrival alone", case["expected_output"])
        self.assertIn("disabled control", case["expected_output"])

    def test_plan_and_independent_review_keep_completion_requirement(self):
        plan = (SKILL / "scenario-design.md").read_text()
        self.assertIn("- V1 completion:", plan)
        verification = (SKILL / "verification-rules.md").read_text()
        handoff = verification.split("## V6 — Independent Re-review", 1)[1]
        self.assertIn("every approved per-scenario V1 completion field", handoff)
        self.assertIn("applicable V1 subsection", handoff)
        self.assertIn("not the writer's verdicts", handoff)
        for required in (
            "copy its title, action, primary outcome, and `V1 completion` field",
            "starting with its `## V1 — Primary Outcome` heading",
            "An alternate heading above an otherwise exact body is not verbatim",
            "a custom label followed by the V1 body does not pass",
            "inspect the actual outgoing packet",
            "not merely linked or paraphrased",
            "do not count a reviewer `PASS` as V6 evidence",
            "use a fresh read-only reviewer",
            "record V6 `CANNOT_VERIFY` and return `PARTIAL/BLOCKED`",
        ):
            with self.subTest(required=required):
                self.assertIn(required, handoff)


class TimingControls(unittest.IsolatedAsyncioTestCase):
    async def observe(self, broken, settle):
        state = {"servings": 1}
        release = asyncio.Event()

        async def delayed_action():
            await release.wait()
            state["servings"] = 0 if broken else 1

        task = asyncio.create_task(delayed_action())
        try:
            # An unchanged matcher can succeed before this action is processed.
            if not settle:
                return state["servings"] == 1
            release.set()
            await task
            return state["servings"] == 1
        finally:
            release.set()
            await task

    async def test_stale_read_misses_fault_but_settled_read_catches_it(self):
        self.assertTrue(await self.observe(broken=True, settle=False))
        self.assertFalse(await self.observe(broken=True, settle=True))

    async def test_correct_unchanged_state_still_passes_after_settling(self):
        self.assertTrue(await self.observe(broken=False, settle=True))


if __name__ == "__main__":
    unittest.main()
