#!/usr/bin/env node
// SPDX-License-Identifier: Apache-2.0
// Manifest v1: copies isolate phases, not execution or host/network access.
import fs from 'node:fs';
import path from 'node:path';
import os from 'node:os';
import { createHash } from 'node:crypto';
import { spawn } from 'node:child_process';
import { fileURLToPath } from 'node:url';

const SELF = fileURLToPath(import.meta.url);
const EXCLUDED = new Set(['.git','node_modules','reports','playwright-report','test-results','.cache','cache','__pycache__','.parcel-cache']);
const ENV_KEYS = ['HOME','PATH','LANG','LC_ALL','USER','LOGNAME','TMPDIR','TEMP','TMP','SystemRoot'];
export const LIMITATION = 'Fresh phase copies are not a sandbox. Trusted commands can access the host and network. Explicit dependency symlinks are read-only by convention, not enforced by this runner.';
const require = (ok, message) => { if (!ok) throw new Error(message); };
const digest = data => createHash('sha256').update(data).digest('hex');
const readText = filename => new TextDecoder('utf-8', {fatal:true,ignoreBOM:true}).decode(fs.readFileSync(filename));
const object = value => value !== null && typeof value === 'object' && !Array.isArray(value);
// Stable, ASCII JSON is used for approval/source digests. Runner bytes intentionally
// invalidate approvals issued to any other runner, including the former Python one.
function canonical(value) {
  const ordered = value => Array.isArray(value) ? value.map(ordered) : object(value) ? Object.fromEntries(Object.keys(value).sort().map(k => [k, ordered(value[k])])) : value;
  return JSON.stringify(ordered(value)).replace(/[\u007f-\uffff]/g, ch => `\\u${ch.charCodeAt(0).toString(16).padStart(4,'0')}`);
}
const environment = () => Object.fromEntries(ENV_KEYS.filter(k => process.env[k] !== undefined).map(k => [k, process.env[k]]));
const exists = name => { try { fs.lstatSync(name); return true; } catch (e) { if (e.code === 'ENOENT' || e.code === 'ENOTDIR') return false; throw e; } };
const inside = (child, parent) => { const rel = path.relative(parent, child); return rel === '' || (!path.isAbsolute(rel) && rel !== '..' && !rel.startsWith('..' + path.sep)); };
function noSymlinks(filename) {
  for (let current = filename; ; current = path.dirname(current)) {
    if (exists(current)) require(!fs.lstatSync(current).isSymbolicLink(), 'symlink path forbidden: ' + filename);
    if (current === path.dirname(current)) break;
  }
}
function absolute(value) {
  require(typeof value === 'string' && value.length > 0, 'invalid absolute path');
  require(!value.split(path.sep).includes('..'), 'absolute path contains traversal');
  const expanded = value === '~' ? os.homedir() : value.startsWith('~/') ? path.join(os.homedir(), value.slice(2)) : value;
  const result = path.resolve(expanded); noSymlinks(result); return result;
}
function relative(value) {
  require(typeof value === 'string' && value && !value.includes('\\'), 'invalid relative path');
  require(!path.posix.isAbsolute(value) && value.split('/').every(p => p && p !== '.' && p !== '..'), 'path traversal');
  require(!value.split('/').some(p => EXCLUDED.has(p)), 'path enters excluded directory'); return value;
}
function keys(value, allowed, required = []) {
  require(object(value) && Object.keys(value).every(k => allowed.includes(k)), 'unexpected manifest keys');
  require(required.every(k => Object.hasOwn(value,k)), 'missing manifest keys');
}
function tree(root) {
  noSymlinks(root); require(fs.statSync(root).isDirectory(), 'source must be a directory'); const files = Object.create(null);
  function visit(base) {
    for (const name of fs.readdirSync(base).sort()) {
      const filename = path.join(base,name), stat = fs.lstatSync(filename);
      // Excluded mounts may themselves be symlinks, but are never followed.
      if (EXCLUDED.has(name) && (stat.isDirectory() || (stat.isSymbolicLink() && fs.statSync(filename, {throwIfNoEntry:false})?.isDirectory()))) continue;
      require(!stat.isSymbolicLink(), 'included symlink forbidden: ' + filename);
      if (stat.isDirectory()) { visit(filename); continue; }
      require(stat.isFile(), 'special file forbidden: ' + filename);
      files[path.relative(root,filename).split(path.sep).join('/')] = {sha256:digest(fs.readFileSync(filename)),mode:stat.mode & 0o7777};
    }
  }
  visit(root); return files;
}
function command(config) {
  keys(config,['argv','timeout_seconds','source'],['argv']);
  require(Array.isArray(config.argv) && config.argv.length && config.argv.every(a => typeof a === 'string' && a && !a.includes('\0')), 'argv must be nonempty strings');
  const timeout = config.timeout_seconds ?? 120; require(Number.isInteger(timeout) && timeout >= 1 && timeout <= 300,'timeout must be 1..300 seconds');
}
export function prepare(plan) {
  keys(plan,['version','source','test_selector','test_paths','mode','promise','edits','test','observer','report','expected_failure','dependency_dirs'],['version','source','test_selector','test_paths','mode','promise','edits','test','report','expected_failure']);
  require(plan.version === 1,'manifest version must be 1'); require(['behavior-fault','assertion-mutation'].includes(plan.mode),'unknown mode');
  const source = absolute(plan.source), files = tree(source);
  require(typeof plan.test_selector === 'string' && plan.test_selector,'test_selector required');
  require(Array.isArray(plan.test_paths),'test_paths must name included tests');
  const tests = new Set(plan.test_paths.map(relative)); require(tests.size && [...tests].every(p => Object.hasOwn(files,p)),'test_paths must name included tests');
  keys(plan.promise,['path','quote','sha256'],['path','quote','sha256']); const p = relative(plan.promise.path);
  require(Object.hasOwn(files,p) && files[p].sha256 === plan.promise.sha256,'promise source hash mismatch');
  require(typeof plan.promise.quote === 'string' && plan.promise.quote && readText(path.join(source,p)).includes(plan.promise.quote),'promise quote absent');
  require(Array.isArray(plan.edits) && plan.edits.length,'edits required'); const seen = new Set();
  for (const edit of plan.edits) {
    keys(edit,['path','before','after','sha256','kind'],['path','before','after','sha256','kind']); const p = relative(edit.path);
    require(!seen.has(p) && Object.hasOwn(files,p),'edit path absent or repeated'); seen.add(p);
    require(edit.sha256 === files[p].sha256,'edit source hash mismatch');
    require(typeof edit.before === 'string' && edit.before && typeof edit.after === 'string','edit text required'); require(edit.before !== edit.after,'noop edit');
    const data = fs.readFileSync(path.join(source,p)), before = Buffer.from(edit.before), first = data.indexOf(before);
    require(first >= 0 && data.indexOf(before,first + before.length) < 0,'edit must match exactly once');
    const kind = tests.has(p) ? 'test' : 'source'; require(edit.kind === kind,'edit kind contradicts test_paths'); require(kind === (plan.mode === 'behavior-fault' ? 'source' : 'test'),'edit forbidden in this mode');
  }
  for (const label of ['test','observer']) {
    if (plan[label] == null) continue; command(plan[label]); const pinned = plan[label].source; keys(pinned,['path','sha256'],['path','sha256']); const script = relative(pinned.path);
    require(Object.hasOwn(files,script) && files[script].sha256 === pinned.sha256,label + ' source hash mismatch'); require(!seen.has(script),label + ' wrapper cannot be mutated');
    require(plan[label].argv.some(a => a === script || a === '{project}/' + script),label + ' argv must reference pinned source script');
  }
  require(plan.mode !== 'behavior-fault' || plan.observer != null,'V3 observer required');
  keys(plan.report,['format','path'],['format','path']); require(['playwright-json','cypress-json'].includes(plan.report.format),'unsupported report format'); const report = relative(plan.report.path); require(!Object.hasOwn(files,report),'report path must be fresh');
  keys(plan.expected_failure,['contains','location'],['contains','location']); require(['contains','location'].every(k => typeof plan.expected_failure[k] === 'string' && plan.expected_failure[k]),'linked failure string and location required');
  const deps = []; require(plan.dependency_dirs === undefined || Array.isArray(plan.dependency_dirs),'invalid dependency directories');
  for (const dep of plan.dependency_dirs ?? []) {
    keys(dep,['path','target'],['path','target']); require(typeof dep.path === 'string','invalid dependency path'); const p = dep.path; relative(p.replaceAll('node_modules','_dependencies'));
    require(p.split('/').filter(p => p === 'node_modules').length === 1 && p.endsWith('node_modules'),'dependency path must end in node_modules');
    require(!deps.some(([d]) => p === d || p.startsWith(d + '/') || d.startsWith(p + '/')),'overlapping dependencies'); const target = absolute(dep.target);
    require(fs.statSync(target).isDirectory(),'dependency target missing'); require(!inside(target,source),'dependency target must be outside source'); require(!exists(path.join(source,p)) || !fs.statSync(path.join(source,p)).isFile(),'dependency target collision'); deps.push([p,target]);
  }
  const payload = {plan,source_files:files,runner_sha256:digest(fs.readFileSync(SELF)),effective_environment:environment()};
  return {source,files,deps,approval:digest(canonical(payload))};
}
function reportRoot(report,project) {
  const value = report.config?.rootDir ?? project; require(typeof value === 'string' && value,'invalid Playwright rootDir'); require(!value.split(path.sep).includes('..'),'Playwright rootDir traversal'); const root = absolute(path.isAbsolute(value) ? value : path.join(project,value)); require(inside(root,project) && fs.statSync(root).isDirectory(),'Playwright rootDir outside phase project or absent'); return root;
}
export function parseNative(report,format,selector,testPaths,project) {
  const tests = [], root = format === 'playwright-json' ? reportRoot(report,project) : project;
  function specPath(value) {
    require(typeof value === 'string' && value,'reported spec path absent'); require(!value.split(path.sep).includes('..'),'reported spec path traversal'); const candidate = path.isAbsolute(value) ? value : path.join(root,value); noSymlinks(candidate);
    require(inside(candidate,project),'reported spec outside phase project'); const name = path.relative(project,candidate).split(path.sep).join('/'); require(exists(candidate) && fs.statSync(candidate).isFile() && testPaths.includes(name),'reported spec not in test_paths or absent');
  }
  function errorText(value) {
    if (typeof value === 'string') return value; require(object(value),'invalid native error'); let text = ['message','stack','value','snippet'].map(k => String(value[k] ?? '')).join('\n'); if (object(value.location)) text += '\n' + ['file','line','column'].map(k => String(value.location[k] ?? '')).join(':'); return text;
  }
  const empty = value => value == null || value === false || value === '' || (Array.isArray(value) && !value.length) || (object(value) && !Object.keys(value).length);
  if (format === 'playwright-json') {
    require(empty(report.errors),'Playwright global errors'); require(report.config?.workers === 1,'Playwright workers must be one'); for (const cfg of report.config?.projects ?? []) require((cfg.retries ?? 0) === 0,'Playwright retries must be zero');
    function visit(suite) { for (const spec of suite.specs ?? []) for (const test of spec.tests ?? []) tests.push([spec,test]); for (const child of suite.suites ?? []) visit(child); }
    for (const suite of report.suites ?? []) visit(suite); require(tests.length === 1,'report must contain exactly one test'); const [spec,test] = tests[0]; specPath(spec.file); require(spec.title === selector,'selected title mismatch'); require((test.expectedStatus ?? 'passed') === 'passed','expected failure/skipped test forbidden');
    const attempts = test.results ?? []; require(attempts.length === 1 && (attempts[0].retry ?? 0) === 0,'report must contain one nonretry attempt'); const outcome = attempts[0], status = outcome.status;
    require(['passed','failed'].includes(status),'skip/interruption/timeout not admitted'); const aggregate = status === 'passed' ? 'expected' : 'unexpected'; require((test.status ?? aggregate) === aggregate,'inconsistent aggregate test status');
    if (report.stats != null) require(Object.entries({expected:Number(status === 'passed'),unexpected:Number(status === 'failed'),flaky:0,skipped:0}).every(([k,v]) => report.stats[k] === v),'inconsistent Playwright stats');
    let errors = outcome.errors ?? []; require(Array.isArray(errors),'invalid Playwright errors'); if (!empty(outcome.error)) errors = [...errors,outcome.error]; require(status !== 'passed' || !errors.length,'passed attempt contains errors'); return [status,errors.map(errorText)];
  }
  require(empty(report.errors) && empty(report.failures) && (report.status ?? 'finished') === 'finished','Cypress top-level error'); const runs = report.runs ?? []; require(runs.length === 1,'exactly one Cypress run required'); const run = runs[0]; require(empty(run.error) && empty(run.errors),'Cypress run/hook error'); specPath(run.spec?.relative);
  const selected = run.tests ?? []; require(selected.length === 1 && report.totalTests === 1,'report must contain exactly one Cypress test'); const test = selected[0]; require(Array.isArray(test.title) && test.title.at(-1) === selector,'selected title mismatch'); require(report.totalPending === 0 && report.totalSkipped === 0,'skipped/pending Cypress test'); const attempts = test.attempts ?? []; require(attempts.length === 1,'report must contain one attempt'); const status = test.state; require(['passed','failed'].includes(status) && attempts[0].state === status,'invalid Cypress outcome');
  require(report.totalPassed === Number(status === 'passed') && report.totalFailed === Number(status === 'failed'),'inconsistent Cypress counts'); if (run.stats != null) require(Object.entries({tests:1,passes:Number(status === 'passed'),failures:Number(status === 'failed'),pending:0,skipped:0}).every(([k,v]) => run.stats[k] === v),'inconsistent Cypress run stats'); const errors = [test.displayError,attempts[0].error].filter(e => !empty(e)).map(errorText); require(status !== 'passed' || !errors.length,'passed Cypress test contains errors'); return [status,errors];
}
export async function runCommand(config,project,phase,report,out) {
  const substitutions = {'{project}':project,'{phase}':phase,'{report}':report,'{selector}':config._selector}; const argv = config.argv.map(arg => Object.entries(substitutions).reduce((arg,[old,value]) => arg.replaceAll(old,() => value),arg)); const env = {...environment(),CI:'1',CYPRESS_retries:'0',E2E_PROBE_PHASE:phase,E2E_PROBE_REPORT:report,E2E_PROBE_SELECTOR:config._selector,E2E_PROBE_WORKERS:'1',E2E_PROBE_RETRIES:'0'};
  const receipt = {argv,cwd:project,environment_names:Object.keys(env).sort()}, stdout = fs.openSync(path.join(out,'stdout.txt'),'wx'), stderr = fs.openSync(path.join(out,'stderr.txt'),'wx');
  try {
    await new Promise((resolve,reject) => {
      const child = spawn(argv[0],argv.slice(1),{cwd:project,env,stdio:['ignore',stdout,stderr],detached:process.platform !== 'win32'}); let timer, timedOut = false, cleanupSent = false;
      function cleanup() {
        if (cleanupSent || !child.pid) return;
        try {
          if (process.platform !== 'win32') {
            process.kill(-child.pid,'SIGKILL');
            receipt.owned_process_group_cleanup = true;
            cleanupSent = true;
          } else cleanupSent = child.kill('SIGKILL');
        } catch (e) {
          if (e.code !== 'ESRCH') throw e;
          receipt.owned_process_group_cleanup ??= 'already exited';
          cleanupSent = true;
        }
      }
      child.once('error',error => { clearTimeout(timer); reject(error); });
      child.once('exit',(code,signal) => { clearTimeout(timer); receipt.exit_code = timedOut ? null : code ?? -1; if (timedOut) receipt.timeout = true; if (signal && !timedOut) receipt.signal = signal; try { cleanup(); resolve(); } catch (e) { reject(e); } });
      timer = setTimeout(() => { timedOut = true; try { cleanup(); } catch (e) { reject(e); } },(config.timeout_seconds ?? 120) * 1000);
    });
  } finally { fs.closeSync(stdout); fs.closeSync(stderr); }
  writeJson(path.join(out,'command.json'),receipt); return receipt;
}
function writeJson(filename,value) { fs.writeFileSync(filename,JSON.stringify(value,null,2) + '\n'); }
export async function execute(plan,{source,files,deps},output) {
  const phases = {}; let error = null, afterDigest = null; const beforeDigest = digest(canonical(files));
  try {
    for (const phase of ['normal','fault','restored']) {
      const folder = path.join(output,phase), project = path.join(folder,'project'); fs.mkdirSync(project,{recursive:true});
      for (const [name,info] of Object.entries(files)) { const dest = path.join(project,name); fs.mkdirSync(path.dirname(dest),{recursive:true}); const data = fs.readFileSync(path.join(source,name)); require(digest(data) === info.sha256,'source changed during copy'); fs.writeFileSync(dest,data); fs.chmodSync(dest,info.mode); }
      for (const [name,target] of deps) { const dest = path.join(project,name); fs.mkdirSync(path.dirname(dest),{recursive:true}); fs.symlinkSync(target,dest,'dir'); }
      const expected = Object.fromEntries(Object.entries(files).map(([name,info]) => [name,info.sha256]));
      if (phase === 'fault') for (const edit of plan.edits) { const dest = path.join(project,edit.path), data = fs.readFileSync(dest), before = Buffer.from(edit.before), index = data.indexOf(before); fs.writeFileSync(dest,Buffer.concat([data.subarray(0,index),Buffer.from(edit.after),data.subarray(index + before.length)])); expected[edit.path] = digest(fs.readFileSync(dest)); }
      const report = path.join(project,plan.report.path); fs.mkdirSync(path.dirname(report),{recursive:true}); const testDir = path.join(folder,'test'); fs.mkdirSync(testDir); const native = await runCommand({...plan.test,_selector:plan.test_selector},project,phase,report,testDir); noSymlinks(report); require(exists(report) && fs.statSync(report).isFile(),'native report missing'); const nativeReport = JSON.parse(readText(report)); const [status,errors] = parseNative(nativeReport,plan.report.format,plan.test_selector,plan.test_paths,project); require(native.exit_code === (status === 'passed' ? 0 : 1),'native exit/report mismatch'); const item = {native:status,errors,report_sha256:digest(fs.readFileSync(report)),source_files:expected};
      if (plan.report.format === 'playwright-json') item.report_rootDir_resolved = reportRoot(nativeReport,project); phases[phase] = item;
      if (plan.observer) { const observerDir = path.join(folder,'observer'); fs.mkdirSync(observerDir); const observed = await runCommand({...plan.observer,_selector:plan.test_selector},project,phase,report,observerDir); require(observed.exit_code === 0,'observer command failed'); const observation = JSON.parse(readText(path.join(observerDir,'stdout.txt'))); require(typeof observation.promised_effect === 'boolean' && typeof observation.fault_reached === 'boolean','invalid observer booleans'); require(observation.project === project,'observer phase provenance mismatch'); require(Array.isArray(observation.evidence) && observation.evidence.length,'observer requires actual evidence files');
        for (const entry of observation.evidence) { keys(entry,['path','sha256'],['path','sha256']); const name = relative(entry.path); require(!Object.hasOwn(files,name) && name !== plan.report.path,'observer evidence must be a fresh observation artifact'); const filename = path.join(project,name); noSymlinks(filename); require(exists(filename) && fs.statSync(filename).isFile() && digest(fs.readFileSync(filename)) === entry.sha256,'observer evidence missing or hash mismatch'); } item.observer = observation;
      }
      for (const [name,wanted] of Object.entries(expected)) { const filename = path.join(project,name); noSymlinks(filename); require(digest(fs.readFileSync(filename)) === wanted,'phase source/test changed: ' + name); require((fs.statSync(filename).mode & 0o7777) === files[name].mode,'phase source mode changed: ' + name); }
      require(canonical(tree(source)) === canonical(files),'original source changed');
    }
  } catch (e) { error = e.message; }
  finally { try { const after = tree(source); afterDigest = digest(canonical(after)); require(canonical(after) === canonical(files),'original source changed'); } catch (e) { error = e.message; } }
  let verdict = 'CANNOT_VERIFY', linked = false;
  if (error === null && Object.keys(phases).length === 3) {
    let baseline = ['normal','restored'].every(p => phases[p].native === 'passed'); if (plan.observer) baseline &&= ['normal','restored'].every(p => phases[p].observer.promised_effect); const fault = phases.fault;
    linked = fault.native === 'failed' && fault.errors.some(text => Object.values(plan.expected_failure).every(s => text.includes(s)));
    if (baseline) { if (plan.mode === 'assertion-mutation') { if (linked) verdict = 'ASSERTION_SENSITIVE'; } else if (fault.observer.fault_reached && !fault.observer.promised_effect) { if (linked) verdict = 'DETECTED'; else if (fault.native === 'passed') verdict = 'SURVIVED'; } }
  }
  if (verdict === 'CANNOT_VERIFY' && error === null) {
    const reasons = []; for (const phase of ['normal','restored']) { if (phases[phase].native !== 'passed') reasons.push(phase + ' native baseline did not pass'); if (plan.observer && !phases[phase].observer.promised_effect) reasons.push(phase + ' promised effect absent'); }
    if (plan.mode === 'behavior-fault') { if (!phases.fault.observer.fault_reached) reasons.push('fault was not reached'); if (phases.fault.observer.promised_effect) reasons.push('fault wrong state was not observed'); }
    if (phases.fault.native === 'failed' && !linked) reasons.push('fault failure did not link string and location in the same error'); if (plan.mode === 'assertion-mutation' && !linked) reasons.push('assertion mutation produced no linked failure'); error = reasons.join('; ') || 'incomplete three-phase evidence';
  }
  return {verdict,error,phases,limitation:LIMITATION,source_before_sha256:beforeDigest,source_after_sha256:afterDigest,original_source_unchanged:beforeDigest === afterDigest,behavior_proof:plan.mode === 'behavior-fault' && ['SURVIVED','DETECTED'].includes(verdict)};
}
export async function main(argv = process.argv.slice(2)) {
  if (argv.length === 1 && ['--help','-h'].includes(argv[0])) { console.log('Usage: node run-probe.mjs --plan manifest.json --output-dir /fresh/output [--preview | --execute --trust-checkout --approve-sha256 DIGEST]\n' + LIMITATION); return 0; }
  let result = {verdict:'ERROR',limitation:LIMITATION}, output, source, plan, ownsOutput = false;
  try {
    const options = {}; for (let i = 0; i < argv.length; i++) { const flag = argv[i]; require(['--plan','--output-dir','--approve-sha256','--preview','--execute','--trust-checkout'].includes(flag),'unknown argument: ' + flag); require(!Object.hasOwn(options,flag),'duplicate argument: ' + flag); if (['--plan','--output-dir','--approve-sha256'].includes(flag)) { require(i + 1 < argv.length && !argv[i + 1].startsWith('--'),'missing value: ' + flag); options[flag] = argv[++i]; } else options[flag] = true; }
    require(options['--plan'] && options['--output-dir'],'--plan and --output-dir required'); require(!(options['--preview'] && options['--execute']),'choose preview or execute'); plan = JSON.parse(readText(options['--plan'])); const prepared = prepare(plan); source = prepared.source; output = absolute(options['--output-dir']); require(!exists(output) && !inside(output,source) && !inside(source,output),'output must be fresh and outside source');
    if (options['--execute']) { require(options['--trust-checkout'],'--trust-checkout required before command execution'); require(options['--approve-sha256'] === prepared.approval,'stale or missing approval digest'); }
    fs.mkdirSync(path.dirname(output),{recursive:true}); fs.mkdirSync(output); ownsOutput = true; writeJson(path.join(output,'preview.json'),{plan,source_files:prepared.files,approval_sha256:prepared.approval,runner_sha256:digest(fs.readFileSync(SELF)),effective_environment:environment(),limitation:LIMITATION});
    if (options['--execute']) { require(prepare(plan).approval === prepared.approval,'source changed since approval check'); result = await execute(plan,prepared,output); } else result = {verdict:'PREVIEW',approval_sha256:prepared.approval,limitation:LIMITATION,commands_executed:0};
  } catch (e) { result.error = e.message; }
  result.candidate = {source:source ?? null,selector:object(plan) ? plan.test_selector ?? null : null}; result.runner = {sha256:digest(fs.readFileSync(SELF)),execution:'trusted local subprocesses; no sandbox'}; result.sourceUnchanged = result.original_source_unchanged ?? null; result.temporaryArtifactsRemaining = output && exists(output) ? output : null;
  result.verification = Object.fromEntries(['V1','V2','V3','V4','V5','V6'].map(key => [key,{verdict:'CANNOT_VERIFY',reason:'Not established by this bounded probe'}]));
  if (result.verdict === 'ASSERTION_SENSITIVE') result.verification.V2 = {verdict:'PASS',reason:'Normal/recovery pass and exact assertion mutation produces linked failure; no behavior proof'};
  else if (['DETECTED','SURVIVED'].includes(result.verdict)) result.verification.V3 = {verdict:result.verdict === 'DETECTED' ? 'PASS' : 'FAIL',reason:'Promised fault reached with wrong state; selected test ' + (result.verdict === 'DETECTED' ? 'detected linked assertion failure' : 'survived')};
  if (ownsOutput) writeJson(path.join(output,'result.json'),result); console.log(JSON.stringify(result,null,2)); return ['PREVIEW','DETECTED','SURVIVED','ASSERTION_SENSITIVE'].includes(result.verdict) ? 0 : 2;
}
// Resolve both sides: manual skill installs may expose a symlinked directory.
// Imports from -e or an unrelated entry point must remain side-effect free.
function isMain() {
  if (!process.argv[1]) return false;
  try { return fs.realpathSync(process.argv[1]) === fs.realpathSync(SELF); }
  catch { return false; }
}
if (isMain()) process.exitCode = await main();
