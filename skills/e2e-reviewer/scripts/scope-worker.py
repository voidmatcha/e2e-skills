#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Persistent scope engine with fail-closed private scanner IPC.

The channel is a request FIFO, a response FIFO and a lock file in the private
scanner directory. FIFOs, unlike AF_UNIX sockets, are allowed by host sandboxes
such as the Codex macOS seatbelt, which denies socket bind/connect by default.
Clients serialize on the lock; a random request id binds each response to its
request, so an answer left for a client that gave up can never satisfy another.
"""
import sys
sys.dont_write_bytecode = True
import argparse
import errno
import fcntl
import importlib.util
import json
import os
from pathlib import Path
import secrets
import select
import signal
import stat
import struct
import threading
import time
from types import SimpleNamespace

MAX_FRAME = 65536
IO_TIMEOUT = 5


class WorkerError(Exception): pass


def unique_object(items):
    result = {}
    for key, value in items:
        if key in result: raise WorkerError('duplicate protocol field')
        result[key] = value
    return result


def signature(path):
    value = os.lstat(path)
    return (value.st_dev, value.st_ino, value.st_mode, value.st_size, value.st_mtime_ns, value.st_ctime_ns)


def private_parent(path):
    parent = os.path.dirname(os.path.abspath(path))
    if not os.path.isabs(path) or os.path.dirname(path) != parent:
        raise WorkerError('IPC paths must use the canonical absolute parent')
    value = os.lstat(parent)
    if (not stat.S_ISDIR(value.st_mode) or value.st_uid != os.getuid() or value.st_mode & 0o077
            or os.path.realpath(parent) != parent):
        raise WorkerError('IPC parent is not a private physical directory')
    return parent, (value.st_dev, value.st_ino, value.st_mode)


def private_regular(fd):
    value = os.fstat(fd)
    if (not stat.S_ISREG(value.st_mode) or value.st_uid != os.getuid()
            or value.st_mode & 0o077 or value.st_nlink != 1):
        raise WorkerError('control or visited file is not private regular storage')
    return value


def channel_paths(channel):
    return {'request': channel + '.req', 'response': channel + '.resp', 'lock': channel + '.lock'}


def channel_identity(paths):
    identity = []
    for name, check in (('request', stat.S_ISFIFO), ('response', stat.S_ISFIFO), ('lock', stat.S_ISREG)):
        value = os.lstat(paths[name])
        if (not check(value.st_mode) or value.st_uid != os.getuid() or value.st_mode & 0o077
                or value.st_nlink != 1):
            raise WorkerError('IPC channel is not private storage')
        identity.append((value.st_dev, value.st_ino, value.st_mode))
    return tuple(identity)


def open_checked(path, flags, expected):
    fd = os.open(path, flags | os.O_NOFOLLOW)
    value = os.fstat(fd)
    if (value.st_dev, value.st_ino, value.st_mode) != expected:
        os.close(fd)
        raise WorkerError('IPC channel identity changed')
    return fd


def read_exact(fd, count, deadline):
    chunks = bytearray()
    while len(chunks) < count:
        remaining = deadline - time.monotonic()
        if remaining <= 0: raise WorkerError('protocol read timed out')
        if not select.select([fd], [], [], remaining)[0]: continue
        try: part = os.read(fd, count - len(chunks))
        except BlockingIOError: continue
        if not part: raise WorkerError('premature protocol EOF')
        chunks.extend(part)
    return bytes(chunks)


def write_all(fd, data, deadline):
    view = memoryview(data)
    while view:
        remaining = deadline - time.monotonic()
        if remaining <= 0: raise WorkerError('protocol write timed out')
        if not select.select([], [fd], [], remaining)[1]: continue
        try: view = view[os.write(fd, view):]
        except BlockingIOError: continue


def decode(payload):
    result = json.loads(payload.decode('utf-8'), object_pairs_hook=unique_object)
    if not isinstance(result, dict): raise WorkerError('protocol frame must be an object')
    return result


def frame_length(header):
    length = struct.unpack('!I', header)[0]
    if not 0 < length <= MAX_FRAME: raise WorkerError('invalid protocol frame length')
    return length


def encode(data):
    payload = json.dumps(data, separators=(',', ':'), ensure_ascii=True).encode()
    if not 0 < len(payload) <= MAX_FRAME: raise WorkerError('response exceeds protocol limit')
    return struct.pack('!I', len(payload)) + payload


def load_engine(path):
    spec = importlib.util.spec_from_file_location('scope_worker_engine', path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class Worker:
    def __init__(self, args):
        self.args = args
        self.parent, self.parent_identity = private_parent(args.control)
        if private_parent(args.channel)[0] != self.parent:
            raise WorkerError('channel and control must share the private directory')
        self.paths = channel_paths(args.channel)
        if type(args.parent_pid) is not int or args.parent_pid <= 1 or os.getppid() != args.parent_pid:
            raise WorkerError('expected scanner parent is no longer the worker parent')
        self.owner_pid = args.parent_pid
        self.nonce = secrets.token_hex(16)
        self.engine = load_engine(args.engine)
        self.graph = None
        self.request_fd = self.request_hold = None
        self.marker_identity = self.channel_identity = None
        self.stop_watchdog = threading.Event()
        self.poisoned = False
        # No existing marker can be adopted, even after a previous worker died.
        fd = os.open(args.control, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
        with os.fdopen(fd, 'w') as stream:
            json.dump({'v': 1, 'pid': os.getpid(), 'nonce': self.nonce}, stream)
        self.marker_identity = signature(args.control)
        data = {'version': 1, 'project': args.project, 'nodes': {}, 'edges': {}, 'witnesses': {}}
        self.graph = self.engine.Graph(SimpleNamespace(helper=args.helper, project=args.project,
                                                       rg=args.rg, rg_errors=args.rg_errors,
                                                       strict_watch=getattr(args, 'watch_mode', 'off') == 'strict'), data)
        self.graph.witnesses.watch(__file__)
        # Create every channel node private from its first visible instant.
        # Exclusive creation means an existing channel can never be adopted.
        previous_umask = os.umask(0o077)
        try:
            os.mkfifo(self.paths['request'], 0o600)
            os.mkfifo(self.paths['response'], 0o600)
            os.close(os.open(self.paths['lock'], os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600))
        finally:
            os.umask(previous_umask)
        self.channel_identity = channel_identity(self.paths)
        self.request_fd = open_checked(self.paths['request'], os.O_RDONLY | os.O_NONBLOCK, self.channel_identity[0])
        # Holding a writer keeps the request FIFO from reporting EOF between clients.
        self.request_hold = open_checked(self.paths['request'], os.O_WRONLY | os.O_NONBLOCK, self.channel_identity[0])
        self.watchdog = threading.Thread(target=self.watch_parent, daemon=True)
        self.watchdog.start()

    def watch_parent(self):
        while not self.stop_watchdog.wait(0.25):
            if os.getppid() != self.owner_pid:
                os.kill(os.getpid(), signal.SIGTERM)
                return

    def identities(self):
        parent, identity = private_parent(self.args.control)
        if parent != self.parent or identity != self.parent_identity:
            raise WorkerError('worker private directory identity changed')
        if signature(self.args.control) != self.marker_identity:
            raise WorkerError('worker continuity marker changed')
        if channel_identity(self.paths) != self.channel_identity:
            raise WorkerError('worker channel identity changed')

    def check_request(self, request):
        if type(request.get('v')) is not int or request['v'] != 1 or request.get('nonce') != self.nonce:
            raise WorkerError('invalid protocol identity')
        if not isinstance(request.get('rid'), str) or len(request['rid']) != 32:
            raise WorkerError('invalid request id')
        operation = request.get('op')
        expected = {'v', 'nonce', 'rid', 'op'}
        if operation == 'query': expected |= {'node', 'visited', 'depth'}
        elif operation not in ('ping', 'checkpoint', 'validate'): raise WorkerError('unknown operation')
        if set(request) != expected: raise WorkerError('invalid operation fields')
        if operation == 'query':
            if (not isinstance(request['node'], str) or not request['node'] or '\0' in request['node']
                    or not isinstance(request['visited'], str) or '\0' in request['visited']
                    or type(request['depth']) is not int):
                raise WorkerError('invalid query fields')
        return operation

    def visited(self, request):
        path = request['visited']
        if os.path.dirname(path) != self.parent or not os.path.isabs(path):
            raise WorkerError('visited file is outside the private scanner directory')
        fd = os.open(path, os.O_RDWR | os.O_APPEND | os.O_NOFOLLOW)
        try:
            info = private_regular(fd)
            path_info = os.lstat(path)
            if (path_info.st_dev, path_info.st_ino) != (info.st_dev, info.st_ino):
                raise WorkerError('visited file identity changed before query')
            stream = os.fdopen(fd, 'r+', encoding=sys.getfilesystemencoding(), errors='surrogateescape', newline='')
        except BaseException:
            os.close(fd)
            raise
        with stream:
            visited = set(stream.read().split('\n'))
            result = self.engine.walk(self.graph, request['node'], visited, request['depth'], lambda node: stream.write(node + '\n'))
            stream.flush()
            after = private_regular(stream.fileno())
            current = os.lstat(path)
            if (not stat.S_ISREG(current.st_mode)
                    or (current.st_dev, current.st_ino) != (after.st_dev, after.st_ino)):
                raise WorkerError('visited file identity changed during query')
        return result

    def evaluate(self, request):
        self.identities()
        operation = self.check_request(request)
        # A query re-stamps every source and resolution candidate it
        # traversed, so its answer matches the files it read. A path it did
        # not re-read, such as an ancestor directory, can change unseen until
        # the next checkpoint, so some findings may print before the scan
        # fails there. The complete witness set, including ancestor
        # directories, is validated at each scanner checkpoint and by the
        # terminal validate before any Summary.
        # Re-validating the whole set around every query made large scans
        # quadratic without adding a guarantee: stamps carry ctime, which a
        # modify-and-restore cannot reset, and changes that come and go between
        # operations were never caught deterministically (strict watch mode
        # remains the transient guarantee). No memoization of answers.
        if operation == 'query':
            self.graph.touched = set()
            result = self.visited(request)
            self.graph.witnesses.recheck(self.graph.touched)
            status = 'found' if result else 'absent'
        elif operation in ('checkpoint', 'validate'):
            self.graph.witnesses.validate()
            status = 'ok'
        else:
            status = 'ok'
        self.identities()
        if os.path.exists(self.args.rg_errors) and os.path.getsize(self.args.rg_errors):
            raise WorkerError('lexical helper recorded a runtime failure')
        return operation, {'v': 1, 'nonce': self.nonce, 'rid': request['rid'], 'status': status}

    def receive(self):
        deadline = time.monotonic() + IO_TIMEOUT
        length = frame_length(read_exact(self.request_fd, 4, deadline))
        payload = read_exact(self.request_fd, length, deadline)
        # Clients hold the lock for a whole exchange, so any byte already
        # queued after the frame came from the same client.
        try: trailing = os.read(self.request_fd, 1)
        except BlockingIOError: trailing = b''
        if trailing: raise WorkerError('trailing protocol bytes')
        return decode(payload)

    def respond(self, data):
        frame = encode(data)
        try:
            fd = open_checked(self.paths['response'], os.O_WRONLY | os.O_NONBLOCK, self.channel_identity[1])
        except OSError as error:
            if error.errno == errno.ENXIO: raise WorkerError('client stopped waiting for its response')
            raise
        try: write_all(fd, frame, time.monotonic() + IO_TIMEOUT)
        finally: os.close(fd)

    def run(self):
        while not self.poisoned:
            if not select.select([self.request_fd], [], [], 1)[0]:
                self.identities()
                continue
            rid = None
            try:
                request = self.receive()
                rid = request.get('rid') if isinstance(request.get('rid'), str) else None
                signal.alarm(self.args.timeout)
                operation, response = self.evaluate(request)
                signal.alarm(0)
                self.respond(response)
                if operation == 'validate': return 0
            except BaseException as error:
                signal.alarm(0)
                self.poisoned = True
                try:
                    error_response = {'v': 1, 'nonce': self.nonce, 'status': 'error', 'error': str(error)[:4000]}
                    if rid is not None: error_response['rid'] = rid
                    self.respond(error_response)
                except BaseException:
                    pass
                raise
        raise WorkerError('poisoned worker')

    def close(self, restore_signals=True):
        self.stop_watchdog.set()
        # Parent EXIT can send TERM immediately after the terminal ACK. Finish
        # the bounded helper-group reap even when termination signals repeat.
        signals = (signal.SIGINT, signal.SIGTERM, signal.SIGALRM)
        previous = {number: signal.signal(number, signal.SIG_IGN) for number in signals}
        signal.alarm(0)
        try:
            for fd in (self.request_fd, self.request_hold):
                if fd is not None: os.close(fd)
            self.request_fd = self.request_hold = None
            if self.graph is not None: self.graph.close()
        finally:
            if restore_signals:
                for number, handler in previous.items(): signal.signal(number, handler)
        # Keep marker/channel nodes until parent cleanup. This prevents restart
        # and lets the successful terminal client's postcheck pin identities.


def read_control(path):
    private_parent(path)
    before = signature(path)
    fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW)
    with os.fdopen(fd) as stream:
        private_regular(stream.fileno())
        if os.fstat(stream.fileno()).st_size > MAX_FRAME: raise WorkerError('oversized control marker')
        data = json.load(stream, object_pairs_hook=unique_object)
    if signature(path) != before: raise WorkerError('control marker changed during read')
    if (not isinstance(data, dict) or set(data) != {'v', 'pid', 'nonce'} or type(data['v']) is not int or data['v'] != 1
            or type(data['pid']) is not int or data['pid'] <= 0 or not isinstance(data['nonce'], str)
            or len(data['nonce']) != 32 or any(c not in '0123456789abcdef' for c in data['nonce'])):
        raise WorkerError('invalid control marker')
    return data, before


def reader_present(path, expected):
    """True while some process holds the request FIFO's read end.

    Only the worker opens that end, and the kernel drops it when the worker
    exits, so this survives zombies and reused PIDs where a PID probe would not.
    """
    try: fd = open_checked(path, os.O_WRONLY | os.O_NONBLOCK, expected)
    except OSError as error:
        if error.errno == errno.ENXIO: return False
        raise
    os.close(fd)
    return True


def read_response(fd, deadline, alive):
    """Read one frame from a nonblocking response FIFO, then require EOF.

    Before the worker opens its end, reads return EOF immediately, so an
    empty read only means "not answered yet" until the first byte arrives.
    """
    data = bytearray()
    while True:
        if time.monotonic() >= deadline: raise WorkerError('worker response timed out')
        select.select([fd], [], [], 0.05)
        try: part = os.read(fd, MAX_FRAME + 5)
        except BlockingIOError: continue
        if part:
            data.extend(part)
            if len(data) > MAX_FRAME + 4: raise WorkerError('response exceeds protocol limit')
            continue
        if data: break
        if not alive(): raise WorkerError('worker is not running')
        time.sleep(0.02)
    if len(data) < 4: raise WorkerError('premature protocol EOF')
    length = frame_length(bytes(data[:4]))
    if len(data) != 4 + length: raise WorkerError('trailing or missing protocol bytes')
    return decode(bytes(data[4:]))


def client(args):
    paths = channel_paths(args.channel)
    parent, parent_identity = private_parent(args.channel)
    if private_parent(args.control)[0] != parent: raise WorkerError('mismatched IPC directory')
    ready_deadline = time.monotonic() + args.wait_ready
    deadline = time.monotonic() + args.timeout
    rid = secrets.token_hex(16)
    while True:
        lock_fd = response_fd = None
        try:
            identity = channel_identity(paths)
            state, marker_identity = read_control(args.control)
            lock_fd = open_checked(paths['lock'], os.O_RDWR, identity[2])
            alive = lambda: reader_present(paths['request'], identity[0])
            while True:
                try:
                    fcntl.flock(lock_fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
                    break
                except BlockingIOError:
                    if time.monotonic() >= deadline: raise WorkerError('IPC channel lock timed out')
                    if not alive(): raise WorkerError('worker is not running')
                    time.sleep(0.02)
            response_fd = open_checked(paths['response'], os.O_RDONLY | os.O_NONBLOCK, identity[1])
            try:
                request_fd = open_checked(paths['request'], os.O_WRONLY | os.O_NONBLOCK, identity[0])
            except OSError as error:
                if error.errno == errno.ENXIO: raise ConnectionRefusedError('worker is not reading requests')
                raise
            break
        except (FileNotFoundError, ConnectionRefusedError):
            for fd in (response_fd, lock_fd):
                if fd is not None: os.close(fd)
            if args.wait_ready and args.op == 'ping' and time.monotonic() < ready_deadline:
                time.sleep(0.05)
                continue
            raise
        except BaseException:
            for fd in (response_fd, lock_fd):
                if fd is not None: os.close(fd)
            raise
    try:
        request = {'v': 1, 'nonce': state['nonce'], 'rid': rid, 'op': args.op}
        if args.op == 'query': request.update(node=args.node, visited=args.visited, depth=args.depth)
        try: write_all(request_fd, encode(request), deadline)
        finally: os.close(request_fd)
        response = read_response(response_fd, deadline, alive)
    finally:
        os.close(response_fd)
        os.close(lock_fd)
    if (private_parent(args.control) != (parent, parent_identity)
            or signature(args.control) != marker_identity or channel_identity(paths) != identity):
        raise WorkerError('IPC identity changed during request')
    status = response.get('status')
    expected = {'v', 'nonce', 'rid', 'status'}
    if status == 'error':
        expected = {'v', 'nonce', 'status', 'error'} | ({'rid'} if 'rid' in response else set())
    if (set(response) != expected or type(response.get('v')) is not int or response['v'] != 1
            or response.get('nonce') != state['nonce'] or response.get('rid', rid) != rid):
        raise WorkerError('invalid worker response')
    if status == 'error': raise WorkerError('worker rejected request: ' + str(response.get('error')))
    if args.op == 'query':
        if status == 'found': return 0
        if status == 'absent': return 3
    elif status == 'ok': return 0
    raise WorkerError('unexpected operation response')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('mode', choices=['serve', 'client'])
    parser.add_argument('--channel', required=True)
    parser.add_argument('--control', required=True)
    parser.add_argument('--engine', default=str(Path(__file__).with_name('scope-graph.py')))
    parser.add_argument('--parent-pid', type=int)
    parser.add_argument('--project')
    parser.add_argument('--helper')
    parser.add_argument('--rg')
    parser.add_argument('--rg-errors')
    parser.add_argument('--timeout', type=int, default=1800)
    parser.add_argument('--op', choices=['ping', 'query', 'checkpoint', 'validate'], default='ping')
    parser.add_argument('--wait-ready', type=float, default=0)
    parser.add_argument('--repeat', type=int, default=None)
    parser.add_argument('--watch-mode', choices=['off', 'strict'], default='off')
    parser.add_argument('--node')
    parser.add_argument('--visited')
    parser.add_argument('--depth', type=int, default=0)
    args = parser.parse_args()
    worker = None
    def interrupted(signum, frame): raise WorkerError('worker interrupted by signal ' + str(signum))
    try:
        if args.timeout < 1: raise WorkerError('positive workload timeout required')
        if args.watch_mode != 'off' and args.mode != 'serve':
            raise WorkerError('--watch-mode strict requires serve')
        if args.repeat is not None and (args.mode != 'client' or args.op != 'ping' or not 1 <= args.repeat <= 64):
            raise WorkerError('--repeat requires client ping and a count from 1 through 64')
        if args.mode == 'client':
            # Each iteration is the original authenticated request, including
            # fresh client identities; ping itself only proves liveness.
            for _ in range(args.repeat or 1):
                result = client(args)
                if result != 0: return result
            return 0
        if not all((args.project, args.helper, args.rg, args.rg_errors)): raise WorkerError('missing serve arguments')
        for signum in (signal.SIGINT, signal.SIGTERM, signal.SIGALRM): signal.signal(signum, interrupted)
        worker = Worker(args)
        return worker.run()
    except BaseException as error:
        print('error: persistent scope worker: ' + str(error), file=sys.stderr)
        return 2
    finally:
        # The standalone server has finished handling requests. Parent EXIT
        # may still send TERM during interpreter teardown after close returns.
        if worker is not None: worker.close(restore_signals=False)


if __name__ == '__main__': sys.exit(main())
