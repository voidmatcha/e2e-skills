#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Instruction-contract regressions; not a live model or browser evaluation."""
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[2]
SKILL = ROOT / 'skills/e2e-debugger'

class RerunScopeTests(unittest.TestCase):
    def scope(self):
        body = (SKILL / 'SKILL.md').read_text()
        self.assertIn('Before rerunning, follow `rerun-scope.md`', body)
        return (SKILL / 'rerun-scope.md').read_text()

    def test_playwright_replaces_broad_filters_and_verifies_selection(self):
        scope = self.scope()
        for rule in ('Replace existing positional file filters', 'package.json', '--list',
                     'one unique test in the intended project', 'zero or multiple tests',
                     'opaque wrapper', 'do not execute'):
            self.assertIn(rule, scope)
        self.assertNotIn('Playwright: append', (SKILL / 'SKILL.md').read_text())

    def test_cypress_spec_is_not_test_isolation(self):
        scope = self.scope()
        for rule in ('`--spec` selects a file, not a test', 'already-installed title filter',
                     'If title isolation cannot be verified, stop', 'explicit approval',
                     'Do not install a filter or add `.only`', 'named test',
                     'spec exit status', 'UNCLEAR'):
            self.assertIn(rule, scope)

if __name__ == '__main__':
    unittest.main(verbosity=2)
