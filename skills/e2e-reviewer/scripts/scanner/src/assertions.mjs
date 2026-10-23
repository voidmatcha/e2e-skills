// SPDX-License-Identifier: Apache-2.0
// Bounded raw #8a/#8b/#8c and #4a/#4b/#4f detectors.
// Suppression, semantic adjudication and dedupe belong to callers.
import { createReceivers } from './receivers.mjs';
import { unwrap, walk, member, literalString, isWritten, objectMutationTarget, ts } from './source.mjs';

const MODIFIERS = new Set(['not', 'resolves', 'rejects']);
const BOOLEAN_STATE = new Set(['isVisible', 'isEnabled', 'isChecked', 'isDisabled', 'isEditable', 'isHidden']);

function dot(node) {
  node = unwrap(node);
  return ts.isPropertyAccessExpression(node) && !node.questionDotToken
    ? { object: node.expression, name: node.name.text } : null;
}

export function assertions(bytes, filename, { scope } = {}) {
  const receivers = createReceivers(bytes, filename, { scope });
  const { source } = receivers;
  const diagnostics = [...receivers.diagnostics], findings = [];
  if (diagnostics.length) return { findings, diagnostics };
  if (!scope) return { findings, diagnostics: [{ message: 'pinned scope is required for assertion provenance' }] };

  function proven(node, kind) {
    const value = receivers.expression(node);
    if (!value.complete) {
      const start = node.getStart(source);
      diagnostics.push({ start, length: node.end - start, message: value.reasons.join('; ') });
      return false;
    }
    return (Array.isArray(kind) ? kind : [kind]).includes(value.kind);
  }
  function diagnostic(node, message) {
    const start = node.getStart(source);
    diagnostics.push({ start, length: node.end - start, message });
  }

  // Ambient spelling is only a bounded candidate precondition. Reject lexical
  // shadows and explicit same-file writes, including writes through aliases.
  // Arbitrary external call effects are not runtime identity proof.
  function localBinding(node, name) {
    return receivers.checker.getSymbolsInScope(node, ts.SymbolFlags.Value | ts.SymbolFlags.Alias)
      .some(symbol => symbol.name === name && symbol.declarations?.some(declaration =>
        !ts.isBinaryExpression(declaration) && !(ts.isIdentifier(declaration) && member(declaration.parent)?.object === declaration)));
  }
  const ambientWrites = new Map();
  function ambient(node, name) {
    if (localBinding(node, name)) return false;
    if (!ambientWrites.has(name)) {
      let written = false;
      const host = value => ts.isIdentifier(value) && ['globalThis', 'global', 'window'].includes(value.text) && !localBinding(value, value.text);
      function reference(value) {
        value = unwrap(value);
        if (ts.isIdentifier(value)) return value.text === name && !localBinding(value, name);
        const access = member(value);
        return Boolean(access && ((host(unwrap(access.object)) && (access.name === name || access.name === null)) || reference(access.object)));
      }
      function target(value) {
        value = unwrap(value);
        if (reference(value)) written = true;
        else if (ts.isArrayLiteralExpression(value)) value.elements.forEach(target);
        else if (ts.isObjectLiteralExpression(value)) for (const entry of value.properties) {
          if (ts.isShorthandPropertyAssignment(entry)) target(entry.name);
          else if (ts.isPropertyAssignment(entry)) target(entry.initializer);
          else if (ts.isSpreadAssignment(entry)) target(entry.expression);
        }
      }
      walk(source, item => {
        let aliases = [], initial;
        if (ts.isVariableDeclaration(item)) {
          initial = item.initializer;
          aliases = ts.isIdentifier(item.name) ? [item.name] : ts.isObjectBindingPattern(item.name) ?
            item.name.elements.filter(entry => ts.isIdentifier(entry.name) && !entry.dotDotDotToken && !entry.initializer).map(entry => entry.name) : [];
        }
        if (ts.isBinaryExpression(item) && item.operatorToken.kind === ts.SyntaxKind.EqualsToken && ts.isIdentifier(unwrap(item.left))) {
          aliases = [unwrap(item.left)]; initial = item.right;
        }
        if (initial && (reference(initial) || host(unwrap(initial)))) {
          for (const alias of aliases) {
            const symbol = receivers.checker.getSymbolAtLocation(alias);
            if (symbol && isWritten(source, receivers.checker, symbol, { properties: true, propertyOnly: true })) written = true;
          }
        }
        if (ts.isBinaryExpression(item) && item.operatorToken.kind >= ts.SyntaxKind.FirstAssignment && item.operatorToken.kind <= ts.SyntaxKind.LastAssignment) target(item.left);
        if ((ts.isPrefixUnaryExpression(item) || ts.isPostfixUnaryExpression(item)) &&
            [ts.SyntaxKind.PlusPlusToken, ts.SyntaxKind.MinusMinusToken].includes(item.operator)) target(item.operand);
        if ((ts.isForInStatement(item) || ts.isForOfStatement(item)) && !ts.isVariableDeclarationList(item.initializer)) target(item.initializer);
        if (ts.isDeleteExpression(item)) target(item.expression);
        const mutation = objectMutationTarget(item);
        if (mutation) { target(mutation); if (host(unwrap(mutation))) written = true; }
      });
      ambientWrites.set(name, written);
    }
    if (!ambientWrites.get(name)) return true;
    diagnostic(node, `#4f mutated ambient ${name} cannot establish the candidate binding`);
    return false;
  }

  function booleanLocator(node) {
    node = unwrap(node);
    if (!ts.isCallExpression(node) || node.questionDotToken || node.typeArguments || node.arguments.length !== 1 ||
        ts.isSpreadElement(node.arguments[0]) || !ts.isIdentifier(unwrap(node.expression)) || unwrap(node.expression).text !== 'Boolean') return null;
    if (!ambient(unwrap(node.expression), 'Boolean')) return false;
    const subject = unwrap(node.arguments[0]);
    if (ts.isAwaitExpression(subject)) return false;
    return proven(subject, 'locator');
  }

  function computedMatcher(access) {
    const key = unwrap(access.argumentExpression);
    const literal = literalString(key);
    if (literal !== null) return literal;
    if (ts.isIdentifier(key)) {
      const symbol = receivers.checker.getSymbolAtLocation(key);
      const declaration = symbol?.declarations?.length === 1 ? symbol.declarations[0] : null;
      if (declaration && ts.isVariableDeclaration(declaration) && declaration.initializer &&
          (declaration.parent.flags & ts.NodeFlags.Const) &&
          !isWritten(source, receivers.checker, symbol, { properties: true })) {
        const value = literalString(declaration.initializer);
        if (value !== null) return value;
      }
    }
    return null;
  }

  // Optional invocation and constant/immutable computed matcher syntax are
  // triage surfaces, never promoted to the direct confirmed proof below.
  function truthinessCandidate(node) {
    if (!ts.isCallExpression(node)) return;
    const callee = unwrap(node.expression), matcher = member(callee);
    if (!matcher) return;
    const computed = ts.isElementAccessExpression(callee);
    const name = computed ? computedMatcher(callee) : matcher.name;
    let base = unwrap(matcher.object), negated = false;
    const modifier = member(base);
    if (modifier?.name === 'not' && ts.isPropertyAccessExpression(base) && !base.questionDotToken) {
      negated = true; base = unwrap(modifier.object);
    }
    if (!ts.isCallExpression(base) || base.arguments.length < 1 || base.arguments.length > 2 ||
        base.arguments.some(ts.isSpreadElement)) return;
    const optional = Boolean(node.questionDotToken || callee.questionDotToken || base.questionDotToken);
    if (!computed && !optional) return;
    if (name !== null && (node.arguments.length ||
        !(negated ? ['toBeNull','toBeUndefined'] : ['toBeTruthy','toBeDefined']).includes(name))) return;
    if (!proven(base.expression, 'expect')) return;
    if (computed && name === null) {
      diagnostic(callee, '#4f dynamic or mutable computed matcher is outside this constant-key slice'); return;
    }
    const subject = unwrap(base.arguments[0]);
    // Awaited values are scalar reads, not Locator objects (#4c-4e).
    if (ts.isAwaitExpression(subject)) return;
    const value = receivers.expression(subject);
    if (!value.complete) { diagnostic(subject, value.reasons.join('; ')); return; }
    if (value.kind !== 'locator') {
      if (value.kind === 'locator-type' || value.kind === 'page-type' || ts.isCallExpression(subject)) {
        diagnostic(subject, '#4f optional/computed subject needs runtime Locator proof; wrappers/POMs remain unsupported');
      }
      return;
    }
    record('#4f', base, node.end, 'candidate');
  }

  function expectCall(node, { soft = false } = {}) {
    node = unwrap(node);
    if (!ts.isCallExpression(node) || node.questionDotToken ||
        node.arguments.length < 1 || node.arguments.length > 2 ||
        node.arguments.some(ts.isSpreadElement)) return null;
    let callee = unwrap(node.expression);
    if (callee.questionDotToken) return null;
    const access = dot(callee);
    if (soft && access?.name === 'soft') callee = access.object;
    // An outer matcher call is not a bare expect call. Do not ask scope to
    // resolve expect(subject).matcher as an imported function binding.
    let root = callee, parent;
    while ((parent = dot(root))) root = unwrap(parent.object);
    if (!ts.isIdentifier(root)) return null;
    // Unresolved helpers and registrations are not potential bare assertions
    // merely because they take one or two arguments. Preserve diagnostics for
    // an expect spelling or a source-linked expect alias, then let shared
    // scope decide whether that binding is actually the framework API.
    function expectReference(reference, seen = new Set()) {
      reference = unwrap(reference);
      const access = dot(reference);
      if (access) return access.name === 'expect';
      if (!ts.isIdentifier(reference)) return false;
      const symbol = receivers.checker.getSymbolAtLocation(reference);
      if (reference.text === 'expect') {
        const declaration = symbol?.declarations?.length === 1 ? symbol.declarations[0] : null;
        if (declaration && ts.isVariableDeclaration(declaration) && declaration.initializer &&
            (declaration.parent.flags & ts.NodeFlags.Const) &&
            !isWritten(source, receivers.checker, symbol, { properties: true })) {
          const initial = unwrap(declaration.initializer);
          // An explicitly local factory named expect is not an unresolved
          // official import. Keep unknown aliases and mutations diagnostic.
          if (ts.isCallExpression(initial) && !initial.questionDotToken &&
              ts.isIdentifier(unwrap(initial.expression)) &&
              unwrap(initial.expression).text !== 'expect') return false;
        }
        return true;
      }
      if (!symbol || seen.has(symbol)) return false;
      seen.add(symbol);
      const declarations = symbol.declarations;
      if (declarations?.length !== 1) return false;
      const declaration = declarations[0];
      if (ts.isImportSpecifier(declaration)) return (declaration.propertyName ?? declaration.name).text === 'expect';
      return ts.isVariableDeclaration(declaration) && declaration.initializer
        ? expectReference(declaration.initializer, seen) : false;
    }
    const identity = receivers.expression(callee);
    if (!identity.complete && !expectReference(callee)) return null;
    return proven(callee, 'expect') ? node : null;
  }

  function uncalled(node) {
    // A called matcher, assigned reference or ASI continuation is not an
    // uncalled matcher expression statement in the AST.
    if (ts.isCallExpression(node)) {
      const callee = dot(node.expression);
      if (callee) {
        const receiver = receivers.expression(callee.object);
        // A proven Page/Locator action is not a bare expect invocation. Keep
        // imported/namespace expect aliases and unresolved bindings on their
        // existing provenance path.
        if (receiver.complete && ['page', 'locator'].includes(receiver.kind)) return null;
      }
      return expectCall(node, { soft: true });
    }
    const matcher = dot(node);
    if (!matcher || !/^to[A-Z][A-Za-z0-9_$]*$/.test(matcher.name)) return null;
    let base = matcher.object, modifier;
    while ((modifier = dot(base)) && MODIFIERS.has(modifier.name)) base = modifier.object;
    return expectCall(base, { soft: true });
  }

  function literalDestructuredScalar(node) {
    node = unwrap(node);
    if (!ts.isIdentifier(node)) return false;
    const symbol = receivers.checker.getSymbolAtLocation(node);
    const binding = symbol?.declarations?.length === 1 ? symbol.declarations[0] : null;
    if (!binding || !ts.isBindingElement(binding) || binding.initializer || binding.dotDotDotToken ||
        !ts.isObjectBindingPattern(binding.parent) || isWritten(source, receivers.checker, symbol, { properties: true })) return false;
    const declaration = binding.parent.parent, key = binding.propertyName || binding.name;
    if (!(ts.isIdentifier(key) || ts.isStringLiteral(key)) || !ts.isVariableDeclaration(declaration) ||
        !(declaration.parent.flags & ts.NodeFlags.Const) || !declaration.initializer) return false;
    const object = unwrap(declaration.initializer);
    if (!ts.isObjectLiteralExpression(object) || object.properties.some(property =>
      !ts.isPropertyAssignment(property) || !(ts.isIdentifier(property.name) || ts.isStringLiteral(property.name)))) return false;
    const properties = object.properties.filter(property => property.name.text === key.text);
    if (properties.length !== 1) return false;
    const value = unwrap(properties[0].initializer);
    return ts.isNumericLiteral(value) || ts.isStringLiteral(value) || ts.isNoSubstitutionTemplateLiteral(value) ||
      [ts.SyntaxKind.TrueKeyword, ts.SyntaxKind.FalseKeyword, ts.SyntaxKind.NullKeyword].includes(value.kind);
  }
  function unknownFactoryQuery(node) {
    node = unwrap(node);
    if (!ts.isCallExpression(node) || node.questionDotToken || node.arguments.some(ts.isSpreadElement)) return false;
    const query = dot(node.expression);
    if (!query || !['getByRole', 'getByLabel', 'getByPlaceholder', 'getByTestId', 'getByText', 'getByTitle', 'getByAltText'].includes(query.name)) return false;
    let factory = unwrap(query.object);
    if (ts.isIdentifier(factory)) {
      const symbol = receivers.checker.getSymbolAtLocation(factory);
      const declaration = symbol?.declarations?.length === 1 ? symbol.declarations[0] : null;
      if (!declaration || !ts.isVariableDeclaration(declaration) || !declaration.initializer ||
          !(declaration.parent.flags & ts.NodeFlags.Const) || isWritten(source, receivers.checker, symbol, { properties: true })) return false;
      factory = unwrap(declaration.initializer);
    }
    if (!ts.isCallExpression(factory) || factory.questionDotToken || factory.arguments.some(ts.isSpreadElement)) return false;
    const callee = unwrap(factory.expression);
    // A known local/custom implementation must be analyzed on its own terms.
    return ts.isIdentifier(callee) && !receivers.checker.getSymbolAtLocation(callee);
  }

  function unknownFactoryIdentifier(node, call) {
    node = unwrap(node);
    if (!ts.isIdentifier(node) || !/(?:Locator|Button|Link|Input|Field|Checkbox|Radio|Select|Dialog|Modal|Toast|Banner|Heading|Label|Tab|Menu|Item|Row|Cell|Element)$/.test(node.text) || !insideTest(call)) return false;
    const symbol = receivers.checker.getSymbolAtLocation(node);
    const declaration = symbol?.declarations?.length === 1 ? symbol.declarations[0] : null;
    if (!declaration || !ts.isVariableDeclaration(declaration) || !declaration.initializer ||
        !(declaration.parent.flags & ts.NodeFlags.Const) || isWritten(source, receivers.checker, symbol, { properties: true })) return false;
    const factory = unwrap(declaration.initializer);
    if (!ts.isCallExpression(factory) || factory.questionDotToken || factory.arguments.some(ts.isSpreadElement)) return false;
    const callee = unwrap(factory.expression);
    return ts.isIdentifier(callee) && !receivers.checker.getSymbolAtLocation(callee);
  }

  function truthiness(node) {
    let base, chain = [];
    if (ts.isCallExpression(node) && !node.questionDotToken) {
      const matcher = dot(node.expression);
      if (!matcher) return null;
      base = matcher.object;
      chain = [matcher.name];
      let modifier;
      while ((modifier = dot(base))) { chain.unshift(modifier.name); base = modifier.object; }
      const name = chain.join('.');
      const noArguments = node.arguments.length === 0;
      if (!((noArguments && ['toBeTruthy', 'toBeDefined', 'not.toBeNull', 'not.toBeUndefined'].includes(name)) ||
          (name === 'not.to.equal' && node.arguments.length === 1 && unwrap(node.arguments[0]).kind === ts.SyntaxKind.NullKeyword))) return null;
    } else {
      base = node;
      let modifier;
      while ((modifier = dot(base))) { chain.unshift(modifier.name); base = modifier.object; }
      if (chain.join('.') !== 'not.to.be.null') return null;
    }
    const call = expectCall(base);
    if (!call) return null;
    const wrapped = booleanLocator(call.arguments[0]);
    if (wrapped !== null) return wrapped ? { call, disposition: 'candidate' } : null;
    if (literalDestructuredScalar(call.arguments[0])) return null;
    const before = diagnostics.length;
    if (proven(call.arguments[0], 'locator')) return { call, disposition: 'confirmed' };
    if (diagnostics.length > before) {
      const query = unknownFactoryQuery(call.arguments[0]);
      if (query || unknownFactoryIdentifier(call.arguments[0], call)) {
        return { call, disposition: 'candidate', evidence: { kind: query ? 'unresolved-query' : 'unresolved-locator',
          requirements: ['verify-runtime-binding', 'verify-required-test-outcome'] } };
      }
    }
    if (diagnostics.length === before) pomTruthinessGap(call);
    return null;
  }

  function testRegistration(call) {
    if (!ts.isCallExpression(call) || call.questionDotToken) return false;
    let root = unwrap(call.expression), access;
    while ((access = dot(root)) && ['only', 'skip', 'fixme', 'fail'].includes(access.name)) root = unwrap(access.object);
    const value = scope.expression(filename, root);
    return value.complete && value.kind === 'playwright-test';
  }
  function insideTest(node) {
    for (let parent = node.parent; parent; parent = parent.parent) {
      if ((ts.isArrowFunction(parent) || ts.isFunctionExpression(parent)) &&
          testRegistration(parent.parent) && parent.parent.arguments.at(-1) === parent) return true;
    }
    return false;
  }
  function pomTruthinessGap(call) {
    const subject = unwrap(call.arguments[0]), field = dot(subject);
    if (!field || !/(?:Button|Link|Input|Field|Checkbox|Radio|Select|Dialog|Modal|Toast|Banner|Heading|Label|Tab|Menu|Item|Row|Cell|Locator|Element)$/.test(field.name)) return;
    const root = unwrap(field.object);
    let declaration;
    if (ts.isIdentifier(root) && /Page$/.test(root.text) && insideTest(call)) {
      const symbol = receivers.checker.getSymbolAtLocation(root);
      const variable = symbol?.declarations?.length === 1 ? symbol.declarations[0] : null;
      if (!variable || !ts.isVariableDeclaration(variable) || !variable.initializer ||
          !(variable.parent.flags & ts.NodeFlags.Const)) return;
      const constructor = unwrap(variable.initializer);
      if (!ts.isNewExpression(constructor) || !ts.isIdentifier(constructor.expression) ||
          !/Page$/.test(constructor.expression.text)) return;
      const definitions = receivers.checker.getSymbolAtLocation(constructor.expression)?.declarations;
      if (definitions?.length) {
        if (definitions.length !== 1 || !(ts.isClassDeclaration(definitions[0]) || ts.isImportSpecifier(definitions[0]))) return;
        if (ts.isClassDeclaration(definitions[0])) declaration = definitions[0];
      }
    } else if (root.kind === ts.SyntaxKind.ThisKeyword) {
      for (let parent = subject.parent; parent; parent = parent.parent) {
        if (ts.isFunctionDeclaration(parent) || ts.isFunctionExpression(parent)) return;
        if (ts.isClassDeclaration(parent)) { declaration = parent; break; }
      }
      if (!declaration?.name || !/Page$/.test(declaration.name.text)) return;
      let hasTest = false;
      walk(source, node => { if (testRegistration(node)) hasTest = true; });
      if (!hasTest) return;
    } else return;
    // A known scalar/object field is ordinary state, even when its spelling
    // resembles a POM handle. Naming alone never establishes a Locator.
    const property = declaration?.members.find(item => item.name &&
      (ts.isIdentifier(item.name) || ts.isStringLiteral(item.name)) && item.name.text === field.name);
    if (property) {
      if (!ts.isPropertyDeclaration(property)) return;
      const initial = property.initializer && unwrap(property.initializer);
      if (initial && (ts.isLiteralExpression(initial) || ts.isObjectLiteralExpression(initial) ||
          ts.isArrayLiteralExpression(initial) || [ts.SyntaxKind.TrueKeyword, ts.SyntaxKind.FalseKeyword,
            ts.SyntaxKind.NullKeyword].includes(initial.kind))) return;
    }
    diagnostic(subject, '#4f POM member truthiness requires unsupported runtime Locator provenance');
  }

  function discarded(node, awaited) {
    if (!ts.isCallExpression(node) || node.questionDotToken) return null;
    const access = dot(node.expression);
    if (!access) return null;
    if ((access.name === 'locator' || /^getBy[A-Za-z]+$/.test(access.name)) &&
        proven(access.object, 'page') && proven(node, 'locator')) return '#8a';
    // Direct Playwright annotations support a review candidate, never the
    // stronger runtime receiver proof used for confirmed #4f findings.
    if (awaited && BOOLEAN_STATE.has(access.name) && proven(access.object, ['page', 'locator', 'page-type', 'locator-type'])) return '#8b';
    return null;
  }

  function matcherCandidate(node) {
    if (!ts.isCallExpression(node) || node.questionDotToken) return;
    const matcher = dot(node.expression);
    if (!matcher || !['toBeGreaterThanOrEqual', 'toBeAttached'].includes(matcher.name)) return;
    let base = matcher.object, modifier;
    const modifiers = [];
    while ((modifier = dot(base)) && MODIFIERS.has(modifier.name)) {
      modifiers.push(modifier.name);
      base = modifier.object;
    }
    if (matcher.name === 'toBeGreaterThanOrEqual') {
      // The legacy shape is a candidate even when the subject can be negative
      // or a modifier changes its meaning. Nonnegativity needs semantic review.
      if (node.arguments.length !== 1 || !ts.isNumericLiteral(node.arguments[0]) ||
          node.arguments[0].getText(source) !== '0') return;
    } else if (modifiers.includes('not')) return;
    if (!expectCall(base, { soft: true })) return;
    record(matcher.name === 'toBeAttached' ? '#4b' : '#4a', unwrap(node.expression).name,
      node.end, 'candidate', matcher.name === 'toBeAttached' ? 'P1' : 'P0');
  }

  // An ambient, unmodified Chai expect plus proven Cypress context supplies a
  // review candidate. It does not establish a confirmed runtime defect.
  function cypressJqueryCandidate(node) {
    let base = unwrap(node), chain = [], access;
    if (ts.isCallExpression(base)) {
      if (base.questionDotToken || base.arguments.length) return;
      base = unwrap(base.expression);
    }
    while ((access = dot(base))) {
      chain.unshift(access.name); base = unwrap(access.object);
    }
    if (!['to.exist', 'to.be.ok', 'toBeTruthy'].includes(chain.join('.')) ||
        !ts.isCallExpression(base) || base.questionDotToken || base.arguments.length !== 1) return;
    const expect = unwrap(base.expression);
    if (!ts.isIdentifier(expect) || expect.text !== 'expect') return;
    const subject = unwrap(base.arguments[0]);
    if (!ts.isCallExpression(subject) || subject.questionDotToken || subject.arguments.length !== 1 ||
        subject.typeArguments || ts.isSpreadElement(subject.arguments[0])) return;
    const jquery = dot(unwrap(subject.expression));
    if (jquery?.name !== '$') return;
    const root = unwrap(jquery.object);
    if (!ts.isIdentifier(root) || root.text !== 'Cypress') return;
    if (!ambient(expect, 'expect')) return;
    const proof = scope.cypressGlobal(filename, root);
    if (!proof.complete) { diagnostic(root, proof.reasons.join('; ')); return; }
    if (proof.kind === 'cypress-runtime') {
      record('#4f', base, node.end, 'candidate');
    }
  }

  function record(patternId, call, end, disposition = 'confirmed', severity = 'P0') {
    const start = call.getStart(source), position = source.getLineAndCharacterOfPosition(start);
    findings.push({ patternId, severity, disposition, origin: 'ast',
      file: filename, line: position.line + 1, column: position.character + 1, start, end });
  }

  walk(source, node => {
    // Called matcher candidates also occur inside returns, callback expressions
    // and template substitutions; the discarded-expression rules below do not.
    matcherCandidate(node);
    if (!ts.isExpressionStatement(node)) return;
    let expression = unwrap(node.expression);
    const awaited = ts.isAwaitExpression(expression);
    if (awaited) expression = unwrap(expression.expression);
    cypressJqueryCandidate(expression);
    const unused = discarded(expression, awaited);
    if (unused) { record(unused, node.expression, expression.end, 'candidate'); return; }
    const missing = uncalled(expression);
    if (missing) { record('#8c', missing, expression.end); return; }
    const vacuous = truthiness(expression);
    if (vacuous) {
      record('#4f', vacuous.call, expression.end, vacuous.disposition);
      if (vacuous.evidence) findings.at(-1).evidence = vacuous.evidence;
    }
    else truthinessCandidate(expression);
  });
  return { findings, diagnostics };
}
