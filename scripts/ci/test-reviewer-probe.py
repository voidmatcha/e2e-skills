#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Dependency-free adversarial contract checks, not native browser evidence."""
import hashlib
import importlib.util
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

RUNNER = Path(__file__).resolve().parents[2] / 'skills/e2e-reviewer/scripts/run-probe.py'
sha = lambda data: hashlib.sha256(data).hexdigest()
NATIVE = '''import json,os,pathlib
p=pathlib.Path.cwd();fault=(p/'app.txt').read_text()=='BROKEN';phase=os.environ['E2E_PROBE_PHASE'];policy=(p/'policy.txt').read_text()
failed=(fault and policy in ('detected','other')) or (phase=='restored' and policy=='restoredfail')
message='unrelated failure' if policy=='other' else 'expected transfer at test.spec.ts:25:3'
if policy=='sourcechanged':(p/'app.txt').write_text('MUTATED')
status='failed' if failed else 'passed'
r={'config':{'workers':1},'suites':[{'specs':[{'title':'copies content','file':'test.spec.ts','tests':[{'expectedStatus':'passed','results':[{'status':status,'retry':0,'errors':[{'message':message}] if failed else []}]}]}]}]}
pathlib.Path(os.environ['E2E_PROBE_REPORT']).write_text(json.dumps(r))
raise SystemExit(1 if failed else 0)
'''
OBSERVER = '''import hashlib,json,pathlib
p=pathlib.Path.cwd();broken=(p/'app.txt').read_text()=='BROKEN'
e=p/'observed.json';e.write_text(json.dumps({'actual_content':'old' if broken else 'transferred'}))
print(json.dumps({'project':str(p),'promised_effect':not broken,'fault_reached':broken,'evidence':[{'path':'observed.json','sha256':hashlib.sha256(e.read_bytes()).hexdigest()}]}))
'''

class Probe(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup)
        self.root=Path(self.temp.name).resolve();self.source=self.root/'source';self.source.mkdir()
        for name,value in {'app.txt':'WORKS','test.spec.ts':'assert transfer','README.md':'copy transfers content','policy.txt':'survived','native.py':NATIVE,'observer.py':OBSERVER}.items():
            (self.source/name).write_text(value)
        self.plan={'version':1,'source':str(self.source),'test_selector':'copies content','test_paths':['test.spec.ts'],'mode':'behavior-fault','promise':{'path':'README.md','quote':'copy transfers content','sha256':sha((self.source/'README.md').read_bytes())},'edits':[{'path':'app.txt','before':'WORKS','after':'BROKEN','sha256':sha(b'WORKS'),'kind':'source'}],'test':{'argv':[sys.executable,'native.py'],'timeout_seconds':5,'source':{'path':'native.py','sha256':sha(NATIVE.encode())}},'observer':{'argv':[sys.executable,'observer.py'],'source':{'path':'observer.py','sha256':sha(OBSERVER.encode())}},'report':{'format':'playwright-json','path':'native-report.json'},'expected_failure':{'contains':'expected transfer','location':'test.spec.ts:25:3'}}
        self.number=0
    def native(self, script):
        (self.source/'native.py').write_text(script)
        self.plan['test']['source']['sha256']=sha(script.encode())
    def invoke(self, execute=False, approval=None, trust=True):
        self.number+=1;path=self.root/'plan.json';path.write_text(json.dumps(self.plan));out=self.root/f'out{self.number}'
        args=[sys.executable,str(RUNNER),'--plan',str(path),'--output-dir',str(out)]
        if execute:
            args+=['--execute','--approve-sha256',approval or 'bad']
            if trust:args+=['--trust-checkout']
        proc=subprocess.run(args,capture_output=True,text=True,timeout=20)
        return json.loads(proc.stdout),out
    def run_probe(self):
        preview,_=self.invoke();self.assertEqual(preview['verdict'],'PREVIEW')
        return self.invoke(True,preview['approval_sha256'])[0]
    def test_survived(self):self.assertEqual(self.run_probe()['verdict'],'SURVIVED')
    def test_detected(self):
        (self.source/'policy.txt').write_text('detected');self.assertEqual(self.run_probe()['verdict'],'DETECTED')
    def seed_observer(self, create_seed):
        # Synthetic state-machine regression, not browser or model evidence.
        script = """import hashlib,json,pathlib
p=pathlib.Path.cwd();broken=(p/'app.txt').read_text()=='BROKEN'
state={}
def api(operation, content):
    if operation=='create' or not broken:state['content']=content
api('create','' if not CREATE_SEED else 'seeded')
if not CREATE_SEED:api('update','seeded')
before=state['content'];ready=before=='seeded'
api('update','transferred')
after=state['content']
e=p/'observed.json';e.write_text(json.dumps({'before':before,'ready':ready,'after':after}))
print(json.dumps({'project':str(p),'promised_effect':ready and after=='transferred','fault_reached':ready and after!='transferred','evidence':[{'path':'observed.json','sha256':hashlib.sha256(e.read_bytes()).hexdigest()}]}))
""".replace('CREATE_SEED', repr(create_seed))
        (self.source/'observer.py').write_text(script)
        self.plan['observer']['source']['sha256']=sha(script.encode())
        (self.source/'policy.txt').write_text('detected')
    def test_seed_affected_by_fault_cannot_verify_linked_failure(self):
        self.seed_observer(False)
        preview,_=self.invoke();result,out=self.invoke(True,preview['approval_sha256'])
        observed=json.loads((out/'fault/project/observed.json').read_text())
        self.assertEqual(observed,{'before':'','ready':False,'after':''})
        self.assertEqual(result['verdict'],'CANNOT_VERIFY')
        self.assertFalse(result['behavior_proof'])
        self.assertEqual(result['verification']['V3']['verdict'],'CANNOT_VERIFY')
    def test_unaffected_create_branch_of_same_api_is_admissible(self):
        self.seed_observer(True)
        preview,_=self.invoke();result,out=self.invoke(True,preview['approval_sha256'])
        observed=json.loads((out/'fault/project/observed.json').read_text())
        self.assertEqual(observed,{'before':'seeded','ready':True,'after':'seeded'})
        self.assertEqual(result['verdict'],'DETECTED')
        self.assertTrue(result['behavior_proof'])
        self.assertEqual(result['verification']['V3']['verdict'],'PASS')
        self.assertEqual(result['verification']['V6']['verdict'],'CANNOT_VERIFY')
    def test_otherfailure(self):
        (self.source/'policy.txt').write_text('other');self.assertEqual(self.run_probe()['verdict'],'CANNOT_VERIFY')
    def test_restoredfail(self):
        (self.source/'policy.txt').write_text('restoredfail');self.assertEqual(self.run_probe()['verdict'],'CANNOT_VERIFY')
    def test_missingobserver(self):
        del self.plan['observer'];self.assertEqual(self.invoke()[0]['verdict'],'ERROR')
    def test_noop(self):
        self.plan['edits'][0]['after']='WORKS';self.assertEqual(self.invoke()[0]['verdict'],'ERROR')
    def test_traversal(self):
        self.plan['edits'][0]['path']='../app.txt';self.assertEqual(self.invoke()[0]['verdict'],'ERROR')
    def test_staleapproval(self):
        preview,_=self.invoke();(self.source/'policy.txt').write_text('changed')
        self.assertEqual(self.invoke(True,preview['approval_sha256'])[0]['verdict'],'ERROR')
    def test_phase_sourcechanged(self):
        (self.source/'policy.txt').write_text('sourcechanged');self.assertEqual(self.run_probe()['verdict'],'CANNOT_VERIFY')
    def test_untrusted(self):
        preview,_=self.invoke();result,_=self.invoke(True,preview['approval_sha256'],False)
        self.assertEqual(result['verdict'],'ERROR')
    def test_preview_no_commands(self):
        result,out=self.invoke();self.assertEqual(result['commands_executed'],0);self.assertFalse((out/'normal').exists())
    def test_symlink(self):
        (self.source/'linked').symlink_to(self.source/'app.txt');self.assertEqual(self.invoke()[0]['verdict'],'ERROR')
    def test_output_inside_source(self):
        path=self.root/'plan.json';path.write_text(json.dumps(self.plan))
        proc=subprocess.run([sys.executable,str(RUNNER),'--plan',str(path),'--output-dir',str(self.source/'out')],capture_output=True,text=True)
        self.assertEqual(json.loads(proc.stdout)['verdict'],'ERROR')
    def test_bool_not_evidence(self):
        script="import json,pathlib; print(json.dumps({'project':str(pathlib.Path.cwd()),'promised_effect':True,'fault_reached':True,'evidence':True}))"
        (self.source/'observer.py').write_text(script);self.plan['observer']['source']['sha256']=sha(script.encode())
        self.assertEqual(self.run_probe()['verdict'],'CANNOT_VERIFY')
    def test_unknown_key(self):
        self.plan['typo']=True;self.assertEqual(self.invoke()[0]['verdict'],'ERROR')
    def test_wrong_mode_edit(self):
        self.plan['mode']='assertion-mutation';self.assertEqual(self.invoke()[0]['verdict'],'ERROR')
    def test_assertion_sensitive(self):
        self.plan['mode']='assertion-mutation';del self.plan['observer']
        self.plan['edits']=[{'path':'test.spec.ts','before':'assert transfer','after':'assert impossible','sha256':sha(b'assert transfer'),'kind':'test'}]
        script=NATIVE.replace("fault=(p/'app.txt').read_text()=='BROKEN'", "fault=(p/'test.spec.ts').read_text()=='assert impossible'")
        self.native(script);(self.source/'policy.txt').write_text('detected')
        result=self.run_probe();self.assertEqual(result['verdict'],'ASSERTION_SENSITIVE');self.assertFalse(result['behavior_proof'])
    def test_missing_evidence(self):
        script=OBSERVER.replace("'path':'observed.json'", "'path':'absent.json'")
        (self.source/'observer.py').write_text(script);self.plan['observer']['source']['sha256']=sha(script.encode())
        self.assertEqual(self.run_probe()['verdict'],'CANNOT_VERIFY')
    def test_wrong_phase_observer(self):
        script=OBSERVER.replace("'project':str(p)", "'project':'/other/project'")
        (self.source/'observer.py').write_text(script);self.plan['observer']['source']['sha256']=sha(script.encode())
        self.assertEqual(self.run_probe()['verdict'],'CANNOT_VERIFY')
    def test_wrong_selected_test(self):
        self.native(NATIVE.replace("'title':'copies content'", "'title':'different test'"))
        self.assertEqual(self.run_probe()['verdict'],'CANNOT_VERIFY')
    def test_nonboolean_observer(self):
        script=OBSERVER.replace("'promised_effect':not broken", "'promised_effect':'false'")
        (self.source/'observer.py').write_text(script);self.plan['observer']['source']['sha256']=sha(script.encode())
        self.assertEqual(self.run_probe()['verdict'],'CANNOT_VERIFY')
    def test_original_source_changed(self):
        script=NATIVE.replace("p=pathlib.Path.cwd();", "pathlib.Path("+repr(str(self.source/'policy.txt'))+").write_text('MUTATED');p=pathlib.Path.cwd();")
        self.native(script)
        self.assertEqual(self.run_probe()['verdict'],'CANNOT_VERIFY')
    def test_behavior_no_wrongstate(self):
        script=OBSERVER.replace("'promised_effect':not broken", "'promised_effect':True")
        (self.source/'observer.py').write_text(script);self.plan['observer']['source']['sha256']=sha(script.encode())
        self.assertEqual(self.run_probe()['verdict'],'CANNOT_VERIFY')
    def test_installed_copy_selfcontained(self):
        copied=self.root/'installed'/'run-probe.py';copied.parent.mkdir();copied.write_bytes(RUNNER.read_bytes())
        planpath=self.root/'plan.json';planpath.write_text(json.dumps(self.plan))
        preview=subprocess.run([sys.executable,str(copied),'--plan',str(planpath),'--output-dir',str(self.root/'installed-preview')],capture_output=True,text=True)
        approval=json.loads(preview.stdout)['approval_sha256']
        run=subprocess.run([sys.executable,str(copied),'--plan',str(planpath),'--output-dir',str(self.root/'installed-run'),'--execute','--trust-checkout','--approve-sha256',approval],capture_output=True,text=True)
        self.assertEqual(json.loads(run.stdout)['verdict'],'SURVIVED')
    def test_env_approval_stale(self):
        import os
        preview,_=self.invoke();old=os.environ.get('PATH')
        try:
            os.environ['PATH']=(old or '')+':/different-approved-path'
            self.assertEqual(self.invoke(True,preview['approval_sha256'])[0]['verdict'],'ERROR')
        finally:
            if old is None:os.environ.pop('PATH',None)
            else:os.environ['PATH']=old
    def test_absolute_output_traversal(self):
        planpath=self.root/'plan.json';planpath.write_text(json.dumps(self.plan))
        output=str(self.root/'other')+'/../source/artifact'
        run=subprocess.run([sys.executable,str(RUNNER),'--plan',str(planpath),'--output-dir',output],capture_output=True,text=True)
        self.assertEqual(json.loads(run.stdout)['verdict'],'ERROR');self.assertFalse((self.source/'artifact').exists())
    def test_wrapper_mutation_rejected(self):
        self.plan['edits']=[{'path':'native.py','before':'unrelated failure','after':'different failure','sha256':sha(NATIVE.encode()),'kind':'source'}]
        self.assertEqual(self.invoke()[0]['verdict'],'ERROR')
    def test_static_evidence_rejected(self):
        script=OBSERVER.replace("'path':'observed.json','sha256':hashlib.sha256(e.read_bytes()).hexdigest()", "'path':'README.md','sha256':hashlib.sha256((p/'README.md').read_bytes()).hexdigest()")
        (self.source/'observer.py').write_text(script);self.plan['observer']['source']['sha256']=sha(script.encode())
        self.assertEqual(self.run_probe()['verdict'],'CANNOT_VERIFY')
    def test_playwright_report_guards(self):
        import types
        module=types.ModuleType('probe');module.__file__=str(RUNNER);exec(compile(RUNNER.read_bytes(),str(RUNNER),'exec'),module.__dict__)
        r={'config':{'workers':1},'suites':[{'specs':[{'title':'copies content','file':'test.spec.ts','tests':[{'expectedStatus':'passed','status':'expected','results':[{'status':'passed','retry':0,'errors':[]}]}]}]}],'errors':[],'stats':{'expected':1,'unexpected':0,'flaky':0,'skipped':0}}
        parse=lambda:module.parse_native(r,'playwright-json','copies content',['test.spec.ts'],self.source)
        self.assertEqual(parse()[0],'passed')
        for modify in (lambda:r.update(errors=[{'message':'global fail'}]),lambda:r['stats'].update(unexpected=1),lambda:r['suites'][0]['specs'][0].update(file='other.spec.ts'),lambda:r['suites'][0]['specs'][0]['tests'][0].update(status='unexpected'),lambda:r['suites'][0]['specs'][0]['tests'][0]['results'][0].update(errors=[{'message':'error on pass'}])):
            backup=json.loads(json.dumps(r));modify()
            with self.assertRaises(ValueError):parse()
            r=backup
    def test_link_not_pooled_across_errors(self):
        script=NATIVE.replace("'errors':[{'message':message}] if failed else []", "'errors':[{'message':'expected transfer'},{'message':'other at test.spec.ts:25:3'}] if failed else []")
        self.native(script);(self.source/'policy.txt').write_text('detected')
        self.assertEqual(self.run_probe()['verdict'],'CANNOT_VERIFY')
    def test_playwright_native_rootdir(self):
        import types
        module=types.ModuleType('probe');module.__file__=str(RUNNER);exec(compile(RUNNER.read_bytes(),str(RUNNER),'exec'),module.__dict__)
        nested=self.source/'e2e';nested.mkdir();(nested/'smoke.spec.ts').write_text('original test')
        r={'config':{'workers':1,'rootDir':str(nested)},'suites':[{'specs':[{'title':'copies content','file':'smoke.spec.ts','tests':[{'expectedStatus':'passed','results':[{'status':'passed','retry':0,'errors':[]}]}]}]}]}
        parse=lambda:module.parse_native(r,'playwright-json','copies content',['e2e/smoke.spec.ts'],self.source)
        self.assertEqual(parse()[0],'passed')
        # A declared root is exclusive, even if a project-relative fallback exists.
        r['suites'][0]['specs'][0]['file']='e2e/smoke.spec.ts'
        with self.assertRaises(ValueError):parse()
        r['suites'][0]['specs'][0]['file']=str(nested/'smoke.spec.ts')
        self.assertEqual(parse()[0],'passed')
        # Without a declared root, the phase project is the documented default.
        del r['config']['rootDir']
        r['suites'][0]['specs'][0]['file']='e2e/smoke.spec.ts'
        self.assertEqual(parse()[0],'passed')
        r['suites'][0]['specs'][0]['file']='smoke.spec.ts'
        r['config']['rootDir']=str(self.root)
        with self.assertRaises(ValueError):parse()
        r['config']['rootDir']=str(nested)+'/../../outside'
        with self.assertRaises(ValueError):parse()
        r['config']['rootDir']=str(nested)
        r['suites'][0]['specs'][0]['file']='../../smoke.spec.ts'
        with self.assertRaises(ValueError):parse()
        r['suites'][0]['specs'][0]['file']='other/smoke.spec.ts'
        with self.assertRaises(ValueError):parse()
    def test_native_shapes(self):
        spec=importlib.util.spec_from_file_location('probe',RUNNER);module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
        r={'totalTests':1,'totalPassed':1,'totalFailed':0,'totalPending':0,'totalSkipped':0,'runs':[{'spec':{'relative':'test.spec.ts'},'tests':[{'title':['suite','copies content'],'state':'passed','attempts':[{'state':'passed'}],'displayError':None}]}]}
        self.assertEqual(module.parse_native(r,'cypress-json','copies content',['test.spec.ts'],self.source)[0],'passed')
        r['runs'][0]['tests'][0]['attempts'].append({'state':'passed'})
        with self.assertRaises(ValueError):module.parse_native(r,'cypress-json','copies content',['test.spec.ts'],self.source)

if __name__=='__main__':unittest.main()
