#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Dependency-free adversarial contract checks, not native browser evidence."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import signal
import shutil
import socket
import subprocess
import sys
import tempfile
import time
import unittest

RUNNER = Path(__file__).resolve().parents[2] / 'skills/e2e-reviewer/scripts/run-probe.mjs'
PROBE_RUNTIME_FILES = ('run-probe.mjs', 'probe-lifecycle.mjs', 'probe-anchor.mjs', 'probe-cypress.mjs', 'probe-cypress-node.mjs')
parser = argparse.ArgumentParser(add_help=False)
parser.add_argument('--node')
options, remaining = parser.parse_known_args()
sys.argv = [sys.argv[0], *remaining]
NODE = options.node or shutil.which('node')
assert NODE, 'Node.js 22+ required'
assert Path(NODE).is_absolute(), 'Node executable must be absolute'

class NodeRunner:
    """Exercise exported production Node functions, not the historical oracle."""
    @staticmethod
    def call(name, args):
        script = "import * as runner from " + json.dumps(RUNNER.as_uri()) + "; const value=JSON.parse(process.argv[1]); try {console.log(JSON.stringify(await runner[process.argv[2]](...value)))} catch(e) {console.error(e.message);process.exitCode=2}"
        result = subprocess.run([NODE, '--input-type=module', '-e', script,
                                 json.dumps(args, default=str), name], capture_output=True, text=True, timeout=15)
        if result.returncode:
            raise ValueError(result.stderr.strip())
        return json.loads(result.stdout)
    def parse_native(self, *args): return self.call('parseNative', args)
    def run_command(self, *args): return self.call('runCommand', args)

sha = lambda data: hashlib.sha256(data).hexdigest()
NATIVE = '''import json,os,pathlib
p=pathlib.Path.cwd();fault='BROKEN' in (p/'app.js').read_text();phase=os.environ['E2E_PROBE_PHASE'];policy=(p/'policy.txt').read_text()
failed=(fault and policy in ('detected','other')) or (phase=='restored' and policy=='restoredfail')
message='unrelated failure' if policy=='other' else 'AssertionError: expected transfer but received old at test.spec.ts:25:3'
if policy=='sourcechanged':(p/'app.js').write_text('MUTATED')
status='failed' if failed else 'passed'
r={'config':{'workers':1},'suites':[{'specs':[{'title':'copies content','file':'test.spec.ts','tests':[{'expectedStatus':'passed','results':[{'status':status,'retry':0,'errors':[{'message':message}] if failed else []}]}]}]}]}
pathlib.Path(os.environ['E2E_PROBE_REPORT']).write_text(json.dumps(r))
raise SystemExit(1 if failed else 0)
'''
OBSERVER = '''import hashlib,json,os,pathlib
p=pathlib.Path.cwd();broken='BROKEN' in (p/'app.js').read_text()
e=p/'observed.json';e.write_text(json.dumps({'actual_content':'old' if broken else 'transferred'}))
# Synthetic runtime receipt: contract fixture, not browser execution evidence.
cfg=json.loads(os.environ.get('E2E_PROBE_REACHABILITY','null'))
if broken and cfg:
    pathlib.Path(cfg['artifact']).write_text(''.join(json.dumps({**{k:cfg[k] for k in ('token','path','phase','project')},'edit_index':index,'url':'synthetic://fixture'})+'\\n' for index in range(cfg['edit_count'])))
print(json.dumps({'project':str(p),'promised_effect':not broken,'fault_reached':broken,'evidence':[{'path':'observed.json','sha256':hashlib.sha256(e.read_bytes()).hexdigest()}]}))
'''
CYPRESS_NATIVE = '''import json,os,pathlib
p=pathlib.Path.cwd();failed=os.environ['E2E_PROBE_PHASE']=='fault'
message="AssertionError: Timed out retrying after 4000ms: expected rows to have text '0000000000', but the text was '22271929'\\n    at Context.eval (http://127.0.0.1/__cypress/tests?p=e2e/list.cy.js:2:3)"
attempt={'state':'failed' if failed else 'passed'}
if failed:attempt['error']=message
test={'title':['copies content'],'state':attempt['state'],'attempts':[attempt]}
run={'spec':{'relative':'cypress/e2e/list.cy.js'},'tests':[test],'stats':{'tests':1,'passes':int(not failed),'failures':int(failed),'pending':0,'skipped':0}}
r={'runs':[run],'totalTests':1,'totalPassed':int(not failed),'totalFailed':int(failed),'totalPending':0,'totalSkipped':0}
pathlib.Path(os.environ['E2E_PROBE_REPORT']).write_text(json.dumps(r))
raise SystemExit(int(failed))
'''

class Probe(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup)
        self.root=Path(self.temp.name).resolve();self.source=self.root/'source';self.source.mkdir()
        for name,value in {'app.js':'function action() { WORKS; }','test.spec.ts':'assert transfer','README.md':'copy transfers content','policy.txt':'survived','native.py':NATIVE,'observer.py':OBSERVER}.items():
            (self.source/name).write_text(value)
        self.plan={'version':1,'source':str(self.source),'test_selector':'copies content','test_paths':['test.spec.ts'],'mode':'behavior-fault','reachability':{'kind':'browser-binding','edit_path':'app.js'},'promise':{'path':'README.md','quote':'copy transfers content','sha256':sha((self.source/'README.md').read_bytes())},'edits':[{'path':'app.js','before':'WORKS;','after':'BROKEN;','sha256':sha(b'function action() { WORKS; }'),'kind':'source'}],'test':{'argv':[sys.executable,'native.py'],'timeout_seconds':5,'source':{'path':'native.py','sha256':sha(NATIVE.encode())}},'observer':{'argv':[sys.executable,'observer.py'],'source':{'path':'observer.py','sha256':sha(OBSERVER.encode())}},'report':{'format':'playwright-json','path':'native-report.json'},'expected_failure':{'spec':'test.spec.ts','title':'copies content','locator':{'location':'test.spec.ts:25:3'},'kind':'assertion','values':{'expected':{'type':'string','value':'transfer'},'actual':{'type':'string','relation':'different'}}}}
        self.number=0
    def native(self, script):
        (self.source/'native.py').write_text(script)
        self.plan['test']['source']['sha256']=sha(script.encode())
    def invoke(self, execute=False, approval=None, trust=True):
        self.number+=1;path=self.root/'plan.json';path.write_text(json.dumps(self.plan));out=self.root/f'out{self.number}'
        args=[NODE,str(RUNNER),'--plan',str(path),'--output-dir',str(out)]
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
    def cypress_placeholder(self, script=CYPRESS_NATIVE, focused=False):
        spec = self.source/'cypress/e2e/list.cy.js';spec.parent.mkdir(parents=True,exist_ok=True)
        spec.write_text(("it.only" if focused else "it") +
                        "('copies content', () => {\n  cy.get('td').should('have.text', '0000000000');\n});\n")
        self.plan['test_paths']=['cypress/e2e/list.cy.js']
        self.plan['expected_failure']={'contains':'expected selected behavior to hold',
                                       'location':'cypress/e2e/list.cy.js:1'}
        self.plan['report']['format']='cypress-json'
        self.native(script)
    def test_legacy_cypress_placeholder_is_vague(self):
        self.cypress_placeholder(focused=True)
        result=self.run_probe()
        self.assertEqual(result['verdict'],'CANNOT_VERIFY')
        self.assertIn('legacy free-text field is vague',result['error'])
    def test_specific_legacy_text_is_still_vague(self):
        (self.source/'policy.txt').write_text('detected')
        self.plan['expected_failure']={'contains':'expected transfer','location':'test.spec.ts:25:3'}
        result=self.run_probe()
        self.assertEqual(result['verdict'],'CANNOT_VERIFY')
        self.assertIn('legacy free-text field is vague',result['error'])
    def test_structured_cypress_text_attribution(self):
        self.cypress_placeholder()
        self.plan['expected_failure']={'spec':'cypress/e2e/list.cy.js','title':'copies content','locator':{'location':'cypress/e2e/list.cy.js:2:3'},'kind':'text','values':{'expected':{'type':'string','value':'0000000000'},'actual':{'type':'string','relation':'exact','value':'22271929'}}}
        result=self.run_probe()
        self.assertEqual(result['verdict'],'DETECTED')
        self.assertEqual(result['failure_attribution'],'structured-expected-failure')
    def test_structured_wrong_line_kind_and_values_rejected(self):
        self.cypress_placeholder()
        structured={'spec':'cypress/e2e/list.cy.js','title':'copies content','locator':{'location':'cypress/e2e/list.cy.js:2:3'},'kind':'text','values':{'expected':{'type':'string','value':'0000000000'},'actual':{'type':'string','relation':'exact','value':'22271929'}}}
        for change,reason in (({'locator':{'location':'cypress/e2e/list.cy.js:3:3'}},'locator'),({'kind':'count'},'kind'),({'values':{'expected':{'type':'string','value':'wrong'},'actual':{'type':'string','relation':'different'}}},'values.expected')):
            with self.subTest(change=change):
                self.plan['expected_failure']={**structured,**change}
                result=self.run_probe()
                self.assertEqual(result['verdict'],'CANNOT_VERIFY')
                self.assertIn('expected_failure.'+reason,result['error'])
    def test_structured_setup_timeout_rejected(self):
        self.cypress_placeholder(CYPRESS_NATIVE.replace('AssertionError: Timed out retrying after 4000ms: expected rows to have text', 'TimeoutError: Timed out after 4000ms waiting for rows to have text'))
        self.plan['expected_failure']={'spec':'cypress/e2e/list.cy.js','title':'copies content','locator':{'location':'cypress/e2e/list.cy.js:2:3'},'kind':'text','values':{'expected':{'type':'string','value':'0000000000'},'actual':{'type':'string','relation':'different'}}}
        result=self.run_probe()
        self.assertEqual(result['verdict'],'CANNOT_VERIFY')
        self.assertIn('timeout failure',result['error'])
    def test_structured_spec_must_equal_reported_spec(self):
        (self.source/'other.spec.ts').write_text('another test')
        self.plan['test_paths'].append('other.spec.ts')
        self.plan['expected_failure']['spec']='other.spec.ts'
        self.plan['expected_failure']['locator']={'matcher':'expected transfer but received old'}
        (self.source/'policy.txt').write_text('detected')
        result=self.run_probe()
        self.assertEqual(result['verdict'],'CANNOT_VERIFY')
        self.assertIn('expected_failure.spec mismatched',result['error'])
    def test_placeholder_rejects_unrelated_or_unlocated_native_failure(self):
        for script in (CYPRESS_NATIVE.replace('e2e/list.cy.js:2:3','e2e/other.cy.js:2:3'),
                       CYPRESS_NATIVE.replace("'0000000000'", "'wrong-value'"),
                       CYPRESS_NATIVE.replace('AssertionError: Timed out retrying after 4000ms: expected rows to have text', 'Error: Timed out after 4000ms waiting for rows to have text')):
            with self.subTest(script=script):
                self.cypress_placeholder(script)
                self.assertEqual(self.run_probe()['verdict'],'CANNOT_VERIFY')
    def test_placeholder_cannot_rescue_failed_normal_and_restored_baseline(self):
        self.cypress_placeholder(CYPRESS_NATIVE.replace("os.environ['E2E_PROBE_PHASE']=='fault'",'True'))
        self.assertEqual(self.run_probe()['verdict'],'CANNOT_VERIFY')
    def boundary_mode(self, mode):
        self.plan['mode'] = mode
        (self.source/'policy.txt').write_text('detected')
        if mode == 'assertion-mutation':
            self.plan.pop('reachability', None)
            self.plan['edits'] = [{'path':'test.spec.ts','before':'assert transfer','after':'assert impossible','sha256':sha(b'assert transfer'),'kind':'test'}]
            self.native(NATIVE.replace("fault='BROKEN' in (p/'app.js').read_text()", "fault=(p/'test.spec.ts').read_text()=='assert impossible'"))
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
                self.assertIn('ENOENT', result['error'])
                self.assertFalse((out/'fault').exists())
    def test_service_failure_preserves_error_after_verified_cleanup(self):
        for stage in ('startup', 'callback'):
            with self.subTest(stage=stage):
                with socket.socket() as endpoint:
                    endpoint.bind(('127.0.0.1', 0))
                    port = endpoint.getsockname()[1]
                service = ('process.exit(7)' if stage == 'startup' else
                           "require('node:http').createServer((req,res)=>res.end('ready')).listen(" + str(port) + ", '127.0.0.1')")
                script = ('import {withServices} from ' + json.dumps(RUNNER.as_uri()) + ';\n' +
                          'await withServices([{argv:[process.execPath,"-e",' + json.dumps(service) +
                          '],ready:{url:' + json.dumps(f'http://127.0.0.1:{port}/') +
                          ',timeoutMs:2000}}],async()=>{throw Error("callback sentinel failure")});\n')
                (self.source/'service-wrapper.mjs').write_text(script)
                self.plan['test'] = {'argv':[NODE, 'service-wrapper.mjs'], 'timeout_seconds':5,
                                     'source':{'path':'service-wrapper.mjs','sha256':sha(script.encode())}}
                result,out = self.boundary_result()
                expected = 'service exited before readiness' if stage == 'startup' else 'callback sentinel failure'
                self.assertIn(expected, result['error'])
                self.assertNotIn('cleanup is unverified', result['error'])
                self.assertEqual(result['phases'], {})
                self.assertFalse((out/'fault').exists())
                receipt = json.loads((out/'normal/test/command.json').read_text())
                self.assertTrue(receipt['owned_process_group_cleanup'])
                self.assertEqual(receipt['exit_code'], 1)
                self.assertEqual(receipt['services'][0]['status'], 'INCOMPLETE')
                self.assertTrue(all(service['cleanup']['complete'] for service in receipt['services'][0]['services']))
    def test_invalid_or_unfinished_service_receipts_keep_cleanup_unverified(self):
        for index, service_receipt in enumerate((
                {'status':'STARTED','services':[]},
                {'status':'INCOMPLETE','error':'startup failed','services':[{'cleanup':{'complete':False}}]},
                {'status':'INCOMPLETE','services':[{'cleanup':{'complete':True}}]},
                {'status':'COMPLETE','services':[None]},
                {'status':'UNKNOWN','services':[]},
                'not JSON')):
            with self.subTest(receipt=service_receipt):
                output = self.root/f'command-invalid-{index}';output.mkdir()
                raw = service_receipt if isinstance(service_receipt, str) else json.dumps(service_receipt)
                script = ('import os,pathlib;p=pathlib.Path(os.environ["E2E_PROBE_SERVICES_DIR"]);'
                          'p.mkdir();(p/"service.json").write_text(' + repr(raw) + ')')
                with self.assertRaisesRegex(ValueError, 'service cleanup is unverified'):
                    NodeRunner().run_command({'argv':[sys.executable,'-c',script], '_selector':'copies content'},
                                             self.source, 'normal', self.root/'unused-report.json', output)
                receipt = json.loads((output/'command.json').read_text())
                self.assertTrue(receipt['owned_process_group_cleanup'])
    def test_playwright_collection_errors_are_distinct_from_zero_matches(self):
        cause = "SyntaxError: The requested module 'glob' does not provide an export named 'globSync'"
        for index, errors in enumerate(([], [{'message':cause}, {'message':'Error: No tests found.'}])):
            with self.subTest(errors=errors):
                output = self.root/f'collection-{index}';output.mkdir()
                cli = self.source/'collection-cli.mjs'
                cli.write_text('import fs from "node:fs";\n' +
                               'if(!process.argv.includes("--list"))throw Error("native execution must not start");\n' +
                               'fs.writeFileSync(process.env.PLAYWRIGHT_JSON_OUTPUT_NAME,JSON.stringify(' +
                               json.dumps({'suites':[], 'errors':errors}) + '));\nprocess.exit(' + str(int(bool(errors))) + ');\n')
                config = {'selection':{'cli':cli.name,'file':'test.spec.ts','line':1},
                          'project':str(self.source),'phase':'normal','report':str(self.root/'unused-report.json'),
                          'out':str(output)}
                script = ('import {runPlaywright} from ' + json.dumps(RUNNER.as_uri()) + ';\n' +
                          'process.env.E2E_PROBE_PLAYWRIGHT=process.argv[1];\n' +
                          'try{await runPlaywright()}catch(error){console.error(error.message);process.exitCode=2}')
                result = subprocess.run([NODE,'--input-type=module','-e',script,json.dumps(config)],
                                        cwd=self.source,capture_output=True,text=True,timeout=15)
                self.assertEqual(result.returncode, 2)
                if errors:
                    self.assertIn('Playwright selection failed', result.stderr)
                    self.assertIn(cause, result.stderr)
                    self.assertIn('No tests found', result.stderr)
                    self.assertNotIn('Playwright selected 0 tests', result.stderr)
                else:
                    self.assertIn('Playwright selected 0 tests', result.stderr)
                    self.assertIn('declaration line', result.stderr)
                self.assertEqual(json.loads((output/'native-selection/report.json').read_text())['errors'], errors)
                self.assertFalse((self.root/'unused-report.json').exists())
                self.assertFalse((output/'native-run/command.json').exists())
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
    def test_timeout_does_not_signal_owned_group_twice(self):
        output = self.root/'command';output.mkdir()
        script = """import {runCommand} from RUNNER;
const originalKill = process.kill;
let signals = 0;
process.kill = function(pid, signal) {
  if (pid < 0 && signal === 'SIGKILL' && ++signals > 1) {
    const error = new Error('duplicate group signal'); error.code = 'EPERM'; throw error;
  }
  return originalKill.call(process, pid, signal);
};
const receipt = await runCommand(JSON.parse(process.argv[1]), ...JSON.parse(process.argv[2]));
console.log(JSON.stringify({receipt, signals}));
""".replace('RUNNER', json.dumps(RUNNER.as_uri()))
        config = {'argv':[sys.executable,'-c','import time;time.sleep(30)'],
                  '_selector':'copies content', 'timeout_seconds':1}
        args = [str(self.source), 'fault', str(self.root/'unused-report.json'), str(output)]
        result = subprocess.run([NODE, '--input-type=module', '-e', script,
                                 json.dumps(config), json.dumps(args)],
                                capture_output=True, text=True, timeout=15)
        self.assertEqual(result.returncode, 0, result.stderr)
        value = json.loads(result.stdout)
        self.assertEqual(value['signals'], 1)
        self.assertTrue(value['receipt']['timeout'])
        self.assertIs(value['receipt']['owned_process_group_cleanup'], True)
    @unittest.skipUnless(os.name == 'posix', 'process groups require POSIX')
    def test_initial_group_signal_permission_error_still_fails_closed(self):
        output = self.root/'command';output.mkdir()
        script = """import {runCommand} from RUNNER;
process.kill = () => { const error = new Error('group signal denied'); error.code = 'EPERM'; throw error; };
await runCommand(JSON.parse(process.argv[1]), ...JSON.parse(process.argv[2]));
""".replace('RUNNER', json.dumps(RUNNER.as_uri()))
        config = {'argv':[sys.executable,'-c','pass'], '_selector':'copies content'}
        args = [str(self.source), 'fault', str(self.root/'unused-report.json'), str(output)]
        result = subprocess.run([NODE, '--input-type=module', '-e', script,
                                 json.dumps(config), json.dumps(args)],
                                capture_output=True, text=True, timeout=15)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn('group signal denied', result.stderr)
        receipt = json.loads((output/'command.json').read_text())
        self.assertIn('owned process cleanup failed', receipt['error'])
        self.assertIs(receipt['owned_process_group_cleanup'], False)
        self.assertIs(receipt['lifecycle']['cleanup']['complete'], False)
        self.assertEqual(receipt['lifecycle']['cleanup']['error']['code'], 'EPERM')
    @unittest.skipUnless(os.name == 'posix', 'process groups require POSIX')
    def test_timeout_kills_owned_child_process_group(self):
        module = NodeRunner()
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
        script = """import hashlib,json,os,pathlib
p=pathlib.Path.cwd();broken='BROKEN' in (p/'app.js').read_text()
state={}
def api(operation, content):
    if operation=='create' or not broken:state['content']=content
api('create','' if not CREATE_SEED else 'seeded')
if not CREATE_SEED:api('update','seeded')
before=state['content'];ready=before=='seeded'
api('update','transferred')
after=state['content']
e=p/'observed.json';e.write_text(json.dumps({'before':before,'ready':ready,'after':after}))
# Synthetic runtime receipt: contract fixture, not browser execution evidence.
cfg=json.loads(os.environ.get('E2E_PROBE_REACHABILITY','null'))
if ready and broken and cfg:
    pathlib.Path(cfg['artifact']).write_text(''.join(json.dumps({**{k:cfg[k] for k in ('token','path','phase','project')},'edit_index':index,'url':'synthetic://fixture'})+'\\n' for index in range(cfg['edit_count'])))
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
    def test_runtime_receipt_required_despite_observer_boolean_and_fault_text(self):
        script=OBSERVER.replace('if broken and cfg:', 'if False and cfg:')
        (self.source/'observer.py').write_text(script)
        self.plan['observer']['source']['sha256']=sha(script.encode())
        (self.source/'policy.txt').write_text('detected')
        result=self.run_probe()
        self.assertEqual(result['verdict'],'CANNOT_VERIFY')
        self.assertFalse(result['behavior_proof'])
    def test_runtime_receipt_outranks_false_observer_boolean(self):
        script=OBSERVER.replace("'fault_reached':broken", "'fault_reached':False")
        (self.source/'observer.py').write_text(script)
        self.plan['observer']['source']['sha256']=sha(script.encode())
        (self.source/'policy.txt').write_text('detected')
        self.assertEqual(self.run_probe()['verdict'],'DETECTED')
    def test_reachability_must_name_single_edit(self):
        for value in (None, {'kind':'browser-binding','edit_path':'other.txt'}):
            self.plan['reachability']=value
            self.assertEqual(self.invoke()[0]['verdict'],'ERROR')
    def source_edits(self, name, source, pairs):
        (self.source/name).write_text(source)
        self.plan['reachability']['edit_path'] = name
        self.plan['edits'] = [{'path':name,'before':before,'after':after,
                               'sha256':sha(source.encode()),'kind':'source'}
                              for before,after in pairs]
        self.native(NATIVE.replace("'app.js'", repr(name)))
        observer = OBSERVER.replace("'app.js'", repr(name))
        (self.source/'observer.py').write_text(observer)
        self.plan['observer']['source']['sha256'] = sha(observer.encode())
    def detect_instrumented_fault(self, name):
        self.native(NATIVE.replace("'BROKEN' in (p/'app.js').read_text()",
                                   "'__e2e_probe_' in (p/" + repr(name) + ").read_text()"))
        observer = OBSERVER.replace("'BROKEN' in (p/'app.js').read_text()",
                                    "'__e2e_probe_' in (p/" + repr(name) + ").read_text()")
        (self.source/'observer.py').write_text(observer)
        self.plan['observer']['source']['sha256'] = sha(observer.encode())
    def test_jsx_event_handler_marks_invocation(self):
        self.source_edits('app.tsx', 'function App() { return <button onClick={() => WORKS()}>go</button>; }',
                          [('onClick={() => WORKS()}', 'onClick={() => BROKEN()}')])
        result = self.run_probe()
        self.assertEqual(result['verdict'], 'SURVIVED')
        fault = (Path(result['temporaryArtifactsRemaining'])/'fault/project/app.tsx').read_text()
        self.assertIn('...__probeArgs', fault)
        self.assertIn('return (() => BROKEN())(...__probeArgs)', fault)
        self.assertEqual((self.source/'app.tsx').read_text(), 'function App() { return <button onClick={() => WORKS()}>go</button>; }')
    def test_jsx_attribute_value_marks_evaluation(self):
        self.source_edits('app.tsx', 'function App() { return <button aria-label={"WORKS"}>go</button>; }',
                          [('{"WORKS"}', '{"BROKEN"}')])
        result = self.run_probe()
        self.assertEqual(result['verdict'], 'SURVIVED')
        fault = (Path(result['temporaryArtifactsRemaining'])/'fault/project/app.tsx').read_text()
        self.assertIn('(globalThis as any)[', fault)
        self.assertIn('("BROKEN")', fault)
    def test_contiguous_statement_range_restores_exact_bytes(self):
        source = 'function action() { const old = 1; WORKS(old); return old; }'
        self.source_edits('app.js',source,[('const old = 1; WORKS(old);', 'BROKEN();')])
        result = self.run_probe()
        self.assertEqual(result['verdict'], 'SURVIVED')
        self.assertEqual((self.source/'app.js').read_text(),source)
        fault = (Path(result['temporaryArtifactsRemaining'])/'fault/project/app.js').read_text()
        self.assertIn('BROKEN();',fault)
        self.assertNotIn('WORKS(old);',fault)
        self.assertIn('globalThis[',fault)
        self.assertNotIn('(globalThis as any)',fault)
    def test_typescript_marker_does_not_continue_semicolonless_statement(self):
        source = 'function action() {\n  const dispatch = () => 1\n  WORKS()\n}'
        self.source_edits('app.ts',source,[('WORKS()', 'BROKEN()')])
        result = self.run_probe()
        self.assertEqual(result['verdict'],'SURVIVED')
        fault = (Path(result['temporaryArtifactsRemaining'])/'fault/project/app.ts').read_text()
        self.assertIn('const dispatch = () => 1\n  ;(globalThis as any)[',fault)
        self.assertEqual((self.source/'app.ts').read_text(),source)
    def test_insert_statement_before_function_and_object_closers(self):
        source = 'const provider = { get: () => {\n  WORKS();\n  return 1;\n},\n};'
        self.source_edits('app.js',source,[('  WORKS();\n  return 1;\n},\n};',
                                            '  WORKS();\n  BROKEN();\n  return 1;\n},\n};')])
        result = self.run_probe()
        self.assertEqual(result['verdict'],'SURVIVED')
        self.assertEqual((self.source/'app.js').read_text(),source)
        self.assertIn('BROKEN();',(Path(result['temporaryArtifactsRemaining'])/'fault/project/app.js').read_text())
    def test_inserted_jsx_event_attribute_is_one_element_and_restored(self):
        source = 'function App() { return <Dialog aria-describedby={undefined} onInteractOutside={() => WORKS()} />; }'
        self.source_edits('app.tsx',source,[('aria-describedby={undefined} onInteractOutside',
                                             'aria-describedby={undefined} onEscapeKeyDown={(e) => BROKEN(e)} onInteractOutside')])
        result = self.run_probe()
        self.assertEqual(result['verdict'],'SURVIVED')
        self.assertEqual((self.source/'app.tsx').read_text(),source)
        fault = (Path(result['temporaryArtifactsRemaining'])/'fault/project/app.tsx').read_text()
        self.assertIn('onEscapeKeyDown=',fault)
        self.assertIn('...__probeArgs',fault)
    def test_import_specifier_removal_in_three_edit_set(self):
        source = ('import { add, keep } from "mod";\n'
                  'function App() {\n  const _add = () => add();\n'
                  '  function click() { _add(); WORKS(); }\n  return keep;\n}')
        self.source_edits('app.tsx',source,[
            ('import { add, keep } from "mod";', 'import { keep } from "mod";'),
            ('  const _add = () => add();\n',''),
            ('_add(); ','')])
        self.detect_instrumented_fault('app.tsx')
        result = self.run_probe()
        self.assertEqual(result['verdict'],'SURVIVED')
        self.assertEqual(result['phases']['fault']['reachability']['edits_reached'],[0,1,2])
        self.assertEqual((self.source/'app.tsx').read_text(),source)
        fault = (Path(result['temporaryArtifactsRemaining'])/'fault/project/app.tsx').read_text()
        self.assertIn('import { keep } from "mod";\n;(globalThis as any)[',fault)
    def test_refuse_import_module_or_whole_function_change(self):
        source = 'import { add, keep } from "mod";\nfunction App() { WORKS(); }'
        self.source_edits('app.tsx',source,[('import { add, keep } from "mod";',
                                            'import { keep } from "other";')])
        result,_ = self.invoke()
        self.assertEqual(result['verdict'],'ERROR')
        self.assertIn('exactly one named specifier',result['error'])
        self.source_edits('app.tsx',source,[('import { add, keep } from "mod";',
                                            'import { keep } from "mod";')])
        result,_ = self.invoke()
        self.assertEqual(result['verdict'],'ERROR')
        self.assertIn('same-file runtime edit',result['error'])
        self.source_edits('app.tsx',source,[('import { add, keep } from "mod";',
                                            'import { keep } from "mod" ;'),
                                           ('WORKS();','BROKEN();')])
        result,_ = self.invoke()
        self.assertEqual(result['verdict'],'ERROR')
        self.assertIn('exactly one named specifier',result['error'])
        self.source_edits('app.tsx',source,[('function App() { WORKS(); }',
                                            'function App() { BROKEN(); }')])
        result,_ = self.invoke()
        self.assertEqual(result['verdict'],'ERROR')
        self.assertIn('one function body',result['error'])
    def test_refuse_two_new_jsx_attributes_or_cross_element_change(self):
        source = 'function App() { return <Dialog a={1} b={2} />; }'
        self.source_edits('app.tsx',source,[('a={1} b={2}','a={1} c={3} d={4} b={2}')])
        result,_ = self.invoke()
        self.assertEqual(result['verdict'],'ERROR')
        self.assertIn('one JSX attribute',result['error'])
    def test_three_nonoverlapping_edits_are_applied_atomically(self):
        source = 'function action() { WORKS; MID; END; }'
        self.source_edits('app.js',source,[('WORKS;', 'BROKEN;'),('MID;', 'BROKEN2;'),('END;', 'BROKEN3;')])
        result = self.run_probe()
        self.assertEqual(result['verdict'], 'SURVIVED')
        self.assertEqual(result['phases']['fault']['reachability']['edits_reached'], [0,1,2])
        self.assertEqual((self.source/'app.js').read_text(),source)
        fault = (Path(result['temporaryArtifactsRemaining'])/'fault/project/app.js').read_text()
        self.assertTrue(all(part in fault for part in ('BROKEN;', 'BROKEN2;', 'BROKEN3;')))
    def test_overlapping_edits_refused(self):
        source = 'function action() { WORKS; MID; }'
        self.source_edits('app.js',source,[('WORKS; MID;', 'BROKEN;'),('MID;', 'BROKEN2;')])
        result,_ = self.invoke()
        self.assertEqual(result['verdict'], 'ERROR')
        self.assertIn('overlap', result['error'])
    def test_cross_file_edits_refused(self):
        (self.source/'other.js').write_text('function other() { WORKS; }')
        self.plan['edits'].append({'path':'other.js','before':'WORKS;','after':'BROKEN;',
                                   'sha256':sha((self.source/'other.js').read_bytes()),'kind':'source'})
        result,_ = self.invoke()
        self.assertEqual(result['verdict'], 'ERROR')
        self.assertIn('one file', result['error'])
    def test_unparsable_combined_edit_refused(self):
        self.plan['edits'][0]['after'] = 'BROKEN( ;'
        result,_ = self.invoke()
        self.assertEqual(result['verdict'], 'ERROR')
        self.assertIn('statement replacement', result['error'])
    def test_statement_replacement_cannot_escape_function(self):
        self.plan['edits'][0]['after'] = 'BROKEN; } function sneak() { WORKS;'
        result,_ = self.invoke()
        self.assertEqual(result['verdict'], 'ERROR')
        self.assertIn('one function body', result['error'])
    def test_otherfailure(self):
        (self.source/'policy.txt').write_text('other');self.assertEqual(self.run_probe()['verdict'],'CANNOT_VERIFY')
    def test_restoredfail(self):
        (self.source/'policy.txt').write_text('restoredfail');self.assertEqual(self.run_probe()['verdict'],'CANNOT_VERIFY')
    def test_missingobserver(self):
        del self.plan['observer'];self.assertEqual(self.invoke()[0]['verdict'],'ERROR')
    def test_noop(self):
        self.plan['edits'][0]['after']='WORKS;';self.assertEqual(self.invoke()[0]['verdict'],'ERROR')
    def test_traversal(self):
        self.plan['edits'][0]['path']='../app.js';self.assertEqual(self.invoke()[0]['verdict'],'ERROR')
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
        (self.source/'linked').symlink_to(self.source/'app.js');self.assertEqual(self.invoke()[0]['verdict'],'ERROR')
    def test_output_inside_source(self):
        path=self.root/'plan.json';path.write_text(json.dumps(self.plan))
        proc=subprocess.run([NODE,str(RUNNER),'--plan',str(path),'--output-dir',str(self.source/'out')],capture_output=True,text=True)
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
        self.plan['mode']='assertion-mutation';del self.plan['observer'];self.plan.pop('reachability',None)
        self.plan['edits']=[{'path':'test.spec.ts','before':'assert transfer','after':'assert impossible','sha256':sha(b'assert transfer'),'kind':'test'}]
        script=NATIVE.replace("fault='BROKEN' in (p/'app.js').read_text()", "fault=(p/'test.spec.ts').read_text()=='assert impossible'")
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
    def installed_probe(self):
        copied = self.root / 'installed' / 'run-probe.mjs'
        copied.parent.mkdir()
        for filename in PROBE_RUNTIME_FILES:
            (copied.parent / filename).write_bytes((RUNNER.parent / filename).read_bytes())
        parser = copied.parent / 'scanner/vendor/typescript/typescript.cjs'
        parser.parent.mkdir(parents=True)
        parser.write_bytes((RUNNER.parent / 'scanner/vendor/typescript/typescript.cjs').read_bytes())
        return copied
    def installed_invoke(self, copied, output, flags=()):
        planpath = self.root / 'installed-plan.json'
        planpath.write_text(json.dumps(self.plan))
        return subprocess.run([NODE, str(copied), '--plan', str(planpath), '--output-dir', str(output), *flags], capture_output=True, text=True, timeout=20)
    def test_installed_copy_selfcontained(self):
        copied = self.installed_probe()
        preview = self.installed_invoke(copied, self.root / 'installed-preview')
        self.assertEqual(preview.returncode, 0, preview.stderr)
        approval = json.loads(preview.stdout)['approval_sha256']
        run = self.installed_invoke(copied, self.root / 'installed-run', ['--execute', '--trust-checkout', '--approve-sha256', approval])
        self.assertEqual(run.returncode, 0, run.stderr)
        self.assertEqual(json.loads(run.stdout)['verdict'], 'SURVIVED')
    def test_installed_helper_tampering_invalidates_approval(self):
        copied = self.installed_probe()
        preview = self.installed_invoke(copied, self.root / 'installed-preview')
        self.assertEqual(preview.returncode, 0, preview.stderr)
        approval = json.loads(preview.stdout)['approval_sha256']
        for filename in PROBE_RUNTIME_FILES[1:]:
            with self.subTest(helper=filename):
                helper = copied.parent / filename
                original = helper.read_bytes()
                helper.write_bytes(original + b'\n// changed after approval\n')
                try:
                    out = self.root / ('tampered-' + filename)
                    run = self.installed_invoke(copied, out, ['--execute', '--trust-checkout', '--approve-sha256', approval])
                    self.assertEqual(run.returncode, 2, run.stderr)
                    packet = json.loads(run.stdout)
                    self.assertEqual(packet['verdict'], 'ERROR')
                    self.assertIn('stale or missing approval digest', packet['error'])
                    self.assertFalse((out / 'normal').exists())
                finally:
                    helper.write_bytes(original)
    def test_installed_missing_helper_refuses_before_phase_execution(self):
        copied = self.installed_probe()
        for filename in PROBE_RUNTIME_FILES[1:]:
            with self.subTest(helper=filename):
                helper = copied.parent / filename
                original = helper.read_bytes()
                helper.unlink()
                try:
                    out = self.root / ('missing-' + filename)
                    run = self.installed_invoke(copied, out)
                    self.assertNotEqual(run.returncode, 0)
                    self.assertIn(filename, run.stderr + run.stdout)
                    self.assertFalse((out / 'normal').exists())
                finally:
                    helper.write_bytes(original)
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
        run=subprocess.run([NODE,str(RUNNER),'--plan',str(planpath),'--output-dir',output],capture_output=True,text=True)
        self.assertEqual(json.loads(run.stdout)['verdict'],'ERROR');self.assertFalse((self.source/'artifact').exists())
    def test_wrapper_mutation_rejected(self):
        self.plan['edits']=[{'path':'native.py','before':'unrelated failure','after':'different failure','sha256':sha(NATIVE.encode()),'kind':'source'}]
        self.assertEqual(self.invoke()[0]['verdict'],'ERROR')
    def test_static_evidence_rejected(self):
        script=OBSERVER.replace("'path':'observed.json','sha256':hashlib.sha256(e.read_bytes()).hexdigest()", "'path':'README.md','sha256':hashlib.sha256((p/'README.md').read_bytes()).hexdigest()")
        (self.source/'observer.py').write_text(script);self.plan['observer']['source']['sha256']=sha(script.encode())
        self.assertEqual(self.run_probe()['verdict'],'CANNOT_VERIFY')
    def test_playwright_report_guards(self):
        module = NodeRunner()
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
        module = NodeRunner()
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
        module = NodeRunner()
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

    def test_runtime_followup_requires_explicit_opt_in(self):
        skill = (RUNNER.parent.parent / 'references/runtime-probes.md').read_text()
        self.assertIn('Only when the user explicitly requests runtime proof in addition to a static review', skill)
        self.assertIn('offer source-backed mutation or app-fault probes for material uncertainties', skill)
        self.assertIn('With one candidate, offer one probe; with several, offer them as one bounded batch', skill)
        self.assertIn('Collect candidates from every reported uncertainty a probe could settle', skill)
        self.assertIn('propose one representative probe, the highest-ranked, and list the rest as not run, same change as that probe, outside the cap and the approval; its verdict does not transfer to them', skill)
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

    def test_batch_is_gated_capped_and_reported_per_probe(self):
        self.assertIn('Each probe is one test and one change.', self.guidance)
        self.assertIn('never merges changes into one run', self.guidance)
        self.assertIn('A test title alone, a clean test, or a static-only request yields no candidate', self.guidance)
        self.assertIn('probe-count cap (default 10) and a wall-clock cap before approval', self.guidance)
        self.assertIn('One approval covers exactly that list.', self.guidance)
        self.assertIn('A setup failure there stops the batch', self.guidance)
        self.assertIn('never in parallel against a shared app or database', self.guidance)
        self.assertIn('one row per planned probe', self.guidance)
        self.assertIn('never summed into a test-suite adequacy score', self.guidance)
        self.assertIn('A V3 question whose promise source is missing stays out of the batch', self.guidance)
        skill = (RUNNER.parent.parent / 'references/runtime-probes.md').read_text()
        self.assertIn('say the first probe gates the rest', skill)
        self.assertIn('A V3 candidate without a sourced promise stays out of the batch.', skill)

    def test_host_sandbox_and_timeouts_are_not_test_results(self):
        self.assertIn('`bootstrap_check_in` and `Permission denied (1100)`', self.guidance)
        self.assertIn('It is a setup failure, not a test result', self.guidance)
        self.assertIn('The executor never admits a skip, interruption or test timeout as a linked failure.', self.guidance)
        self.assertIn('leave it out of the execution packet, never use it as the gate probe', self.guidance)
        self.assertIn('not as a catalog finding or a Phase 3 coverage gap', self.guidance)
        self.assertIn('Escalation is a new approval', self.guidance)

if __name__=='__main__':unittest.main()
