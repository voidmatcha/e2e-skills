#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""One opt-in official-generator defining-tool canary; no retries or score claims."""

import argparse
import hashlib
import json
import os
from pathlib import Path
import signal
import socket
import subprocess
import time
import urllib.request

SCOPED_TOOLS = ('browser_click', 'browser_close', 'browser_console_messages',
                'browser_drag', 'browser_evaluate', 'browser_file_upload',
                'browser_handle_dialog', 'browser_hover', 'browser_navigate',
                'browser_navigate_back', 'browser_network_request', 'browser_network_requests',
                'browser_press_key', 'browser_run_code_unsafe', 'browser_select_option',
                'browser_snapshot', 'browser_take_screenshot', 'browser_type',
                'browser_verify_element_visible', 'browser_verify_list_visible',
                'browser_verify_text_visible', 'browser_verify_value', 'browser_wait_for',
                'generator_read_log', 'generator_setup_page', 'generator_write_test',
                'planner_save_plan', 'planner_setup_page', 'test_run')


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def stop(process):
    if process.poll() is None:
        os.killpg(process.pid, signal.SIGTERM)
        try:
            process.wait(timeout=5)
        except subprocess.TimeoutExpired:
            os.killpg(process.pid, signal.SIGKILL)
            process.wait(timeout=5)


def run(directory, allow_live, registry_proof):
    if not allow_live:
        raise ValueError('requires --allow-live: one model call and local browser/test execution')
    directory = directory.resolve(strict=True)
    registry_proof = registry_proof.resolve(strict=True)
    if 'playwright_test_generator' not in registry_proof.read_text():
        raise ValueError('registry proof lacks named generator')
    preflight = json.loads((directory / 'preflight.json').read_text())
    project = directory / 'project'
    if (project / '.codex/config.toml').exists():
        raise ValueError('unexpected project config')
    for name, expected in preflight['files_sha256'].items():
        if sha(directory / name) != expected:
            raise ValueError('preflight input changed: ' + name)
    if (directory / 'canary-freeze.json').exists():
        raise ValueError('this prepared directory was already used; no automatic retry')
    node, codex = preflight['node']['path'], preflight['codex']['path']
    cli = preflight['playwright']['cli']
    with socket.socket() as reservation:
        reservation.bind(('127.0.0.1', 0))
        port = reservation.getsockname()[1]
    origin = 'http://127.0.0.1:' + str(port)
    plan = f'''# Generator canary\n\n## Like counter\n\n**Seed:** tests/seed.spec.ts\n\n### Clicking Like increments the counter\n\n1. Navigate to {origin}.\n2. Confirm heading "Generator canary" and status "0".\n3. Click the button named "Like".\n4. Confirm the status is "1".\n\nGenerate exactly one test in tests/like-counter.spec.ts.\n'''
    (project / 'specs/canary-plan.md').write_text(plan)
    prompt = f'''Execute ONE bounded official-generator transport canary, not an experiment to prove skill superiority.
Project: {project}. The owned disposable app is already running at {origin}; only this origin is approved. No backend or production service exists.
Use exactly the installed official playwright_test_generator named agent from .codex/agents/playwright_test_generator.toml, if that named role is actually available in your runtime agent catalog. Delegate the single approved plan specs/canary-plan.md to it, wait for completion, and report its identity. The caller has approved local navigation, the described Like click and output tests/like-counter.spec.ts. Do not invoke planner/healer or another child.
If the named official role is not available, stop and report INCONCLUSIVE with missing named role; do not substitute a generic agent or hand-write the test.
Require actual completed generator_setup_page, generator_read_log and generator_write_test calls. The child should use the documented runtime tools, inspect the page, click Like, and verify counter1; do not guess assertions from the app source. No shell/model code browser evaluation or uploads are approved. Do not alter existing fixture, seed, agent or configuration files.
After the child finishes, report generated path and status. The external harness will run the generated spec, so do not execute tests or shell commands yourself except reading the plan or official definition if necessary. If blocked, stop; do not install, change settings or retry this canary. Model budget: one child; project only.
'''
    overrides = {
        'model_reasoning_effort': 'medium',
        'mcp_servers.playwright-test.command': node,
        'mcp_servers.playwright-test.args': [cli, 'run-test-mcp-server', '--headless', '--config', str(project / 'playwright.config.mjs')],
        'mcp_servers.playwright-test.required': True,
        'mcp_optional_startup_grace_ms': 0,
        'mcp_servers.playwright-test.default_tools_approval_mode': 'prompt',
        'mcp_servers.playwright-test.enabled_tools': list(SCOPED_TOOLS),
    }
    for tool in SCOPED_TOOLS:
        overrides['mcp_servers.playwright-test.tools.' + tool + '.approval_mode'] = 'approve'
    argv = [codex, 'exec', '--ignore-user-config', '--ignore-rules', '--strict-config',
            '--skip-git-repo-check', '--json', '--sandbox', 'workspace-write',
            '--model', 'gpt-6.1-sol', '-C', str(project)]
    for key, value in overrides.items():
        argv.extend(['-c', key + '=' + json.dumps(value)])
    # Whole-table TOML is accepted by native strict validation; dotted project
    # overrides are rejected by Codex 0.159.3. This trusts this owned fixture only.
    project_trust = 'projects={' + json.dumps(str(project)) + '={trust_level="trusted"}}'
    argv.extend(['-c', project_trust, '-'])
    freeze = {'schema': 1, 'scope': 'one named official-generator canary', 'model': 'gpt-6.1-sol',
              'registry_proof': {'path': str(registry_proof), 'sha256': sha(registry_proof)},
              'setup_revision': 'whole-table invocation-local project trust; generated agents unchanged',
              'project_trust_override': project_trust,
              'origin': origin, 'app_command': [node, str(project / 'app.mjs'), str(port)],
              'model_command': argv, 'timeout_seconds': 420,
              'script_sha256': sha(Path(__file__)), 'prepared_input_sha256': preflight['files_sha256'],
              'plan_sha256': sha(project / 'specs/canary-plan.md'),
              'acceptance': ['actual named official generator delegation', 'completed setup/read_log/write_test',
                             'same-app generated spec passes', 'frozen existing input bytes unchanged'],
              'exclusions': ['general superiority', 'thin-rule effect', 'scanner incremental effect', 'planner path']}
    (directory / 'canary-prompt.txt').write_text(prompt)
    freeze['prompt_sha256'] = sha(directory / 'canary-prompt.txt')
    (directory / 'canary-freeze.json').write_text(json.dumps(freeze, indent=2) + '\n')
    started = time.monotonic()
    app = model = None
    result = {'status': 'INCONCLUSIVE', 'new_parent_invocations': 0, 'origin': origin}
    try:
        with (directory / 'app.stdout.txt').open('x') as out, (directory / 'app.stderr.txt').open('x') as err:
            app = subprocess.Popen(freeze['app_command'], cwd=project, stdout=out, stderr=err, start_new_session=True)
        ready = False
        for _ in range(40):
            try:
                with urllib.request.urlopen(origin, timeout=1) as response:
                    ready = response.status == 200
            except OSError:
                pass
            if ready:
                break
            time.sleep(.1)
        if not ready:
            raise ValueError('owned app failed readiness')
        with (directory / 'model-transcript.jsonl').open('x') as out, (directory / 'model-stderr.txt').open('x') as err:
            model = subprocess.Popen(argv, cwd=project, stdin=subprocess.PIPE, stdout=out, stderr=err,
                                     text=True, start_new_session=True)
            result['new_parent_invocations'] = 1
            try:
                model.communicate(prompt, timeout=420)
                result['model_exit'] = model.returncode
            except subprocess.TimeoutExpired:
                result['reason'] = 'one canary timed out; no retry'
                stop(model)
        spec = project / 'tests/like-counter.spec.ts'
        if spec.is_file():
            command = [node, cli, 'test', str(spec), '--config', str(project / 'playwright.config.mjs'), '--reporter=json']
            native = subprocess.run(command, cwd=project, capture_output=True, text=True, timeout=90)
            (directory / 'native-report.json').write_text(native.stdout)
            (directory / 'native-stderr.txt').write_text(native.stderr)
            result.update(native_exit=native.returncode, generated_spec_sha256=sha(spec), native_command=command)
        else:
            result['reason'] = 'no generated spec; inspect named role/tool evidence'
        result['existing_input_integrity'] = all(sha(directory / name) == digest for name, digest in preflight['files_sha256'].items())
    except (OSError, ValueError, subprocess.TimeoutExpired) as error:
        result['reason'] = str(error)
    finally:
        if model:
            stop(model)
        if app:
            stop(app)
        result['seconds'] = round(time.monotonic() - started, 2)
        result['process_cleanup'] = {'model_stopped': model is None or model.poll() is not None,
                                     'app_stopped': app is None or app.poll() is not None}
        (directory / 'canary-execution.json').write_text(json.dumps(result, indent=2) + '\n')
    return result


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--directory', required=True, type=Path)
    parser.add_argument('--registry-proof', required=True, type=Path)
    parser.add_argument('--allow-live', action='store_true')
    print(json.dumps(run(**vars(parser.parse_args())), indent=2))
