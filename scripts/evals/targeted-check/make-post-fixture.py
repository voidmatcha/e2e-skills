#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Create a fresh, external authored fixture. Does not execute project code."""
import argparse
import hashlib
import json
from pathlib import Path

CLIENT = """document.querySelector('button').onclick = async () => {
  document.querySelector('button').setAttribute('aria-pressed', 'true');
  await fetch('/probe/entered', {method: 'POST'});
  await fetch('/api/like', {method: 'POST'});
  await fetch('/probe/settled', {method: 'POST'});
  document.querySelector('[role=status]').textContent = 'Done';
};
"""
SERVER = """import http from 'node:http';
import fs from 'node:fs';
import { randomUUID } from 'node:crypto';
export async function start() {
  const session = randomUUID(); let liked = false; let sequence = 0;
  const record = (event, extra = {}) => fs.appendFileSync('app-log.ndjson', JSON.stringify({session, sequence: ++sequence, event, liked, ...extra}) + '\\n');
  record('server-start');
  const server = http.createServer((req, res) => {
    if (req.url === '/' && req.method === 'GET') {res.setHeader('content-type','text/html');res.end('<button aria-pressed="false">Like</button><p role="status">Ready</p><script src="/client.js"></script>');}
    else if(req.url === '/client.js' && req.method === 'GET') {res.setHeader('content-type','text/javascript');res.end(fs.readFileSync('client.js'));}
    else if(req.url === '/probe/entered' && req.method === 'POST') {record('handler-entered');res.end('ok');}
    else if(req.url === '/probe/settled' && req.method === 'POST') {record('handler-settled');res.end('ok');}
    else if(req.url === '/api/like' && req.method === 'POST') {liked = true;record('like-write');res.setHeader('content-type','application/json');res.end(JSON.stringify({liked}));}
    else if(req.url === '/api/like' && req.method === 'GET') {record('state-read');res.setHeader('content-type','application/json');res.end(JSON.stringify({liked}));}
    else {res.statusCode=404;res.end('missing');}
  });
  await new Promise(resolve => server.listen(0,'127.0.0.1',resolve));
  return {url:'http://127.0.0.1:'+server.address().port, close:async()=>{await new Promise(resolve=>server.close(resolve));record('server-close');fs.writeFileSync('server-state.json',JSON.stringify({session,liked}));}};
}
"""
WRAPPER = """import { spawn } from 'node:child_process';
import { start } from './server.mjs';
const server = await start();
let code = 2;
try {
  const child = spawn(process.execPath, ['node_modules/playwright/cli.js','test','--config=playwright.config.mjs','--grep',process.env.E2E_PROBE_SELECTOR+'$'], {stdio:'inherit',env:{...process.env,E2E_TARGET_URL:server.url}});
  code = await new Promise((resolve,reject)=>{child.once('error',reject);child.once('exit',code=>resolve(code ?? 2));});
} finally {await server.close();}
process.exitCode = code;
"""
TEST = """import { test, expect } from '@playwright/test';
for (const kind of ['strong', 'weak']) {
  test(kind + ' optimistic write', async ({ page, request }) => {
    await page.goto(process.env.E2E_TARGET_URL);
    await page.getByRole('button', {name:'Like',exact:true}).click();
    await expect(page.getByRole('button', {name:'Like',exact:true})).toHaveAttribute('aria-pressed','true');
    await expect(page.getByRole('status')).toHaveText('Done');
    if (kind === 'strong') {
      const state = await (await request.get(process.env.E2E_TARGET_URL+'/api/like')).json();
      expect(state.liked).toBe(true);
    }
  });
}
"""
OBSERVER = """import fs from 'node:fs';
import crypto from 'node:crypto';
const log=fs.readFileSync('app-log.ndjson');
const entries=log.toString().trim().split('\\n').map(line=>JSON.parse(line));
const state=JSON.parse(fs.readFileSync('server-state.json'));
const events=entries.map(e=>e.event);
const entered=entries.filter(e=>e.event==='handler-entered');
const settled=entries.filter(e=>e.event==='handler-settled');
const writes=entries.filter(e=>e.event==='like-write');
const valid=events[0]==='server-start' && events.at(-1)==='server-close' && entries.every((e,i)=>e.sequence===i+1 && e.session===state.session) && entered.length===1 && settled.length===1 && entered[0].sequence<settled[0].sequence;
const between=writes.filter(e=>e.sequence>entered[0]?.sequence && e.sequence<settled[0]?.sequence);
const evidence=['app-log.ndjson','server-state.json'].map(path=>({path,sha256:crypto.createHash('sha256').update(fs.readFileSync(path)).digest('hex')}));
process.stdout.write(JSON.stringify({project:process.cwd(),promised_effect:!!(valid && state.liked===true && writes.length===1 && between.length===1 && settled[0].liked===true),fault_reached:!!(valid && writes.length===0 && state.liked===false && settled[0].liked===false),evidence,observation:{events,final_liked:state.liked,session:state.session}})+'\\n');
"""


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', required=True, type=Path)
    parser.add_argument('--dependency-dir', required=True, type=Path)
    parser.add_argument('--browser', required=True, type=Path)
    parser.add_argument('--node', required=True, type=Path)
    args = parser.parse_args()
    root = args.output.absolute()
    if root.exists() or not all(p.is_absolute() and p.exists() for p in (args.dependency_dir, args.browser, args.node)):
        raise ValueError('fresh output and explicit existing absolute tooling required')
    project = root / 'project'
    project.mkdir(parents=True)
    config = "import { defineConfig } from '@playwright/test';\nexport default defineConfig(" + json.dumps({'testDir':'.','testMatch':'optimistic.spec.mjs','workers':1,'retries':0,'timeout':10000,'expect':{'timeout':1000},'use':{'headless':True,'launchOptions':{'executablePath':str(args.browser)}}}) + ");\n"
    config = config.replace('defineConfig({', "defineConfig({reporter:[['json',{outputFile:process.env.E2E_PROBE_REPORT}]],", 1)
    files = {'client.js':CLIENT,'server.mjs':SERVER,'run.mjs':WRAPPER,'optimistic.spec.mjs':TEST,'observer.mjs':OBSERVER,'playwright.config.mjs':config,'package.json':json.dumps({'private':True,'type':'module'}),'README.md':'# Authored optimistic POST fixture\nClicking Like must persist liked=true through POST /api/like.\n'}
    for name, text in files.items():
        (project/name).write_text(text)
    digest = lambda name: hashlib.sha256((project/name).read_bytes()).hexdigest()
    for kind in ('strong','weak'):
        binding = {'source':str(project),'test_selector':kind+' optimistic write','test_paths':['optimistic.spec.mjs'],'promise':{'path':'README.md','quote':'Clicking Like must persist liked=true through POST /api/like.','sha256':digest('README.md')},'test':{'argv':[str(args.node),'run.mjs'],'timeout_seconds':30,'source':{'path':'run.mjs','sha256':digest('run.mjs')}},'observer':{'argv':[str(args.node),'observer.mjs'],'timeout_seconds':10,'source':{'path':'observer.mjs','sha256':digest('observer.mjs')}},'report':{'format':'playwright-json','path':'native-report.json'},'expected_failure':{'contains':'toBe','location':'optimistic.spec.mjs:10'},'dependency_dirs':[{'path':'node_modules','target':str(args.dependency_dir)}]}
        (root/(kind+'-binding.json')).write_text(json.dumps(binding,indent=2)+'\n')
    print(root)


if __name__ == '__main__':
    main()
