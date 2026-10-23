#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Conservative opt-in CI selection. Unknown inputs always require full CI."""
import argparse
import json
import os
from pathlib import Path
import subprocess

GROUPS = ('generator', 'verification', 'install', 'debuggers', 'behavioral',
          'evidence', 'holdout', 'scanner', 'harness', 'fixtures', 'tooling',
          'preflight', 'postfix', 'parity', 'selfscan')


def select(paths):
    selected = set()
    for path in paths:
        # Do not normalize names: Git paths are exact, including hostile bytes.
        if path in ('README.md', 'README.ko.md', 'README.ja.md', 'README.zh-cn.md'):
            # Artifact-download contracts also inspect the public acquisition examples.
            selected.add('debuggers')
            continue
        if path in ('CHANGELOG.md', 'LICENSE', 'NOTICE') or (
                    path.startswith('docs/') and path.endswith('.md')) or (
                    path.startswith('benchmarks/') and path.endswith('.md')):
            continue
        if path.startswith('skills/e2e-reviewer/'):
            # Reviewer references feed generator, debugger, installation and
            # assertion guidance as well as the scanner and harness contracts.
            selected.update(GROUPS)
        elif path.startswith('skills/playwright-test-generator/'):
            selected.update(('generator', 'verification', 'install', 'behavioral',
                             'fixtures', 'parity', 'selfscan'))
        elif path.startswith(('skills/playwright-debugger/', 'skills/cypress-debugger/')):
            selected.update(('debuggers', 'verification', 'install', 'behavioral',
                             'fixtures', 'parity', 'selfscan'))
        elif path.startswith(('agents/', '.codex/agents/')):
            selected.update(('install', 'debuggers', 'verification', 'behavioral', 'parity'))
        elif path.startswith('examples/react-optimistic-write/'):
            selected.update(('evidence', 'selfscan'))
        elif path.startswith(('scripts/evals/fixtures/', 'scripts/evals/semantic-probes/')):
            selected.update(('fixtures', 'selfscan'))
        elif path in ('scripts/evals/run-reviewer-holdout.py',
                      'scripts/evals/compare-reviewer-holdouts.py'):
            selected.update(('harness', 'holdout', 'behavioral'))
        elif path.startswith(('scripts/ci/test-scanner-', 'scripts/ci/test-reviewer-scanner.')):
            selected.update(('scanner', 'tooling', 'selfscan'))
        elif path in ('scripts/pr-preflight.sh', 'scripts/ci/test-pr-preflight.py'):
            selected.add('preflight')
        elif path in ('scripts/verify-fixes.sh', 'scripts/ci/test-verify-fixes.py') or path.startswith('scripts/ast-grep-rules/'):
            selected.add('postfix')
        elif path in ('scripts/dev/reinstall-skills.sh', 'scripts/dev/install-codex-agents.sh',
                      'scripts/dev/install-claude-agents.sh', 'scripts/ci/test-reinstall-skills.py'):
            selected.update(('install', 'parity'))
        else:
            return 'full', 'unknown or shared path: ' + json.dumps(path, ensure_ascii=True), GROUPS
        if path.endswith(('.js', '.jsx', '.ts', '.tsx', '.mjs', '.cjs', '.mts', '.cts')):
            selected.add('selfscan')
    return 'scoped', 'changed paths classified: ' + str(len(paths)), tuple(
        group for group in GROUPS if group in selected)


def changed_paths(root, base):
    # Fixed executable, no shell, no user-supplied Git options, no inherited
    # Git config/environment hooks. Never use status text or line delimiters.
    env = {key: os.environ[key] for key in ('PATH', 'HOME', 'TMPDIR') if key in os.environ}
    env.update(GIT_CONFIG_NOSYSTEM='1', GIT_CONFIG_GLOBAL='/dev/null',
               GIT_TERMINAL_PROMPT='0', GIT_OPTIONAL_LOCKS='0')

    def git(*args):
        return subprocess.run(['/usr/bin/git', '-c', 'core.fsmonitor=false',
                               '-c', 'core.hooksPath=/dev/null', *args], cwd=root,
                              env=env, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                              check=True).stdout

    revision = git('rev-parse', '--verify', '--end-of-options', base + '^{commit}').strip()
    merge = git('merge-base', revision.decode('ascii'), 'HEAD').strip().decode('ascii')
    # Keep each source separately: later edits can cancel a committed change
    # or an index change without making its dependency irrelevant.
    paths = set()
    common = ('diff', '--no-ext-diff', '--no-textconv', '--no-renames', '--name-only', '-z')
    for args in (common + (merge, 'HEAD', '--'),
                 common + ('--cached', 'HEAD', '--'),
                 common + ('--',),
                 ('ls-files', '--others', '--exclude-standard', '-z')):
        raw = git(*args)
        if raw and not raw.endswith(b'\0'):
            raise ValueError('unterminated Git path output')
        paths.update(os.fsdecode(path) for path in raw.split(b'\0') if path)
    return sorted(paths)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--repo', type=Path, required=True)
    parser.add_argument('--base', required=True)
    args = parser.parse_args()
    try:
        mode, reason, groups = select(changed_paths(args.repo, args.base))
    except (OSError, ValueError, subprocess.SubprocessError, UnicodeError):
        mode, reason, groups = 'full', 'base or Git diff unavailable; full CI required', GROUPS
    print(mode)
    print(reason)
    print(' '.join(groups) or '-')


if __name__ == '__main__':
    main()
