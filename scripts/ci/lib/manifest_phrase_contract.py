# SPDX-License-Identifier: Apache-2.0
"""Canonical manifest phrase contract keyed by checked reviewer ID/title."""

from __future__ import annotations


# (pattern ID, canonical Quick Reference title, manifest severity group,
# user-facing manifest phrase)
MANIFEST_PATTERN_PHRASES = (
    ("1", "Name-Assertion", "P0", "name-assertion mismatch"),
    ("2", "Missing Then", "P0", "missing Then"),
    ("3", "Error Swallowing", "P0", "error swallowing"),
    (
        "3b",
        "Cypress uncaught:exception suppression",
        "P0",
        "Cypress uncaught:exception suppression",
    ),
    (
        "4",
        "Vacuous / Retry-Weakening Assertions",
        "P0",
        "vacuous/non-retrying assertions",
    ),
    ("5", "Bypass Patterns", "P0", "bypass patterns"),
    ("7", "Focused Test Leak", "P0", "focused test leak"),
    ("8", "Missing Assertion", "P0", "missing assertions"),
    ("12", "Missing Auth Setup", "P0", "missing auth setup"),
    ("6", "Raw DOM Queries", "P1", "raw DOM queries"),
    ("9", "Hard-coded Sleeps", "P1", "hard-coded sleeps"),
    ("10", "Flaky Test Patterns", "P1", "flaky test patterns"),
    ("13", "Inconsistent POM Usage", "P1", "inconsistent POM usage"),
    ("14", "Hardcoded Credentials", "P1", "hardcoded credentials"),
    ("15", "Missing await on expect", "P1", "missing await on expect"),
    ("16", "Missing await on action", "P1", "missing await on action"),
    (
        "17",
        "Discouraged direct Page selector API",
        "P1",
        "direct page action API",
    ),
    ("18", "`expect.soft()` dependency leak", "P1", "expect.soft overuse"),
    (
        "19",
        "Module-Level Mutable State",
        "P1",
        "module-level mutable state in test utilities",
    ),
    (
        "20",
        "Unmocked Real-Backend Writes",
        "P1",
        "unmocked real-backend writes",
    ),
    (
        "22",
        "Optimistic UI Without Call Proof",
        "P1",
        "optimistic UI without call proof",
    ),
    ("11", "YAGNI + Zombie Specs", "P2", "YAGNI + zombie specs"),
    (
        "21",
        "Manual Session-File Dependency",
        "P2",
        "manually-captured session-file dependency",
    ),
    (
        "23",
        "Fixture Ignores Render Guards",
        "P2",
        "fixture ignores render guards",
    ),
)
