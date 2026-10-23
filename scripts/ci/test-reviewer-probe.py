#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Dependency-free adversarial contract checks, not native browser evidence."""
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import signal
import subprocess
import sys
import tempfile
import time
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
    def boundary_mode(self, mode):
        self.plan['mode'] = mode
        (self.source/'policy.txt').write_text('detected')
        if mode == 'assertion-mutation':
            self.plan['edits'] = [{'path':'test.spec.ts','before':'assert transfer','after':'assert impossible','sha256':sha(b'assert transfer'),'kind':'test'}]
            self.native(NATIVE.replace("fault=(p/'app.txt').read_text()=='BROKEN'", "fault=(p/'test.spec.ts').read_text()=='assert impossible'"))
    def boundary_result(self):
        before = {p.relative_to(self.source).as_posix(): (p.read_bytes(), p.stat().st_mode) for p in self.source.rglob('*') if p.is_file()}
        preview,_ = self.invoke()
        self.assertEqual(preview['verdict'], 'PREVIEW')
        result,out = self.invoke(True, preview['approval_sha256'])
        after = {p.relative_to(self.source).as_posix(): (p.read_bytes(), p.stat().st_mode) for p in self.source.rglob('*') if p.is_file()}
        self.assertEqual(after, before)
        self.assertTrue(result['original_source_unchanged'])
        self.assertEqual(result['source_before_sha256'], result['source_after_sha256'])
        self.assertEqual(result['verdict'], 'CANNOT_VERIFY')
        self.assertFalse(result['behavior_proof'])
        return result,out
    def test_native_command_startup_failure_preserves_original(self):
        for mode in ('behavior-fault', 'assertion-mutation'):
            with self.subTest(mode=mode):
                self.boundary_mode(mode)
                self.plan['test']['argv'] = [str(self.root/'missing-python'), 'native.py']
                result,out = self.boundary_result()
                self.assertEqual(result['phases'], {})
                self.assertIn('No such file', result['error'])
                self.assertFalse((out/'fault').exists())
    def test_native_nonzero_cannot_use_valid_report_as_detection(self):
        for mode in ('behavior-fault', 'assertion-mutation'):
            with self.subTest(mode=mode):
                self.boundary_mode(mode)
                script = (self.source/'native.py').read_text().replace('raise SystemExit(1 if failed else 0)', "raise SystemExit(7 if phase=='fault' else 0)")
                self.native(script)
                result,out = self.boundary_result()
                self.assertEqual(result['error'], 'native exit/report mismatch')
                report = json.loads((out/'fault/project/native-report.json').read_text())
                self.assertEqual(report['suites'][0]['specs'][0]['tests'][0]['results'][0]['status'], 'failed')
                self.assertEqual(json.loads((out/'fault/test/command.json').read_text())['exit_code'], 7)
    def test_native_timeout_cannot_use_valid_report_as_detection(self):
        for mode in ('behavior-fault', 'assertion-mutation'):
            with self.subTest(mode=mode):
                self.boundary_mode(mode)
                script = (self.source/'native.py').read_text().replace('raise SystemExit(1 if failed else 0)', "if phase=='fault':\n import time;time.sleep(30)\nraise SystemExit(1 if failed else 0)")
                self.native(script)
                self.plan['test']['timeout_seconds'] = 1
                result,out = self.boundary_result()
                self.assertEqual(result['error'], 'native exit/report mismatch')
                receipt = json.loads((out/'fault/test/command.json').read_text())
                self.assertTrue(receipt['timeout'])
                self.assertIsNone(receipt['exit_code'])
                self.assertTrue((out/'fault/project/native-report.json').is_file())
    def test_failed_observer_cannot_use_valid_stdout_as_detection(self):
        for mode in ('behavior-fault', 'assertion-mutation'):
            self.boundary_mode(mode)
            for phase in ('normal', 'fault', 'restored'):
                with self.subTest(mode=mode, phase=phase):
                    # Emit otherwise valid observations before failing. Even a late
                    # observer failure must invalidate the entire three-phase proof.
                    script = OBSERVER + "\nimport os\nraise SystemExit(7 if os.environ['E2E_PROBE_PHASE']==" + repr(phase) + " else 0)\n"
                    (self.source/'observer.py').write_text(script)
                    self.plan['observer']['source']['sha256'] = sha(script.encode())
                    result,out = self.boundary_result()
                    self.assertEqual(result['error'], 'observer command failed')
                    command_dir = out/phase/'observer'
                    self.assertEqual(json.loads((command_dir/'command.json').read_text())['exit_code'], 7)
                    self.assertIn('evidence', json.loads((command_dir/'stdout.txt').read_text()))
    @unittest.skipUnless(os.name == 'posix', 'process groups require POSIX')
    def test_timeout_kills_owned_child_process_group(self):
        spec = importlib.util.spec_from_file_location('probe_timeout', RUNNER)
        module = importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
        output = self.root/'command';output.mkdir()
        child_pid = self.root/'child.pid'
        child_code = 'import time;time.sleep(30)'
        parent_code = "import pathlib,subprocess,sys,time;p=subprocess.Popen([sys.executable,'-c'," + repr(child_code) + "]);pathlib.Path(" + repr(str(child_pid)) + ").write_text(str(p.pid));time.sleep(30)"
        def alive(pid):
            # A reparented zombie has stopped executing; Linux container PID 1
            # need not reap it immediately, so kill(pid, 0) alone is insufficient.
            if sys.platform.startswith('linux'):
                try:
                    status = (Path('/proc')/str(pid)/'stat').read_text()
                except FileNotFoundError:
                    return False
                # The parenthesized command name may contain spaces or ')'.
                # State is the first token after its final closing parenthesis.
                state = status.rsplit(')', 1)[1].split()[0]
                return state not in ('Z', 'X')
            status = subprocess.run(['/bin/ps','-o','stat=','-p',str(pid)], capture_output=True, text=True, timeout=2)
            return bool(status.stdout.strip()) and not status.stdout.strip().startswith('Z')
        try:
            receipt = module.run_command({'argv':[sys.executable,'-c',parent_code], '_selector':'copies content', 'timeout_seconds':1}, self.source, 'fault', self.root/'unused-report.json', output)
            self.assertTrue(child_pid.is_file(), 'child must start before timeout')
            pid = int(child_pid.read_text())
            self.assertTrue(receipt['timeout'])
            self.assertIsNone(receipt['exit_code'])
            self.assertIs(receipt['owned_process_group_cleanup'], True)
            deadline = time.monotonic() + 3
            while alive(pid) and time.monotonic() < deadline:time.sleep(0.05)
            self.assertFalse(alive(pid), 'owned child survived process-group cleanup')
            self.assertEqual(json.loads((output/'command.json').read_text()), receipt)
        finally:
            if child_pid.exists():
                try:os.kill(int(child_pid.read_text()), signal.SIGKILL)
                except ProcessLookupError:pass
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

class PreparationGuidance(unittest.TestCase):
    """Instruction regression guards; these do not certify actor behavior."""

    def setUp(self):
        self.guidance = ' '.join(
            (RUNNER.parent.parent / 'references/runtime-probes.md').read_text().split()
        )

    def test_reviewer_owns_missing_project_glue(self):
        self.assertIn('Create the missing native wrapper, V3 observer, and JSON plan yourself', self.guidance)
        self.assertIn('Do not require the user to author these artifacts or register an adapter.', self.guidance)

    def test_baseline_is_not_repaired_into_probe_success(self):
        self.assertIn('First run the unchanged selected test in the disposable snapshot', self.guidance)
        self.assertIn('A failing or skipped baseline is not mutation or fault evidence.', self.guidance)

    def test_no_new_install_authority_or_original_edits(self):
        self.assertIn('Reuse existing dependencies and browser binaries', self.guidance)
        self.assertIn('Do not install packages, download tools, pull images', self.guidance)
        self.assertIn('Existing approval for the exact scope remains valid', self.guidance)
        self.assertIn('Keep the original checkout unchanged', self.guidance)

    def test_modes_do_not_require_irrelevant_preparation(self):
        self.assertIn('V2 needs no V3 observer', self.guidance)
        self.assertIn('Do not substitute V2 for requested V3 evidence', self.guidance)
        self.assertIn('one evidence-backed setup correction', self.guidance)

    def test_ordinary_review_offers_a_bounded_followup(self):
        skill = (RUNNER.parent.parent / 'SKILL.md').read_text()
        self.assertIn('After completing the static review', skill)
        self.assertIn('offer at most one source-backed mutation or app-fault probe', skill)
        self.assertIn('Do not block the completed review on a reply', skill)
        self.assertIn('already requested and authorized: proceed without asking again', skill)
        self.assertIn('Static-only requests or no meaningful candidate: omit the offer', skill)
        self.assertIn('Explain the additional token and execution-time cost', skill)
        self.assertIn('do not promise higher overall accuracy', skill)

    def test_followup_distinguishes_assertion_and_app_questions(self):
        self.assertIn('Select V2 for an unresolved question', self.guidance)
        self.assertIn('select V3 for an unresolved question', self.guidance)
        self.assertIn('Offer both only when both questions matter', self.guidance)
        self.assertIn('separate probes with separate verdicts', self.guidance)
        self.assertIn('do not run both automatically for every review', self.guidance)

if __name__=='__main__':unittest.main()
