// SPDX-License-Identifier: Apache-2.0
// Compatibility entrypoint; the experimental inventory has one implementation.
import fs from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';
import { inventory, revalidate } from '../../../packages/scanner/src/inventory.mjs';
export { inventory, revalidate } from '../../../packages/scanner/src/inventory.mjs';

if (process.argv[1] && path.resolve(process.argv[1]) === fileURLToPath(import.meta.url)) {
  let report;
  try {
    const args = process.argv.slice(2);
    if (args.length === 1 && args[0] !== '--revalidate') report = inventory(args[0]);
    else if (args.length === 2 && args[0] === '--revalidate') report = revalidate(JSON.parse(fs.readFileSync(args[1], 'utf8')));
    else report = { complete: false, errors: [{ code: 'invalid-request', path: '', detail: 'usage: node inventory.mjs ROOT | --revalidate MANIFEST.json' }] };
  } catch (cause) { report = { complete: false, errors: [{ code: 'invalid-request', path: '', detail: cause.message }] }; }
  process.stdout.write(`${JSON.stringify(report, null, 2)}\n`);
  process.exitCode = report.complete ? 0 : 2;
}
