// SPDX-License-Identifier: Apache-2.0
import { test } from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs';
import os from 'node:os';
import path from 'node:path';
import crypto from 'node:crypto';
import vm from 'node:vm';
import { spawnSync } from 'node:child_process';
import * as setup from '../dev/setup.mjs';
import toml from '../dev/vendor/smol-toml/index.cjs';
const base = fs.realpathSync(fs.mkdtempSync(path.join(os.tmpdir(), 'e2e node installer tests ')));
process.on('exit', () => fs.rmSync(base, { recursive: true, force: true }));
let sequence = 0;
function fixture() {
  const root = path.join(base, String(sequence++)), project = path.join(root, 'project with spaces'), home = path.join(root, 'home');
  fs.mkdirSync(project, { recursive: true }); fs.mkdirSync(home);
  const config = path.join(project, 'playwright.config.cjs');
  fs.writeFileSync(config, "throw Error('project config must never execute');\n");
  const pkg = path.join(project, 'node_modules/playwright'); fs.mkdirSync(pkg, { recursive: true });
  fs.writeFileSync(path.join(pkg, 'package.json'), '{"name":"playwright"}');
  const cli = path.join(pkg, 'cli.js'); fs.writeFileSync(cli, "throw Error('project CLI must never execute on dry-run');\n");
  return { root, project, home, cli, config, env: { HOME: home, PATH: '/usr/bin:/bin', CODEX_HOME: path.join(home, '.codex'), CLAUDE_CONFIG_DIR: path.join(home, '.claude') } };
}
function fakeRun(command, stage) {
  if (command.at(-1) === '--help') return { stdout: 'choices: claude, codex' };
  const host = command.at(-1).split('=').at(-1), folder = path.join(stage, host === 'codex' ? '.codex/agents' : '.claude/agents');
  fs.mkdirSync(folder, { recursive: true });
  for (const role of ['planner', 'generator', 'healer']) {
    const name = host === 'codex' ? `playwright_test_${role}.toml` : `playwright-test-${role}.md`;
    const text = host === 'codex' ? `name = "playwright_test_${role}"\ndeveloper_instructions = "official fixture"\n\n[mcp_servers.playwright-test]\ncommand = "npx"\nargs = ["playwright", "run-test-mcp-server"]\nenabled_tools = ["generator_write_test"]\n` : `---\nname: playwright-test-${role}\n---\nofficial fixture\n`;
    fs.writeFileSync(path.join(folder, name), text);
  }
  return { stdout: 'generated' };
}
const plan = (f, host = 'codex', dry = false, run = fakeRun) => setup.projectPlan(f.project, host, f.env, dry, run);
const target = (f, host) => path.join(f.project, host === 'codex' ? '.codex/config.toml' : '.mcp.json');
function put(file, text) { fs.mkdirSync(path.dirname(file), { recursive: true }); fs.writeFileSync(file, text); }
for (const host of ['codex', 'claude']) {
  test(host + ': preserve other config, recovery mode, idempotence and children', () => {
    const f = fixture(), file = target(f, host), before = host === 'codex' ? '# keep\nmodel = "demo"\n[mcp_servers.other]\ncommand="keep"\n' : '{"mcpServers":{"other":{"command":"keep"}},"custom":42}';
    put(file, before); const pending = plan(f, host); setup.preflightBackups(pending); setup.applyPlan(pending);
    assert.equal(fs.readFileSync(file + '.e2e-skills-backup', 'utf8'), before);
    assert.equal(fs.statSync(file + '.e2e-skills-backup').mode & 0o777, 0o600);
    const after = fs.readFileSync(file, 'utf8'); setup.applyPlan(plan(f, host)); assert.equal(fs.readFileSync(file, 'utf8'), after);
    const parsed = host === 'codex' ? toml.parse(after) : JSON.parse(after);
    assert.equal(parsed[host === 'codex' ? 'mcp_servers' : 'mcpServers'].other.command, 'keep');
    if (host === 'codex') {
      const server = parsed.mcp_servers['playwright-test']; assert.equal(server.args.at(-1), f.config); assert.equal(server.required, true);
      for (const name of fs.readdirSync(path.join(f.project, '.codex/agents'))) { const child = toml.parse(fs.readFileSync(path.join(f.project, '.codex/agents', name), 'utf8')).mcp_servers['playwright-test']; assert.deepEqual(child.args, server.args); assert.equal(child.command, server.command); assert.deepEqual(child.enabled_tools, ['generator_write_test']); }
    } else assert.equal(parsed.custom, 42);
    assert.equal(fs.existsSync(path.join(f.project, 'tests')), false); assert.equal(fs.existsSync(path.join(f.project, 'specs')), false);
  });
  test(host + ': conflict does not execute CLI or alter configuration', () => {
    const f = fixture(), file = target(f, host), text = host === 'codex' ? '[mcp_servers."playwright-test"]\ncommand="foreign"\n' : '{"mcpServers":{"playwright-test":{"command":"foreign"}}}';
    put(file, text); assert.throws(() => plan(f, host, false, () => assert.fail('executed')), /MCP differs/); assert.equal(fs.readFileSync(file, 'utf8'), text);
  });
  test(host + ': backup collision, snapshot race and symlink fail closed', () => {
    const f = fixture(), file = target(f, host); put(file, host === 'codex' ? '# comment\n' : '{}'); put(file + '.e2e-skills-backup', 'preserve');
    assert.throws(() => setup.preflightBackups(plan(f, host)), /backup already exists/);
    fs.unlinkSync(file + '.e2e-skills-backup'); const pending = plan(f, host); fs.writeFileSync(file, 'concurrent'); assert.throws(() => setup.applyPlan(pending), /changed during installation/); assert.equal(fs.readFileSync(file, 'utf8'), 'concurrent');
    fs.unlinkSync(file); fs.symlinkSync(f.config, file); assert.throws(() => plan(f, host), /symlinked/);
  });
  test(host + ': dry run uses no CLI and makes no project writes', () => {
    const f = fixture(); assert.equal(plan(f, host, true, () => assert.fail('executed')).size, 1); assert.equal(fs.existsSync(target(f, host)), false);
  });
  test(host + ': dedicated agents preserve foreign files', () => {
    const f = fixture(), destination = path.join(host === 'codex' ? f.env.CODEX_HOME : f.env.CLAUDE_CONFIG_DIR, 'agents', 'e2e-finding-verifier' + (host === 'codex' ? '.toml' : '.md'));
    put(destination, 'foreign'); assert.throws(() => setup.dedicatedPreflight(host, f.env), /conflicts/); assert.equal(fs.readFileSync(destination, 'utf8'), 'foreign');
  });
  test(host + ': main routing uses clean staged env without executing real installers', async () => {
    const f = fixture(), calls = [];
    await setup.main(['--host', host, '--dry-run'], { cleanEnv: () => ({ ...f.env }), install: () => assert.fail('installed') });
    assert.equal(await setup.main(['--host', host], { cleanEnv: () => ({ ...f.env }), install: (command, cwd, env) => calls.push({ command, cwd, env }) }), 0);
    assert.equal(calls.length, host === 'codex' ? 1 : 2); assert.equal(calls[0].env.E2E_SKILLS_AGENTS, host === 'codex' ? '-a codex' : '-a claude-code -a codex'); assert.equal(calls[0].env.E2E_SKILLS_INSTALL_CODEX_AGENTS, host === 'codex' ? '1' : '0');
  });
  test(host + ': diagnostic status does not infer session/approval or execute foreign config', async () => {
    const f = fixture(); assert.equal((await setup.checkSetup(f.project, host, f.env, () => assert.fail('discovery'))).status, 'CONFIG_MISSING');
    setup.applyPlan(plan(f, host)); const file = target(f, host), original = fs.readFileSync(file, 'utf8');
    const required = new Set(['planner_setup_page', 'planner_save_plan', 'generator_setup_page', 'generator_write_test']);
    for (const [names, status] of [[required, 'SERVER_VERIFIED'], [new Set(), 'TOOLS_MISSING'], [null, 'SERVER_ERROR']]) {
      const report = await setup.checkSetup(f.project, host, f.env, async () => { if (names === null) throw Error('untrusted secret approval text'); return names; });
      assert.equal(report.status, status); assert.equal(report.session, 'unverified'); assert.equal(report.approval, 'unknown'); assert.equal(JSON.stringify(report).includes('secret approval'), false);
    }
    for (const [key, value, status] of [['enabled', false, 'CONFIG_DISABLED'], ['enabled_tools', ['browser_navigate'], 'TOOLS_BLOCKED'], ['disabled_tools', ['generator_write_test'], 'TOOLS_BLOCKED']]) {
      if (host === 'codex') put(file, original.split('\n').filter(line => !line.startsWith(key + ' =')).join('\n') + `\n${key} = ${JSON.stringify(value)}\n`);
      else { const parsed = JSON.parse(original); parsed.mcpServers['playwright-test'][key] = value; put(file, JSON.stringify(parsed)); }
      assert.equal((await setup.checkSetup(f.project, host, f.env, () => assert.fail('discovery'))).status, status);
    }
    put(file, host === 'codex' ? '[mcp_servers.playwright-test]\ncommand="foreign"\nargs=[]\n' : '{"mcpServers":{"playwright-test":{"command":"foreign","args":[]}}}');
    assert.equal((await setup.checkSetup(f.project, host, f.env, () => assert.fail('foreign command'))).status, 'CONFIG_ERROR');
  });
}
test('TOML full parser handles multiline, quoted dotted names, dates and refuses duplicate/inline table collisions', () => {
  const f = fixture(), file = target(f, 'codex');
  const before = '# comment\ntext = """multi\nline [mcp_servers.playwright-test]\n"""\ndate = 2026-10-23T12:00:00Z\n[mcp_servers."a.b"]\ncommand = "keep"\n'; put(file, before);
  const pending = plan(f); setup.applyPlan(pending); assert.equal(fs.readFileSync(file, 'utf8').startsWith(before.trimEnd()), true); assert.equal(toml.parse(fs.readFileSync(file, 'utf8')).mcp_servers['a.b'].command, 'keep');
  for (const bad of ['mcp_servers = {}\n', '[mcp_servers]\nplaywright-test = {}\n', 'model="a"\nmodel="b"\n']) { put(file, bad); assert.throws(() => plan(f)); assert.equal(fs.readFileSync(file, 'utf8'), bad); }
});
test('prototype keys are data, never ambient inherited servers', () => {
  const f = fixture(), file = target(f, 'claude'); put(file, '{"__proto__":{"x":1},"mcpServers":{"constructor":{"command":"keep"}}}'); setup.applyPlan(plan(f, 'claude')); assert.equal({}.x, undefined); assert.equal(JSON.parse(fs.readFileSync(file, 'utf8')).mcpServers.constructor.command, 'keep');
});
test('foreign generated agent and unsupported official layout fail before writes', () => {
  const f = fixture(); put(path.join(f.project, '.codex/agents/playwright_test_planner.toml'), 'foreign'); assert.throws(() => plan(f), /existing file differs/); assert.equal(fs.existsSync(target(f, 'codex')), false);
  const g = fixture(); assert.throws(() => plan(g, 'codex', false, () => ({ stdout: 'claude' })), /does not advertise/);
});
test('CLI check rejects missing project / dry-run and skips all installers', async () => {
  await assert.rejects(setup.main(['--host', 'codex', '--check']), /requires --project/);
  const f = fixture(); await assert.rejects(setup.main(['--host', 'codex', '--check', '--project', f.project, '--dry-run']), /cannot be combined/);
  assert.equal(await setup.main(['--host', 'codex', '--check', '--project', f.project], { cleanEnv: () => f.env, checkSetup: async () => ({ status: 'SERVER_VERIFIED' }), install: () => assert.fail('install') }), 0);
});
test('public shell entry is Node-only, rejects Node injection and uses fixture home', () => {
  const f = fixture(), sentinel = path.join(f.root, 'injected'), injection = path.join(f.root, 'injection.cjs'); put(injection, `require('fs').writeFileSync(${JSON.stringify(sentinel)}, 'bad')`);
  const result = spawnSync('/bin/bash', ['-p', path.join(setup.ROOT, 'install.sh'), '--host', 'codex', '--dry-run'], { env: { ...f.env, NODE_OPTIONS: '--require=' + injection, PYTHONPATH: 'poison' }, encoding: 'utf8' });
  assert.equal(result.status, 0, result.stderr); assert.equal(fs.existsSync(sentinel), false); assert.equal(fs.existsSync(f.env.CODEX_HOME), false);
  const entry = fs.readFileSync(path.join(setup.ROOT, 'install.sh'), 'utf8'); assert.equal(entry.includes('setup.py'), false); assert.equal(entry.includes('exec "$node"'), true);
});
test('vendored TOML parser/license match pinned provenance hashes', () => {
  const dir = path.join(setup.ROOT, 'scripts/dev/vendor/smol-toml'), provenance = JSON.parse(fs.readFileSync(path.join(dir, 'provenance.json')));
  for (const [name, expected] of Object.entries(provenance.files)) assert.equal(crypto.createHash('sha256').update(fs.readFileSync(path.join(dir, name))).digest('hex'), expected);
  assert.equal(provenance.version, '1.4.2'); assert.equal(provenance.license, 'BSD-3-Clause');
});
function fakeMcp(f, body) {
  const script = path.join(f.root, 'mcp.cjs'), pid = path.join(f.root, 'pid'), transcript = path.join(f.root, 'transcript');
  put(script, `const fs=require('fs'),rl=require('readline').createInterface({input:process.stdin});fs.writeFileSync(${JSON.stringify(pid)},String(process.pid));const log=${JSON.stringify(transcript)};const respond=(id,result)=>process.stdout.write(JSON.stringify({jsonrpc:'2.0',id,result})+'\\n');rl.on('line',line=>{const message=JSON.parse(line);fs.appendFileSync(log,line+'\\n');${body}});`);
  return { command: [process.execPath, script], pid, transcript };
}
function reaped(file) { assert.throws(() => process.kill(Number(fs.readFileSync(file, 'utf8')), 0), { code: 'ESRCH' }); }
test('MCP handshake/pagination lists tools only and reaps child', async () => {
  const f = fixture(), server = fakeMcp(f, `if(message.method==='initialize')respond(message.id,{capabilities:{tools:{}}});else if(message.method==='tools/list')respond(message.id,message.params.cursor?{tools:[{name:'generator_write_test'}]}:{tools:[{name:'planner_setup_page'}],nextCursor:'page2'});`);
  assert.deepEqual(await setup.mcpTools(server.command, f.project, f.env, 3000), new Set(['planner_setup_page', 'generator_write_test'])); reaped(server.pid);
  assert.deepEqual(fs.readFileSync(server.transcript, 'utf8').trim().split('\n').map(line => JSON.parse(line).method), ['initialize','notifications/initialized','tools/list','tools/list']);
});
test('MCP timeout and oversized output fail closed and reap child', async () => {
  for (const body of ['', "process.stdout.write('x'.repeat(5*1024*1024));"]) {
    const f = fixture(), server = fakeMcp(f, body), start = Date.now(); await assert.rejects(setup.mcpTools(server.command, f.project, f.env, 200)); assert.ok(Date.now()-start<4000); reaped(server.pid);
  }
});
test('MCP invalid catalog, malformed reply and repeated cursor fail closed', async () => {
  for (const result of [{ tools: 'invalid' }, { tools: [{ name: 42 }] }, { tools: [], nextCursor: 'repeat' }]) {
    const f = fixture(), server = fakeMcp(f, `if(message.method==='initialize')respond(message.id,{capabilities:{}});else if(message.method==='tools/list')respond(message.id,${JSON.stringify(result)});`); await assert.rejects(setup.mcpTools(server.command, f.project, f.env, 3000)); reaped(server.pid);
  }
});
test('MCP backpressure uses shared deadline even when server never reads requests', async () => {
  const f = fixture(), script = path.join(f.root, 'backpressure.cjs'), pid = path.join(f.root, 'pid');
  put(script, `const fs=require('fs');fs.writeFileSync(${JSON.stringify(pid)},String(process.pid));process.stdout.write(JSON.stringify({id:1,result:{capabilities:{}}})+'\\n');for(let id=2;id<102;id++)process.stdout.write(JSON.stringify({id,result:{tools:[],nextCursor:String(id)+'\\0'.repeat(4093)}})+'\\n');setInterval(()=>{},1000);`);
  const start = Date.now(); await assert.rejects(setup.mcpTools([process.execPath, script], f.project, f.env, 300), /timed out|pagination/); assert.ok(Date.now()-start<4000); reaped(pid);
});
test('symlinked parent, generated symlink and failed installer never write project config', async () => {
  const f = fixture(), outside = path.join(f.root, 'outside'); fs.mkdirSync(outside); fs.symlinkSync(outside, path.join(f.project, '.codex'));
  assert.throws(() => plan(f), /symlinked/); assert.deepEqual(fs.readdirSync(outside), []);
  const g = fixture(); assert.throws(() => plan(g, 'codex', false, (command, stage) => {
    if (command.at(-1) === '--help') return { stdout: 'codex' };
    const folder = path.join(stage, '.codex/agents'); fs.mkdirSync(folder, { recursive: true }); fs.symlinkSync(g.config, path.join(folder, 'playwright_test_planner.toml')); return { stdout: '' };
  }), /symlinked/);
  const h = fixture(); await assert.rejects(setup.main(['--host', 'codex', '--project', h.project], { cleanEnv: () => h.env, run: fakeRun, install: () => { throw Error('stopped installer'); } }), /stopped installer/); assert.equal(fs.existsSync(target(h, 'codex')), false);
});
test('Claude project settings disable discovery without changing configuration', async () => {
  const f = fixture(); setup.applyPlan(plan(f, 'claude'));
  for (const relative of ['.claude/settings.json', '.claude/settings.local.json']) {
    const file = path.join(f.project, relative); put(file, '{"disabledMcpjsonServers":["playwright-test"]}');
    assert.equal((await setup.checkSetup(f.project, 'claude', f.env, () => assert.fail('discovery'))).status, 'CONFIG_DISABLED'); fs.unlinkSync(file);
  }
});
test('workspace-hoisted Playwright is resolved without executing package/config and backup extension is rejected', () => {
  const f = fixture(), nested = path.join(f.project, 'workspace'); fs.mkdirSync(nested); fs.writeFileSync(path.join(nested, 'playwright.config.ts'), 'throw Error("must not execute")');
  assert.equal(setup.projectDependencies(nested).cli, f.cli);
  fs.renameSync(f.config, f.config + '.bak'); assert.throws(() => plan(f), /directory containing/);
});
test('owned global agents may upgrade; custom Claude directory and relative global targets fail', async () => {
  const f = fixture(); put(path.join(f.env.CODEX_HOME, 'agents/e2e-finding-verifier.toml'), '# e2e-skills Codex native agent: old\n'); assert.doesNotThrow(() => setup.dedicatedPreflight('codex', f.env));
  assert.throws(() => setup.dedicatedPreflight('codex', { ...f.env, CODEX_HOME: 'relative' }), /absolute/);
  await assert.rejects(setup.main(['--host', 'claude', '--dry-run'], { cleanEnv: () => ({ ...f.env, CLAUDE_CONFIG_DIR: path.join(f.home, 'custom') }) }), /custom CLAUDE_CONFIG_DIR/);
});
test('MCP spawn failure, malformed JSON and protocol error do not hang or echo server secrets', async () => {
  const f = fixture(); await assert.rejects(setup.mcpTools([path.join(f.root, 'absent')], f.project, f.env, 200));
  for (const body of ["process.stdout.write('not JSON\\n');", "process.stdout.write(JSON.stringify({id:message.id,error:{message:'secret'}})+'\\n');"]) {
    const server = fakeMcp(f, body); await assert.rejects(setup.mcpTools(server.command, f.project, f.env, 200), error => !error.message.includes('secret')); reaped(server.pid);
  }
});
test('MCP cleanup terminates its descendants after group leader exits', async () => {
  const f = fixture(), script = path.join(f.root, 'descendant.cjs'), pid = path.join(f.root, 'descendant-pid');
  put(script, `const {spawn}=require('child_process'),fs=require('fs');const child=spawn(process.execPath,['-e','setInterval(()=>{},1000)'],{stdio:'ignore'});fs.writeFileSync(${JSON.stringify(pid)},String(child.pid));process.exit(0);`);
  await assert.rejects(setup.mcpTools([process.execPath, script], f.project, f.env, 1000));
  // Reparented children are reaped by init asynchronously, unlike the direct child.
  for (let retry=0;retry<30;retry++) { try { process.kill(Number(fs.readFileSync(pid,'utf8')),0); await new Promise(resolve=>setTimeout(resolve,20)); } catch(error) { if(error.code==='ESRCH') return; throw error; } }
  assert.fail('owned MCP descendant survived cleanup');
});
test('malformed UTF-8 in existing TOML/JSON and generated agents fails closed', async () => {
  for (const host of ['codex','claude']) {
    const f=fixture(), file=target(f,host), bad=Buffer.concat([Buffer.from(host==='codex'?'# malformed ': '{"custom":"'), Buffer.from([0xff]), Buffer.from(host==='codex'?'\n':'"}')]);
    put(file,bad); assert.throws(()=>plan(f,host), /encoded data|UTF-8/); assert.deepEqual(fs.readFileSync(file),bad);
    assert.equal((await setup.checkSetup(f.project,host,f.env,()=>assert.fail('discovery'))).status,'CONFIG_ERROR');
    const g=fixture(); assert.throws(()=>plan(g,host,false,(command,stage)=>{const result=fakeRun(command,stage);if(command.at(-1)!=='--help'){const file=path.join(stage,host==='codex'?'.codex/agents/playwright_test_planner.toml':'.claude/agents/playwright-test-planner.md');fs.appendFileSync(file,Buffer.from([0xff]));}return result;}), /encoded data|UTF-8/);
  }
});

test('malformed project configuration never echoes sensitive source in CLI errors', () => {
  const sentinel = 'FAKE_SECRET_SENTINEL';
  for (const host of ['claude', 'codex']) {
    const f = fixture(), file = target(f, host);
    const source = host === 'claude' ? '{"TOKEN":' + sentinel + '}' : 'token = ' + sentinel;
    put(file, source);
    const result = spawnSync(process.execPath, [path.join(setup.ROOT, 'scripts/dev/setup.mjs'), '--host', host, '--project', f.project, '--dry-run'], { env: f.env, encoding: 'utf8' });
    assert.equal(result.status, 1);
    assert.match(result.stderr, /invalid (JSON|TOML) configuration:/);
    assert.equal((result.stdout + result.stderr).includes(sentinel), false);
    assert.equal(fs.readFileSync(file, 'utf8'), source);
    assert.equal(fs.existsSync(file + '.e2e-skills-backup'), false);
  }
  const f = fixture(), file = path.join(f.project, 'node_modules/playwright/package.json');
  put(file, '{"TOKEN":' + sentinel + '}');
  assert.throws(() => plan(f), error => /invalid JSON configuration/.test(error.message) && !error.message.includes(sentinel));
});

test('direct installer invocation through a symlink executes the CLI', () => {
  const f = fixture(), link = path.join(f.root, 'linked-repository');
  fs.symlinkSync(setup.ROOT, link, 'dir');
  const result = spawnSync(process.execPath, [path.join(link, 'scripts/dev/setup.mjs'), '--host', 'codex', '--dry-run'], { env: f.env, encoding: 'utf8' });
  assert.equal(result.status, 0, result.stderr);
  assert.match(result.stdout, /Dry run: no files changed/);
  assert.equal(fs.existsSync(f.env.CODEX_HOME), false);
});
test('public installer enforces the documented Node 22.20 minimum', () => {
  const entry = fs.readFileSync(path.join(setup.ROOT, 'install.sh'), 'utf8');
  const expression = entry.match(/\"\$node\" -e '([^']+)'/)[1];
  for (const [version, expected] of [['21.99.0', 1], ['22.19.9', 1], ['22.20.0', 0], ['22.23.3', 0], ['23.0.0', 0], ['26.10.0', 0]]) {
    let code; vm.runInNewContext(expression, { process: { versions: { node: version }, exit: value => { code = value; } } });
    assert.equal(code, expected, version);
  }
});
test('symlinked env ancestors resolve; the base itself and destinations below it stay refused', () => {
  const f = fixture(), real = path.join(f.root, 'real'), link = path.join(f.root, 'link'); fs.mkdirSync(path.join(real, 'home'), { recursive: true }); fs.symlinkSync(real, link);
  assert.equal(setup.resolveAncestors(path.join(link, 'home')), path.join(real, 'home'));
  assert.equal(setup.resolveAncestors(path.join(link, 'missing/codex-home')), path.join(real, 'missing/codex-home'));
  assert.equal(setup.resolveAncestors('relative/home'), 'relative/home');
  fs.symlinkSync(path.join(f.root, 'nowhere'), path.join(real, 'dangling'));
  assert.equal(setup.resolveAncestors(path.join(link, 'dangling/home')), path.join(real, 'dangling/home'));
  const env = setup.canonicalEnv({ HOME: path.join(link, 'home'), CODEX_HOME: path.join(link, 'home/.codex'), PATH: '/usr/bin:/bin' });
  assert.deepEqual(env, { HOME: path.join(real, 'home'), CODEX_HOME: path.join(real, 'home/.codex'), PATH: '/usr/bin:/bin' });
  for (const host of ['codex', 'claude']) setup.dedicatedPreflight(host, env);
  assert.throws(() => setup.dedicatedPreflight('codex', setup.canonicalEnv({ HOME: path.join(link, 'dangling/home') })), /refusing symlinked destination/);
  assert.throws(() => setup.dedicatedPreflight('codex', setup.canonicalEnv({ HOME: link })), /refusing symlinked destination/);
  fs.symlinkSync(f.root, path.join(real, 'home/.claude'));
  assert.throws(() => setup.dedicatedPreflight('claude', env), /refusing symlinked destination/);
});
