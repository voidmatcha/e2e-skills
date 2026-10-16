#!/usr/bin/env python3
"""Offline verification of the pending root-rollout repair, without editing frozen files. Apache-2.0."""
import argparse
import importlib.machinery
import importlib.util
import json
from pathlib import Path
import re
import sys
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[3]
PATCH = Path(__file__).with_name('root-rollout-spawns.patch')


def candidate_sources():
    """Apply exact unified-diff hunks in memory; refuse stale patch context."""
    sources = {}
    lines = PATCH.read_text().splitlines(keepends=True)
    pos = 0
    while pos < len(lines):
        assert lines[pos].startswith('--- a/')
        rel = lines[pos][6:].strip()
        original = (ROOT / rel).read_text().splitlines(keepends=True)
        pos += 2
        rebuilt, cursor = [], 0
        while pos < len(lines) and not lines[pos].startswith('--- a/'):
            hunk = re.match(r'@@ -(\d+)(?:,\d+)? \+\d+(?:,\d+)? @@', lines[pos])
            assert hunk, lines[pos]
            start = int(hunk[1]) - 1
            rebuilt.extend(original[cursor:start])
            cursor = start
            pos += 1
            while pos < len(lines) and not lines[pos].startswith(('@@ ', '--- a/')):
                mark, text = lines[pos][0], lines[pos][1:]
                if mark in (' ', '-'):
                    assert original[cursor] == text, (rel, cursor)
                    cursor += 1
                if mark in (' ', '+'):
                    rebuilt.append(text)
                pos += 1
        rebuilt.extend(original[cursor:])
        sources[str(ROOT / rel)] = ''.join(rebuilt)
    return sources


def candidate_loader(sources):
    original = importlib.machinery.SourceFileLoader.get_code

    def get_code(loader, fullname):
        source = sources.get(str(Path(loader.path).resolve()))
        return compile(source, loader.path, 'exec') if source is not None else original(loader, fullname)

    return patch.object(importlib.machinery.SourceFileLoader, 'get_code', get_code)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--stored', action='store_true', help='Read the finished persisted harness check; never rewrite it.')
    parser.add_argument('--tests', action='store_true', help='Run the three offline scripts against the in-memory candidate.')
    args = parser.parse_args()
    sources = candidate_sources()
    with candidate_loader(sources):
        if args.tests:
            import unittest
            for name in ('test-generator-multimodel-v2-codex.py', 'test-generator-v2-codex-harness-fixes.py', 'test-generator-v2-codex-smoke.py'):
                spec = importlib.util.spec_from_file_location('candidate_' + name.replace('-', '_').replace('.py', ''), ROOT / 'scripts/ci' / name)
                module = importlib.util.module_from_spec(spec)
                spec.loader.exec_module(module)
                result = unittest.TextTestRunner(verbosity=1).run(unittest.defaultTestLoader.loadTestsFromModule(module))
                if not result.wasSuccessful():
                    return 1
        else:
            spec = importlib.util.spec_from_file_location('candidate_runner', ROOT / 'scripts/evals/run-generator-multimodel-v2-codex.py')
            module = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(module)
            root = (Path.home() / '.cache/e2e-skills-bench/multimodel-v2-codex/_entry/harness-check') if args.stored else Path(__file__).parents[1] / 'fixtures/harness-check'
            rec = json.loads((root / 'call.json').read_text())
            check = module.evaluate_harness_check(rec, root / 'transcripts')
            fid = module.classify_fidelity(rec, root / 'transcripts')
            cost = module.tokens_for_record(rec, root / 'transcripts')
            print(json.dumps({'implementation': 'pending patch in memory; frozen files unchanged', 'input': 'stored finished harness check' if args.stored else 'scrubbed real fixture', 'check': check, 'fidelity_primary_signal': fid['evidence'].get('primary_signal'), 'fidelity_primary_signal_complete': fid['evidence'].get('primary_signal_complete'), 'cost_complete': cost['complete'], 'total_tokens': cost['total']}, indent=2))
            return 0 if check['criteria']['spawns_have_rollouts'] else 1
    return 0


if __name__ == '__main__':
    sys.exit(main())
