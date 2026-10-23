// SPDX-License-Identifier: Apache-2.0
import assert from 'node:assert/strict';
import { createHash } from 'node:crypto';
import test from 'node:test';
import { assertions } from '../src/assertions.mjs';
import { pageReads } from '../src/page-reads.mjs';
import { domQueries } from '../src/dom-queries.mjs';
import { createScope } from '../src/scope.mjs';
import { reviewCandidates } from '../src/review-candidates.mjs';
import { handoffDiagnostics } from '../src/review-obligations.mjs';

const FILE = '/pinned-project/example.spec.ts';
const MESSAGES = {
  '#4f': '#4f POM member truthiness requires unsupported runtime Locator provenance',
  '#17': '#17 POM selector action requires unsupported runtime Page provenance',
  '#10a': 'unsupported provenance-producing call',
};
const hash = value => createHash('sha256').update(value).digest('hex');
function fixture(pattern = '#4f', prefix = '', positional = 'first()') {
  const body = pattern === '#4f'
    ? 'const settingsPage=new SettingsPage(); expect(settingsPage.submitButton).toBeTruthy();'
    : pattern === '#17' ? "const selector='button'; await settingsPage.click(selector);"
      : 'const eventTypePage=await bookingPage.previewEventType();\n' +
        `await eventTypePage.getByTestId('time').${positional}.waitFor({state:'visible'});`;
  const bytes = Buffer.from(prefix + "import {test,expect} from '@playwright/test';\n" +
    `test('canary',async({${pattern === '#10a' ? 'bookingPage' : 'page'}})=>{\n${body}\n});\n`);
  const manifest = { schema: 'node-candidate-inventory-v1', complete: true, errors: [],
    root: { canonical: '/pinned-project', kind: 'directory' }, candidates: [{ path: FILE,
      identity: { size: String(bytes.length), sha256: hash(bytes) } }] };
  const scope = createScope({ manifest, sources: new Map([[FILE, bytes]]) });
  const detector = pattern === '#4f' ? 'assertions' : pattern === '#17' ? 'pageReads' : 'domQueries';
  const raw = ({ assertions, pageReads, domQueries })[detector](bytes, FILE, { scope });
  const diagnostics = raw.diagnostics.filter(item => item.message === MESSAGES[pattern]);
  assert.equal(diagnostics.length, 1, 'fixture must exercise a real allowed detector reason');
  const findings = reviewCandidates(bytes, FILE, { scope }).findings;
  assert.equal(findings.length, 1, 'fixture must retain a real source candidate');
  return { detector, file: FILE, bytes, diagnostics, findings };
}
function untouched(input) {
  const result = handoffDiagnostics(input);
  assert.deepEqual(result.diagnostics, input.diagnostics);
  assert.deepEqual(result.obligations, []);
  input.diagnostics.forEach((item, index) => assert.equal(result.diagnostics[index], item));
}

test('the two real detector gaps link to their retained candidates without mutation', () => {
  for (const pattern of ['#4f', '#17']) {
    const input = fixture(pattern), before = JSON.stringify(input);
    const result = handoffDiagnostics(input), diagnostic = input.diagnostics[0];
    assert.deepEqual(result.diagnostics, []);
    assert.equal(result.obligations.length, 1);
    const obligation = result.obligations[0];
    assert.deepEqual(Object.keys(obligation).sort(),
      ['causeId', 'detector', 'patternId', 'file', 'start', 'end', 'sourceSha256', 'findingId'].sort());
    assert.equal(obligation.causeId, pattern === '#4f' ? 'pom-locator-truthiness' : 'pom-page-selector');
    assert.equal(obligation.detector, input.detector);
    assert.equal(obligation.patternId, pattern);
    assert.equal(obligation.file, FILE);
    assert.equal(obligation.start, diagnostic.start);
    assert.equal(obligation.end, diagnostic.start + diagnostic.length);
    assert.equal(obligation.sourceSha256, hash(input.bytes));
    assert.match(obligation.findingId, /^finding-sha256:[0-9a-f]{64}$/);
    assert.deepEqual(handoffDiagnostics(input), result);
    assert.equal(JSON.stringify(input), before);
  }
});

test('wrong detector, pattern, severity, evidence or retained disposition does not link', () => {
  untouched({ ...fixture(), detector: 'promises' });
  for (const delta of [
    { patternId: '#17' }, { severity: 'P1' }, { disposition: 'confirmed' },
    { disposition: 'justified-review' }, { origin: 'heuristic' },
    { evidence: { kind: 'unresolved-query', requirements: ['verify-runtime-binding', 'verify-required-test-outcome'] } },
    { evidence: { kind: 'unresolved-locator', requirements: [] } },
    { evidence: undefined },
  ]) {
    const input = fixture();
    input.findings = [{ ...input.findings[0], ...delta }];
    untouched(input);
  }
  untouched({ ...fixture(), findings: [] });
});

test('wrong file, line, column or a different candidate range cannot discharge a diagnostic', () => {
  for (const field of ['file', 'line', 'column', 'start', 'end']) {
    const input = fixture(), finding = input.findings[0];
    input.findings = [{ ...finding, [field]: field === 'file' ? '/pinned-project/other.spec.ts' : finding[field] + 1 }];
    untouched(input);
  }
  const input = fixture();
  input.findings = [input.findings[0], { ...input.findings[0] }];
  untouched(input); // Ambiguous retained identity is not silently resolved.
  for (const delta of [{ file: '/pinned-project/other.spec.ts' }, { detector: 'promises' }]) {
    const input = fixture();
    input.diagnostics = [{ ...input.diagnostics[0], ...delta }];
    untouched(input);
  }
});

test('missing, invalid, partial and out-of-range diagnostic spans stay raw', () => {
  for (const delta of [
    { start: undefined }, { length: undefined }, { start: -1 }, { length: 0 },
    { start: 0.5 }, { length: 0.5 }, { start: Number.MAX_SAFE_INTEGER }, { length: Number.MAX_SAFE_INTEGER },
    { start: 0 }, { length: 1 }, { length: 100000 },
  ]) {
    const input = fixture();
    input.diagnostics = [{ ...input.diagnostics[0], ...delta }];
    untouched(input);
  }
});

test('unknown, joined, prefixed and parse diagnostics are never reclassified by their code', () => {
  for (const delta of [
    { message: 'unsupported provenance-producing call' },
    { message: 'source unavailable or syntactically invalid: /pinned-project/example.spec.ts' },
    { message: 'unsupported package/path alias: @workspace/fixtures' },
    { message: MESSAGES['#4f'] + '; missing pinned module: ./helper' },
    { message: MESSAGES['#4f'] + ' ' },
    { message: 'unknown', code: 'provenance-unsupported' },
    { code: 'parse-invalid' },
    { code: 'provenance-unsupported' },
  ]) {
    const input = fixture();
    input.diagnostics = [{ ...input.diagnostics[0], ...delta }];
    untouched(input);
  }
  const input = fixture();
  const error = { code: 'parse-invalid', message: 'parse failed', start: 0, length: 1 };
  input.diagnostics.push(error);
  const result = handoffDiagnostics(input);
  assert.equal(result.obligations.length, 1);
  assert.deepEqual(result.diagnostics, [error]);
});

test('different source expressions and syntactically invalid source cannot borrow candidate spans', () => {
  for (const pattern of ['#4f', '#17']) {
    const input = fixture(pattern);
    input.bytes = Buffer.from(input.bytes.toString().replace(pattern === '#4f' ? 'toBeTruthy' : '.click(',
      pattern === '#4f' ? 'toBeVisible' : '.print('));
    untouched(input);
  }
  const input = fixture();
  input.bytes = Buffer.from(input.bytes.toString() + '\nconst =');
  untouched(input);
});

test('spans and columns use UTF-16 positions while source hashes use complete bytes', () => {
  for (const pattern of ['#4f', '#17']) {
    const input = fixture(pattern, '// 한글 🧪\r\n');
    const result = handoffDiagnostics(input);
    assert.equal(result.obligations.length, 1);
    const obligation = result.obligations[0];
    assert.equal(obligation.sourceSha256, hash(input.bytes));
    const subject = input.bytes.toString().slice(obligation.start, obligation.end);
    assert.equal(subject, pattern === '#4f' ? 'settingsPage.submitButton' : 'settingsPage');
    assert.notEqual(Buffer.byteLength(input.bytes.toString().slice(0, obligation.start)), obligation.start);
  }
});

test('obligation IDs change with source bytes and duplicate raw diagnostics do not double count', () => {
  const input = fixture(), first = handoffDiagnostics(input).obligations[0];
  input.bytes = Buffer.from(input.bytes.toString() + '\n// unrelated change\n');
  const next = handoffDiagnostics(input).obligations[0];
  assert.notEqual(next.sourceSha256, first.sourceSha256);
  assert.notEqual(next.findingId, first.findingId);
  input.diagnostics.push({ ...input.diagnostics[0] });
  assert.deepEqual(handoffDiagnostics(input), { diagnostics: [], obligations: [next] });
});

test('obligations never serialize source, diagnostic suffixes or extra candidate metadata', () => {
  const sentinel = 'PRIVATE_SENTINEL_DO_NOT_EXPORT';
  const input = fixture('#4f', `// ${sentinel}\n`);
  input.findings[0].source = sentinel;
  input.findings[0].evidence.note = sentinel;
  const output = handoffDiagnostics(input);
  assert.equal(output.obligations.length, 1);
  assert.ok(!JSON.stringify(output.obligations).includes(sentinel));
  input.diagnostics[0] = { ...input.diagnostics[0], message: MESSAGES['#4f'] + ': ' + sentinel };
  untouched(input);
});

test('invalid top-level input is rejected rather than creating an obligation', () => {
  for (const delta of [{ file: 'relative.ts' }, { file: '/pinned-project/../other.ts' },
    { bytes: 'source' }, { diagnostics: null }, { findings: null }, { detector: null }]) {
    assert.throws(() => handoffDiagnostics({ ...fixture(), ...delta }), TypeError);
  }
});

test('factory POM first, last and nth receivers link only to their exact domQueries diagnostic', () => {
  for (const positional of ['first()', 'last()', 'nth(2)']) {
    const input = fixture('#10a', '', positional), before = JSON.stringify(input);
    const result = handoffDiagnostics(input);
    assert.deepEqual(result.diagnostics, []);
    assert.equal(result.obligations.length, 1);
    const obligation = result.obligations[0];
    assert.equal(obligation.causeId, 'pom-positional-locator');
    assert.equal(obligation.detector, 'domQueries');
    assert.equal(obligation.patternId, '#10a');
    assert.equal(input.bytes.toString().slice(obligation.start, obligation.end), "eventTypePage.getByTestId('time')");
    assert.equal(obligation.sourceSha256, hash(input.bytes));
    assert.deepEqual(handoffDiagnostics(input), result);
    assert.equal(JSON.stringify(input), before);
  }
});

test('positional handoff rejects other detectors, reasons, patterns, evidence and receiver spans', () => {
  for (const detector of ['assertions', 'pageReads', 'promises']) untouched({ ...fixture('#10a'), detector });
  for (const delta of [{ message: MESSAGES['#10a'] + '; missing pinned module' },
    { message: MESSAGES['#17'] }, { start: undefined }, { length: 1 }, { code: 'provenance-unsupported' }]) {
    const input = fixture('#10a');
    input.diagnostics = [{ ...input.diagnostics[0], ...delta }];
    untouched(input);
  }
  for (const delta of [{ patternId: '#17' }, { severity: 'P0' }, { disposition: 'confirmed' },
    { evidence: { kind: 'unresolved-page', requirements: ['verify-runtime-binding', 'verify-required-test-outcome'] } }]) {
    const input = fixture('#10a');
    input.findings = [{ ...input.findings[0], ...delta }];
    untouched(input);
  }
  const input = fixture('#10a'), finding = input.findings[0];
  input.diagnostics = [{ ...input.diagnostics[0], start: finding.start, length: finding.end - finding.start }];
  untouched(input); // A whole positional call is not the exact receiver diagnostic.
});

test('positional handoff validates method, arity and optional/computed/spread source shapes', () => {
  for (const replacement of ['.count()', '.first(1)', '.last(1)', '.nth()', '.nth(...xs)',
    '.first?.()', "['first']()", '?.first()']) {
    const input = fixture('#10a');
    input.bytes = Buffer.from(input.bytes.toString().replace('.first()', replacement));
    input.findings[0].end += replacement.length - '.first()'.length;
    untouched(input);
  }
});
