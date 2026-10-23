// SPDX-License-Identifier: Apache-2.0
import fs from 'node:fs';
import path from 'node:path';
import { createHash } from 'node:crypto';
import { MAX_SOURCE_BYTES } from './source.mjs';

const FIELDS = ['dev', 'ino', 'mode', 'size', 'mtimeNs', 'ctimeNs'];
const identity = stat => FIELDS.map(key => String(stat[key]));
const equal = (a, b) => a.length === b.length && a.every((value, index) => value === b[index]);

// Read exactly the regular file inventoried by the caller. The parser consumes
// these bytes, never a second path read. This is drift detection, not a sandbox.
export function readCandidate(candidate) {
  if (!candidate || !path.isAbsolute(candidate.path ?? '') || !candidate.identity ||
      !FIELDS.every(key => typeof candidate.identity[key] === 'string') ||
      !/^[a-f0-9]{64}$/.test(candidate.identity.sha256 ?? '')) throw new TypeError('invalid candidate');
  if (fs.constants.O_NOFOLLOW === undefined) throw new Error('O_NOFOLLOW unavailable');
  const parent = path.dirname(candidate.path);
  const parentIdentity = identity(fs.statSync(parent, { bigint: true }));
  const guardParent = () => {
    if (fs.realpathSync(parent) !== parent ||
        !equal(parentIdentity, identity(fs.statSync(parent, { bigint: true })))) throw new Error('candidate parent drift');
  };
  guardParent();
  const fd = fs.openSync(candidate.path, fs.constants.O_RDONLY | fs.constants.O_NOFOLLOW | fs.constants.O_NONBLOCK);
  try {
    guardParent();
    const before = fs.fstatSync(fd, { bigint: true });
    const expected = FIELDS.map(key => candidate.identity[key]);
    if (!before.isFile() || !equal(expected, identity(before))) throw new Error('candidate identity drift before read');
    if (before.size > BigInt(MAX_SOURCE_BYTES)) throw new RangeError('source exceeds the 16 MiB parser limit');
    const bytes = fs.readFileSync(fd);
    if (!equal(expected, identity(fs.fstatSync(fd, { bigint: true }))) ||
        !equal(expected, identity(fs.lstatSync(candidate.path, { bigint: true })))) throw new Error('candidate identity drift after read');
    guardParent();
    if (createHash('sha256').update(bytes).digest('hex') !== candidate.identity.sha256) throw new Error('candidate content drift');
    return bytes;
  } finally { fs.closeSync(fd); }
}
