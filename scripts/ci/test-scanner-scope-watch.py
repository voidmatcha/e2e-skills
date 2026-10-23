#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Strict local APFS missing-witness monitor contracts."""
import ctypes
import errno
import importlib.util
import os
from pathlib import Path
import select
import stat
import sys
import tempfile
import unittest
from unittest import mock

sys.dont_write_bytecode = True

sys.path.insert(0, str(Path(__file__).resolve().parent))
from lib.legacy_scanner_oracle import legacy_scanner_file

SOURCE = legacy_scanner_file('scope-watch.py')
spec = importlib.util.spec_from_file_location('scope_watch', SOURCE)
m = importlib.util.module_from_spec(spec)
spec.loader.exec_module(m)


class Failure(Exception): pass


def stamp(path, identity_only=False):
    try: value = os.lstat(path)
    except (FileNotFoundError, NotADirectoryError): return None
    result = [value.st_dev, value.st_ino, value.st_mode]
    return result if identity_only else result + [value.st_size, value.st_mtime_ns, value.st_ctime_ns]


class PortableTests(unittest.TestCase):
    def test_unsupported_platform(self):
        with mock.patch.object(m.sys, 'platform', 'linux'):
            self.assertIsNone(m.create(stamp, Failure))

    def test_filesystem_probe_requires_local_apfs(self):
        state = {'name': b'apfs', 'flags': 0x1000}
        def query(fd, pointer):
            value = ctypes.cast(pointer, ctypes.POINTER(m.StatFS64)).contents
            value.f_flags = state['flags']; value.f_fstypename = state['name']
            return 0
        function = mock.Mock(side_effect=query)
        library = mock.Mock(fstatfs64=function)
        with mock.patch.object(m.ctypes, 'CDLL', return_value=library):
            probe = m.filesystem_probe()
        self.assertTrue(probe(0))
        state['flags'] = 0; self.assertFalse(probe(0))
        state['flags'] = 0x1000; state['name'] = b'nfs'; self.assertFalse(probe(0))

    def test_installed_darwin_statfs64_layout(self):
        self.assertEqual(ctypes.sizeof(m.StatFS64), 2168)
        self.assertEqual(m.StatFS64.f_flags.offset, 64)
        self.assertEqual(m.StatFS64.f_fstypename.offset, 72)


@unittest.skipUnless(sys.platform == 'darwin' and hasattr(select, 'kqueue'), 'macOS kqueue required')
class WatchTests(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory(prefix='scope-watch-', dir=str(Path('/tmp').resolve()))
        self.addCleanup(tmp.cleanup)
        self.root = Path(tmp.name)
        fd = os.open(self.root, os.O_RDONLY)
        try:
            if not m.filesystem_probe()(fd): self.skipTest('local APFS required')
        finally: os.close(fd)
        self.counter = mock.Mock(side_effect=stamp)
        self.monitor = m.create(self.counter, Failure)
        self.addCleanup(self.monitor.close)

    def observe(self, relative, expected=None):
        path = str(self.root / relative)
        self.monitor.observe(path, expected)
        return path

    def test_stable_missing_chain_uses_no_stamp_on_validation(self):
        missing = self.observe('absent/deep/file.ts')
        dotted = self.observe('./other.ts')
        self.assertEqual(self.monitor.covered, {missing, dotted})
        self.counter.reset_mock()
        for _ in range(5): self.monitor.validate()
        self.counter.assert_not_called()

    def test_present_witness_keeps_original_stamp(self):
        path = self.root / 'present'; path.write_text('original')
        self.monitor.observe(str(path), stamp(path))
        self.counter.reset_mock(); self.monitor.validate()
        self.counter.assert_called_once_with(str(path), False)
        path.write_text('changed')
        with self.assertRaises(Failure): self.monitor.validate()

    def test_create_and_transient_and_sibling_rejected(self):
        for mode in ('create', 'transient', 'sibling', 'chain'):
            with self.subTest(mode=mode):
                monitor = m.create(stamp, Failure); self.addCleanup(monitor.close)
                target = self.root / ('missing-' + mode)
                monitor.observe(str(target / 'nested' if mode == 'chain' else target), None)
                changed = self.root / 'sibling' if mode == 'sibling' else target
                if mode == 'chain': changed.mkdir()
                else: changed.write_text('x')
                if mode == 'transient': changed.unlink()
                with self.assertRaises(Failure): monitor.validate()
                with self.assertRaises(Failure): monitor.validate()

    def test_registration_creation_race_rejected(self):
        path = self.root / 'raced'
        real = self.monitor.queue
        wrapper = mock.Mock()
        def control(changes, *args):
            result = real.control(changes, *args)
            if changes and changes[0].fflags == self.monitor.all_events:
                path.write_text('created after registration')
            return result
        wrapper.control.side_effect = control
        self.monitor.queue = wrapper
        try:
            with self.assertRaises(Failure): self.monitor.observe(str(path), None)
            self.assertNotIn(str(path), self.monitor.covered)
        finally: self.monitor.queue = real

    def test_open_binding_replacement_rejected(self):
        real = os.fstat
        def mismatched(fd):
            value = real(fd)
            fields = list(value)
            fields[1] += 1
            return os.stat_result(fields)
        with mock.patch.object(m.os, 'fstat', side_effect=mismatched):
            with self.assertRaises(Failure): self.observe('missing')
        self.assertFalse(self.monitor.covered)

    def test_rename_parent_rejected(self):
        parent = self.root / 'parent'; parent.mkdir()
        self.monitor.observe(str(parent / 'missing'), None)
        parent.rename(self.root / 'renamed')
        with self.assertRaises(Failure): self.monitor.validate()

    def test_symlink_traversal_fallback(self):
        target = self.root / 'target'; target.mkdir()
        link = self.root / 'link'; link.symlink_to(target, target_is_directory=True)
        for path in (str(link / 'missing'), str(link / 'missing') + '/.'):
            self.monitor.observe(path, None)
            self.assertIn(path, self.monitor.fallback)
            self.assertNotIn(path, self.monitor.covered)
        dangling = self.root / 'dangling'; dangling.symlink_to(self.root / 'outside')
        raw = str(dangling) + '/.'
        self.monitor.observe(raw, None)
        self.assertIn(raw, self.monitor.fallback)

    def test_hardlink_replacement_fallback(self):
        path = self.root / 'file'; alias = self.root / 'alias'
        path.write_text('same'); os.link(path, alias)
        self.monitor.observe(str(path), stamp(path))
        path.unlink(); path.write_text('same')
        with self.assertRaises(Failure): self.monitor.validate()

    def test_dynamic_observe_and_identity_to_write_upgrade(self):
        nested = self.root / 'nested'; nested.mkdir()
        first = str(nested / 'missing')
        self.monitor.observe(first, None)
        # root directory initially has identity coverage only.
        self.assertEqual(self.monitor.watched[str(self.root)][1], self.monitor.identity_events)
        second = str(self.root / 'another')
        self.monitor.observe(second, None)
        self.assertEqual(self.monitor.watched[str(self.root)][1], self.monitor.all_events)
        self.monitor.observe(first, None)
        self.monitor.validate()
        self.assertEqual(self.monitor.covered, {first, second})

    def test_initial_parent_mask_preserves_coverage_at_descriptor_cap(self):
        left = self.root / 'left'
        right = self.root / 'right'
        left.mkdir(); right.mkdir()
        # One descriptor for each common ancestor (including root), then
        # exactly one for each distinct nearest parent. No upgrade is needed.
        self.monitor.limit = len(self.root.parents) + 3
        paths = {str(left / 'missing'), str(right / 'missing')}
        for path in sorted(paths):
            self.monitor.observe(path, None)
        self.assertEqual(self.monitor.covered, paths)
        self.assertEqual(self.monitor.retired, [])
        self.assertEqual(len(self.monitor.watched), self.monitor.limit)
        self.counter.reset_mock()
        self.monitor.validate()
        self.counter.assert_not_called()

    def test_raw_prebind_metadata_drift_retains_original_fallback(self):
        (self.root / 'entered').mkdir()
        raw = str(self.root) + '/entered/../missing'
        original_stamp = self.monitor.stamp
        seen = []
        def changing_stamp(path, identity_only=False):
            result = original_stamp(path, identity_only)
            if path == str(self.root):
                seen.append(True)
                # First access is traversal probing, second is raw-before.
                if len(seen) == 2: (self.root / 'unrelated').write_text('sibling')
            return result
        with mock.patch.object(self.monitor, 'stamp', side_effect=changing_stamp):
            self.monitor.observe(raw, None)
        self.assertIn(raw, self.monitor.fallback)
        self.assertNotIn(raw, self.monitor.covered)
        self.counter.reset_mock(); self.monitor.validate()
        self.counter.assert_called_once_with(raw, False)

    def test_raw_post_identity_binding_accepts_sibling_metadata_change(self):
        path = str(self.root)
        original_register = self.monitor.register
        def register(directory, mask):
            result = original_register(directory, mask)
            (self.root / 'unrelated').write_text('sibling')
            return result
        with mock.patch.object(self.monitor, 'register', side_effect=register):
            self.assertTrue(self.monitor.bind_raw_prefix(path, path, self.monitor.identity_events))
        self.monitor.validate()

    def test_raw_post_all_binding_rejects_sibling_metadata_change(self):
        path = str(self.root)
        original_register = self.monitor.register
        def register(directory, mask):
            result = original_register(directory, mask)
            (self.root / 'unrelated').write_text('sibling')
            return result
        with mock.patch.object(self.monitor, 'register', side_effect=register):
            with self.assertRaises(Failure):
                self.monitor.bind_raw_prefix(path, path, self.monitor.all_events)
        with self.assertRaises(Failure): self.monitor.validate()

    def test_raw_post_identity_binding_rejects_replacement(self):
        directory = self.root / 'target'; directory.mkdir()
        original_register = self.monitor.register
        def register(path, mask):
            result = original_register(path, mask)
            directory.rename(self.root / 'moved'); directory.mkdir()
            return result
        with mock.patch.object(self.monitor, 'register', side_effect=register):
            with self.assertRaises(Failure):
                self.monitor.bind_raw_prefix(str(directory), str(directory), self.monitor.identity_events)
        with self.assertRaises(Failure): self.monitor.validate()

    def test_raw_parent_ordinary_missing_path_is_covered(self):
        (self.root / 'entered').mkdir()
        path = str(self.root) + '/entered/../missing'
        self.monitor.observe(path, None)
        self.assertIn(path, self.monitor.covered)
        self.counter.reset_mock(); self.monitor.validate()
        self.counter.assert_not_called()

    def test_missing_raw_intermediate_is_not_lexically_collapsed(self):
        (self.root / 'existing').write_text('present at collapsed path')
        path = str(self.root) + '/absent/../existing'
        self.assertIsNone(stamp(path))
        self.monitor.observe(path, None)
        self.assertIn(path, self.monitor.covered)
        self.counter.reset_mock(); self.monitor.validate()
        self.counter.assert_not_called()
        (self.root / 'absent').mkdir()
        with self.assertRaises(Failure): self.monitor.validate()

    def test_missing_raw_intermediate_transient_creation_rejected(self):
        path = str(self.root) + '/absent/deep/../../missing'
        self.monitor.observe(path, None)
        self.assertIn(path, self.monitor.covered)
        (self.root / 'absent').mkdir(); (self.root / 'absent').rmdir()
        with self.assertRaises(Failure): self.monitor.validate()

    def test_exited_raw_ancestor_remains_watched(self):
        entered = self.root / 'entered'; entered.mkdir()
        outer = self.root / 'outer'; outer.mkdir()
        path = str(self.root) + '/entered/../outer/missing'
        self.monitor.observe(path, None)
        self.assertIn(path, self.monitor.covered)
        self.assertIn(str(entered), self.monitor.watched)
        self.assertEqual(self.monitor.watched[str(self.root)][1], self.monitor.identity_events)
        entered.rename(self.root / 'moved')
        entered.symlink_to(outer, target_is_directory=True)
        with self.assertRaises(Failure): self.monitor.validate()

    def test_raw_binding_replacement_race_rejected(self):
        entered = self.root / 'entered'; entered.mkdir()
        outer = self.root / 'outer'; outer.mkdir()
        original_register = self.monitor.register
        def register(path, mask):
            result = original_register(path, mask)
            if path == str(entered): entered.rename(self.root / 'moved')
            return result
        with mock.patch.object(self.monitor, 'register', side_effect=register):
            with self.assertRaises(Failure):
                self.monitor.observe(str(self.root) + '/entered/../outer/missing', None)

    def test_raw_aliases_share_descriptors_and_cap_falls_back(self):
        entered = self.root / 'entered'; entered.mkdir()
        outer = self.root / 'outer'; outer.mkdir()
        first = str(self.root) + '/entered/../outer/missing'
        second = str(self.root) + '/entered/.././outer/another'
        self.monitor.observe(first, None)
        self.assertIn(first, self.monitor.covered)
        bound = len(self.monitor.watched) + len(self.monitor.retired)
        self.monitor.limit = bound
        self.monitor.observe(second, None)
        self.assertIn(second, self.monitor.covered)
        self.assertEqual(len(self.monitor.watched) + len(self.monitor.retired), bound)
        # A separate monitor proves insufficient initial capacity stays conservative.
        limited = m.create(stamp, Failure, limit=1); self.addCleanup(limited.close)
        limited.observe(first, None)
        self.assertIn(first, limited.fallback)
        limited.validate()

    def test_raw_terminal_dot_or_parent_stays_fallback(self):
        for suffix in ('/absent/../.', '/absent/..'):
            path = str(self.root) + suffix
            self.assertIsNone(stamp(path))
            self.monitor.observe(path, None)
            self.assertIn(path, self.monitor.fallback)
            self.assertNotIn(path, self.monitor.covered)
        self.monitor.validate()

    def test_raw_root_parent_traversal_is_physically_bound(self):
        (self.root / 'entered').mkdir()
        path = '/../..' + str(self.root) + '/entered/../missing'
        self.monitor.observe(path, None)
        self.assertIn(path, self.monitor.covered)
        self.monitor.validate()

    def test_raw_non_utf8_directory_name_when_filesystem_supports_it(self):
        entered = self.root / os.fsdecode(b'raw-\xff')
        try: entered.mkdir()
        except OSError as error:
            if error.errno in (errno.EILSEQ, errno.EINVAL): self.skipTest('filesystem rejects non-UTF8 names')
            raise
        path = str(entered) + '/../missing'
        self.monitor.observe(path, None)
        self.assertIn(path, self.monitor.covered)
        self.monitor.validate()

    def test_first_missing_branch_creation_before_and_after_all_binding(self):
        for when in ('before', 'after'):
            with self.subTest(when=when):
                directory = self.root / when; directory.mkdir()
                (directory / 'existing').write_text('present')
                monitor = m.create(stamp, Failure); self.addCleanup(monitor.close)
                register_original = monitor.register
                raw = str(directory) + '/absent/../existing'
                injected = []
                def register(path, mask):
                    trigger = path == str(directory) and mask == monitor.all_events
                    if trigger and when == 'before':
                        (directory / 'absent').mkdir(); injected.append(True)
                    result = register_original(path, mask)
                    if trigger and when == 'after':
                        (directory / 'absent').mkdir(); injected.append(True)
                    return result
                with mock.patch.object(monitor, 'register', side_effect=register):
                    with self.assertRaises(Failure): monitor.observe(raw, None)
                self.assertEqual(injected, [True])
                self.assertNotIn(raw, monitor.covered)

    def test_first_missing_upgrade_preserves_pending_identity_event(self):
        path = str(self.root) + '/absent/../missing'
        register_original = self.monitor.register
        injected = []
        old_fds = []
        def register(directory, mask):
            if directory == str(self.root) and mask == self.monitor.all_events:
                old_fds.append(self.monitor.watched[directory][0])
                original_poll = self.monitor.poll
                def poll():
                    original_poll()
                    if not injected:
                        injected.append(True)
                        os.chmod(directory, os.stat(directory).st_mode)
                with mock.patch.object(self.monitor, 'poll', side_effect=poll):
                    return register_original(directory, mask)
            return register_original(directory, mask)
        with mock.patch.object(self.monitor, 'register', side_effect=register):
            with self.assertRaises(Failure): self.monitor.observe(path, None)
        self.assertEqual(len(old_fds), 1)
        self.assertIn(old_fds[0], self.monitor.retired)
        self.assertNotIn(path, self.monitor.covered)

    def test_first_missing_upgrade_cap_retains_stamp_fallback(self):
        (self.root / 'existing').write_text('present')
        self.monitor.limit = len(self.root.parents) + 1
        path = str(self.root) + '/absent/../existing'
        self.monitor.observe(path, None)
        self.assertIn(path, self.monitor.fallback)
        self.assertNotIn(path, self.monitor.covered)
        self.assertEqual(self.monitor.retired, [])
        self.assertEqual(self.monitor.watched[str(self.root)][1], self.monitor.identity_events)
        self.monitor.validate()
        (self.root / 'absent').mkdir()
        with self.assertRaises(Failure): self.monitor.validate()

    def test_raw_exited_symlink_remains_fallback(self):
        target = self.root / 'target'; target.mkdir()
        link = self.root / 'link'; link.symlink_to(target, target_is_directory=True)
        path = str(self.root) + '/link/../missing'
        self.assertIsNone(stamp(path))
        self.monitor.observe(path, None)
        self.assertIn(path, self.monitor.fallback)
        self.assertNotIn(path, self.monitor.covered)
        self.monitor.validate()

    def test_upgrade_retains_pending_original_registration(self):
        path = str(self.root)
        self.assertTrue(self.monitor.register(path, self.monitor.identity_events))
        old_fd = self.monitor.watched[path][0]
        original_poll = self.monitor.poll
        injected = []
        def poll():
            original_poll()
            if not injected:
                injected.append(True)
                # Deliver an identity event after the pre-upgrade poll but
                # before registration. before/after stamps see the new state.
                os.chmod(path, os.stat(path).st_mode)
        with mock.patch.object(self.monitor, 'poll', side_effect=poll):
            with self.assertRaises(Failure): self.monitor.register(path, self.monitor.all_events)
        self.assertNotEqual(self.monitor.watched[path][0], old_fd)
        self.assertIn(old_fd, self.monitor.retired)
        os.fstat(old_fd)

    def test_upgrade_counts_retained_descriptors_against_cap(self):
        self.monitor.limit = 2
        path = str(self.root)
        self.assertTrue(self.monitor.register(path, self.monitor.identity_events))
        self.assertTrue(self.monitor.register(path, self.monitor.all_events))
        self.assertEqual(len(self.monitor.watched) + len(self.monitor.retired), 2)
        self.assertFalse(self.monitor.register(str(self.root.parent), self.monitor.identity_events))
        self.monitor.validate()

    def test_cleanup_continues_after_individual_close_error(self):
        path = str(self.root)
        self.monitor.register(path, self.monitor.identity_events)
        self.monitor.register(path, self.monitor.all_events)
        fds = [value[0] for value in self.monitor.watched.values()] + self.monitor.retired
        queue_fd = self.monitor.queue.fileno()
        real_close = os.close
        attempted = []
        def close(fd):
            attempted.append(fd)
            real_close(fd)
            if len(attempted) == 1: raise OSError(errno.EBADF, 'injected close error')
        with mock.patch.object(m.os, 'close', side_effect=close): self.monitor.close()
        self.assertEqual(attempted, fds)
        for fd in fds + [queue_fd]:
            with self.assertRaises(OSError): os.fstat(fd)

    def test_limit_and_filesystem_fallback(self):
        for limit in (0, 1):
            monitor = m.create(stamp, Failure, limit=limit); self.addCleanup(monitor.close)
            path = str(self.root / 'missing')
            monitor.observe(path, None)
            self.assertIn(path, monitor.fallback)
            self.assertLessEqual(len(monitor.watched), limit)
            monitor.validate()
        with mock.patch.object(self.monitor, 'probe', return_value=False):
            path = self.observe('unsupported')
        self.assertIn(path, self.monitor.fallback)
        self.monitor.validate()

    def test_fd_pressure_falls_back(self):
        with mock.patch.object(m.os, 'open', side_effect=OSError(errno.EMFILE, 'full')):
            path = self.observe('missing')
        self.assertIn(path, self.monitor.fallback)
        self.monitor.validate()

    def test_poll_failure_permanently_poisons(self):
        path = self.observe('missing')
        queue = self.monitor.queue
        self.monitor.queue = mock.Mock()
        self.monitor.queue.control.side_effect = OSError(errno.EBADF, 'broken')
        with self.assertRaises(Failure): self.monitor.validate()
        self.monitor.queue = queue
        self.assertIn(path, self.monitor.covered)
        with self.assertRaises(Failure): self.monitor.validate()

    def test_unsupported_registration_keeps_fallback(self):
        real = self.monitor.queue
        wrapper = mock.Mock()
        def control(changes, *args):
            if changes: raise OSError(errno.ENOTSUP, 'unsupported')
            return real.control(changes, *args)
        wrapper.control.side_effect = control
        self.monitor.queue = wrapper
        try:
            path = self.observe('missing')
            self.assertIn(path, self.monitor.fallback)
            self.monitor.validate()
        finally: self.monitor.queue = real

    def test_cleanup_and_initial_backend_failure(self):
        self.observe('missing')
        fds = [fd for fd, _ in self.monitor.watched.values()] + self.monitor.retired
        queue_fd = self.monitor.queue.fileno()
        self.monitor.close(); self.monitor.close()
        for fd in fds + [queue_fd]:
            with self.assertRaises(OSError): os.fstat(fd)
        with mock.patch.object(m.select, 'kqueue', side_effect=OSError(errno.EMFILE, 'full')):
            self.assertIsNone(m.create(stamp, Failure))


if __name__ == '__main__': unittest.main()
