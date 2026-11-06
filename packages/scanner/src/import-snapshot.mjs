// SPDX-License-Identifier: Apache-2.0
// Pin reachable source imports without running project configuration or modules.
import fs from 'node:fs';
import path from 'node:path';
import { builtinModules } from 'node:module';
import { createHash } from 'node:crypto';
import { inventory } from './inventory.mjs';
import { readCandidate } from './read-candidate.mjs';
import { revalidateProjectContext } from './project-context.mjs';
import { createScope } from './scope.mjs';
import { sourceModel, walk, ts } from './source.mjs';

const EXTENSIONS = ['ts', 'tsx', 'js', 'jsx', 'mts', 'mjs', 'cts', 'cjs'];
const BUILTINS = new Set(builtinModules);
const EXCLUDED = new Set(['node_modules', '.git', 'playwright-report', 'test-results', 'dist', 'build', '.next', 'out', 'coverage', '.yarn', '.pnp.cjs', '.pnp.loader.mjs']);
// Expansion budgets cover new helpers, not the caller's existing scan targets.
const MAX_HELPERS = 128, MAX_HELPER_BYTES = 16 * 1024 * 1024, MAX_DEPTH = 32;
// Data-leaf reads also honor credential/agent-config boundaries. This named
// policy is deliberately conservative, not a content-based secret detector.
const DATA_RESERVED = new Set(['.git', '.codex', '.claude', '.agents', '.omx', '.skill', '.auth', '.ssh', '.aws', '.azure', '.gcloud', '.config']);
// Compare conservatively on every platform: case-insensitive filesystems can
// resolve an uppercase spelling to the same protected file.
const forbiddenDataPath = file => {
  const normalized = file.toLowerCase();
  return normalized.split(path.sep).some(part => DATA_RESERVED.has(part) || part.startsWith('.env')) || ['auth.json', '.npmrc', 'agents.md', 'claude.md'].includes(path.basename(normalized));
};
const directoryIdentity = stat => ['dev', 'ino', 'mode'].map(key => String(stat[key]));
const fileIdentity = stat => ['dev', 'ino', 'mode', 'size', 'mtimeNs', 'ctimeNs'].map(key => String(stat[key]));
const excluded = file => file.split(path.sep).some(part => EXCLUDED.has(part)) || /(?:^|\/)cypress\/reports(?:\/|$)|\.min\.(?:js|ts)$/.test(file);
const within = (root, file) => file === root || file.startsWith(root === path.sep ? root : root + path.sep);

const PLAYWRIGHT_CONFIG = /^playwright\.config\.(?:ts|js|mts|mjs|cts|cjs)$/;
const MAX_CONFIG_BYTES = 1024 * 1024, MAX_CONFIGS = 256, MAX_CONFIG_TOTAL = 8 * 1024 * 1024;
// A hostile config must not make resolution expensive: bounded `paths`
// shape, bounded alias filesystem probes, and a bounded observation set.
const MAX_PATH_KEYS = 64, MAX_PATH_VALUES = 8, MAX_ALIAS_PROBES = 4096, MAX_OBSERVATIONS = 65536;
const MAX_MARKER_BYTES = 1024 * 1024;
// Framework packages are never wildcard- or baseUrl-expanded; only an exact
// `paths` key can shadow one with a local file.
const FRAMEWORK_SPECIFIERS = new Set(['@playwright/test', 'playwright/test', 'playwright', 'playwright-core', 'cypress', 'vitest', 'jest', '@jest/globals', 'mocha', 'bun:test', '@wdio/globals']);

export function prepareImportSnapshot({ manifest, sources } = {}) {
  const diagnostics = [], helpers = [], dataDependencies = [], dataBytes = new Map(), copied = new Map(), observations = new Map();
  // Bare specifiers resolved through a pinned tsconfig/jsconfig `paths`
  // mapping, keyed `${importer}\0${specifier}`. Only proven in-scope files.
  const aliases = new Map(), configs = new Map(), unresolvedImports = [], configDependencies = [];
  let aliasPolicy, configCount = 0, configBytes = 0;
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
    if (!observations.has(file) && observations.size >= MAX_OBSERVATIONS) throw new RangeError('import observation limit');
    const value = observe(file), serialized = JSON.stringify(value);
    if (observations.has(file) && observations.get(file) !== serialized) throw new Error('import resolution drift');
    observations.set(file, serialized);
    return value;
  }
  function resolve(file, specifier, start, dataLeaf = false) {
    if (!specifier.startsWith('./') && !specifier.startsWith('../')) {
      if (dataLeaf || specifier.startsWith('/') || /[\\\n\r\0]/.test(specifier)) return null;
      try {
        const mapped = resolveAlias(file, specifier);
        // An unknown mapping of a framework specifier could redirect it to a
        // user module, so its official provenance cannot be trusted.
        if (mapped.unknown && FRAMEWORK_SPECIFIERS.has(specifier) && frameworkMappingPossible(file, specifier)) {
          add('import-framework-alias-unknown', file, start); return null;
        }
        if (!mapped.file) {
          // No tsconfig mapping applies: a workspace package declared by the
          // project root resolves by name inside the pinned scope.
          const member = mapped.package && !FRAMEWORK_SPECIFIERS.has(specifier) ? workspaceResolve(specifier) : null;
          if (!member) return null;
          aliases.set(`${file}\0${specifier}`, member);
          return member;
        }
        aliases.set(`${file}\0${specifier}`, mapped.file);
        return mapped.file;
      } catch { add('import-entry-unsafe', file, start); return null; }
    }
    if (/[\\:\n\r\0]/.test(specifier)) { add('import-path-unsupported', file, start); return null; }
    const candidate = path.resolve(path.dirname(file), specifier);
    // Refuse before observing, inventorying, opening, or reading target bytes.
    if ((dataLeaf || /\.json$/i.test(specifier)) && forbiddenDataPath(candidate)) { add('import-data-path-forbidden', file, start); return null; }
    const parts = candidate.split(path.sep);
    // Relative vendor dependencies are opaque, like bare packages: never read
    // their code or infer framework provenance from the package-looking path.
    // Keep outside-root and every other excluded-tree boundary fail-closed.
    if (within(root, candidate) && parts.slice(0, -1).includes('node_modules') &&
        !excluded(parts.filter(part => part !== 'node_modules').join(path.sep))) return null;
    if (!within(root, candidate) || excluded(candidate)) { add('import-outside-scope', file, start); return null; }
    const base = /\.(?:js|jsx|mjs|cjs)$/.test(candidate) ? candidate.slice(0, candidate.lastIndexOf('.')) : candidate;
    const alternatives = dataLeaf ? [candidate] : [...new Set([candidate, ...EXTENSIONS.map(ext => `${base}.${ext}`), ...EXTENSIONS.map(ext => path.join(candidate, `index.${ext}`))])];
    try {
      const matches = alternatives.filter(name => pin(name).kind === 'file');
      if (matches.length !== 1) {
        add(matches.length ? 'import-ambiguous' : 'import-missing', file, start);
        // The text view names the relative specifier that was not followed.
        if (!matches.length) unresolvedImports.push({ file, start, specifier });
        return null;
      }
      if (!(dataLeaf && matches[0].endsWith('.json')) && !/\.(?:ts|tsx|js|jsx|mts|mjs|cts|cjs)$/.test(matches[0])) { add('import-extension-unsupported', file, start); return null; }
      return matches[0];
    } catch { add('import-entry-unsafe', file, start); return null; }
  }
  // Playwright's loader maps a bare specifier with the nearest tsconfig.json
  // or jsconfig.json above the importing file (playwright/lib/transform). It
  // is emulated only when the scope holds Playwright configuration that does
  // not select a single `tsconfig`, and only from configs inside the pinned
  // scope. Anything else (package extends, references, a candidate outside
  // scope, ambiguous files) is unknown and the import stays unresolved.
  function aliasesEnabled() {
    if (aliasPolicy !== undefined) return aliasPolicy;
    aliasPolicy = false;
    const files = new Map();
    for (const candidate of original.candidates) if (PLAYWRIGHT_CONFIG.test(path.basename(candidate.path))) files.set(candidate.path, sources.get(candidate.path));
    for (const marker of original.projectContext.markers || []) {
      if (marker.kind !== 'file' || !PLAYWRIGHT_CONFIG.test(path.basename(marker.path)) || files.has(marker.path)) continue;
      if (!within(root, marker.path) || excluded(marker.path)) return aliasPolicy;
      // Pin the marker path, then read only a regular, bounded file.
      if (pin(marker.path).kind !== 'file' || fs.lstatSync(marker.path).size > MAX_MARKER_BYTES) return aliasPolicy;
      const bytes = readRegular(marker.path, MAX_MARKER_BYTES);
      if (!bytes) return aliasPolicy;
      if (createHash('sha256').update(bytes).digest('hex') !== marker.sha256) throw new Error('configuration drift');
      files.set(marker.path, bytes);
    }
    // The config's single `tsconfig` option replaces per-file lookup.
    aliasPolicy = files.size > 0 && [...files.values()].every(bytes => Buffer.isBuffer(bytes) && !bytes.includes('tsconfig'));
    return aliasPolicy;
  }
  function readRegular(file, limit) {
    let fd;
    try {
      fd = fs.openSync(file, fs.constants.O_RDONLY | (fs.constants.O_NOFOLLOW || 0) | (fs.constants.O_NONBLOCK || 0));
      const stat = fs.fstatSync(fd);
      if (!stat.isFile() || stat.size > limit) return null;
      const buffer = Buffer.alloc(stat.size);
      let offset = 0, count;
      while (offset < buffer.length && (count = fs.readSync(fd, buffer, offset, buffer.length - offset, offset)) > 0) offset += count;
      return offset === buffer.length ? buffer : null;
    } catch { return null; } finally { if (fd !== undefined) fs.closeSync(fd); }
  }
  function readConfig(file) {
    if (forbiddenDataPath(file) || pin(file).kind !== 'file' || fs.lstatSync(file).size > MAX_CONFIG_BYTES) return null;
    // Configs have their own budget. Past it a mapping is simply unknown:
    // the import stays unresolved exactly as without alias support.
    if (configCount >= MAX_CONFIGS) return null;
    const single = inventory(file);
    if (!single.complete || single.candidates.length !== 1 || single.candidates[0].path !== file) return null;
    const candidate = single.candidates[0], bytes = readCandidate(candidate);
    if (bytes.length > MAX_CONFIG_BYTES || configBytes + bytes.length > MAX_CONFIG_TOTAL) return null;
    configCount++; configBytes += bytes.length;
    configDependencies.push(candidate); dataBytes.set(file, Buffer.from(bytes));
    let text;
    try { text = new TextDecoder('utf-8', { fatal: true }).decode(bytes); } catch { return null; }
    const parsed = ts.parseConfigFileTextToJson(file, text.charCodeAt(0) === 0xfeff ? text.slice(1) : text);
    return !parsed.error && parsed.config && typeof parsed.config === 'object' && !Array.isArray(parsed.config) ? parsed.config : null;
  }
  // tsconfig-loader semantics: extends in order (Object.assign), then own
  // allowJs, paths (based at this file) and baseUrl. null = unknown.
  function loadConfig(file, visiting = new Set()) {
    if (configs.has(file)) return configs.get(file);
    if (visiting.has(file) || visiting.size > 16) return null;
    visiting.add(file);
    let result = null;
    const config = readConfig(file);
    if (config) {
      result = {};
      const bases = config.extends === undefined ? [] : Array.isArray(config.extends) ? config.extends : [config.extends];
      for (const base of bases) {
        if (typeof base !== 'string' || !(base.startsWith('./') || base.startsWith('../')) || /[\\:\n\r\0]/.test(base)) { result = null; break; }
        const target = path.resolve(path.dirname(file), base.endsWith('.json') ? base : `${base}.json`);
        const loaded = within(root, target) && !excluded(target) ? loadConfig(target, visiting) : null;
        if (!loaded) { result = null; break; }
        Object.assign(result, loaded);
      }
      const options = config.compilerOptions ?? {};
      if (result && (typeof options !== 'object' || Array.isArray(options) || Array.isArray(config.references) && config.references.length ||
          config.references !== undefined && !Array.isArray(config.references))) result = null;
      if (result) {
        if (options.allowJs !== undefined) result.allowJs = options.allowJs;
        if (options.paths !== undefined) {
          const valid = options.paths && typeof options.paths === 'object' && !Array.isArray(options.paths) &&
            Object.keys(options.paths).length <= MAX_PATH_KEYS &&
            Object.entries(options.paths).every(([key, values]) => key.split('*').length <= 2 && Array.isArray(values) && values.length <= MAX_PATH_VALUES &&
              values.every(value => typeof value === 'string' && value.split('*').length <= 2 && !/[\\:\n\r\0]/.test(value)));
          result = valid ? { ...result, paths: { mapping: options.paths, base: path.dirname(file) } } : null;
        }
        if (result && options.baseUrl !== undefined) {
          result = typeof options.baseUrl === 'string' && !/[\\:\n\r\0]/.test(options.baseUrl) ?
            { ...result, baseUrl: path.resolve(path.dirname(file), options.baseUrl) } : null;
        }
      }
    }
    if (result && path.basename(file) === 'jsconfig.json' && result.allowJs === undefined) result.allowJs = true;
    if (result) result.id = file;
    visiting.delete(file);
    configs.set(file, result);
    return result;
  }
  // The nearest config folder above the importer, inside the pinned scope.
  function nearestConfig(file) {
    for (let directory = path.dirname(file); within(root, directory); directory = path.dirname(directory)) {
      for (const name of ['tsconfig.json', 'jsconfig.json']) {
        const candidate = path.join(directory, name);
        if (pin(candidate).kind === 'file') return loadConfig(candidate);
      }
      if (directory === root) break;
    }
    return null; // the governing config may lie outside the pinned scope
  }
  // Whether the governing config has any paths key or baseUrl that could
  // apply to this specifier. Without one, Node resolution is the only path.
  function frameworkMappingPossible(file, specifier) {
    if (!aliasesEnabled()) return false;
    const config = nearestConfig(file);
    if (!config) return false;
    if (config.baseUrl) return true;
    return Object.keys(config.paths?.mapping ?? {}).some(key => {
      if (!key.includes('*')) return key === specifier;
      const [prefix, suffix] = key.split('*');
      return specifier.startsWith(prefix) && specifier.endsWith(suffix) && specifier.length >= prefix.length + suffix.length;
    });
  }
  let aliasProbes = 0;
  function existing(candidate) {
    if (!within(root, candidate) || excluded(candidate)) return undefined;
    if ((aliasProbes += 1 + 2 * EXTENSIONS.length) > MAX_ALIAS_PROBES) return undefined;
    const observed = pin(candidate);
    // A mapped directory may select its package.json main field.
    if (observed.kind === 'directory' && pin(path.join(candidate, 'package.json')).kind !== 'absent') return undefined;
    const base = /\.(?:js|jsx|mjs|cjs)$/.test(candidate) ? candidate.slice(0, candidate.lastIndexOf('.')) : candidate;
    const alternatives = [...new Set([candidate, ...EXTENSIONS.map(ext => `${base}.${ext}`), ...EXTENSIONS.map(ext => path.join(candidate, `index.${ext}`))])];
    const matches = alternatives.filter(name => pin(name).kind === 'file');
    if (matches.length > 1) return undefined;
    return matches[0] ?? null;
  }
  // { file } when the mapping proves one in-scope source file, { package }
  // when no mapping applies (Node resolution follows), otherwise unknown.
  const aliasResults = new Map();
  function resolveAlias(file, specifier) {
    if (specifier.startsWith('node:') || BUILTINS.has(specifier)) return { package: true };
    if (!aliasesEnabled()) return { unknown: true };
    const config = nearestConfig(file);
    if (!config) return { unknown: true };
    if (!/\.tsx?$/.test(file) && !config.allowJs) return { package: true };
    // One result per (config, specifier), misses included.
    const key = `${config.id}\0${specifier}`;
    if (!aliasResults.has(key)) aliasResults.set(key, mapAlias(config, specifier));
    return aliasResults.get(key);
  }
  // Framework specifiers get no exception: Playwright's resolver applies
  // wildcard and baseUrl mappings to `@playwright/test` too, so an in-scope
  // match is a user module, never the official package. A mapping into
  // node_modules reaches the installed package and leaves it official.
  const PACKAGE = Symbol('package');
  function mapAlias(config, specifier) {
    const base = config.baseUrl ?? config.paths?.base;
    const framework = FRAMEWORK_SPECIFIERS.has(specifier);
    const entries = Object.entries(config.paths?.mapping ?? {})
      .concat(config.baseUrl ? [['*', ['*']]] : []);
    let longest = -1, selected = null;
    for (const [key, values] of entries) {
      const [prefix, suffix] = key.split('*');
      let matched = specifier;
      if (key.includes('*')) {
        if (prefix && !specifier.startsWith(prefix)) continue;
        if (prefix) matched = matched.slice(prefix.length);
        if (suffix && !specifier.endsWith(suffix)) continue;
        if (suffix) matched = matched.slice(0, matched.length - suffix.length);
      } else if (specifier !== key) continue;
      if (prefix.length <= longest) continue;
      for (const value of values) {
        const target = path.resolve(base, value.includes('*') ? value.replace('*', matched) : value);
        if (framework && target.split(path.sep).includes('node_modules')) {
          // Opaque installed package: only an exact absence check is unknown.
          if (within(root, target) && pin(target).kind !== 'absent') { longest = prefix.length; selected = PACKAGE; }
          continue;
        }
        const found = existing(target);
        if (found === undefined) return { unknown: true };
        if (found) { longest = prefix.length; selected = found; }
      }
    }
    if (!selected || selected === PACKAGE) return { package: true };
    // Same credential/agent-config boundary as configuration reads.
    return /\.(?:ts|tsx|js|jsx|mts|mjs|cts|cjs)$/.test(selected) && !forbiddenDataPath(selected) ? { file: selected } : { unknown: true };
  }
  // ---- workspace packages ----
  // The `name` of the package.json in a directory: '' when absent or
  // unnamed, null when it cannot be read. Never follows a symbolic link.
  const packages = new Map(), packageConfigs = new Map();
  function packageName(directory) {
    if (packages.has(directory)) return packages.get(directory);
    let name = null;
    try {
      const file = path.join(directory, 'package.json');
      const kind = within(root, file) && !excluded(file) ? pin(file).kind : null;
      if (kind === 'absent') name = '';
      else if (kind === 'file') {
        const config = readConfig(file);
        if (config) { name = typeof config.name === 'string' ? config.name : ''; packageConfigs.set(directory, config); }
      }
    } catch { name = null; }
    packages.set(directory, name);
    return name;
  }
  // name -> package directory for the workspaces the project root declares
  // (package.json `workspaces`, or pnpm-workspace.yaml `packages`). Only
  // literal directories and a trailing `/*` are expanded; directories are
  // listed without following links. null when the declaration is unknown.
  let workspaceMap;
  const MAX_WORKSPACES = 512;
  function workspacePatterns() {
    const manifestFile = path.join(root, 'package.json');
    const config = pin(manifestFile).kind === 'file' ? readConfig(manifestFile) : null;
    if (pin(manifestFile).kind === 'file' && !config) return null;
    let patterns = config?.workspaces === undefined ? undefined : Array.isArray(config.workspaces) ? config.workspaces : config.workspaces?.packages;
    if (config?.workspaces !== undefined && !Array.isArray(patterns)) return null;
    const pnpm = path.join(root, 'pnpm-workspace.yaml');
    if (pin(pnpm).kind === 'file') {
      const bytes = readRegular(pnpm, MAX_MARKER_BYTES);
      if (!bytes) return null;
      const lines = bytes.toString('utf8').split(/\r?\n/), listed = [];
      let section = false, seen = false;
      for (const line of lines) {
        if (/^\s*(#.*)?$/.test(line)) continue;
        if (/^packages:\s*(#.*)?$/.test(line)) { section = true; seen = true; continue; }
        if (!/^\s/.test(line)) { section = false; continue; }
        if (!section) continue;
        const item = /^\s+-\s+(?:'([^']*)'|"([^"]*)"|([^'"#\s]+))\s*(#.*)?$/.exec(line);
        if (!item) return null;
        listed.push(item[1] ?? item[2] ?? item[3]);
      }
      if (!seen) return null;
      patterns = [...(patterns ?? []), ...listed];
    }
    return patterns ?? [];
  }
  function workspaces() {
    if (workspaceMap !== undefined) return workspaceMap;
    workspaceMap = null;
    try {
      const patterns = workspacePatterns();
      if (!patterns || !patterns.every(item => typeof item === 'string')) return workspaceMap;
      const directories = [];
      for (let pattern of patterns) {
        pattern = pattern.replace(/^\.\//, '').replace(/\/+$/, '');
        if (!pattern || /[!?{}\[\]\\:\n\r\0]|\*\*/.test(pattern) || pattern.split('/').some(part => part === '..' || part === '.')) return workspaceMap;
        const parts = pattern.split('/');
        if (parts.slice(0, -1).some(part => part.includes('*')) || parts.at(-1).includes('*') && parts.at(-1) !== '*') return workspaceMap;
        if (parts.at(-1) !== '*') { directories.push(path.join(root, ...parts)); continue; }
        const parent = path.join(root, ...parts.slice(0, -1));
        if (!within(root, parent) || excluded(parent)) return workspaceMap;
        const kind = pin(parent).kind;
        if (kind === 'absent') continue;
        if (kind !== 'directory') return workspaceMap;
        for (const entry of fs.readdirSync(parent, { withFileTypes: true })) {
          // A linked workspace entry is not followed: its name stays unknown.
          if (entry.isSymbolicLink()) return workspaceMap;
          if (entry.isDirectory() && !EXCLUDED.has(entry.name)) directories.push(path.join(parent, entry.name));
        }
      }
      if (directories.length > MAX_WORKSPACES) return workspaceMap;
      const map = new Map();
      for (const directory of directories) {
        if (!within(root, directory) || excluded(directory) || pin(directory).kind !== 'directory') continue;
        const name = packageName(directory);
        if (name === null) return workspaceMap;
        if (name) map.set(name, map.has(name) ? false : directory);
      }
      workspaceMap = map;
    } catch { workspaceMap = null; }
    return workspaceMap;
  }
  // `name` or `name/sub` of a declared workspace package, to one pinned
  // source file: its `main` (or index) or the subpath. A package with an
  // `exports` map, or a target outside the package, stays unresolved.
  function workspaceResolve(specifier) {
    const map = workspaces();
    if (!map) return null;
    const parts = specifier.split('/');
    const size = specifier.startsWith('@') ? 2 : 1;
    if (parts.length < size || parts.slice(0, size).some(part => !part)) return null;
    const directory = map.get(parts.slice(0, size).join('/'));
    const config = directory && packageConfigs.get(directory);
    if (!config || config.exports !== undefined) return null;
    const sub = parts.slice(size).join('/');
    const target = sub ? path.resolve(directory, sub) : typeof config.main === 'string' ? path.resolve(directory, config.main) : path.join(directory, 'index');
    if (!within(directory, target) || target === directory) return null;
    const found = existing(target);
    return found && /\.(?:ts|tsx|js|jsx|mts|mjs|cts|cjs)$/.test(found) && !forbiddenDataPath(found) ? found : null;
  }
  function edges(bytes, file) {
    const model = sourceModel(bytes, file), result = [];
    if (model.diagnostics.length) { add('import-parse-invalid', file); return result; }
    function emit(node, specifier, dataLeaf = false) {
      if (specifier && (ts.isStringLiteral(specifier) || ts.isNoSubstitutionTemplateLiteral(specifier))) result.push({ specifier: specifier.text, start: node.getStart(model.source), dataLeaf });
    }
    walk(model.source, node => {
      if (ts.isImportDeclaration(node)) {
        const clause = node.importClause, bindings = clause?.namedBindings;
        if (!clause?.isTypeOnly && (!bindings || !ts.isNamedImports(bindings) || clause.name || bindings.elements.some(item => !item.isTypeOnly))) emit(node, node.moduleSpecifier, Boolean(clause?.name && !bindings && ts.isStringLiteral(node.moduleSpecifier) && node.moduleSpecifier.text.endsWith('.json')));
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
        const selected = resolve(file, edge.specifier, edge.start, edge.dataLeaf);
        if (!selected || loaded.has(selected)) continue;
        if (depth >= MAX_DEPTH) { add('import-depth-limit', file, edge.start); continue; }
        if (helpers.length + dataDependencies.length >= MAX_HELPERS) { add('import-file-limit', file, edge.start); continue; }
        try {
          const stat = fs.lstatSync(selected, { bigint: true });
          if (stat.size > BigInt(MAX_HELPER_BYTES - helperBytes)) { add('import-byte-limit', file, edge.start); continue; }
          const single = inventory(selected);
          if (!single.complete || single.candidates.length !== 1 || single.candidates[0].path !== selected) throw new Error('helper inventory unavailable');
          const candidate = single.candidates[0], bytes = readCandidate(candidate);
          pin(selected);
          if (helperBytes + bytes.length > MAX_HELPER_BYTES) { add('import-byte-limit', file, edge.start); continue; }
          if (edge.dataLeaf) {
            try { JSON.parse(new TextDecoder('utf-8', { fatal: true }).decode(bytes)); }
            catch { add('import-json-invalid', file, edge.start); continue; }
            // Pin data for integrity only. Never parse it as source, traverse its
            // contents as imports, or expose it to framework/receiver provenance.
            dataDependencies.push(candidate); dataBytes.set(selected, Buffer.from(bytes));
            loaded.add(selected); helperBytes += bytes.length;
            continue;
          }
          copied.set(selected, Buffer.from(bytes)); loaded.add(selected); helperBytes += bytes.length;
          helpers.push(candidate); expanded.candidates.push(candidate); queue.push({ file: selected, depth: depth + 1 });
        } catch { add('import-read-unavailable', file, edge.start); }
      }
    }
    // The package (by package.json name) that holds each pinned file: a bare
    // import of that name could reach the file through a linked install.
    for (const file of copied.keys()) {
      for (let directory = path.dirname(file); within(root, directory); directory = path.dirname(directory)) {
        packageName(directory);
        if (directory === root) break;
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
      for (const candidate of [...dataDependencies, ...configDependencies]) if (!readCandidate(candidate).equals(dataBytes.get(candidate.path))) throw new Error('data drift');
      for (const candidate of expanded.candidates) if (!readCandidate(candidate).equals(copied.get(candidate.path))) throw new Error('source drift');
    } catch { result.push({ code: 'import-snapshot-drift' }); }
    return { complete: result.length === 0, diagnostics: result };
  }
  return { manifest: expanded, sources: copied, helpers, dataDependencies, diagnostics, revalidate, aliases, unresolvedImports, packages };
}
