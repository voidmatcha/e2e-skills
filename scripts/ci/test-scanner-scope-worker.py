#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Persistent scanner scope worker protocol and fail-closed regressions."""
import sys
sys.dont_write_bytecode = True
import importlib.util
import json
import os
from pathlib import Path
import shutil
import signal
import fcntl
import struct
import subprocess
import tempfile
import time
import unittest
from unittest import mock
from types import SimpleNamespace

sys.path.insert(0, str(Path(__file__).resolve().parent))
from lib.legacy_scanner_oracle import legacy_scanner_file

BASE = legacy_scanner_file().parent
WORKER = BASE / 'scope-worker.py'
spec = importlib.util.spec_from_file_location('worker', WORKER)
m = importlib.util.module_from_spec(spec); spec.loader.exec_module(m)


def resolve_rg() -> str:
    configured = os.environ.get("E2E_SMELL_RG_BIN")
    candidates = [configured] if configured else [
        "/opt/homebrew/bin/rg",
        "/usr/local/bin/rg",
        "/usr/bin/rg",
        "/bin/rg",
    ]
    for candidate in candidates:
        path = Path(candidate)
        if path.is_absolute() and path.is_file() and os.access(path, os.X_OK):
            return str(path)
    raise RuntimeError("Set E2E_SMELL_RG_BIN to an absolute executable ripgrep path")


class WorkerTests(unittest.TestCase):
    watch_mode = 'off'

    def setUp(self):
        self.rg = resolve_rg()
        self.tmp = tempfile.TemporaryDirectory(prefix='sw-', dir=str(Path('/tmp').resolve()))
        self.base = Path(self.tmp.name).resolve()
        self.project = self.base / 'project'; self.project.mkdir()
        self.ipc = self.base / 'ipc'; self.ipc.mkdir(mode=0o700)
        self.channel = self.ipc / 's'; self.control = self.ipc / 'state'
        self.rg_errors = self.ipc / 'rg-errors'; self.rg_errors.touch(mode=0o600)
        self.visited = self.ipc / 'visited'; self.visited.touch(mode=0o600)
        self.source = self.project / 'entry.ts'; self.source.write_text("import { test } from './support';\n")
        self.support = self.project / 'support.ts'; self.support.write_text("export { test } from '@playwright/test';\n")
        self.helper = self.base / 'helper.sh'; shutil.copyfile(BASE / 'scope-source.sh', self.helper)
        if self._testMethodName == 'test_terminal_ack_term_cannot_interrupt_helper_reap':
            with self.helper.open('a') as stream:
                stream.write('\necho $$ > "' + str(self.base/'helper.pid') + '"\nsleep 30\n')
        self.log = (self.base / 'worker.log').open('wb')
        launcher = [sys.executable, '-I', '-B']
        if self._testMethodName == 'test_terminal_cleanup_term_during_interpreter_shutdown_is_quiet':
            # Deterministically deliver parent-cleanup TERM after main returns,
            # in the same interpreter shutdown window seen in full field scans.
            launcher += ['-c',
                'import atexit,os,runpy,signal,sys; script=sys.argv.pop(1); '
                'atexit.register(lambda: os.kill(os.getpid(),signal.SIGTERM)); '
                'runpy.run_path(script,run_name="__main__")']
        self.process = subprocess.Popen(launcher + [str(WORKER),'serve',
            '--channel',str(self.channel),'--control',str(self.control),
            '--parent-pid',str(os.getpid()),'--project',str(self.project),'--helper',str(self.helper),
            '--rg',self.rg,'--rg-errors',str(self.rg_errors), '--timeout','30',
            '--watch-mode',self.watch_mode],
            stdout=self.log,stderr=subprocess.STDOUT,start_new_session=True)
        self.addCleanup(self.cleanup)
        result = self.client('ping', extra=['--wait-ready','5'])
        self.assertEqual(result.returncode, 0, result.stderr)

    def cleanup(self):
        if self.process.poll() is None:
            self.process.terminate()
            try: self.process.wait(timeout=6)
            except subprocess.TimeoutExpired:
                self.process.kill(); self.process.wait(timeout=2)
        self.log.close(); self.tmp.cleanup()

    def client(self, op, extra=()):
        args = [sys.executable,'-I','-B',str(WORKER),'client','--channel',str(self.channel),
                '--control',str(self.control),'--op',op,'--timeout','5']
        if op == 'query': args += ['--node',str(self.source),'--visited',str(self.visited)]
        return subprocess.run(args + list(extra),capture_output=True,text=True,timeout=8)

    def test_ping_is_liveness_only_and_checkpoint_catches_mutation(self):
        self.assertEqual(self.client('query').returncode, 0)
        self.support.write_text('export const replacement = 1;\n')
        self.assertEqual(self.client('ping', extra=['--repeat', '3']).returncode, 0)
        self.assertEqual(self.client('checkpoint').returncode, 2)
        self.assertEqual(self.process.wait(timeout=3), 2)

    def test_checkpoint_is_not_terminal(self):
        self.assertEqual(self.client('query').returncode, 0)
        self.assertEqual(self.client('checkpoint').returncode, 0)
        self.visited.write_text('')
        self.assertEqual(self.client('query').returncode, 0)
        self.assertEqual(self.client('validate').returncode, 0)
        self.assertEqual(self.process.wait(timeout=3), 0)

    def test_repeat_count_and_operation_contract(self):
        self.assertEqual(self.client('ping', extra=['--repeat', '64']).returncode, 0)
        for count in (1, 2, 64):
            argv = [str(WORKER), 'client', '--channel', str(self.channel),
                    '--control', str(self.control), '--repeat', str(count)]
            with mock.patch.object(sys, 'argv', argv), mock.patch.object(m, 'client', return_value=0) as client:
                self.assertEqual(m.main(), 0)
                self.assertEqual(client.call_count, count)
        for mode, op, count in [('client', 'ping', '0'), ('client', 'ping', '-1'),
                                ('client', 'ping', '65'), ('client', 'query', '1'),
                                ('client', 'validate', '1'), ('serve', 'ping', '1')]:
            argv = [str(WORKER), mode, '--channel', str(self.channel),
                    '--control', str(self.control), '--op', op, '--repeat', count]
            with mock.patch.object(sys, 'argv', argv), mock.patch.object(m, 'client') as client:
                self.assertEqual(m.main(), 2)
                client.assert_not_called()
        result = self.client('ping', extra=['--repeat', 'invalid'])
        self.assertEqual(result.returncode, 2)

    def test_multiquery_order_and_terminal_validation(self):
        for _ in range(2):
            self.visited.write_text('existing\rname\n')
            result = self.client('query')
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual(self.visited.read_bytes(), ('existing\rname\n'+str(self.source)+'\n'+str(self.support)+'\n').encode())
        self.assertEqual(self.client('validate').returncode, 0)
        self.assertEqual(self.process.wait(timeout=3), 0)
        self.assertEqual(self.client('query').returncode, 2)

    def test_source_mutation_permanently_poisoned(self):
        self.assertEqual(self.client('query').returncode, 0)
        self.visited.write_text(''); self.support.write_text('export const replacement = 1;\n')
        result = self.client('query')
        self.assertEqual(result.returncode, 2, result.stderr)
        self.assertEqual(self.process.wait(timeout=3), 2)
        self.assertEqual(self.client('validate').returncode, 2)

    def test_missing_alternative_appearing_fails(self):
        self.source.write_text("import { test } from './absent';\n")
        self.assertEqual(self.client('query').returncode, 3)
        self.visited.write_text(''); (self.project/'absent.ts').write_text("export { test } from '@playwright/test';\n")
        self.assertEqual(self.client('query').returncode, 2)

    def test_marker_deletion_fails_and_cannot_restart(self):
        self.control.unlink()
        self.assertEqual(self.client('query').returncode, 2)
        self.assertEqual(self.process.wait(timeout=3), 2)

    def test_marker_replacement_fails(self):
        original = self.control.read_bytes(); self.control.unlink()
        self.control.write_bytes(original); self.control.chmod(0o600)
        self.assertEqual(self.client('query').returncode, 2)

    def test_worker_crash_not_implicit_empty_history(self):
        self.process.kill(); self.process.wait(timeout=3)
        self.assertEqual(self.client('query').returncode, 2)
        self.assertEqual(self.client('validate').returncode, 2)

    def test_visited_symlink_rejected(self):
        outside = self.base/'outside'; outside.write_text('unchanged'); outside.chmod(0o600)
        self.visited.unlink(); self.visited.symlink_to(outside)
        self.assertEqual(self.client('query').returncode, 2)
        self.assertEqual(outside.read_text(), 'unchanged')

    def raw_exchange(self, data):
        """Send raw bytes as one locked client exchange and return the worker's reply."""
        paths = m.channel_paths(str(self.channel))
        lock_fd = os.open(paths['lock'], os.O_RDWR)
        try:
            fcntl.flock(lock_fd, fcntl.LOCK_EX)
            response_fd = os.open(paths['response'], os.O_RDONLY | os.O_NONBLOCK)
            try:
                request_fd = os.open(paths['request'], os.O_WRONLY)
                try: os.write(request_fd, data)
                finally: os.close(request_fd)
                return m.read_response(response_fd, time.monotonic() + 10, lambda: True)
            finally: os.close(response_fd)
        finally: os.close(lock_fd)

    def test_dead_unreaped_worker_fails_fast(self):
        # An unreaped (zombie) worker still answers a PID probe; the client must
        # notice the closed FIFO instead and fail long before its deadline.
        self.process.send_signal(signal.SIGKILL)
        time.sleep(0.2)
        started = time.monotonic()
        result = subprocess.run([sys.executable, '-I', '-B', str(WORKER), 'client', '--channel', str(self.channel),
                                 '--control', str(self.control), '--op', 'ping', '--timeout', '60'],
                                capture_output=True, text=True, timeout=30)
        self.assertEqual(result.returncode, 2, result.stderr)
        self.assertLess(time.monotonic() - started, 10)

    def test_malformed_frame_poisoned(self):
        response = self.raw_exchange(struct.pack('!I', 100) + b'{')
        self.assertEqual(response['status'], 'error')
        self.assertEqual(self.process.wait(timeout=8), 2)

    def test_duplicate_request_field_poisoned(self):
        state = json.loads(self.control.read_text())
        payload = ('{"v":1,"v":1,"nonce":"'+state['nonce']+'","rid":"'+'0'*32+'","op":"ping"}').encode()
        response = self.raw_exchange(struct.pack('!I',len(payload))+payload)
        self.assertEqual(response['status'], 'error')
        self.assertEqual(self.process.wait(timeout=3), 2)

    def test_oversized_frame_poisoned(self):
        self.assertEqual(self.raw_exchange(struct.pack('!I', 65537))['status'], 'error')
        self.assertEqual(self.process.wait(timeout=3), 2)

    def test_trailing_frame_bytes_poisoned(self):
        state = json.loads(self.control.read_text())
        payload = json.dumps({'v': 1, 'nonce': state['nonce'], 'rid': '0'*32, 'op': 'ping'}).encode()
        self.assertEqual(self.raw_exchange(struct.pack('!I', len(payload)) + payload + b'x')['status'], 'error')
        self.assertEqual(self.process.wait(timeout=3), 2)

    def test_request_without_request_id_poisoned(self):
        state = json.loads(self.control.read_text())
        payload = json.dumps({'v': 1, 'nonce': state['nonce'], 'op': 'ping'}).encode()
        self.assertEqual(self.raw_exchange(struct.pack('!I', len(payload)) + payload)['status'], 'error')
        self.assertEqual(self.process.wait(timeout=3), 2)

    def test_response_echoes_request_id(self):
        state = json.loads(self.control.read_text())
        rid = 'ab' * 16
        payload = json.dumps({'v': 1, 'nonce': state['nonce'], 'rid': rid, 'op': 'ping'}).encode()
        response = self.raw_exchange(struct.pack('!I', len(payload)) + payload)
        self.assertEqual((response['status'], response['rid']), ('ok', rid))

    def test_response_for_another_request_is_rejected(self):
        state = json.loads(self.control.read_text())
        foreign = {'v': 1, 'nonce': state['nonce'], 'rid': 'cd' * 16, 'status': 'ok'}
        args = SimpleNamespace(channel=str(self.channel), control=str(self.control), op='ping',
                               wait_ready=0, timeout=5, node=None, visited=None, depth=0)
        with mock.patch.object(m, 'read_response', return_value=foreign):
            with self.assertRaisesRegex(m.WorkerError, 'invalid worker response'):
                m.client(args)

    def test_parent_death_interrupts_blocked_helper(self):
        self.process.terminate(); self.process.wait(timeout=4)
        for suffix in ('.req', '.resp', '.lock'): Path(str(self.channel) + suffix).unlink()
        self.control.unlink()
        helper_pid = self.base / 'helper.pid'
        self.helper.write_text('echo $$ > "' + str(helper_pid) + '"\nsleep 30\n')
        launcher = subprocess.Popen([sys.executable, '-c',
            'import subprocess,sys,time,os; subprocess.Popen(sys.argv[1:]+["--parent-pid",str(os.getpid())]); time.sleep(30)',
            sys.executable, '-I', '-B', str(WORKER), 'serve', '--channel', str(self.channel),
            '--control', str(self.control), '--project', str(self.project), '--helper', str(self.helper),
            '--rg', self.rg, '--rg-errors', str(self.rg_errors),
            '--watch-mode', self.watch_mode], stdout=self.log, stderr=self.log)
        query = None
        try:
            self.assertEqual(self.client('ping', extra=['--wait-ready', '5']).returncode, 0)
            worker_pid = json.loads(self.control.read_text())['pid']
            query = subprocess.Popen([sys.executable, '-I', '-B', str(WORKER), 'client',
                '--channel', str(self.channel), '--control', str(self.control), '--op', 'query',
                '--node', str(self.source), '--visited', str(self.visited), '--timeout', '10'],
                stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            deadline = time.monotonic() + 5
            while not helper_pid.exists() and time.monotonic() < deadline: time.sleep(.05)
            self.assertTrue(helper_pid.exists())
            launcher.terminate(); launcher.wait(timeout=2)
            self.assertEqual(query.wait(timeout=6), 2)
            def alive(pid):
                result = subprocess.run(['ps', '-o', 'stat=', '-p', str(pid)], capture_output=True, text=True)
                return result.returncode == 0 and not result.stdout.strip().startswith('Z')
            deadline = time.monotonic() + 6
            while alive(worker_pid) and time.monotonic() < deadline: time.sleep(.05)
            self.assertFalse(alive(worker_pid))
            self.assertFalse(alive(int(helper_pid.read_text())))
        finally:
            if launcher.poll() is None: launcher.terminate(); launcher.wait(timeout=2)
            if query is not None and query.poll() is None: query.kill(); query.wait(timeout=2)

    def test_wrong_expected_parent_rejected_before_marker_creation(self):
        control = self.ipc/'other-control'
        result = subprocess.run([sys.executable, '-I', '-B', str(WORKER), 'serve',
            '--channel', str(self.ipc/'other-socket'), '--control', str(control),
            '--parent-pid', str(os.getppid()), '--project', str(self.project),
            '--helper', str(self.helper), '--rg', self.rg, '--rg-errors', str(self.rg_errors)],
            capture_output=True, timeout=3)
        self.assertEqual(result.returncode, 2)
        self.assertFalse(control.exists())

    def test_terminal_ack_term_cannot_interrupt_helper_reap(self):
        self.assertEqual(self.client('query').returncode, 0)
        self.assertEqual(self.client('validate').returncode, 0)
        helper_pid = self.base/'helper.pid'
        deadline = time.monotonic() + 1
        while not helper_pid.exists() and time.monotonic() < deadline: time.sleep(.01)
        self.assertTrue(helper_pid.exists())
        for _ in range(5):
            self.process.terminate(); time.sleep(.02)
        self.assertEqual(self.process.wait(timeout=6), 0)
        result = subprocess.run(['ps', '-o', 'stat=', '-p', helper_pid.read_text().strip()], capture_output=True, text=True)
        self.assertTrue(result.returncode != 0 or result.stdout.strip().startswith('Z'))

    def test_terminal_cleanup_term_during_interpreter_shutdown_is_quiet(self):
        self.assertEqual(self.client('query').returncode, 0)
        self.assertEqual(self.client('validate').returncode, 0)
        self.assertEqual(self.process.wait(timeout=6), 0)
        self.assertEqual((self.base / 'worker.log').read_text(), '')

    def test_helper_mutation_caught_final(self):
        self.assertEqual(self.client('query').returncode, 0)
        with self.helper.open('a') as stream: stream.write('\n# changed\n')
        self.assertEqual(self.client('validate').returncode, 2)


class InProcessCostTests(unittest.TestCase):
    """The per-query cost must track what the query traversed, not the whole witness set."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(prefix='sw-cost-', dir=str(Path('/tmp').resolve()))
        base = Path(self.tmp.name).resolve()
        self.project = base / 'project'; self.project.mkdir()
        ipc = base / 'ipc'; ipc.mkdir(mode=0o700)
        rg_errors = ipc / 'rg-errors'; rg_errors.touch(mode=0o600)
        self.visited = ipc / 'visited'; self.visited.touch(mode=0o600)
        self.source = self.project / 'entry.ts'; self.source.write_text("import { test } from './support';\n")
        (self.project / 'support.ts').write_text("export { test } from '@playwright/test';\n")
        helper = base / 'helper.sh'; shutil.copyfile(BASE / 'scope-source.sh', helper)
        self.filler = base / 'filler'; self.filler.mkdir()
        self.worker = m.Worker(SimpleNamespace(
            control=str(ipc / 'state'), channel=str(ipc / 's'), parent_pid=os.getppid(),
            engine=str(BASE / 'scope-graph.py'), project=str(self.project), helper=str(helper),
            rg=resolve_rg(), rg_errors=str(rg_errors), watch_mode='off', timeout=30))
        self.addCleanup(self.cleanup)

    def cleanup(self):
        self.worker.close()
        self.tmp.cleanup()

    def query(self):
        self.visited.write_text('')
        return self.worker.evaluate({'v': 1, 'nonce': self.worker.nonce, 'rid': 'e' * 32, 'op': 'query',
                                     'node': str(self.source), 'visited': str(self.visited), 'depth': 0})

    def test_query_and_ping_never_revalidate_the_whole_set(self):
        calls = []
        original = self.worker.graph.witnesses.validate
        self.worker.graph.witnesses.validate = lambda: (calls.append(1), original())[1]
        for _ in range(3):
            self.assertEqual(self.query()[1]['status'], 'found')
        for _ in range(2):
            self.worker.evaluate({'v': 1, 'nonce': self.worker.nonce, 'rid': 'e' * 32, 'op': 'ping'})
        self.assertEqual(calls, [])
        self.worker.evaluate({'v': 1, 'nonce': self.worker.nonce, 'rid': 'e' * 32, 'op': 'checkpoint'})
        self.assertEqual(calls, [1])

    def test_query_stat_count_does_not_grow_with_the_witness_set(self):
        self.query()
        engine = self.worker.engine
        witnesses = self.worker.graph.witnesses.data
        for index in range(3000):
            path = self.filler / f'f{index}.ts'
            path.write_text('')
            witnesses[str(path)] = engine.stamp(str(path))
        calls = []
        original = engine.stamp
        engine.stamp = lambda *args, **kwargs: (calls.append(1), original(*args, **kwargs))[1]
        try:
            self.assertEqual(self.query()[1]['status'], 'found')
        finally:
            engine.stamp = original
        self.assertLess(len(calls), 300, len(calls))

    def test_query_rechecks_a_source_it_read_earlier(self):
        self.assertEqual(self.query()[1]['status'], 'found')
        self.source.write_text("import { test } from './support';\n// edited\n")
        with self.assertRaisesRegex(self.worker.engine.ScopeError, 'scope dependency changed: .*entry.ts'):
            self.query()

    def test_query_rechecks_a_missing_resolution_candidate(self):
        self.assertEqual(self.query()[1]['status'], 'found')
        (self.project / 'support').write_text('')
        with self.assertRaisesRegex(self.worker.engine.ScopeError, 'scope dependency changed: .*/support$'):
            self.query()


class StrictWorkerTests(WorkerTests):
    """The same authenticated worker and mutation contract in strict mode."""
    watch_mode = 'strict'


class WorkerStartupTests(unittest.TestCase):
    def worker_args(self, base):
        errors = base/'errors'; errors.touch(mode=0o600)
        return SimpleNamespace(channel=str(base/'channel'), control=str(base/'control'),
            parent_pid=os.getppid(), engine=str(BASE/'scope-graph.py'), project=str(base),
            helper=str(BASE/'scope-source.sh'), rg=resolve_rg(), rg_errors=str(errors), timeout=30)

    def test_channel_is_private_on_creation_and_umask_restored(self):
        with tempfile.TemporaryDirectory(prefix='sw-', dir=str(Path('/tmp').resolve())) as tmp:
            base = Path(tmp).resolve()
            args = self.worker_args(base)
            original_mkfifo = os.mkfifo
            observed_modes = []
            def observed_mkfifo(path, mode=0o666, *rest, **kwargs):
                original_mkfifo(path, mode, *rest, **kwargs)
                observed_modes.append(os.lstat(path).st_mode & 0o077)
            worker = None
            previous_mask = os.umask(0o022)
            try:
                with mock.patch.object(m.os, 'mkfifo', observed_mkfifo):
                    worker = m.Worker(args)
                restored_mask = os.umask(0o022)
                self.assertEqual(observed_modes, [0, 0])
                self.assertEqual(restored_mask, 0o022)
                self.assertEqual(os.lstat(str(base/'channel') + '.lock').st_mode & 0o077, 0)
            finally:
                os.umask(previous_mask)
                if worker is not None: worker.close()

    def test_existing_channel_is_never_adopted(self):
        with tempfile.TemporaryDirectory(prefix='sw-', dir=str(Path('/tmp').resolve())) as tmp:
            base = Path(tmp).resolve()
            args = self.worker_args(base)
            os.mkfifo(str(base/'channel') + '.req', 0o600)
            with self.assertRaises(FileExistsError):
                m.Worker(args)


@unittest.skipUnless(shutil.which('sandbox-exec'), 'macOS sandbox-exec is unavailable')
class SandboxedScannerTests(unittest.TestCase):
    """Host sandboxes such as the Codex seatbelt deny AF_UNIX sockets; the scanner must still run."""

    def test_scanner_completes_when_socket_networking_is_denied(self):
        with tempfile.TemporaryDirectory(prefix='sw-sbx-', dir=str(Path('/tmp').resolve())) as tmp:
            project = Path(tmp).resolve() / 'project'; project.mkdir()
            (project / 'login.spec.ts').write_text(
                "import { test, expect } from '@playwright/test';\n"
                "test('shows the dashboard', async ({ page }) => {\n"
                "  await page.goto('/');\n"
                "  await expect(page.getByRole('heading')).toBeVisible();\n"
                "});\n")
            # Current Node scanning has no ripgrep worker or socket dependency.
            env = {'PATH': '/usr/bin:/bin:/usr/sbin:/sbin', 'LANG': 'C', 'LC_ALL': 'C'}
            result = subprocess.run(['sandbox-exec', '-p', '(version 1)(allow default)(deny network*)',
                                     '/bin/bash', '-p', str(Path(__file__).resolve().parents[2] / 'skills/e2e-reviewer/scripts/scan.sh'), str(project),
                                     '--format', 'json'],
                                    capture_output=True, text=True, timeout=240, env=env)
            self.assertEqual(result.returncode, 0, result.stderr[-2000:])
            report = json.loads(result.stdout)
            self.assertEqual(report['schema'], 'e2e-skills-node-scan-v1')
            self.assertEqual(report['status'], 'COMPLETE')
            self.assertTrue(report['execution']['complete'])
            self.assertEqual(report['execution']['diagnostics'], [])
            self.assertEqual(report['execution']['exitCode'], 0)
            self.assertEqual(report['findings'], [])
            self.assertNotIn('persistent scope worker', result.stderr)


if __name__ == '__main__': unittest.main()
