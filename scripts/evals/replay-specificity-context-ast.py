#!/usr/bin/env python3
"""Apache-2.0. Offline AST diagnostic on a hash-verified intake; never admission."""
import argparse
import hashlib
import json
from pathlib import Path, PurePosixPath
import subprocess
import tempfile

ROOT = Path(__file__).resolve().parents[2]
ANALYZER = ROOT / 'scripts/evals/specificity-context-ast.cjs'


def sha(data):
    return hashlib.sha256(data).hexdigest()


WRAPPER_SHA256 = sha(Path(__file__).read_bytes())


def validate_report(report, expected):
    if (not isinstance(report, dict) or report.get('source_sha256') != expected
            or report.get('context_completeness_proven') is not False
            or report.get('evaluation_allowed') is not False or report.get('version') != 'typescript-context-v1'
            or report.get('parser_version') != '6.0.3' or report.get('limitations') != [
                'static-bindings-do-not-prove-execution-or-postconditions', 'staged-files-not-whole-repository', 'configuration-not-executed']
            or any(not isinstance(report.get(k), list) or any(not isinstance(r, dict) for r in report[k])
                   for k in ('imports', 'calls', 'exports', 'configs', 'unresolved'))):
        raise ValueError('AST report source or admission contract mismatch')


def analyze(files, parser, node):
    if sha(Path(__file__).read_bytes()) != WRAPPER_SHA256:
        raise ValueError('wrapper changed after import')
    parser = Path(parser).resolve(strict=True)
    node = Path(node).resolve(strict=True)
    provenance = {parser: sha(parser.read_bytes()), ANALYZER: sha(ANALYZER.read_bytes()), node: sha(node.read_bytes())}
    with tempfile.TemporaryFile() as stdout, tempfile.TemporaryFile() as stderr:
        result = subprocess.run([str(node), '--max-old-space-size=512', str(ANALYZER), str(parser)],
                                input=json.dumps({'files': files}).encode(), stdout=stdout, stderr=stderr,
                                timeout=60, cwd=ROOT, env={'PATH': '/usr/bin:/bin', 'LANG': 'C.UTF-8'})
        if result.returncode:
            stderr.seek(max(0, stderr.tell() - 2000))
            raise ValueError('AST parser failed: ' + stderr.read(2000).decode(errors='replace'))
        if stdout.tell() > 4000000:
            raise ValueError('AST output budget')
        stdout.seek(0)
        report = json.load(stdout)
    if (sha(Path(__file__).read_bytes()) != WRAPPER_SHA256
            or any(sha(p.read_bytes()) != h for p, h in provenance.items())
            or report['parser_sha256'] != provenance[parser]
            or report['node_sha256'] != provenance[node]
            or report['implementation_sha256'] != provenance[ANALYZER]):
        raise ValueError('parser changed during analysis')
    expected = {p: sha(s.encode()) for p, s in files.items()}
    validate_report(report, expected)
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--typescript', type=Path, required=True, help='trusted TypeScript 6.0.3 lib/typescript.js')
    parser.add_argument('--node', type=Path, required=True, help='trusted absolute Node executable')
    args = parser.parse_args()
    source, output = args.source.resolve(strict=True), args.output.resolve()
    if (output.exists() or output.is_relative_to(ROOT) or output.is_relative_to(source)
            or source.is_relative_to(output)):
        raise ValueError('fresh external output separate from input required')
    original = (source / 'context-report.json').read_bytes()
    intake = json.loads(original)
    rows, snapshots = [], {}
    ids = [case['id'] for case in intake['cases']]
    if not ids or len(set(ids)) != len(ids):
        raise ValueError('nonempty unique case ids required')
    for case in intake['cases']:
        case_id = case['id']
        if not isinstance(case_id, str) or not case_id or '/' in case_id or '\\' in case_id or case_id in {'.', '..'}:
            raise ValueError('invalid case id')
        base = source / 'sources' / case_id
        files = {}
        for name, digest in case['source_sha256'].items():
            p = PurePosixPath(name)
            if p.is_absolute() or '..' in p.parts or '\\' in name:
                raise ValueError('unsafe source path')
            target = (base / name).resolve(strict=True)
            if not target.is_relative_to(base.resolve()) or not target.is_relative_to(source):
                raise ValueError('source escape')
            data = target.read_bytes()
            if sha(data) != digest:
                raise ValueError('staged source hash mismatch')
            snapshots[target] = digest
            files[name] = data.decode('utf-8')
        rows.append({'id': case_id, 'repository': case['repository'], 'commit': case['commit'],
                     **analyze(files, args.typescript, args.node)})
    if (source / 'context-report.json').read_bytes() != original or any(sha(p.read_bytes()) != h for p, h in snapshots.items()):
        raise ValueError('source changed during replay')
    result = {'status': 'diagnostic-complete', 'evaluation_allowed': False, 'network_calls': 0, 'model_calls': 0,
              'network_policy': 'analyzer performs no network operations; not an OS sandbox attestation',
              'context_report_sha256': sha(original), 'wrapper_sha256': WRAPPER_SHA256, 'cases': rows}
    output.mkdir(parents=True, exist_ok=False)
    (output / 'ast-context-report.json').write_text(json.dumps(result, indent=2, sort_keys=True) + '\n')
    print(json.dumps({'status': result['status'], 'cases': [
        {'id': r['id'], 'imports': len(r['imports']), 'calls': len(r['calls']),
         'bound_calls': sum(c['declaration'] is not None for c in r['calls']),
         'unresolved': len(r['unresolved']), 'configs': len(r['configs'])} for r in rows]}))


if __name__ == '__main__':
    main()
