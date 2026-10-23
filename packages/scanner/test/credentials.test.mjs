// SPDX-License-Identifier: Apache-2.0
import assert from 'node:assert/strict';
import { test } from 'node:test';
import { credentials } from '../src/credentials.mjs';
const file = '/virtual/credential-test.spec.ts';
const scan = text => credentials(Buffer.from(text), file);

test('three legacy literal contexts produce location-only P1 candidates', () => {
  const result = scan(`loginPage.login('fake-user','NOT_A_REAL_PASSWORD_A');
page.getByLabel('Password').fill('NOT_A_REAL_PASSWORD_B');
const validUser={username:'fake-user',password:'NOT_A_REAL_PASSWORD_C'};
request.post('/login',{data:{email:'fake@example.test',password:'NOT_A_REAL_PASSWORD_D'}});`);
  assert.deepEqual(result.findings.map(x => x.line), [1,2,3,4]);
  assert.ok(result.findings.every(x => x.patternId === '#14' && x.severity === 'P1' && x.disposition === 'candidate'));
  assert.deepEqual(result.diagnostics, []);
  assert.ok(result.findings.every(x => Object.keys(x).sort().join(',') === 'column,disposition,end,file,line,origin,patternId,severity,start'));
});

test('six own-statement environment forms exclude candidates without sibling/ancestor leakage', () => {
  for (const env of ['process.env.PASSWORD','import.meta.env.PASSWORD',"Cypress.env('PASSWORD')","cy.env('PASSWORD')",'Deno.env.PASSWORD','Bun.env.PASSWORD']) {
    assert.deepEqual(scan(`login('fake-user','FAKE_LITERAL',${env});`).findings, [], env);
    assert.deepEqual(scan(`request.post('/login',{data:{email:'fake@example.test',password:${env}}});`).findings, [], env);
  }
  const result = scan(`cy.env(['PASSWORD']).then(({PASSWORD})=>cy.login('fake-user',PASSWORD));
cy.env(['PASSWORD']).then(({PASSWORD})=>{
cy.request('POST','/login',{email:'fake@example.test',password:PASSWORD});
});
login('fake-user','FAKE_LITERAL',agency.env('TENANT'));
const fromEnv=process.env.PASSWORD; login('fake-user','FAKE_LITERAL');`);
  assert.deepEqual(result.findings.map(x => x.line), [3,5,6]);
});

test('ordinary values, empty form arguments, function declarations and token boundaries stay clean', () => {
  const result = scan(`page.getByLabel('Author').fill('Jane');
tokenizer.fill('abc');
titleInput.fill('ordinary text');
passwordInput.fill('');
passwordInput.type();
function login(user='fake',password='fake'){}
class Page { login(user='fake',password='fake'){} }
const quoted="login('fake','fake')";
// passwordInput.fill('fake');
const password='FAKE_LITERAL';`);
  assert.deepEqual(result.findings, []);
  assert.deepEqual(result.diagnostics, []);
});

test('credential-shaped selector/variable/value and multiline chains retain the legacy candidate sweep', () => {
  const result = scan(`page.getByLabel('Authorization').fill('FAKE_BEARER');
input.fill('NOT_A_REAL_secret_value');
cy.get(usernameSelector)
.type('fake-user');
cy.get('[name=password]')
.should('be.visible')
.type('FAKE_PASSWORD');`);
  assert.deepEqual(result.findings.map(x => x.line), [1,2,4,7]);
});

test('unsupported dynamic and multiline shapes produce fixed diagnostics without promotion', () => {
  const result = scan("passwordInput.fill('FAKE_' + suffix);\nlogin('fake', `FAKE_${suffix}`);\nrequest.post('/login',{\ndata:{password:'FAKE_PASSWORD'}\n});\npasswordInput['fill']('FAKE_PASSWORD');\npasswordInput.fill(\n'FAKE_PASSWORD');");
  assert.deepEqual(result.findings, []);
  assert.ok(result.diagnostics.length >= 5);
});

test('immutable fake sentinels never escape through findings or any diagnostic', () => {
  const sentinels = ['NOT_A_REAL_SECRET_SENTINEL_ONE_34819','NOT_A_REAL_SECRET_SENTINEL_TWO_76352'];
  for (const text of [
    `login('fake','${sentinels[0]}');passwordInput.fill('${sentinels[1]}');`,
    `// JUSTIFIED: ${sentinels[0]}\npasswordInput.fill('${sentinels[1]}' + suffix);`,
    `const password = "${sentinels[0]}\nBROKEN_SYNTAX_${sentinels[1]}`,
    `request.post('/login',{\n password:'${sentinels[0]}',token:'${sentinels[1]}'\n});`,
  ]) {
    const bytes = Buffer.from(text), original = Buffer.from(bytes), result = credentials(bytes, file);
    const serialized = JSON.stringify(result);
    for (const sentinel of sentinels) assert.ok(!serialized.includes(sentinel));
    assert.ok(bytes.equals(original));
  }
});
