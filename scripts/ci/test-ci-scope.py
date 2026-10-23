#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""CI selection regression tests use disposable Git and command-stub fixtures."""
import importlib.util
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[2]
SPEC = importlib.util.spec_from_file_location('ci_scope', ROOT / 'scripts/ci/lib/ci-scope.py')
SCOPE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(SCOPE)


def git(root, *args):
    return subprocess.run(['/usr/bin/git', *args], cwd=root, check=True,
                          stdout=subprocess.PIPE, stderr=subprocess.PIPE).stdout


class ScopeTests(unittest.TestCase):
    def test_path_domains(self):
        for path, expected in (
            ('docs/e2e-test-smells.md', set()),
            ('skills/playwright-test-generator/code-rules.md', {'generator', 'verification'}),
            ('skills/playwright-debugger/references/fix-verification.md', {'debuggers', 'verification'}),
            ('skills/cypress-debugger/scripts/artifact.py', {'debuggers', 'fixtures'}),
            ('skills/e2e-reviewer/references/scanner-workflow.md', set(SCOPE.GROUPS)),
            ('scripts/ci/test-scanner-scope-graph.py', {'scanner', 'tooling'}),
            ('scripts/evals/fixtures/app.js', {'fixtures', 'selfscan'}),
            ('scripts/evals/run-reviewer-holdout.py', {'harness', 'holdout'}),
            ('scripts/dev/reinstall-skills.sh', {'install'}),
            ('scripts/ast-grep-rules/sg-postfix-empty-expect.yml', {'postfix'}),
            ('examples/react-optimistic-write/index.html', {'evidence', 'selfscan'}),
        ):
            mode, _, groups = SCOPE.select([path])
            self.assertEqual(mode, 'scoped', path)
            self.assertTrue(expected <= set(groups), path)
            if not expected:
                self.assertEqual(groups, (), path)
        for readme in ('README.md', 'README.ko.md', 'README.ja.md', 'README.zh-cn.md'):
            self.assertEqual(SCOPE.select([readme])[2], ('debuggers',), readme)
        all_skills = ['skills/' + name + '/SKILL.md' for name in (
            'e2e-reviewer', 'playwright-test-generator', 'playwright-debugger', 'cypress-debugger')]
        self.assertEqual(set(SCOPE.select(all_skills)[2]), set(SCOPE.GROUPS))

    def test_unknown_and_shared_are_full(self):
        for path in ('AGENTS.md', 'CONTRIBUTING.md', '.github/workflows/ci.yml', '.plugin-scanner.toml',
                     'scripts/ci/ci-local.sh', 'scripts/ci/lib/ci-scope.py',
                     'scripts/ci/test-ci-scope.py', 'scripts/ci/lib/python-isolated.sh',
                     'unrecognized.txt', '-option\n$(touch nope)'):
            self.assertEqual(SCOPE.select([path])[0], 'full', path)

    def test_git_union_and_hostile_paths(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            git(root, 'init', '-q')
            for name in ('README.md', 'docs/old.md', 'docs/deleted.md'):
                path = root / name
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_text('base')
            git(root, 'add', '.')
            git(root, '-c', 'user.name=Fixture', '-c', 'user.email=fixture@example.invalid', 'commit', '-qm', 'base')
            git(root, 'mv', 'docs/old.md', 'docs/new.md')
            (root / 'docs/deleted.md').unlink()
            hostile = 'docs/-odd\tline\n$(touch unexpected).md'
            (root / hostile).write_text('untracked')
            (root / 'README.md').write_text('staged')
            git(root, 'add', 'README.md')
            (root / 'README.md').write_text('base')  # index-only change
            self.assertEqual(set(SCOPE.changed_paths(root, 'HEAD')),
                             {'README.md', 'docs/old.md', 'docs/new.md', 'docs/deleted.md', hostile})
            self.assertFalse((root / 'unexpected').exists())
            # A committed change reverted to the merge base in both index and
            # worktree must remain in the union.
            git(root, 'add', '.')
            git(root, '-c', 'user.name=Fixture', '-c', 'user.email=fixture@example.invalid', 'commit', '-qm', 'changes')
            (root / 'docs/new.md').write_text('committed')
            git(root, 'add', '.')
            git(root, '-c', 'user.name=Fixture', '-c', 'user.email=fixture@example.invalid', 'commit', '-qm', 'next')
            (root / 'docs/new.md').write_text('base')
            git(root, 'add', '.')
            self.assertIn('docs/new.md', SCOPE.changed_paths(root, 'HEAD~1'))
            result = subprocess.run([sys.executable, str(SPEC.origin), '--repo', str(root),
                                     '--base', 'missing-base'], capture_output=True, text=True)
            self.assertEqual(result.returncode, 0)
            self.assertTrue(result.stdout.startswith('full\n'))
            self.assertIn('unavailable', result.stdout)

    def test_runner_routes_and_failures(self):
        source = (ROOT / 'scripts/ci/ci-local.sh').read_text()
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            ci = root / 'scripts/ci'
            (ci / 'lib').mkdir(parents=True)
            runner = ci / 'ci-local.sh'
            # Runtime resolution is tested by the existing isolation suite;
            # this fixture only observes group dispatch using tiny stubs.
            fixture = re.sub(r'step "Trusted Node.js runtime".*?(?=if selected generator;)',
                             'NODE_BIN=/usr/bin/true\n\n', source, flags=re.S)
            runner.write_text(fixture)
            shutil.copy2(SPEC.origin, ci / 'lib/ci-scope.py')
            log = root / 'route.log'
            (root / '.gitignore').write_text('route.log\n')
            stub = "from pathlib import Path\nimport sys\np=Path(__file__)\nwith open(" + repr(str(log)) + ", 'a') as f: f.write(p.name+'\\n')\n"
            for relative in re.findall(r'run_python (scripts/[^\s]+\.py)', source):
                path = root / relative
                if relative == 'scripts/ci/lib/ci-scope.py':
                    continue
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_text(stub)
            for relative in re.findall(r'/bin/bash -p (scripts/[^\s]+\.sh)', source):
                path = root / relative
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_text('#!/bin/bash\nprintf "%s\\n" "${0##*/}" >> ' + repr(str(log)) + '\n')
            (ci / 'lib/init-python-isolation.sh').write_text('run_python() { ' + repr(sys.executable) + ' "$@"; }\n')
            enumerator = ci / 'lib/enumerate-shell-files.sh'
            enumerator.write_text('#!/bin/bash\nprintf "%s\\n" scripts/ci/ci-local.sh\n')
            enumerator.chmod(0o755)
            (root / 'skills').mkdir()
            (root / 'README.md').write_text('base')
            (root / 'docs').mkdir()
            (root / 'docs/example.md').write_text('base')
            git(root, 'init', '-q')
            git(root, 'add', '.')
            git(root, '-c', 'user.name=Fixture', '-c', 'user.email=fixture@example.invalid', 'commit', '-qm', 'base')
            (root / 'docs/example.md').write_text('docs change')

            def run(*args, **kwargs):
                return subprocess.run(['/bin/bash', '-p', str(runner), *args], cwd=root,
                                      text=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, **kwargs)

            result = run('--changed', 'HEAD', '--plan')
            self.assertEqual(result.returncode, 0, result.stdout)
            self.assertIn('omitted group: scanner', result.stdout)
            self.assertFalse(log.exists())
            result = run('--changed', 'HEAD')
            self.assertEqual(result.returncode, 0, result.stdout)
            self.assertIn('scoped checks passed', result.stdout)
            self.assertNotIn('all checks passed', result.stdout)
            calls = log.read_text().splitlines()
            self.assertIn('review.sh', calls)
            self.assertIn('test-debugger-contracts.py', calls)
            self.assertNotIn('test-reviewer-scanner.py', calls)
            self.assertNotIn('test-playwright-debugger-artifact-download.py', calls)
            result = run('--quiet', '--changed', 'HEAD')
            self.assertEqual(result.returncode, 0, result.stdout)
            self.assertIn('scoped checks passed', result.stdout)
            log.unlink()
            (root / 'README.md').write_text('README acquisition example change')
            result = run('--changed', 'HEAD')
            self.assertEqual(result.returncode, 0, result.stdout)
            self.assertIn('test-playwright-debugger-artifact-download.py', log.read_text())
            self.assertNotIn('test-reviewer-scanner.py', log.read_text())
            log.unlink()
            (root / 'skills/playwright-test-generator').mkdir()
            (root / 'skills/playwright-test-generator/SKILL.md').write_text('change')
            result = run('--changed', 'HEAD')
            self.assertEqual(result.returncode, 0, result.stdout)
            self.assertIn('test-generator-router.py', log.read_text())
            self.assertNotIn('test-reviewer-scanner.py', log.read_text())
            log.unlink()
            result = run('--full')
            self.assertEqual(result.returncode, 0, result.stdout)
            self.assertIn('all checks passed', result.stdout)
            self.assertIn('test-reviewer-scanner.py', log.read_text())
            (ci / 'test-generator-router.py').write_text('raise SystemExit(17)\n')
            result = run('--changed', 'HEAD')
            self.assertNotEqual(result.returncode, 0)
            self.assertIn('test-generator-router.py failed', result.stdout)
            for args in (('--unknown',), ('--changed',), ('--full', '--changed', 'HEAD')):
                self.assertEqual(run(*args).returncode, 2)
            for flag in ('E2E_SKILLS_SKIP_CI_LOCAL', 'E2E_SKILLS_SKIP_SECURITY',
                         'E2E_SKILLS_SKIP_PARITY_SMOKE', 'E2E_SKILLS_SKIP_SMELL_SCAN'):
                self.assertEqual(run('--plan', env=dict(os.environ, **{flag: '1'})).returncode, 2)
            result = run('--changed', 'missing-base', '--plan')
            self.assertEqual(result.returncode, 0)
            self.assertIn('full plan:', result.stdout)
            self.assertNotIn('omitted group:', result.stdout)
            result = run('--full', '--plan')
            self.assertEqual(result.returncode, 0)
            self.assertIn('run group: scanner', result.stdout)
            selector = ci / 'lib/ci-scope.py'
            for bad_source in ("raise SystemExit(7)\n", "print('scoped\\nreason')\n",
                               "print('scoped\\nreason\\nunknown')\n",
                               "print('scoped\\nreason\\n-\\nextra')\n"):
                selector.write_text(bad_source)
                result = run('--changed', 'HEAD', '--plan')
                self.assertEqual(result.returncode, 0, result.stdout)
                self.assertIn('full plan:', result.stdout)
                self.assertNotIn('omitted group:', result.stdout)
            selector.unlink()
            for args in (('--full', '--plan'), ('--quiet', '--plan'), ('--plan',)):
                result = run(*args)
                self.assertEqual(result.returncode, 0, result.stdout)
                self.assertIn('run group: scanner', result.stdout)


if __name__ == '__main__':
    unittest.main()
