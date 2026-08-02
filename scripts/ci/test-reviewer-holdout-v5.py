#!/usr/bin/env python3
"""Validate the frozen, neutral public-development v5 reviewer corpus."""

from __future__ import annotations

from collections import Counter
import copy
import hashlib
import importlib.util
import json
from pathlib import Path
import re
import subprocess
import sys
import tempfile
import unittest
from unittest import mock


ROOT = Path(__file__).resolve().parents[2]
CASES_PATH = ROOT / "scripts/evals/reviewer-holdout-v5.json"
PROTOCOL_PATH = ROOT / "scripts/evals/reviewer-validation-protocol-v5.json"
SOURCE_ROOT = ROOT / "scripts/evals/files/holdout-v5"
V4_SOURCE_ROOT = ROOT / "scripts/evals/files/holdout-v4"
RUNNER_PATH = ROOT / "scripts/evals/run-reviewer-holdout.py"
COMPARATOR_PATH = ROOT / "scripts/evals/compare-reviewer-holdouts.py"

EXPECTED_CASES_FILE_SHA256 = "50c828c5e267a683ced73a161a645af0b73f305f6391b6fe0e8ee150ec419849"
EXPECTED_CORPUS_SHA256 = "745bc765fb6f424abe90d6d3fc9a3b85e921472a4cc1291054879af8002e965f"
EXPECTED_PROTOCOL_SHA256 = "f7b8acb8b80d0ae673e0a3291b0bdd7c08d8f3e221dd624226724c9ef3c4b40c"
EXPECTED_SOURCE_TREE_SHA256 = "33f3d5900f4af5dabc922a574e97a979fdcd9405195085430e0eb632aa37e896"
EXPECTED_FAMILIES = {f"#{number}" for number in range(1, 24)} | {"#3b"}
ANSWER_LEADING_TERMS = re.compile(
    r"\b(?:"
    r"anti[- ]?pattern|bad|broken|bug|bypass|false positive|finding|flaky|"
    r"hardcoded|manual|missing|oracle|pattern|smell|swallow|unsafe|"
    r"unprotected|unused|vacuous|weak|zombie"
    r")\b",
    re.IGNORECASE,
)


def family(pattern_id: str) -> str:
    if pattern_id == "#3b":
        return pattern_id
    for prefix in ("#4", "#5", "#8", "#9", "#10"):
        if pattern_id.startswith(prefix):
            return prefix
    return pattern_id


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def source_tree_sha256(root: Path) -> str:
    digest = hashlib.sha256()
    for path in sorted(candidate for candidate in root.rglob("*") if candidate.is_file()):
        digest.update(path.relative_to(root).as_posix().encode("utf-8"))
        digest.update(b"\0")
        digest.update(path.read_bytes())
        digest.update(b"\0")
    return digest.hexdigest()


def load_module(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"cannot load {path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def synthetic_arm_cases() -> list[dict]:
    return [
        {
            "id": "finding-a",
            "framework": "playwright",
            "labels": [
                {
                    "kind": "finding",
                    "pattern_id": "#1",
                    "severity": "P0",
                    "file": "tests/a.spec.ts",
                    "line": 1,
                }
            ],
        },
        {
            "id": "finding-b",
            "framework": "cypress",
            "labels": [
                {
                    "kind": "finding",
                    "pattern_id": "#2",
                    "severity": "P0",
                    "file": "cypress/e2e/b.cy.ts",
                    "line": 2,
                }
            ],
        },
        {
            "id": "clean-a",
            "framework": "playwright",
            "labels": [
                {
                    "kind": "fp_guard",
                    "pattern_id": "#3",
                    "severity": "P0",
                    "file": "tests/c.spec.ts",
                    "line": 3,
                }
            ],
        },
        {
            "id": "clean-b",
            "framework": "cypress",
            "labels": [
                {
                    "kind": "fp_guard",
                    "pattern_id": "#3b",
                    "severity": "P0",
                    "file": "cypress/e2e/d.cy.ts",
                    "line": 4,
                }
            ],
        },
    ]


def synthetic_arm_report(
    comparator,
    profile: str,
    runner: str,
    model: str,
    behavior: str,
    cases: list[dict],
) -> dict:
    predictions_by_case: dict[str, list[dict]] = {}
    for case in cases:
        label = case["labels"][0]
        finding = {
            key: label[key]
            for key in ("pattern_id", "severity", "file", "line")
        }
        if behavior == "strong" and label["kind"] == "finding":
            predictions_by_case[case["id"]] = [finding]
        elif behavior == "weak" and case["id"] in {"clean-a", "clean-b"}:
            predictions_by_case[case["id"]] = [finding]
        else:
            predictions_by_case[case["id"]] = []

    totals = {"tp": 0, "fp": 0, "fn": 0}
    clean_without_prediction = 0
    clean_count = 0
    runs = []
    for case in cases:
        labels = case["labels"]
        expected = {
            (
                label["pattern_id"],
                label["severity"],
                label["file"],
                label["line"],
            )
            for label in labels
            if label["kind"] == "finding"
        }
        predictions = predictions_by_case[case["id"]]
        predicted = {
            (
                finding["pattern_id"],
                finding["severity"],
                finding["file"],
                finding["line"],
            )
            for finding in predictions
        }
        score = {
            "tp": len(predicted & expected),
            "fp": len(predicted - expected),
            "fn": len(expected - predicted),
        }
        for name in totals:
            totals[name] += score[name]
        clean = {label["kind"] for label in labels} == {"fp_guard"}
        if clean:
            clean_count += 1
            clean_without_prediction += not predictions
        for repetition in range(1, 4):
            runs.append(
                {
                    "case": case["id"],
                    "repetition": repetition,
                    "findings": copy.deepcopy(predictions),
                    "score": score.copy(),
                }
            )

    rates = comparator.RUNNER.rates(**totals)
    specificity = clean_without_prediction / clean_count
    runner_identity = (
        "codex-cli 0.146.0"
        if runner == "codex"
        else "2.1.220 (Claude Code)"
    )
    return {
        "prompt_profile": profile,
        "runner": runner,
        "model": model,
        "complete": True,
        "execution_complete": True,
        "status": "PASS" if behavior == "strong" else "FAIL",
        "skill_sha256": "1" * 64,
        "corpus_sha256": "2" * 64,
        "protocol_sha256": "3" * 64,
        "schedule_sha256": "4" * 64,
        "repetitions": 3,
        "evaluator_sha256": "5" * 64,
        "git_revision": "synthetic",
        "git_dirty": False,
        "git_dirty_sha256": "6" * 64,
        "source_read_isolation": "prompt-complete-zero-tools",
        "workspace_integrity": "pre-post-sha256",
        "input_snapshot": "copy-once-temp",
        "model_tool_surface": "none",
        "evidence_scope": "development",
        "runner_identity": runner_identity,
        "runner_executable": f"/opt/frozen/{runner}",
        "prompt_set_sha256": hashlib.sha256(profile.encode()).hexdigest(),
        "primary_metrics": {
            "unique": rates,
            "stability": {"required_hits": 2},
            "p0_per_label_stability": {
                "stable_label_recall": rates["recall"],
            },
            "clean_case_specificity": {"value": specificity},
        },
        "secondary_metrics": {"precision": rates["precision"]},
        "runs": runs,
    }


class ReviewerHoldoutV5Test(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.corpus = json.loads(CASES_PATH.read_text(encoding="utf-8"))
        cls.protocol = json.loads(PROTOCOL_PATH.read_text(encoding="utf-8"))
        cls.cases = cls.corpus["cases"]
        cls.by_id = {case["id"]: case for case in cls.cases}

    def source(self, case_id: str, path: str) -> str:
        return (SOURCE_ROOT / case_id / path).read_text(encoding="utf-8")

    def test_covers_each_stable_family_once_for_findings_and_guards(self) -> None:
        by_kind = {
            kind: [
                label
                for case in self.cases
                for label in case["labels"]
                if label["kind"] == kind
            ]
            for kind in ("finding", "fp_guard")
        }
        for kind, labels in by_kind.items():
            families = [family(label["pattern_id"]) for label in labels]
            self.assertEqual(EXPECTED_FAMILIES, set(families), kind)
            self.assertEqual(len(EXPECTED_FAMILIES), len(families), kind)

    def test_runner_accepts_corpus_schema_and_canonical_severities(self) -> None:
        runner = load_module("reviewer_holdout_v5_runner", RUNNER_PATH)
        _, loaded_cases = runner.load_cases(CASES_PATH)
        self.assertEqual(CASES_PATH, runner.V5_CASES)
        self.assertEqual(PROTOCOL_PATH, runner.V5_PROTOCOL)
        self.assertEqual(self.protocol, runner.load_protocol(PROTOCOL_PATH))
        self.assertNotIn(
            self.protocol["protocol_id"],
            runner.HISTORICAL_DIAGNOSTIC_PROTOCOL_IDS,
        )
        self.assertIn(
            self.protocol["protocol_id"],
            runner.PROVIDER_BALANCED_PROTOCOL_IDS,
        )
        self.assertEqual(
            {
                self.protocol["prompt_arms"]["treatment"],
                *self.protocol["prompt_arms"]["controls"],
            },
            set(runner.PROMPT_SKILL_PROFILES),
        )
        pinned = runner.PINNED_LIVE_INPUTS[(CASES_PATH, PROTOCOL_PATH)]
        self.assertEqual(EXPECTED_CASES_FILE_SHA256, pinned["cases_file_sha256"])
        self.assertEqual(EXPECTED_CORPUS_SHA256, pinned["corpus_sha256"])
        self.assertEqual(EXPECTED_PROTOCOL_SHA256, pinned["protocol_sha256"])
        self.assertEqual(
            runner.corpus_digest(CASES_PATH, loaded_cases),
            EXPECTED_CORPUS_SHA256,
        )
        self.assertTrue(
            runner.runner_identity_matches(
                "codex",
                "codex-cli 0.146.0",
                "codex-cli 0.146.0",
            )
        )
        self.assertTrue(
            runner.runner_identity_matches(
                "claude",
                "2.1.220 (Claude Code)",
                "Claude Code 2.1.220",
            )
        )
        self.assertFalse(
            runner.runner_identity_matches(
                "claude",
                "2.1.145 (Claude Code)",
                "Claude Code 2.1.220",
            )
        )
        self.assertEqual(self.cases, loaded_cases)
        canonical = runner.canonical_severities(ROOT / "skills/e2e-reviewer")
        for case in loaded_cases:
            for label in case["labels"]:
                self.assertEqual(
                    canonical[label["pattern_id"]],
                    label["severity"],
                    label["finding_id"],
                )

    def test_clean_case_specificity_uses_stable_case_level_predictions(self) -> None:
        runner = load_module("reviewer_holdout_v5_specificity", RUNNER_PATH)
        clean_cases = [
            case
            for case in self.cases
            if {label["kind"] for label in case["labels"]} == {"fp_guard"}
        ]
        target = clean_cases[0]
        guard = target["labels"][0]
        stable_guard_prediction = {
            "pattern_id": guard["pattern_id"],
            "severity": guard["severity"],
            "file": guard["file"],
            "line": guard["line"],
        }
        runs = []
        for case in self.cases:
            for repetition in range(1, 4):
                findings = (
                    [stable_guard_prediction]
                    if case["id"] == target["id"] and repetition <= 2
                    else []
                )
                runs.append(
                    {
                        "case": case["id"],
                        "repetition": repetition,
                        "findings": findings,
                        "score": {},
                    }
                )
        specificity = runner.primary_metrics(
            self.cases,
            runs,
            3,
            "strict-majority",
        )["clean_case_specificity"]
        self.assertEqual(8, specificity["clean_cases"])
        self.assertEqual(7, specificity["cases_without_stable_predictions"])
        self.assertEqual(0.875, specificity["value"])
        self.assertTrue(
            specificity["by_case"][target["id"]]["has_stable_prediction"]
        )

    def test_provider_families_are_equal_weighted_after_within_family_mean(
        self,
    ) -> None:
        comparator = load_module(
            "reviewer_holdout_v5_comparator",
            COMPARATOR_PATH,
        )

        def report(runner: str, model: str, precision: float) -> dict:
            return {
                "runner": runner,
                "model": model,
                "primary_metrics": {
                    "unique": {
                        "precision": precision,
                        "recall": precision,
                        "f1": precision,
                    },
                    "p0_per_label_stability": {
                        "stable_label_recall": precision,
                    },
                    "clean_case_specificity": {"value": precision},
                },
                "secondary_metrics": {"precision": precision},
            }

        aggregation = comparator.provider_family_aggregation(
            [
                report("codex", "gpt-5.6-sol", 1.0),
                report("claude", "claude-opus-5", 1.0),
                report("claude", "claude-fable-5", 0.0),
            ]
        )
        self.assertEqual(
            "mean-within-provider-family-then-equal-weight-families",
            aggregation["method"],
        )
        self.assertEqual(2, aggregation["provider_family_denominator"])
        self.assertEqual(
            1,
            aggregation["families"]["openai"]["configuration_count"],
        )
        self.assertEqual(
            2,
            aggregation["families"]["anthropic"]["configuration_count"],
        )
        self.assertEqual(
            0.5,
            aggregation["families"]["anthropic"]["metrics"][
                "stable_precision"
            ]["value"],
        )
        self.assertEqual(
            0.75,
            aggregation["equal_weighted_metrics"]["stable_precision"]["value"],
        )
        self.assertNotEqual(
            (1.0 + 1.0 + 0.0) / 3,
            aggregation["equal_weighted_metrics"]["stable_precision"]["value"],
        )

    def test_exact_source_lines_and_manifest_coverage_match(self) -> None:
        manifested_sources: set[Path] = set()
        finding_sources: set[Path] = set()
        guard_sources: set[Path] = set()
        for case in self.cases:
            sources = {
                entry["path"]: ROOT / "scripts/evals" / entry["source"]
                for entry in case["source_files"]
            }
            self.assertGreaterEqual(len(sources), 2, case["id"])
            self.assertTrue(
                any(
                    path.endswith((".spec.ts", ".cy.ts"))
                    for path in sources
                ),
                case["id"],
            )
            self.assertTrue(
                any(
                    not path.endswith((".spec.ts", ".cy.ts"))
                    for path in sources
                ),
                case["id"],
            )
            manifested_sources.update(sources.values())
            for label in case["labels"]:
                source = sources[label["file"]]
                lines = source.read_text(encoding="utf-8").splitlines()
                self.assertGreaterEqual(label["line"], 1, label["finding_id"])
                self.assertLessEqual(label["line"], len(lines), label["finding_id"])
                self.assertEqual(
                    label["source_line"],
                    lines[label["line"] - 1].strip(),
                    label["finding_id"],
                )
                target = finding_sources if label["kind"] == "finding" else guard_sources
                target.add(source)

        actual_sources = {
            candidate for candidate in SOURCE_ROOT.rglob("*") if candidate.is_file()
        }
        self.assertEqual(actual_sources, manifested_sources)
        self.assertTrue(finding_sources.isdisjoint(guard_sources))

    def test_clean_cases_are_separate_and_comprise_forty_percent(self) -> None:
        kinds_by_case = [
            {label["kind"] for label in case["labels"]}
            for case in self.cases
        ]
        self.assertTrue(all(len(kinds) == 1 for kinds in kinds_by_case))
        clean = [
            case
            for case, kinds in zip(self.cases, kinds_by_case)
            if kinds == {"fp_guard"}
        ]
        ratio = len(clean) / len(self.cases)
        self.assertEqual(20, len(self.cases))
        self.assertEqual(12, len(self.cases) - len(clean))
        self.assertEqual(8, len(clean))
        self.assertGreaterEqual(ratio, 0.30)
        self.assertLessEqual(ratio, 0.50)
        self.assertEqual(0.40, ratio)

    def test_finding_and_clean_cases_are_framework_balanced(self) -> None:
        counts = Counter(
            (
                case["labels"][0]["kind"],
                case["framework"],
            )
            for case in self.cases
        )
        self.assertEqual(counts[("finding", "playwright")], 6)
        self.assertEqual(counts[("finding", "cypress")], 6)
        self.assertEqual(counts[("fp_guard", "playwright")], 4)
        self.assertEqual(counts[("fp_guard", "cypress")], 4)
        framework_counts = Counter(case["framework"] for case in self.cases)
        self.assertEqual(
            {"playwright": 10, "cypress": 10},
            dict(framework_counts),
        )

    def test_label_identifiers_and_splits_are_v5_only(self) -> None:
        identifiers = [
            label["finding_id"]
            for case in self.cases
            for label in case["labels"]
        ]
        self.assertEqual(48, len(identifiers))
        self.assertEqual(48, len(set(identifiers)))
        self.assertTrue(
            all(re.fullmatch(r"V5-(?:G)?[0-9]{2,3}", value) for value in identifiers)
        )
        self.assertEqual(
            {"public-development-v5"},
            {case["split"] for case in self.cases},
        )

    def test_positive_oracle_repairs_are_present(self) -> None:
        pw_a02 = self.source("pw-a02", "tests/activity.spec.ts")
        self.assertEqual(2, pw_a02.count("await activity.open();"))
        self.assertNotIn("page.goto('/activity')", pw_a02)

        pw_a03_page = self.source("pw-a03", "pages/billing-page.ts")
        pw_a03_spec = self.source("pw-a03", "tests/billing.spec.ts")
        self.assertIn("async open()", pw_a03_page)
        self.assertIn("await billing.open();", pw_a03_spec)
        self.assertNotIn("page.goto('/billing')", pw_a03_spec)
        self.assertEqual(1, pw_a03_spec.count("await page.goto("))

        pw_a04_page = self.source("pw-a04", "pages/profile-page.ts")
        pw_a04_spec = self.source("pw-a04", "tests/profile.spec.ts")
        self.assertNotIn("setDisplayName", pw_a04_page)
        self.assertIn(
            "keeps the profile screen visible after editing the display name",
            pw_a04_spec,
        )
        self.assertIn(
            "await expect(page.getByRole("
            "'heading', { name: 'Profile', exact: true })).toBeVisible();",
            pw_a04_spec,
        )
        self.assertIn("expect(banner).toBeVisible();", pw_a04_spec)
        self.assertIn(
            "page.getByRole('button', { name: 'Reload profile', exact: true }).click();",
            pw_a04_spec,
        )

        pw_a05 = self.source("pw-a05", "tests/preferences.spec.ts")
        self.assertFalse((SOURCE_ROOT / "pw-a05/pages/preferences-page.ts").exists())
        self.assertNotIn("PreferencesPage", pw_a05)
        self.assertIn("await page.goto('/preferences');", pw_a05)
        self.assertIn("await page.selectOption('#locale', 'ko-KR');", pw_a05)

        pw_a06 = self.source("pw-a06", "tests/search.spec.ts")
        self.assertFalse((SOURCE_ROOT / "pw-a06/pages/search-page.ts").exists())
        self.assertNotIn("SearchPage", pw_a06)
        self.assertIn("await page.goto('/search');", pw_a06)
        self.assertIn("test('shows tea in the search results'", pw_a06)
        self.assertIn("toContainText('tea')", pw_a06)
        self.assertIn("} catch {", pw_a06)

        cy_a03 = self.source("cy-a03", "cypress/e2e/search.cy.ts")
        self.assertIn("reaches the ready state after refresh", cy_a03)
        self.assertIn("cy.wait(600);", cy_a03)
        self.assertIn(".click()", cy_a03)

        cy_a04_spec = self.source("cy-a04", "cypress/e2e/account.cy.ts")
        cy_a04_page = self.source("cy-a04", "cypress/pages/account-page.ts")
        self.assertNotIn("AccountPage", cy_a04_spec)
        self.assertIn(".type(Cypress.env('E2E_EMAIL'))", cy_a04_spec)
        self.assertEqual(1, cy_a04_spec.count("'Summer2026!'"))
        self.assertNotIn("open()", cy_a04_page)
        self.assertIn("openHistoryPanel()", cy_a04_page)

        cy_a05_spec = self.source("cy-a05", "cypress/e2e/contacts.cy.ts")
        cy_a05_service = self.source("cy-a05", "src/contact-service.ts")
        cy_a05_component = self.source("cy-a05", "src/ContactEditor.tsx")
        self.assertIn("import { nextContactName }", cy_a05_spec)
        self.assertIn("const name = nextContactName();", cy_a05_spec)
        self.assertIn("let contactSequence = 0;", cy_a05_service)
        self.assertIn('data-cy="save"', cy_a05_component)
        self.assertIn("onClick={() => void createContact(name)}", cy_a05_component)

        cy_a06_spec = self.source("cy-a06", "cypress/e2e/board.cy.ts")
        cy_a06_component = self.source("cy-a06", "src/Board.tsx")
        self.assertIn('data-cy="lane-done" onDrop={moveToDone}', cy_a06_component)
        self.assertLess(
            cy_a06_component.index("setLane('done');"),
            cy_a06_component.index("void fetch("),
        )
        self.assertIn(
            "cy.intercept('PATCH', '/api/cards/7', { statusCode: 204 });",
            cy_a06_spec,
        )
        self.assertNotIn(".as('moveCard')", cy_a06_spec)
        self.assertNotIn("cy.wait('@moveCard')", cy_a06_spec)
        self.assertIn("trigger('drop')", cy_a06_spec)
        self.assertIn("lane === 'done' ? card : null", cy_a06_component)

    def test_clean_oracle_repairs_are_present(self) -> None:
        pw_c01 = self.source("pw-c01", "tests/orders.spec.ts")
        self.assertNotIn("page.goto('/orders')", pw_c01)
        self.assertEqual(3, pw_c01.count("await orders.open();"))
        self.assertIn(".click().catch((error) => {", pw_c01)
        self.assertIn("toHaveText(/Closed|Unavailable/)", pw_c01)
        self.assertIn("await expect.poll(async () => (", pw_c01)

        for case_id in ("pw-c02", "pw-c04"):
            auth = self.source(case_id, "auth.setup.ts")
            self.assertLess(
                auth.index("await expect(page).toHaveURL('/member');"),
                auth.index("storageState"),
            )
            self.assertLess(auth.index("Member overview"), auth.index("storageState"))

        pw_c02 = self.source("pw-c02", "tests/theme.spec.ts")
        self.assertNotIn(".isVisible()", pw_c02)
        self.assertIn("await expect.poll(", pw_c02)
        self.assertIn(
            "() => getComputedStyle(document.body).getPropertyValue('--theme-name'),",
            pw_c02,
        )
        self.assertIn("await expect(drawer).toBeVisible();", pw_c02)
        self.assertIn("await expect(drawer).toBeHidden();", pw_c02)
        self.assertLess(
            pw_c02.index("await expect(drawer).toBeVisible();"),
            pw_c02.index("Close drawer"),
        )

        pw_c03_page = self.source("pw-c03", "pages/profile-page.ts")
        pw_c03_spec = self.source("pw-c03", "tests/profile.spec.ts")
        self.assertNotIn("page.goto(", pw_c03_spec)
        for call in (
            "await profile.setName('Mina');",
            "await profile.save();",
            "await profile.continue();",
            "await profile.refresh();",
        ):
            self.assertIn(call, pw_c03_spec)
        self.assertIn("await Promise.all([", pw_c03_page)
        self.assertIn(
            "this.page.getByRole('button', { name: 'Refresh', exact: true }).click(),",
            pw_c03_page,
        )

        cy_c01 = self.source("cy-c01", "cypress/e2e/editor.cy.ts")
        self.assertLess(
            cy_c01.index("cy.get('[data-cy=editor]').should('be.visible');"),
            cy_c01.index("cy.get('[data-cy=close]').click();"),
        )
        self.assertLess(
            cy_c01.index("cy.get('[data-cy=close]').click();"),
            cy_c01.index("cy.get('[data-cy=editor]').should('not.exist');"),
        )

        cy_c03_spec = self.source("cy-c03", "cypress/e2e/account.cy.ts")
        cy_c03_page = self.source("cy-c03", "cypress/pages/account-page.ts")
        cy_c03_state = self.source("cy-c03", "cypress/support/state.ts")
        for method in ("open", "fill", "submit"):
            self.assertIn(f"account.{method}(", cy_c03_spec)
            self.assertIn(f"{method}(", cy_c03_page)
        self.assertNotRegex(cy_c03_state, r"(?m)^let ")
        self.assertIn("export interface AccountFields {", cy_c03_state)
        self.assertIn("import type { AccountFields }", cy_c03_page)
        self.assertIn("password: 'short',", cy_c03_spec)
        self.assertNotIn("ScenarioState", cy_c03_spec + cy_c03_state)

        for case_id in ("cy-c02",):
            v5_files = {
                path.relative_to(SOURCE_ROOT / case_id): path.read_bytes()
                for path in (SOURCE_ROOT / case_id).rglob("*")
                if path.is_file()
            }
            v4_files = {
                path.relative_to(V4_SOURCE_ROOT / case_id): path.read_bytes()
                for path in (V4_SOURCE_ROOT / case_id).rglob("*")
                if path.is_file()
            }
            self.assertEqual(v4_files, v5_files, case_id)

        cy_c04 = self.source("cy-c04", "cypress/e2e/profile.cy.ts")
        self.assertIn(
            "cy.intercept('POST', '/api/profile', { statusCode: 201 }).as('saveProfile');",
            cy_c04,
        )
        self.assertIn(
            "cy.intercept('PATCH', '/api/cards/7', { statusCode: 204 }).as('moveCard');",
            cy_c04,
        )

    def test_source_surface_contains_no_answer_leading_vocabulary(self) -> None:
        for path in sorted(candidate for candidate in SOURCE_ROOT.rglob("*") if candidate.is_file()):
            relative = path.relative_to(SOURCE_ROOT).as_posix()
            text = path.read_text(encoding="utf-8")
            self.assertIsNone(ANSWER_LEADING_TERMS.search(relative), relative)
            self.assertIsNone(ANSWER_LEADING_TERMS.search(text), relative)
            self.assertNotRegex(text, r"(?m)^\s*(?://|/\*|\*)")
            self.assertNotRegex(text, r"#[0-9]+b?\b")

    def test_case_identifiers_and_paths_are_neutral(self) -> None:
        for case in self.cases:
            self.assertRegex(case["id"], r"^(?:pw|cy)-[ac][0-9]{2}$")
            self.assertIsNone(ANSWER_LEADING_TERMS.search(case["id"]))
            for source in case["source_files"]:
                self.assertTrue(source["source"].startswith("files/holdout-v5/"))
                self.assertIsNone(ANSWER_LEADING_TERMS.search(source["source"]))

    def test_protocol_declares_scope_balance_repetitions_and_limits(self) -> None:
        protocol = self.protocol
        self.assertEqual(
            {
                "schema_version",
                "protocol_id",
                "schedule",
                "stability",
                "execution_identity",
                "prompt_arms",
                "arm_comparison",
                "host_matrix",
                "confidence_intervals",
                "decision",
                "cross_host_decision",
            },
            set(protocol),
        )
        self.assertEqual(protocol["protocol_id"], "reviewer-holdout-v5")
        self.assertEqual(
            protocol["schedule"]["evidence_scope"],
            "public-development",
        )
        self.assertEqual(protocol["schedule"]["seed"], 20260801)
        self.assertEqual(protocol["schedule"]["default_repetitions"], 3)
        self.assertEqual(protocol["schedule"]["release_repetitions"], 3)
        self.assertEqual(protocol["stability"]["minimum_repetitions"], 3)
        self.assertEqual(
            protocol["prompt_arms"],
            {
                "treatment": "full",
                "controls": ["catalog-only", "no-skill"],
                "shared_output_legend": True,
                "no_skill_is_taxonomy_free": False,
                "comparison_unit": "separate-complete-host-matrix",
                "matrix_requirement": (
                    "Run a separate complete host matrix for full, catalog-only, "
                    "and no-skill."
                ),
            },
        )
        self.assertEqual(
            {
                (entry["runner"], entry["model"])
                for entry in protocol["host_matrix"]
            },
            {
                ("codex", "gpt-5.6-sol"),
                ("claude", "claude-opus-5"),
                ("claude", "claude-fable-5"),
            },
        )
        self.assertEqual(
            protocol["decision"]["thresholds"]["clean_case_specificity_min"],
            0.95,
        )
        identity = protocol["execution_identity"]
        self.assertTrue(identity["require_explicit_runner_path"])
        self.assertEqual(
            identity["expected_cli_versions"],
            {
                "codex": "codex-cli 0.146.0",
                "claude": "Claude Code 2.1.220",
            },
        )
        self.assertIn("provenance", identity["attestation_limit"])
        self.assertIn("not cryptographic attestation", identity["attestation_limit"])
        self.assertNotRegex(json.dumps(identity), r"/Users/|/home/|sha256|SHA-256")
        self.assertIn(
            "equal top-level weight",
            protocol["cross_host_decision"]["aggregation_intent"],
        )
        arm_comparison = protocol["arm_comparison"]
        self.assertEqual("full", arm_comparison["treatment"])
        self.assertEqual(
            ["catalog-only", "no-skill"],
            arm_comparison["controls"],
        )
        self.assertEqual(
            "exact-three-profiles-by-three-hosts",
            arm_comparison["required_matrix"],
        )
        self.assertTrue(
            arm_comparison["requires_each_control_comparison_pass"],
        )
        self.assertEqual(
            "three-sequence-cyclic-latin-square-interleaved-by-round",
            arm_comparison["execution_order_design"],
        )
        self.assertEqual(
            [
                ("full", "codex", "gpt-5.6-sol"),
                ("catalog-only", "claude", "claude-opus-5"),
                ("no-skill", "claude", "claude-fable-5"),
                ("catalog-only", "codex", "gpt-5.6-sol"),
                ("no-skill", "claude", "claude-opus-5"),
                ("full", "claude", "claude-fable-5"),
                ("no-skill", "codex", "gpt-5.6-sol"),
                ("full", "claude", "claude-opus-5"),
                ("catalog-only", "claude", "claude-fable-5"),
            ],
            [
                (
                    step["prompt_profile"],
                    step["runner"],
                    step["model"],
                )
                for step in arm_comparison["execution_order"]
            ],
        )
        self.assertEqual(
            list(range(1, 10)),
            [step["ordinal"] for step in arm_comparison["execution_order"]],
        )
        self.assertEqual(
            43_200,
            arm_comparison["maximum_matrix_elapsed_seconds"],
        )
        self.assertTrue(
            arm_comparison["requires_sequential_non_overlapping_execution"],
        )
        self.assertEqual(
            "first-start-to-last-completion",
            arm_comparison["matrix_elapsed_basis"],
        )
        self.assertIn(
            "identify or freeze provider backend revisions",
            arm_comparison["temporal_validity_limit"],
        )
        self.assertEqual(
            "mean-within-provider-family-then-equal-weight-families",
            arm_comparison["provider_aggregation"],
        )
        self.assertEqual(
            {
                "stable_f1_delta_min": 0.05,
                "stable_f1_delta_ci95_lower_min": 0.01,
                "stable_precision_delta_min": -0.02,
                "stable_recall_delta_min": -0.02,
                "clean_case_specificity_delta_min": 0,
                "repeated_precision_delta_min": 0,
            },
            arm_comparison["decision"]["thresholds"],
        )
        self.assertEqual(
            {
                "method": "paired-stratified-case-bootstrap",
                "seed": 20260801,
                "iterations": 10_000,
                "confidence": 0.95,
                "strata": ["finding-cases", "clean-cases"],
                "percentile_method": "nearest-rank",
                "metrics": [
                    "stable_precision",
                    "stable_recall",
                    "stable_f1",
                    "clean_case_specificity",
                ],
                "interpretation_limit": (
                    "Bootstrap intervals describe case-resampling sensitivity on this "
                    "fixed public case set. They do not quantify model-run "
                    "stochasticity and are not population confidence intervals, "
                    "independent replications, or release-grade causal inference."
                ),
            },
            arm_comparison["uncertainty"],
        )
        self.assertEqual(
            "No skill-lift claim is allowed.",
            arm_comparison["claim_policy"]["fail"],
        )
        self.assertEqual(
            "No skill-lift claim is allowed.",
            arm_comparison["claim_policy"]["inconclusive"],
        )
        self.assertIn(
            "never as a causal or partial skill-lift claim",
            arm_comparison["claim_policy"]["partial_results"],
        )
        limits = protocol["decision"]["point_estimate_limits"].lower()
        for required in (
            "descriptive",
            "confidence intervals",
            "public and inspectable",
            "blind evaluation",
            "generalization",
            "not established",
        ):
            self.assertIn(required, limits)

    def synthetic_arm_matrix(
        self,
        comparator,
        *,
        treatment_behavior: str = "strong",
        control_behavior: str = "weak",
    ) -> tuple[list[dict], list[dict], dict]:
        cases = synthetic_arm_cases()
        protocol = copy.deepcopy(self.protocol)
        behaviors = {
            "full": treatment_behavior,
            "catalog-only": control_behavior,
            "no-skill": control_behavior,
        }
        reports = [
            synthetic_arm_report(
                comparator,
                profile,
                host["runner"],
                host["model"],
                behaviors[profile],
                cases,
            )
            for profile in ("full", "catalog-only", "no-skill")
            for host in protocol["host_matrix"]
        ]
        reports_by_configuration = {
            (
                report["prompt_profile"],
                report["runner"],
                report["model"],
            ): report
            for report in reports
        }
        for step in protocol["arm_comparison"]["execution_order"]:
            report = reports_by_configuration[
                (
                    step["prompt_profile"],
                    step["runner"],
                    step["model"],
                )
            ]
            report["started_at"] = (
                f"2026-08-01T00:00:{step['ordinal'] - 1:02d}+00:00"
            )
            report["created_at"] = (
                f"2026-08-01T00:00:{step['ordinal']:02d}+00:00"
            )
        return reports, cases, protocol

    def compare_synthetic_arm_matrix(
        self,
        comparator,
        reports: list[dict],
        cases: list[dict],
        protocol: dict,
    ) -> dict:
        with (
            mock.patch.object(
                comparator,
                "recompute_report",
                side_effect=lambda report, *_args, **_kwargs: report,
            ),
            mock.patch.object(
                comparator,
                "compare_reports",
                return_value={
                    "status": "PASS",
                    "status_reasons": [],
                    "metrics": {},
                },
            ),
        ):
            return comparator.compare_arm_reports(
                reports,
                cases,
                "a" * 64,
                protocol,
                "b" * 64,
                "public",
                "development",
            )

    def test_arm_comparison_passes_only_complete_lift_matrix(self) -> None:
        comparator = load_module(
            "reviewer_holdout_v5_arm_pass",
            COMPARATOR_PATH,
        )
        reports, cases, protocol = self.synthetic_arm_matrix(comparator)
        first = self.compare_synthetic_arm_matrix(
            comparator,
            reports,
            cases,
            protocol,
        )
        second = self.compare_synthetic_arm_matrix(
            comparator,
            reports,
            cases,
            protocol,
        )
        self.assertEqual("PASS", first["status"])
        self.assertTrue(first["skill_lift_claim_eligible"])
        self.assertEqual(
            first["metrics"]["uncertainty"],
            second["metrics"]["uncertainty"],
        )
        self.assertEqual(
            "exact-three-profiles-by-three-hosts",
            first["metrics"]["comparison_unit"],
        )
        self.assertEqual(
            first["metrics"]["execution_order"]["required"],
            first["metrics"]["execution_order"]["observed"],
        )
        self.assertLessEqual(
            first["metrics"]["execution_order"]["elapsed_seconds"],
            first["metrics"]["execution_order"]["maximum_elapsed_seconds"],
        )
        for control in ("catalog-only", "no-skill"):
            lift = first["metrics"]["lift"][control]
            self.assertTrue(lift["passed"])
            self.assertGreaterEqual(lift["point_deltas"]["stable_f1"], 0.05)
            self.assertGreaterEqual(
                lift["paired_bootstrap_ci95"]["stable_f1"]["lower"],
                0.01,
            )
            self.assertTrue(
                all(check["passed"] for check in lift["decision_checks"])
            )

    def test_nearest_rank_uses_exact_preregistered_percentile_ranks(self) -> None:
        comparator = load_module(
            "reviewer_holdout_v5_nearest_rank",
            COMPARATOR_PATH,
        )
        values = list(range(1, 10_001))
        self.assertEqual(250, comparator.nearest_rank(values, 0.025))
        self.assertEqual(9_750, comparator.nearest_rank(values, 0.975))

    def test_comparator_snapshots_corpus_and_rejects_later_source_mutation(
        self,
    ) -> None:
        comparator = load_module(
            "reviewer_holdout_v5_snapshot",
            COMPARATOR_PATH,
        )
        with (
            tempfile.TemporaryDirectory() as source_temp,
            tempfile.TemporaryDirectory() as snapshot_temp,
        ):
            source_root = Path(source_temp)
            source_path = source_root / "files/example.ts"
            source_path.parent.mkdir()
            source_path.write_text("export const value = 1;\n", encoding="utf-8")
            cases_path = source_root / "cases.json"
            cases_payload = {
                "cases": [
                    {
                        "source_files": [
                            {
                                "source": "files/example.ts",
                            }
                        ]
                    }
                ]
            }
            cases_path.write_text(
                json.dumps(cases_payload),
                encoding="utf-8",
            )
            snapshot_cases, captured = comparator.snapshot_corpus_inputs(
                cases_path,
                Path(snapshot_temp),
            )
            self.assertEqual(cases_path.read_bytes(), snapshot_cases.read_bytes())
            self.assertEqual(
                source_path.read_bytes(),
                (Path(snapshot_temp) / "files/example.ts").read_bytes(),
            )
            source_path.write_text(
                "export const value = 2;\n",
                encoding="utf-8",
            )
            with self.assertRaisesRegex(ValueError, "input changed"):
                comparator.verify_input_digests(captured)

    def test_comparator_rejects_evaluator_source_drift(self) -> None:
        comparator = load_module(
            "reviewer_holdout_v5_evaluator_pin",
            COMPARATOR_PATH,
        )
        expected = comparator.EVALUATOR_SHA256_AT_IMPORT
        comparator.verify_evaluator_digest(expected)
        with (
            mock.patch.object(
                comparator.RUNNER,
                "evaluator_digest",
                return_value="0" * 64,
            ),
            self.assertRaisesRegex(ValueError, "evaluator changed"),
        ):
            comparator.verify_evaluator_digest(expected)

    def test_arm_comparison_fail_forbids_claim_when_there_is_no_lift(self) -> None:
        comparator = load_module(
            "reviewer_holdout_v5_arm_fail",
            COMPARATOR_PATH,
        )
        reports, cases, protocol = self.synthetic_arm_matrix(
            comparator,
            control_behavior="strong",
        )
        result = self.compare_synthetic_arm_matrix(
            comparator,
            reports,
            cases,
            protocol,
        )
        self.assertEqual("FAIL", result["status"])
        self.assertFalse(result["skill_lift_claim_eligible"])
        self.assertEqual(
            "No skill-lift claim is allowed.",
            result["claim_policy"]["fail"],
        )
        self.assertTrue(
            any(
                reason["code"] == "arm_lift_threshold_not_met"
                and reason["metric"] == "stable_f1_delta_min"
                for reason in result["status_reasons"]
            )
        )

    def test_arm_comparison_rejects_partial_duplicate_and_identity_drift(
        self,
    ) -> None:
        comparator = load_module(
            "reviewer_holdout_v5_arm_inconclusive",
            COMPARATOR_PATH,
        )
        reports, cases, protocol = self.synthetic_arm_matrix(comparator)
        scenarios = {
            "missing": reports[:-1],
            "duplicate": [*reports[:-1], copy.deepcopy(reports[0])],
            "runner-path-drift": copy.deepcopy(reports),
            "cross-model-runner-drift": copy.deepcopy(reports),
            "execution-order-drift": copy.deepcopy(reports),
            "execution-overlap": copy.deepcopy(reports),
            "elapsed-window": copy.deepcopy(reports),
            "long-first-cell": copy.deepcopy(reports),
        }
        scenarios["runner-path-drift"][3]["runner_executable"] = (
            "/opt/frozen/codex-different"
        )
        for report in scenarios["cross-model-runner-drift"]:
            if report["model"] == "claude-fable-5":
                report["runner_executable"] = "/opt/frozen/claude-fable"
        (
            scenarios["execution-order-drift"][0]["started_at"],
            scenarios["execution-order-drift"][4]["started_at"],
        ) = (
            scenarios["execution-order-drift"][4]["started_at"],
            scenarios["execution-order-drift"][0]["started_at"],
        )
        scenarios["execution-overlap"][4]["started_at"] = (
            "2026-08-01T00:00:00.500000+00:00"
        )
        scenarios["elapsed-window"][5]["created_at"] = (
            "2026-08-02T00:00:09+00:00"
        )
        scenarios["long-first-cell"][0]["started_at"] = (
            "2026-07-31T11:59:59+00:00"
        )
        for name, scenario in scenarios.items():
            with self.subTest(name=name):
                result = self.compare_synthetic_arm_matrix(
                    comparator,
                    scenario,
                    cases,
                    protocol,
                )
                self.assertEqual("INCONCLUSIVE", result["status"])
                self.assertFalse(result["skill_lift_claim_eligible"])
                self.assertIsNone(result["metrics"])
                self.assertEqual(
                    "No skill-lift claim is allowed.",
                    result["claim_policy"]["inconclusive"],
                )

    def test_comparator_cli_exposes_frozen_arm_mode(self) -> None:
        result = subprocess.run(
            [sys.executable, str(COMPARATOR_PATH), "--help"],
            cwd=ROOT,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            timeout=30,
            check=False,
        )
        self.assertEqual(0, result.returncode, result.stdout)
        self.assertIn("--compare-arms", result.stdout)

    def test_comparator_refuses_to_overwrite_benchmark_inputs(self) -> None:
        result = subprocess.run(
            [
                sys.executable,
                str(COMPARATOR_PATH),
                "--cases",
                str(CASES_PATH),
                "--protocol",
                str(PROTOCOL_PATH),
                "--output",
                str(CASES_PATH),
                "/tmp/nonexistent-reviewer-report.json",
            ],
            cwd=ROOT,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            timeout=30,
            check=False,
        )
        self.assertEqual(2, result.returncode, result.stdout)
        self.assertIn(
            "comparison output must not overwrite a benchmark input",
            result.stdout,
        )

    def test_protocol_requires_explicit_runner_path_before_live_execution(self) -> None:
        result = subprocess.run(
            [
                sys.executable,
                str(RUNNER_PATH),
                "--cases",
                str(CASES_PATH),
                "--protocol",
                str(PROTOCOL_PATH),
                "--runner",
                "codex",
                "--model",
                "gpt-5.6-sol",
                "--allow-live",
            ],
            cwd=ROOT,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            timeout=30,
            check=False,
        )
        self.assertEqual(2, result.returncode, result.stdout)
        self.assertIn(
            "requires an explicit --runner-path",
            result.stdout,
        )

    def test_frozen_artifact_digests_are_deterministic(self) -> None:
        self.assertEqual(sha256(CASES_PATH), sha256(CASES_PATH))
        self.assertEqual(sha256(PROTOCOL_PATH), sha256(PROTOCOL_PATH))
        self.assertEqual(source_tree_sha256(SOURCE_ROOT), source_tree_sha256(SOURCE_ROOT))
        runner = load_module("reviewer_holdout_v5_digest", RUNNER_PATH)
        _, loaded_cases = runner.load_cases(CASES_PATH)
        self.assertEqual(EXPECTED_CASES_FILE_SHA256, sha256(CASES_PATH))
        self.assertEqual(
            EXPECTED_CORPUS_SHA256,
            runner.corpus_digest(CASES_PATH, loaded_cases),
        )
        self.assertEqual(EXPECTED_PROTOCOL_SHA256, sha256(PROTOCOL_PATH))
        self.assertEqual(EXPECTED_SOURCE_TREE_SHA256, source_tree_sha256(SOURCE_ROOT))


if __name__ == "__main__":
    unittest.main(verbosity=2)
