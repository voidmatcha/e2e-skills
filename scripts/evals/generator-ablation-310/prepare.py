#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Prepare a fresh host generator canary and list MCP tools without a model/browser."""

import argparse
import hashlib
import json
from pathlib import Path
import queue
import re
import subprocess
import threading

ROOT = Path(__file__).resolve().parents[3]
VERSION = '1.62.0'
REQUIRED = ('planner_setup_page', 'planner_save_plan', 'planner_submit_plan',
            'generator_setup_page', 'generator_read_log', 'generator_write_test', 'test_run')


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def probe(argv, cwd, output):
    process = subprocess.Popen(argv, cwd=cwd, stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                               stderr=subprocess.PIPE, text=True)
    messages = queue.Queue()
    errors = []
    def stdout_reader():
        for line in process.stdout:
            try:
                messages.put(json.loads(line))
            except ValueError:
                messages.put({'invalid_json': True})
    def stderr_reader():
        for line in process.stderr:
            errors.append(line)
    readers = [threading.Thread(target=stdout_reader, daemon=True),
               threading.Thread(target=stderr_reader, daemon=True)]
    for reader in readers:
        reader.start()
    transcript = []
    def request(value):
        process.stdin.write(json.dumps(value) + '\n')
        process.stdin.flush()
        if 'id' not in value:
            return
        while True:
            response = messages.get(timeout=20)
            transcript.append(response)
            if response.get('invalid_json') or response.get('error'):
                raise ValueError('MCP rejected initialization/listing')
            if response.get('id') == value['id']:
                return response['result']
    try:
        initialized = request({'jsonrpc': '2.0', 'id': 1, 'method': 'initialize',
                               'params': {'protocolVersion': '2024-11-05', 'capabilities': {},
                                          'clientInfo': {'name': 'e2e-skills-generator-310-preflight', 'version': '1'}}})
        request({'jsonrpc': '2.0', 'method': 'notifications/initialized'})
        result = request({'jsonrpc': '2.0', 'id': 2, 'method': 'tools/list'})
        if result.get('nextCursor'):
            raise ValueError('unexpected paginated tool list')
        tools = {tool['name']: tool for tool in result['tools']}
        for name in REQUIRED:
            if name not in tools or not isinstance(tools[name].get('inputSchema'), dict):
                raise ValueError('required tool or runtime input schema missing: ' + name)
        (output / 'mcp-transcript.json').write_text(json.dumps(transcript, indent=2) + '\n')
        (output / 'tools-schema.json').write_text(json.dumps(result, indent=2) + '\n')
        return {'initialize': initialized, 'required_tools': list(REQUIRED),
                'tool_names': list(tools), 'model_calls': 0, 'browser_calls': 0,
                'methods_sent': ['initialize', 'notifications/initialized', 'tools/list']}
    finally:
        if process.poll() is None:
            process.terminate()
            try:
                process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait(timeout=5)
        for reader in readers:
            reader.join(timeout=2)
        (output / 'mcp-stderr.txt').write_text(''.join(errors))
        process.stdin.close()
        process.stdout.close()
        process.stderr.close()


def prepare(output, modules, node, codex):
    output = output.expanduser().absolute()
    if any(p.is_symlink() for p in (output, *output.parents)):
        raise ValueError('output must not use symlinks')
    output = output.resolve()
    if output.is_relative_to(ROOT) or output.exists():
        raise ValueError('output must be fresh and outside the checkout')
    modules = modules.resolve(strict=True)
    node = node.resolve(strict=True)
    codex = codex.resolve(strict=True)
    for name in ('playwright', '@playwright/test', 'playwright-core'):
        package = json.loads((modules / name / 'package.json').read_text())
        if package['version'] != VERSION:
            raise ValueError('exact dependency version required: ' + name)
    cli = modules / 'playwright/cli.js'
    node_version = subprocess.check_output([str(node), '--version'], text=True).strip()
    codex_version = subprocess.check_output([str(codex), '--version'], text=True).strip()
    version = subprocess.check_output([str(node), str(cli), '--version'], text=True).strip()
    output.mkdir()
    project = output / 'project'
    project.mkdir()
    (project / 'node_modules').symlink_to(modules, target_is_directory=True)
    (project / 'package.json').write_text(json.dumps({'name': 'e2e-skills-generator-310-canary',
        'private': True, 'type': 'module', 'license': 'Apache-2.0',
        'devDependencies': {'@playwright/test': VERSION}}, indent=2) + '\n')
    (project / 'playwright.config.mjs').write_text("import { defineConfig } from '@playwright/test';\nexport default defineConfig({testDir:'./tests',workers:1,retries:0,use:{browserName:'chromium',headless:true}});\n")
    (project / 'tests').mkdir()
    (project / 'tests/seed.spec.ts').write_text("import { test } from '@playwright/test';\ntest('seed', async ({ page }) => { /* owned seed; no navigation yet */ });\n")
    (project / 'app.mjs').write_text("import http from 'node:http';\nconst port=Number(process.argv[2]); if(!Number.isInteger(port)||port<1024) throw Error('explicit loopback port required');\nhttp.createServer((req,res)=>{res.setHeader('Content-Type','text/html');res.end('<!doctype html><title>Generator canary</title><h1>Generator canary</h1><button>Like</button><p role=\\\"status\\\">0</p><script>document.querySelector(\\\"button\\\").onclick=()=>document.querySelector(\\\"[role=status]\\\").textContent=\\\"1\\\"</script>');}).listen(port,'127.0.0.1');\n")
    init = [str(node), str(cli), 'init-agents', '--loop', 'codex', '--config', str(project / 'playwright.config.mjs')]
    result = subprocess.run(init, cwd=project, capture_output=True, text=True, timeout=30, check=True)
    (output / 'init-agents.stdout.txt').write_text(result.stdout)
    (output / 'init-agents.stderr.txt').write_text(result.stderr)
    mcp = [str(node), str(cli), 'run-test-mcp-server', '--headless', '--config', str(project / 'playwright.config.mjs')]
    listing = probe(mcp, project, output)
    enabled_tools = {'test_run'}
    for agent in ('planner', 'generator'):
        definition = (project / '.codex/agents' / ('playwright_test_' + agent + '.toml')).read_text()
        match = re.search(r'^enabled_tools = (\[.*\])$', definition, re.M)
        if not match:
            raise ValueError('official agent enabled_tools missing')
        enabled_tools.update(json.loads(match.group(1)))
    if not enabled_tools <= set(listing['tool_names']) or len(enabled_tools) >= 80:
        raise ValueError('official agent tools unavailable or over budget')
    listing['enabled_tools_for_next_canary'] = sorted(enabled_tools)
    subprocess.run([str(node), '--check', str(project / 'app.mjs')], check=True, capture_output=True, text=True)
    # CLI overrides are invocation-local. No user config, auth, trust or MCP
    # approval state is read or edited by this preparation script.
    overrides = {'mcp_servers.playwright-test.command': str(node),
                 'mcp_servers.playwright-test.args': mcp[1:],
                 'mcp_servers.playwright-test.required': True,
                 'mcp_optional_startup_grace_ms': 0,
                 'mcp_servers.playwright-test.enabled_tools': sorted(enabled_tools)}
    argv = [str(codex), 'exec', '--json', '--ignore-user-config', '--strict-config',
            '--skip-git-repo-check', '-C', str(project), '--model', 'gpt-6.1-sol',
            '-c', 'model_reasoning_effort="medium"']
    for key, value in overrides.items():
        argv.extend(['-c', key + '=' + json.dumps(value)])
    argv.append('-')
    (output / 'next-model-command.json').write_text(json.dumps({'argv': argv,
        'executed': False, 'session_persistence': 'retain child rollouts; do not use --ephemeral',
        'preconditions': ['explicit model/browser execution authorization', 'choose free loopback port and start owned app',
                          'freeze approved scenario + exact commands + source hashes',
                          'use existing approved auth through host; never print or modify credentials',
                          'resolve local tool approval policy without blanket bypass'],
        'acceptance': ['official agent delegation recorded in persistent child rollout',
                       'completed generator_setup_page + generator_read_log + generator_write_test',
                       'generated spec runs on the same owned target'],
        'stop': 'one defining-tool canary only; missing tool or timeout is INCONCLUSIVE, no blind retries'}, indent=2) + '\n')
    evidence_paths = [p for p in project.rglob('*') if p.is_file() and 'node_modules' not in p.parts]
    evidence_paths += [output / 'tools-schema.json', output / 'mcp-transcript.json', output / 'next-model-command.json']
    hashes = {str(p.relative_to(output)): sha(p) for p in sorted(evidence_paths)}
    provenance = {'schema': 1, 'scope': 'model-free setup and runtime MCP listing only',
        'node': {'path': str(node), 'version': node_version},
        'codex': {'path': str(codex), 'version': codex_version},
        'playwright': {'version': version, 'cli': str(cli), 'cli_sha256': sha(cli)},
        'source': {'official_agents': str(modules / 'playwright/lib/agents'),
                   'generator_source_sha256': sha(modules / 'playwright/lib/agents/generateAgents.js'),
                   'prepare_script_sha256': sha(Path(__file__)),
                   'historical_lineage': 'generator-final-v3-comparison-20261018-updated-fresh-v1; historical harness not imported'},
        'dependency_metadata_sha256': {name: sha(modules / name / 'package.json')
                                     for name in ('playwright', '@playwright/test', 'playwright-core')},
        'official_agent_source_sha256': {p.name: sha(p) for p in sorted((modules / 'playwright/lib/agents').glob('*.agent.md'))},
        'commands': {'init_agents': init, 'mcp': mcp}, 'runtime': listing,
        'files_sha256': hashes, 'status': 'PASS',
        'limits': ['No browser started, no model called, no native test executed',
                   'Tool discovery does not prove Codex session approval or actual agent delegation',
                   'Reused dependency directory is shared mutable input; frozen dependency metadata is not an OS sandbox']}
    (output / 'preflight.json').write_text(json.dumps(provenance, indent=2) + '\n')
    return {'output': str(output), 'status': 'PASS', 'model_calls': 0, 'browser_calls': 0,
            'tools_discovered': len(listing['tool_names']), 'preflight_sha256': sha(output / 'preflight.json')}


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    for flag in ('output', 'modules', 'node', 'codex'):
        parser.add_argument('--' + flag, required=True, type=Path)
    print(json.dumps(prepare(**vars(parser.parse_args())), indent=2))
