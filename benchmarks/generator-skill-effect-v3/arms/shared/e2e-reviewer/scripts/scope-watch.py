#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Opt-in strict missing-path acceleration on local macOS APFS only.

Directory events reject even transient or sibling changes. Present witnesses
always retain their original stamp checks. No compiler or SDK is needed at run
time; the ABI below follows Darwin sys/mount.h __DARWIN_STRUCT_STATFS64.
"""
import ctypes
import errno
import os
import select
import stat
import sys
from collections import OrderedDict


class StatFS64(ctypes.Structure):
    _fields_ = [
        ('f_bsize', ctypes.c_uint32), ('f_iosize', ctypes.c_int32),
        ('f_blocks', ctypes.c_uint64), ('f_bfree', ctypes.c_uint64),
        ('f_bavail', ctypes.c_uint64), ('f_files', ctypes.c_uint64),
        ('f_ffree', ctypes.c_uint64), ('f_fsid', ctypes.c_int32 * 2),
        ('f_owner', ctypes.c_uint32), ('f_type', ctypes.c_uint32),
        ('f_flags', ctypes.c_uint32), ('f_fssubtype', ctypes.c_uint32),
        ('f_fstypename', ctypes.c_char * 16),
        ('f_mntonname', ctypes.c_char * 1024),
        ('f_mntfromname', ctypes.c_char * 1024),
        ('f_flags_ext', ctypes.c_uint32), ('f_reserved', ctypes.c_uint32 * 7),
    ]


def filesystem_probe():
    libc = ctypes.CDLL('/usr/lib/libSystem.B.dylib', use_errno=True)
    function = libc.fstatfs64
    function.argtypes = [ctypes.c_int, ctypes.POINTER(StatFS64)]
    function.restype = ctypes.c_int
    def local_apfs(fd):
        value = StatFS64()
        if function(fd, ctypes.byref(value)):
            raise OSError(ctypes.get_errno(), 'fstatfs64 failed')
        return bool(value.f_flags & 0x1000) and value.f_fstypename == b'apfs'
    return local_apfs


def create(stamp, error_type, limit=2048):
    if sys.platform != 'darwin' or not hasattr(select, 'kqueue'):
        return None
    if type(limit) is not int or not 0 <= limit <= 2048:
        raise ValueError('watch descriptor limit must be from 0 through 2048')
    try:
        probe = filesystem_probe()
        queue = select.kqueue()
    except (OSError, AttributeError):
        return None
    return Monitor(stamp, error_type, limit, queue, probe)


class Monitor:
    def __init__(self, stamp, error_type, limit, queue, probe):
        self.stamp = stamp
        self.error_type = error_type
        self.limit = limit
        self.queue = queue
        self.probe = probe
        self.fallback = OrderedDict()
        self.covered = set()
        self.watched = {}
        self.retired = []
        self.poisoned = False
        self.closed = False
        self.identity_events = (select.KQ_NOTE_DELETE | select.KQ_NOTE_RENAME |
                                select.KQ_NOTE_REVOKE | select.KQ_NOTE_ATTRIB)
        self.all_events = (self.identity_events | select.KQ_NOTE_WRITE |
                           select.KQ_NOTE_EXTEND | select.KQ_NOTE_LINK)

    def fail(self, message):
        self.poisoned = True
        raise self.error_type('scope watch failure: ' + message)

    def poll(self):
        if self.poisoned or self.closed:
            self.fail('monitor unavailable')
        try:
            events = self.queue.control(None, 1, 0)
        except Exception as error:
            self.fail('event polling failed: ' + str(error))
        if events:
            self.fail('watched directory changed')

    def register(self, path, mask):
        old = self.watched.get(path)
        if old and not mask & ~old[1]:
            return True
        self.poll()
        fd = None
        try:
            before = self.stamp(path)
            if before is None or not stat.S_ISDIR(before[2]):
                return False
            if len(self.watched) + len(self.retired) >= self.limit:
                return False
            if old:
                mask |= old[1]
            # Never modify a registered knote: a pending event must survive a
            # mask upgrade. Bind a second descriptor and retain the original
            # registration until close; both descriptors count toward the cap.
            fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
            value = os.fstat(fd)
            actual = [value.st_dev, value.st_ino, value.st_mode,
                      value.st_size, value.st_mtime_ns, value.st_ctime_ns]
            if actual != before:
                self.fail('directory changed while opening: ' + path)
            if not self.probe(fd):
                return False
            self.queue.control([select.kevent(fd, filter=select.KQ_FILTER_VNODE,
                flags=select.KQ_EV_ADD | select.KQ_EV_CLEAR, fflags=mask)], 0, 0)
            if self.stamp(path) != before:
                self.fail('directory changed while registering: ' + path)
            if old:
                self.retired.append(old[0])
            self.watched[path] = (fd, mask)
            fd = None
            self.poll()
            return True
        except OSError as error:
            # A failed new registration never grants coverage. Existing watches
            # remain installed, including the old mask of an unsuccessful upgrade.
            if error.errno in (errno.EMFILE, errno.ENFILE, errno.ENOSPC, errno.ENOMEM,
                               errno.ENOTSUP, errno.EINVAL, errno.EACCES, errno.ENOENT,
                               errno.ENOTDIR, errno.ELOOP):
                return False
            self.fail('directory registration failed: ' + str(error))
        finally:
            if fd is not None:
                os.close(fd)

    def bind_raw_prefix(self, raw_prefix, canonical, mask):
        # Share a canonical descriptor only after proving that this exact raw
        # traversal reaches the same ordinary directory, before and after bind.
        self.poll()
        raw_before = self.stamp(raw_prefix)
        canonical_before = self.stamp(canonical)
        if raw_before is None or not stat.S_ISDIR(raw_before[2]):
            return False
        if raw_before != canonical_before:
            # No binding has been established: retain the original witness
            # instead of rejecting unrelated ancestor metadata churn.
            return False
        if not self.register(canonical, mask):
            return False
        # Ancestor identity watches permit unrelated sibling writes. Nearest
        # parent ALL watches retain the strict full-metadata comparison.
        identity_only = mask == self.identity_events
        width = 3 if identity_only else 6
        if (self.stamp(raw_prefix, identity_only) != raw_before[:width] or
                self.stamp(canonical, identity_only) != canonical_before[:width]):
            self.fail('raw/canonical prefix changed during binding')
        self.poll()
        return True

    def cover_raw_parent(self, path):
        if not path.startswith('/') or '//' in path or path.endswith('/'):
            return False
        parts = path.split('/')[1:]
        # Terminal traversal components retain the original stamp fallback.
        if parts[-1] in ('.', '..'):
            return False
        raw = ''
        stack = []
        if not self.bind_raw_prefix('/', '/', self.identity_events):
            return False
        for index, part in enumerate(parts[:-1]):
            prior_raw = raw or '/'
            raw += '/' + part
            # Prove physical traversal before changing the canonical stack.
            # Exited directories retain their identity watches after '..'.
            value = self.stamp(raw)
            if value is None:
                # A missing component stops kernel traversal. Never collapse
                # absent/../existing into an existing canonical destination.
                if not self.bind_raw_prefix(prior_raw, '/' + '/'.join(stack), self.all_events):
                    return False
                if self.stamp(raw) is not None:
                    self.fail('missing raw prefix appeared')
                self.poll()
                return True
            if not stat.S_ISDIR(value[2]):
                return False
            if part == '..':
                if stack:
                    stack.pop()
            elif part != '.':
                stack.append(part)
            canonical = '/' + '/'.join(stack)
            mask = self.all_events if index == len(parts) - 2 else self.identity_events
            if not self.bind_raw_prefix(raw, canonical, mask):
                return False
        return True

    def cover(self, path):
        if isinstance(path, str) and '..' in path.split('/'):
            return self.cover_raw_parent(path)
        if (not isinstance(path, str) or not path.startswith('/') or '//' in path
                or path.endswith('/') or '..' in path.split('/')):
            return False
        parts = [part for part in path.split('/')[1:] if part != '.']
        ancestors = ['/']
        current = ''
        parent_parts = parts if path.split('/')[-1] == '.' else parts[:-1]
        for part in parent_parts:
            current += '/' + part
            value = self.stamp(current)
            if value is None:
                break
            if not stat.S_ISDIR(value[2]):
                return False
            ancestors.append(current)
        for ancestor in ancestors[:-1]:
            if not self.register(ancestor, self.identity_events):
                return False
        return self.register(ancestors[-1], self.all_events)

    def observe(self, path, expected):
        self.poll()
        try:
            identity = expected is not None and len(expected) == 3
            if self.stamp(path, identity) != expected:
                self.fail('witness changed: ' + path)
            # Put the conservative path in place before attempting coverage.
            self.fallback[path] = expected
            self.covered.discard(path)
            if expected is None and self.cover(path):
                if self.stamp(path) is not None:
                    self.fail('missing witness appeared: ' + path)
                self.poll()
                del self.fallback[path]
                self.covered.add(path)
            self.poll()
        except Exception as error:
            self.poisoned = True
            if isinstance(error, self.error_type):
                raise
            self.fail('observing witness failed: ' + str(error))

    def validate(self):
        self.poll()
        try:
            for path, expected in self.fallback.items():
                if self.stamp(path, expected is not None and len(expected) == 3) != expected:
                    self.fail('witness changed: ' + path)
            self.poll()
        except Exception as error:
            self.poisoned = True
            if isinstance(error, self.error_type):
                raise
            self.fail('validating witnesses failed: ' + str(error))

    def close(self):
        if self.closed:
            return
        self.closed = True
        self.poisoned = True
        try:
            for fd in [value[0] for value in self.watched.values()] + self.retired:
                try:
                    os.close(fd)
                except OSError:
                    pass
        finally:
            self.watched.clear()
            self.retired.clear()
            self.queue.close()
