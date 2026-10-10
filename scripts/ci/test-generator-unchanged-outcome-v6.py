#!/usr/bin/env python3
"""Offline packet/provenance controls; never calls a model. Apache-2.0."""
import copy
import importlib.util
import tempfile
from pathlib import Path
from types import SimpleNamespace
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[2]
spec = importlib.util.spec_from_file_location('unchanged_v6', ROOT / 'scripts/evals/run-generator-unchanged-outcome-v6.py')
m = importlib.util.module_from_spec(spec)
spec.loader.exec_module(m)
PLAN = [{'title': 'Approved unique title', 'action': 'Approved unique action', 'primary_outcome': 'Approved unique outcome', 'v1_completion': 'Approved unique completion'}]
SECTION = '## V1 — Primary Outcome\n\nExact instructions.\n'


def events(prompt=None, receiver='reviewer-1', verdict_receiver=None):
    prompt = prompt if prompt is not None else 'read-only e2e-reviewer tests/a.spec.mjs\n' + '\n'.join(PLAN[0].values()) + '\n' + SECTION
    return [dict(type='item.completed', item=dict(type='collab_tool_call', tool='spawn_agent', prompt=prompt,
                receiver_thread_ids=[receiver], status='completed')),
            dict(type='item.completed', item=dict(type='collab_tool_call', tool='wait',
                agents_states={verdict_receiver or receiver: dict(status='completed', message='V6 VERDICT: PASS P0=0 P1=0 P2=0 reviewer=id')}))]


def matrix():
    rows, entries = [], []
    for item in m.schedule():
        call = f"{item['case']}-{item['arm']}-r{item['repetition']}"
        rows.append(dict(item, call_id=call, clean=True, refactor_score=1, scan={'p0':0}, timeout=False,
                         packet=dict(credited=item['arm']=='after', scope_violations=[]),
                         faults={key:dict(killed=True) for key in ('late-dom-below-minimum','synchronous-below-minimum','disabled-enabled')}))
        entries.append(dict(call_id=call,status='VERIFIED',primary_causal_dom_kill=True,synchronous_covered=True,
                            disabled_covered=True,synchronous_guard_killed=True,disabled_guard_killed=True,evidence=[{'reason':'bound'}]))
    return rows,dict(entries=entries)


class Tests(unittest.TestCase):
    def test_v5_boundary_replay_is_posthoc_only(self):
        p=m.read(m.BENCH/'packet-boundary-preflight.json')
        self.assertEqual(p['status'],'POSTHOC_CALIBRATION_ONLY')
        self.assertEqual(len(p['rows']),8)
        self.assertEqual(p['old_totals'],{'before':0,'after':2})
        self.assertEqual(p['new_totals'],{'before':0,'after':4})
        repaired=[row for row in p['rows'] if row['new_credit'] and not row['old_credit']]
        self.assertEqual(len(repaired),2)
        for row in repaired:
            accepted=[packet for packet in row['new_packets'] if packet['credited']]
            self.assertTrue(accepted)
            self.assertTrue(all(packet['section_match']=='one-terminal-lf-at-message-end' and not packet['missing_fields'] for packet in accepted))

    def test_terminal_newline_forms_are_credited(self):
        original=events()[0]['item']['prompt']
        self.assertEqual(m.section_match(original,SECTION),'exact')
        trimmed=original[:-1]
        self.assertEqual(m.section_match(trimmed,SECTION),'one-terminal-lf-at-message-end')
        self.assertTrue(m.packet_check(events(trimmed),PLAN,SECTION)['credited'])
        self.assertTrue(m.packet_check(events(original),PLAN,SECTION)['credited'])

    def test_only_one_terminal_lf_can_be_omitted_at_end_of_message(self):
        section=SECTION+'\n'
        prompt='read-only e2e-reviewer tests/a.spec.mjs\n'+'\n'.join(PLAN[0].values())+'\n'+section
        self.assertTrue(m.packet_check(events(prompt[:-1]),PLAN,section)['credited'])
        for bad in (prompt[:-2],prompt[:-1]+'suffix',prompt[:-2]+' ',prompt[:-1]+'\r'):
            self.assertFalse(m.packet_check(events(bad),PLAN,section)['credited'])
        no_lf=SECTION[:-1]
        self.assertIsNone(m.section_match('prefix '+no_lf[:-1],no_lf))

    def test_internal_bytes_header_lists_and_whitespace_are_not_normalized(self):
        section='## V1 — Primary Outcome\n\n- Exact first item.\n- Exact second item.\n'
        prefix='read-only e2e-reviewer tests/a.spec.mjs\n'+'\n'.join(PLAN[0].values())+'\n'
        for bad in (section.replace('## V1 — Primary Outcome\n',''),section.replace('first','other'),section.replace('- Exact','* Exact'),section.replace('\n\n','\n'),section.replace('Exact first','Exact  first'),section.replace('\n','\r\n'),section[:-3],section.replace('item.\n','item. \n')):
            self.assertFalse(m.packet_check(events(prefix+bad),PLAN,section)['credited'])

    def test_terminal_lf_does_not_bypass_receiver_or_fail_verdict(self):
        data=events(events()[0]['item']['prompt'][:-1],verdict_receiver='wrong')
        self.assertFalse(m.packet_check(data,PLAN,SECTION)['credited'])
        data=events(events()[0]['item']['prompt'][:-1])
        data[1]['item']['agents_states']['reviewer-1']['message']='V6 VERDICT: FAIL P0=1 P1=0 P2=0 reviewer=id'
        self.assertFalse(m.packet_check(data,PLAN,SECTION)['credited'])

    def test_runtime_configuration_is_pinned_default_trace_on(self):
        p=m.protocol()
        for case in m.CASES:
            config=m.BENCH/'cases'/case/'playwright.config.mjs'
            self.assertEqual(m.digest(config),p['runtime_configuration_sha256'][case])
            self.assertIn("trace:'on'",config.read_text())
            self.assertNotIn('outputDir:',config.read_text())
        changed=copy.deepcopy(m.read(m.PROTOCOL));changed['runtime_configuration_sha256'][m.CASES[0]]='0'*64
        original=m.read
        with patch.object(m,'read',lambda path:changed if path==m.PROTOCOL else original(path)):
            with self.assertRaisesRegex(ValueError,'runtime classification'):m.protocol()

    def test_retained_runtime_preflight_has_all_seventeen_completed_calls(self):
        p=m.read(m.BENCH/'runtime-preflight.json')
        self.assertEqual(p['status'],'PASS')
        self.assertEqual(p['replayed_calls'],17)
        self.assertEqual({version:sum(row['version']==version for row in p['rows']) for version in (2,3,4)},{2:12,3:2,4:3})
        for row in p['rows']:
            self.assertEqual(m.scope_violations(row['runtime_paths']),row['scope_violations'])
            self.assertEqual(row['scope_violations'],[])
            self.assertEqual(len(row['transcript_sha256']),64)

    def test_transcript_exact_report_anchor_and_privacy_alias(self):
        with tempfile.TemporaryDirectory() as directory:
            report=Path(directory).resolve()/'final.json'
            folder=report.parent/'final-transcripts';folder.mkdir()
            path=folder/('a'*32+'.jsonl');path.write_text('{}\n')
            row={'attempts':[{'transcript_path':str(path),'transcript_sha256':m.digest(path)}]}
            self.assertEqual(m.transcript_path(row,report),path)
            with patch.object(m.engine,'sanitize',lambda value:value.replace(str(report.parent),'/Users/user/.cache/test')):
                row['attempts'][0]['transcript_path']='/Users/user/.cache/test/final-transcripts/'+path.name
                self.assertEqual(m.transcript_path(row,report),path)
            for invalid in ('/Users/user/elsewhere/final-transcripts/'+path.name,str(report.parent/'wrong-transcripts'/path.name),str(folder/'..'/'final-transcripts'/path.name)):
                row['attempts'][0]['transcript_path']=invalid
                with self.assertRaises(ValueError):m.transcript_path(row,report)
            row['attempts'][0]['transcript_path']=str(path)
            row['attempts'][0]['transcript_sha256']='0'*64
            with self.assertRaises(ValueError):m.transcript_path(row,report)
            row['attempts'][0]['transcript_path']=str(folder/('c'*32+'.jsonl'))
            with self.assertRaises(ValueError):m.transcript_path(row,report)

    def test_transcript_symlink_and_invalid_filename_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            report=Path(directory).resolve()/'final.json'
            folder=report.parent/'final-transcripts';folder.mkdir()
            real=report.parent/'real';real.write_text('{}\n')
            path=folder/('b'*32+'.jsonl');path.symlink_to(real)
            row={'attempts':[{'transcript_path':str(path),'transcript_sha256':m.digest(real)}]}
            with self.assertRaises(ValueError):m.transcript_path(row,report)
            row['attempts'][0]['transcript_path']=str(folder/'arbitrary.jsonl')
            with self.assertRaises(ValueError):m.transcript_path(row,report)

    def test_configured_runtime_outputs_are_classified_by_path(self):
        names=['test-results/.last-run.json','test-results/minimum-control/trace.zip','test-results/minimum-control/error-context.md']
        self.assertEqual(m.scope_violations(names),[])
        for command in ('find test-results -type f 2>/dev/null | sort', 'cat test-results/.last-run.json', 'node read-results.mjs'):
            events=[dict(type='item.completed',item=dict(type='command_execution',command=command,exit_code=0))]
            self.assertEqual(m.scope_violations(names,events),[])
        for name in ('test-results/../../app.mjs','test-results/credentials.json','test-results/a/b/trace.zip','test-results/a/custom.json','test-results/./trace.zip','test-results/../trace.zip','test-results/.hidden/trace.zip','test-results/a/../../../trace.zip'):
            self.assertEqual(m.scope_violations([name]),[name])

    def test_score_validation_recomputes_packet_from_bound_transcript(self):
        record={'call_id':'candidate'}
        scored={'scores':[{'call_id':'candidate','packet':{'credited':True}}], 'raw_manifest':{'raw.json':'hash'},'original_manifest':{'orig.json':'orig'},'export_map':[{'sanitized_path':'raw.json','sanitized_sha256':'hash','original_path':'orig.json','original_sha256':'orig'}]}
        with patch.object(m,'check_rows'),patch.object(m,'check_manifest'),patch.object(m,'process_record',return_value={'credited':False}) as recompute:
            with self.assertRaisesRegex(ValueError,'actual bound outgoing transcript'):
                m.validate_score_records(scored,{'runs':[record]},Path('/output'),Path('/output/final.json'))
            recompute.assert_called_once_with(record,Path('/output/final.json'))

    def test_eight_calls_sequential_pairs(self):
        rows=m.schedule()
        self.assertEqual(len(rows),8)
        self.assertEqual(m.protocol()['maximum_model_attempts'],8)
        self.assertEqual(m.protocol()['workers'],1)
        for a,b in zip(rows[::2],rows[1::2]):
            self.assertEqual((a['case'],a['repetition']),(b['case'],b['repetition']))
            self.assertNotEqual(a['arm'],b['arm'])

    def test_exact_packet_and_receiver_verdict_credit(self):
        result=m.packet_check(events(),PLAN,SECTION)
        self.assertTrue(result['credited'])
        self.assertEqual(result['packets'][0]['line'],1)
        self.assertEqual(result['packets'][0]['verdict']['line'],2)

    def test_verbatim_section_required(self):
        prompt=events()[0]['item']['prompt'].replace('Exact instructions.','Paraphrased instructions.')
        self.assertFalse(m.packet_check(events(prompt),PLAN,SECTION)['credited'])

    def test_every_approved_field_required(self):
        for field in PLAN[0]:
            prompt=events()[0]['item']['prompt'].replace('\n'+PLAN[0][field]+'\n','\n')
            self.assertFalse(m.packet_check(events(prompt),PLAN,SECTION)['credited'],field)

    def test_link_is_not_section(self):
        prompt='read-only e2e-reviewer tests/a.spec.mjs T A O C verification-rules.md V1'
        self.assertFalse(m.packet_check(events(prompt),PLAN,SECTION)['credited'])

    def test_self_report_is_not_packet(self):
        data=[dict(type='item.completed',item=dict(type='agent_message',text=events()[0]['item']['prompt']))]
        self.assertFalse(m.packet_check(data,PLAN,SECTION)['credited'])

    def test_command_read_output_is_not_packet(self):
        data=[dict(type='item.completed',item=dict(type='command_execution',aggregated_output=events()[0]['item']['prompt']))]
        self.assertFalse(m.packet_check(data,PLAN,SECTION)['credited'])

    def test_started_spawn_not_credit(self):
        data=events(); data[0]['type']='item.started'
        self.assertFalse(m.packet_check(data,PLAN,SECTION)['credited'])

    def test_other_reviewer_verdict_not_credit(self):
        self.assertFalse(m.packet_check(events(verdict_receiver='wrong'),PLAN,SECTION)['credited'])

    def test_missing_verdict_not_credit(self):
        self.assertFalse(m.packet_check(events()[:1],PLAN,SECTION)['credited'])

    def test_failure_verdict_not_credit(self):
        data=events();data[1]['item']['agents_states']['reviewer-1']['message']='V6 VERDICT: FAIL P0=1 P1=0 P2=0 reviewer=id'
        self.assertFalse(m.packet_check(data,PLAN,SECTION)['credited'])

    def test_non_fresh_send_message_not_credit(self):
        data=events();data[0]['item']['tool']='send_message'
        self.assertFalse(m.packet_check(data,PLAN,SECTION)['credited'])

    def test_no_read_only_contract_not_credit(self):
        self.assertFalse(m.packet_check(events(events()[0]['item']['prompt'].replace('read-only','writer')),PLAN,SECTION)['credited'])

    def test_section_extraction_preserves_bytes(self):
        text='prefix\n'+SECTION+'\n## V2 — Assertion Falsification\nother'
        self.assertEqual(m.v1_section(text),SECTION)

    def test_timestamped_cli_outputs_are_runtime_even_with_guard_setup(self):
        name='.playwright-cli/page-2026-10-09T01-02-03-004Z.yml'
        self.assertEqual(m.scope_violations([name]),[])
        command='printf guard > /tmp/guard.json; npx --no-install playwright cli --config /tmp/guard.json snapshot'
        events=[dict(type='item.completed',item=dict(type='command_execution',command=command,exit_code=0))]
        self.assertEqual(m.scope_violations([name],events),[])
        self.assertEqual(m.scope_violations([name,'app.mjs'],events),['app.mjs'])
        self.assertEqual(m.scope_violations(['.playwright-cli/page-custom.yml']),['.playwright-cli/page-custom.yml'])

    def test_scope_traversal_and_arbitrary_cli_files_rejected(self):
        names=['.playwright-cli/../app.mjs','.playwright-cli/page-custom.yml','.playwright-cli/credentials.json']
        self.assertEqual(m.scope_violations(names),names)

    def test_packet_primary_signal_dom_is_guard(self):
        rows,audit=matrix(); result=m.decision(rows,audit)
        self.assertEqual(result['status'],'DIRECTIONAL_SIGNAL')
        self.assertEqual(result['packet_primary_totals'],{'before':0,'after':4})
        self.assertFalse(result['release_equivalence'])

    def test_packet_tie_not_signal(self):
        rows,audit=matrix()
        for row in rows: row['packet']['credited']=True
        self.assertEqual(m.decision(rows,audit)['status'],'NO_DIRECTIONAL_SIGNAL')

    def test_three_after_minimum(self):
        rows,audit=matrix()
        for row in rows:
            if row['arm']=='after' and row['case']==m.CASES[0]:row['packet']['credited']=False
        self.assertEqual(m.decision(rows,audit)['status'],'NO_DIRECTIONAL_SIGNAL')

    def test_dom_regression_blocks_signal(self):
        rows,audit=matrix();audit['entries'][0]['primary_causal_dom_kill']=False
        self.assertFalse(m.decision(rows,audit)['guards'])

    def test_scope_violation_blocks_signal(self):
        rows,audit=matrix();rows[0]['packet']['scope_violations']=['app.mjs']
        self.assertFalse(m.decision(rows,audit)['guards'])

    def test_missing_cell_rejected(self):
        rows,audit=matrix()
        with self.assertRaises(ValueError):m.decision(rows[:-1],audit)

    def test_repeated_ready_requires_second_commit(self):
        truth=m.read(m.BENCH/'truth/repeated-ready.json')
        self.assertIn('second time',truth['task'])
        self.assertIn('id === 2',truth['faults'][0]['replace'])
        self.assertIn('Render 2 complete',m.read(m.BENCH/'approved-plan.json')['repeated-ready'][0]['v1_completion'])

    def test_approved_plan_matches_task_and_no_reference_staging(self):
        plans=m.read(m.BENCH/'approved-plan.json')
        for case in m.CASES:
            task=m.read(m.BENCH/'truth'/(case+'.json'))['task']
            for scenario in plans[case]:
                for value in scenario.values():self.assertIn(value,task)
            paths=m.engine.tree_digest(m.BENCH/'cases'/case)
            self.assertFalse(any('truth' in name or 'reference' in name for name in paths))

    def test_paid_calls_require_explicit_flag(self):
        with patch.object(m,'frozen') as frozen:
            with self.assertRaises(ValueError):m.run(SimpleNamespace(allow_live=False))
            frozen.assert_not_called()


if __name__=='__main__':unittest.main()
