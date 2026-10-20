#!/usr/bin/env python3
"""Offline-built Codex component ablation, repaired design (core cost tier plus quality tiers). Apache-2.0.

Imports the v4 multimodel runner (repaired evidence module that rejects a contradicting root thread), the machine-wide campaign lock and the
byte-identical historical design helpers. Every operation that executes a model or browser needs --allow-live, a freeze, an
ablation-specific harness check, a preflight, and the v3 admission of the chosen model.
"""
import argparse
import contextlib
from fractions import Fraction
import hashlib
import importlib.util
import json
import os
import random
import re
import shlex
import shutil
import sys
import tempfile
from pathlib import Path

sys.dont_write_bytecode = True
ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'scripts/evals'))
BENCH = ROOT / 'benchmarks/generator-ablation-v2'
PROTOCOL, LOCK, README = BENCH / 'protocol.json', BENCH / 'freeze.json', BENCH / 'README.md'
REVALIDATION = BENCH / 'manipulation-revalidation.json'
REF = BENCH / 'reference'
V3_FREEZE = ROOT / 'benchmarks/generator-multimodel-v3-codex/freeze.json'
THIN_SOURCE = ROOT / 'benchmarks/generator-thin-layer-v1/THIN-RULES.md'
HELPERS = ROOT / 'scripts/evals/generator_ablation_v2_stats.py'


def load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


rt = load('ablation_codex_v4', ROOT / 'scripts/evals/run-generator-multimodel-v4-codex.py')
zep = load('ablation_machine_lock', ROOT / 'scripts/evals/generator_oss_zeppelin.py')
stats = load('ablation_stats', HELPERS)
gab = load('ablation_historical_design', REF / 'generator_ablation_v1.py')
sig = load('ablation_historical_signals', REF / 'generator_ablation_signals.py')
orig, engine, ev, pooled = rt.orig, rt.engine, rt.evidence, rt.pooled
# These are private imported module instances, never another worker's runtime.
gab.BASE_DIR = REF / 'playwright-test-generator'
gab.COMPONENT_ORDER = ('L', 'E', 'P', 'R', 'V', 'VR')
BASE_DEFAULT = Path(tempfile.gettempdir()) / 'e2e-skills-bench-generator-ablation-v2'
PROTOCOL_ID = 'generator-ablation-v2'
COMPONENTS = ('L', 'E', 'P', 'R', 'V')
SIGNALS = ('L', 'E', 'P', 'R', 'V', 'V6', 'X')
TIERS = ('0', '0b', '1', '2')
HISTORICAL_DETECTORS = ('L', 'E', 'P', 'R')
VERDICT = re.compile(r'(?m)^\s*V6 VERDICT:\s*(?:PASS|FAIL)\b')
HARNESS_ARM = 'ablation-harness'
HARNESS_MARKER = 'ablation-harness-ok'
HARNESS_LINE = ('\n\nThis is a harness check, not a test-writing task: do not create or edit any file and do not run any command yourself. '
                'Spawn exactly one native agent. Tell it to run the shell command `echo ablation-harness-ok` and then to reply with exactly '
                'these two lines and nothing else:\nshell: <the command output>\nV6 VERDICT: PASS P0=0 P1=0 P2=0 reviewer=harness\n'
                'Wait for that agent to finish. Then finish with status `other` and the summary `harness check`.')
MODEL_ROSTER_KEY = 'offline_replay'


def read(path):
    return json.loads(Path(path).read_text())


def digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def file_hashes(root):
    return {p.relative_to(root).as_posix(): digest(p) for p in sorted(Path(root).rglob('*'))
            if p.is_file() and '__pycache__' not in p.parts and p.name != '.DS_Store'}


# ------------------------------------------------------------------------------------------------------- model choice

def rule_outcome(selection):
    """The model the stated rule selects, computed from the stored offline replay (never from a score)."""
    candidates = []
    for model, row in selection[MODEL_ROSTER_KEY].items():
        if row.get('C_calls_observed') == selection['scheduled'] and row.get('panel_complete', True) is not False:
            candidates.append((-row['execution_and_child_V6'], -row['delivered'], model))
    if not candidates:
        raise ValueError('no model has a completed arm-C panel in the replay')
    return sorted(candidates)[0][2]


def check_model_choice(p):
    selection = p['model_selection']
    outcome = rule_outcome(selection)
    if selection.get('rule_outcome') != outcome:
        raise ValueError('stored rule_outcome differs from the outcome computed from the replay')
    if p['model'] == outcome:
        return {'mode': 'stated-rule', 'model': outcome}
    owner = selection.get('owner_choice') or {}
    if (owner.get('model') != p['model'] or p['model'] not in selection[MODEL_ROSTER_KEY]
            or not re.fullmatch(r'\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z', str(owner.get('recorded_utc') or ''))
            or not str(owner.get('statement') or '').strip()):
        raise ValueError('model differs from the stated rule outcome without a complete owner_choice record')
    return {'mode': 'owner-choice', 'model': p['model'], 'rule_outcome': outcome, 'recorded_utc': owner['recorded_utc']}


def model_cfg(p):
    return {'id': p['model'], 'runner': 'codex', 'family': 'codex', 'lineage': 'gpt-6', 'order': 1}


def v3_admission(model, v3_dir=None):
    """Read exactly the chosen model's entry decision of the Codex v3 campaign; fail closed on anything else."""
    base = Path(v3_dir or os.environ.get('MULTIMODEL_V3_CODEX_DIR') or Path.home() / '.cache/e2e-skills-bench/multimodel-v3-codex')
    entry = base / '_entry' / (model + '.json')
    if not entry.is_file():
        raise ValueError('v3 admission missing for ' + model + ': the Codex v3 entry decision is a precondition')
    data = read(entry)
    criteria = data.get('harness_criteria') or {}
    if (data.get('model') != model or data.get('decision') != 'admitted' or data.get('freeze_sha256') != digest(V3_FREEZE)
            or not criteria.get('child_shell_works') or not criteria.get('child_mutating_mcp_ok')):
        raise ValueError('v3 admission for %s is not an admitted decision bound to the current v3 freeze' % model)
    return {'path': str(entry), 'sha256': digest(entry), 'decided_utc': data.get('decided_utc')}


# ------------------------------------------------------------------------------------------------ protocol and schedule

def merged_design(old, p):
    return dict(old, components=dict(old['components'], **p['extension']['components']))


def protocol():
    p = read(PROTOCOL)
    old = read(REF / 'protocol.json')
    if (p['protocol_id'], p['repetitions'], p['workers']) != (PROTOCOL_ID, 4, 1):
        raise ValueError('unexpected protocol/repetitions/workers')
    check_model_choice(p)
    for key in ('tasks', 'components', 'guard_rule'):
        if p[key] != old[key]:
            raise ValueError('historical design changed: ' + key)
    if p['extension']['component_order'] != list(gab.COMPONENT_ORDER):
        raise ValueError('component order differs from the runner')
    by_id = {c['id']: c for c in p['conditions']}
    for oc in old['conditions']:
        strip = lambda c: {k: v for k, v in c.items() if k != 'tier'}
        if strip(by_id[oc['id']]) != strip(oc):
            raise ValueError('historical condition changed: ' + oc['id'])
    if [c['id'] for c in p['conditions']][len(old['conditions']):] != ['minus-V6', 'thin']:
        raise ValueError('unexpected extra conditions')
    for cid, oc in old['contrasts'].items():
        keep = ('name', 'reference', 'ablated', 'manipulation') + (() if 'moved_from_tier' in p['contrasts'][cid] else ('note',))
        if {k: p['contrasts'][cid].get(k) for k in keep} != {k: oc.get(k) for k in keep}:
            raise ValueError('historical contrast changed: ' + cid)
    for tier, spec in p['tiers'].items():
        if any(c not in by_id for c in spec['conditions']):
            raise ValueError('tier names an unknown condition')
    if (p['tiers']['1']['conditions'], p['tiers']['1']['schedule_seed']) != (old['tiers']['1']['conditions'], old['tiers']['1']['schedule_seed']):
        raise ValueError('tier 1 changed')
    if (p['tiers']['0']['conditions'], p['tiers']['0']['schedule_seed']) != (p['tiers']['0b']['conditions'], p['tiers']['0b']['schedule_seed']) \
            or p['tiers']['0']['repetitions'][1] + 1 != p['tiers']['0b']['repetitions'][0] or p['tiers']['0b']['repetitions'][1] != p['repetitions']:
        raise ValueError('tiers 0 and 0b must split one schedule')
    if p['reuse']['reference_files'] != file_hashes(REF):
        raise ValueError('historical reference bytes changed')
    if p['reuse']['arms_files'] != file_hashes(BENCH / 'arms') or p['reuse']['plans_files'] != file_hashes(BENCH / 'plans'):
        raise ValueError('historical overlays or plans changed')
    base = gab.base_files()
    if gab.tree_digest(base) != p['reuse']['base_tree_sha256']:
        raise ValueError('historical base tree changed')
    design = merged_design(old, p)
    for c in p['conditions']:
        if c['kind'] == 'skill-variant':
            if gab.tree_digest(gab.materialize(design, c['removes'], base)) != p['reuse']['arm_trees'][c['id']]:
                raise ValueError('variant tree differs: ' + c['id'])
    for c in old['conditions']:
        if orig.sha(gab.condition_prompt_line(old, c['id'], base)) != p['reuse']['condition_line_sha256'][c['id']]:
            raise ValueError('repaired historical prompt changed')
    thin = p['extension']['thin']
    thin_bytes = (BENCH / 'arms/thin/overlay/SKILL.md').read_bytes()
    if gab.tree_digest({'SKILL.md': thin_bytes}) != thin['tree_sha256'] or hashlib.sha256(thin_bytes).hexdigest() != thin['source_sha256_at_copy']:
        raise ValueError('thin rules copy differs from the recorded digest')
    return p


def schedule(tier, p=None):
    p = p or protocol()
    spec = p['tiers'][tier]
    lo, hi = spec['repetitions']
    base = {'tiers': {'x': {'conditions': spec['conditions'], 'schedule_seed': spec['schedule_seed']}},
            'tasks': p['tasks'], 'repetitions': p['repetitions']}
    return [dict(case=r['case'], arm=r['condition'], repetition=r['repetition'], ordinal=r['ordinal'], tier=tier)
            for r in gab.schedule(base, 'x') if lo <= r['repetition'] <= hi]


def view_schedule(view, p=None):
    p = p or protocol()
    return [row for tier in p['views'][view]['tiers'] for row in schedule(tier, p)]


# ------------------------------------------------------------------------------------------------------ prompts, staging

def condition_of(p, condition):
    return next(c for c in p['conditions'] if c['id'] == condition)


def prompt_line(condition, p=None):
    """Condition clause + scratch approval. The skill-specific scratch sentence is appended only where a skill tree is staged."""
    p = p or read(PROTOCOL)
    cond = condition_of(p, condition)
    lines = p['extension']['prompt_lines']
    if cond['kind'] == 'no-skill':
        return lines['scratch_without_skill_text']
    if cond['kind'] == 'thin-rules':
        return lines['thin_head'].format(thin='/work/skill/playwright-thin-rules/SKILL.md') + lines['scratch_without_skill_text']
    if condition == 'minus-V6':
        template = (gab.LINE_HEAD + gab.LINE_REPORT + gab.LINE_REFERENCES + lines['minus-V6_reviewer_clause'] + gab.LINE_APPROVALS)
    else:
        template = gab.condition_prompt_line(read(REF / 'protocol.json'), condition, gab.base_files())
    return template.format(gen='/work/skill/playwright-test-generator/SKILL.md',
                           rev='/work/skill/e2e-reviewer/SKILL.md') + rt.C_SCRATCH


def reviewer_staged(p, condition):
    cond = condition_of(p, condition)
    return cond['kind'] == 'skill-variant' and '/work/skill/e2e-reviewer/SKILL.md' in prompt_line(condition, p)


def stage_condition(work, condition):
    p = protocol()
    cond = condition_of(p, condition)
    if cond['kind'] == 'no-skill':
        return {'generator': None, 'reviewer': None}
    root = BENCH / 'arms' / condition
    if cond['kind'] == 'thin-rules':
        dest = Path(work) / 'skill/playwright-thin-rules'
        dest.mkdir(parents=True)
        shutil.copyfile(root / 'overlay/SKILL.md', dest / 'SKILL.md')
        if gab.tree_digest({'SKILL.md': (dest / 'SKILL.md').read_bytes()}) != p['reuse']['arm_trees'][condition]:
            raise ValueError('staged thin tree drift')
        return {'generator': dest, 'reviewer': None}
    dest = Path(work) / 'skill/playwright-test-generator'
    shutil.copytree(gab.BASE_DIR, dest)
    for name in (root / 'deleted-files.txt').read_text().split():
        (dest / name).unlink()
    for f in sorted((root / 'overlay').rglob('*')):
        if f.is_file():
            target = dest / f.relative_to(root / 'overlay')
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(f, target)
    if gab.tree_digest({k: (dest / k).read_bytes() for k in file_hashes(dest)}) != p['reuse']['arm_trees'][condition]:
        raise ValueError('staged tree drift')
    reviewer = None
    if reviewer_staged(p, condition):
        reviewer = Path(work) / 'skill/e2e-reviewer'
        shutil.copytree(REF / 'e2e-reviewer', reviewer)
    return {'generator': dest, 'reviewer': reviewer}


def expected_exposure(condition, p=None):
    """Which signals the condition keeps (expected present) and removes (expected absent); L and P absence is hard."""
    p = p or read(PROTOCOL)
    cond = condition_of(p, condition)
    removed = set(SIGNALS) if cond['kind'] == 'no-skill' else set()
    if cond['kind'] == 'thin-rules':
        removed = {'L', 'E', 'P', 'R', 'V6'}
    elif cond['kind'] == 'skill-variant':
        parts = set(cond['removes'])
        removed = {s for s in ('L', 'E', 'P', 'R') if s in parts}
        if 'V' in parts:
            removed |= {'V6', 'X'}
        if 'VR' in parts:
            removed.add('V6')
    present = [s for s in SIGNALS if s not in removed and s != 'V']
    return {'present': present, 'absent': sorted(removed), 'hard_absent': [s for s in ('L', 'P') if s in removed]}


def bindings():
    p = protocol()
    return {'protocol': digest(PROTOCOL), 'runner': digest(Path(__file__)), 'stats': digest(HELPERS), 'machine_lock': digest(Path(zep.__file__)),
            'readme': digest(README), 'reference': file_hashes(REF), 'arms': file_hashes(BENCH / 'arms'), 'plans': file_hashes(BENCH / 'plans'),
            'v4_bindings': rt.bindings(), 'engine_inputs': engine.input_digests(),
            'prompts': {c['id']: orig.sha(prompt_line(c['id'], p)) for c in p['conditions']},
            'model_choice': check_model_choice(p), 'revalidation': digest(REVALIDATION) if REVALIDATION.is_file() else None,
            'harness_line': orig.sha(HARNESS_LINE)}


def freeze_preconditions(p=None):
    p = p or protocol()
    problems = []
    rev = p['manipulation_checks']['revalidation']
    if rev['status'] != 'RECORDED' or not REVALIDATION.is_file():
        problems.append('manipulation revalidation is %s: record it first' % rev['status'])
    elif read(REVALIDATION).get('reviewed') is not True:
        problems.append('revalidation artifact is not marked reviewed by the owner')
    if digest(THIN_SOURCE) != p['extension']['thin']['source_sha256_at_copy']:
        problems.append('THIN-RULES.md changed since the copy; re-copy and re-review')
    if not rt.v1_unchanged():
        problems.append('a file bound by the v1 freeze differs from its recorded digest')
    return problems


def freeze_document():
    return {'protocol_id': PROTOCOL_ID, 'bindings': bindings(), 'schedules': {t: schedule(t) for t in TIERS}, 'frozen_utc': engine.utc_now()}


def frozen():
    if not LOCK.is_file():
        raise ValueError('not frozen: freeze.json missing')
    lock = read(LOCK)
    if lock.get('bindings') != bindings() or lock.get('schedules') != {t: schedule(t) for t in TIERS}:
        raise ValueError('freeze drift')
    return lock


def require_live(args, command, model_call=True):
    """Live gate: --allow-live, a matching freeze and, for commands that call the model, the v3 admission of the chosen model."""
    if not getattr(args, 'allow_live', False):
        raise ValueError(command + ' requires --allow-live')
    lock = frozen()
    if model_call:
        args.v3_admission = v3_admission(read(PROTOCOL)['model'], getattr(args, 'v3_dir', None))
    return lock


# ----------------------------------------------------------------------------------------------- locks and machinery

@contextlib.contextmanager
def campaign_guard(process_probe=None):
    """Machine-wide exclusivity: the shared campaign lock with its driver probe (sees v2, v3, v4, thin-eval, oss, loop and claude drivers
    by script name) plus the v4 multimodel lock, so drivers that only know that lock also refuse."""
    with zep.CampaignLock(zep.SHARED_LOCK, process_probe=process_probe, campaign_id=PROTOCOL_ID):
        handle = rt.campaign_lock()
        try:
            yield
        finally:
            handle.close()


@contextlib.contextmanager
def machinery(base):
    """Bind only our private v4 instance; the machine-wide lock is held by the caller before rebasing the output directory."""
    orig.output_guard(Path(base) / 'probe.json')
    saved = {k: getattr(rt, k) for k in ('BASE', 'LOCK', 'protocol', 'frozen')}
    saved_plans = orig.PLANS
    rt.BASE, rt.LOCK, rt.protocol, rt.frozen = Path(base), LOCK, protocol, frozen
    try:
        yield
    finally:
        orig.PLANS = saved_plans
        for k, value in saved.items():
            setattr(rt, k, value)


def configure(args):
    p = protocol()
    result = rt.configure(args, p, model_cfg(p))
    rt.compat.ARM_LINES.update({c['id']: prompt_line(c['id'], p) for c in p['conditions']})
    rt.compat.ARM_LINES[HARNESS_ARM] = HARNESS_LINE
    return result


def one_call(item, args, ports, artifacts):
    """v4 non-official one-call path with historical condition staging before the adapter call; generation-only server reuse,
    persisted rollouts and every attempt record. No official agent initializer is called."""
    p = protocol()
    real_call, saved_plans = engine.call_model, orig.PLANS
    orig.PLANS = getattr(args, 'staging_plans', BENCH / 'plans')
    def call(project, work, arm, task, model, timeout, budget):
        stage_condition(work, arm)
        return real_call(project, work, arm, task, model, timeout, budget)
    engine.call_model = call
    try:
        with rt.generation_staging() as staged:
            rec = rt._V1['one_call'](item, args, ports, artifacts, model_cfg(p), p)
        rec['generation_config'] = rt.generation_summary(staged)
        return rec
    finally:
        engine.call_model = real_call
        orig.PLANS = saved_plans


# ------------------------------------------------------------------------------------------------- rollout evidence

def strict_events(path):
    if not path or not Path(path).is_file():
        return None
    try:
        events = [json.loads(line) for line in Path(path).read_text().splitlines() if line.strip()]
        return events if events and all(isinstance(e, dict) for e in events) else None
    except (ValueError, OSError):
        return None


def exit_code(value):
    if isinstance(value, bool):
        return None
    if isinstance(value, int):
        return value
    return int(value) if isinstance(value, str) and re.fullmatch(r'-?\d+', value.strip()) else None


def normalize_rollout(events):
    """Convert persisted raw function calls/results to completed command events without truncation.

    Requests without outputs do not count. The exit code is kept (None when unobserved); the caller decides which codes count."""
    outputs = {e['payload'].get('call_id'): e['payload'].get('output') for e in events
               if e.get('type') == 'response_item' and e.get('payload', {}).get('type') == 'function_call_output'}
    out = [e for e in events if e.get('type') == 'item.completed']
    native = []
    for e in events:
        payload = e.get('payload') or {}
        item = payload.get('item') or {}
        if e.get('type') == 'event_msg' and payload.get('type') == 'item_completed':
            if item.get('type') in ('CommandExecution', 'command_execution'):
                cmd = item.get('command') or ''
                if isinstance(cmd, list):
                    shell_c = next((i for i, arg in enumerate(cmd) if arg in ('-c', '-lc', '-ic') and i + 1 < len(cmd)), None)
                    cmd = cmd[shell_c + 1] if shell_c is not None else shlex.join(cmd)
                native.append({'type': 'item.completed', 'item': dict(item, type='command_execution', command=cmd,
                                                                       exit_code=exit_code(item.get('exit_code')))})
            elif item.get('type') in ('AgentMessage', 'agent_message'):
                content = item.get('content') or item.get('text') or ''
                if isinstance(content, list):
                    content = '\n'.join(str(block.get('text') or '') for block in content if isinstance(block, dict))
                native.append({'type': 'item.completed', 'item': dict(item, type='agent_message', text=content)})
    if native:
        return native  # avoid counting event and function-call representations twice
    for e in events:
        p = e.get('payload') or {}
        if e.get('type') != 'response_item' or p.get('type') != 'function_call' or p.get('call_id') not in outputs:
            continue
        try:
            inp = json.loads(p.get('arguments') or '{}')
        except ValueError:
            continue
        name = p.get('name', '').split('.')[-1]
        result = outputs[p['call_id']]
        raw = result if isinstance(result, str) else json.dumps(result)
        if name in ('exec_command', 'shell_command', 'shell') and ('cmd' in inp or 'command' in inp):
            code = result.get('exit_code') if isinstance(result, dict) else None
            if code is None:
                match = re.search(r'(?:Process exited with code|exit_code["\s:]+)\s*(\d+)', raw)
                code = int(match.group(1)) if match else None
            out.append({'type': 'item.completed', 'item': {'type': 'command_execution',
                        'command': inp.get('cmd', inp.get('command', '')), 'aggregated_output': raw, 'exit_code': exit_code(code)}})
    return out


def signal_events(events, codes=(0,)):
    """Command executions that ran to completion with an accepted exit code, in the historical detector shape."""
    out = []
    for e in events:
        i = e.get('item') or {}
        if e.get('type') == 'item.completed' and i.get('type') == 'command_execution' and exit_code(i.get('exit_code')) in codes:
            out.append({'tool': 'Bash', 'input': {'command': i.get('command', '')}, 'out': i.get('aggregated_output', ''),
                        'ok': True, 'exit_code': exit_code(i.get('exit_code'))})
    return out


def executed_tests(command):
    commands, parsed = sig.simple_commands(command)
    if not parsed:
        return False
    for argv in commands:
        # The historical parser strips shell/env/timeout wrappers and rejects echo/heredoc data.
        if not argv:
            continue
        is_playwright, rest = sig._is_playwright(argv)
        if is_playwright and rest and rest[0] == 'test' and not any(flag in rest for flag in ('--list', '--help', '-h')):
            return True
    return False


def lineage_members(directory, root_thread_id):
    """Every persisted rollout of a cell with its role: root, child (descendant of the identified root) or unlinked."""
    members, seen = [], set()
    for path in sorted(Path(directory).rglob('rollout-*.jsonl')):
        if path.is_symlink() or not path.is_file():
            continue
        parsed = ev.parse_rollout(path)
        if parsed.get('thread_id') and parsed['thread_id'] in seen:
            continue  # duplicate thread: the summary already reports it as an observation gap
        seen.add(parsed.get('thread_id'))
        members.append({'path': path, 'parsed': parsed, 'raw': strict_events(path), 'role': 'unlinked'})
    linked = {root_thread_id} if root_thread_id else set()
    for m in members:
        if root_thread_id and m['parsed'].get('thread_id') == root_thread_id and not m['parsed'].get('parent_thread_id'):
            m['role'] = 'root'
    frontier = set(linked)
    while frontier:
        level = [m for m in members if m['role'] == 'unlinked' and m['parsed'].get('parent_thread_id') in frontier]
        for m in level:
            m['role'] = 'child'
        frontier = {m['parsed'].get('thread_id') for m in level if m['parsed'].get('thread_id')}
    return members


def observed(rec, tdir):
    """(parent events, rollout summary, gaps, sessions directory) or (None, ..., reason) when evidence cannot be taken as complete."""
    parent = strict_events(Path(tdir) / Path(rec.get('transcript_path') or '').name)
    if parent is None:
        return None, None, ['parent transcript missing or malformed'], None
    summary = rt.rollout_summary(rec, tdir, parent)
    gaps = rt.observation_gaps(rec, summary, ev.spawn_observation(parent).get('thread_ids'))
    directory = ev.sessions_dir_for(rec, tdir)
    if not directory or summary is None or not summary.get('root_found'):
        gaps = gaps + ['rollout observation incomplete']
    return parent, summary, gaps, directory


def child_returned_verdict(child_events):
    return any(VERDICT.search(str((e.get('item') or {}).get('text') or (e.get('item') or {}).get('content') or ''))
               for e in child_events if (e.get('item') or {}).get('type') == 'agent_message')


def parent_returned_verdict(parent):
    return any(VERDICT.search(str(state.get('message') or '')) for e in parent
               for state in ((e.get('item') or {}).get('agents_states') or {}).values() if isinstance(state, dict))


def manipulation(rec, tdir, p=None):
    p = p or read(PROTOCOL)
    parent, summary, gaps, directory = observed(rec, tdir)
    if parent is None:
        return {'signals': None, 'reason': gaps[0]}
    if gaps:
        return {'signals': None, 'reason': 'rollout observation incomplete', 'gaps': gaps}
    members = lineage_members(directory, summary['root_thread_id'])
    if any(m['raw'] is None for m in members):
        return {'signals': None, 'reason': 'rollout malformed'}
    if any(m['role'] == 'unlinked' for m in members):
        return {'signals': None, 'reason': 'rollout not linked to the identified root'}
    root_events = [e for m in members if m['role'] == 'root' for e in normalize_rollout(m['raw'])]
    child_events = [e for m in members if m['role'] == 'child' for e in normalize_rollout(m['raw'])]
    codes = p['manipulation_checks']['accepted_exit_codes']
    detectors = {k: p['manipulation_checks']['signals'][k] for k in HISTORICAL_DETECTORS}
    author = root_events or parent
    strict = (sig.detect(signal_events(author, tuple(codes['L'])), detectors), sig.detect(signal_events(child_events, tuple(codes['L'])), detectors))
    scanner = sig.detect(signal_events(author, tuple(codes['R'])), detectors)['R']
    hits = {k: strict[0][k] or strict[1][k] for k in ('L', 'E', 'P')}
    hits['R'] = scanner  # a scanner run by a V6 child is not the writer's Step 6 gate
    test_events = signal_events(author, tuple(codes['X'])) + signal_events(child_events, tuple(codes['X']))
    hits['X'] = any(executed_tests(e['input']['command']) for e in test_events)
    child_verdict, parent_verdict = child_returned_verdict(child_events), parent_returned_verdict(parent)
    hits['V6'] = child_verdict or parent_verdict
    hits['V'] = hits['V6'] and hits['X']  # execution plus an independent verdict; a verdict alone cannot prove execution verification
    return {'signals': hits, 'v6_source': {'child_rollout': child_verdict, 'parent_state': parent_verdict},
            'exit_codes': {'scanner': sorted({e['exit_code'] for e in signal_events(author, tuple(codes['R']))
                                              if sig.detect([e], {'R': detectors['R']})['R']}),
                           'tests': sorted({e['exit_code'] for e in test_events if executed_tests(e['input']['command'])})},
            'compliance_raw': ev.compliance_from_events(author), 'child_compliance_raw': ev.compliance_from_events(child_events),
            'rollouts': summary}


def usage_row(usage):
    cached = usage['cached_input_tokens']
    uncached = max(0, usage['input_tokens'] - cached)
    return {'uncached_input': uncached, 'cached_input': cached, 'output': usage['output_tokens'],
            'reasoning_output': usage['reasoning_output_tokens'], 'processed': uncached + usage['output_tokens'],
            'total': uncached + usage['output_tokens'] + cached}


def blank_roles():
    return {r: {k: 0 for k in stats.TOKEN_KEYS} for r in stats.ROLES}


def role_tokens_one(rec, tdir):
    """Tokens of one call split by rollout role: root, V6 reviewer child (a linked child that returned a literal verdict line) and other
    children. Incomplete (complete False) when evidence has a gap, a rollout is unlinked, or a usage record is missing."""
    out = {'complete': False, 'roles': blank_roles(), 'v6_children': 0, 'other_children': 0, 'unlinked': 0, 'reasons': []}
    parent, summary, gaps, directory = observed(rec, tdir)
    if parent is None or gaps:
        out['reasons'] = gaps
        return out
    members = lineage_members(directory, summary['root_thread_id'])
    if any(m['raw'] is None for m in members):
        out['reasons'].append('rollout malformed')
    for m in members:
        usage = m['parsed'].get('usage')
        if m['role'] == 'unlinked':
            out['unlinked'] += 1
            continue
        if usage is None:
            out['reasons'].append('missing usage in ' + m['parsed'].get('file', '?'))
            continue
        if m['role'] == 'root':
            role = 'root'
        else:
            verdict = m['raw'] is not None and child_returned_verdict(normalize_rollout(m['raw']))
            role = 'v6_reviewer' if verdict else 'other_children'
            out['v6_children' if verdict else 'other_children'] += 1
        for k, v in usage_row(usage).items():
            out['roles'][role][k] += v
    if out['unlinked']:
        out['reasons'].append('%d unlinked rollout(s)' % out['unlinked'])
    out['complete'] = not out['reasons'] and any(m['role'] == 'root' for m in members)
    return out


def cell_roles(rec, tdir):
    """Role tokens of the cell: every attempt contributes once, exactly as the cell's pipeline tokens do."""
    attempts = rec.get('attempts') or []
    parts = [role_tokens_one(a, tdir) for a in attempts] if len(attempts) > 1 or (rt.is_aborted(rec) and attempts) else [role_tokens_one(rec, tdir)]
    out = {'complete': all(x['complete'] for x in parts), 'roles': blank_roles(), 'attempts': len(parts),
           'v6_children': sum(x['v6_children'] for x in parts), 'other_children': sum(x['other_children'] for x in parts),
           'unlinked': sum(x['unlinked'] for x in parts), 'reasons': sorted({r for x in parts for r in x['reasons']})}
    for x in parts:
        for role, row in x['roles'].items():
            for k, v in row.items():
                out['roles'][role][k] += v
    return out


def reconciles(roles, tokens):
    """Role sums equal the cell's pipeline processed tokens (parent plus child), the additivity check of the cost accounting."""
    if not roles.get('complete') or not tokens.get('complete'):
        return False
    return sum(r['processed'] for r in roles['roles'].values()) == tokens['processed']


# ----------------------------------------------------------------------------------------------------------- analysis

exact_p = stats.exact_p


def task_conditional(rows, tasks):
    means = []
    for task in tasks:
        value = stats.task_value(rows, task, 'survival')
        if value is None:
            return None
        means.append(value)
    return float(sum(means) / len(means))


def cost_endpoint(rows):
    out = pooled.cost_endpoint(rows)
    known = sum((c.get('pipeline') or {}).get('elapsed_s') is not None for c in rows)
    out['cells_with_complete_time'] = known
    out['time_complete'] = known == len(rows)
    out['cells_incomplete_tokens'] = len(rows) - out['cells_with_complete_tokens']
    if not out['time_complete']:
        out['elapsed_s_per_survivor'] = None
    return out


def manipulation_status(contrast, ref_cells, abl_cells, scheduled_per_arm, validated, p):
    """Per-component exposure instead of one all-or-nothing flag. Statuses: EXERCISED, NOT_EXERCISED, NO_EVIDENCE, DETECTOR_FAILS_BOUNDS.
    exposure: complete (all exercised and kept components kept), partial, none. A component named in `kept` must remain in the ablated arm."""
    rule, bounds = p['manipulation_checks']['pass'], p['manipulation_checks']['validation_bounds']
    ref = [c['signals'] for c in ref_cells if c.get('signals') is not None]
    abl = [c['signals'] for c in abl_cells if c.get('signals') is not None]
    covered = min(len(ref), len(abl)) / scheduled_per_arm if scheduled_per_arm else 0.0
    share = lambda rows, comp: sum(bool(r.get(comp)) for r in rows) / len(rows) if rows else None
    detail, reasons = {}, []
    for comp in contrast['manipulation']:
        a, b = share(ref, comp), share(abl, comp)
        historical = comp in HISTORICAL_DETECTORS
        valid = gab.validation_passes(validated[comp], bounds) if historical else None
        if covered < rule['min_transcript_coverage']:
            status = 'NO_EVIDENCE'
        elif historical and not valid:
            status = 'DETECTOR_FAILS_BOUNDS'
        elif a is not None and b is not None and a >= rule['min_reference_share'] and b <= rule['max_ablated_share']:
            status = 'EXERCISED'
        else:
            status = 'NOT_EXERCISED'
        detail[comp] = {'reference_share': round(a, 4) if a is not None else None, 'ablated_share': round(b, 4) if b is not None else None,
                        'detector': 'historical' if historical else 'unvalidated', 'detector_validated': valid, 'status': status}
        if status != 'EXERCISED':
            reasons.append('%s: %s' % (comp, status))
    kept = {}
    for comp in contrast.get('kept', []):
        b = share(abl, comp)
        kept[comp] = {'ablated_share': round(b, 4) if b is not None else None,
                      'ok': b is not None and b >= rule['min_reference_share'] and covered >= rule['min_transcript_coverage']}
        if not kept[comp]['ok']:
            reasons.append('%s: not kept in the ablated arm' % comp)
    exercised = [c for c, d in detail.items() if d['status'] == 'EXERCISED']
    if covered < rule['min_transcript_coverage'] or not exercised:
        exposure = 'none'
    elif len(exercised) == len(detail) and all(k['ok'] for k in kept.values()):
        exposure = 'complete'
    else:
        exposure = 'partial'
    return {'ok': exposure == 'complete', 'exposure': exposure, 'components': detail, 'kept': kept, 'exercised': exercised,
            'not_exercised': [c for c in detail if c not in exercised],
            'unvalidated_detectors': [c for c, d in detail.items() if d['detector'] == 'unvalidated'],
            'reasons': reasons, 'transcript_coverage': round(covered, 4)}


def overall_label(endpoint_labels, guards):
    """Combine several endpoint labels of one contrast (decision_rule.overall_label)."""
    values = list(endpoint_labels.values())
    if 'CARRIES' in values:
        return 'CARRIES'
    if 'ABLATION_BETTER' in values:
        return 'ABLATION_BETTER'
    if values and all(v == 'NO_LARGE_EFFECT' for v in values):
        return 'NO_LARGE_EFFECT' if guards else 'GUARD_WORSE'
    return 'INCONCLUSIVE'


def apply_exposure(label, manip):
    """Partial exposure keeps an observed effect but cannot support a null; no exposure is NOT_EXERCISED."""
    if manip['exposure'] == 'none':
        return 'NOT_EXERCISED', 'no named component exercised or transcript coverage below the bound'
    if manip['exposure'] == 'partial' and label in ('NO_LARGE_EFFECT', 'GUARD_WORSE'):
        return 'INCONCLUSIVE', 'partial exposure: a null cannot be attributed (not exercised: %s)' % ', '.join(manip['not_exercised'] + [
            k for k, v in manip['kept'].items() if not v['ok']])
    return label, None


def analyze_contrast(cid, spec, by, p, complete, validation, scheduled_per_arm):
    dr = p['decision_rule']
    ref, abl = by[spec['reference']], by[spec['ablated']]
    manip = manipulation_status(spec, ref, abl, scheduled_per_arm, validation, p)
    co = cid in dr['co_primary_endpoint_contrasts']
    results = {}
    for endpoint in spec['endpoints']:
        alpha = dr['primary_alpha_two_sided'] if co or (endpoint == 'survival' and cid in dr['primary_contrasts']) else dr['other_alpha_two_sided']
        results[endpoint] = stats.paired_endpoint(ref, abl, p['tasks'], endpoint, alpha, dr['minimum_effect'], dr['min_tasks'])
    guards = gab.guards_hold(gab.condition_aggregates(ref), gab.condition_aggregates(abl), p['guard_rule']) if ref and abl else False
    labels = {k: v['label'] for k, v in results.items()}
    label = overall_label(labels, guards)
    reason = None
    if not complete:
        label, reason = 'INCONCLUSIVE', 'schedule incomplete or aborted cells'
    else:
        label, reason = apply_exposure(label, manip)
    itt_alpha = dr['other_alpha_two_sided']
    out = {'label': label, 'label_note': reason, 'role': spec['role'], 'name': spec['name'], 'endpoints': results, 'endpoint_labels': labels,
           'guards_hold': guards, 'manipulation': manip, 'itt_survival': stats.paired_endpoint(ref, abl, p['tasks'], 'itt_survival', itt_alpha, dr['minimum_effect'], dr['min_tasks'])}
    if manip['exposure'] == 'partial' and label in ('CARRIES', 'ABLATION_BETTER'):
        out['attributed_to'] = manip['exercised']
    surv = results.get('survival', {})
    out['mean_diff'] = surv.get('mean_diff')
    out['p_two_sided'] = surv.get('p_two_sided')
    rule = p['cost_deliverable']['rule']
    out['cost'] = {m: stats.cost_contrast(ref, abl, p['tasks'], m, rule['alpha'], rule['min_ratio'], dr['min_tasks']) for m in stats.COST_METRICS}
    return out


def tier2_gate_status(contrasts, complete):
    """Reported, never silent. OPEN when tier 1 is complete and C1, C2 or C4 CARRIES with at least one exercised component."""
    watched = ('C1', 'C2', 'C4')
    carriers = [c for c in watched if c in contrasts and contrasts[c]['label'] == 'CARRIES' and contrasts[c]['manipulation']['exposure'] != 'none']
    exposure = {c: {k: v['status'] for k, v in contrasts[c]['manipulation']['components'].items()} for c in watched if c in contrasts}
    if not complete:
        status, reasons = 'CLOSED_INCOMPLETE', ['tier 1 is not a complete scheduled matrix']
    elif carriers:
        status, reasons = 'OPEN', ['%s labeled CARRIES' % ', '.join(carriers)]
    elif any(contrasts[c]['label'] == 'NOT_EXERCISED' for c in exposure):
        status, reasons = 'CLOSED_NOT_EXERCISED', ['%s: %s' % (c, contrasts[c]['manipulation']['reasons']) for c in exposure
                                                   if contrasts[c]['label'] == 'NOT_EXERCISED']
    else:
        status, reasons = 'CLOSED_NO_CARRIES', ['labels: ' + ', '.join('%s=%s' % (c, contrasts[c]['label']) for c in exposure)]
    return {'status': status, 'tier2_open': status == 'OPEN', 'reasons': reasons, 'carriers': carriers, 'component_exposure': exposure,
            'override': 'drive --tier 2 --owner-ungated "<reason>" runs tier 2 anyway and records the reason'}


def analyze_cells(cells, view, p=None):
    p = p or protocol()
    vspec = p['views'][view]
    expected = {(r['case'], r['arm'], r['repetition']) for r in view_schedule(view, p)}
    got = [(c['case'], c['arm'], c['repetition']) for c in cells]
    complete = set(got) == expected and len(got) == len(expected) and not any(c.get('aborted') for c in cells)
    conditions = []
    for tier in vspec['tiers']:
        conditions += [c for c in p['tiers'][tier]['conditions'] if c not in conditions]
    by = {arm: [c for c in cells if c['arm'] == arm] for arm in conditions}
    validation = read(REF / 'manipulation-validation.json')['per_component']['codex_only']
    scheduled_per_arm = len(p['tasks']) * vspec['repetitions_per_cell']
    out = {}
    for cid, spec in p['contrasts'].items():
        if spec['tier'] == vspec['contrasts_of'] and spec['reference'] in by and spec['ablated'] in by:
            out[cid] = analyze_contrast(cid, spec, by, p, complete, validation, scheduled_per_arm)
    if 'C2' in out and 'C3' in out and all(out[c].get('mean_diff') is not None for c in ('C2', 'C3')):
        out['interaction_C2_minus_C3'] = out['C2']['mean_diff'] - out['C3']['mean_diff']
    rates = p['cost_deliverable']['dollars']['rates_per_million_tokens']
    roles = {a: stats.role_table(rows) for a, rows in by.items()}
    return {'protocol_id': p['protocol_id'], 'model': p['model'], 'view': view, 'grade': vspec['grade'], 'complete': complete,
            'status': 'DEVELOPMENT_EVIDENCE', 'contrasts': out,
            'gate': tier2_gate_status(out, complete) if view == '1' and {'C1', 'C2', 'C4'} <= set(out) else None,
            'selector_hygiene': {a: pooled.selector_table(rows) for a, rows in by.items()},
            'task_weighted_clean_conditional_survival': {a: task_conditional(rows, p['tasks']) for a, rows in by.items()},
            'secondary': {a: gab.condition_aggregates(rows) for a, rows in by.items()},
            'cost_endpoints': {a: cost_endpoint(rows) for a, rows in by.items()},
            'tokens_by_role': roles,
            'role_reconciliation': {a: {'cells_reconciling': sum(bool(c.get('roles_reconcile')) for c in rows), 'cells': len(rows)} for a, rows in by.items()},
            'dollar_estimate': {a: stats.dollar_estimate({r: t for r, t in tab['roles'].items()}, rates) for a, tab in roles.items()},
            'fidelity': {a: {'cells': len(rows), 'evidence_complete': sum(c.get('signals') is not None for c in rows),
                             'signals': {s: sum(bool((c.get('signals') or {}).get(s)) for c in rows) for s in SIGNALS}}
                         for a, rows in by.items()}, 'cells': cells}


def check_report(report, tier, complete=True):
    lock = frozen()
    p = protocol()
    if (report.get('protocol_id'), report.get('model'), report.get('tier'), report.get('freeze_sha256'), report.get('workers')) != (
            PROTOCOL_ID, p['model'], tier, digest(LOCK), 1):
        raise ValueError('report identity/freeze mismatch')
    if report.get('arms') != p['tiers'][tier]['conditions'] or report.get('input_drift') or report.get('completed_calls') != len(report['runs']):
        raise ValueError('report arms/count/drift mismatch')
    orig.check_rows(report['runs'], lock['schedules'][tier], complete)


def paths(base, tier):
    return Path(base) / ('tier' + tier) / 'final.json'


def tier_cells(base, tier, p):
    report_path = paths(base, tier)
    report, scores = read(report_path), read(report_path.parent / 'scores.json')
    state = read(report_path.parent / 'scoring-state.json')
    if state != {'status': 'complete', 'report_sha256': digest(report_path), 'freeze_sha256': digest(LOCK),
                 'scores_sha256': digest(report_path.parent / 'scores.json')}:
        raise ValueError('latest scoring attempt incomplete, failed or stale (tier %s)' % tier)
    check_report(report, tier)
    if scores.get('report_sha256') != digest(report_path) or scores.get('freeze_sha256') != digest(LOCK):
        raise ValueError('scores/report/freeze mismatch')
    orig.check_rows(scores['scores'], schedule(tier, p))
    records = {orig.identity(r): r for r in report['runs']}
    cells, cache = [], {}
    tdir = report_path.parent / 'final-transcripts'
    for row in scores['scores']:
        rec = records[orig.identity(row)]
        cell = rt.v1.make_cell(p['model'], row, rec, report_path)
        cell.update(rt.cell_extras(rec, tdir, report_path.parent))
        attempts = rec.get('attempts') or []
        if attempts:
            cell['elapsed_s'] = (sum(a['elapsed_ms'] for a in attempts) / 1000
                                 if all(a.get('elapsed_ms') is not None for a in attempts) else None)
        detail = manipulation(rec, tdir, p)
        roles = cell_roles(rec, tdir)
        cell.update(condition=cell['arm'], signals=detail['signals'], manipulation_evidence=detail, tokens_by_role=roles,
                    roles_reconcile=reconciles(roles, cell['tokens']))
        cell['pipeline'] = {'tokens': cell['tokens'], 'elapsed_s': cell['elapsed_s']}
        cell['references_renamed_selector'] = rt.selector_status(cell, report_path.parent, cache)
        cell['dynamic_selector_hint'] = rt.dynamic_selector_status(cell, report_path.parent)
        cells.append(cell)
    rt.generation_uniformity(cells)
    return cells, report_path, report


def analysis_path(base, view):
    return Path(base) / ('analysis-' + view.replace('+', '_')) / 'results.json'


def analyze_file(base, view, write=True):
    frozen()
    p = protocol()
    cells, digests = [], {}
    for tier in p['views'][view]['tiers']:
        tc, report_path, report = tier_cells(base, tier, p)
        cells += tc
        digests[tier] = {'report_sha256': digest(report_path), 'scores_sha256': digest(report_path.parent / 'scores.json')}
        if report.get('gate_override'):
            digests[tier]['gate_override'] = report['gate_override']
    result = analyze_cells(cells, view, p)
    result.update(tiers=digests, freeze_sha256=digest(LOCK))
    if write:
        analysis_path(base, view).parent.mkdir(parents=True, exist_ok=True)
        engine.write_json(analysis_path(base, view), result)
    return result


def tier2_gate(base, override=None):
    """Recompute the tier-1 gate from digest-bound reports; a closed gate stops tier 2 unless the owner records an explicit reason."""
    stored = read(analysis_path(base, '1'))
    fresh = analyze_file(base, '1', write=False)
    if stored != fresh:
        raise ValueError('tier 1 analysis is stale or edited; recompute it with `analyze --view 1`')
    gate = fresh['gate']
    if gate['tier2_open']:
        return {'status': 'OPEN'}
    if override and str(override).strip():
        return {'status': gate['status'], 'override': str(override).strip()}
    raise ValueError('tier 2 gate %s: %s. Run with --owner-ungated "<reason>" to override on the record.' % (gate['status'], '; '.join(gate['reasons'])))


# ------------------------------------------------------------------------------------------------- harness and preflight

def evaluate_ablation_harness(rec, tdir):
    """Criteria of the ablation-specific harness check. The parent spawns one child that runs a shell command and returns a literal
    V6 verdict line; the verdict, shell output and usage must be persisted and the child usage additive to the root rollout."""
    parent, summary, gaps, directory = observed(rec, tdir)
    infra = bool(rec.get('infrastructure_error'))
    members = lineage_members(directory, summary['root_thread_id']) if parent is not None and summary and summary.get('root_found') and directory else []
    children = [m for m in members if m['role'] == 'child' and m['raw'] is not None]
    child_events = [e for m in children for e in normalize_rollout(m['raw'])]
    spawns = ev.compliance_from_events(parent)['agent_spawns_in_stream'] if parent else 0
    shell = any(HARNESS_MARKER in str(e['input']['command']) and HARNESS_MARKER in str(e['out']) for e in signal_events(child_events))
    child_total = ((summary or {}).get('child_usage') or {}).get('total_tokens', 0)
    root_usage = (summary or {}).get('root_rollout_usage')
    turns = [u for u in (rec.get('usage_all_turns') or []) if u] or ([rec['usage']] if rec.get('usage') else [])
    stream_total = ev.usage_dict({k: sum(int(u.get(k) or 0) for u in turns) for k in ev.USAGE_KEYS})['total_tokens'] if turns else None
    additive, mode = False, 'unavailable'
    if stream_total and root_usage and child_total:
        near = lambda a, b: abs(a - b) <= 0.02 * max(a, 1)
        if near(stream_total, root_usage['total_tokens']):
            additive, mode = True, 'stream_excludes_children'
        elif near(stream_total, root_usage['total_tokens'] + child_total):
            additive, mode = True, 'stream_includes_children'
        else:
            mode = 'unexplained'
    criteria = {
        'call_ok': parent is not None and not infra and not rec.get('timeout'),
        'sessions_persisted': bool(summary), 'root_rollout_identified': bool(summary and summary.get('root_found')),
        'persistence_census_clean': not rt.census_problem(rec) and not bool(summary and (
            summary.get('malformed_lines') or summary.get('children_unlinked') or summary.get('extra_root_rollouts'))),
        'child_rollout_found': bool(summary and summary.get('children_total')),
        'spawns_have_rollouts': bool(summary and not summary.get('spawn_observation_gaps') and (not spawns or 'parent_stream_spawns' in summary)),
        'child_shell_works': shell, 'child_verdict_persisted': child_returned_verdict(child_events),
        'child_token_usage_present': bool(summary and summary.get('children_total') and child_total > 0 and not summary.get('children_without_usage')),
        'child_usage_additive': additive}
    info = {'spawns_in_parent_stream': spawns, 'parent_stream_total_tokens': stream_total,
            'root_rollout_total_tokens': root_usage['total_tokens'] if root_usage else None, 'child_total_tokens': child_total,
            'additivity_mode': mode, 'parent_stream_carries_verdict': parent_returned_verdict(parent or []),
            'child_rollouts': (summary or {}).get('children_total', 0)}
    required = read(PROTOCOL)['harness']['criteria']
    if infra:
        status = 'aborted'
    elif all(criteria[k] for k in required):
        status = 'pass'
    elif criteria['call_ok'] and criteria['root_rollout_identified'] and not criteria['child_rollout_found']:
        status = 'inconclusive'
    else:
        status = 'fail'
    return {'status': status, 'criteria': criteria, 'info': info}


def harness_path(base):
    return Path(base) / '_entry' / 'ablation-harness-check.json'


def load_harness_check(base):
    f = harness_path(base)
    if not f.is_file():
        raise ValueError('no ablation harness check recorded; run `harness-check --allow-live`')
    data = read(f)
    if data.get('freeze_sha256') != digest(LOCK) or data.get('status') != 'pass':
        raise ValueError('the ablation harness check is not a pass bound to this freeze (status %s)' % data.get('status'))
    return data


def ensure_harness_check(args):
    f = harness_path(args.output)
    if f.is_file():
        data = read(f)
        if data.get('freeze_sha256') == digest(LOCK) and data.get('status') == 'pass':
            return data
    p = protocol()
    root = Path(args.output) / '_entry' / 'ablation-harness'
    root.mkdir(parents=True, exist_ok=True)
    tdir = root / 'transcripts'
    engine.CODEX_TRANSCRIPTS = tdir
    work = Path(tempfile.mkdtemp(prefix='ablation-harness-')).resolve()
    try:
        project = engine.stage(engine.CASES / p['entry_rule']['task'], engine.Ports(6700).take(), work, git=True)
        rec = dict(engine.call_model(project, work, HARNESS_ARM, 'Run the harness check described below; there is nothing to implement.',
                                     p['model'], 420, None), arm=HARNESS_ARM, spec_files=[])
    finally:
        shutil.rmtree(work, ignore_errors=True)
    engine.write_json(root / 'call.json', {k: v for k, v in rec.items() if k != 'stderr'})
    result = evaluate_ablation_harness(rec, tdir)
    previous = read(f).get('attempts', 0) if f.is_file() else 0
    data = dict(result, model=p['model'], freeze_sha256=digest(LOCK), decided_utc=engine.utc_now(), attempts=previous + 1,
                elapsed_s=round((rec.get('elapsed_ms') or 0) / 1000, 1), v3_admission_sha256=args.v3_admission['sha256'])
    engine.write_json(f, data)
    return data


def harness(args):
    require_live(args, args.command)
    with campaign_guard():
        with machinery(args.output):
            configure(args)
            result = ensure_harness_check(args)
    print(json.dumps({k: result[k] for k in ('status', 'criteria', 'info', 'model', 'attempts')}, indent=1))
    return 0 if result['status'] == 'pass' else 5


def preflight_cells(p):
    """Non-data preflight matrix on the unscheduled entry task: the full condition six times, every other condition once."""
    cells = [('full', k) for k in range(p['manipulation_checks']['preflight_exposure']['full_cells'])]
    cells += [(c['id'], 0) for c in p['conditions'] if c['id'] != 'full']
    return cells


def preflight_assertions(rows, p):
    """Pure check of a preflight matrix: presence in the full cells, hard absence of L and P where the text is gone, evidence and token
    integrity; soft expected-exposure table for everything else."""
    spec = p['manipulation_checks']['preflight_exposure']
    hard = {}
    wanted = count_pairs(preflight_cells(p))
    seen = count_pairs([(r['arm'], r['repetition']) for r in rows])
    hard['matrix_complete'] = wanted == seen
    hard['all_cells_deliverable'] = bool(rows) and all(r.get('deliverable') and not r.get('infrastructure_error') for r in rows)
    hard['all_evidence_complete'] = bool(rows) and all((r.get('manipulation_evidence') or {}).get('signals') is not None for r in rows)
    hard['role_tokens_reconcile'] = bool(rows) and all(r.get('roles_reconcile') for r in rows)
    full = [r for r in rows if r['arm'] == 'full' and (r.get('manipulation_evidence') or {}).get('signals') is not None]
    presence = {s: sum(bool(r['manipulation_evidence']['signals'].get(s)) for r in full) for s in spec['hard']['full_presence_min_cells_of_6']}
    hard['full_presence'] = {s: {'cells': presence[s], 'min': need, 'ok': presence[s] >= need}
                             for s, need in spec['hard']['full_presence_min_cells_of_6'].items()}
    leaks = []
    for r in rows:
        signals = (r.get('manipulation_evidence') or {}).get('signals') or {}
        for s in expected_exposure(r['arm'], p)['hard_absent']:
            if signals.get(s):
                leaks.append('%s repetition %s shows %s although its text is removed' % (r['arm'], r['repetition'], s))
    hard['removed_text_absent'] = {'leaks': leaks, 'ok': not leaks}
    soft = {}
    for r in rows:
        if r['arm'] == 'full':
            continue
        signals = (r.get('manipulation_evidence') or {}).get('signals') or {}
        exp = expected_exposure(r['arm'], p)
        soft[r['arm']] = {'unexpected_present': [s for s in exp['absent'] if signals.get(s)],
                          'expected_present_missing': [s for s in exp['present'] if not signals.get(s)]}
    ok = (hard['matrix_complete'] and hard['all_cells_deliverable'] and hard['all_evidence_complete'] and hard['role_tokens_reconcile']
          and all(v['ok'] for v in hard['full_presence'].values()) and hard['removed_text_absent']['ok'])
    return {'pass': ok, 'hard': hard, 'soft': soft}


def count_pairs(pairs):
    out = {}
    for pair in pairs:
        out[pair] = out.get(pair, 0) + 1
    return out


def preflight(args):
    require_live(args, 'preflight')
    with campaign_guard():
        with machinery(args.output):
            configure(args)
            if ensure_harness_check(args)['status'] != 'pass':
                return 5
            p = protocol()
            base = Path(args.output) / '_entry/preflight'
            base.mkdir(parents=True, exist_ok=True)
            if (base / 'decision.json').exists():
                raise ValueError('preflight already recorded for this campaign root')
            with tempfile.TemporaryDirectory(prefix='ablation-v2-plans-') as tmp:
                planroot = Path(tmp)
                shutil.copytree(BENCH / 'plans', planroot, dirs_exist_ok=True)
                (planroot / 'v2-01').mkdir()
                (planroot / 'v2-01/plan.md').write_text(orig.plan_text('v2-01'))
                args.staging_plans = planroot
                rows = []
                for condition, k in preflight_cells(p):
                    tdir = base / ('%s-%d' % (condition, k)) / 'final-transcripts'
                    engine.CODEX_TRANSCRIPTS = tdir
                    rec = one_call({'case': 'v2-01', 'arm': condition, 'repetition': k, 'ordinal': 0}, args, engine.Ports(6700), tdir.parent / 'final-artifacts')
                    rec['manipulation_evidence'] = manipulation(rec, tdir, p)
                    rec['tokens_by_role'] = cell_roles(rec, tdir)
                    tokens = rt.tokens_for_record(rec, tdir)
                    rec['roles_reconcile'] = reconciles(rec['tokens_by_role'], tokens)
                    engine.write_json(tdir.parent / 'call.json', rec)
                    rows.append(rec)
                    if rec['infrastructure_error']:
                        break
            del args.staging_plans
            verdict = preflight_assertions(rows, p)
            engine.write_json(base / 'decision.json', {
                'freeze_sha256': digest(LOCK), 'pass': verdict['pass'], 'assertions': verdict, 'non_data': True,
                'v3_admission_sha256': args.v3_admission['sha256'], 'harness_check_sha256': digest(harness_path(args.output)),
                'call_hashes': {'%s-%d' % (c, k): digest(base / ('%s-%d' % (c, k)) / 'call.json') for c, k in preflight_cells(p)
                                if (base / ('%s-%d' % (c, k)) / 'call.json').exists()}})
            print(json.dumps(verdict, indent=1))
            return 0 if verdict['pass'] else 5


def preflight_gate(base, p=None):
    p = p or protocol()
    root = Path(base) / '_entry/preflight'
    decision = read(root / 'decision.json')
    actual = {'%s-%d' % (c, k): digest(root / ('%s-%d' % (c, k)) / 'call.json') for c, k in preflight_cells(p)}
    if decision.get('freeze_sha256') != digest(LOCK) or not decision.get('pass') or actual != decision.get('call_hashes'):
        raise ValueError('preflight is missing, failed, stale or edited')
    if decision.get('harness_check_sha256') != digest(harness_path(base)):
        raise ValueError('preflight is not bound to the current harness check')
    return decision


# ------------------------------------------------------------------------------------------------------ drive and score

def drive(args):
    require_live(args, 'drive')
    p = protocol()
    with campaign_guard():
        with machinery(args.output):
            load_harness_check(args.output)
            decision = preflight_gate(args.output, p)
            if decision.get('v3_admission_sha256') != args.v3_admission['sha256']:
                raise ValueError('v3 admission changed since preflight')
            override = None
            if args.tier == '2':
                override = tier2_gate(args.output, getattr(args, 'owner_ungated', None)).get('override')
            elif getattr(args, 'owner_ungated', None):
                raise ValueError('--owner-ungated applies only to tier 2')
            work, image, cli = configure(args)
            out = paths(args.output, args.tier)
            if out.exists() and not args.resume:
                raise ValueError('output exists; use --resume')
            rows = read(out)['runs'] if out.exists() else []
            if out.exists():
                prior = read(out)
                check_report(prior, args.tier, complete=False)
                if prior['cli'] != cli or prior['container_image'] != image:
                    raise ValueError('CLI/container changed on resume')
                if any(r['infrastructure_error'] for r in rows):
                    raise ValueError('recorded infrastructure failure needs a new reviewed campaign; no silent replacement')
            done = {orig.identity(r) for r in rows}
            engine.CODEX_TRANSCRIPTS = out.parent / 'final-transcripts'
            def flush():
                data = {'protocol_id': PROTOCOL_ID, 'model': p['model'], 'tier': args.tier, 'arms': p['tiers'][args.tier]['conditions'],
                        'freeze_sha256': digest(LOCK), 'workers': 1, 'stage': 'final', 'completed_calls': len(rows),
                        'scheduled_calls': len(schedule(args.tier)), 'input_drift': False, 'cli': cli, 'container_image': image,
                        'v3_admission_sha256': args.v3_admission['sha256'], 'runs': rows}
                if override:
                    data['gate_override'] = override
                engine.write_json(out, data)
            flush()
            ports = engine.Ports(6300)
            for item in schedule(args.tier):
                if orig.identity(item) in done:
                    continue
                frozen()
                if shutil.disk_usage(work).free < p['minimum_free_disk_bytes']:
                    raise ValueError('disk safety floor reached')
                rows.append(one_call(item, args, ports, out.parent / 'final-artifacts'))
                flush()
                if rows[-1]['infrastructure_error']:
                    raise ValueError('infrastructure failure; partial report preserved')
            return 0


def score(args):
    require_live(args, 'score', model_call=False)
    p = protocol()
    with campaign_guard():
        rt.scoring_guard(p['tasks'])
        engine.LOAD_PAUSE_THRESHOLD = p['load']['pause_threshold']
        report_path = paths(args.output, args.tier)
        check_report(read(report_path), args.tier)
        target = report_path.parent / 'scores.json'
        if target.exists() and (not args.resume or read(target).get('report_sha256') != digest(report_path)):
            raise ValueError('score output exists or resume binding changed')
        before = digest(report_path)
        real_write = engine.write_json
        state_path = report_path.parent / 'scoring-state.json'
        state_base = {'report_sha256': before, 'freeze_sha256': digest(LOCK)}
        real_write(state_path, dict(state_base, status='started'))
        def write(path, data):
            data.update(report_sha256=before, freeze_sha256=digest(LOCK), tier=args.tier)
            real_write(path, data)
        engine.write_json = write
        try:
            engine.cmd_score(argparse.Namespace(report=report_path, output=target, resume=args.resume))
            if digest(report_path) != before:
                raise ValueError('report changed during scoring')
            orig.check_rows(read(target)['scores'], schedule(args.tier))
            real_write(state_path, dict(state_base, status='complete', scores_sha256=digest(target)))
        except BaseException:
            real_write(state_path, dict(state_base, status='failed'))
            raise
        finally:
            engine.write_json = real_write
        return 0


# ---------------------------------------------------------------------------------------------- offline inspection tools

def revalidate(cells_dir, out_path, p=None):
    """Offline, read-only replay of the ablation detectors over a directory of FINISHED cells (final.json, final-transcripts,
    codex-sessions). It writes per-cell signals, role-token reconciliation and unlinked-rollout counts for human review; it records
    no acceptance. The owner sets manipulation_checks.revalidation.status to RECORDED after review."""
    p = p or protocol()
    cells_dir, out_path = Path(cells_dir), Path(out_path)
    orig.output_guard(out_path)
    report = read(cells_dir / 'final.json')
    tdir = cells_dir / 'final-transcripts'
    rows = []
    for rec in report['runs']:
        if rec.get('infrastructure_error') or not rec.get('transcript_path'):
            rows.append({'call_id': rec.get('call_id'), 'arm': rec.get('arm'), 'skipped': 'infrastructure error or no transcript'})
            continue
        detail = manipulation(rec, tdir, p)
        roles = cell_roles(rec, tdir)
        tokens = rt.tokens_for_record(rec, tdir)
        rows.append({'call_id': rec.get('call_id'), 'arm': rec.get('arm'), 'signals': detail['signals'], 'reason': detail.get('reason'),
                     'v6_source': detail.get('v6_source'), 'exit_codes': detail.get('exit_codes'),
                     'roles_complete': roles['complete'], 'roles_reconcile': reconciles(roles, tokens), 'v6_children': roles['v6_children'],
                     'other_children': roles['other_children'], 'unlinked': roles['unlinked'],
                     'processed_by_role': {r: roles['roles'][r]['processed'] for r in stats.ROLES}})
    scored = [r for r in rows if 'signals' in r]
    summary = {'cells': len(rows), 'evidence_complete': sum(r['signals'] is not None for r in scored),
               'signals': {s: sum(bool((r['signals'] or {}).get(s)) for r in scored) for s in SIGNALS},
               'roles_reconcile': sum(bool(r['roles_reconcile']) for r in scored), 'cells_with_v6_child': sum(r['v6_children'] > 0 for r in scored)}
    engine.write_json(out_path, {'reviewed': False, 'source_cells': str(cells_dir.name), 'summary': summary, 'rows': rows})
    return summary


def power(replicates=None):
    p = read(PROTOCOL)['power']
    n = replicates or p['replicates']
    results = {}
    # Simulation uses all-clean quarter-step differences; gab's integer DP is exact here.
    for hetero in (False, True):
        rates = {}
        for delta in p['grid']:
            rng = random.Random(f"{p['seed']}:{hetero}:{delta}")
            passed = 0
            for _ in range(n):
                probs = [rng.uniform(.75, .95) if hetero else p['baseline'] for _ in range(12)]
                diffs = [(sum(rng.random() < a for _ in range(4)) - sum(rng.random() < a - delta for _ in range(4))) / 4 for a in probs]
                mean = sum(diffs) / 12
                if mean >= .25 and min(1, 2 * gab.signflip_p_upper(diffs, 4)) <= protocol_alpha():
                    passed += 1
            rates[str(delta)] = passed / n
        results['heterogeneous' if hetero else 'homogeneous'] = {'power': rates,
            'grid_mde_80': next((d for d in p['grid'] if rates[str(d)] >= .8), None)}
    return {'seed': p['seed'], 'replicates': n, 'assumptions': p['assumptions'], 'scenarios': results}


def protocol_alpha():
    return read(PROTOCOL)['decision_rule']['primary_alpha_two_sided']


def budget(p=None):
    p = p or protocol()
    return {'points_per_cell': p['budget']['points_per_cell'], 'unit': p['budget']['unit'], 'window': p['budget']['window'],
            'rows': stats.budget_rows(p), 'recommended_first_stage': p['budget']['recommended_first_stage'], 'caveat': p['budget']['caveat']}


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest='command', required=True)
    for name in ('plan', 'check', 'freeze', 'power', 'budget'):
        sub.add_parser(name)
    reval = sub.add_parser('revalidate')
    reval.add_argument('--cells-dir', type=Path, required=True)
    reval.add_argument('--out', type=Path, required=True)
    for name in ('harness-check', 'preflight', 'drive', 'score', 'analyze', 'summary'):
        cmd = sub.add_parser(name)
        cmd.add_argument('--output', type=Path, default=BASE_DEFAULT, help='external campaign directory (never an existing benchmark cache)')
        if name in ('drive', 'score'):
            cmd.add_argument('--tier', choices=TIERS, required=True)
        if name == 'drive':
            cmd.add_argument('--owner-ungated', default=None, help='run tier 2 although its gate is closed; the reason is recorded')
        if name == 'analyze':
            cmd.add_argument('--view', choices=('0', '0+0b', '1', '2'), required=True)
        if name in ('harness-check', 'preflight', 'drive', 'score'):
            cmd.add_argument('--allow-live', action='store_true')
            cmd.add_argument('--resume', action='store_true')
            cmd.add_argument('--v3-dir', type=Path, default=None, help='Codex v3 campaign directory holding _entry/<model>.json')
    args = parser.parse_args(argv)
    if args.command in ('plan', 'check'):
        p = protocol()
        extra = {}
        if args.command == 'check':
            with tempfile.TemporaryDirectory(prefix='ablation-v2-check-') as tmp:
                for c in p['conditions']:
                    stage_condition(Path(tmp) / c['id'], c['id'])
            extra = {'staged_conditions': len(p['conditions']), 'model_choice': check_model_choice(p),
                     'freeze_preconditions_open': freeze_preconditions(p),
                     'thin_rules_source_matches_copy': digest(THIN_SOURCE) == p['extension']['thin']['source_sha256_at_copy']}
        print(json.dumps(dict({'protocol': p['protocol_id'], 'model': p['model'], 'calls': {t: len(schedule(t, p)) for t in TIERS},
                               'paid_calls_started': 0, 'frozen': LOCK.exists()}, **extra), indent=2))
        return 0
    if args.command == 'freeze':
        problems = freeze_preconditions()
        if problems:
            raise ValueError('freeze refused: ' + '; '.join(problems))
        data = freeze_document()
        with LOCK.open('x') as handle:
            json.dump(data, handle, indent=2)
            handle.write('\n')
        return 0
    if args.command == 'power':
        print(json.dumps(power(), indent=2))
        return 0
    if args.command == 'budget':
        print(json.dumps(budget(), indent=2))
        return 0
    if args.command == 'revalidate':
        print(json.dumps(revalidate(args.cells_dir, args.out), indent=2))
        return 0
    # Even offline report operations reject repository paths and freeze drift.
    orig.output_guard(Path(args.output) / 'probe.json')
    if args.command == 'analyze':
        print(json.dumps({k: v for k, v in analyze_file(args.output, args.view).items() if k != 'cells'}, indent=2))
        return 0
    if args.command == 'summary':
        frozen()
        p = protocol()
        results = {v: analyze_file(args.output, v, write=False) for v in p['views']
                   if all(paths(args.output, t).exists() for t in p['views'][v]['tiers'])}
        print(json.dumps({'protocol': PROTOCOL_ID, 'results': {v: {k: x for k, x in r.items() if k != 'cells'} for v, r in results.items()},
                          'unverified_live_checks': ['child rollout persistence and token additivity', 'variant exposure/manipulation',
                                                     'generation server reuse', 'scoring in clean environments']}, indent=2))
        return 0
    return {'harness-check': harness, 'preflight': preflight, 'drive': drive, 'score': score}[args.command](args)


if __name__ == '__main__':
    try:
        raise SystemExit(main())
    except (ValueError, KeyError, FileNotFoundError) as error:
        print('refused: ' + str(error), file=sys.stderr)
        raise SystemExit(3)
