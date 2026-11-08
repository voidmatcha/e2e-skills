// SPDX-License-Identifier: Apache-2.0
// Bounded raw #8a/#8b/#8c and #4a/#4b/#4f detectors.
// Suppression, semantic adjudication and dedupe belong to callers.
import { createReceivers, UNPROVEN_MEMBER } from './receivers.mjs';
import { unwrap, walk, member, literalString, isWritten, objectMutationTarget, ts } from './source.mjs';
import { demoteToReviewHint } from './review-hints.mjs';

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
    // A value only declared Locator (a typed parameter, or a page-object
    // member built from one) is a review candidate, never a silent pass.
    if (diagnostics.length === before && receivers.expression(call.arguments[0]).kind === 'locator-type')
      return { call, disposition: 'candidate', evidence: { kind: 'unresolved-locator',
        requirements: ['verify-runtime-binding', 'verify-required-test-outcome'] } };
    if (diagnostics.length > before) {
      const query = unknownFactoryQuery(call.arguments[0]);
      if (query || unknownFactoryIdentifier(call.arguments[0], call)) {
        return { call, disposition: 'candidate', evidence: { kind: query ? 'unresolved-query' : 'unresolved-locator',
          requirements: ['verify-runtime-binding', 'verify-required-test-outcome'] } };
      }
      // An unproven page-object member keeps the POM gap message, which
      // links the retained #4f review candidate.
      if (diagnostics.length === before + 1 && UNPROVEN_MEMBER.has(diagnostics.at(-1).message) && pomTruthinessGap(call, false)) {
        diagnostics.pop();
        pomTruthinessGap(call);
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
  // Records the POM gap diagnostic for a matching shape; with emit false it
  // only reports whether the shape matches.
  function pomTruthinessGap(call, emit = true) {
    const subject = unwrap(call.arguments[0]), field = dot(subject);
    if (!field || !/(?:Button|Link|Input|Field|Checkbox|Radio|Select|Dialog|Modal|Toast|Banner|Heading|Label|Tab|Menu|Item|Row|Cell|Locator|Element)$/.test(field.name)) return false;
    const root = unwrap(field.object);
    let declaration;
    if (ts.isIdentifier(root) && /Page$/.test(root.text) && insideTest(call)) {
      const symbol = receivers.checker.getSymbolAtLocation(root);
      const variable = symbol?.declarations?.length === 1 ? symbol.declarations[0] : null;
      if (!variable || !ts.isVariableDeclaration(variable) || !variable.initializer ||
          !(variable.parent.flags & ts.NodeFlags.Const)) return false;
      const constructor = unwrap(variable.initializer);
      if (!ts.isNewExpression(constructor) || !ts.isIdentifier(constructor.expression) ||
          !/Page$/.test(constructor.expression.text)) return false;
      const definitions = receivers.checker.getSymbolAtLocation(constructor.expression)?.declarations;
      if (definitions?.length) {
        if (definitions.length !== 1 || !(ts.isClassDeclaration(definitions[0]) || ts.isImportSpecifier(definitions[0]))) return false;
        if (ts.isClassDeclaration(definitions[0])) declaration = definitions[0];
      }
    } else if (root.kind === ts.SyntaxKind.ThisKeyword) {
      for (let parent = subject.parent; parent; parent = parent.parent) {
        if (ts.isFunctionDeclaration(parent) || ts.isFunctionExpression(parent)) return false;
        if (ts.isClassDeclaration(parent)) { declaration = parent; break; }
      }
      if (!declaration?.name || !/Page$/.test(declaration.name.text)) return false;
      let hasTest = false;
      walk(source, node => { if (testRegistration(node)) hasTest = true; });
      if (!hasTest) return false;
    } else return false;
    // A known scalar/object field is ordinary state, even when its spelling
    // resembles a POM handle. Naming alone never establishes a Locator.
    const property = declaration?.members.find(item => item.name &&
      (ts.isIdentifier(item.name) || ts.isStringLiteral(item.name)) && item.name.text === field.name);
    if (property) {
      if (!ts.isPropertyDeclaration(property)) return false;
      const initial = property.initializer && unwrap(property.initializer);
      if (initial && (ts.isLiteralExpression(initial) || ts.isObjectLiteralExpression(initial) ||
          ts.isArrayLiteralExpression(initial) || [ts.SyntaxKind.TrueKeyword, ts.SyntaxKind.FalseKeyword,
            ts.SyntaxKind.NullKeyword].includes(initial.kind))) return false;
    }
    if (emit) diagnostic(subject, '#4f POM member truthiness requires unsupported runtime Locator provenance');
    return true;
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

  // A value that can be nullish by its own shape: an optional chain, an
  // index or property read, or a lookup method that returns undefined/null
  // on a miss. Anything else (a count, a length, a literal, an unknown call)
  // is not proven nullable, so its fallback keeps the #4a candidate.
  const NULLABLE_LOOKUPS = new Set(['get', 'find', 'findLast', 'at', 'match', 'exec', 'getAttribute', 'getItem', 'textContent', 'pop', 'shift']);
  function maybeNullish(node, depth = 0) {
    node = unwrap(node);
    if (depth > 8) return false;
    if (ts.isIdentifier(node)) {
      const symbol = receivers.checker.getSymbolAtLocation(node);
      const declaration = symbol?.declarations?.length === 1 ? symbol.declarations[0] : null;
      return Boolean(declaration && ts.isVariableDeclaration(declaration) && ts.isIdentifier(declaration.name) &&
        declaration.initializer && declaration.parent.flags & ts.NodeFlags.Const &&
        !isWritten(source, receivers.checker, symbol) && maybeNullish(declaration.initializer, depth + 1));
    }
    if (ts.isAwaitExpression(node)) return maybeNullish(node.expression, depth + 1);
    if (ts.isOptionalChain(node) || ts.isElementAccessExpression(node)) return true;
    if (ts.isCallExpression(node)) {
      const access = member(node.expression);
      return Boolean(access && NULLABLE_LOOKUPS.has(access.name));
    }
    // A missing property reads undefined; a length or size never does.
    if (ts.isPropertyAccessExpression(node)) return !['length', 'size'].includes(node.name.text);
    return false;
  }
  function searchResult(node, depth = 0) {
    node = unwrap(node);
    if (depth > 8) return false;
    if (ts.isIdentifier(node)) {
      const symbol = receivers.checker.getSymbolAtLocation(node);
      const declaration = symbol?.declarations?.length === 1 ? symbol.declarations[0] : null;
      return Boolean(declaration && ts.isVariableDeclaration(declaration) && ts.isIdentifier(declaration.name) &&
        declaration.initializer && declaration.parent.flags & ts.NodeFlags.Const &&
        !isWritten(source, receivers.checker, symbol) && searchResult(declaration.initializer, depth + 1));
    }
    const SEARCH = ['indexOf', 'lastIndexOf', 'findIndex', 'findLastIndex', 'search'];
    // `x ?? -1`: the negative fallback itself fails `>= 0`, but only when
    // `x` can be nullish. A fallback that cannot be reached (a Locator
    // count, a length, a literal) leaves the assertion always-pass.
    if (ts.isBinaryExpression(node) && node.operatorToken.kind === ts.SyntaxKind.QuestionQuestionToken) {
      const right = unwrap(node.right);
      return ts.isPrefixUnaryExpression(right) && right.operator === ts.SyntaxKind.MinusToken &&
        ts.isNumericLiteral(unwrap(right.operand)) && Number(unwrap(right.operand).text) > 0 &&
        (maybeNullish(node.left) || searchResult(node.left, depth + 1));
    }
    // `await locator.evaluateAll(items => items.findIndex(...))`: the browser
    // callback searches its Element array, which yields -1 on no match. The
    // same holds for `evaluate(() => [...nodes].findIndex(...))` on an array
    // literal or `Array.from(...)` built inside the browser callback.
    if (ts.isAwaitExpression(node)) {
      const call = unwrap(node.expression), access = ts.isCallExpression(call) && member(call.expression);
      const callback = ['evaluate', 'evaluateAll'].includes(access?.name) && call.arguments.length >= 1 && unwrap(call.arguments[0]);
      if (!callback || !(ts.isArrowFunction(callback) || ts.isFunctionExpression(callback))) return false;
      const items = access.name === 'evaluateAll' && callback.parameters[0] && ts.isIdentifier(callback.parameters[0].name)
        ? callback.parameters[0].name.text : null;
      const owner = receivers.expression(access.object);
      if (!owner.complete || !['page', 'locator'].includes(owner.kind)) return false;
      const values = [];
      if (!ts.isBlock(callback.body)) values.push(callback.body);
      else {
        const last = callback.body.statements.at(-1);
        if (!last || !ts.isReturnStatement(last)) return false;
        let bare = false;
        (function returns(item) {
          if (item !== callback.body && ts.isFunctionLike(item)) return;
          if (ts.isReturnStatement(item)) { if (item.expression) values.push(item.expression); else bare = true; }
          ts.forEachChild(item, returns);
        })(callback.body);
        if (bare) return false;
      }
      return values.every(value => {
        value = unwrap(value);
        const search = ts.isCallExpression(value) && member(value.expression);
        const receiver = search && unwrap(search.object);
        return Boolean(search && SEARCH.includes(search.name) && receiver &&
          (items !== null && ts.isIdentifier(receiver) && receiver.text === items || browserArray(receiver)));
      });
    }
    if (!ts.isCallExpression(node)) return false;
    const access = member(node.expression);
    return Boolean(access && SEARCH.includes(access.name) && (receivers.data(access.object) || searchable(access.object)));
  }
  // Inside a browser callback: an array literal, or Array.from(...) on the
  // unshadowed global, is a real Array whose search methods yield -1.
  function browserArray(node) {
    node = unwrap(node);
    if (ts.isArrayLiteralExpression(node)) return true;
    const access = ts.isCallExpression(node) && !node.questionDotToken && member(node.expression);
    const root = access && unwrap(access.object);
    return Boolean(access?.name === 'from' && ts.isIdentifier(root) && root.text === 'Array' &&
      !receivers.checker.getSymbolAtLocation(root)?.declarations?.length);
  }
  // A value that is a built-in Array or string (or throws when read): text
  // and serialized evaluate results from a proven Page/Locator, and Array or
  // string methods applied to such a value. Its search methods are the
  // built-ins, which yield -1 on no match.
  const TEXT_READS = new Set(['allTextContents', 'allInnerTexts', 'textContent', 'innerText', 'innerHTML', 'inputValue', 'getAttribute']);
  const SERIALIZED_READS = new Set(['evaluate', 'evaluateAll', '$eval', '$$eval']);
  const DERIVED = new Set(['map', 'filter', 'slice', 'concat', 'flat', 'flatMap', 'sort', 'reverse', 'toSorted', 'toReversed',
    'split', 'trim', 'trimStart', 'trimEnd', 'toLowerCase', 'toUpperCase', 'replace', 'replaceAll', 'substring']);
  // The binding never escapes: every use reads one of its members, so no
  // other code can redefine its search methods.
  function memberUsesOnly(symbol, name) {
    let only = true;
    walk(source, node => {
      if (!only || !ts.isIdentifier(node) || node === name || receivers.checker.getSymbolAtLocation(node) !== symbol) return;
      let use = node;
      while (ts.isParenthesizedExpression(use.parent) || ts.isNonNullExpression(use.parent)) use = use.parent;
      if (!(ts.isPropertyAccessExpression(use.parent) && use.parent.expression === use)) only = false;
    });
    return only;
  }
  function searchable(node, depth = 0) {
    node = unwrap(node);
    if (depth > 8) return false;
    if (ts.isIdentifier(node)) {
      const symbol = receivers.checker.getSymbolAtLocation(node);
      const declaration = symbol?.declarations?.length === 1 ? symbol.declarations[0] : null;
      return Boolean(declaration && ts.isVariableDeclaration(declaration) && ts.isIdentifier(declaration.name) &&
        declaration.initializer && declaration.parent.flags & ts.NodeFlags.Const &&
        !isWritten(source, receivers.checker, symbol, { properties: true }) && memberUsesOnly(symbol, declaration.name) &&
        searchable(declaration.initializer, depth + 1));
    }
    if (ts.isArrayLiteralExpression(node)) return true;
    if (ts.isAwaitExpression(node)) {
      const call = unwrap(node.expression);
      const access = ts.isCallExpression(call) && !call.questionDotToken && dot(call.expression);
      if (!access || !(TEXT_READS.has(access.name) || SERIALIZED_READS.has(access.name))) return false;
      const owner = receivers.expression(access.object);
      return owner.complete && (owner.kind === 'locator' || owner.kind === 'page' && access.name !== 'allTextContents' && access.name !== 'allInnerTexts');
    }
    const access = ts.isCallExpression(node) && !node.questionDotToken && dot(node.expression);
    return Boolean(access && DERIVED.has(access.name) && searchable(access.object, depth + 1));
  }
  // `box.x` / `box.y` of `const box = await locator.boundingBox()`, or of
  // `(await locator.boundingBox())!` directly: Playwright reports page
  // coordinates, which are negative for an element scrolled or positioned
  // off-screen, so `>= 0` can fail and is not a #4a invariant. The receiver
  // must be a proven Locator or a parameter annotated with Playwright's
  // Locator type; width and height are never negative and stay candidates.
  function boundingBoxCall(node) {
    const awaited = unwrap(node);
    const call = ts.isAwaitExpression(awaited) && unwrap(awaited.expression);
    const access = call && ts.isCallExpression(call) && !call.questionDotToken && !call.arguments.length && dot(call.expression);
    if (!access || access.name !== 'boundingBox') return false;
    const owner = receivers.expression(access.object);
    return owner.complete && ['locator', 'locator-type'].includes(owner.kind);
  }
  function boxCoordinate(node) {
    node = unwrap(node);
    if (!ts.isPropertyAccessExpression(node) || !['x', 'y'].includes(node.name.text)) return false;
    const box = unwrap(node.expression);
    if (ts.isAwaitExpression(box)) return boundingBoxCall(box);
    if (!ts.isIdentifier(box)) return false;
    const symbol = receivers.checker.getSymbolAtLocation(box);
    const declaration = symbol?.declarations?.length === 1 ? symbol.declarations[0] : null;
    if (!declaration || !ts.isVariableDeclaration(declaration) || !ts.isIdentifier(declaration.name) || !declaration.initializer ||
        !(declaration.parent.flags & ts.NodeFlags.Const) || isWritten(source, receivers.checker, symbol, { properties: true })) return false;
    return boundingBoxCall(declaration.initializer);
  }
  // A positional coordinate (`.x`, `.y`, `.top`, `.left`, `.right`,
  // `.bottom` of any value) or a difference `a - b`: both can be negative,
  // so `>= 0` is a real check, not invariant math. Review hint, not P0.
  // Width and height are never negative and stay candidates.
  const POSITIONS = new Set(['x', 'y', 'top', 'left', 'right', 'bottom']);
  function signedSubject(node) {
    node = unwrap(node);
    if (ts.isPropertyAccessExpression(node)) return POSITIONS.has(node.name.text);
    return ts.isBinaryExpression(node) && node.operatorToken.kind === ts.SyntaxKind.MinusToken;
  }
  // expect.poll(fn).toBeGreaterThanOrEqual(0) passes on its first sample
  // when the polled value cannot be negative, so it never waits.
  function pollCall(node) {
    node = unwrap(node);
    if (!ts.isCallExpression(node) || node.questionDotToken || !node.arguments.length || node.arguments.length > 2) return false;
    const access = member(node.expression);
    return Boolean(access?.name === 'poll' && ts.isIdentifier(unwrap(access.object)) && proven(access.object, 'expect'));
  }
  // `await <proven Locator>.count()` directly, or through a same-function,
  // never-written const bound to exactly that awaited call. A count is a
  // nonnegative integer, so `>= 0` and `> -1` cannot fail.
  function locatorCount(node) {
    node = unwrap(node);
    if (ts.isIdentifier(node)) {
      const symbol = receivers.checker.getSymbolAtLocation(node);
      const declaration = symbol?.declarations?.length === 1 ? symbol.declarations[0] : null;
      if (!declaration || !ts.isVariableDeclaration(declaration) || !ts.isIdentifier(declaration.name) ||
          !declaration.initializer || !(declaration.parent.flags & ts.NodeFlags.Const) ||
          isWritten(source, receivers.checker, symbol, { properties: true }) ||
          ts.getContainingFunction(declaration) !== ts.getContainingFunction(node)) return false;
      node = unwrap(declaration.initializer);
    }
    if (!ts.isAwaitExpression(node)) return false;
    const call = unwrap(node.expression);
    const access = ts.isCallExpression(call) && !call.questionDotToken && !call.arguments.length && dot(call.expression);
    if (!access || access.name !== 'count') return false;
    const owner = receivers.expression(access.object);
    return owner.complete && owner.kind === 'locator';
  }
  function negativeOne(node) {
    node = unwrap(node);
    return ts.isPrefixUnaryExpression(node) && node.operator === ts.SyntaxKind.MinusToken &&
      ts.isNumericLiteral(node.operand) && node.operand.getText(source) === '1';
  }
  // `expect(x || true).toBeTruthy()`: a `||` with a truthy literal operand is
  // truthy whatever `x` is. `x ?? <defined literal>` is never undefined.
  function truthyLiteral(node) {
    node = unwrap(node);
    if (node.kind === ts.SyntaxKind.TrueKeyword) return true;
    if (ts.isNumericLiteral(node)) { const value = Number(node.text); return Number.isFinite(value) && value !== 0; }
    return (ts.isStringLiteral(node) || ts.isNoSubstitutionTemplateLiteral(node)) && node.text.length > 0;
  }
  // A value that is always a boolean: a boolean literal, a negation, a
  // comparison, an awaited state read on a proven Page/Locator, or a
  // never-written same-function const bound to one of these.
  const STATE_BOOLEANS = new Set([...BOOLEAN_STATE]);
  function booleanValue(node, depth = 0) {
    node = unwrap(node);
    if (depth > 8) return false;
    if ([ts.SyntaxKind.TrueKeyword, ts.SyntaxKind.FalseKeyword].includes(node.kind)) return true;
    if (ts.isPrefixUnaryExpression(node) && node.operator === ts.SyntaxKind.ExclamationToken) return true;
    if (ts.isBinaryExpression(node) && [ts.SyntaxKind.EqualsEqualsEqualsToken, ts.SyntaxKind.ExclamationEqualsEqualsToken,
      ts.SyntaxKind.EqualsEqualsToken, ts.SyntaxKind.ExclamationEqualsToken, ts.SyntaxKind.LessThanToken, ts.SyntaxKind.LessThanEqualsToken,
      ts.SyntaxKind.GreaterThanToken, ts.SyntaxKind.GreaterThanEqualsToken].includes(node.operatorToken.kind)) return true;
    if (ts.isIdentifier(node)) {
      const symbol = receivers.checker.getSymbolAtLocation(node);
      const declaration = symbol?.declarations?.length === 1 ? symbol.declarations[0] : null;
      return Boolean(declaration && ts.isVariableDeclaration(declaration) && ts.isIdentifier(declaration.name) && declaration.initializer &&
        declaration.parent.flags & ts.NodeFlags.Const && !isWritten(source, receivers.checker, symbol) &&
        ts.getContainingFunction(declaration) === ts.getContainingFunction(node) && booleanValue(declaration.initializer, depth + 1));
    }
    if (ts.isBinaryExpression(node) && [ts.SyntaxKind.BarBarToken, ts.SyntaxKind.AmpersandAmpersandToken].includes(node.operatorToken.kind))
      return booleanValue(node.left, depth + 1) && booleanValue(node.right, depth + 1);
    if (!ts.isAwaitExpression(node)) return false;
    let call = unwrap(node.expression);
    // `read().catch(() => false)`: the fallback is a boolean literal too.
    const fallback = ts.isCallExpression(call) && !call.questionDotToken && dot(call.expression)?.name === 'catch' &&
      call.arguments.length === 1 && unwrap(call.arguments[0]);
    if (fallback && ts.isArrowFunction(fallback) && !ts.isBlock(fallback.body) &&
        [ts.SyntaxKind.TrueKeyword, ts.SyntaxKind.FalseKeyword].includes(unwrap(fallback.body).kind)) call = unwrap(dot(call.expression).object);
    const access = ts.isCallExpression(call) && !call.questionDotToken && dot(call.expression);
    if (!access || !STATE_BOOLEANS.has(access.name)) return false;
    const owner = receivers.expression(access.object);
    return owner.complete && ['page', 'locator'].includes(owner.kind);
  }
  function alwaysTruthyAssertion(node) {
    if (!ts.isCallExpression(node) || node.questionDotToken) return;
    const matcher = dot(node.expression);
    if (!matcher) return;
    const name = matcher.name;
    if (!((['toBeTruthy', 'toBeDefined'].includes(name) && !node.arguments.length) ||
        (name === 'toBe' && node.arguments.length === 1 && unwrap(node.arguments[0]).kind === ts.SyntaxKind.TrueKeyword))) return;
    const base = unwrap(matcher.object);
    // Any modifier (.not, .resolves, .rejects) changes the meaning.
    if (!ts.isCallExpression(base) || base.questionDotToken || base.arguments.length < 1 || base.arguments.length > 2) return;
    const subject = unwrap(base.arguments[0]);
    if (!ts.isBinaryExpression(subject)) return;
    const operator = subject.operatorToken.kind;
    // `||` returns an operand, not a boolean: `'yes' || true` is 'yes', which
    // fails toBe(true). Truthiness matchers pass on any truthy literal side;
    // toBe(true) only when the result is provably the boolean true, that is
    // `true || x`, or `x || true` with x provably boolean.
    const isTrue = node => unwrap(node).kind === ts.SyntaxKind.TrueKeyword;
    const vacuous = operator === ts.SyntaxKind.BarBarToken
      ? name === 'toBe' ? isTrue(subject.left) || isTrue(subject.right) && booleanValue(subject.left)
        : truthyLiteral(subject.right) || truthyLiteral(subject.left)
      : operator === ts.SyntaxKind.QuestionQuestionToken && name === 'toBeDefined' && truthyLiteral(subject.right);
    // `x || true` under toBe(true) with x not provably boolean passes for
    // every boolean or falsy x: a review candidate, not a confirmed defect.
    const likely = !vacuous && operator === ts.SyntaxKind.BarBarToken && name === 'toBe' && isTrue(subject.right);
    if (!(vacuous || likely) || !expectCall(base, { soft: true })) return;
    record('#4a', base, node.end, vacuous ? 'confirmed' : 'candidate');
  }
  function matcherCandidate(node) {
    if (!ts.isCallExpression(node) || node.questionDotToken) return;
    const matcher = dot(node.expression);
    if (matcher?.name === 'toBeGreaterThan' && node.arguments.length === 1 && negativeOne(node.arguments[0]) &&
        ts.isCallExpression(unwrap(matcher.object))) {
      const call = expectCall(matcher.object, { soft: true });
      if (call && locatorCount(call.arguments[0])) record('#4a', unwrap(node.expression).name, node.end, 'confirmed');
      return;
    }
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
    const call = expectCall(base, { soft: true });
    if (!call && !(matcher.name === 'toBeGreaterThanOrEqual' && pollCall(base))) return;
    // A built-in search result on plain data is -1 when nothing matches, so
    // `>= 0` can fail and is not a #4a invariant.
    if (call && matcher.name === 'toBeGreaterThanOrEqual' && !modifiers.length &&
        (searchResult(call.arguments[0]) || boxCoordinate(call.arguments[0]))) return;
    const confirmed = call && matcher.name === 'toBeGreaterThanOrEqual' && !modifiers.length && locatorCount(call.arguments[0]);
    record(matcher.name === 'toBeAttached' ? '#4b' : '#4a', unwrap(node.expression).name,
      node.end, confirmed ? 'confirmed' : 'candidate', matcher.name === 'toBeAttached' ? 'P1' : 'P0');
    if (!confirmed && call && matcher.name === 'toBeGreaterThanOrEqual' && !modifiers.length && signedSubject(call.arguments[0]))
      demoteToReviewHint(findings.at(-1), 'position-not-invariant');
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
    alwaysTruthyAssertion(node);
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
