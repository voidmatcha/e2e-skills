// SPDX-License-Identifier: Apache-2.0
// Experimental candidate inventory; deliberately contains no scanner rules.
import fs from 'node:fs';
import path from 'node:path';
import { createHash } from 'node:crypto';
import { discoverProjectContext, revalidateProjectContext } from './project-context.mjs';

const EXTENSIONS = new Set(['ts', 'js', 'tsx', 'jsx', 'mts', 'mjs', 'cts', 'cjs']);
const EXCLUDED = new Set(['node_modules', '.git', 'playwright-report', 'test-results', 'dist', 'build', '.next', 'out', 'coverage']);
const SOURCE_ROOTS = new Set(['src', 'test', 'tests', 'e2e', 'spec', 'specs', 'playwright', 'cypress', 'support', 'fixtures']);
const INTENTIONAL_FIXTURES = /(?:^|\/)evals\/files(?:\/|$)|(?:^|\/)scripts\/evals\/skills\/(?:e2e-reviewer|playwright-test-generator|playwright-debugger|cypress-debugger)\/files(?:\/|$)|(?:^|\/)scripts\/ci\/fixtures(?:\/|$)/;
const BUNDLED_PARSER = 'skills/e2e-reviewer/scripts/scanner/vendor/typescript/typescript.cjs';
const BUNDLED_PARSER_SHA256 = '569177652966bd528c319171c7dd22860dbf72bde116cbc4f644f1d02bb12e39';
const FIELDS = ['dev', 'ino', 'mode', 'size', 'mtimeNs', 'ctimeNs'];
const rootIdentity = stat => ['dev', 'ino', 'mode'].map(key => String(stat[key]));
const equalRootIdentity = (a, b) => a.length === b.length && a.every((value, index) => value === b[index]);
const same = (a, b) => FIELDS.every(key => a[key] === b[key]);
const isCode = name => EXTENSIONS.has(name.slice(name.lastIndexOf('.') + 1)) && name.includes('.');
const byteSort = (a, b) => Buffer.compare(Buffer.from(a), Buffer.from(b));
function excludedTree(file) {
  const segments = file.split(path.sep);
  return segments.some(part => EXCLUDED.has(part)) || /(?:^|\/)cypress\/reports(?:\/|$)/.test(file);
}
function error(code, file, detail) { return { code, path: file, detail }; }
function inspectRoot(requested) {
  const stat = fs.lstatSync(requested, { bigint: true });
  if (stat.isSymbolicLink()) throw new Error('symbolic-link scan root');
  if (!stat.isDirectory() && !stat.isFile()) throw new Error('non-regular scan root');
  return { requested, canonical: fs.realpathSync(requested), kind: stat.isDirectory() ? 'directory' : 'file', identity: rootIdentity(stat) };
}
function guardRoot(root) {
  const now = inspectRoot(root.requested);
  if (now.canonical !== root.canonical || now.kind !== root.kind || !equalRootIdentity(now.identity, root.identity)) {
    throw new Error('scan root identity changed');
  }
}
function fingerprint(file) {
  if (fs.constants.O_NOFOLLOW === undefined) throw new Error('O_NOFOLLOW unavailable');
  // Nonblocking prevents an intervening FIFO replacement from hanging open().
  const flags = fs.constants.O_RDONLY | fs.constants.O_NOFOLLOW | fs.constants.O_NONBLOCK;
  const parent = path.dirname(file);
  const parentBefore = fs.statSync(parent, { bigint: true });
  if (fs.realpathSync(parent) !== parent) throw new Error('candidate parent changed');
  const guardParent = () => {
    if (fs.realpathSync(parent) !== parent ||
        !equalRootIdentity(rootIdentity(parentBefore), rootIdentity(fs.statSync(parent, { bigint: true })))) {
      throw new Error('candidate parent changed while fingerprinting');
    }
  };
  const fd = fs.openSync(file, flags);
  try {
    // Reject a persistent parent swap before reading contents from the opened fd.
    guardParent();
    const before = fs.fstatSync(fd, { bigint: true });
    if (!before.isFile()) throw new Error('candidate is not a regular file');
    const hash = createHash('sha256');
    const buffer = Buffer.alloc(1024 * 1024);
    let count;
    while ((count = fs.readSync(fd, buffer)) !== 0) hash.update(buffer.subarray(0, count));
    const after = fs.fstatSync(fd, { bigint: true });
    if (!same(before, after)) throw new Error('candidate changed while fingerprinting');
    if (!same(after, fs.lstatSync(file, { bigint: true }))) throw new Error('candidate path changed while fingerprinting');
    guardParent();
    return { ...Object.fromEntries(FIELDS.map(key => [key, String(after[key])])), sha256: hash.digest('hex') };
  } finally { fs.closeSync(fd); }
}
function specialCanHideSource(file, stat) {
  if (isCode(path.basename(file))) return true;
  if (!stat.isSymbolicLink()) return false;
  try { if (fs.statSync(file).isDirectory()) return true; } catch (cause) {
    if (!['ENOENT', 'ENOTDIR', 'ELOOP'].includes(cause.code)) throw cause;
  }
  return SOURCE_ROOTS.has(path.basename(file));
}
function walk(root, errors, context) {
  const directFixture = INTENTIONAL_FIXTURES.test(root.canonical);
  const selfExclude = context.selfRepositoryScope && !directFixture;
  const files = [];
  function visit(file) {
    if (excludedTree(file) || (selfExclude && INTENTIONAL_FIXTURES.test(file))) return;
    const stat = fs.lstatSync(file, { bigint: true });
    // This exact upstream dependency is not authored E2E source. Do not turn
    // this into a vendor-directory exclusion: changed bytes, other projects
    // and an explicitly requested file root must still be inventoried.
    if (selfExclude && root.kind === 'directory' && stat.isFile() &&
        file === path.join(context.projectRoot, BUNDLED_PARSER) && stat.size === 9144216n &&
        fingerprint(file).sha256 === BUNDLED_PARSER_SHA256) return;
    if (!stat.isDirectory() && /\.min\.(js|ts)$/.test(file)) return;
    if (stat.isDirectory()) {
      if (fs.realpathSync(file) !== file || !same(stat, fs.lstatSync(file, { bigint: true }))) {
        throw new Error(`directory identity changed before traversal: ${file}`);
      }
      const names = fs.readdirSync(file, { encoding: 'buffer' });
      for (const bytes of names) {
        const name = bytes.toString('utf8');
        if (!Buffer.from(name).equals(bytes)) {
          errors.push(error('unsupported-filename-encoding', file, bytes.toString('hex'))); continue;
        }
        visit(path.join(file, name));
      }
      if (fs.realpathSync(file) !== file || !same(stat, fs.lstatSync(file, { bigint: true }))) throw new Error(`directory identity changed: ${file}`);
    } else if (stat.isFile()) {
      if (root.kind === 'file' || (isCode(path.basename(file)) && !file.split(path.sep).some(part => ['.yarn', '.pnp.cjs', '.pnp.loader.mjs'].includes(part) || /\.min\.(js|ts)$/.test(part)) && !['.pnp.cjs', '.pnp.loader.mjs'].includes(path.basename(file)))) files.push(file);
    } else if (specialCanHideSource(file, stat)) {
      errors.push(error('unsupported-entry', file, stat.isSymbolicLink() ? 'symbolic link' : stat.isFIFO() ? 'FIFO' : 'non-regular entry'));
    }
  }
  visit(root.canonical);
  return files.sort(byteSort);
}
export function inventory(requested) {
  const report = { schema: 'node-candidate-inventory-v1', complete: false, root: null, projectContext: null, candidates: [], errors: [] };
  try {
    const root = inspectRoot(path.resolve(requested));
    report.root = root;
    guardRoot(root);
    const context = discoverProjectContext(root.canonical);
    report.projectContext = context;
    if (!context.complete) {
      report.errors.push(error('project-context-unavailable', root.canonical, 'project marker discovery could not be validated')); return report;
    }
    const files = walk(root, report.errors, context);
    guardRoot(root);
    if (report.errors.length) return report;
    for (const file of files) {
      if (/[:\n]/.test(file)) { report.errors.push(error('unsupported-filename', file, 'colon/newline transport boundary')); return report; }
    }
    for (const file of files) {
      try { report.candidates.push({ path: file, identity: fingerprint(file) }); }
      catch (cause) { report.errors.push(error('fingerprint-unavailable', file, cause.message)); return report; }
    }
    guardRoot(root);
    if (!revalidateProjectContext(context).complete) {
      report.errors.push(error('project-context-drift', root.canonical, 'project marker identity changed')); return report;
    }
    report.complete = true;
  } catch (cause) { report.errors.push(error('inventory-unavailable', report.root?.canonical ?? String(requested), cause.message)); }
  return report;
}
function validBaseline(expected) {
  const root = expected?.root;
  if (expected?.projectContext?.schema !== 'node-project-context-discovery-v1' || expected.projectContext.complete !== true || expected?.schema !== 'node-candidate-inventory-v1' || expected.complete !== true || !root ||
      typeof root.requested !== 'string' || !path.isAbsolute(root.requested) ||
      typeof root.canonical !== 'string' || !path.isAbsolute(root.canonical) ||
      !['directory', 'file'].includes(root.kind) || !Array.isArray(root.identity) ||
      root.identity.length !== 3 || !root.identity.every(value => typeof value === 'string' && /^\d+$/.test(value)) ||
      !Array.isArray(expected.candidates) || !Array.isArray(expected.errors) || expected.errors.length !== 0) return false;
  const seen = new Set();
  for (const item of expected.candidates) {
    if (!item || typeof item.path !== 'string' || !path.isAbsolute(item.path) || seen.has(item.path) ||
        (root.kind === 'file' ? item.path !== root.canonical : !item.path.startsWith(root.canonical === path.sep ? path.sep : root.canonical + path.sep)) ||
        !item.identity || !FIELDS.every(key => typeof item.identity[key] === 'string' && /^-?\d+$/.test(item.identity[key])) ||
        typeof item.identity.sha256 !== 'string' || !/^[a-f0-9]{64}$/.test(item.identity.sha256)) return false;
    seen.add(item.path);
  }
  return true;
}
export function revalidate(expected) {
  if (!validBaseline(expected)) {
    return { complete: false, errors: [error('invalid-baseline', '', 'a complete, well-formed inventory is required')] };
  }
  let contextValid;
  try { contextValid = revalidateProjectContext(expected.projectContext).complete; }
  catch { contextValid = false; }
  const current = inventory(expected.root.requested);
  if (!current.complete) return current;
  const root = expected.root;
  if (current.root.canonical !== root.canonical || current.root.kind !== root.kind ||
      !equalRootIdentity(current.root.identity, root.identity)) {
    current.errors.push(error('root-drift', current.root.canonical, 'root identity changed'));
  }
  const previous = new Map(expected.candidates.map(item => [item.path, item.identity]));
  const actual = new Map(current.candidates.map(item => [item.path, item.identity]));
  for (const file of previous.keys()) if (!actual.has(file)) current.errors.push(error('removed', file, 'removed from candidate set'));
  for (const file of actual.keys()) if (!previous.has(file)) current.errors.push(error('added', file, 'added to candidate set'));
  for (const [file, identity] of previous) if (actual.has(file) &&
      [...FIELDS, 'sha256'].some(key => identity[key] !== actual.get(file)[key])) {
    current.errors.push(error('identity-drift', file, 'regular-file identity/content drift'));
  }
  if (!contextValid) current.errors.push(error('project-context-drift', expected.root.canonical, 'project marker identity changed'));
  current.complete = current.errors.length === 0;
  return current;
}
