#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Manifest v1 local probe. Copies isolate phases, NOT execution or security.

Preview executes no checkout code. Execution requires trust and approval of the
canonical manifest, included source file hashes, and this runner's bytes. Trusted
commands retain host filesystem/network access. Dependency links are reused by
convention read-only, not OS-enforced; no sandbox claim is made.
"""
from __future__ import annotations
import argparse
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import signal
import stat
import subprocess
import sys

EXCLUDED = {'.git', 'node_modules', 'reports', 'playwright-report', 'test-results',
            '.cache', 'cache', '__pycache__', '.parcel-cache'}
ENV_KEYS = ('HOME', 'PATH', 'LANG', 'LC_ALL', 'USER', 'LOGNAME', 'TMPDIR', 'TEMP', 'TMP', 'SystemRoot')
LIMITATION = ('Fresh phase copies are not a sandbox. Trusted commands can access the host and network. '
              'Explicit dependency symlinks are read-only by convention, not enforced by this runner.')


def require(ok, message):
    if not ok:
        raise ValueError(message)


def digest(data):
    return hashlib.sha256(data).hexdigest()


def relative(value):
    require(isinstance(value, str) and value and '\\' not in value, 'invalid relative path')
    path = PurePosixPath(value)
    require(not path.is_absolute() and all(p not in ('', '.', '..') for p in value.split('/')), 'path traversal')
    require(not any(p in EXCLUDED for p in path.parts), 'path enters excluded directory')
    return str(path)


def no_symlinks(path):
    for part in (path, *path.parents):
        require(not part.is_symlink(), 'symlink path forbidden: ' + str(path))


def absolute(value):
    path = Path(value).expanduser().absolute()
    require('..' not in path.parts, 'absolute path contains traversal')
    no_symlinks(path)
    return path.resolve(strict=False)


def environment():
    return {k: os.environ[k] for k in ENV_KEYS if k in os.environ}


def tree(root):
    """Hash every included regular file; reject links/special files, never follow."""
    no_symlinks(root)
    require(root.is_dir(), 'source must be a directory')
    files = {}
    for base, dirs, names in os.walk(root, followlinks=False):
        dirs[:] = sorted(d for d in dirs if d not in EXCLUDED)
        for name in dirs + sorted(names):
            path = Path(base) / name
            mode = path.lstat().st_mode
            require(not stat.S_ISLNK(mode), 'included symlink forbidden: ' + str(path))
            if stat.S_ISDIR(mode):
                continue
            require(stat.S_ISREG(mode), 'special file forbidden: ' + str(path))
            rel = path.relative_to(root).as_posix()
            # Excluded names apply to directories only, not arbitrary source files.
            files[rel] = {'sha256': digest(path.read_bytes()), 'mode': stat.S_IMODE(mode)}
    return files


def keys(value, allowed, required=()):
    require(isinstance(value, dict) and not (set(value) - set(allowed)), 'unexpected manifest keys')
    require(set(required) <= set(value), 'missing manifest keys')


def command(value):
    keys(value, ('argv', 'timeout_seconds', 'source'), ('argv',))
    argv = value.get('argv')
    require(isinstance(argv, list) and argv and all(isinstance(a, str) and a and '\0' not in a for a in argv), 'argv must be nonempty strings')
    timeout = value.get('timeout_seconds', 120)
    require(type(timeout) is int and 1 <= timeout <= 300, 'timeout must be 1..300 seconds')


def prepare(plan):
    keys(plan, ('version', 'source', 'test_selector', 'test_paths', 'mode', 'promise', 'edits', 'test', 'observer', 'report', 'expected_failure', 'dependency_dirs'), ('version', 'source', 'test_selector', 'test_paths', 'mode', 'promise', 'edits', 'test', 'report', 'expected_failure'))
    require(plan.get('version') == 1 and type(plan['version']) is int, 'manifest version must be 1')
    require(plan.get('mode') in ('behavior-fault', 'assertion-mutation'), 'unknown mode')
    source = absolute(plan['source'])
    files = tree(source)
    require(isinstance(plan.get('test_selector'), str) and plan['test_selector'], 'test_selector required')
    test_paths = {relative(p) for p in plan['test_paths']}
    require(test_paths and test_paths <= files.keys(), 'test_paths must name included tests')
    keys(plan['promise'], ('path', 'quote', 'sha256'), ('path', 'quote', 'sha256'))
    promise = plan['promise']; p = relative(promise['path'])
    require(p in files and files[p]['sha256'] == promise['sha256'], 'promise source hash mismatch')
    require(isinstance(promise['quote'], str) and promise['quote'] and promise['quote'] in (source / p).read_text(), 'promise quote absent')
    edits = plan['edits']; require(isinstance(edits, list) and edits, 'edits required')
    seen = set()
    for edit in edits:
        keys(edit, ('path', 'before', 'after', 'sha256', 'kind'), ('path', 'before', 'after', 'sha256', 'kind'))
        p = relative(edit['path'])
        require(p not in seen and p in files, 'edit path absent or repeated'); seen.add(p)
        require(edit['sha256'] == files[p]['sha256'], 'edit source hash mismatch')
        require(isinstance(edit['before'], str) and edit['before'] and isinstance(edit['after'], str), 'edit text required')
        require(edit['before'] != edit['after'], 'noop edit')
        require((source / p).read_bytes().count(edit['before'].encode()) == 1, 'edit must match exactly once')
        kind = 'test' if p in test_paths else 'source'
        require(edit.get('kind') == kind, 'edit kind contradicts test_paths')
        require(kind == ('source' if plan['mode'] == 'behavior-fault' else 'test'), 'edit forbidden in this mode')
    for label in ('test', 'observer'):
        if plan.get(label) is None:
            continue
        command(plan[label])
        pinned = plan[label]['source']
        keys(pinned, ('path', 'sha256'), ('path', 'sha256'))
        script = relative(pinned['path'])
        require(script in files and files[script]['sha256'] == pinned['sha256'], label + ' source hash mismatch')
        require(script not in seen, label + ' wrapper cannot be mutated')
        require(any(arg in (script, '{project}/' + script) for arg in plan[label]['argv']), label + ' argv must reference pinned source script')
    require(plan['mode'] != 'behavior-fault' or plan.get('observer') is not None, 'V3 observer required')
    keys(plan['report'], ('format', 'path'), ('format', 'path'))
    require(plan['report']['format'] in ('playwright-json', 'cypress-json'), 'unsupported report format')
    report_path = relative(plan['report']['path'])
    require(report_path not in files, 'report path must be fresh')
    keys(plan['expected_failure'], ('contains', 'location'), ('contains', 'location'))
    expected = plan['expected_failure']
    require(all(isinstance(expected.get(k), str) and expected[k] for k in ('contains', 'location')), 'linked failure string and location required')
    deps = []
    for dep in plan.get('dependency_dirs', []):
        keys(dep, ('path', 'target'), ('path', 'target'))
        # node_modules is the one permitted excluded dependency mount location.
        p = dep['path']; probe = relative(p.replace('node_modules', '_dependencies'))
        require(p.split('/').count('node_modules') == 1 and p.endswith('node_modules'), 'dependency path must end in node_modules')
        require(not any(p == d[0] or p.startswith(d[0] + '/') or d[0].startswith(p + '/') for d in deps), 'overlapping dependencies')
        target = absolute(dep['target'])
        require(target.is_dir(), 'dependency target missing')
        require(not target.is_relative_to(source), 'dependency target must be outside source')
        require(not (source / p).is_file(), 'dependency target collision')
        deps.append((p, target))
    payload = {'plan': plan, 'source_files': files, 'runner_sha256': digest(Path(__file__).read_bytes()), 'effective_environment': environment()}
    approval = digest(json.dumps(payload, sort_keys=True, separators=(',', ':'), ensure_ascii=True).encode())
    return source, files, deps, approval


def report_root(report, project):
    value = report.get('config', {}).get('rootDir', str(project))
    require(isinstance(value, str) and value, 'invalid Playwright rootDir')
    root = Path(value)
    require('..' not in root.parts, 'Playwright rootDir traversal')
    if not root.is_absolute(): root = project / root
    root = absolute(str(root))
    require(root.is_relative_to(project) and root.is_dir(), 'Playwright rootDir outside phase project or absent')
    return root


def parse_native(report, format_name, selector, test_paths, project):
    tests = []
    root = report_root(report, project) if format_name == 'playwright-json' else project
    def spec_path(value):
        require(isinstance(value, str) and value, 'reported spec path absent')
        path = Path(value)
        require('..' not in path.parts, 'reported spec path traversal')
        # Playwright JSONReporter serializes locations relative to config.rootDir.
        # A declared root is authoritative; never reinterpret a missing file
        # against the project directory or accept a basename/suffix match.
        candidates = [path] if path.is_absolute() else [root / path]
        for candidate in candidates:
            no_symlinks(candidate)
            candidate = candidate.resolve(strict=False)
            require(candidate.is_relative_to(project), 'reported spec outside phase project')
            name = candidate.relative_to(project).as_posix()
            if candidate.is_file():
                require(name in test_paths, 'reported spec not in test_paths')
                return
        raise ValueError('reported spec not in test_paths or absent')
    def error_text(value):
        if isinstance(value, str): return value
        require(isinstance(value, dict), 'invalid native error')
        text = '\n'.join(str(value.get(k, '')) for k in ('message', 'stack', 'value', 'snippet'))
        location = value.get('location')
        if isinstance(location, dict):
            text += '\n' + str(location.get('file', '')) + ':' + str(location.get('line', '')) + ':' + str(location.get('column', ''))
        return text
    if format_name == 'playwright-json':
        require(not report.get('errors'), 'Playwright global errors')
        require(report.get('config', {}).get('workers') == 1, 'Playwright workers must be one')
        for project_config in report.get('config', {}).get('projects', []):
            require(project_config.get('retries', 0) == 0, 'Playwright retries must be zero')
        def visit(suite):
            for spec in suite.get('specs', []):
                for test in spec.get('tests', []): tests.append((spec, test))
            for child in suite.get('suites', []): visit(child)
        for suite in report.get('suites', []): visit(suite)
        require(len(tests) == 1, 'report must contain exactly one test')
        spec, test = tests[0]; spec_path(spec.get('file'))
        require(spec.get('title') == selector, 'selected title mismatch')
        require(test.get('expectedStatus', 'passed') == 'passed', 'expected failure/skipped test forbidden')
        attempts = test.get('results', [])
        require(len(attempts) == 1 and attempts[0].get('retry', 0) == 0, 'report must contain one nonretry attempt')
        outcome = attempts[0]; status = outcome.get('status')
        require(status in ('passed', 'failed'), 'skip/interruption/timeout not admitted')
        require(test.get('status', 'expected' if status == 'passed' else 'unexpected') == ('expected' if status == 'passed' else 'unexpected'), 'inconsistent aggregate test status')
        stats = report.get('stats')
        if stats is not None:
            require(all(stats.get(k) == v for k, v in {'expected': int(status == 'passed'), 'unexpected': int(status == 'failed'), 'flaky': 0, 'skipped': 0}.items()), 'inconsistent Playwright stats')
        errors = outcome.get('errors', [])
        require(isinstance(errors, list), 'invalid Playwright errors')
        if outcome.get('error'): errors = errors + [outcome['error']]
        require(status != 'passed' or not errors, 'passed attempt contains errors')
        return status, [error_text(e) for e in errors]
    require(not report.get('errors') and not report.get('failures') and report.get('status', 'finished') == 'finished', 'Cypress top-level error')
    runs = report.get('runs', [])
    require(len(runs) == 1, 'exactly one Cypress run required')
    run = runs[0]; require(not run.get('error') and not run.get('errors'), 'Cypress run/hook error')
    spec_path(run.get('spec', {}).get('relative'))
    tests = run.get('tests', [])
    require(len(tests) == 1 and report.get('totalTests') == 1, 'report must contain exactly one Cypress test')
    test = tests[0]
    require(test.get('title', [None])[-1] == selector, 'selected title mismatch')
    require(report.get('totalPending') == 0 and report.get('totalSkipped') == 0, 'skipped/pending Cypress test')
    attempts = test.get('attempts', [])
    require(len(attempts) == 1, 'report must contain one attempt')
    status = test.get('state'); require(status in ('passed', 'failed') and attempts[0].get('state') == status, 'invalid Cypress outcome')
    counts = {'totalPassed': int(status == 'passed'), 'totalFailed': int(status == 'failed')}
    require(all(report.get(k) == v for k, v in counts.items()), 'inconsistent Cypress counts')
    if run.get('stats') is not None:
        require(all(run['stats'].get(k) == v for k,v in {'tests':1,'passes':int(status == 'passed'),'failures':int(status == 'failed'),'pending':0,'skipped':0}.items()), 'inconsistent Cypress run stats')
    errors = [error_text(e) for e in (test.get('displayError'), attempts[0].get('error')) if e]
    require(status != 'passed' or not errors, 'passed Cypress test contains errors')
    return status, errors


def run_command(config, project, phase, report, out):
    replacements = {'{project}': str(project), '{phase}': phase, '{report}': str(report)}
    replacements['{selector}'] = config['_selector']
    argv = config['argv'][:]
    for i, arg in enumerate(argv):
        for old, new in replacements.items(): arg = arg.replace(old, new)
        argv[i] = arg
    env = environment()
    env.update({'CI': '1', 'CYPRESS_retries': '0', 'E2E_PROBE_PHASE': phase,
                'E2E_PROBE_REPORT': str(report), 'E2E_PROBE_SELECTOR': config['_selector'],
                'E2E_PROBE_WORKERS': '1', 'E2E_PROBE_RETRIES': '0'})
    receipt = {'argv': argv, 'cwd': str(project), 'environment_names': sorted(env)}
    with (out / 'stdout.txt').open('xb') as stdout, (out / 'stderr.txt').open('xb') as stderr:
        process = subprocess.Popen(argv, cwd=project, env=env, stdout=stdout, stderr=stderr, start_new_session=True)
        try:
            receipt['exit_code'] = process.wait(timeout=config.get('timeout_seconds', 120))
        except subprocess.TimeoutExpired:
            receipt['exit_code'] = None; receipt['timeout'] = True
        finally:
            if os.name == 'posix':
                try:
                    os.killpg(process.pid, signal.SIGKILL)
                    receipt['owned_process_group_cleanup'] = True
                except ProcessLookupError:
                    receipt['owned_process_group_cleanup'] = 'already exited'
            elif process.poll() is None:
                process.kill()
            process.wait()
    (out / 'command.json').write_text(json.dumps(receipt, indent=2) + '\n')
    return receipt


def execute(plan, source, files, deps, output):
    phases = {}; error = None
    before_digest = digest(json.dumps(files, sort_keys=True).encode())
    after_digest = None
    try:
        for phase in ('normal', 'fault', 'restored'):
            folder = output / phase; folder.mkdir(); project = folder / 'project'; project.mkdir()
            for name, info in files.items():
                dest = project / name; dest.parent.mkdir(parents=True, exist_ok=True)
                data = (source / name).read_bytes(); require(digest(data) == info['sha256'], 'source changed during copy')
                dest.write_bytes(data); dest.chmod(info['mode'])
            for name, target in deps:
                dest = project / name; dest.parent.mkdir(parents=True, exist_ok=True); dest.symlink_to(target, target_is_directory=True)
            expected = {name: info['sha256'] for name, info in files.items()}
            if phase == 'fault':
                for edit in plan['edits']:
                    dest = project / edit['path']; dest.write_bytes(dest.read_bytes().replace(edit['before'].encode(), edit['after'].encode(), 1))
                    expected[edit['path']] = digest(dest.read_bytes())
            report = project / plan['report']['path']; report.parent.mkdir(parents=True, exist_ok=True)
            test_dir = folder / 'test'; test_dir.mkdir()
            native = run_command(dict(plan['test'], _selector=plan['test_selector']), project, phase, report, test_dir)
            no_symlinks(report)
            require(report.is_file(), 'native report missing')
            native_report = json.loads(report.read_text())
            status, errors = parse_native(native_report, plan['report']['format'], plan['test_selector'], plan['test_paths'], project)
            require(native['exit_code'] == (0 if status == 'passed' else 1), 'native exit/report mismatch')
            item = {'native': status, 'errors': errors, 'report_sha256': digest(report.read_bytes()), 'source_files': expected}
            if plan['report']['format'] == 'playwright-json':
                item['report_rootDir_resolved'] = str(report_root(native_report, project))
            phases[phase] = item
            if plan.get('observer'):
                observer_dir = folder / 'observer'; observer_dir.mkdir()
                observed = run_command(dict(plan['observer'], _selector=plan['test_selector']), project, phase, report, observer_dir)
                require(observed['exit_code'] == 0, 'observer command failed')
                observation = json.loads((observer_dir / 'stdout.txt').read_text())
                require(type(observation.get('promised_effect')) is bool and type(observation.get('fault_reached')) is bool, 'invalid observer booleans')
                require(observation.get('project') == str(project), 'observer phase provenance mismatch')
                evidence = observation.get('evidence')
                require(isinstance(evidence, list) and evidence, 'observer requires actual evidence files')
                for entry in evidence:
                    keys(entry, ('path', 'sha256'), ('path', 'sha256'))
                    evidence_name = relative(entry['path'])
                    require(evidence_name not in files and evidence_name != plan['report']['path'], 'observer evidence must be a fresh observation artifact')
                    evidence_path = project / evidence_name; no_symlinks(evidence_path)
                    require(evidence_path.is_file() and digest(evidence_path.read_bytes()) == entry['sha256'], 'observer evidence missing or hash mismatch')
                item['observer'] = observation
            for name, wanted in expected.items():
                no_symlinks(project / name)
                require(digest((project / name).read_bytes()) == wanted, 'phase source/test changed: ' + name)
                require(stat.S_IMODE((project / name).stat().st_mode) == files[name]['mode'], 'phase source mode changed: ' + name)
            require(tree(source) == files, 'original source changed')
    except (ValueError, OSError, KeyError, TypeError, AttributeError, json.JSONDecodeError) as exc:
        error = str(exc)
    finally:
        try:
            after_tree = tree(source)
            after_digest = digest(json.dumps(after_tree, sort_keys=True).encode())
            require(after_tree == files, 'original source changed')
        except (ValueError, OSError) as exc: error = str(exc)
    verdict = 'CANNOT_VERIFY'
    if error is None and len(phases) == 3:
        baseline = all(phases[p]['native'] == 'passed' for p in ('normal', 'restored'))
        if plan.get('observer'):
            baseline = baseline and all(phases[p]['observer']['promised_effect'] for p in ('normal', 'restored'))
        fault = phases['fault']; expected = plan['expected_failure']
        linked = fault['native'] == 'failed' and any(all(s in error for s in expected.values()) for error in fault['errors'])
        if baseline:
            if plan['mode'] == 'assertion-mutation':
                if linked: verdict = 'ASSERTION_SENSITIVE'
            elif fault['observer']['fault_reached'] and not fault['observer']['promised_effect']:
                if linked: verdict = 'DETECTED'
                elif fault['native'] == 'passed': verdict = 'SURVIVED'
    if verdict == 'CANNOT_VERIFY' and error is None:
        reasons = []
        for phase in ('normal', 'restored'):
            if phases[phase]['native'] != 'passed': reasons.append(phase + ' native baseline did not pass')
            if plan.get('observer') and not phases[phase]['observer']['promised_effect']: reasons.append(phase + ' promised effect absent')
        if plan['mode'] == 'behavior-fault':
            if not phases['fault']['observer']['fault_reached']: reasons.append('fault was not reached')
            if phases['fault']['observer']['promised_effect']: reasons.append('fault wrong state was not observed')
        if phases['fault']['native'] == 'failed' and not linked: reasons.append('fault failure did not link string and location in the same error')
        if plan['mode'] == 'assertion-mutation' and not linked: reasons.append('assertion mutation produced no linked failure')
        error = '; '.join(reasons) or 'incomplete three-phase evidence'
    return {'verdict': verdict, 'error': error, 'phases': phases, 'limitation': LIMITATION,
            'source_before_sha256': before_digest, 'source_after_sha256': after_digest,
            'original_source_unchanged': before_digest == after_digest,
            'behavior_proof': plan['mode'] == 'behavior-fault' and verdict in ('SURVIVED', 'DETECTED')}


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--plan', type=Path, required=True)
    parser.add_argument('--output-dir', type=Path, required=True)
    parser.add_argument('--preview', action='store_true')
    parser.add_argument('--execute', action='store_true')
    parser.add_argument('--trust-checkout', action='store_true')
    parser.add_argument('--approve-sha256')
    args = parser.parse_args(argv)
    output = args.output_dir.expanduser().absolute()
    owns_output = False
    result = {'verdict': 'ERROR', 'limitation': LIMITATION}
    try:
        require(not (args.preview and args.execute), 'choose preview or execute')
        plan = json.loads(args.plan.read_text())
        source, files, deps, approval = prepare(plan)
        output = absolute(str(output))
        require(not output.exists() and not output.is_relative_to(source) and not source.is_relative_to(output), 'output must be fresh and outside source')
        if args.execute:
            require(args.trust_checkout, '--trust-checkout required before command execution')
            require(args.approve_sha256 == approval, 'stale or missing approval digest')
        output.mkdir(parents=True)
        owns_output = True
        frozen = {'plan': plan, 'source_files': files, 'approval_sha256': approval, 'runner_sha256': digest(Path(__file__).read_bytes()), 'effective_environment': environment(), 'limitation': LIMITATION}
        (output / 'preview.json').write_text(json.dumps(frozen, indent=2) + '\n')
        if args.execute:
            require(prepare(plan)[3] == approval, 'source changed since approval check')
            result = execute(plan, source, files, deps, output)
        else:
            result = {'verdict': 'PREVIEW', 'approval_sha256': approval, 'limitation': LIMITATION, 'commands_executed': 0}
        (output / 'result.json').write_text(json.dumps(result, indent=2) + '\n')
    except (ValueError, OSError, KeyError, TypeError, AttributeError, json.JSONDecodeError) as exc:
        result['error'] = str(exc)
    result['candidate'] = {'source': str(source) if 'source' in locals() else None, 'selector': plan.get('test_selector') if 'plan' in locals() and isinstance(plan, dict) else None}
    result['runner'] = {'sha256': digest(Path(__file__).read_bytes()), 'execution': 'trusted local subprocesses; no sandbox'}
    result['sourceUnchanged'] = result.get('original_source_unchanged')
    result['temporaryArtifactsRemaining'] = str(output) if output.exists() else None
    result['verification'] = {key: {'verdict': 'CANNOT_VERIFY', 'reason': 'Not established by this bounded probe'} for key in ('V1','V2','V3','V4','V5','V6')}
    if result['verdict'] == 'ASSERTION_SENSITIVE':
        result['verification']['V2'] = {'verdict': 'PASS', 'reason': 'Normal/recovery pass and exact assertion mutation produces linked failure; no behavior proof'}
    elif result['verdict'] in ('DETECTED', 'SURVIVED'):
        result['verification']['V3'] = {'verdict': 'PASS' if result['verdict'] == 'DETECTED' else 'FAIL', 'reason': 'Promised fault reached with wrong state; selected test ' + ('detected linked assertion failure' if result['verdict'] == 'DETECTED' else 'survived')}
    if owns_output:
        (output / 'result.json').write_text(json.dumps(result, indent=2) + '\n')
    print(json.dumps(result, indent=2))
    return 0 if result['verdict'] in ('PREVIEW', 'DETECTED', 'SURVIVED', 'ASSERTION_SENSITIVE') else 2

if __name__ == '__main__':
    sys.exit(main())
