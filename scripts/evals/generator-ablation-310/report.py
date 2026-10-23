#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Summarize one preserved canary without trusting final-message success claims."""

import argparse
from collections import Counter
import hashlib
import json
from pathlib import Path


def summarize(directory, receipt_name="canary-receipt.json"):
    if Path(receipt_name).name != receipt_name or receipt_name in (".", ".."):
        raise ValueError("receipt_name must be a basename")
    directory = directory.resolve(strict=True)
    events = [json.loads(line) for line in (directory / 'model-transcript.jsonl').read_text().splitlines()]
    completed = [e for e in events if e.get('type') == 'turn.completed']
    root_id = next((e['thread_id'] for e in events if e.get('type') == 'thread.started'), None)
    mcp, collaboration = Counter(), Counter()
    rollouts = []
    roles_reported = []
    named_children = []
    for path in sorted((directory / 'persistent-rollouts').glob('*.jsonl')):
        rollouts.append({'path': str(path.relative_to(directory)),
                         'sha256': hashlib.sha256(path.read_bytes()).hexdigest()})
        for line in path.read_text().splitlines():
            event = json.loads(line)
            payload = event.get('payload', {})
            if event.get('type') == 'session_meta':
                spawn = payload.get('source', {}).get('subagent', {}).get('thread_spawn', {}) if isinstance(payload.get('source'), dict) else {}
                if spawn.get('parent_thread_id') == root_id and spawn.get('agent_role') == 'playwright_test_generator':
                    named_children.append({'thread_id': payload.get('id'), 'parent_thread_id': root_id,
                                           'agent_role': spawn['agent_role'], 'rollout': str(path.relative_to(directory))})
            if event.get('type') == 'response_item' and payload.get('type') == 'function_call':
                if payload.get('name') in ('spawn_agent', 'send_message', 'wait_agent'):
                    collaboration[payload['name']] += 1
            if event.get('type') == 'event_msg' and payload.get('type') == 'item_completed':
                item = payload.get('item', {})
                if item.get('type') == 'McpToolCall':
                    mcp[(item.get('server'), item.get('tool'), item.get('status'))] += 1
    for event in events:
        item = event.get('item', {})
        if event.get('type') == 'item.completed' and item.get('type') == 'agent_message':
            roles_reported.append(item.get('text', ''))
    execution = json.loads((directory / 'canary-execution.json').read_text())
    required = ('generator_setup_page', 'generator_read_log', 'generator_write_test')
    defining = {tool: mcp[('playwright-test', tool, 'completed')] for tool in required}
    acceptance = {'parent_model_completed': len(completed) == 1,
                  'delegation_observed': collaboration['spawn_agent'] > 0,
                  'named_official_child_observed': bool(named_children),
                  'defining_calls_completed': all(defining.values()),
                  'generated_spec_native_passed': execution.get('native_exit') == 0,
                  'frozen_input_integrity': execution.get('existing_input_integrity') is True,
                  'persistent_rollout_present': bool(rollouts)}
    receipt = {'schema': 1, 'status': 'PASS' if all(acceptance.values()) else 'INCONCLUSIVE',
               'scope': 'one generator defining-tool canary; not a quality comparison',
               'root_thread': root_id, 'parent_model_turns_completed': len(completed),
               'distinct_persistent_model_sessions': len(rollouts),
               'usage': [e.get('usage') for e in completed],
               'acceptance': acceptance, 'defining_completed_counts': defining,
               'collaboration_call_counts': dict(collaboration), 'named_children': named_children,
               'native_stats': json.loads((directory / 'native-report.json').read_text()).get('stats') if (directory / 'native-report.json').exists() else None,
               'mcp_counts': [{'server': s, 'tool': t, 'status': st, 'count': n}
                              for (s, t, st), n in mcp.items()],
               'persistent_rollouts': rollouts, 'model_reports': roles_reported,
               'discovery_limit': ('Named child metadata and parent linkage verified from persistent rollouts.' if named_children else 'No linked named child metadata. A model statement alone does not prove registry absence or its cause.'),
               'process_cleanup': execution['process_cleanup'],
               'execution_sha256': hashlib.sha256((directory / 'canary-execution.json').read_bytes()).hexdigest()}
    target = directory / receipt_name
    with target.open('x') as output:
        output.write(json.dumps(receipt, indent=2) + '\n')
    return receipt


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--directory', required=True, type=Path)
    parser.add_argument('--receipt-name', default='canary-receipt.json')
    print(json.dumps(summarize(**vars(parser.parse_args())), indent=2))
