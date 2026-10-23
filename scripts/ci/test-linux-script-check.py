#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Linux snapshot honesty and consumer routing; no Docker/network invocation."""

from __future__ import annotations

from pathlib import Path
import os
import re
import shutil
import subprocess
import tempfile


ROOT = Path(__file__).resolve().parents[2]
SOURCE_CHECK = ROOT / "scripts/dev/linux-script-check.sh"
BASH = Path("/bin/bash")
GIT = Path("/usr/bin/git")
NODE_IMAGE = "node@sha256:3ed98443660ff48413b5af19ecefce3b9d50845a901a43420d47cc63a9fddbe9"
NODE_INPUTS = (
    "packages/scanner/src/cli.mjs",
    "packages/scanner/test/cli-static-review.test.mjs",
    "scripts/ci/test-scanner-launcher.py",
    "scripts/ci/test-scanner-runtime.py",
    "scripts/ci/test-scanner-node-performance.py",
    "scripts/ci/test-local-eslint-node.py",
    "scripts/ci/test-linux-script-check.py",
    "scripts/ci/fixtures/legacy-scanner/manifest.json",
    "scripts/ci/lib/legacy_scanner_oracle.py",
    "scripts/evals/files/holdout/example.spec.ts",
    "scripts/dev/build-scanner-runtime.py",
    "scripts/dev/scanner-launcher.sh",
)


def run(*args: str, cwd: Path, check: bool = True) -> subprocess.CompletedProcess[str]:
    result = subprocess.run(
        [*args],
        cwd=cwd,
        text=True,
        capture_output=True,
        timeout=15,
        check=False,
    )
    if check and result.returncode != 0:
        raise AssertionError(
            f"command failed ({result.returncode}): {args}\n"
            f"stdout:\n{result.stdout}\nstderr:\n{result.stderr}"
        )
    return result


def write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def assert_consumer_routing() -> None:
    """Execute the real container shell body with recorded preparation/test stubs.

    This proves ordering, routing and failure propagation, not a Linux/image run.
    Only OS preparation and suite execution are stubbed; no package is installed.
    """
    source = SOURCE_CHECK.read_text()
    assert f'IMAGE="{NODE_IMAGE}"' in source
    assert 'archive --format=tar "$REV_SHA"' in source
    # Artifact cleanup tests intentionally orphan descendants; PID 1 must reap
    # them so a dead process group is not mistaken for a surviving child.
    assert '"$DOCKER" run --init --rm -i --network=bridge "$IMAGE"' in source
    body = source.split('"$IMAGE" /bin/bash -c \'\n', 1)[1].rsplit("\n  '\n", 1)[0]
    assert 'export PATH=/usr/local/bin:/usr/bin:/bin:/usr/sbin:/sbin' in body
    assert 'apt-get install -y -qq --no-install-recommends python3 ripgrep git ca-certificates' in body
    assert not re.search(r'apt-get install[^\n]*\b(?:nodejs|npm)\b', body)
    suites = re.findall(r'^      (scripts/ci/test-[^ ]+) \\$', body, re.M)
    suites += re.findall(r'^      (scripts/ci/test-[^;\n]+); do$', body, re.M)
    required = {
        'test-scanner-runtime.py', 'test-scanner-launcher.py',
        'test-scanner-node-performance.py', 'test-reviewer-scanner.py',
        'test-eslint-import-resolution.py', 'test-local-eslint-node.py',
        'test-debugger-contracts.py', 'test-playwright-debugger-artifact-download.py',
        'test-playwright-debugger-report-publish.py',
        'test-cypress-debugger-artifact-download.py', 'test-cypress-debugger-report-publish.py',
    }
    assert {Path(item).name for item in suites} == required, suites
    assert len(suites) == len(required), 'duplicate or missing consumer suite'
    with tempfile.TemporaryDirectory(prefix='linux-routing-') as directory:
        base = Path(directory)
        repo = base / 'repo'
        repo.mkdir()
        for suite in suites:
            write(repo / suite, '# recorded consumer fixture\n')
        bin_dir = base / 'bin'
        bin_dir.mkdir()
        log = base / 'commands'
        stub = '''#!/bin/bash
printf '%s %s\\n' "${0##*/}" "$*" >> "$ROUTING_LOG"
case "${0##*/}" in
  node) exit "$NODE_STATUS" ;;
  su)
    [ "$1" = checker ] || exit 91
    for argument; do last="$argument"; done
    if [ -n "$FAIL_COMMAND" ] && [[ "$last" == *"$FAIL_COMMAND"* ]]; then exit 37; fi
    ;;
esac
'''
        for command in ('node', 'apt-get', 'useradd', 'install', 'tar', 'chown', 'su'):
            write(bin_dir / command, stub)
            (bin_dir / command).chmod(0o755)
        script = base / 'container.sh'
        # These replacements change only the disposable execution environment.
        script.write_text(body.replace('/srv/repo', str(repo))
                          .replace('export PATH=/usr/local/bin:/usr/bin:/bin:/usr/sbin:/sbin',
                                   f'export PATH={bin_dir}:/usr/bin:/bin')
                          .replace('/usr/local/bin/node', str(bin_dir / 'node')))

        def execute(*, node_status=0, fail=''):
            log.write_text('')
            result = subprocess.run([str(BASH), '-p', str(script)], cwd=repo,
                                    env={**os.environ, 'ROUTING_LOG': str(log),
                                         'NODE_STATUS': str(node_status), 'FAIL_COMMAND': fail},
                                    capture_output=True, text=True, timeout=10)
            return result, log.read_text().splitlines()

        result, commands = execute()
        assert result.returncode == 0, result.stderr
        assert commands[0].startswith('node -e '), commands
        assert 'process.versions.node' in commands[0] and '< 22' in commands[0]
        checks = [line for line in commands if line.startswith('su ')]
        assert all(line.startswith('su checker -s /bin/bash -c ') for line in checks)
        freshness = next(i for i, line in enumerate(checks) if 'build-scanner-runtime.py --check' in line)
        assert all(next(i for i, line in enumerate(checks) if suite in line) > freshness for suite in suites)
        assert all(sum(suite in line for line in checks) == 1 for suite in suites)

        result, commands = execute(node_status=2)
        assert result.returncode == 2 and len(commands) == 1, (result, commands)
        result, commands = execute(fail='build-scanner-runtime.py --check')
        assert result.returncode != 0 and not any('scripts/ci/test-' in line for line in commands)
        result, commands = execute(fail='test-scanner-launcher.py')
        assert result.returncode == 1 and not any('test-scanner-node-performance.py' in line for line in commands)
        (repo / 'scripts/ci/test-scanner-launcher.py').unlink()
        result, commands = execute()
        assert result.returncode == 1 and 'missing suite:' in result.stderr
        assert not any('test-scanner-node-performance.py' in line for line in commands)


def main() -> None:
    assert BASH.is_file(), "test requires the shipped /bin/bash contract"
    assert GIT.is_file(), "test requires the shipped /usr/bin/git contract"
    assert_consumer_routing()

    with tempfile.TemporaryDirectory(prefix="e2e-linux-check-") as directory:
        repo = Path(directory) / "repo"
        repo.mkdir()
        check_script = repo / "scripts/dev/linux-script-check.sh"
        check_script.parent.mkdir(parents=True)
        shutil.copy2(SOURCE_CHECK, check_script)
        write(repo / "skills/e2e-reviewer/scripts/scan.sh", "#!/bin/bash -p\n")
        write(
            repo / "skills/cypress-debugger/references/report-acquisition.md",
            "# Report acquisition\n",
        )
        write(repo / "skills/playwright-debugger/evals/evals.json", "{}\n")
        write(repo / "scripts/ci/test-reviewer-scanner.py", "# fixture\n")
        for relative in NODE_INPUTS:
            write(repo / relative, '# Node validation input fixture\n')
        write(repo / "unrelated.txt", "clean\n")

        run(str(GIT), "init", "-q", cwd=repo)
        run(str(GIT), "config", "user.name", "linux-check-test", cwd=repo)
        run(str(GIT), "config", "user.email", "linux-check@example.invalid", cwd=repo)
        run(str(GIT), "add", "-A", cwd=repo)
        run(str(GIT), "commit", "-qm", "fixture", cwd=repo)

        clean = run(
            str(BASH), "-p", str(check_script), "--validate-inputs-only", cwd=repo
        )
        assert "relevant worktree inputs are clean" in clean.stdout
        assert "skills/**" in clean.stdout
        assert "README*.md" in clean.stdout
        assert ".github/workflows/e2e-smell-scan.yml" in clean.stdout
        assert "scripts/ci/ci-local.sh" in clean.stdout

        with (repo / "unrelated.txt").open("a", encoding="utf-8") as stream:
            stream.write("outside the Linux validation scope\n")
        scoped_clean = run(
            str(BASH), "-p", str(check_script), "--validate-inputs-only", cwd=repo
        )
        assert "relevant worktree inputs are clean" in scoped_clean.stdout

        for relative in NODE_INPUTS:
            with (repo / relative).open('a') as stream:
                stream.write('# dirty Node validation input\n')
            dirty_node_input = run(str(BASH), '-p', str(check_script),
                                   '--validate-inputs-only', cwd=repo, check=False)
            assert dirty_node_input.returncode == 2 and relative in dirty_node_input.stderr
            run(str(GIT), 'restore', '--', relative, cwd=repo)

        staged_input = NODE_INPUTS[0]
        write(repo / staged_input, '# staged scanner change\n')
        run(str(GIT), 'add', '--', staged_input, cwd=repo)
        staged = run(str(BASH), '-p', str(check_script), '--validate-inputs-only', cwd=repo, check=False)
        assert staged.returncode == 2 and staged_input in staged.stderr
        run(str(GIT), 'restore', '--staged', '--worktree', '--', staged_input, cwd=repo)
        (repo / staged_input).unlink()
        deleted = run(str(BASH), '-p', str(check_script), '--validate-inputs-only', cwd=repo, check=False)
        assert deleted.returncode == 2 and staged_input in deleted.stderr
        run(str(GIT), 'restore', '--', staged_input, cwd=repo)
        new_input = 'packages/scanner/src/new-input.mjs'
        write(repo / new_input, '// untracked scanner source\n')
        untracked_node = run(str(BASH), '-p', str(check_script), '--validate-inputs-only', cwd=repo, check=False)
        assert untracked_node.returncode == 2 and new_input in untracked_node.stderr
        (repo / new_input).unlink()

        with (repo / "skills/e2e-reviewer/scripts/scan.sh").open(
            "a", encoding="utf-8"
        ) as stream:
            stream.write("# dirty\n")
        dirty = run(
            str(BASH),
            "-p",
            str(check_script),
            "--validate-inputs-only",
            cwd=repo,
            check=False,
        )
        assert dirty.returncode == 2, dirty
        assert "default HEAD snapshot excludes" in dirty.stderr
        assert "skills/e2e-reviewer/scripts/scan.sh" in dirty.stderr

        run(str(GIT), "restore", "--", "skills/e2e-reviewer/scripts/scan.sh", cwd=repo)
        for relative in (
            "skills/cypress-debugger/references/report-acquisition.md",
            "skills/playwright-debugger/evals/evals.json",
        ):
            with (repo / relative).open("a", encoding="utf-8") as stream:
                stream.write("dirty skill input\n")
            dirty_skill_input = run(
                str(BASH),
                "-p",
                str(check_script),
                "--validate-inputs-only",
                cwd=repo,
                check=False,
            )
            assert dirty_skill_input.returncode == 2, dirty_skill_input
            assert relative in dirty_skill_input.stderr
            run(str(GIT), "restore", "--", relative, cwd=repo)

        untracked_path = repo / "skills/playwright-debugger/scripts/new-reader.py"
        write(untracked_path, "# untracked\n")
        untracked = run(
            str(BASH),
            "-p",
            str(check_script),
            "--validate-inputs-only",
            cwd=repo,
            check=False,
        )
        assert untracked.returncode == 2, untracked
        assert "skills/playwright-debugger/scripts/new-reader.py" in untracked.stderr

        with (repo / "scripts/ci/test-reviewer-scanner.py").open(
            "a", encoding="utf-8"
        ) as stream:
            stream.write("# explicit revision ignores this worktree change\n")
        explicit = run(
            str(BASH),
            "-p",
            str(check_script),
            "--validate-inputs-only",
            "HEAD",
            cwd=repo,
        )
        assert "explicit commit-only revision" in explicit.stdout
        assert "worktree changes intentionally ignored" in explicit.stdout

    print("linux script check snapshot honesty and consumer routing: pass (Docker/image execution not tested)")


if __name__ == "__main__":
    main()
