// SPDX-License-Identifier: Apache-2.0
import assert from 'node:assert/strict';
import { test } from 'node:test';
import { createHash } from 'node:crypto';
import path from 'node:path';
import { createScope } from '../src/scope.mjs';
import { sourceModel, walk, ts } from '../src/source.mjs';

const root = '/pinned-project';
function fixture(files) {
  const sources = new Map(Object.entries(files).map(([file, text]) => [path.join(root, file), Buffer.from(text)]));
  const manifest = { schema: 'node-candidate-inventory-v1', complete: true, errors: [],
    root: { canonical: root, requested: root, kind: 'directory' },
    candidates: [...sources].map(([file, bytes]) => ({ path: file, identity: { size: String(bytes.length), sha256: createHash('sha256').update(bytes).digest('hex') } })) };
  return { sources, manifest, scope: createScope({ sources, manifest }) };
}
const binding = (scope, file, name, position) => scope.binding(path.join(root, file), name, position);

test('direct bindings preserve rename, namespace, type-only and lexical identity', () => {
  const text = "import { test as scenario, expect } from '@playwright/test';\nimport * as pw from '@playwright/test';\nimport type { test as typed } from '@playwright/test';\nfunction local(scenario) { scenario.only('shadow',()=>{}); }\nscenario.only('real',()=>{});";
  const { scope } = fixture({ 'test.ts': text });
  assert.equal(binding(scope, 'test.ts', 'scenario').kind, 'playwright-test');
  assert.equal(binding(scope, 'test.ts', 'expect').kind, 'playwright-expect');
  assert.equal(binding(scope, 'test.ts', 'pw').kind, 'playwright-namespace');
  assert.equal(binding(scope, 'test.ts', 'typed').kind, 'none');
  assert.equal(binding(scope, 'test.ts', 'scenario', text.indexOf('scenario.only')).kind, 'none');
  assert.equal(binding(scope, 'test.ts', 'scenario', text.lastIndexOf('scenario.only')).kind, 'playwright-test');
  assert.equal(scope.validate().complete, true);
  assert.deepEqual(scope.framework(path.join(root, 'test.ts')).frameworks, ['playwright']);
});

test('relative fixture .extend, named/default re-exports and star barrels preserve exact export binding', () => {
  const { scope } = fixture({
    'fixture.ts': "import { test as base } from '@playwright/test';\nexport const test = base.extend({});\nexport const custom = {only(){}};",
    'barrel.ts': "export { test, test as default, custom } from './fixture';",
    'star.ts': "export * from './barrel';",
    'test.ts': "import { test as scenario, custom } from './star';\nimport defaultTest from './barrel';\nimport * as fixtures from './barrel';\nfixtures.test.only('x',()=>{});",
  });
  assert.equal(binding(scope, 'test.ts', 'scenario').kind, 'playwright-test');
  assert.equal(binding(scope, 'test.ts', 'defaultTest').kind, 'playwright-test');
  assert.equal(binding(scope, 'test.ts', 'custom').kind, 'none');
  const file = path.join(root, 'test.ts');
  const model = sourceModel(Buffer.from("import { test as scenario, custom } from './star';\nimport defaultTest from './barrel';\nimport * as fixtures from './barrel';\nfixtures.test.only('x',()=>{});"), file);
  let receiver;
  walk(model.source, node => { if (ts.isCallExpression(node)) receiver = node.expression.expression; });
  assert.equal(scope.expression(file, receiver).kind, 'playwright-test');
});

test('foreign imports and custom sibling exports do not inherit Playwright provenance', () => {
  const { scope } = fixture({
    'mixed.ts': "export { test } from '@playwright/test';\nexport { it } from 'mocha';\nexport const scenario = {only(){}};",
    'test.ts': "import { test, it, scenario } from './mixed';",
  });
  assert.equal(binding(scope, 'test.ts', 'test').kind, 'playwright-test');
  assert.equal(binding(scope, 'test.ts', 'it').kind, 'foreign');
  assert.equal(binding(scope, 'test.ts', 'scenario').kind, 'none');
});

test('module aliases, missing dependencies, ambiguity, cycles and mutable factories remain incomplete', () => {
  const { scope } = fixture({
    'test.ts': "import { test as alias } from '@/fixtures';\nimport { test as missing } from './missing';\nimport { test as ambiguous } from './ambiguous';\nimport { test as cyclic } from './cycle';\nimport { test as base } from '@playwright/test';\nlet mutable = base;\nconst factory = arbitrary();",
    'ambiguous.ts': "export { test } from '@playwright/test';",
    'ambiguous.js': "export const test = custom;",
    'cycle.ts': "export { test } from './cycle';",
  });
  for (const name of ['alias', 'missing', 'ambiguous', 'cyclic', 'mutable', 'factory']) {
    const result = binding(scope, 'test.ts', name);
    assert.equal(result.kind, 'unknown', name);
    assert.equal(result.complete, false, name);
    assert.ok(result.reasons.length > 0);
  }
});

test('excluded trees and dependencies outside pinned project cannot prove a binding', () => {
  const { scope } = fixture({
    'test.ts': "import { test as outside } from '../outside';\nimport { test as vendor } from './node_modules/helper';\nimport { test as absent } from './not-in-snapshot';",
    'node_modules/helper.ts': "export { test } from '@playwright/test';",
  });
  for (const name of ['outside', 'vendor', 'absent']) assert.equal(binding(scope, 'test.ts', name).complete, false);
});

test('pinned bytes reject drift and extra paths, and caller buffer mutations cannot alter frozen scope', () => {
  const { sources, manifest, scope } = fixture({ 'test.ts': "import { test } from '@playwright/test';" });
  const bytes = sources.get(path.join(root, 'test.ts'));
  bytes.fill(32);
  assert.equal(binding(scope, 'test.ts', 'test').kind, 'playwright-test');
  assert.equal(scope.validate().complete, true);
  const drifted = createScope({ manifest, sources });
  assert.equal(drifted.validate().complete, false);
  assert.equal(binding(drifted, 'test.ts', 'test').complete, false);
  sources.set('/outside/extra.ts', Buffer.from('test'));
  assert.equal(createScope({ manifest, sources }).validate().complete, false);
});

test('Cypress framework uses source/path provenance and symbol-level shadow guards', () => {
  const text = "import { it as foreign } from 'mocha';\ncy.visit('/');\nfunction f(it) { it.only('shadow',()=>{}); }\nit.only('real',()=>{});";
  const { scope } = fixture({ 'test.ts': text,
    'plain.cy.ts': "it.only('yes',()=>{});",
    'foreign.cy.ts': "import { it } from 'vitest';\ndescribe.only('unit',()=>{});",
    'shadow.ts': "function f(cy) { cy.visit('/'); }\nit.only('no',()=>{});",
    'require.ts': "require();",
    'dynamic.ts': "await import('cypress'); it.only('yes',()=>{});",
    'dynamic-foreign.cy.ts': "await import('vitest'); it.only('no',()=>{});",
  });
  assert.deepEqual(scope.framework(path.join(root, 'test.ts')).frameworks, ['cypress']);
  assert.equal(binding(scope, 'test.ts', 'it', text.indexOf("it.only('shadow'")).kind, 'none');
  assert.equal(binding(scope, 'test.ts', 'it', text.indexOf("it.only('real'")).kind, 'cypress-test');
  assert.equal(binding(scope, 'test.ts', 'foreign').kind, 'foreign');
  assert.deepEqual(scope.framework(path.join(root, 'plain.cy.ts')).frameworks, ['cypress']);
  assert.equal(binding(scope, 'plain.cy.ts', 'it').kind, 'cypress-test');
  assert.deepEqual(scope.framework(path.join(root, 'foreign.cy.ts')).frameworks, []);
  assert.deepEqual(scope.framework(path.join(root, 'shadow.ts')).frameworks, []);
  assert.deepEqual(scope.framework(path.join(root, 'require.ts')).frameworks, []);
  assert.deepEqual(scope.framework(path.join(root, 'dynamic.ts')).frameworks, ['cypress']);
  assert.deepEqual(scope.framework(path.join(root, 'dynamic-foreign.cy.ts')).frameworks, []);
});

test('js-to-ts and index resolution follows bounded legacy candidate surfaces', () => {
  const { scope } = fixture({
    'fixture.ts': "export { test } from '@playwright/test';",
    'directory/index.mts': "export { test } from '@playwright/test';",
    'test.ts': "import { test as mapped } from './fixture.js';\nimport { test as indexed } from './directory';",
  });
  assert.equal(binding(scope, 'test.ts', 'mapped').kind, 'playwright-test');
  assert.equal(binding(scope, 'test.ts', 'indexed').kind, 'playwright-test');
});


test('namespace re-exports and object CommonJS exports remain unknown', () => {
  const { scope } = fixture({
    'barrel.ts': "export * as tests from '@playwright/test';",
    'common.cjs': "module.exports = { test: require('@playwright/test').test };",
    'test.ts': "import { tests } from './barrel';\nconst { test: common } = require('@playwright/test');\nimport equals = require('./barrel');\nimport { test as exportedCommon } from './common.cjs';",
  });
  assert.equal(binding(scope, 'test.ts', 'common').kind, 'playwright-test');
  assert.equal(binding(scope, 'test.ts', 'equals').kind, 'module-namespace');
  for (const name of ['tests', 'exportedCommon']) {
    assert.equal(binding(scope, 'test.ts', name).complete, false, name);
  }
});


test('literal CommonJS and import-equals bindings retain direct test and namespace provenance', () => {
  const { scope } = fixture({
    'test.cjs': "const pw = require('@playwright/test');\nconst scenario = require('@playwright/test').test;\nconst { test: renamed } = require('@playwright/test');\nconst { test } = require('@playwright/test');",
    'equals.ts': "import pw = require('@playwright/test');\nimport type typed = require('@playwright/test');",
  });
  assert.equal(binding(scope, 'test.cjs', 'pw').kind, 'playwright-namespace');
  for (const name of ['scenario', 'renamed', 'test']) assert.equal(binding(scope, 'test.cjs', name).kind, 'playwright-test');
  assert.equal(binding(scope, 'equals.ts', 'pw').kind, 'playwright-namespace');
  assert.equal(binding(scope, 'equals.ts', 'typed').kind, 'none');
  for (const file of ['test.cjs', 'equals.ts']) assert.deepEqual(scope.framework(path.join(root, file)).frameworks, ['playwright']);
});

test('relative literal require follows ESM fixture exports and whole-module CJS re-exports', () => {
  const { scope } = fixture({
    'fixture.ts': "import { test as base } from '@playwright/test';\nexport const test = base.extend({});\nexport const custom = {};",
    'reexport.cjs': "module.exports = require('./fixture');",
    'direct.cjs': "module.exports = require('@playwright/test');",
    'test.cjs': "const { test: scenario, custom } = require('./reexport.cjs');\nconst direct = require('./direct.cjs').test;\nconst fixtures = require('./fixture');",
    'equals.ts': "import fixtures = require('./reexport.cjs');",
  });
  assert.equal(binding(scope, 'test.cjs', 'scenario').kind, 'playwright-test');
  assert.equal(binding(scope, 'test.cjs', 'direct').kind, 'playwright-test');
  assert.equal(binding(scope, 'test.cjs', 'custom').kind, 'none');
  assert.equal(binding(scope, 'test.cjs', 'fixtures').kind, 'module-namespace');
  assert.equal(binding(scope, 'equals.ts', 'fixtures').kind, 'module-namespace');
});

test('require shadowing and dynamic/mutable bindings never establish Playwright identity', () => {
  const { scope } = fixture({
    'shadow.cjs': "const require = custom;\nconst pw = require('@playwright/test');\nconst {test: scenario} = require('@playwright/test');",
    'equals-shadow.ts': "const require = custom;\nimport pw = require('@playwright/test');",
    'assigned.cjs': "require = custom;\nconst pw = require('@playwright/test');",
    'assigned-equals.ts': "require = custom;\nimport pw = require('@playwright/test');",
    'unrelated-shadow.cjs': "function f(require) { require = custom; }\nconst pw = require('@playwright/test');",
    'dynamic.cjs': "const moduleName = '@playwright/test';\nconst dynamic = require(moduleName);\nlet mutable = require('@playwright/test');\nconst {test: fallback = custom} = require('@playwright/test');\nconst { ...rest } = require('@playwright/test');\nconst reassigned = require('@playwright/test');\nreassigned.test = custom;",
  });
  for (const name of ['pw', 'scenario']) assert.equal(binding(scope, 'shadow.cjs', name).complete, false);
  assert.equal(binding(scope, 'equals-shadow.ts', 'pw').complete, false);
  assert.equal(binding(scope, 'assigned.cjs', 'pw').complete, false);
  assert.equal(binding(scope, 'assigned-equals.ts', 'pw').complete, false);
  assert.equal(binding(scope, 'unrelated-shadow.cjs', 'pw').kind, 'playwright-namespace');
  for (const name of ['dynamic', 'mutable', 'fallback', 'rest', 'reassigned']) assert.equal(binding(scope, 'dynamic.cjs', name).complete, false, name);
});

test('foreign require and lexical local parameters remain distinct from Playwright', () => {
  const text = "const {test} = require('@playwright/test');\nconst {it} = require('mocha');\nfunction f(test) { test.only('shadow',()=>{}); }\ntest.only('real',()=>{});";
  const { scope } = fixture({ 'test.cjs': text });
  assert.equal(binding(scope, 'test.cjs', 'it').kind, 'foreign');
  assert.equal(binding(scope, 'test.cjs', 'test', text.indexOf('test.only')).kind, 'none');
  assert.equal(binding(scope, 'test.cjs', 'test', text.lastIndexOf('test.only')).kind, 'playwright-test');
});

test('conditional/multiple CJS writes and shadowed module objects stay unproven', () => {
  const { scope } = fixture({
    'conditional.cjs': "if (ready) module.exports = require('@playwright/test');",
    'multiple.cjs': "module.exports = require('@playwright/test');\nmodule.exports = custom;",
    'shadow.cjs': "const module = custom; module.exports = require('@playwright/test');",
    'mixed.cjs': "export const test = custom; module.exports = require('@playwright/test');",
    'test.cjs': "const {test: conditional} = require('./conditional.cjs');\nconst {test: multiple} = require('./multiple.cjs');\nconst {test: shadow} = require('./shadow.cjs');\nconst {test: mixed} = require('./mixed.cjs');",
  });
  for (const name of ['conditional', 'multiple', 'mixed']) assert.equal(binding(scope, 'test.cjs', name).complete, false, name);
  assert.equal(binding(scope, 'test.cjs', 'shadow').kind, 'none');
});

test('shared Cypress global proof maps pinned identifiers and distinguishes mutations from shadows', () => {
  function query(text, name = 'cy', file = 'example.cy.ts') {
    const {scope} = fixture({[file]:text});
    const absolute=path.join(root,file), external=sourceModel(Buffer.from(text),absolute);
    const identifiers=[];
    walk(external.source,node=>{if(ts.isIdentifier(node)&&node.text===name)identifiers.push(node);});
    return scope.cypressGlobal(absolute,identifiers.at(-1));
  }
  assert.equal(query("cy.wait(1);").kind,'cypress-runtime');
  assert.equal(query("Cypress.on('uncaught:exception',()=>false);",'Cypress').kind,'cypress-runtime');
  for(const write of ['cy = custom;', '[cy] = custom;', '({cy} = custom);', '({other:cy} = custom);', '({...cy} = custom);',
    'cy.wait = custom;', "cy['wait'] = custom;", 'delete cy.wait;', 'for(cy of custom) {}',
    'globalThis.cy = custom;', "globalThis['cy'].wait = custom;", 'window.cy = custom;', 'globalThis[key] = custom;']) {
    const result=query(write+'\ncy.wait(1);');
    assert.equal(result.kind,'unknown',write);
    assert.match(result.reasons.join(';'),/mutated Cypress global: cy/,write);
  }
  assert.equal(query('Cypress.on=custom;\nCypress.on("x",handler);','Cypress').kind,'unknown');
  assert.equal(query('function f(cy){cy.wait=custom;}\ncy.wait(1);').kind,'cypress-runtime');
  assert.equal(query('function f(globalThis){globalThis.cy=custom;}\ncy.wait(1);').kind,'cypress-runtime');
  for(const text of ['function f(cy){cy.wait(1);}', "import {cy} from 'vitest';cy.wait(1);"]) {
    assert.deepEqual(query(text),{kind:'none',complete:true,reasons:[]});
  }
  assert.equal(query('it.only("x",()=>{});','it','plain.ts').kind,'none');
  const {scope}=fixture({'example.cy.ts':'cy.wait(1);'});
  assert.equal(scope.cypressGlobal(path.join(root,'example.cy.ts'),{start:900,end:901}).complete,false);
});

test('Cypress shorthands retain shared scope and reject their own global writes',()=>{
  for(const name of ['it','test','describe','context','specify','suite','xit','xdescribe']) {
    const text=`${name}=custom;\n${name}.skip('x',()=>{});`;
    const {scope}=fixture({'example.cy.ts':text});
    const absolute=path.join(root,'example.cy.ts'), external=sourceModel(Buffer.from(text),absolute);
    let target;
    walk(external.source,node=>{if(ts.isIdentifier(node)&&node.text===name)target=node;});
    assert.equal(scope.cypressGlobal(absolute,target).kind,'unknown',name);
    if(['it','test','describe','context','specify'].includes(name)) assert.equal(scope.expression(absolute,target).complete,false,name);
  }
  const text='cy=custom;cy.visit("/");it.only("x",()=>{});';
  const {scope}=fixture({'plain.ts':text});
  assert.equal(scope.framework(path.join(root,'plain.ts')).complete,false);
});

test('same-file alias property writes invalidate original framework provenance', () => {
  for (const mutation of ['scenario.only = custom;', "scenario['only'] = custom;", 'delete scenario.only;',
    '({only:scenario.only} = custom);', 'for(scenario.only of custom) {}']) {
    const {scope}=fixture({'alias.ts':"import {test} from '@playwright/test';\nconst scenario=test;\n"+mutation});
    assert.equal(binding(scope,'alias.ts','test').complete,false,mutation);
  }
  for(const setup of [
    "import {test} from '@playwright/test';const scenario=test;const another=scenario;another.only=custom;",
    "import * as pw from '@playwright/test';const scenario=pw.test;scenario.only=custom;",
    "import * as pw from '@playwright/test';const {test:scenario}=pw;scenario.only=custom;",
    "const {test}=require('@playwright/test');const scenario=test;scenario.only=custom;",
  ]) {
    const {scope}=fixture({'alias.ts':setup});
    assert.equal(binding(scope,'alias.ts',setup.includes('pw')?'pw':'test').complete,false,setup);
  }
});

test('alias rebinding and unrelated lexical property writes do not mutate original object', () => {
  for(const setup of [
    'let scenario=test;scenario=custom;',
    'let scenario=test;[unused,scenario]=custom;',
    'let scenario=test;({scenario}=custom);',
    'const scenario=test;function f(scenario){scenario.only=custom;}',
    'function f(test){const scenario=test;scenario.only=custom;}',
  ]) {
    const text="import {test} from '@playwright/test';\n"+setup+"\ntest.only('real',()=>{});";
    const {scope}=fixture({'alias.ts':text});
    assert.equal(binding(scope,'alias.ts','test',text.lastIndexOf('test.only')).kind,'playwright-test',setup);
  }
});

test('Cypress lifecycle hooks have distinct global proof with shadow, foreign and mutation guards', () => {
  function query(text, name, file='case.cy.ts') {
    const {scope}=fixture({[file]:text}),absolute=path.join(root,file);
    const parsed=sourceModel(Buffer.from(text),absolute);
    let identifier;
    walk(parsed.source,node=>{if(ts.isIdentifier(node)&&node.text===name)identifier=node;});
    return {global:scope.cypressGlobal(absolute,identifier),expression:scope.expression(absolute,identifier)};
  }
  for(const name of ['before','beforeEach','after','afterEach']) {
    const call=`${name}(()=>{cy.visit('/');});`;
    const direct=query(call,name);
    assert.equal(direct.global.kind,'cypress-hook',name);
    assert.equal(direct.expression.kind,'cypress-hook',name);
    for(const text of [`function f(${name}){${call}}`, `import {${name}} from 'vitest';${name}(()=>{});`]) {
      assert.equal(query(text,name).global.kind,'none',text);
    }
    assert.equal(query(`${name}(()=>{});`,name,'unit.ts').global.kind,'none',name);
    for(const write of [`${name}=custom;`,`globalThis.${name}=custom;`,`delete globalThis.${name};`]) {
      assert.equal(query(write+call,name).global.complete,false,write);
    }
    assert.equal(query(`function f(${name}){${name}=custom;}${call}`,name).global.kind,'cypress-hook');
    assert.equal(query(`import {test} from '@playwright/test';${name}(()=>{});`,name,'case.spec.ts').global.kind,'none');
  }
});

test('Cypress global declaration aliases propagate property mutation without alias-rebinding false positives', () => {
  function query(prefix, name='cy', append=true) {
    const text=prefix+(append?`\n${name}();`:''), file='case.cy.ts', {scope}=fixture({[file]:text});
    const absolute=path.join(root,file),parsed=sourceModel(Buffer.from(text),absolute);
    let target;
    walk(parsed.source,node=>{if(ts.isIdentifier(node)&&node.text===name)target=node;});
    return scope.cypressGlobal(absolute,target);
  }
  for(const name of ['cy','Cypress','it','test','before','beforeEach','after','afterEach']) {
    for(const prefix of [
      `const alias=${name};alias.method=custom;`,
      `const alias=${name};const next=alias;delete next.method;`,
      `const alias=globalThis.${name};alias.method=custom;`,
      `const {method:alias}=${name};alias.extra=custom;`,
    ]) {
      const result=query(prefix,name);
      assert.equal(result.complete,false,prefix);
      assert.match(result.reasons.join(';'),/mutated Cypress global/,prefix);
    }
    for(const prefix of [
      `let alias=${name};alias=custom;`,
      `let alias=${name};[unused,alias]=custom;`,
      `let alias=${name};({alias}=custom);`,
      `const alias=${name};function f(alias){alias.method=custom;}`,
      `function f(${name}){const alias=${name};alias.method=custom;}`,
      `function f(globalThis){const alias=globalThis.${name};alias.method=custom;}`,
    ]) assert.equal(query(prefix,name).complete,true,prefix);
  }
  assert.equal(query("const alias=cy;alias.get=custom;function f(cy){cy();}",'cy',false).kind,'none','lexical shadow remains none even when the outer global was mutated');
});

test('assignment aliases and explicit object mutation invalidate imported framework bindings', () => {
  for (const mutation of [
    'let alias;alias=test;alias.only=custom;',
    'let alias;alias=test;let second;second=alias;second.only=custom;',
    'Object.assign(test,{only:custom});',
    'Object.defineProperty(test,"only",{value:custom});',
    'Object.defineProperties(test,{only:{value:custom}});',
    'Reflect.set(test,"only",custom);',
    'Reflect.deleteProperty(test,"only");',
    'function f(Object){Object.assign(test,{only:custom});}',
  ]) {
    const {scope}=fixture({'mutation.ts':"import {test} from '@playwright/test';"+mutation});
    assert.equal(binding(scope,'mutation.ts','test').complete,false,mutation);
  }
  for (const mutation of ['let alias;alias=test;alias=custom;', 'Object.assign(custom,{test});']) {
    const {scope}=fixture({'mutation.ts':"import {test} from '@playwright/test';"+mutation});
    assert.equal(binding(scope,'mutation.ts','test').kind,'playwright-test',mutation);
  }
});

test('Cypress global assignment aliases and explicit object mutations preserve global identity boundaries', () => {
  function query(prefix, name='cy') {
    const text=prefix+`\n${name}();`, file='mutated.cy.ts', {scope}=fixture({[file]:text});
    const absolute=path.join(root,file),parsed=sourceModel(Buffer.from(text),absolute);
    let selected;
    walk(parsed.source,node=>{if(ts.isIdentifier(node)&&node.text===name)selected=node;});
    return scope.cypressGlobal(absolute,selected);
  }
  for(const name of ['cy','Cypress','it','beforeEach']) {
    for(const prefix of [
      `let alias;alias=${name};alias.method=custom;`,
      `let alias;alias=${name};let next;next=alias;Reflect.set(next,'method',custom);`,
      `let alias;alias=globalThis.${name};delete alias.method;`,
      `Object.assign(${name},{method:custom});`,
      `Object.defineProperty(${name},'method',{value:custom});`,
      `Object.defineProperties(${name},{method:{value:custom}});`,
      `Reflect.set(${name},'method',custom);`,
      `Reflect.deleteProperty(${name},'method');`,
      `Object.assign(globalThis.${name},{method:custom});`,
    ]) assert.equal(query(prefix,name).complete,false,prefix);
    for(const prefix of [
      `let alias;alias=${name};alias=custom;`,
      `let alias;alias=${name};function f(alias){alias.method=custom;}`,
      `function f(${name}){let alias;alias=${name};alias.method=custom;}`,
      `function f(${name}){Object.assign(${name},{method:custom});}`,
      `Object.assign(custom,{value:${name}});`,
    ]) assert.equal(query(prefix,name).complete,true,prefix);
  }
});
