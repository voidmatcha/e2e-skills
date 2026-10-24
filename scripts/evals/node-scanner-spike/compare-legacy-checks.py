#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Reproduce bounded call-variant comparisons, without executing project config.

python3 scripts/evals/node-scanner-spike/compare-legacy-checks.py --output /new/cache/path
Each legacy call needs its own observed target hit; absence is UNMEASURED.
This is a synthetic compatibility study, not grammar coverage or accuracy evidence.
"""
import argparse
import collections
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
import time


def digest(data):
    return hashlib.sha256(data).hexdigest()


def write_json(path, value):
    path.write_text(json.dumps(value, indent=2) + '\n')


def run_environments(ambient):
    """Legacy backend controls must never reach the current CLI."""
    clean = {k: v for k, v in ambient.items()
             if not k.startswith('E2E_SMELL_') and k not in ('BASH_ENV', 'ENV', 'NODE_OPTIONS', 'NODE_PATH')}
    overrides = {'E2E_SMELL_ALLOW_PROJECT_ESLINT': '0', 'E2E_SMELL_NO_ESLINT_DOWNLOAD': '1',
                 'E2E_SMELL_DISABLE_AST_GREP': '1', 'E2E_SMELL_NO_AST_GREP_DOWNLOAD': '1',
                 'E2E_SMELL_FAIL_ON': 'none'}
    return clean, {**clean, **overrides}, overrides


def trace_legacy_calls(original, calls, case_count):
    literal_calls = [(n, line) for n, line in enumerate(original.splitlines(), 1) if line.startswith('run_check ')]
    assert len(calls) == len(literal_calls) == case_count == 69
    traced = []
    index = 0
    for line in original.splitlines(keepends=True):
        if line.startswith('run_check '):
            index += 1
            assert calls[index-1]['call_index'] == index
            assert calls[index-1]['legacy']['call'] == line.rstrip('\n')
            traced.extend([f"printf '%s\\n' '__E2E_CALL_BEGIN__ {index}'\n", line,
                           f"printf '%s\\n' '__E2E_CALL_END__ {index}'\n"])
        else:
            traced.append(line)
    return ''.join(traced), literal_calls


def read_node_result(result, expected, target_line, arm, filename):
    """Missing or malformed evidence must never count as a target observation."""
    invalid = {'exitCode': result.returncode, 'invalidReport': True}
    try:
        report = json.loads(result.stdout)
    except (ValueError, TypeError):
        return {**invalid, 'invalidJson': True}
    if not isinstance(report, dict) or report.get('schema') != 'e2e-skills-node-scan-v1':
        return invalid
    execution = report.get('execution')
    findings = report.get('findings')
    if (not isinstance(execution, dict) or not isinstance(findings, list)
            or type(execution.get('complete')) is not bool
            or execution.get('exitCode') != result.returncode
            or not isinstance(execution.get('diagnostics'), list)
            or not isinstance(execution.get('incomplete'), list)):
        return invalid
    for finding in findings:
        if (not isinstance(finding, dict) or not isinstance(finding.get('patternId'), str)
                or finding.get('severity') not in ('P0', 'P1', 'P2')
                or type(finding.get('line')) is not int or finding['line'] < 1
                or finding.get('file') != str(filename)
                or not isinstance(finding.get('disposition'), str)):
            return invalid
    target = [f for f in findings if f['patternId'] == expected['pattern_id']
              and f['severity'] == expected['severity']
              and (arm == 'negative' or f['line'] == target_line)]
    return {'exitCode': result.returncode, 'findings': findings,
            'target_pattern_findings': target, 'diagnostics': execution['diagnostics'],
            'incomplete': execution['incomplete'], 'complete': execution['complete']}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True, help='New external evidence directory')
    parser.add_argument('--dependency-dir', type=Path, help='Existing scanner node_modules directory; copied, never installed')
    args = parser.parse_args()
    root = Path(__file__).resolve().parents[3]
    out = args.output.expanduser().resolve()
    if out.exists() or out == root or root in out.parents:
        parser.error('output must be a new directory outside the checkout')
    out.mkdir(parents=True)
    corpus = out / 'corpus'
    corpus.mkdir()
    sources = sorted(set([
        *root.glob('skills/e2e-reviewer/scripts/*.*'),
        *root.glob('packages/scanner/src/**/*'),
        *root.glob('scripts/ci/fixtures/legacy-scanner/*'),
        root / 'scripts/ci/lib/legacy_scanner_oracle.py',
        root / 'packages/scanner/package.json',
        root / 'packages/scanner/package-lock.json',
        root / 'scripts/ci/test-reviewer-scanner.py',
        Path(__file__).resolve(),
        Path(__file__).with_name('legacy-check-canaries.json'),
        Path(__file__).with_name('migration-coverage.json'),
    ]))
    before = {}
    snap = out / 'source-snapshot'
    for path in sources:
        if not path.is_file():
            continue
        rel = path.relative_to(root)
        data = path.read_bytes()
        target = snap / rel
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(data)
        before[str(rel)] = digest(data)
    write_json(out / 'source-before.json', before)
    # Freeze the existing parser dependency; never install or load project config.
    dependency = (args.dependency_dir or root / 'packages/scanner/node_modules').expanduser().resolve()
    if not dependency.exists():
        raise RuntimeError('existing scanner node_modules required; no automatic installation')
    parser_version = json.loads((dependency / 'typescript/package.json').read_text())['version']
    required_version = json.loads((snap / 'packages/scanner/package.json').read_text())['dependencies']['typescript']
    if parser_version != required_version:
        raise RuntimeError(f'parser dependency mismatch: expected {required_version}, got {parser_version}')
    frozen_dependency = snap / 'packages/scanner/node_modules/typescript'
    shutil.copytree(dependency / 'typescript', frozen_dependency)
    dependency_hashes = {str(p.relative_to(frozen_dependency)): digest(p.read_bytes())
                         for p in sorted(frozen_dependency.rglob('*')) if p.is_file()}
    write_json(out / 'dependency.json', {
        'typescriptVersion': json.loads((dependency / 'typescript/package.json').read_text())['version'],
        'source': str(dependency),
        'files': dependency_hashes,
    })
    corpus_spec = json.loads((snap / Path(__file__).relative_to(root)).with_name('legacy-check-canaries.json').read_text())
    ledger = json.loads((snap / 'scripts/evals/node-scanner-spike/migration-coverage.json').read_text())
    calls = ledger['calls']
    # Use the verified frozen shell oracle, never the current generated launcher.
    sys.path.insert(0, str(snap / 'scripts/ci'))
    from lib.legacy_scanner_oracle import legacy_scanner_file, MANIFEST_SHA256
    oracle_manifest = json.loads((snap / 'scripts/ci/fixtures/legacy-scanner/manifest.json').read_text())
    oracle = out / 'legacy-oracle'
    for entry in oracle_manifest['files']:
        data = legacy_scanner_file(entry['path']).read_bytes()
        target = oracle / entry['path']
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(data)
        target.chmod(entry['mode'])
    write_json(out / 'legacy-provenance.json', {
        'manifestSha256': MANIFEST_SHA256, 'manifest': oracle_manifest,
        'scope': 'Frozen shell run_check mechanisms with optional ESLint and ast-grep disabled',
    })
    scan = oracle / 'scan.sh'
    original = scan.read_text()
    traced, literal_calls = trace_legacy_calls(original, calls, len(corpus_spec['cases']))
    trace = scan.with_name('scan-trace.sh')
    trace.write_text(traced)
    manifest = []
    for case in corpus_spec['cases']:
        for arm in ('positive', 'negative'):
            name = f"{case['call_index']:02}-{arm}{case['extension']}"
            data = case[arm].encode()
            (corpus / name).write_bytes(data)
            manifest.append({'path': name, 'call_index': case['call_index'], 'arm': arm,
                             'sha256': digest(data), 'provenance': case['provenance']})
    write_json(out / 'corpus-manifest.json', manifest)
    node_env, legacy_env, legacy_overrides = run_environments(os.environ)
    runs = []

    def run(name, argv, *, legacy=False):
        env = legacy_env if legacy else node_env
        overrides = legacy_overrides if legacy else {}
        started = time.monotonic()
        result = subprocess.run(argv, cwd=snap, env=env, capture_output=True, timeout=900)
        (out / (name + '.stdout')).write_bytes(result.stdout)
        (out / (name + '.stderr')).write_bytes(result.stderr)
        runs.append({'name': name, 'argv': argv, 'cwd': str(snap), 'exitCode': result.returncode,
                     'seconds': round(time.monotonic()-started, 3), 'environmentOverrides': overrides,
                     'stdoutSha256': digest(result.stdout), 'stderrSha256': digest(result.stderr)})
        write_json(out / 'runs.json', runs)
        print(name, result.returncode, flush=True)
        return result

    baseline = run('legacy-original', ['/bin/bash', '-p', str(scan), str(corpus)], legacy=True)
    marked = run('legacy-traced', ['/bin/bash', '-p', str(trace), str(corpus)], legacy=True)
    mark_re = re.compile(rb'^__E2E_CALL_(?:BEGIN|END)__ \d+\n', re.M)
    trace_valid = mark_re.sub(b'', marked.stdout) == baseline.stdout and marked.returncode == baseline.returncode
    header_re = re.compile(r'^\[(P[012])\??\](?:\[LLM-TRIAGE\])? (#[\w-]+) (.*?) \(\d+ hits?\)$')
    sections = collections.defaultdict(list)
    active = None
    header = None
    for line in marked.stdout.decode().splitlines():
        if line.startswith('__E2E_CALL_BEGIN__ '):
            active = int(line.rsplit(' ', 1)[1]); header = None
        elif line.startswith('__E2E_CALL_END__ '):
            active = None; header = None
        elif active is not None:
            match = header_re.match(line)
            if match:
                header = {'severity': match[1], 'pattern_id': match[2], 'title': match[3]}
            elif header and line.startswith('  ' + str(corpus) + '/'):
                location = re.match(r'^  (.*?):(\d+):(.*)$', line)
                if location:
                    sections[active].append({**header, 'file': Path(location[1]).name,
                                             'line': int(location[2]), 'source': location[3]})
    cli = snap / 'packages/scanner/src/cli.mjs'
    node = shutil.which('node')
    if node is None:
        raise RuntimeError('node executable required')
    results = []
    for case, call in zip(corpus_spec['cases'], calls):
        idx = case['call_index']
        expected = {k: call['legacy'][k] for k in ('severity', 'pattern_id', 'title')}
        pos = f"{idx:02}-positive{case['extension']}"
        neg = f"{idx:02}-negative{case['extension']}"
        hits = [h for h in sections[idx] if all(h[k] == v for k, v in expected.items())]
        positive = [h for h in hits if h['file'] == pos and h['line'] == case['target_line']]
        negative = [h for h in hits if h['file'] == neg]
        row = {'call_index': idx, 'legacy_source': {'line': literal_calls[idx-1][0], 'call': literal_calls[idx-1][1]},
               'expected': expected, 'target_line': case['target_line'], 'positive_file': pos,
               'negative_file': neg, 'legacy_positive': positive, 'legacy_negative': negative,
               'measurement': 'MEASURED' if trace_valid and positive else 'UNMEASURED', 'node': {}}
        for arm, filename in (('positive', pos), ('negative', neg)):
            result = run(f'node-{idx:02}-{arm}', [node, str(cli), '--scan', str(corpus / filename), '--fail-on', 'p0'])
            row['node'][arm] = read_node_result(result, expected, case['target_line'], arm, corpus / filename)
        p = row['node']['positive']
        row['comparison'] = ('UNMEASURED' if row['measurement'] != 'MEASURED' else
                             'TARGET_PATTERN_FOUND' if p.get('target_pattern_findings') else
                             'SILENT_CLEAN_GAP' if p.get('exitCode') == 0 and p.get('complete') is True and not p.get('findings') and not p.get('diagnostics') and not p.get('incomplete') else
                             'NO_TARGET_PATTERN_WITH_DIAGNOSTIC_OR_OTHER_FINDING')
        results.append(row)
        write_json(out / 'comparison.json', results)
    after = {rel: digest((root / rel).read_bytes()) for rel in before}
    write_json(out / 'source-after.json', after)
    drift = [rel for rel in before if before[rel] != after[rel]]
    dependency_preserved = dependency_hashes == {
        str(p.relative_to(frozen_dependency)): digest(p.read_bytes())
        for p in sorted(frozen_dependency.rglob('*')) if p.is_file()}
    snapshot_preserved = all(digest((snap / rel).read_bytes()) == sha for rel, sha in before.items())
    oracle_preserved = all(digest((oracle / entry['path']).read_bytes()) == entry['sha256']
                           for entry in oracle_manifest['files'])
    summary = {'schema': 'legacy-call-comparison-v2',
               'node_mode': '--scan', 'equivalence_claimed': False,
               'scope': 'Per-call target pattern and severity presence at the positive target line; negative guards checked separately. Not whole-output or semantic equivalence.',
               'source_snapshot_preserved': snapshot_preserved,
               'dependency_snapshot_preserved': dependency_preserved,
               'legacy_oracle_preserved': oracle_preserved,
               'node_missing_target_call_indices': [r['call_index'] for r in results if not r['node']['positive'].get('target_pattern_findings')],
               'node_incomplete_runs': [{'call_index': r['call_index'], 'arm': arm}
                                        for r in results for arm in ('positive', 'negative')
                                        if r['node'][arm].get('complete') is not True or r['node'][arm].get('exitCode') not in (0, 1)],
               'node_invalid_report_runs': [{'call_index': r['call_index'], 'arm': arm}
                                            for r in results for arm in ('positive', 'negative')
                                            if r['node'][arm].get('invalidReport')],
               'node_negative_other_findings_call_indices': [r['call_index'] for r in results
                                                             if r['node']['negative'].get('findings')],
               'node_positive_target_dispositions': dict(collections.Counter(
                   f['disposition'] for r in results for f in r['node']['positive'].get('target_pattern_findings', []))),
               'target_multiplicity_differences': [{'call_index': r['call_index'],
                                                   'legacy': len(r['legacy_positive']),
                                                   'node': len(r['node']['positive'].get('target_pattern_findings', []))}
                                                  for r in results if len(r['legacy_positive']) != len(r['node']['positive'].get('target_pattern_findings', []))],
               'claims': '69 synthetic call variants, not all grammar or defect accuracy',
               'trace_matches_original_stdout': trace_valid, 'source_drift': drift,
               'counts': dict(collections.Counter(r['comparison'] for r in results)),
               'unmeasured_call_indices': [r['call_index'] for r in results if r['measurement'] == 'UNMEASURED'],
               'negative_target_hits_call_indices': [r['call_index'] for r in results if r['legacy_negative']],
               'node_negative_target_hits_call_indices': [r['call_index'] for r in results if r['node']['negative'].get('target_pattern_findings')],
               'node_negative_diagnostic_call_indices': [r['call_index'] for r in results if r['node']['negative'].get('diagnostics')],
               'silent_clean_gap_call_indices': [r['call_index'] for r in results if r['comparison'] == 'SILENT_CLEAN_GAP'],
               'corpus_preserved': all(digest((corpus / m['path']).read_bytes()) == m['sha256'] for m in manifest),
               'node_version': subprocess.check_output([node, '--version'], text=True).strip()}
    write_json(out / 'summary.json', summary)
    receipts = {str(p.relative_to(out)): digest(p.read_bytes()) for p in sorted(out.rglob('*')) if p.is_file() and 'node_modules' not in p.parts}
    write_json(out / 'receipt.json', receipts)
    print(json.dumps(summary, indent=2))
    # Exit status validates the evidence receipt, never declares scanner equivalence.
    return 0 if (trace_valid and summary['corpus_preserved'] and snapshot_preserved
                 and dependency_preserved and oracle_preserved and not drift) else 2


if __name__ == '__main__':
    raise SystemExit(main())
