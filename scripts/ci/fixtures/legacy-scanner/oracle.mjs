// SPDX-License-Identifier: Apache-2.0
// Verification-only frozen shell oracle. Never imported by the product runtime.
import fs from 'node:fs';
import path from 'node:path';
import { createHash } from 'node:crypto';
import { gunzipSync } from 'node:zlib';
import { pathToFileURL } from 'node:url';

const MANIFEST_SHA256 = '2cc59f596d49a867637839c397e8b0e888affd90a2771ffc4e136d66b3a7a08b';
const sha = bytes => createHash('sha256').update(bytes).digest('hex');
let directory, entries;
function regularBytes(file) {
  const stat = fs.lstatSync(file);
  if (!stat.isFile() || stat.isSymbolicLink()) throw new Error('legacy oracle requires regular files');
  return fs.readFileSync(file);
}
function verified() {
  if (!directory) {
    const manifestBytes = regularBytes(new URL('./manifest.json', import.meta.url));
    if (sha(manifestBytes) !== MANIFEST_SHA256) throw new Error('legacy oracle manifest digest mismatch');
    const manifest = JSON.parse(manifestBytes);
    const archive = regularBytes(new URL('./oracle.json.gz', import.meta.url));
    if (archive.length !== manifest.archiveBytes || sha(archive) !== manifest.archiveSha256)
      throw new Error('legacy oracle archive digest mismatch');
    const data = JSON.parse(gunzipSync(archive, { maxOutputLength: 2 * 1024 * 1024 }));
    if (data.schema !== 'legacy-scanner-files-v1' || data.files.length !== manifest.files.length)
      throw new Error('legacy oracle archive schema mismatch');
    entries = new Map();
    for (let index = 0; index < data.files.length; index++) {
      const item = data.files[index], expected = manifest.files[index];
      if (item.path !== expected.path || !/^[A-Za-z0-9_-]+(?:[./][A-Za-z0-9_-]+)*$/.test(item.path) ||
          item.path.split('/').some(part => part === '.' || part === '..') || entries.has(item.path))
        throw new Error('legacy oracle archive path mismatch');
      const bytes = Buffer.from(item.data, 'base64');
      if (bytes.length !== expected.bytes || sha(bytes) !== expected.sha256)
        throw new Error('legacy oracle file digest mismatch');
      entries.set(item.path, { ...expected, bytes });
    }
    // Fixed OS temporary root; ambient TMPDIR must not redirect executable fixtures.
    const temporary = fs.mkdtempSync(path.join(fs.realpathSync('/tmp'), 'e2e-legacy-oracle-'));
    fs.chmodSync(temporary, 0o700);
    try {
      for (const [name, item] of entries) {
        const target = path.join(temporary, name);
        fs.mkdirSync(path.dirname(target), { recursive: true, mode: 0o700 });
        fs.writeFileSync(target, item.bytes, { flag: 'wx', mode: item.mode });
        fs.chmodSync(target, item.mode);
      }
      directory = temporary;
      process.once('exit', () => fs.rmSync(temporary, { recursive: true, force: true }));
    } catch (error) {
      fs.rmSync(temporary, { recursive: true, force: true });
      throw error;
    }
  }
  if (!fs.lstatSync(directory).isDirectory() || fs.realpathSync(directory) !== directory)
    throw new Error('legacy oracle directory changed');
  for (const [name, item] of entries) {
    const target = path.join(directory, name);
    if (fs.realpathSync(target) !== target || sha(regularBytes(target)) !== item.sha256)
      throw new Error('legacy oracle extracted file changed');
  }
  return directory;
}

/** Each access revalidates every frozen file, including helper dependencies. */
export function legacyOracleFile(name = 'scan.sh') {
  const root = verified();
  if (!entries.has(name)) throw new Error('unknown legacy oracle file');
  return path.join(root, name);
}
export function legacyOracleURL(name = 'scan.sh') {
  return pathToFileURL(legacyOracleFile(name));
}
