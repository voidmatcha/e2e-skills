#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Per-scan lexical metadata cache; each query retains the scanner's ordered DFS."""
import argparse
import hashlib
import importlib.util
import json
import os
import signal
import stat
import subprocess
import sys
import tempfile


class ScopeError(Exception):
    """Scope cannot be established from intact source and cache metadata."""


def stamp(path, identity_only=False):
    try:
        value = os.lstat(path)
    except (FileNotFoundError, NotADirectoryError):
        return None
    identity = [value.st_dev, value.st_ino, value.st_mode]
    return identity if identity_only else identity + [value.st_size, value.st_mtime_ns, value.st_ctime_ns]


class Witnesses:
    def __init__(self, data):
        self.data = data
        self.events = None

    def enable_events(self, factory):
        events = factory(stamp, ScopeError)
        if events is None:
            return
        try:
            for path, expected in self.data.items():
                events.observe(path, expected)
            events.validate()
        except BaseException:
            events.close()
            raise
        self.events = events

    def watch(self, path):
        # Do not normalize '..' through symlinks: the shell resolver follows
        # actual directory traversal, not lexical path normalization.
        if not os.path.isabs(path):
            path = os.getcwd() + '/' + path
        identity_only = False
        while path:
            current = stamp(path, identity_only)
            expected = self.data.get(path)
            if path in self.data:
                size = min(len(expected or []), len(current or []))
                if (expected is None) != (current is None) or (expected is not None and expected[:size] != current[:size]):
                    raise ScopeError('scope dependency changed: ' + path)
                if expected is not None and len(expected) > len(current):
                    current = expected
            self.data[path] = current
            if self.events is not None:
                self.events.observe(path, current)
            parent = os.path.dirname(path)
            if parent == path:
                break
            path = parent
            identity_only = True

    def validate(self):
        if self.events is not None:
            self.events.validate()
            return
        for path, expected in self.data.items():
            if stamp(path, expected is not None and len(expected) == 3) != expected:
                raise ScopeError('scope dependency changed: ' + path)


def unique_object(items):
    result = {}
    for key, value in items:
        if key in result:
            raise ScopeError('duplicate scope cache field: ' + key)
        result[key] = value
    return result


def read_cache(path, project):
    try:
        fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW)
        with os.fdopen(fd, 'r') as stream:
            info = os.fstat(stream.fileno())
            if not stat.S_ISREG(info.st_mode) or info.st_uid != os.getuid() or info.st_nlink != 1 or info.st_mode & 0o077:
                raise ScopeError('scope cache is not private regular storage')
            data = json.load(stream, object_pairs_hook=unique_object)
        if (not isinstance(data, dict) or set(data) != {'version', 'project', 'nodes', 'edges', 'witnesses'}
                or data['version'] != 1 or data['project'] != project):
            raise ScopeError('invalid scope cache identity')
        for name in ('nodes', 'edges', 'witnesses'):
            if not isinstance(data[name], dict):
                raise ScopeError('invalid scope cache map: ' + name)
        for node, record in data['nodes'].items():
            if (not isinstance(record, dict) or 'direct' not in record or type(record['direct']) is not bool
                    or set(record) - {'direct', 'imports'}):
                raise ScopeError('invalid scope node: ' + node)
            if 'imports' in record and (not isinstance(record['imports'], list) or any(not isinstance(x, str) for x in record['imports'])):
                raise ScopeError('invalid scope imports')
        for values in data['edges'].values():
            if not isinstance(values, list) or any(not isinstance(x, str) for x in values):
                raise ScopeError('invalid scope edges')
        for key, value in data['witnesses'].items():
            if not os.path.isabs(key) or (value is not None and (not isinstance(value, list) or len(value) not in (3, 6) or any(type(x) is not int for x in value))):
                raise ScopeError('invalid scope witness')
        return data
    except (OSError, ValueError, TypeError) as error:
        raise ScopeError('cannot read scope cache: ' + str(error)) from error


def write_cache(path, data):
    fd, temporary = tempfile.mkstemp(prefix='scope-write.', dir=os.path.dirname(path))
    try:
        with os.fdopen(fd, 'w') as stream:
            json.dump(data, stream, separators=(',', ':'))
        os.replace(temporary, path)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)


def walk(graph, node, visited, depth, remember):
    # Both this ordering and the shared visited set are observable: a node
    # first reached at depth 32 is not revisited through a later short path.
    if depth > 32 or node in visited:
        return False
    visited.add(node)
    remember(node)
    if graph.direct(node):
        return True
    for item in graph.imports(node):
        for candidate in graph.resolve(node, item):
            if walk(graph, candidate, visited, depth + 1, remember):
                return True
    return False


class Graph:
    def __init__(self, args, data):
        self.args = args
        self.data = data
        self.witnesses = Witnesses(data['witnesses'])
        self.witnesses.validate()
        self.witnesses.watch(args.helper)
        self.witnesses.watch(__file__)
        self.helper = None
        self.changed = False
        with open(args.helper, 'rb') as stream:
            self.paired_paths = hashlib.sha256(stream.read()).hexdigest() == (
                '4d49abb39ebbdeb50d81eaac4c655d8f750c1a3344160edcdd2a0431064c0b65')
        self.witnesses.watch(args.helper)
        self.lexer = self.load_lexer()
        if getattr(args, 'strict_watch', False):
            self.enable_strict_watch()

    def enable_strict_watch(self):
        path = os.path.join(os.path.dirname(__file__), 'scope-watch.py')
        self.witnesses.watch(path)
        spec = importlib.util.spec_from_file_location('scope_watch', path)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        self.witnesses.watch(path)
        self.witnesses.enable_events(module.create)

    def load_lexer(self):
        # Custom ripgrep wrappers and unproved locales retain the original
        # subprocess behavior, including their errors. Never activate later.
        if os.environ.get('E2E_SMELL_RG_BIN'):
            return None
        locales = ('C', 'POSIX', 'C.UTF-8', 'C.utf8')
        for category in ('LC_CTYPE', 'LC_COLLATE'):
            effective = (os.environ.get('LC_ALL') or os.environ.get(category)
                         or os.environ.get('LANG') or 'C')
            if effective not in locales:
                return None
        defaults = ('/opt/homebrew/bin/rg', '/usr/local/bin/rg', '/usr/bin/rg', '/bin/rg')
        if self.args.rg not in defaults and self.args.rg not in map(os.path.realpath, defaults):
            return None
        with open(self.args.helper, 'rb') as stream:
            paired = hashlib.sha256(stream.read()).hexdigest()
        self.witnesses.watch(self.args.helper)
        if paired != '4d49abb39ebbdeb50d81eaac4c655d8f750c1a3344160edcdd2a0431064c0b65':
            return None
        path = os.path.join(os.path.dirname(__file__), 'scope-lexer.py')
        self.witnesses.watch(path)
        if not os.path.exists(path):
            return None
        if not stat.S_ISREG(os.lstat(path).st_mode):
            raise ScopeError('scope lexer is not a regular file')
        spec = importlib.util.spec_from_file_location('scope_lexer', path)
        lexer = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(lexer)
        self.witnesses.watch(path)
        return lexer

    def lexical_metadata(self, node):
        if self.lexer is None:
            return None
        fd = os.open(node, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
        with os.fdopen(fd, 'rb') as stream:
            info = os.fstat(stream.fileno())
            expected = self.witnesses.data[node]
            actual = [info.st_dev, info.st_ino, info.st_mode, info.st_size,
                      info.st_mtime_ns, info.st_ctime_ns]
            if not stat.S_ISREG(info.st_mode) or actual != expected:
                raise ScopeError('scope source changed before lexical read: ' + node)
            source = stream.read(32769)
        self.witnesses.watch(node)
        try:
            return self.lexer.metadata(source)
        except self.lexer.Fallback:
            return None

    def request(self, operation, node, item=''):
        if self.helper is None:
            self.helper = subprocess.Popen(
                ['/bin/bash', '-p', self.args.helper, self.args.project,
                 self.args.rg, self.args.rg_errors], stdin=subprocess.PIPE,
                stdout=subprocess.PIPE, start_new_session=True)
        self.helper.stdin.write(b'\0'.join(os.fsencode(x) for x in (operation, node, item)) + b'\0')
        self.helper.stdin.flush()
        fields = []
        field = bytearray()
        while True:
            char = self.helper.stdout.read(1)
            if not char:
                raise ScopeError('scope source helper terminated before its response')
            if char != b'\0':
                field.extend(char)
            elif field:
                fields.append(os.fsdecode(bytes(field)))
                field.clear()
            else:
                return fields

    def direct(self, node):
        if node not in self.data['nodes']:
            self.witnesses.watch(node)
            info = os.lstat(node)
            if not stat.S_ISREG(info.st_mode):
                raise ScopeError('scope source is not a regular file: ' + node)
            metadata = self.lexical_metadata(node)
            if metadata is not None:
                direct, imports = metadata
                self.witnesses.watch(node)
                self.data['nodes'][node] = {'direct': direct, 'imports': imports}
                self.changed = True
                return direct
            values = self.request('direct', node)
            if values not in (['0'], ['1']):
                raise ScopeError('invalid scope direct-reference response')
            self.witnesses.watch(node)
            self.data['nodes'][node] = {'direct': values == ['1']}
            self.changed = True
        return self.data['nodes'][node]['direct']

    def imports(self, node):
        record = self.data['nodes'][node]
        if 'imports' not in record:
            self.witnesses.watch(node)
            record['imports'] = self.request('imports', node)
            self.witnesses.watch(node)
            self.changed = True
        return record['imports']

    def candidate_paths(self, node, item):
        # Only mirror the shell's simple dirname branch and ASCII relative
        # imports. Platform utility, newline framing, and encoding edge cases
        # continue through the original helper, as do alternate helper scripts.
        self.witnesses.watch(self.args.helper)
        if (not self.paired_paths or not node.isascii() or not item.isascii()
                or not item.startswith(('./', '../')) or '/' not in node
                or node.endswith('/') or node.startswith(('//', '-'))
                or '\n' in node or '\n' in item or '\0' in node or '\0' in item):
            return self.request('candidates', node, item)
        parent = node.rsplit('/', 1)[0]
        if parent.endswith('/'):
            return self.request('candidates', node, item)
        module = (parent or '/') + '/' + item
        base = (module.rsplit('.', 1)[0]
                if module.endswith(('.js', '.jsx', '.mjs', '.cjs')) else module)
        extensions = ('ts', 'tsx', 'js', 'jsx', 'mts', 'mjs', 'cts', 'cjs')
        return ([module] + [base + '.' + suffix for suffix in extensions]
                + [module + '/index.' + suffix for suffix in extensions])

    def resolve(self, node, item):
        key = json.dumps([node, item], separators=(',', ':'))
        if key not in self.data['edges']:
            # Keep all ordered alternatives (including duplicates and missing
            # paths) witnessed around the unchanged shell resolver.
            candidates = self.candidate_paths(node, item)
            for candidate in candidates:
                self.witnesses.watch(candidate)
            values = self.request('resolve', node, item)
            for candidate in candidates:
                self.witnesses.watch(candidate)
            self.data['edges'][key] = values
            self.changed = True
        return self.data['edges'][key]

    def close(self):
        if self.witnesses.events is not None:
            self.witnesses.events.close()
        if self.helper is not None:
            self.helper.stdin.close()
            try:
                self.helper.wait(timeout=2)
            except subprocess.TimeoutExpired:
                os.killpg(self.helper.pid, signal.SIGTERM)
                try:
                    self.helper.wait(timeout=2)
                except subprocess.TimeoutExpired:
                    os.killpg(self.helper.pid, signal.SIGKILL)
                    self.helper.wait()


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--cache', required=True)
    parser.add_argument('--project', required=True)
    parser.add_argument('--helper', required=True)
    parser.add_argument('--rg', required=True)
    parser.add_argument('--rg-errors', required=True)
    parser.add_argument('--errors', required=True)
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument('--init', action='store_true')
    mode.add_argument('--validate', action='store_true')
    parser.add_argument('node', nargs='?')
    parser.add_argument('visited', nargs='?')
    parser.add_argument('depth', nargs='?', type=int, default=0)
    args = parser.parse_args()
    graph = None
    def interrupted(signum, frame):
        raise ScopeError('scope query interrupted by signal ' + str(signum))
    for signum in (signal.SIGINT, signal.SIGTERM):
        signal.signal(signum, interrupted)
    try:
        if args.init:
            data = {'version': 1, 'project': args.project, 'nodes': {}, 'edges': {}, 'witnesses': {}}
            graph = Graph(args, data)
            # Initialization belongs to the scanner's main process, once,
            # before queries. Never silently discard accumulated witnesses.
            fd = os.open(args.cache, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
            with os.fdopen(fd, 'w') as stream:
                json.dump(data, stream, separators=(',', ':'))
            return 0
        data = read_cache(args.cache, args.project)
        graph = Graph(args, data)
        if args.validate:
            return 0
        if args.node is None or args.visited is None:
            raise ScopeError('missing scope query arguments')
        with open(args.visited, encoding=sys.getfilesystemencoding(), errors='surrogateescape', newline='') as stream:
            visited = set(stream.read().split('\n'))
        with open(args.visited, 'a', encoding=sys.getfilesystemencoding(), errors='surrogateescape', newline='') as stream:
            result = walk(graph, args.node, visited, args.depth, lambda node: stream.write(node + '\n'))
        graph.witnesses.validate()
        if graph.changed:
            write_cache(args.cache, data)
        return 0 if result else 3
    except (ScopeError, OSError, ValueError) as error:
        message = 'error: scope graph metadata invalid: ' + str(error)
        print(message, file=sys.stderr)
        try:
            with open(args.errors, 'a') as stream:
                stream.write(message + '\n')
        except OSError:
            # Parent also records any query exit > 1 in its error marker.
            pass
        return 2
    finally:
        if graph is not None:
            graph.close()


if __name__ == '__main__':
    sys.exit(main())
