#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""One preregistered authored generator comparison; fixed faults, no repairs."""
import argparse
import hashlib
import json
import os
import re
from pathlib import Path
import signal
import shutil
from collections import Counter
import socket
import subprocess
import sys
import time
import urllib.request

ROOT = Path(__file__).resolve().parents[3]
APP = r'''import http from 'node:http';
let mode='normal', items={Alpha:3,Beta:7}, requests=[];
const html=`<!doctype html><title>Two counters</title><h1>Two counters</h1>
<section aria-label="Alpha"><h2>Alpha</h2><output aria-label="Alpha count"></output><button>Increment Alpha</button></section>
<section aria-label="Beta"><h2>Beta</h2><output aria-label="Beta count"></output><button>Increment Beta</button></section>
<script>
async function load(){const state=await (await fetch('/api/items')).json();for(const name of ['Alpha','Beta'])document.querySelector('[aria-label="'+name+' count"]').textContent=state[name];}
for(const name of ['Alpha','Beta'])document.querySelector('[aria-label="'+name+'"] button').onclick=async()=>{const output=document.querySelector('[aria-label="'+name+' count"]');output.textContent=Number(output.textContent)+1;await fetch('/api/items/'+name,{method:'POST'});};load();
</script>`;
http.createServer((req,res)=>{
 const url=new URL(req.url,'http://127.0.0.1');
 if(url.pathname==='/__control'){mode=url.searchParams.get('mode')||'normal';items={Alpha:3,Beta:7};requests=[];res.end('reset');return;}
 if(url.pathname==='/__witness'){res.setHeader('Content-Type','application/json');res.end(JSON.stringify({mode,items,requests}));return;}
 if(url.pathname==='/api/items'){res.setHeader('Content-Type','application/json');res.end(JSON.stringify(items));return;}
 if(req.method==='POST'&&url.pathname.startsWith('/api/items/')){const name=decodeURIComponent(url.pathname.split('/').pop());requests.push({name,mode,before:{...items}});if(mode==='wrong-item-update')items[name==='Alpha'?'Beta':'Alpha']++;else if(mode!=='omit-write')items[name]++;requests.at(-1).after={...items};res.end('{}');return;}
 if(url.pathname==='/'){res.setHeader('Content-Type','text/html');res.end(html);return;}res.statusCode=404;res.end();
}).listen(Number(process.argv[2]),'127.0.0.1');
'''
CANDIDATE = '''# Candidate four rule groups
- Prefer semantic locators with observed accessible names, labels, test IDs or text. Scope repeated elements meaningfully; justify positional disambiguation.
- Await actions and retrying observable assertions. Reject vacuous checks and assert the promised outcome, not object truthiness or styling.
- When an operation has an explicit ownership or filtering boundary, verify an unaffected witness outside it remains unchanged.
- Wait for observable conditions; never use sleeps or waitForTimeout.
'''
ARMS=('official-only','official+current-12','official+candidate-4')
MODES=('normal','omit-write','wrong-item-update','restored')

def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def write(p,data):p.write_text(json.dumps(data,indent=2)+'\n')
def get(url):
    with urllib.request.urlopen(url,timeout=3) as r:return r.read().decode()
def stop(p):
    if p.poll() is None:
        os.killpg(p.pid,signal.SIGTERM)
        try:p.wait(timeout=5)
        except subprocess.TimeoutExpired:os.killpg(p.pid,signal.SIGKILL);p.wait(timeout=5)

def load_machine(config_path):
    data=json.loads(config_path.read_text())
    fields={'setup_template','modules','node','codex','sessions_directory'}
    if set(data)!=fields:raise ValueError('machine config requires exactly '+', '.join(sorted(fields)))
    resolved={}
    for name,value in data.items():
        path=Path(value)
        if not path.is_absolute():raise ValueError('absolute machine path required: '+name)
        resolved[name]=str(path.resolve(strict=True))
    return resolved

def prepare(directory, machine_config):
    machine=load_machine(machine_config)
    directory=directory.expanduser().absolute()
    if directory.exists() or directory.is_relative_to(ROOT):raise ValueError('fresh external directory required')
    for p in directory.parents:
        if p.is_symlink():raise ValueError('symlink ancestor')
    directory.mkdir(parents=True)
    rules=ROOT/'skills/playwright-test-generator/thin-rules.md'
    if sha(rules)!='4dff3e824f42681e99b0673b6ed22be99885863d1605bacf7246b57ccec6a798':raise ValueError('current12 drift')
    (directory/'current-12.md').write_bytes(rules.read_bytes());(directory/'candidate-4.md').write_text(CANDIDATE)
    template=Path(machine['setup_template'])
    source=json.loads(template.read_text()); old=source['model_command'][source['model_command'].index('-C')+1]
    cells=[]
    for arm in ARMS:
        cell=directory/arm;cell.mkdir();project=cell/'project'
        cmd=[sys.executable,str(Path(__file__).with_name('prepare.py')),'--output',str(cell/'prepared'),'--modules',machine['modules'],'--node',machine['node'],'--codex',machine['codex']]
        subprocess.run(cmd,check=True,capture_output=True,text=True)
        project=cell/'prepared/project';(project/'app.mjs').write_text(APP)
        with socket.socket() as s:s.bind(('127.0.0.1',0));port=s.getsockname()[1]
        origin='http://127.0.0.1:'+str(port)
        requirement=f'''# Counter ownership and persistence\n\n**Seed:** tests/seed.spec.ts\n\n## Increment Alpha without changing Beta\n\n1. Navigate to {origin}.\n2. Confirm Alpha count is 3 and Beta count is 7.\n3. Click Increment Alpha once.\n4. Confirm Alpha is 4 and Beta remains 7.\n5. Reload the page. Confirm Alpha is still 4 and Beta is still 7.\n\nGenerate exactly tests/counter-persistence.spec.ts containing one test.\n'''
        (project/'specs/comparison-plan.md').write_text(requirement)
        appendix='' if arm=='official-only' else (directory/('current-12.md' if arm=='official+current-12' else 'candidate-4.md')).read_text()
        prompt=f'''Perform one bounded generation task using exactly the installed named playwright_test_generator agent. Delegate specs/comparison-plan.md and the appendix below to that named child, then wait. One child only, no planner/healer/repairs. Do not invoke or read installed skills: this frozen study supplies the complete task, safety instructions and arm appendix. Read the approved plan and official agent definition if needed, not the app implementation.
Only {origin} is approved, an owned disposable local fixture with no external backend. User approves navigation, reading both counters, one Alpha increment, reload, and writing tests/counter-persistence.spec.ts. Never change app, seed, config, plan or agents. Never mock API requests, read control/witness endpoints, use browser evaluation/unsafe-code/uploads, install anything, or run tests. Use real page observations and require completed generator_setup_page, generator_read_log, generator_write_test in that sequence. Preserve all required outcomes exactly. If unavailable or blocked, stop INCONCLUSIVE without substitute agent or retry. Parent harness will run normal and fixed-fault tests. No advantage is expected or required.
Appendix (only experimental difference):\n{appendix}'''
        argv=[x.replace(old,str(project)) for x in source['model_command']]
        argv[0]=machine['codex']
        for index,value in enumerate(argv):
            if value.startswith('mcp_servers.playwright-test.command='):
                argv[index]='mcp_servers.playwright-test.command='+json.dumps(machine['node'])
            elif value.startswith('mcp_servers.playwright-test.args='):
                args=json.loads(value.split('=',1)[1]);args[0]=str(Path(machine['modules'])/'playwright/cli.js')
                argv[index]='mcp_servers.playwright-test.args='+json.dumps(args)
        argv=argv[:-1]+['-c','features.skip_host_skill_discovery=true','-']
        (cell/'prompt.txt').write_text(prompt);write(cell/'model-command.json',argv)
        files={str(p.relative_to(project)):sha(p) for p in project.rglob('*') if p.is_file() and 'node_modules' not in p.parts}
        cells.append({'arm':arm,'project':str(project),'origin':origin,'port':port,'input_sha256':files,'prompt_sha256':sha(cell/'prompt.txt'),'argv_sha256':sha(cell/'model-command.json')})
    protocol={'schema':2,'machine':machine,'machine_config_sha256':sha(machine_config),'model':'gpt-6.1-sol','order':ARMS,'repetitions':1,'scenario':'one authored two-item counter ownership/persistence task','cells':cells,'modes':MODES,'app_sha256':hashlib.sha256(APP.encode()).hexdigest(),'rule_sha256':{p.name:sha(p) for p in (directory/'current-12.md',directory/'candidate-4.md')},'source_setup_template':{'path':str(template),'sha256':sha(template)},'comparability':'Same task text except origin paths and rule appendix; fresh independent official named child per arm; no repairs','faults':{'omit-write':'POST observed but selected server write omitted','wrong-item-update':'POST observed but other item incremented'},'acceptance':['actual official child metadata','three completed defining tools','normal and restored native pass','both faults reach POST witness and alter persisted state','input hashes unchanged'],'scanner':'Separate fixed-spec static observation only; no scanner-driven repairs','limits':['one authored scenario, not OSS or general superiority','fixed manual fault runner, not packaged generic check','fixed arm order, no randomization or confidence interval','model-free host skill discovery suppression is common to all arms'],'stop':'Any generation, baseline, witness, restoration or source-integrity failure stops next cell; null outcomes retained','script_sha256':sha(Path(__file__))}
    write(directory/'protocol.json',protocol);return {'protocol':str(directory/'protocol.json'),'sha256':sha(directory/'protocol.json')}

def defining_receipt(root, sessions_directory):
    events=[json.loads(l) for l in (root/'model-transcript.jsonl').read_text().splitlines()]
    thread=next(e['thread_id'] for e in events if e.get('type')=='thread.started')
    # Native sessions are kept by the runtime. Select only this exact root and
    # metadata-linked children, never unrelated transcript content.
    day=Path(sessions_directory)
    target=root/'persistent-rollouts';target.mkdir()
    found=[];counts=Counter();child=False
    for path in day.glob('*.jsonl'):
        if path.stat().st_mtime < (root/'prompt.txt').stat().st_mtime-2:continue
        with path.open() as stream:meta=json.loads(stream.readline()).get('payload',{})
        source=meta.get('source',{});spawn=source.get('subagent',{}).get('thread_spawn',{}) if isinstance(source,dict) else {}
        linked=spawn.get('parent_thread_id')==thread and spawn.get('agent_role')=='playwright_test_generator'
        if meta.get('id')!=thread and not linked:continue
        child=child or linked;shutil.copyfile(path,target/path.name);found.append({'file':path.name,'sha256':sha(target/path.name),'official_child':linked})
        for line in path.read_text().splitlines():
            event=json.loads(line);payload=event.get('payload',{});item=payload.get('item',{})
            if linked and event.get('type')=='event_msg' and payload.get('type')=='item_completed' and item.get('type')=='McpToolCall' and item.get('server')=='playwright-test' and item.get('status')=='completed':counts[item.get('tool')]+=1
    required={t:counts[t] for t in ('generator_setup_page','generator_read_log','generator_write_test')}
    receipt={'root':thread,'official_child':child,'defining_completed':required,'all_completed_tools':dict(counts),'rollouts':found,'pass':child and all(required.values()),'parent_usage':[e.get('usage') for e in events if e.get('type')=='turn.completed']}
    write(root/'defining-receipt.json',receipt);return receipt

def run(directory):
    protocol=json.loads((directory/'protocol.json').read_text());results=[]
    if protocol.get('schema')!=2:raise ValueError('this harness version requires freshly prepared schema2 protocol; preserve older frozen runners')
    machine=protocol['machine']
    if (directory/'run-started.json').exists():raise ValueError('already attempted')
    write(directory/'run-started.json',{'protocol_sha256':sha(directory/'protocol.json'),'started':time.time()})
    for cell in protocol['cells']:
        root=directory/cell['arm'];project=Path(cell['project']);argv=json.loads((root/'model-command.json').read_text());app=None;model=None
        result={'arm':cell['arm'],'status':'INCONCLUSIVE','conditions':[]};start=time.monotonic()
        try:
            if any(sha(project/p)!=v for p,v in cell['input_sha256'].items()):raise ValueError('input drift')
            with (root/'app.stdout.txt').open('x') as out,(root/'app.stderr.txt').open('x') as err:app=subprocess.Popen([machine['node'],str(project/'app.mjs'),str(cell['port'])],stdout=out,stderr=err,start_new_session=True)
            for _ in range(30):
                try:get(cell['origin']);break
                except OSError:time.sleep(.1)
            reuse=cell.get('reuse_generation')
            if reuse:
                prior=Path(reuse)
                for name in ('model-transcript.jsonl','model.stderr.txt','defining-receipt.json'):
                    shutil.copyfile(prior/name,root/name)
                shutil.copytree(prior/'persistent-rollouts',root/'persistent-rollouts')
                result['generation_reused_from']=str(prior)
                result['new_parent_model_invocations']=0
                result['defining']=json.loads((root/'defining-receipt.json').read_text())
            else:
                result['new_parent_model_invocations']=1
                with (root/'model-transcript.jsonl').open('x') as out,(root/'model.stderr.txt').open('x') as err:
                    model=subprocess.Popen(argv,cwd=project,stdin=subprocess.PIPE,stdout=out,stderr=err,text=True,start_new_session=True)
                    try:model.communicate((root/'prompt.txt').read_text(),timeout=240)
                    except subprocess.TimeoutExpired:raise ValueError('generation timeout; stop')
                if model.returncode:raise ValueError('model failed')
                result['defining']=defining_receipt(root,machine['sessions_directory'])
            if not result['defining']['pass']:raise ValueError('named child/defining calls not established')
            spec=project/'tests/counter-persistence.spec.ts'
            if not spec.exists():raise ValueError('spec not generated')
            result['spec_sha256']=sha(spec)
            if cell.get('reuse_spec_sha256') and result['spec_sha256']!=cell['reuse_spec_sha256']:raise ValueError('reused spec changed')
            for mode in MODES:
                actual='normal' if mode=='restored' else mode
                get(cell['origin']+'/__control?mode='+actual);before=json.loads(get(cell['origin']+'/__witness'))
                native=subprocess.run([machine['node'],str(Path(machine['modules'])/'playwright/cli.js'),'test',re.escape(str(spec.relative_to(project)))+'$','--config',str(project/'playwright.config.mjs'),'--reporter=json'],cwd=project,capture_output=True,text=True,timeout=45)
                after=json.loads(get(cell['origin']+'/__witness'));(root/(mode+'.native.json')).write_text(native.stdout);(root/(mode+'.stderr.txt')).write_text(native.stderr)
                reached=any(r['name']=='Alpha' for r in after['requests']);condition={'mode':mode,'exit':native.returncode,'before':before,'after':after,'fault_reached':reached,'stats':json.loads(native.stdout).get('stats')};result['conditions'].append(condition);write(root/'progress.json',result)
                stats=condition['stats']
                if stats.get('skipped') or stats.get('flaky') or stats.get('expected',0)+stats.get('unexpected',0)!=1:raise ValueError('native did not execute exactly one unskipped test')
                if mode in ('normal','restored') and (native.returncode or stats.get('expected')!=1):raise ValueError(mode+' control failed')
                if not reached:raise ValueError('target write not reached')
                if mode=='omit-write' and after['items']!={'Alpha':3,'Beta':7}:raise ValueError('omit-write not observed')
                if mode=='wrong-item-update' and after['items']!={'Alpha':3,'Beta':8}:raise ValueError('wrong-item fault not observed')
            scanenv=os.environ.copy()
            scanenv.update({'E2E_SMELL_ALLOW_PROJECT_ESLINT':'0','E2E_SMELL_NO_ESLINT_DOWNLOAD':'1','E2E_SMELL_NO_AST_GREP_DOWNLOAD':'1','E2E_SMELL_DISABLE_AST_GREP':'1'})
            scan=subprocess.run(['/bin/bash','-p',str(ROOT/'skills/e2e-reviewer/scripts/scan.sh'),str(spec)],env=scanenv,text=True,capture_output=True,timeout=45)
            (root/'scanner.stdout.txt').write_text(scan.stdout);(root/'scanner.stderr.txt').write_text(scan.stderr)
            result['scanner_exit']=scan.returncode
            result['input_unchanged']=all(sha(project/p)==v for p,v in cell['input_sha256'].items())
            if not result['input_unchanged']:raise ValueError('input changed')
            result['status']='VALID_FIXED_SCENARIO_CELL'
        except (ValueError,OSError,subprocess.TimeoutExpired) as e:result['reason']=str(e)
        finally:
            if model:stop(model)
            if app:stop(app)
            result['seconds']=round(time.monotonic()-start,2);result['cleanup']={'model_stopped':model is None or model.poll() is not None,'app_stopped':app is None or app.poll() is not None};write(root/'result.json',result);results.append(result);write(directory/'results.json',results)
        if result['status']=='INCONCLUSIVE':break
    return results

if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--directory',required=True,type=Path);p.add_argument('--prepare-only',action='store_true');p.add_argument('--machine-config',type=Path);p.add_argument('--allow-live',action='store_true');args=p.parse_args()
    if args.prepare_only:
        if args.machine_config is None:p.error('--prepare-only requires --machine-config')
        print(json.dumps(prepare(args.directory,args.machine_config.resolve(strict=True)),indent=2))
    elif args.allow_live:print(json.dumps(run(args.directory.resolve(strict=True)),indent=2))
    else:raise SystemExit('choose --prepare-only or explicit --allow-live')
