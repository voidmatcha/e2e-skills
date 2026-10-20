#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Offline manifest, restore, corruption and archive containment regressions."""
import contextlib
import hashlib
import importlib.util
import io
import json
import os
from pathlib import Path
import subprocess
import tarfile
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[2]
SPEC = importlib.util.spec_from_file_location('benchmark_fetch', ROOT / 'scripts/dev/fetch-benchmark-evidence.py')
FETCH = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(FETCH)


def sha(data):
    return hashlib.sha256(data).hexdigest()


class RestoreTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory(prefix='benchmark-fetch-test-')
        self.addCleanup(self.temporary.cleanup)
        self.base = Path(self.temporary.name).resolve()
        content = b'#!/bin/sh\nexit 0\n'
        name = 'benchmarks/example/run.sh'
        record = dict(path=name, git_blob=hashlib.sha1(b'blob ' + str(len(content)).encode() + b'\0' + content).hexdigest(),
                      mode='100755', source_bytes=len(content), export_bytes=len(content),
                      source_sha256=sha(content), export_sha256=sha(content), transform=None)
        self.metadata = json.dumps(dict(schema_version=1, status='COMPLETE', source_commit='a'*40,
                                       tracked_entry_count=1, exported_file_count=1, exported_bytes=len(content),
                                       symlink_count=0, excluded=[], files=[record])).encode()
        self.manifest = dict(schema_version=2, dataset='example/evidence', repo_type='dataset', revision='b'*40,
                             source_commit='a'*40, file_count=1, total_bytes=len(content),
                             metadata=dict(path='snapshot/META.json', sha256=sha(self.metadata), bytes=len(self.metadata)))
        self.members = [('META.json', self.metadata, None), (name, content, None)]
        self.build_archive()
        self.out = self.base / 'restored'

    def build_archive(self):
        buffer = io.BytesIO()
        with tarfile.open(fileobj=buffer, mode='w:gz') as archive:
            for name, data, kind in self.members:
                member = tarfile.TarInfo(name)
                member.size = len(data)
                if kind:
                    member.type = kind
                    member.linkname = 'outside'
                archive.addfile(member, io.BytesIO(data) if not kind else None)
        self.archive = buffer.getvalue()
        self.manifest['archive'] = dict(path='snapshot/full-git-benchmarks.tar.gz', sha256=sha(self.archive), bytes=len(self.archive))

    def fake_download(self, manifest, entry, destination):
        destination.write_bytes(self.metadata if entry['path'].endswith('META.json') else self.archive)
        FETCH.checked_bytes(destination, entry)

    def run_main(self, *arguments):
        with patch.object(FETCH, 'load_manifest', return_value=self.manifest), patch.object(FETCH, 'download', side_effect=self.fake_download), contextlib.redirect_stdout(io.StringIO()):
            return FETCH.main(list(arguments))

    def restore(self):
        self.assertEqual(self.run_main('--output', str(self.out)), 0)

    def test_restore_verify_modes_and_no_network_dry_run(self):
        with patch.object(FETCH, 'download', side_effect=AssertionError('network')), patch.object(FETCH, 'load_manifest', return_value=self.manifest), contextlib.redirect_stdout(io.StringIO()):
            self.assertEqual(FETCH.main(['--dry-run']), 0)
        self.restore()
        self.assertEqual((self.out/'benchmarks/example/run.sh').stat().st_mode & 0o777, 0o755)
        self.assertEqual(self.run_main('--verify-only', '--output', str(self.out)), 0)

    def test_destination_required_external_absolute_and_absent(self):
        for args in [[], ['--output','relative'], ['--output',str(ROOT/'new-output')], ['--output',str(self.base/'..'/'escape')]]:
            with self.subTest(args=args), self.assertRaises(ValueError):
                self.run_main(*args)
        self.out.mkdir()
        marker=self.out/'keep';marker.write_text('preserve')
        with self.assertRaises(ValueError):
            self.run_main('--output',str(self.out))
        self.assertEqual(marker.read_text(),'preserve')
        link=self.base/'link';link.symlink_to(self.out,target_is_directory=True)
        with self.assertRaises(ValueError):
            self.run_main('--output',str(link/'child'))

    def test_exclusive_publication_does_not_replace_existing_empty_directory(self):
        src=self.base/'source';src.mkdir();self.out.mkdir()
        with self.assertRaises(OSError):
            FETCH.publish(src,self.out)
        self.assertTrue(src.is_dir())
        self.assertTrue(self.out.is_dir())

    def test_corrupt_archive_or_metadata_never_published(self):
        for key in ('archive','metadata'):
            original=self.manifest[key]['sha256'];self.manifest[key]['sha256']='0'*64
            with self.subTest(key=key),self.assertRaises(ValueError):
                self.run_main('--output',str(self.out))
            self.assertFalse(self.out.exists());self.manifest[key]['sha256']=original

    def test_missing_extra_tampered_mode_or_symlink_original_is_rejected(self):
        self.restore();original=self.out/'benchmarks/example/run.sh'
        data=original.read_bytes()
        for mutation in ('missing','extra','tampered','mode','symlink'):
            if mutation=='missing':original.unlink()
            elif mutation=='extra':(original.parent/'extra').write_bytes(b'x')
            elif mutation=='tampered':original.write_bytes(b'wrong')
            elif mutation=='mode':original.chmod(0o644)
            else:original.unlink();original.symlink_to(self.base/'external')
            with self.subTest(mutation=mutation),self.assertRaises(ValueError):
                FETCH.verify(self.out,self.manifest)
            extra=original.parent/'extra'
            if extra.exists():extra.unlink()
            if original.is_symlink():original.unlink()
            original.write_bytes(data);original.chmod(0o755)

    def test_traversal_links_devices_duplicates_and_unexpected_files_rejected(self):
        normal=list(self.members)
        for member in [('../escape',b'x',None),('/absolute',b'x',None),('benchmarks/../escape',b'x',None),
                       ('benchmarks/link',b'',tarfile.SYMTYPE),('benchmarks/link',b'',tarfile.LNKTYPE),
                       ('benchmarks/device',b'',tarfile.CHRTYPE),('META.json',self.metadata,None),
                       ('unexpected.txt',b'x',None)]:
            self.members=normal+[member];self.build_archive()
            with self.subTest(name=member[0],kind=member[2]),self.assertRaises(ValueError):
                self.run_main('--output',str(self.out))
            self.assertFalse(self.out.exists())
        self.assertFalse((self.base/'escape').exists())

    def test_missing_original_and_mismatched_embedded_metadata_rejected(self):
        normal=list(self.members)
        for members in [normal[:1],[('META.json',b'{}',None),normal[1]]]:
            self.members=members;self.build_archive()
            with self.assertRaises(ValueError):
                self.run_main('--output',str(self.out))
            self.assertFalse(self.out.exists())

    def test_manifest_paths_identity_and_counts_are_validated(self):
        target=self.base/'manifest.json'
        for key,value in [('revision','main'),('dataset','../owner/repo'),('repo_type','model'),('file_count',True)]:
            changed=dict(self.manifest);changed[key]=value;target.write_text(json.dumps(changed))
            with self.subTest(key=key),self.assertRaises(ValueError):FETCH.load_manifest(target)
        for name in ('../escape','/absolute','a//b','a/./b','a\\b'):
            changed=dict(self.manifest);changed['archive']=dict(self.manifest['archive'],path=name);target.write_text(json.dumps(changed))
            with self.subTest(name=name),self.assertRaises(ValueError):FETCH.load_manifest(target)
        meta=json.loads(self.metadata);meta['files'][0]['git_blob']='0'*40
        targetroot=self.base/'manual';targetroot.mkdir()
        FETCH.extract(self._archive_path(),targetroot,FETCH.metadata_files(json.loads(self.metadata),self.manifest),self.metadata)
        changed_metadata=json.dumps(meta).encode();(targetroot/'META.json').write_bytes(changed_metadata)
        changed=dict(self.manifest,metadata=dict(self.manifest['metadata'],sha256=sha(changed_metadata),bytes=len(changed_metadata)))
        with self.assertRaisesRegex(ValueError,'Git blob'):FETCH.verify(targetroot,changed)

    def source_archive(self, members):
        buffer = io.BytesIO()
        expanded = count = 0
        with tarfile.open(fileobj=buffer, mode='w:gz') as archive:
            for name, data, kind, mode in members:
                entry = tarfile.TarInfo(name)
                entry.type = kind
                entry.mode = mode
                entry.size = len(data)
                if kind in (tarfile.SYMTYPE, tarfile.LNKTYPE):
                    entry.linkname = 'outside'
                archive.addfile(entry, io.BytesIO(data) if kind == tarfile.REGTYPE else None)
                if kind == tarfile.REGTYPE:
                    count += 1
                    expanded += len(data)
        self.archive = buffer.getvalue()
        self.manifest['source_archive'] = dict(path='snapshot/source.tar.gz', sha256=sha(self.archive),
                                              bytes=len(self.archive), file_count=max(count,1),
                                              expanded_bytes=max(expanded,1))

    def restore_source(self):
        with patch.object(FETCH, 'download', side_effect=self.fake_download):
            return FETCH.restore_source(self.manifest, self.out)

    def test_source_archive_restores_regular_modes_and_never_clobbers(self):
        self.source_archive([('AGENTS.md',b'source',tarfile.REGTYPE,0o664),
                             ('scripts/run.sh',b'#!/bin/sh\n',tarfile.REGTYPE,0o775)])
        self.assertEqual(self.restore_source(),self.out)
        self.assertEqual((self.out/'AGENTS.md').read_bytes(),b'source')
        self.assertEqual((self.out/'AGENTS.md').stat().st_mode & 0o777,0o644)
        self.assertEqual((self.out/'scripts/run.sh').stat().st_mode & 0o777,0o755)
        with self.assertRaises(ValueError):self.restore_source()
        self.assertEqual((self.out/'AGENTS.md').read_bytes(),b'source')

    def test_source_archive_rejects_paths_links_duplicates_special_modes(self):
        original=('AGENTS.md',b'source',tarfile.REGTYPE,0o644)
        for malicious in [('../escape',b'x',tarfile.REGTYPE,0o644),
                          ('/absolute',b'x',tarfile.REGTYPE,0o644),
                          ('benchmarks/hidden',b'x',tarfile.REGTYPE,0o644),
                          ('.git/config',b'x',tarfile.REGTYPE,0o644),
                          ('link',b'',tarfile.SYMTYPE,0o644),
                          ('link',b'',tarfile.LNKTYPE,0o644),
                          ('device',b'',tarfile.CHRTYPE,0o644),
                          ('suid',b'x',tarfile.REGTYPE,0o4755), original]:
            self.source_archive([original,malicious])
            with self.subTest(malicious=malicious),self.assertRaises(ValueError):
                self.restore_source()
            self.assertFalse(self.out.exists())
        self.assertFalse((self.base/'escape').exists())

    def test_source_archive_rejects_digest_size_count_and_manifest_drift(self):
        for key,change in [('sha256','0'*64),('bytes',1),('expanded_bytes',1),
                           ('expanded_bytes',999),('file_count',2),('file_count',0)]:
            self.source_archive([('AGENTS.md',b'source',tarfile.REGTYPE,0o644)])
            self.manifest['source_archive'][key]=change
            with self.subTest(key=key,value=change),self.assertRaises(ValueError):
                self.restore_source()
            self.assertFalse(self.out.exists())
        del self.manifest['source_archive']
        with self.assertRaisesRegex(ValueError,'required'):self.restore_source()

    def _archive_path(self):
        path=self.base/'archive.tar.gz';path.write_bytes(self.archive);return path


class RepositoryManifestTests(unittest.TestCase):
    def test_repository_manifest_and_shell_dry_run(self):
        manifest=FETCH.load_manifest()
        result=subprocess.run(['/bin/bash','-p',str(ROOT/'scripts/dev/fetch-benchmark-evidence.sh'),'--dry-run'],capture_output=True,text=True,check=False)
        self.assertEqual(result.returncode,0,result.stderr)
        for text in (manifest['revision'],manifest['source_commit'],manifest['archive']['sha256'],str(manifest['file_count'])):
            self.assertIn(text,result.stdout)


if __name__=='__main__':
    unittest.main()
