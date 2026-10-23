// SPDX-License-Identifier: Apache-2.0
// Pin reachable source imports without running project configuration or modules.
import fs from 'node:fs';
import path from 'node:path';
import { inventory } from './inventory.mjs';
import { readCandidate } from './read-candidate.mjs';
import { revalidateProjectContext } from './project-context.mjs';
import { createScope } from './scope.mjs';
import { sourceModel, walk, ts } from './source.mjs';

const EXTENSIONS = ['ts', 'tsx', 'js', 'jsx', 'mts', 'mjs', 'cts', 'cjs'];
const EXCLUDED = new Set(['node_modules', '.git', 'playwright-report', 'test-results', 'dist', 'build', '.next', 'out', 'coverage', '.yarn', '.pnp.cjs', '.pnp.loader.mjs']);
// Expansion budgets cover new helpers, not the caller's existing scan targets.
const MAX_HELPERS = 128, MAX_HELPER_BYTES = 16 * 1024 * 1024, MAX_DEPTH = 32;
const directoryIdentity = stat => ['dev', 'ino', 'mode'].map(key => String(stat[key]));
const fileIdentity = stat => ['dev', 'ino', 'mode', 'size', 'mtimeNs', 'ctimeNs'].map(key => String(stat[key]));
const excluded = file => file.split(path.sep).some(part => EXCLUDED.has(part)) || /(?:^|\/)cypress\/reports(?:\/|$)|\.min\.(?:js|ts)$/.test(file);
const within = (root, file) => file === root || file.startsWith(root === path.sep ? root : root + path.sep);

export function prepareImportSnapshot({ manifest, sources } = {}) {
  const diagnostics = [], helpers = [], copied = new Map(), observations = new Map();
  const original = manifest ? structuredClone(manifest) : null;
  let expanded = original, root, rootIdentity, helperBytes = 0;
  const add = (code, file, start) => diagnostics.push({ code, ...(file ? { file } : {}), ...(Number.isInteger(start) ? { start } : {}) });
  // Every component is checked with lstat, including absent resolution choices.
  // Directory identities exclude mtime: unrelated sibling edits are permitted.
  function observe(file) {
    if (!within(root, file) || excluded(file)) throw new Error('unsafe import path');
    const parts = path.relative(root, file).split(path.sep).filter(Boolean);
    let current = root;
    const entries = [];
    for (const part of ['', ...parts]) {
      if (part) current = path.join(current, part);
      let stat;
      try { stat = fs.lstatSync(current, { bigint: true }); }
      catch (error) {
        if (error.code === 'ENOENT' || error.code === 'ENOTDIR') return { entries, missing: current, kind: 'absent' };
        throw error;
      }
      if (stat.isSymbolicLink() || (!stat.isDirectory() && !stat.isFile())) throw new Error('unsupported import entry');
      const kind = stat.isDirectory() ? 'directory' : 'file';
      entries.push([current, kind, kind === 'directory' ? directoryIdentity(stat) : fileIdentity(stat)]);
    }
    return { entries, kind: entries.at(-1)[1] };
  }
  function pin(file) {
    const value = observe(file), serialized = JSON.stringify(value);
    if (observations.has(file) && observations.get(file) !== serialized) throw new Error('import resolution drift');
    observations.set(file, serialized);
    return value;
  }
  function resolve(file, specifier, start) {
    if (!specifier.startsWith('./') && !specifier.startsWith('../')) return null;
    if (/[\\:\n\r\0]/.test(specifier)) { add('import-path-unsupported', file, start); return null; }
    const candidate = path.resolve(path.dirname(file), specifier);
    const parts = candidate.split(path.sep);
    // Relative vendor dependencies are opaque, like bare packages: never read
    // their code or infer framework provenance from the package-looking path.
    // Keep outside-root and every other excluded-tree boundary fail-closed.
    if (within(root, candidate) && parts.slice(0, -1).includes('node_modules') &&
        !excluded(parts.filter(part => part !== 'node_modules').join(path.sep))) return null;
    if (!within(root, candidate) || excluded(candidate)) { add('import-outside-scope', file, start); return null; }
    const base = /\.(?:js|jsx|mjs|cjs)$/.test(candidate) ? candidate.slice(0, candidate.lastIndexOf('.')) : candidate;
    const alternatives = [...new Set([candidate, ...EXTENSIONS.map(ext => `${base}.${ext}`), ...EXTENSIONS.map(ext => path.join(candidate, `index.${ext}`))])];
    try {
      const matches = alternatives.filter(name => pin(name).kind === 'file');
      if (matches.length !== 1) { add(matches.length ? 'import-ambiguous' : 'import-missing', file, start); return null; }
      if (!/\.(?:ts|tsx|js|jsx|mts|mjs|cts|cjs)$/.test(matches[0])) { add('import-extension-unsupported', file, start); return null; }
      return matches[0];
    } catch { add('import-entry-unsafe', file, start); return null; }
  }
  function edges(bytes, file) {
    const model = sourceModel(bytes, file), result = [];
    if (model.diagnostics.length) { add('import-parse-invalid', file); return result; }
    function emit(node, specifier) {
      if (specifier && (ts.isStringLiteral(specifier) || ts.isNoSubstitutionTemplateLiteral(specifier))) result.push({ specifier: specifier.text, start: node.getStart(model.source) });
    }
    walk(model.source, node => {
      if (ts.isImportDeclaration(node)) {
        const clause = node.importClause, bindings = clause?.namedBindings;
        if (!clause?.isTypeOnly && (!bindings || !ts.isNamedImports(bindings) || clause.name || bindings.elements.some(item => !item.isTypeOnly))) emit(node, node.moduleSpecifier);
      } else if (ts.isExportDeclaration(node)) {
        if (!node.isTypeOnly && (!node.exportClause || !ts.isNamedExports(node.exportClause) || node.exportClause.elements.some(item => !item.isTypeOnly))) emit(node, node.moduleSpecifier);
      } else if (ts.isImportEqualsDeclaration(node)) {
        if (!node.isTypeOnly && ts.isExternalModuleReference(node.moduleReference)) emit(node, node.moduleReference.expression);
      } else if (ts.isCallExpression(node) && !node.questionDotToken && node.arguments.length === 1 && ts.isIdentifier(node.expression) && node.expression.text === 'require') {
        const symbol = model.checker.getSymbolAtLocation(node.expression);
        if (!symbol?.declarations?.length) emit(node, node.arguments[0]);
      }
    });
    return result;
  }
  try {
    if (!createScope({ manifest: original, sources }).validate().complete || !original.projectContext?.complete || !revalidateProjectContext(original.projectContext).complete) throw new Error('invalid source snapshot');
    root = original.projectContext.projectRoot;
    if (!path.isAbsolute(root || '') || path.normalize(root) !== root || excluded(root)) throw new Error('invalid project root');
    const stat = fs.lstatSync(root, { bigint: true });
    if (!stat.isDirectory() || fs.realpathSync(root) !== root) throw new Error('unsafe project root');
    rootIdentity = directoryIdentity(stat);
    expanded = { ...original, root: { requested: root, canonical: root, kind: 'directory', identity: rootIdentity }, candidates: [...original.candidates] };
    const queue = [], loaded = new Set();
    for (const candidate of original.candidates) {
      if (!within(root, candidate.path) || excluded(candidate.path)) throw new Error('source outside project');
      const bytes = sources.get(candidate.path);
      pin(candidate.path);
      if (!readCandidate(candidate).equals(bytes)) throw new Error('source drift');
      copied.set(candidate.path, Buffer.from(bytes)); loaded.add(candidate.path); queue.push({ file: candidate.path, depth: 0 });
    }
    for (let index = 0; index < queue.length; index++) {
      const { file, depth } = queue[index];
      for (const edge of edges(copied.get(file), file)) {
        const selected = resolve(file, edge.specifier, edge.start);
        if (!selected || loaded.has(selected)) continue;
        if (depth >= MAX_DEPTH) { add('import-depth-limit', file, edge.start); continue; }
        if (helpers.length >= MAX_HELPERS) { add('import-file-limit', file, edge.start); continue; }
        try {
          const stat = fs.lstatSync(selected, { bigint: true });
          if (stat.size > BigInt(MAX_HELPER_BYTES - helperBytes)) { add('import-byte-limit', file, edge.start); continue; }
          const single = inventory(selected);
          if (!single.complete || single.candidates.length !== 1 || single.candidates[0].path !== selected) throw new Error('helper inventory unavailable');
          const candidate = single.candidates[0], bytes = readCandidate(candidate);
          pin(selected);
          if (helperBytes + bytes.length > MAX_HELPER_BYTES) { add('import-byte-limit', file, edge.start); continue; }
          copied.set(selected, Buffer.from(bytes)); loaded.add(selected); helperBytes += bytes.length;
          helpers.push(candidate); expanded.candidates.push(candidate); queue.push({ file: selected, depth: depth + 1 });
        } catch { add('import-read-unavailable', file, edge.start); }
      }
    }
  } catch (error) {
    add(error instanceof RangeError ? 'import-snapshot-limit' : 'import-snapshot-invalid');
    expanded = { ...(expanded || {}), complete: false };
  }
  function revalidate() {
    const result = [...diagnostics];
    try {
      if (!root || !revalidateProjectContext(original.projectContext).complete || JSON.stringify(directoryIdentity(fs.lstatSync(root, { bigint: true }))) !== JSON.stringify(rootIdentity) || fs.realpathSync(root) !== root) throw new Error('context drift');
      for (const [file, expected] of observations) if (JSON.stringify(observe(file)) !== expected) throw new Error('resolution drift');
      for (const candidate of expanded.candidates) if (!readCandidate(candidate).equals(copied.get(candidate.path))) throw new Error('source drift');
    } catch { result.push({ code: 'import-snapshot-drift' }); }
    return { complete: result.length === 0, diagnostics: result };
  }
  return { manifest: expanded, sources: copied, helpers, diagnostics, revalidate };
}
