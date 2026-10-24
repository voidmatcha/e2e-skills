#!/usr/bin/env node
// SPDX-License-Identifier: Apache-2.0
import fs from 'node:fs';
import path from 'node:path';
import { spawnSync } from 'node:child_process';
import { fileURLToPath } from 'node:url';
import { inventory } from './inventory.mjs';
import { readCandidate } from './read-candidate.mjs';
import { discoverAssertion, discoverPost, bindAssertion, bindPost, parserIdentity } from './check-candidates.mjs';

const HELP = `Usage:
  e2e-skills-check discover assertion|post SOURCE_ROOT SOURCE_REL
  e2e-skills-check discover --explain assertion|post SOURCE_ROOT SOURCE_REL
  e2e-skills-check bind CANDIDATE_JSON BINDING_JSON
  e2e-skills-check probe [run-probe.mjs arguments]

Discover and bind write JSON to stdout without executing project code or
changing source files. Bind requires a manually prepared execution plan.
LLMs select targets, supply plans and interpret results; this CLI structures
candidates, checks plans and preserves execution evidence. Missing bind inputs
return NEEDS_INPUT (exit 2); full plan validation remains probe preview's job.
Candidates prove neither assertion sensitivity nor behavior-fault detection.
Default discovery keeps its JSON array. --explain adds static support diagnostics;
no supported candidate exits 2 and never means the project has no problems.
The probe command uses the bundled Node.js runner. It previews by default;
execution requires --execute --trust-checkout --approve-sha256 HASH. Commands
have host access; phase copies are not an OS sandbox. No dependencies, browser,
observer or test command are installed or inferred.
`;
function bytes(filename) {
  const result = inventory(filename);
  if (!result.complete || result.candidates.length !== 1) throw new Error('source must be a stable supported regular file');
  return readCandidate(result.candidates[0]);
}
function readJson(filename, label) {
  const text = fs.readFileSync(filename, 'utf8');
  try { return JSON.parse(text); }
  catch { throw new Error(`invalid ${label} JSON`); }
}
// Missing-input output contains field names and static reasons, never plan values.
function bindOrRequirements(candidate, binding, bind) {
  if (!binding || typeof binding !== 'object' || Array.isArray(binding)) throw new Error('binding must be an object');
  const post = ['omit-awaited-post-statement-v1', 'omit-post-promise-chain-statement-v1'].includes(candidate.operator);
  const required = ['source', 'test_selector',
    ...(post ? ['test_paths'] : []),
    'promise', 'test', ...(post ? ['observer'] : []),
    'report', 'expected_failure'];
  const missing = required.filter(field => !binding[field]);
  if (!missing.length) return bind(candidate, binding);
  if (binding.source) {
    // Preserve the binder's source/pin validation before reporting missing inputs.
    try { return bind(candidate, binding); }
    catch (error) { if (!/^explicit binding required: /.test(error.message)) throw error; }
  } else {
    // Without the root, freshness cannot yet be checked. Reject malformed
    // candidate envelopes rather than reporting their defects as missing inputs.
    const hash = value => typeof value === 'string' && /^[a-f0-9]{64}$/.test(value);
    const range = candidate.range;
    if (candidate.version !== 1 || !candidate.path || path.isAbsolute(candidate.path) ||
        candidate.path.includes('\\') || candidate.path.split('/').some(p => !p || ['.', '..'].includes(p)) ||
        !hash(candidate.source_sha256) || !candidate.parser ||
        candidate.parser.version !== parserIdentity().version || candidate.parser.sha256 !== parserIdentity().sha256 ||
        !range || !['utf16_start', 'utf16_end', 'byte_start', 'byte_end'].every(k => Number.isSafeInteger(range[k]) && range[k] >= 0) ||
        range.utf16_end <= range.utf16_start || range.byte_end <= range.byte_start ||
        typeof candidate.before !== 'string' || !candidate.before || typeof candidate.after !== 'string' || !candidate.after ||
        !Number.isSafeInteger(candidate.line) || candidate.line < 1 || !Number.isSafeInteger(candidate.column) || candidate.column < 1) {
      throw new Error('malformed candidate');
    }
  }
  // The existing POST binder checks these after its missing-field loop. Do not
  // hide an already supplied invalid path list behind another missing field.
  if (post && binding.test_paths) {
    if (!Array.isArray(binding.test_paths) || !binding.test_paths.length || binding.test_paths.includes(candidate.path) ||
        binding.test_paths.some(p => typeof p !== 'string' || !p || path.isAbsolute(p) || p.includes('\\') || p.split('/').some(part => !part || ['.', '..'].includes(part)))) {
      throw new Error('invalid POST test_paths');
    }
  }
  process.exitCode = 2;
  return { schema: 'e2e-skills-check-requirements-v1', status: 'NEEDS_INPUT',
    operator: candidate.operator,
    requirements: missing.map(field => ({ field, reason: field === 'source' ?
      'Absolute project root required to verify the candidate source pin.' :
      'Explicit manual binding required; no value is inferred.' })) };
}
function main(args) {
  if (args.length === 1 && ['--help', '-h'].includes(args[0])) { process.stdout.write(HELP); return; }
  if (args[0] === 'probe') {
    const runner = fileURLToPath(new URL('../scripts/run-probe.mjs', import.meta.url));
    const result = spawnSync(process.execPath, [runner, ...args.slice(1)], { stdio: 'inherit' });
    if (result.error || result.signal) throw new Error('probe process did not complete');
    process.exitCode = result.status ?? 2;
    return;
  }
  const explain = args[0] === 'discover' && args[1] === '--explain';
  if (explain) args = [args[0], ...args.slice(2)];
  let value;
  if (args.length === 4 && args[0] === 'discover' && ['assertion', 'post'].includes(args[1])) {
    const root = fs.realpathSync(args[2]), relative = args[3];
    if (path.isAbsolute(relative) || relative.includes('\\') || relative.split('/').some(part => !part || ['.', '..'].includes(part))) throw new Error('safe relative source path required');
    const filename = path.join(root, relative);
    if (fs.realpathSync(filename) !== filename) throw new Error('source symlinks forbidden');
    const diagnostics = [];
    value = (args[1] === 'assertion' ? discoverAssertion : discoverPost)(bytes(filename), relative, { diagnostics });
    if (explain) {
      const found = value.length > 0;
      value = { schema: 'e2e-skills-check-discovery-v1',
        status: found ? 'CANDIDATES_FOUND' : 'NO_SUPPORTED_CANDIDATE',
        operator: args[1], candidates: value, diagnostics,
        limitation: 'Syntactic candidates only; no runtime execution or test quality verdict.' };
      if (!found) process.exitCode = 2;
    }
  } else if (args.length === 3 && args[0] === 'bind') {
    const candidate = readJson(args[1], 'candidate');
    const binding = readJson(args[2], 'binding');
    const bind = candidate?.operator === 'playwright-to-have-text-literal-v1' ? bindAssertion :
      ['omit-awaited-post-statement-v1', 'omit-post-promise-chain-statement-v1'].includes(candidate?.operator) ? bindPost : null;
    if (!bind) throw new Error('unsupported candidate operator');
    value = bindOrRequirements(candidate, binding, bind);
  } else throw new Error('unsupported command or argument count');
  process.stdout.write(`${JSON.stringify(value, null, 2)}\n`);
}
try { main(process.argv.slice(2)); }
catch (error) { process.stderr.write(`${error.message}\n${HELP}`); process.exitCode = 2; }
