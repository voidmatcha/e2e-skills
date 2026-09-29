#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Validate the published semantic-mutant corpus and score ledger offline."""
import hashlib
import json
from pathlib import Path, PurePosixPath

BASE = Path(__file__).resolve().parents[2] / 'benchmarks/semantic-mutants-v1'

def check(ok, message):
    if not ok:
        raise AssertionError(message)

def load(name):
    return json.loads((BASE / name).read_text())

def check_case_files(root, cases, allowed_severities={'P0', 'P1'}):
    for case in cases:
        check(case['quoted_rule'] and case['verifier_reason'] and case['edit'], 'provenance fields')
        check(case['severity'] in allowed_severities and case['line'] > 0, 'label fields')
        for side in ('mutant', 'original'):
            entry = case['files'][side]
            rel = PurePosixPath(entry['path'])
            check(not rel.is_absolute() and '..' not in rel.parts and rel.parts[0] == 'cases', 'safe path')
            path = root / rel
            check(path.is_file() and not path.is_symlink(), 'spec file')
            check(hashlib.sha256(path.read_bytes()).hexdigest() == entry['sha256'], 'spec digest')
        mutant = (root / case['files']['mutant']['path']).read_text().splitlines()
        check(mutant[case['line']-1] == case['source_line'], 'mutant source line')

def check_scores(batch, ids, expected):
    root = BASE / 'batches' / batch
    rows = json.loads((root / 'scores/samples.json').read_text())
    summary = json.loads((root / 'scores/summary.json').read_text())
    check(len(rows) == len(ids) * 4 and summary['sample_count'] == len(rows) and
          summary['case_count'] == len(ids), f'{batch} sample count')
    for arm, strict, lenient, alarms, mean in expected:
        subset = [r for r in rows if r['arm'] == arm]
        check(len(subset) == len(ids) * 2, f'{batch} arm sample count')
        check({(r['case'], r['side']) for r in subset} ==
              {(cid, side) for cid in ids for side in ('before', 'after')},
              f'{batch} sample identity')
        def total(metric, field, side):
            return sum(r['scores'][metric][field] for r in subset if r['side'] == side)
        check(total('strict_recall', 'hits', 'before') == strict, f'{batch} strict hits')
        check(total('lenient_recall', 'hits', 'before') == lenient, f'{batch} lenient hits')
        check(total('after_false_alarm', 'alarms', 'after') == alarms, f'{batch} AFTER alarms')
        check(total('strict_recall', 'n', 'before') == len(ids), f'{batch} BEFORE denominator')
        check(total('after_false_alarm', 'n', 'after') == len(ids), f'{batch} AFTER denominator')
        check(abs(sum(r['input_tokens'] for r in subset)/len(subset) - mean) < 0.01,
              f'{batch} token mean')
        aggregate = summary['arms'][arm]
        check(aggregate['samples'] == len(subset) and
              aggregate['strict_recall']['hits'] == strict and
              aggregate['lenient_recall']['hits'] == lenient and
              aggregate['after_false_alarm']['alarms'] == alarms and
              abs(aggregate['input_tokens']['mean'] - mean) < 0.01,
              f'{batch} summary arithmetic')
    return rows

def run():
    corpus = load('corpus.json')
    cases = corpus['cases']
    check(corpus['schema_version'] == 1 and len(cases) == 10, 'corpus count')
    check(corpus['provenance']['human_labels'] is False, 'label provenance')
    ids = [case['id'] for case in cases]
    check(len(set(ids)) == 10, 'unique cases')
    check({case['pattern_id'] for case in cases} == {'#1', '#2'}, 'pattern scope')
    check(sum(case['verifier_verdict'] == 'confirm' for case in cases) == 9, 'confirmed labels')
    check(sum(case['verifier_verdict'] == 'correct' for case in cases) == 1, 'corrected label')
    corrected = next(case for case in cases if case['verifier_verdict'] == 'correct')
    check((corrected['id'], corrected['pattern_id'], corrected['severity']) ==
          ('then-onboarding-submit', '#2', 'P1'), 'corrected P1')
    for case in cases:
        check(case['repo'] in {'payload', 'storybook'} and case['license'] == 'MIT', 'license metadata')
    check_case_files(BASE, cases)
    for repo in ('payload', 'storybook'):
        path = BASE / 'licenses' / f'{repo}-LICENSE.txt'
        reference = BASE.parent / 'fixpair-v1' / 'licenses' / path.name
        check(path.read_bytes() == reference.read_bytes(), 'upstream license copy')
    rows = load('scores/samples.json')
    summary = load('scores/summary.json')
    check(len(rows) == 40 and summary['sample_count'] == 40 and summary['case_count'] == 10, 'sample count')
    for arm, strict, lenient, alarms, mean in (('skill', 7, 7, 1, 558223.6),
                                                ('no-skill', 5, 7, 1, 138077.7)):
        subset = [r for r in rows if r['arm'] == arm]
        check(len(subset) == 20, 'arm sample count')
        check({(r['case'], r['side']) for r in subset} ==
              {(cid, side) for cid in ids for side in ('before', 'after')}, 'sample identity')
        def total(metric, field, side):
            return sum(r['scores'][metric][field] for r in subset if r['side'] == side)
        check(total('strict_recall', 'hits', 'before') == strict, 'strict hits')
        check(total('lenient_recall', 'hits', 'before') == lenient, 'lenient hits')
        check(total('after_false_alarm', 'alarms', 'after') == alarms, 'AFTER alarms')
        check(total('strict_recall', 'n', 'before') == 10, 'BEFORE denominator')
        check(total('after_false_alarm', 'n', 'after') == 10, 'AFTER denominator')
        check(abs(sum(r['input_tokens'] for r in subset)/20 - mean) < 0.01, 'token mean')
        aggregate = summary['arms'][arm]
        check(aggregate['samples'] == 20 and
              aggregate['strict_recall']['hits'] == strict and
              aggregate['lenient_recall']['hits'] == lenient and
              aggregate['after_false_alarm']['alarms'] == alarms and
              abs(aggregate['input_tokens']['mean'] - mean) < 0.01, 'summary arithmetic')
    # S2 publishes four #23 fixture mutants and five reworked #20 pass-through
    # writes. All labels were independently confirmed.
    s2root = BASE / 'batches/s2'
    s2 = json.loads((s2root / 'corpus.json').read_text())
    s2cases = s2['cases']
    check(s2['schema_version'] == 1 and s2['batch'] == 'S2' and len(s2cases) == 9, 'S2 corpus count')
    check(s2['provenance']['human_labels'] is False, 'S2 label provenance')
    check(sum(c['pattern_id'] == '#23' and c['severity'] == 'P2' for c in s2cases) == 4,
          'S2 #23 labels')
    check(sum(c['pattern_id'] == '#20' and c['severity'] == 'P1' for c in s2cases) == 5,
          'S2 #20 labels')
    check({c['repo'] for c in s2cases} == {'payload', 'refine'} and
          all(c['license'] == 'MIT' and c['verifier_verdict'] == 'confirm' for c in s2cases),
          'S2 verification')
    check_case_files(s2root, s2cases, {'P1', 'P2'})
    for case in (c for c in s2cases if c['pattern_id'] == '#20'):
        mutant = (s2root / case['files']['mutant']['path']).read_text()
        check('req.continue()' in mutant, 'S2 #20 pass-through mutation')
    s2rows = check_scores('s2', [c['id'] for c in s2cases],
                          (('skill', 8, 8, 0, 520121.3888888889),
                           ('no-skill', 2, 7, 0, 134502.05555555556)))
    for arm, p20_strict, p20_lenient, p23_strict in (('skill', 5, 5, 3),
                                                      ('no-skill', 0, 5, 2)):
        before = [r for r in s2rows if r['arm'] == arm and r['side'] == 'before']
        p20 = [r for r in before if r['case'].startswith('p20-')]
        p23 = [r for r in before if r['case'].startswith('fixture-')]
        check(sum(r['scores']['strict_recall']['hits'] for r in p20) == p20_strict and
              sum(r['scores']['lenient_recall']['hits'] for r in p20) == p20_lenient and
              sum(r['scores']['strict_recall']['hits'] for r in p23) == p23_strict,
              f'S2 pattern totals {arm}')

    # S3 isolates #22 in refine's optimistic mutation mode.
    s3root = BASE / 'batches/s3'
    s3 = json.loads((s3root / 'corpus.json').read_text())
    s3cases = s3['cases']
    check(s3['schema_version'] == 1 and s3['batch'] == 'S3' and len(s3cases) == 6, 'S3 corpus count')
    check(s3['provenance']['human_labels'] is False, 'S3 label provenance')
    check(all(c['repo'] == 'refine' and c['license'] == 'MIT' and
              c['pattern_id'] == '#22' and c['severity'] == 'P1' and
              c['verifier_verdict'] == 'confirm' for c in s3cases), 'S3 verification')
    check_case_files(s3root, s3cases)
    check_scores('s3', [c['id'] for c in s3cases],
                 (('skill', 5, 5, 0, 680515.5833333334),
                  ('no-skill', 2, 3, 2, 136168.91666666666)))

    for batch, count, expected in (
        ('s2', 9, (('skill', 3, 4, 0, 6838330), ('no-skill', 4, 7, 2, 740151))),
        ('s3', 6, (('skill', 5, 5, 0, 5098989), ('no-skill', 3, 4, 2, 587133))),
    ):
        sonnet_rows = json.loads((BASE / 'batches' / batch / 'scores/sonnet-5-5-samples.json').read_text())
        check(len(sonnet_rows) == count * 4, f'{batch} Sonnet 5.5 sample count')
        for arm, strict, lenient, alarms, tokens in expected:
            rows = [row for row in sonnet_rows if row['arm'] == arm]
            check(len(rows) == count * 2 and len({row['sample'] for row in rows}) == count * 2,
                  f'{batch} Sonnet 5.5 {arm} sample identities')
            check(sum(row['strict_recall']['hits'] for row in rows) == strict and
                  sum(row['strict_recall']['n'] for row in rows) == count and
                  sum(row['lenient_recall']['hits'] for row in rows) == lenient and
                  sum(row['after_false_alarm']['alarms'] for row in rows) == alarms and
                  sum(row['input_tokens'] for row in rows) == tokens,
                  f'{batch} Sonnet 5.5 {arm} totals')

    refine_license = BASE / 'licenses/refine-LICENSE.txt'
    check(refine_license.is_file() and
          hashlib.sha256(refine_license.read_bytes()).hexdigest() ==
          'ae616936d77df09838b97cb6d4a41921bcd47b676fe9ce623a5ee4cdbb1db91f',
          'refine license copy')

    readme = (BASE / 'README.md').read_text()
    for claim in ('7/10', '5/10', '+20 percentage points', '8/9', '2/9', '7/9',
                  '5/6', '2/6', '3/6', '13/15', '4/15', 'req.continue()',
                  'model-injected defects in real code', 'one repository, refine',
                  '#12 is not covered'):
        check(claim in readme, f'README claim: {claim}')
    print('semantic mutants v1: S1 10 cases/40 samples; S2 strict 8/9 vs 2/9, '
          'lenient 8/9 vs 7/9, alarms 0/9 each; S3 strict 5/6 vs 2/6, '
          'lenient 5/6 vs 3/6, alarms 0/6 vs 2/6')

if __name__ == '__main__':
    run()
