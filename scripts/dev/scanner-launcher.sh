#!/bin/bash -p
# SPDX-License-Identifier: Apache-2.0
# Copied to the installed reviewer's scripts/scan.sh by the runtime builder.
# Only this trusted local launcher starts Node; no target-project executable,
# package manager, shell analyzer or automatic download is used.
builtin unset ENV BASH_ENV CDPATH GLOBIGNORE NODE_OPTIONS NODE_PATH
builtin unset LD_PRELOAD LD_LIBRARY_PATH DYLD_INSERT_LIBRARIES DYLD_LIBRARY_PATH
while IFS= builtin read -r scanner_function; do
  builtin unset -f "$scanner_function"
done < <(builtin compgen -A function)
builtin shopt -u expand_aliases
builtin unalias -a 2>/dev/null || true
builtin export PATH=/usr/bin:/bin:/usr/sbin:/sbin LANG=C LC_ALL=C
builtin set -uo pipefail

scanner_node=
for scanner_candidate in /opt/homebrew/bin/node /usr/local/bin/node /usr/bin/node /bin/node; do
  if [[ -f "$scanner_candidate" && -x "$scanner_candidate" ]] &&
      "$scanner_candidate" -e 'process.exit(Number(process.versions.node.split(".")[0]) >= 22 ? 0 : 2)' >/dev/null 2>&1; then
    scanner_node="$scanner_candidate"
    break
  fi
done
if [[ -z "$scanner_node" ]]; then
  builtin printf '%s\n' 'INCOMPLETE: scanner requires Node.js 22 or newer at a standard system or Homebrew path. Nothing was installed.' >&2
  exit 2
fi

"$scanner_node" --input-type=module - "${BASH_SOURCE[0]}" "$@" <<'SCANNER_NODE'
import fs from 'node:fs';
import path from 'node:path';
import crypto from 'node:crypto';
import { pathToFileURL } from 'node:url';

try {
  const launcher = fs.realpathSync(process.argv[2]);
  const root = path.join(path.dirname(launcher), 'scanner');
  const regular = file => {
    let current = root;
    if (!fs.lstatSync(current).isDirectory() || fs.lstatSync(current).isSymbolicLink()) throw Error('runtime directory');
    const pieces = file.split('/');
    if (!pieces.length || pieces.some(part => !part || part === '.' || part === '..') || file.includes('\\')) throw Error('runtime path');
    for (const [index, piece] of pieces.entries()) {
      current = path.join(current, piece);
      const stat = fs.lstatSync(current);
      if (stat.isSymbolicLink() || (index === pieces.length - 1 ? !stat.isFile() : !stat.isDirectory())) throw Error('runtime file');
    }
    return fs.readFileSync(current);
  };
  const manifest = JSON.parse(regular('manifest.json').toString('utf8'));
  if (manifest.schema !== 'e2e-skills-scanner-runtime-v1' || manifest.entrypoint !== 'src/cli.mjs' ||
      !manifest.files || typeof manifest.files !== 'object' || Array.isArray(manifest.files) ||
      !Object.hasOwn(manifest.files, manifest.entrypoint)) throw Error('runtime manifest');
  const actual = [];
  const inventory = (directory, prefix = '') => {
    for (const name of fs.readdirSync(directory)) {
      const relative = prefix + name, file = path.join(directory, name);
      const stat = fs.lstatSync(file);
      if (stat.isSymbolicLink()) throw Error('runtime symbolic link');
      if (stat.isDirectory()) inventory(file, relative + '/');
      else if (stat.isFile()) {
        if (relative !== 'manifest.json') actual.push(relative);
      } else throw Error('runtime non-regular entry');
    }
  };
  inventory(root);
  if (JSON.stringify(actual.sort()) !== JSON.stringify(Object.keys(manifest.files).sort())) throw Error('runtime file inventory');
  for (const [name, expected] of Object.entries(manifest.files)) {
    if (!expected || !Number.isSafeInteger(expected.bytes) || expected.bytes < 0 ||
        !/^[a-f0-9]{64}$/.test(expected.sha256)) throw Error('runtime manifest record');
    const bytes = regular(name);
    if (bytes.length !== expected.bytes || crypto.createHash('sha256').update(bytes).digest('hex') !== expected.sha256) throw Error('runtime integrity');
  }
  const supplied = process.argv.slice(3);
  if (supplied.length === 1 && ['--help', '-h'].includes(supplied[0])) {
    process.argv = [process.execPath, path.join(root, manifest.entrypoint), '--help'];
  } else {
    let hasRoot = false, hasFormat = false, hasReport = false;
    for (let index = 0; index < supplied.length; index++) {
      const arg = supplied[index];
      if (['--format', '--report-file', '--fail-on'].includes(arg)) {
        if (arg === '--format') hasFormat = true;
        if (arg === '--report-file') hasReport = true;
        index++;
      } else if (!arg.startsWith('-')) hasRoot = true;
    }
    const args = ['--scan', ...supplied];
    if (!hasRoot) args.push('.');
    if (!hasFormat && !hasReport) args.push('--format', 'text');
    process.argv = [process.execPath, path.join(root, manifest.entrypoint), ...args];
  }
  await import(pathToFileURL(path.join(root, manifest.entrypoint)).href);
} catch {
  // Do not echo source-controlled parser messages or paths into this boundary.
  process.stderr.write('INCOMPLETE: scanner runtime is missing, damaged, or could not complete. Reinstall the skill and retry.\n');
  process.exitCode = 2;
}
SCANNER_NODE
scanner_status=$?
case "$scanner_status" in
  0|1|2) exit "$scanner_status" ;;
  *) builtin printf '%s\n' 'INCOMPLETE: scanner process failed.' >&2; exit 2 ;;
esac
