// SPDX-License-Identifier: Apache-2.0
// Bounded #3 inline .catch callbacks and direct assertion try statements.
// These are review candidates; broader propagation analysis remains diagnostic.
import { createReceivers } from './receivers.mjs';
import { isWritten, member, objectMutationTarget, unwrap, walk, ts } from './source.mjs';
import { demoteToReviewHint } from './review-hints.mjs';

export function catchHandlers(bytes, filename, { scope, waitTimeouts } = {}) {
  const receivers = createReceivers(bytes, filename, { scope });
  const { source, diagnostics: parseErrors } = receivers;
  const findings = [], diagnostics = [...parseErrors];
  if (diagnostics.length) return { findings, diagnostics };
  if (!scope) return { findings, diagnostics: [{ message: 'pinned scope is required for catch candidate file membership' }] };
  let relevant = false;
  walk(source, node => {
    if (ts.isTryStatement(node)) relevant = true;
    if (!ts.isCallExpression(node)) return;
    const access = member(unwrap(node.expression));
    if (access?.name === 'catch' || access?.name === 'allSettled' &&
        ts.isIdentifier(unwrap(access.object)) && unwrap(access.object).text === 'Promise') relevant = true;
  });
  if (!relevant) return { findings, diagnostics };
  const framework = scope.framework(filename);
  if (!framework.complete) {
    uncertainFixtureCatches();
    return { findings, diagnostics: [{ message: framework.reasons.join('; ') }] };
  }
  const runtimeFramework = framework.frameworks.some(name => name === 'playwright' || name === 'cypress');
  function diagnostic(node, message) {
    const start = node.getStart(source);
    diagnostics.push({ start, length: node.end - start, message });
  }
  const supported = new Set();
  function proven(node, expected, receiver = false) {
    const value = receiver ? receivers.expression(node) : scope.expression(filename, node);
    if (!value.complete) diagnostic(node, value.reasons.join('; '));
    return value.complete && value.kind === expected;
  }
  function dot(node) {
    node = unwrap(node);
    return ts.isPropertyAccessExpression(node) && !node.questionDotToken ? node : null;
  }
  function plainBinding(node) {
    node = unwrap(node);
    const access = dot(node);
    return ts.isIdentifier(node) || (access && plainBinding(access.expression));
  }
  // Deliberately no helper traversal or inferred control flow: the try is a
  // direct statement in a proven test callback, containing an awaited known
  // hard Locator assertion. Custom matchers, soft and unawaited calls stay gaps.
  function registeredTest(callback, requireAsync = true) {
    if (!callback || !(ts.isArrowFunction(callback) || ts.isFunctionExpression(callback)) ||
        callback.asteriskToken || requireAsync && !callback.modifiers?.some(m => m.kind === ts.SyntaxKind.AsyncKeyword) ||
        !ts.isCallExpression(callback.parent) || callback.parent.questionDotToken ||
        callback.parent.arguments.length !== 2 || callback.parent.arguments[1] !== callback ||
        !plainBinding(callback.parent.expression) ||
        !proven(callback.parent.expression, 'playwright-test')) return false;
    return true;
  }
  function directTestStatement(statement) {
    const callback = statement.parent?.parent;
    return statement.parent === callback?.body && registeredTest(callback);
  }
  function directAssertion(statement) {
    if (!directTestStatement(statement)) return false;
    if (statement.tryBlock.statements.length !== 1) return false;
    const line = statement.tryBlock.statements[0];
    if (!ts.isExpressionStatement(line) || !ts.isAwaitExpression(unwrap(line.expression))) return false;
    return hardLocatorAssertion(unwrap(unwrap(line.expression).expression));
  }
  function literalOption(node) {
    node = unwrap(node);
    return ts.isStringLiteral(node) || ts.isNumericLiteral(node) ||
      [ts.SyntaxKind.TrueKeyword, ts.SyntaxKind.FalseKeyword].includes(node.kind);
  }
  function assertionOptions(node, names) {
    node = unwrap(node);
    return ts.isObjectLiteralExpression(node) && node.properties.every(property =>
      ts.isPropertyAssignment(property) && (ts.isIdentifier(property.name) || ts.isStringLiteral(property.name)) &&
      names.includes(property.name.text) && literalOption(property.initializer));
  }
  function matcherShape(call) {
    call = unwrap(call);
    if (!ts.isCallExpression(call) || call.questionDotToken || call.typeArguments?.length) return null;
    const matcher = dot(call.expression);
    if (!matcher) return null;
    const args = call.arguments, name = matcher.name.text;
    const text = node => ts.isStringLiteral(unwrap(node)) || ts.isNoSubstitutionTemplateLiteral(unwrap(node)) ||
      ts.isRegularExpressionLiteral(unwrap(node));
    if (name === 'toBeVisible' && (args.length === 0 || args.length === 1 &&
        assertionOptions(args[0], ['timeout', 'visible']))) return matcher;
    if (name === 'toHaveText' && args.length >= 1 && args.length <= 2 && text(args[0]) &&
        (args.length === 1 || assertionOptions(args[1], ['timeout', 'ignoreCase', 'useInnerText']))) return matcher;
    if (name === 'toHaveAttribute' && args.length >= 2 && args.length <= 3 && ts.isStringLiteral(unwrap(args[0])) &&
        text(args[1]) && (args.length === 2 || assertionOptions(args[2], ['timeout', 'ignoreCase']))) return matcher;
    return null;
  }
  function hardLocatorAssertion(call, locator = node => proven(node, 'locator', true)) {
    const matcher = matcherShape(call);
    if (!matcher) return false;
    const expect = unwrap(matcher.expression);
    return ts.isCallExpression(expect) && !expect.questionDotToken && !expect.typeArguments?.length &&
      expect.arguments.length === 1 && plainBinding(expect.expression) && proven(expect.expression, 'expect', true) &&
      locator(expect.arguments[0]);
  }
  function directTry(statement) {
    const final = statement.finallyBlock;
    const cleanup = !statement.catchClause && final?.statements.length === 1 &&
      ts.isExpressionStatement(final.statements[0]) && unwrap(final.statements[0].expression);
    // A plain call's normal completion preserves a pending throw from any
    // try body; its own throw also fails the test. Keep registration proof,
    // and leave awaited, nested and control-flow cleanup shapes unresolved.
    if (cleanup && ts.isCallExpression(cleanup) && !cleanup.questionDotToken &&
        plainBinding(cleanup.expression) && directTestStatement(statement)) {
      supported.add(final); return;
    }
    if (!directAssertion(statement)) return;
    const emptyCatch = statement.catchClause && !statement.finallyBlock &&
      statement.catchClause.block.statements.length === 0 &&
      (!statement.catchClause.variableDeclaration || ts.isIdentifier(statement.catchClause.variableDeclaration.name));
    // The returned expression can itself throw/reject. Report the override
    // shape for review, never claim that the whole test necessarily passes.
    const finalReturn = !statement.catchClause && final?.statements.length === 1 &&
      ts.isReturnStatement(final.statements[0]) &&
      statement.parent?.parent && ts.isArrowFunction(statement.parent.parent);
    const catchBlock = statement.catchClause?.block;
    const directThrow = !final && catchBlock?.statements.length === 1 &&
      ts.isThrowStatement(catchBlock.statements[0]);
    // A direct throw does not discard an assertion rejection.
    if (directThrow) { supported.add(statement.catchClause); return; }
    if (!(emptyCatch || finalReturn)) return;
    const node = emptyCatch ? statement.catchClause : final;
    supported.add(node);
    const start = node.getStart(source), position = source.getLineAndCharacterOfPosition(start);
    findings.push({ patternId: '#3', severity: 'P0', disposition: 'candidate', origin: 'ast',
      variant: emptyCatch ? 'try-empty-catch' : 'finally-return', file: filename,
      line: position.line + 1, column: position.character + 1, start, end: node.end });
  }
  // Preserve source-linked handoffs from the shell scanner without claiming
  // runtime failure or whole-program propagation. Only the first direct try
  // statement supplies the gate; deferred bodies and nested tries cannot lend
  // their assertions to an enclosing catch. Following statements have no line
  // window, so a long try still pairs with its own catch.
  function dependentContext(statement) {
    if (directTestStatement(statement)) return true;
    const callback = statement.parent?.parent;
    if (!callback || !(ts.isArrowFunction(callback) || ts.isFunctionExpression(callback)) ||
        callback.asteriskToken || statement.parent !== callback.body) return false;
    const parent = callback.parent;
    if (ts.isPropertyAssignment(parent) && parent.initializer === callback &&
        ts.isObjectLiteralExpression(parent.parent)) {
      const object = parent.parent, call = object.parent;
      const extension = ts.isCallExpression(call) && dot(call.expression);
      return Boolean(extension && extension.name.text === 'extend' && !call.questionDotToken &&
        call.arguments.length === 1 && call.arguments[0] === object &&
        plainBinding(extension.expression) && proven(extension.expression, 'playwright-test'));
    }
    if (!ts.isCallExpression(parent) || parent.questionDotToken ||
        parent.arguments.length !== 1 || parent.arguments[0] !== callback) return false;
    const then = dot(parent.expression), request = then && unwrap(then.expression);
    const wait = request && ts.isCallExpression(request) && dot(request.expression);
    if (!then || then.name.text !== 'then' || !wait || wait.name.text !== 'waitForRequest' ||
        request.questionDotToken || !proven(wait.expression, 'page', true)) return false;
    let enclosing = parent.parent;
    while (enclosing && !ts.isFunctionLike(enclosing)) enclosing = enclosing.parent;
    return registeredTest(enclosing);
  }
  function dependentGate(statement) {
    const first = statement.tryBlock.statements[0];
    if (!first || !ts.isExpressionStatement(first)) return false;
    let call = unwrap(first.expression);
    const awaited = ts.isAwaitExpression(call);
    if (awaited) call = unwrap(call.expression);
    if (!ts.isCallExpression(call) || call.questionDotToken || call.typeArguments?.length) return false;
    const access = dot(call.expression);
    if (!access) return false;
    if (access.name.text === 'waitFor') return awaited && call.arguments.length <= 1 &&
      proven(access.expression, 'locator', true);
    if (awaited && hardLocatorAssertion(call)) return true;
    // A sync payload equality assertion can throw inside a request callback.
    // A poll assertion rejects only when awaited. Soft/custom matchers and
    // arbitrary expect factories stay outside this slice.
    const expectation = unwrap(access.expression);
    if (!ts.isCallExpression(expectation) || expectation.questionDotToken || expectation.typeArguments?.length ||
        expectation.arguments.length !== 1 || call.arguments.length !== 1) return false;
    const factory = dot(expectation.expression);
    if (factory?.name.text === 'poll') return awaited && access.name.text === 'toBe' &&
      plainBinding(factory.expression) && proven(factory.expression, 'expect', true);
    return access.name.text === 'toEqual' && plainBinding(expectation.expression) &&
      proven(expectation.expression, 'expect', true);
  }
  function logArgument(node) {
    node = unwrap(node);
    return ts.isIdentifier(node) || ts.isLiteralExpression(node) ||
      ts.isTemplateExpression(node) && node.templateSpans.every(span =>
        ts.isIdentifier(unwrap(span.expression)) || ts.isLiteralExpression(unwrap(span.expression)));
  }
  function loggingOnly(block) {
    return block.statements.every(statement => {
      if (!ts.isExpressionStatement(statement)) return false;
      const call = unwrap(statement.expression), access = ts.isCallExpression(call) && dot(call.expression);
      if (!access || call.questionDotToken || !['log', 'warn', 'error', 'info', 'debug'].includes(access.name.text) ||
          !ts.isIdentifier(access.expression) || access.expression.text !== 'console' ||
          receivers.checker.getSymbolAtLocation(access.expression)) return false;
      // Calling recovery code from a log argument is not logging-only.
      return call.arguments.every(logArgument);
    });
  }
  function dependentTry(statement) {
    const clause = statement.catchClause;
    if (!clause || supported.has(clause) || statement.finallyBlock ||
        !dependentContext(statement) || !dependentGate(statement)) return;
    const propagation = outcomes(clause.block);
    if (propagation.size === 1 && propagation.has('throw')) { supported.add(clause); return; }
    if ((clause.variableDeclaration && !ts.isIdentifier(clause.variableDeclaration.name)) ||
        !loggingOnly(clause.block)) return;
    supported.add(clause);
    const start = clause.getStart(source), position = source.getLineAndCharacterOfPosition(start);
    findings.push({ patternId: '#3', severity: 'P0', disposition: 'candidate', origin: 'ast',
      variant: 'try-dependent', file: filename, line: position.line + 1,
      column: position.character + 1, start, end: clause.end });
  }
  function sourceCandidate(clause, variant, kind, requirements) {
    const start = clause.getStart(source), position = source.getLineAndCharacterOfPosition(start);
    findings.push({ patternId: '#3', severity: 'P0', disposition: 'candidate', origin: 'ast',
      variant, file: filename, line: position.line + 1, column: position.character + 1, start, end: clause.end,
      evidence: { kind, requirements } });
  }
  // Unknown fixture packages cannot prove framework or Promise semantics.
  // Preserve only an exact aliased-expect/Locator empty-catch source shape
  // tied to a named test import and registration. Membership stays unknown.
  function uncertainFixtureCatches() {
    const bindings = new Map(), checker = receivers.checker;
    for (const statement of source.statements) {
      if (!ts.isImportDeclaration(statement) || statement.importClause?.isTypeOnly ||
          !ts.isStringLiteral(statement.moduleSpecifier) || statement.moduleSpecifier.text.startsWith('.')) continue;
      const named = statement.importClause?.namedBindings;
      if (!named || !ts.isNamedImports(named)) continue;
      for (const entry of named.elements) {
        const role = (entry.propertyName || entry.name).text, symbol = checker.getSymbolAtLocation(entry.name);
        if (entry.isTypeOnly || !['test', 'expect'].includes(role) || !symbol ||
            isWritten(source, checker, symbol, { properties: true })) continue;
        const proof = scope.expression(filename, entry.name);
        if (!proof.complete && proof.reasons.length && proof.reasons.every(reason => reason.startsWith('unsupported package/path alias:')))
          bindings.set(symbol, { role, module: statement.moduleSpecifier.text });
      }
    }
    const binding = node => ts.isIdentifier(unwrap(node)) && bindings.get(checker.getSymbolAtLocation(unwrap(node)));
    const registrations = new Map();
    for (const statement of source.statements) {
      if (!ts.isExpressionStatement(statement)) continue;
      const call = unwrap(statement.expression);
      if (!ts.isCallExpression(call) || call.questionDotToken || call.arguments.length !== 2) continue;
      const access = dot(call.expression), owner = binding(access?.name.text === 'only' ? access.expression : call.expression);
      const callback = call.arguments[1];
      if (owner?.role === 'test' && ts.isStringLiteral(call.arguments[0]) &&
          (ts.isArrowFunction(callback) || ts.isFunctionExpression(callback)) && !callback.asteriskToken)
        registrations.set(callback, owner.module);
    }
    if (!registrations.size) return;
    walk(source, node => {
      if (!ts.isCallExpression(node) || node.questionDotToken || node.typeArguments?.length || node.arguments.length !== 1) return;
      const access = dot(node.expression), handler = node.arguments[0];
      if (!access || access.name.text !== 'catch' || !ts.isArrowFunction(handler) || handler.parameters.length ||
          handler.modifiers?.length || !ts.isBlock(handler.body) || handler.body.statements.length) return;
      const target = unwrap(access.expression);
      if (!ts.isCallExpression(target) || target.questionDotToken || target.typeArguments?.length) return;
      let line = node;
      if (ts.isAwaitExpression(line.parent)) line = line.parent;
      if (!ts.isExpressionStatement(line.parent)) return;
      line = line.parent;
      let accepted = false;
      {
        const callback = line.parent?.parent, module = registrations.get(callback), matcher = dot(target.expression);
        const expectation = matcher && unwrap(matcher.expression);
        if (!module || callback.body !== line.parent || !matcher || matcher.name.text !== 'toBeVisible' || target.arguments.length ||
            !ts.isCallExpression(expectation) || expectation.questionDotToken || expectation.typeArguments?.length || expectation.arguments.length !== 1) return;
        const expect = binding(expectation.expression), locator = unwrap(expectation.arguments[0]);
        const query = ts.isCallExpression(locator) && dot(locator.expression);
        if (expect?.role !== 'expect' || expect.module !== module || !query || query.name.text !== 'locator' ||
            locator.questionDotToken || locator.typeArguments?.length || locator.arguments.length !== 1 ||
            !ts.isStringLiteral(locator.arguments[0]) || !ts.isIdentifier(query.expression)) return;
        const symbol = checker.getSymbolAtLocation(query.expression), declarations = symbol?.declarations;
        const element = declarations?.length === 1 && declarations[0];
        accepted = Boolean(element && ts.isBindingElement(element) && (element.propertyName || element.name).text === 'page' &&
          ts.isObjectBindingPattern(element.parent) && ts.isParameter(element.parent.parent) &&
          element.parent.parent.parent === callback && !element.initializer && !element.dotDotDotToken &&
          !isWritten(source, checker, symbol, { properties: true }));
      }
      if (!accepted) return;
      const start = access.name.getStart(source), position = source.getLineAndCharacterOfPosition(start);
      findings.push({ patternId: '#3', severity: 'P0', disposition: 'candidate', origin: 'ast',
        variant: 'unresolved-fixture-empty-catch', file: filename, line: position.line + 1,
        column: position.character + 1, start, end: node.end,
        evidence: { kind: 'unresolved-fixture-empty-catch', requirements:
          ['verify-test-fixture-membership', 'verify-runtime-catch-contract', 'verify-required-test-outcome'] } });
    });
  }
  // Two source-linked response paths only: an awaited page.request.get().then
  // whose inline callback returns a hard ok() assertion, and a finished().then
  // callback over a same-test const response from await waitForResponse().
  // The local source link is evidence for review, not whole-program response
  // provenance or a claim that an endpoint/branch actually ran.
  function immutableSymbol(node) {
    node = unwrap(node);
    if (!ts.isIdentifier(node)) return null;
    const symbol = receivers.checker.getSymbolAtLocation(node);
    return symbol?.declarations?.length === 1 && !isWritten(source, receivers.checker, symbol, { properties: true })
      ? symbol : null;
  }
  // A detached rejection observer does not replace the original Promise.
  // Admit only a direct const Playwright wait plus adjacent await in the
  // same registered test; aliases, derived promises and races stay outside.
  function observedOriginalAwait(call) {
    const statement = call.parent;
    if (!ts.isExpressionStatement(statement) || statement.expression !== call ||
        !directTestStatement(statement) || call.questionDotToken) return false;
    const access = dot(call.expression), name = access && unwrap(access.expression);
    const symbol = name && immutableSymbol(name), declaration = symbol?.declarations[0];
    if (!declaration || !ts.isVariableDeclaration(declaration) ||
        !ts.isIdentifier(declaration.name) || !declaration.initializer ||
        !ts.isVariableDeclarationList(declaration.parent) || declaration.parent.declarations.length !== 1 ||
        !(declaration.parent.flags & ts.NodeFlags.Const) ||
        declaration.parent.parent.parent !== statement.parent) return false;
    const initial = unwrap(declaration.initializer), wait = ts.isCallExpression(initial) && dot(initial.expression);
    if (!wait || initial.questionDotToken || initial.typeArguments?.length ||
        !['waitForURL', 'waitForResponse', 'waitForRequest', 'waitForEvent'].includes(wait.name.text) ||
        !proven(wait.expression, 'page', true)) return false;
    const lines = statement.parent.statements, index = lines.indexOf(statement);
    // Keep the original declaration immediately before the observer. This
    // excludes intervening escapes or calls that could replace its methods.
    if (index < 1 || declaration.parent.parent !== lines[index - 1]) return false;
    const next = lines[index + 1];
    if (!next || !ts.isExpressionStatement(next)) return false;
    const awaited = unwrap(next.expression);
    return ts.isAwaitExpression(awaited) && immutableSymbol(awaited.expression) === symbol;
  }
  function inlineThen(call) {
    call = unwrap(call);
    if (!ts.isCallExpression(call) || call.questionDotToken || call.typeArguments?.length || call.arguments.length !== 1) return null;
    const then = dot(call.expression), callback = call.arguments[0];
    if (!then || then.name.text !== 'then' || !(ts.isArrowFunction(callback) || ts.isFunctionExpression(callback)) ||
        callback.asteriskToken || callback.modifiers?.some(m => m.kind === ts.SyntaxKind.AsyncKeyword)) return null;
    return { promise: unwrap(then.expression), callback };
  }
  function responseAssertion(node, responseSymbol, method, matcherName) {
    node = unwrap(node);
    if (!ts.isCallExpression(node) || node.questionDotToken || node.typeArguments?.length) return false;
    const matcher = dot(node.expression);
    if (!matcher || matcher.name.text !== matcherName ||
        (matcherName === 'toBeTruthy' ? node.arguments.length !== 0 :
          node.arguments.length !== 1 || !ts.isNumericLiteral(unwrap(node.arguments[0])))) return false;
    const expect = unwrap(matcher.expression);
    if (!ts.isCallExpression(expect) || expect.questionDotToken || expect.typeArguments?.length ||
        expect.arguments.length !== 1 || !plainBinding(expect.expression) || !proven(expect.expression, 'expect', true)) return false;
    const value = unwrap(expect.arguments[0]), read = ts.isCallExpression(value) && dot(value.expression);
    return Boolean(read && read.name.text === method && !value.questionDotToken && !value.typeArguments?.length &&
      value.arguments.length === 0 && immutableSymbol(read.expression) === responseSymbol);
  }
  function requestThenGate(statement) {
    if (!directTestStatement(statement) || statement.tryBlock.statements.length !== 1) return false;
    const line = statement.tryBlock.statements[0];
    if (!ts.isExpressionStatement(line) || !ts.isAwaitExpression(unwrap(line.expression))) return false;
    const chain = inlineThen(unwrap(unwrap(line.expression).expression));
    if (!chain || chain.callback.parameters.length !== 1) return false;
    const request = chain.promise, get = ts.isCallExpression(request) && dot(request.expression);
    const context = get && dot(get.expression);
    if (!context || context.name.text !== 'request' || get.name.text !== 'get' || request.questionDotToken ||
        request.typeArguments?.length || request.arguments.length !== 1 || !ts.isStringLiteral(unwrap(request.arguments[0])) ||
        !proven(context.expression, 'page', true)) return false;
    const parameter = chain.callback.parameters[0];
    if (!ts.isIdentifier(parameter.name) || parameter.initializer || parameter.dotDotDotToken) return false;
    const symbol = immutableSymbol(parameter.name);
    if (!symbol) return false;
    let assertion = chain.callback.body;
    if (ts.isBlock(assertion)) {
      if (assertion.statements.length !== 1 || !ts.isReturnStatement(assertion.statements[0]) ||
          !assertion.statements[0].expression) return false;
      assertion = assertion.statements[0].expression;
    }
    return responseAssertion(assertion, symbol, 'ok', 'toBeTruthy');
  }
  function localConst(node, callback, before) {
    const symbol = immutableSymbol(node), declaration = symbol?.declarations[0];
    if (!declaration || !ts.isVariableDeclaration(declaration) || !declaration.initializer || declaration.end > before ||
        !ts.isIdentifier(declaration.name) || !ts.isVariableDeclarationList(declaration.parent) ||
        !(declaration.parent.flags & ts.NodeFlags.Const) || !ts.isVariableStatement(declaration.parent.parent) ||
        declaration.parent.parent.parent !== callback.body) return null;
    return declaration;
  }
  function waitedResponse(node, callback) {
    const response = localConst(node, callback, node.getStart(source));
    if (!response || !ts.isAwaitExpression(unwrap(response.initializer))) return null;
    const initializer = unwrap(unwrap(response.initializer).expression);
    const pending = localConst(initializer, callback, response.getStart(source));
    // Only the original two-binding form, or its direct await equivalent.
    const request = pending ? unwrap(pending.initializer) : initializer;
    const wait = ts.isCallExpression(request) && dot(request.expression);
    if (!wait || wait.name.text !== 'waitForResponse' || request.questionDotToken || request.typeArguments?.length ||
        request.arguments.length !== 1 || !ts.isStringLiteral(unwrap(request.arguments[0])) ||
        !proven(wait.expression, 'page', true)) return null;
    return immutableSymbol(node);
  }
  function finishedThenGate(statement) {
    const callback = statement.parent?.parent;
    if (!callback || statement.parent !== callback.body || callback.parameters?.length !== 0) return false;
    const call = callback.parent;
    if (!ts.isCallExpression(call)) return false;
    const chain = inlineThen(call);
    if (!chain || chain.callback !== callback) return false;
    const awaited = call.parent, line = awaited?.parent;
    if (!ts.isAwaitExpression(awaited) || !ts.isExpressionStatement(line) || !directTestStatement(line)) return false;
    const finished = chain.promise, method = ts.isCallExpression(finished) && dot(finished.expression);
    if (!method || method.name.text !== 'finished' || finished.questionDotToken || finished.typeArguments?.length ||
        finished.arguments.length !== 0) return false;
    const symbol = waitedResponse(method.expression, line.parent.parent);
    if (!symbol || statement.tryBlock.statements.length !== 1) return false;
    const first = statement.tryBlock.statements[0];
    return ts.isExpressionStatement(first) && responseAssertion(first.expression, symbol, 'status', 'toBe');
  }
  function responseTry(statement) {
    const clause = statement.catchClause;
    if (!clause || supported.has(clause) || statement.finallyBlock ||
        !(requestThenGate(statement) || finishedThenGate(statement))) return;
    const propagation = outcomes(clause.block);
    if (propagation.size === 1 && propagation.has('throw')) { supported.add(clause); return; }
    if (clause.variableDeclaration && !ts.isIdentifier(clause.variableDeclaration.name) || !loggingOnly(clause.block)) return;
    supported.add(clause);
    sourceCandidate(clause, 'try-response-chain', 'source-linked-response-chain',
      ['verify-response-chain-execution', 'verify-required-test-outcome']);
  }
  // This synchronous slice does not borrow promise rejection semantics. Only
  // a direct, proven hard equality assertion over literal values is admitted.
  function synchronousTry(statement) {
    const clause = statement.catchClause, callback = statement.parent?.parent;
    if (!clause || supported.has(clause) || statement.finallyBlock || statement.parent !== callback?.body ||
        !registeredTest(callback, false) || statement.tryBlock.statements.length !== 1) return;
    const line = statement.tryBlock.statements[0];
    if (!ts.isExpressionStatement(line)) return;
    const call = unwrap(line.expression), matcher = ts.isCallExpression(call) && dot(call.expression);
    if (!matcher || matcher.name.text !== 'toBe' || call.questionDotToken || call.typeArguments?.length ||
        call.arguments.length !== 1 || !literalOption(call.arguments[0])) return;
    const expect = unwrap(matcher.expression);
    if (!ts.isCallExpression(expect) || expect.questionDotToken || expect.typeArguments?.length ||
        expect.arguments.length !== 1 || !literalOption(expect.arguments[0]) || !plainBinding(expect.expression) ||
        !proven(expect.expression, 'expect', true)) return;
    const propagation = outcomes(clause.block);
    if (propagation.size === 1 && propagation.has('throw')) { supported.add(clause); return; }
    if (clause.variableDeclaration && !ts.isIdentifier(clause.variableDeclaration.name) || !loggingOnly(clause.block)) return;
    supported.add(clause);
    sourceCandidate(clause, 'try-sync-assertion', 'hard-sync-assertion', ['verify-required-test-outcome']);
  }
  // An imported Page annotation identifies a review surface, not a runtime
  // receiver. Limit this lane to top-level async helpers and their own direct
  // try, or a direct try in one for-loop. Never promote this evidence to a
  // proven Locator, and retain a diagnostic even for an emitted candidate.
  function typedHelperContext(statement) {
    let body = statement.parent;
    if (ts.isBlock(body) && ts.isForStatement(body.parent) && body.parent.statement === body) body = body.parent.parent;
    const fn = body?.parent;
    return ts.isBlock(body) && ts.isFunctionDeclaration(fn) && fn.body === body && fn.parent === source &&
      !fn.asteriskToken && fn.modifiers?.some(m => m.kind === ts.SyntaxKind.AsyncKeyword) ? fn : null;
  }
  function typedLocator(node, fn) {
    node = unwrap(node);
    if (!ts.isCallExpression(node) || node.questionDotToken || node.typeArguments?.length || !node.arguments.length) return false;
    const access = dot(node.expression);
    if (!access || !['locator', 'getByRole', 'getByText', 'getByLabel', 'getByTestId',
      'getByPlaceholder', 'getByAltText', 'getByTitle'].includes(access.name.text)) return false;
    const root = unwrap(access.expression);
    if (!ts.isIdentifier(root)) return false;
    const symbol = receivers.checker.getSymbolAtLocation(root), declarations = symbol?.declarations;
    const parameter = declarations?.length === 1 && declarations[0];
    if (!parameter || !ts.isParameter(parameter) || parameter.parent !== fn || parameter.initializer ||
        parameter.dotDotDotToken || !ts.isIdentifier(parameter.name)) return false;
    const proof = receivers.expression(root);
    // Call-site proof of an annotated Page parameter is stronger evidence for
    // the same review lane; it never discharges the helper-outcome diagnostic.
    return proof.complete && (proof.kind === 'page-type' || proof.kind === 'page' && Boolean(parameter.type));
  }
  function typedHelperTry(statement) {
    const clause = statement.catchClause, fn = typedHelperContext(statement);
    if (!clause || supported.has(clause) || !fn || statement.finallyBlock ||
        clause.variableDeclaration && !ts.isIdentifier(clause.variableDeclaration.name) || !loggingOnly(clause.block)) return;
    const first = statement.tryBlock.statements[0];
    if (!first || !ts.isExpressionStatement(first) || !ts.isAwaitExpression(unwrap(first.expression))) return;
    const call = unwrap(unwrap(first.expression).expression), access = ts.isCallExpression(call) && dot(call.expression);
    if (!access || call.questionDotToken || call.typeArguments?.length) return;
    const gate = access.name.text === 'waitFor' && call.arguments.length <= 1 && typedLocator(access.expression, fn) ||
      hardLocatorAssertion(call, node => typedLocator(node, fn));
    if (!gate) return;
    sourceCandidate(clause, 'try-typed-helper', 'typed-playwright-helper',
      ['verify-runtime-receiver', 'verify-helper-callers', 'verify-required-test-outcome']);
    diagnostic(clause, 'unresolved #3 typed helper runtime provenance and required outcome; Page annotation is not runtime proof');
  }
  // The ordinary timeout branch can consume a wait failure even while all
  // other error classes rethrow. Match this exact lexical allowlist; unrelated
  // application error names and general conditional recovery remain gaps.
  function timeoutTry(statement) {
    const clause = statement.catchClause;
    if (!clause || supported.has(clause) || statement.finallyBlock || !directTestStatement(statement) ||
        !dependentGate(statement) || !clause.variableDeclaration ||
        !ts.isIdentifier(clause.variableDeclaration.name) || clause.block.statements.length !== 1) return;
    const error = receivers.checker.getSymbolAtLocation(clause.variableDeclaration.name);
    const sameError = node => ts.isIdentifier(unwrap(node)) && receivers.checker.getSymbolAtLocation(unwrap(node)) === error;
    if (!error || isWritten(source, receivers.checker, error, { properties: true })) return;
    const branch = clause.block.statements[0];
    if (!ts.isIfStatement(branch) || branch.elseStatement) return;
    const condition = unwrap(branch.expression);
    if (!ts.isPrefixUnaryExpression(condition) || condition.operator !== ts.SyntaxKind.ExclamationToken) return;
    const and = unwrap(condition.operand);
    if (!ts.isBinaryExpression(and) || and.operatorToken.kind !== ts.SyntaxKind.AmpersandAmpersandToken) return;
    const instance = unwrap(and.left), name = unwrap(and.right);
    if (!ts.isBinaryExpression(instance) || instance.operatorToken.kind !== ts.SyntaxKind.InstanceOfKeyword ||
        !sameError(instance.left) || !ts.isIdentifier(instance.right) || instance.right.text !== 'Error' ||
        receivers.checker.getSymbolAtLocation(instance.right) || !ts.isBinaryExpression(name) ||
        name.operatorToken.kind !== ts.SyntaxKind.EqualsEqualsEqualsToken) return;
    const property = dot(name.left);
    if (!property || property.name.text !== 'name' || !sameError(property.expression) ||
        !ts.isStringLiteral(unwrap(name.right)) || unwrap(name.right).text !== 'TimeoutError') return;
    const rethrow = ts.isBlock(branch.thenStatement) && branch.thenStatement.statements.length === 1
      ? branch.thenStatement.statements[0] : branch.thenStatement;
    if (!ts.isThrowStatement(rethrow) || !sameError(rethrow.expression)) return;
    supported.add(clause);
    sourceCandidate(clause, 'try-timeout-filter', 'consumed-timeout-branch', ['verify-required-test-outcome']);
  }
  // A known hard assertion plus an exact error-name allowlist is a review
  // anchor, not proof of the runtime error's class, getters or branch outcome.
  // Keep the ordinary propagation diagnostic: this lane never marks supported.
  function namedErrorTry(statement) {
    const clause = statement.catchClause;
    if (!clause || supported.has(clause) || statement.finallyBlock || !directAssertion(statement) ||
        !clause.variableDeclaration || !ts.isIdentifier(clause.variableDeclaration.name) ||
        clause.block.statements.length !== 1) return;
    const error = receivers.checker.getSymbolAtLocation(clause.variableDeclaration.name);
    const sameError = node => ts.isIdentifier(unwrap(node)) && receivers.checker.getSymbolAtLocation(unwrap(node)) === error;
    if (!error || isWritten(source, receivers.checker, error, { properties: true })) return;
    const branch = clause.block.statements[0];
    if (!ts.isIfStatement(branch) || branch.elseStatement) return;
    const rethrow = ts.isBlock(branch.thenStatement) && branch.thenStatement.statements.length === 1
      ? branch.thenStatement.statements[0] : branch.thenStatement;
    if (!ts.isThrowStatement(rethrow) || !sameError(rethrow.expression)) return;
    let condition = unwrap(branch.expression), negated = false;
    if (ts.isPrefixUnaryExpression(condition) && condition.operator === ts.SyntaxKind.ExclamationToken) {
      condition = unwrap(condition.operand); negated = true;
    }
    if (!ts.isBinaryExpression(condition)) return;
    const names = ['TimeoutError', 'BrowserTimeoutError', 'AssertionError'];
    if (condition.operatorToken.kind === ts.SyntaxKind.InstanceOfKeyword) {
      const constructor = unwrap(condition.right);
      if (!negated || !sameError(condition.left) || !ts.isIdentifier(constructor) ||
          !names.includes(constructor.text) || receivers.checker.getSymbolAtLocation(constructor)) return;
      // An unresolved name is deliberately uncertain. Reject visible bindings,
      // writes, aliases and global-property references instead of trusting it.
      let otherReference = false;
      walk(source, node => {
        if (node === constructor || !(ts.isIdentifier(node) || ts.isStringLiteral(node)) || node.text !== constructor.text) return;
        if (ts.isIdentifier(node) && ts.isBinaryExpression(node.parent) && node.parent.right === node &&
            node.parent.operatorToken.kind === ts.SyntaxKind.InstanceOfKeyword &&
            !receivers.checker.getSymbolAtLocation(node)) return;
        otherReference = true;
      });
      if (otherReference) return;
    } else {
      const expected = negated ? ts.SyntaxKind.EqualsEqualsEqualsToken : ts.SyntaxKind.ExclamationEqualsEqualsToken;
      const value = unwrap(condition.right), property = dot(condition.left);
      if (condition.operatorToken.kind !== expected || !ts.isStringLiteral(value) || !names.includes(value.text) ||
          !property || property.name.text !== 'name') return;
      const owner = unwrap(property.expression), constructor = dot(owner);
      if (!sameError(owner) && !(constructor?.name.text === 'constructor' && sameError(constructor.expression))) return;
    }
    sourceCandidate(clause, 'try-named-error-filter', 'hard-assertion-error-allowlist',
      ['verify-runtime-error-identity', 'verify-consumed-branch', 'verify-required-test-outcome']);
  }
  // These exact catch bodies expose a possible consumption path, but the
  // branch value and JSX factory can still throw. Retain propagation unknowns.
  function sourceCatchOutcome(statement) {
    const clause = statement.catchClause;
    if (!clause || supported.has(clause) || statement.finallyBlock || !directAssertion(statement)) return;
    const lines = clause.block.statements;
    if (clause.variableDeclaration && ts.isIdentifier(clause.variableDeclaration.name) && lines.length === 2) {
      const error = receivers.checker.getSymbolAtLocation(clause.variableDeclaration.name);
      const branch = lines[0], last = lines[1];
      if (!error || isWritten(source, receivers.checker, error, { properties: true }) ||
          !ts.isIfStatement(branch) || branch.elseStatement || !ts.isIdentifier(unwrap(branch.expression)) ||
          !ts.isThrowStatement(last) || !last.expression || !ts.isIdentifier(unwrap(last.expression)) ||
          receivers.checker.getSymbolAtLocation(unwrap(last.expression)) !== error) return;
      const exit = ts.isBlock(branch.thenStatement) && branch.thenStatement.statements.length === 1
        ? branch.thenStatement.statements[0] : branch.thenStatement;
      if (!ts.isReturnStatement(exit) || exit.expression) return;
      sourceCandidate(clause, 'try-conditional-return', 'hard-assertion-conditional-return',
        ['verify-return-branch-reachability', 'verify-required-test-outcome']);
    } else if (!clause.variableDeclaration && lines.length === 1 && ts.isVariableStatement(lines[0])) {
      const list = lines[0].declarationList;
      if (!(list.flags & ts.NodeFlags.Const) || list.declarations.length !== 1) return;
      const declaration = list.declarations[0], jsx = declaration.initializer && unwrap(declaration.initializer);
      if (!ts.isIdentifier(declaration.name) || !jsx || !ts.isJsxElement(jsx) ||
          !ts.isIdentifier(jsx.openingElement.tagName) || !/^[a-z]/.test(jsx.openingElement.tagName.text) ||
          jsx.openingElement.attributes.properties.length || jsx.openingElement.typeArguments?.length ||
          !ts.isIdentifier(jsx.closingElement.tagName) || jsx.closingElement.tagName.text !== jsx.openingElement.tagName.text ||
          !jsx.children.every(ts.isJsxText)) return;
      sourceCandidate(clause, 'try-jsx-literal', 'hard-assertion-catch-jsx',
        ['verify-jsx-runtime', 'verify-required-test-outcome']);
    }
  }
  // Type-only Page POMs have no runtime framework membership. Preserve the
  // original direct instance-method catch candidates via an exact constructor
  // parameter-property link, retaining uncertainty instead of proving Page.
  function typedPomRoot(root, call) {
    const access = dot(root);
    if (!access || unwrap(access.expression).kind !== ts.SyntaxKind.ThisKeyword) return false;
    let expression = call;
    if (ts.isAwaitExpression(expression.parent)) expression = expression.parent;
    const line = expression.parent, method = line?.parent?.parent;
    if (!(ts.isExpressionStatement(line) || ts.isReturnStatement(line)) || line.expression !== expression ||
        !method || !ts.isMethodDeclaration(method) || method.body !== line.parent || method.asteriskToken ||
        method.modifiers?.some(item => item.kind === ts.SyntaxKind.StaticKeyword) ||
        method.parameters.some(item => ts.isIdentifier(item.name) && item.name.text === 'this')) return false;
    const klass = method.parent;
    if (!ts.isClassDeclaration(klass) || !klass.name || klass.heritageClauses?.length) return false;
    const classSymbol = receivers.checker.getSymbolAtLocation(klass.name);
    if (!classSymbol || isWritten(source, receivers.checker, classSymbol, { properties: true })) return false;
    const constructors = klass.members.filter(ts.isConstructorDeclaration);
    if (constructors.length !== 1 || !constructors[0].body || constructors[0].body.statements.length) return false;
    const matches = constructors[0].parameters.filter(parameter => ts.isIdentifier(parameter.name) &&
      parameter.name.text === access.name.text && !parameter.initializer && !parameter.dotDotDotToken &&
      parameter.modifiers?.some(item => [ts.SyntaxKind.PrivateKeyword, ts.SyntaxKind.PublicKeyword,
        ts.SyntaxKind.ProtectedKeyword, ts.SyntaxKind.ReadonlyKeyword].includes(item.kind)));
    if (matches.length !== 1 || klass.members.some(item => item.name &&
        (ts.isIdentifier(item.name) || ts.isStringLiteral(item.name)) && item.name.text === access.name.text)) return false;
    const proof = receivers.expression(matches[0].name);
    if (!proof.complete || proof.kind !== 'page-type') return false;
    let unsafe = false;
    walk(klass, node => {
      if (node.kind !== ts.SyntaxKind.ThisKeyword) return;
      const field = node.parent;
      if (!ts.isPropertyAccessExpression(field) || field.expression !== node || field.questionDotToken) { unsafe = true; return; }
      if (field.name.text !== access.name.text) return;
      // The Page value must not escape, be aliased, or be replaced. Only an
      // immediate method call is admitted; property writes and getters remain
      // unresolved. The entire class is checked, including deferred methods.
      const operation = field.parent, invocation = operation?.parent;
      if (!ts.isPropertyAccessExpression(operation) || operation.expression !== field || operation.questionDotToken ||
          !ts.isCallExpression(invocation) || invocation.expression !== operation || invocation.questionDotToken) unsafe = true;
    });
    return !unsafe;
  }
  function typedPomCatch(call) {
    const access = dot(call.expression);
    if (!access || access.name.text !== 'catch' || call.questionDotToken || call.typeArguments?.length || call.arguments.length !== 1) return false;
    const operation = unwrap(access.expression), action = ts.isCallExpression(operation) && dot(operation.expression);
    if (!action || operation.questionDotToken || operation.typeArguments?.length ||
        !(action.name.text === 'goto' && operation.arguments.length === 1 && ts.isStringLiteral(unwrap(operation.arguments[0])) ||
          ['close', 'title'].includes(action.name.text) && operation.arguments.length === 0) ||
        !typedPomRoot(action.expression, call)) return false;
    const callback = call.arguments[0];
    if (!(ts.isArrowFunction(callback) || ts.isFunctionExpression(callback)) || callback.asteriskToken ||
        callback.parameters.length || callback.modifiers?.some(item => item.kind === ts.SyntaxKind.AsyncKeyword)) return false;
    const empty = ts.isBlock(callback.body) && callback.body.statements.length === 0;
    if (!empty && ts.isBlock(callback.body) || returnedRejection(callback.body) || hasCleanup(call)) return false;
    const start = access.name.getStart(source), position = source.getLineAndCharacterOfPosition(start);
    if (source.getLineAndCharacterOfPosition(call.end).line - position.line > 12) return false;
    findings.push({ patternId: '#3', severity: 'P0', disposition: 'candidate', origin: 'ast',
      variant: empty ? 'empty' : 'fallback', file: filename, line: position.line + 1,
      column: position.character + 1, start, end: call.end,
      evidence: { kind: 'typed-playwright-pom-catch',
        requirements: ['verify-runtime-receiver', 'verify-helper-callers', 'verify-required-test-outcome'] } });
    diagnostic(access.name, 'unresolved #3 typed POM runtime provenance and required outcome; Page annotation is not runtime proof');
    return true;
  }
  // A literal cy.get(...).then callback can contain a synchronous manual gate.
  // Pair only its own direct try/if/throw with a logging-only catch. The branch
  // may never execute: this is a source-linked review candidate, not a claim
  // about runtime failure or the effect of a Cypress command queue.
  function cypressGlobal(node) {
    node = unwrap(node);
    if (!ts.isIdentifier(node) || node.text !== 'cy') return false;
    const proof = scope.cypressGlobal(filename, node);
    if (!proof.complete) diagnostic(node, proof.reasons.join('; '));
    return proof.complete && proof.kind === 'cypress-runtime';
  }
  function cypressManualContext(statement) {
    const callback = statement.parent?.parent;
    if (!callback || !(ts.isArrowFunction(callback) || ts.isFunctionExpression(callback)) ||
        callback.asteriskToken || callback.modifiers?.some(m => m.kind === ts.SyntaxKind.AsyncKeyword) ||
        statement.parent !== callback.body || callback.parameters.length !== 1 ||
        !ts.isIdentifier(callback.parameters[0].name) || callback.parameters[0].initializer ||
        callback.parameters[0].dotDotDotToken) return false;
    const call = callback.parent;
    if (!ts.isCallExpression(call) || call.questionDotToken || call.arguments.length !== 1 ||
        call.arguments[0] !== callback) return false;
    const then = dot(call.expression), query = then && unwrap(then.expression);
    const get = query && ts.isCallExpression(query) && dot(query.expression);
    return Boolean(then && then.name.text === 'then' && get && get.name.text === 'get' &&
      !query.questionDotToken && !query.typeArguments?.length && query.arguments.length === 1 &&
      ts.isStringLiteral(unwrap(query.arguments[0])) && cypressGlobal(get.expression));
  }
  function directManualThrow(statement) {
    if (statement.tryBlock.statements.length !== 1) return false;
    const gate = statement.tryBlock.statements[0];
    if (!ts.isIfStatement(gate) || gate.elseStatement) return false;
    const branch = ts.isBlock(gate.thenStatement) && gate.thenStatement.statements.length === 1
      ? gate.thenStatement.statements[0] : gate.thenStatement;
    if (!ts.isThrowStatement(branch) || !branch.expression) return false;
    const error = unwrap(branch.expression);
    return ts.isNewExpression(error) && ts.isIdentifier(error.expression) &&
      error.expression.text === 'Error' && !receivers.checker.getSymbolAtLocation(error.expression) &&
      !error.typeArguments?.length && (!error.arguments || error.arguments.length <= 1 &&
        error.arguments.every(arg => ts.isStringLiteral(unwrap(arg))));
  }
  function cypressManualTry(statement) {
    const clause = statement.catchClause;
    if (!clause || supported.has(clause) || statement.finallyBlock ||
        !cypressManualContext(statement) || !directManualThrow(statement)) return;
    const propagation = outcomes(clause.block);
    if (propagation.size === 1 && propagation.has('throw')) { supported.add(clause); return; }
    if (clause.variableDeclaration && !ts.isIdentifier(clause.variableDeclaration.name)) return;
    if (!clause.block.statements.length || !clause.block.statements.every(line => {
      if (!ts.isExpressionStatement(line)) return false;
      const call = unwrap(line.expression), log = ts.isCallExpression(call) && dot(call.expression);
      return log && log.name.text === 'log' && !call.questionDotToken && !call.typeArguments?.length &&
        call.arguments.length > 0 && call.arguments.every(arg => ts.isStringLiteral(unwrap(arg))) &&
        cypressGlobal(log.expression);
    })) return;
    supported.add(clause);
    const start = clause.getStart(source), position = source.getLineAndCharacterOfPosition(start);
    findings.push({ patternId: '#3', severity: 'P0', disposition: 'candidate', origin: 'ast',
      variant: 'try-cypress-manual-gate', file: filename, line: position.line + 1,
      column: position.character + 1, start, end: clause.end,
      evidence: { kind: 'cypress-manual-gate', requirements: ['verify-throw-reachability', 'verify-required-test-outcome'] } });
  }
  function ambientPromise(node) {
    node = unwrap(node);
    if (ts.isIdentifier(node)) return node.text === 'Promise' && !receivers.checker.getSymbolAtLocation(node);
    const access = member(node), root = access && unwrap(access.object);
    return access?.name === 'Promise' && ts.isIdentifier(root) &&
      ['globalThis', 'global', 'window'].includes(root.text) &&
      !receivers.checker.getSymbolAtLocation(root)?.declarations?.length;
  }
  let promiseMutated;
  function modifiedPromise() {
    if (promiseMutated !== undefined) return promiseMutated;
    promiseMutated = false;
    function reference(node) {
      node = unwrap(node);
      return ambientPromise(node) || Boolean(member(node) && reference(member(node).object));
    }
    function target(node) {
      node = unwrap(node);
      if (reference(node)) promiseMutated = true;
      else if (ts.isArrayLiteralExpression(node)) node.elements.forEach(target);
      else if (ts.isObjectLiteralExpression(node)) for (const entry of node.properties) {
        if (ts.isShorthandPropertyAssignment(entry)) target(entry.name);
        else if (ts.isPropertyAssignment(entry)) target(entry.initializer);
        else if (ts.isSpreadAssignment(entry)) target(entry.expression);
      }
    }
    walk(source, node => {
      if (ts.isBinaryExpression(node) && node.operatorToken.kind >= ts.SyntaxKind.FirstAssignment &&
          node.operatorToken.kind <= ts.SyntaxKind.LastAssignment) target(node.left);
      if (ts.isDeleteExpression(node)) target(node.expression);
      if ((ts.isPrefixUnaryExpression(node) || ts.isPostfixUnaryExpression(node)) &&
          [ts.SyntaxKind.PlusPlusToken, ts.SyntaxKind.MinusMinusToken].includes(node.operator)) target(node.operand);
      if ((ts.isForInStatement(node) || ts.isForOfStatement(node)) && !ts.isVariableDeclarationList(node.initializer)) target(node.initializer);
      const mutation = objectMutationTarget(node);
      if (mutation) target(mutation);
      const alias = ts.isVariableDeclaration(node) && node.initializer && reference(node.initializer) ? node.name :
        ts.isBinaryExpression(node) && node.operatorToken.kind === ts.SyntaxKind.EqualsToken && reference(node.right) ? node.left : null;
      if (alias && ts.isIdentifier(alias)) {
        const symbol = receivers.checker.getSymbolAtLocation(alias);
        if (symbol && isWritten(source, receivers.checker, symbol, { properties: true, propertyOnly: true })) promiseMutated = true;
      }
    });
    return promiseMutated;
  }
  function discardedSettled(node) {
    const callee = dot(node.expression);
    if (!callee || node.questionDotToken || node.typeArguments?.length || node.arguments.length !== 1 ||
        !ambientPromise(callee.expression) || modifiedPromise()) return false;
    let expression = node;
    while (expression.parent && unwrap(expression.parent) === expression) expression = expression.parent;
    if (!ts.isAwaitExpression(expression.parent)) return false;
    expression = expression.parent;
    while (expression.parent && unwrap(expression.parent) === expression) expression = expression.parent;
    const statement = expression.parent, items = unwrap(node.arguments[0]);
    if (!ts.isExpressionStatement(statement) || !directTestStatement(statement) ||
        !ts.isArrayLiteralExpression(items) || !items.elements.length ||
        !items.elements.every(item => hardLocatorAssertion(item))) return false;
    const start = node.getStart(source), position = source.getLineAndCharacterOfPosition(start);
    findings.push({ patternId: '#3', severity: 'P0', disposition: 'candidate', origin: 'ast',
      variant: 'all-settled', file: filename, line: position.line + 1, column: position.character + 1,
      start, end: node.end });
    return true;
  }
  // A proven afterEach/afterAll callback, or a proven test callback whose
  // final statement is a try with this catch in its finally block.
  function registeredHook(callback) {
    if (!callback || !(ts.isArrowFunction(callback) || ts.isFunctionExpression(callback)) || callback.asteriskToken ||
        !ts.isCallExpression(callback.parent) || callback.parent.questionDotToken || callback.parent.arguments.at(-1) !== callback) return false;
    const access = dot(callback.parent.expression);
    return Boolean(access && ['afterEach', 'afterAll'].includes(access.name.text) && plainBinding(access.expression) &&
      proven(access.expression, 'playwright-test'));
  }
  // Swallowing a cleanup failure after the test's assertions have run cannot
  // hide a failed outcome: nothing later in the callback reads an expect, and
  // the swallowed chain is not itself an assertion.
  function trailingCleanup(call) {
    const mentionsExpect = node => { let found = false; walk(node, item => {
      if (ts.isIdentifier(item) && item.text === 'expect') found = true; }); return found; };
    if (mentionsExpect(call.expression)) return false;
    let finallyOf = null, fn = call.parent;
    for (; fn && !ts.isFunctionLike(fn); fn = fn.parent) {
      if (ts.isBlock(fn) && ts.isTryStatement(fn.parent) && fn.parent.finallyBlock === fn) finallyOf = fn.parent;
    }
    if (!fn?.body || !ts.isBlock(fn.body)) return false;
    const hook = registeredHook(fn);
    const trailing = finallyOf && finallyOf.parent === fn.body && fn.body.statements.at(-1) === finallyOf && registeredTest(fn, false);
    if (!hook && !trailing) return false;
    // No assertion may follow the swallowed operation in this callback.
    let later = false;
    walk(fn.body, item => { if (item.pos >= call.end && ts.isIdentifier(item) && item.text === 'expect') later = true; });
    return !later;
  }
  // `await <locator>.waitFor(...).catch(...)` followed in the same block by an
  // awaited hard web-first assertion on the same locator expression re-checks
  // the waited state with retries, so the swallowed wait is not load-bearing.
  function reverifiedWait(call) {
    const wait = unwrap(dot(call.expression)?.expression);
    const waitAccess = wait && ts.isCallExpression(wait) && dot(wait.expression);
    if (!waitAccess || waitAccess.name.text !== 'waitFor' || !proven(waitAccess.expression, 'locator', true)) return false;
    const target = waitAccess.expression.getText(source).replace(/\s+/g, '');
    let statement = call;
    while (statement.parent && !ts.isBlock(statement.parent)) {
      if (ts.isFunctionLike(statement.parent)) return false;
      statement = statement.parent;
    }
    if (!ts.isExpressionStatement(statement)) return false;
    // The waited state, from a literal `state` option (default 'visible').
    const options = wait.arguments[0] && unwrap(wait.arguments[0]);
    let state = 'visible';
    if (wait.arguments.length > 1 || options && !ts.isObjectLiteralExpression(options)) return false;
    for (const item of options?.properties ?? []) {
      if (!ts.isPropertyAssignment(item) || !ts.isIdentifier(item.name)) return false;
      if (item.name.text === 'state') {
        if (!ts.isStringLiteral(unwrap(item.initializer))) return false;
        state = unwrap(item.initializer).text;
      }
    }
    // Matchers whose retried pass proves the waited state on that element.
    const proves = { visible: ['toBeVisible'], hidden: ['toBeHidden'],
      attached: ['toBeAttached', 'toBeVisible', 'toHaveText', 'toContainText', 'toHaveAttribute', 'toHaveValue'] }[state];
    if (!proves) return false;
    const block = statement.parent, index = block.statements.indexOf(statement);
    return block.statements.slice(index + 1).some(next => {
      if (!ts.isExpressionStatement(next)) return false;
      const awaited = unwrap(next.expression);
      const assertion = ts.isAwaitExpression(awaited) && unwrap(awaited.expression);
      const matcher = assertion && ts.isCallExpression(assertion) && !assertion.questionDotToken && dot(assertion.expression);
      const expectation = matcher && unwrap(matcher.expression);
      if (!matcher || !proves.includes(matcher.name.text) || !ts.isCallExpression(expectation) || expectation.questionDotToken ||
          expectation.arguments.length !== 1 || !plainBinding(expectation.expression) || !proven(expectation.expression, 'expect', true)) return false;
      // toBeVisible({ visible: false }) asserts the opposite state.
      if (matcher.name.text === 'toBeVisible' && assertion.arguments.length &&
          !(ts.isObjectLiteralExpression(unwrap(assertion.arguments[0])) && unwrap(assertion.arguments[0]).properties.every(item =>
            ts.isPropertyAssignment(item) && ts.isIdentifier(item.name) && item.name.text === 'timeout'))) return false;
      const subject = expectation.arguments[0];
      return unwrap(subject).getText(source).replace(/\s+/g, '') === target && proven(subject, 'locator', true);
    });
  }
  // `await op().catch(error => { errors.push(error); })` where `errors` is a
  // local const array that the same callback later asserts empty with a
  // direct `expect(errors).toEqual([])` statement: the caught error is
  // re-reported, not swallowed. Every other use of the array, a return that
  // could skip the assertion, or an unawaited chain keeps the candidate.
  function collectedErrors(call) {
    const checker = receivers.checker, callback = unwrap(call.arguments[0]);
    if (call.arguments.length !== 1 || !(ts.isArrowFunction(callback) || ts.isFunctionExpression(callback)) ||
        callback.parameters.length !== 1 || !ts.isIdentifier(callback.parameters[0].name) || callback.parameters[0].dotDotDotToken) return false;
    let line = callback.body;
    if (ts.isBlock(line)) {
      if (line.statements.length !== 1 || !ts.isExpressionStatement(line.statements[0])) return false;
      line = line.statements[0].expression;
    }
    line = unwrap(line);
    const push = ts.isCallExpression(line) && !line.questionDotToken && dot(line.expression);
    const errorSymbol = checker.getSymbolAtLocation(callback.parameters[0].name);
    if (!push || push.name.text !== 'push' || line.arguments.length !== 1 || !ts.isIdentifier(unwrap(line.arguments[0])) ||
        checker.getSymbolAtLocation(unwrap(line.arguments[0])) !== errorSymbol || !ts.isIdentifier(unwrap(push.expression))) return false;
    const list = checker.getSymbolAtLocation(unwrap(push.expression));
    const declaration = list?.declarations?.length === 1 ? list.declarations[0] : null;
    if (!declaration || !ts.isVariableDeclaration(declaration) || !declaration.initializer ||
        !ts.isArrayLiteralExpression(unwrap(declaration.initializer)) || unwrap(declaration.initializer).elements.length ||
        !(declaration.parent.flags & ts.NodeFlags.Const)) return false;
    // The awaited chain sits in the function that declares the array.
    let awaited = call;
    while (ts.isParenthesizedExpression(awaited.parent)) awaited = awaited.parent;
    if (!ts.isAwaitExpression(awaited.parent)) return false;
    let fn = call.parent;
    for (; fn && !ts.isFunctionLike(fn); fn = fn.parent);
    let owner = declaration.parent;
    for (; owner && !ts.isFunctionLike(owner); owner = owner.parent);
    if (!fn || fn !== owner || !fn.body || !ts.isBlock(fn.body)) return false;
    let unsupported = false, assertion = null;
    walk(fn.body, node => {
      if (unsupported) return;
      if (ts.isReturnStatement(node)) {
        let inner = node.parent;
        for (; inner && inner !== fn && !ts.isFunctionLike(inner); inner = inner.parent);
        if (inner === fn) unsupported = true;
      }
      if (!ts.isIdentifier(node) || node === declaration.name || checker.getSymbolAtLocation(node) !== list) return;
      const parent = node.parent;
      if (dot(parent) && parent.expression === node && parent.name.text === 'push' && ts.isCallExpression(parent.parent) &&
          parent.parent.expression === parent) return;
      if (ts.isForOfStatement(parent) && parent.expression === node) return;
      const expectation = parent;
      const matcher = ts.isCallExpression(expectation) && expectation.arguments.length === 1 && expectation.arguments[0] === node &&
        dot(expectation.parent) && expectation.parent.expression === expectation && expectation.parent.parent;
      const statement = matcher && ts.isCallExpression(matcher) && !matcher.questionDotToken && matcher.parent;
      const empty = matcher && (['toEqual', 'toStrictEqual'].includes(expectation.parent.name.text) && matcher.arguments.length === 1 &&
        ts.isArrayLiteralExpression(unwrap(matcher.arguments[0])) && !unwrap(matcher.arguments[0]).elements.length ||
        expectation.parent.name.text === 'toHaveLength' && matcher.arguments.length === 1 && unwrap(matcher.arguments[0]).getText(source) === '0');
      if (empty && ts.isExpressionStatement(statement) && statement.parent === fn.body && statement.pos >= call.end &&
          ts.isIdentifier(expectation.expression) && proven(expectation.expression, 'expect', true)) { assertion = statement; return; }
      unsupported = true;
    });
    return !unsupported && Boolean(assertion);
  }
  // Quiet proofs for the narrowing rules below: an unresolved receiver keeps
  // the candidate without adding a diagnostic of its own.
  function quietKind(node, receiver = true) {
    const value = receiver ? receivers.expression(node) : scope.expression(filename, node);
    return value.complete ? value.kind : 'unknown';
  }
  function skipParens(node) {
    while (node.parent && ts.isParenthesizedExpression(node.parent)) node = node.parent;
    return node;
  }
  function primitiveLiteral(node) {
    node = unwrap(node);
    if (ts.isStringLiteral(node) || ts.isNoSubstitutionTemplateLiteral(node)) return { value: node.text };
    if (ts.isNumericLiteral(node)) return { value: Number(node.text) };
    if (ts.isPrefixUnaryExpression(node) && node.operator === ts.SyntaxKind.MinusToken && ts.isNumericLiteral(unwrap(node.operand)))
      return { value: -Number(unwrap(node.operand).text) };
    if (node.kind === ts.SyntaxKind.TrueKeyword) return { value: true };
    if (node.kind === ts.SyntaxKind.FalseKeyword) return { value: false };
    if (node.kind === ts.SyntaxKind.NullKeyword) return { value: null };
    if (ts.isIdentifier(node) && node.text === 'undefined' && !receivers.checker.getSymbolAtLocation(node)?.declarations?.length)
      return { value: undefined };
    return null;
  }
  // Review hint: `await x.act().catch(() => undefined);` as a statement. The
  // fallback is `undefined` and nothing reads it, so the only harm is a later
  // step that depends on the swallowed call, which is what review decides.
  // Kept at P0: an empty block body (`() => {}`), a stored or returned
  // result, any wait (swallowed waits have their own timeout triage), state
  // checks, count(), matchers, polls, toPass, test.step and other calls that
  // take a callback, Promise combinators, then/finally, assertion-named
  // helpers, and a receiver that is not a direct method call.
  const KEEP_RECEIVERS = new Set(['isVisible', 'isHidden', 'isEnabled', 'isDisabled', 'isChecked', 'isEditable', 'count',
    'waitForTimeout', 'toPass', 'poll', 'step', 'all', 'allSettled', 'any', 'race', 'then', 'finally', 'catch']);
  const ASSERTING_NAME = /^(?:to[A-Z]|expect|assert|verify|check|ensure|should|validate|wait|poll)/;
  function discardedFallback(call) {
    const fallback = literalFallback(call);
    if (!fallback || fallback.value !== undefined) return false;
    const handler = unwrap(call.arguments[0]);
    if (handler.parameters.length || !ts.isIdentifier(unwrap(handler.body))) return false;
    const receiver = receiverCall(call);
    if (!receiver || WAITS.has(receiver.name) || KEEP_RECEIVERS.has(receiver.name) || ASSERTING_NAME.test(receiver.name) ||
        receiver.call.arguments.some(argument => ts.isArrowFunction(unwrap(argument)) || ts.isFunctionExpression(unwrap(argument)))) return false;
    let value = skipParens(call);
    if (ts.isAwaitExpression(value.parent) || ts.isVoidExpression(value.parent)) value = skipParens(value.parent);
    return ts.isExpressionStatement(value.parent);
  }
  // The handler's fallback value when it is a concise-body primitive literal.
  function literalFallback(call) {
    const handler = unwrap(call.arguments[0]);
    if (!(ts.isArrowFunction(handler) || ts.isFunctionExpression(handler)) || handler.asteriskToken ||
        handler.modifiers?.some(item => item.kind === ts.SyntaxKind.AsyncKeyword) || ts.isBlock(handler.body)) return null;
    return primitiveLiteral(handler.body);
  }
  function receiverCall(call) {
    const receiver = unwrap(unwrap(call.expression).expression);
    if (!ts.isCallExpression(receiver) || !ts.isPropertyAccessExpression(unwrap(receiver.expression))) return null;
    const access = unwrap(receiver.expression);
    return { call: receiver, name: access.name.text, object: access.expression, optional: Boolean(access.questionDotToken || receiver.questionDotToken) };
  }
  // C: `animation.finished.catch(...)` mapped over `getAnimations()` inside a
  // proven browser callback. Animation.finished rejects only when the
  // animation is cancelled, after which nothing is animating, and browser
  // code cannot swallow a Playwright assertion or timeout.
  function animationSettle(call) {
    if (!receivers.inBrowserCallback(call)) return false;
    const finished = unwrap(unwrap(call.expression).expression);
    if (!ts.isPropertyAccessExpression(finished) || finished.questionDotToken || finished.name.text !== 'finished' ||
        !ts.isIdentifier(unwrap(finished.expression))) return false;
    const symbol = receivers.checker.getSymbolAtLocation(unwrap(finished.expression));
    const parameter = symbol?.declarations?.length === 1 ? symbol.declarations[0] : null;
    const mapper = parameter && ts.isParameter(parameter) && ts.isIdentifier(parameter.name) && !parameter.dotDotDotToken ? parameter.parent : null;
    if (!mapper || !(ts.isArrowFunction(mapper) || ts.isFunctionExpression(mapper)) || mapper.parameters[0] !== parameter ||
        ts.isBlock(mapper.body) || isWritten(source, receivers.checker, symbol)) return false;
    let body = unwrap(mapper.body);
    if (ts.isAwaitExpression(body)) body = unwrap(body.expression);
    if (body !== call) return false;
    const map = mapper.parent;
    if (!ts.isCallExpression(map) || map.questionDotToken || map.arguments.length !== 1 || map.arguments[0] !== mapper) return false;
    const access = dot(map.expression);
    if (!access || access.name.text !== 'map') return false;
    return animationList(access.expression, 0);
  }
  // A receiver whose getAnimations() is the DOM method: the unshadowed
  // `document`, its body/documentElement, a document.querySelector(...) or
  // getElementById(...) result (through an unwritten const), or the element
  // parameter of a callback passed to evaluate() on a proven Locator. A user
  // object with a getAnimations member is not one.
  function nativeAnimatable(node, depth = 0) {
    node = unwrap(node);
    if (depth > 4) return false;
    const unboundDocument = item => ts.isIdentifier(item) && item.text === 'document' && !receivers.checker.getSymbolAtLocation(item);
    if (unboundDocument(node)) return true;
    if (ts.isPropertyAccessExpression(node) && ['body', 'documentElement'].includes(node.name.text)) return unboundDocument(unwrap(node.expression));
    if (ts.isCallExpression(node)) {
      const access = dot(node.expression);
      return Boolean(access && ['querySelector', 'getElementById'].includes(access.name.text) && unboundDocument(unwrap(access.expression)));
    }
    if (!ts.isIdentifier(node)) return false;
    const symbol = receivers.checker.getSymbolAtLocation(node);
    const declaration = symbol?.declarations?.length === 1 ? symbol.declarations[0] : null;
    if (!declaration || isWritten(source, receivers.checker, symbol, { properties: true })) return false;
    if (ts.isVariableDeclaration(declaration))
      return Boolean(declaration.initializer && declaration.parent.flags & ts.NodeFlags.Const && nativeAnimatable(declaration.initializer, depth + 1));
    if (!ts.isParameter(declaration) || declaration.dotDotDotToken) return false;
    const fn = declaration.parent, call = fn.parent;
    if (!(ts.isArrowFunction(fn) || ts.isFunctionExpression(fn)) || fn.parameters[0] !== declaration ||
        !ts.isCallExpression(call) || call.arguments[0] !== fn) return false;
    const evaluate = dot(call.expression);
    return Boolean(evaluate && evaluate.name.text === 'evaluate' && quietKind(evaluate.expression) === 'locator');
  }
  function animationList(node, depth) {
    node = unwrap(node);
    if (depth > 8) return false;
    if (ts.isIdentifier(node)) {
      const symbol = receivers.checker.getSymbolAtLocation(node);
      const declaration = symbol?.declarations?.length === 1 ? symbol.declarations[0] : null;
      return Boolean(declaration && ts.isVariableDeclaration(declaration) && ts.isIdentifier(declaration.name) && declaration.initializer &&
        declaration.parent.flags & ts.NodeFlags.Const && !isWritten(source, receivers.checker, symbol, { properties: true }) &&
        receivers.inBrowserCallback(declaration) && animationList(declaration.initializer, depth + 1));
    }
    // `element?.getAnimations() ?? []`
    if (ts.isBinaryExpression(node) && node.operatorToken.kind === ts.SyntaxKind.QuestionQuestionToken) {
      const right = unwrap(node.right);
      return ts.isArrayLiteralExpression(right) && !right.elements.length && animationList(node.left, depth + 1);
    }
    if (!ts.isCallExpression(node) || !ts.isPropertyAccessExpression(unwrap(node.expression))) return false;
    const access = unwrap(node.expression), name = access.name.text;
    if (name === 'getAnimations') return node.arguments.length <= 1 && nativeAnimatable(access.expression);
    return name === 'filter' && !node.questionDotToken && !access.questionDotToken && animationList(access.expression, depth + 1);
  }
  // J: a discarded `.catch` on closing or unrouting a proven Playwright
  // object. A failed teardown leaves a resource alive; it cannot make a
  // later assertion on the product pass.
  const TEARDOWN = new Map([['close', ['page', 'context', 'browser', 'electron-app']], ['dispose', ['request']],
    ['unroute', ['page', 'context']], ['unrouteAll', ['page', 'context']]]);
  function teardownCatch(call) {
    const receiver = receiverCall(call);
    if (!receiver || !TEARDOWN.has(receiver.name) || !TEARDOWN.get(receiver.name).includes(quietKind(receiver.object))) return false;
    let holder = skipParens(call).parent;
    if (ts.isAwaitExpression(holder) || ts.isVoidExpression(holder)) holder = skipParens(holder).parent;
    return ts.isExpressionStatement(holder);
  }
  // I: a proven response body read (`res.json()`/`res.text()`) whose literal
  // fallback reaches only failure messages: a template or `+` operand of a
  // `throw new Error(...)` message, an `expect(subject, message)` message or a
  // `console.*` argument, directly or through a const read only there. A
  // message cannot change whether a test passes, so swallowing the parse
  // error hides nothing.
  const MESSAGE_ERRORS = new Set(['Error', 'TypeError', 'RangeError']);
  function messageUse(node) {
    for (;;) {
      const parent = node.parent;
      if (ts.isParenthesizedExpression(parent) || ts.isAsExpression(parent) || ts.isNonNullExpression(parent) ||
          ts.isTemplateSpan(parent) || ts.isTemplateExpression(parent) ||
          ts.isBinaryExpression(parent) && parent.operatorToken.kind === ts.SyntaxKind.PlusToken) { node = parent; continue; }
      // `body.slice(0, 300)`, `JSON.stringify(body)`, `String(body)`.
      if (ts.isPropertyAccessExpression(parent) && parent.expression === node && !parent.questionDotToken &&
          ['slice', 'substring', 'trim'].includes(parent.name.text) && ts.isCallExpression(parent.parent) &&
          parent.parent.expression === parent && parent.parent.arguments.every(item => primitiveLiteral(item))) { node = parent.parent; continue; }
      if (ts.isCallExpression(parent) && parent.arguments.length === 1 && parent.arguments[0] === node) {
        const callee = unwrap(parent.expression), access = dot(callee);
        const global = (item, name) => ts.isIdentifier(unwrap(item)) && unwrap(item).text === name && !receivers.checker.getSymbolAtLocation(unwrap(item));
        if (global(callee, 'String') || access && access.name.text === 'stringify' && global(access.expression, 'JSON')) { node = parent; continue; }
      }
      break;
    }
    const parent = node.parent;
    if (ts.isNewExpression(parent) && parent.arguments?.[0] === node && ts.isIdentifier(unwrap(parent.expression)) &&
        MESSAGE_ERRORS.has(unwrap(parent.expression).text) && !receivers.checker.getSymbolAtLocation(unwrap(parent.expression)) &&
        ts.isThrowStatement(skipParens(parent).parent)) return true;
    if (ts.isCallExpression(parent) && parent.arguments.length === 2 && parent.arguments[1] === node && !parent.questionDotToken &&
        quietKind(parent.expression) === 'expect') return true;
    const consoleCall = ts.isCallExpression(parent) && parent.arguments.includes(node) && dot(parent.expression);
    return Boolean(consoleCall && ts.isIdentifier(unwrap(consoleCall.expression)) && unwrap(consoleCall.expression).text === 'console' &&
      !receivers.checker.getSymbolAtLocation(unwrap(consoleCall.expression)));
  }
  function messageOnlyBody(call) {
    const receiver = receiverCall(call);
    if (!receiver || receiver.optional || !['json', 'text'].includes(receiver.name) || receiver.call.arguments.length ||
        receivers.inBrowserCallback(call) || !receivers.data(receiver.call)) return false;
    const handler = unwrap(call.arguments[0]);
    if (!(ts.isArrowFunction(handler) || ts.isFunctionExpression(handler)) || handler.asteriskToken || ts.isBlock(handler.body) ||
        handler.modifiers?.some(item => item.kind === ts.SyntaxKind.AsyncKeyword)) return false;
    const fallback = unwrap(handler.body);
    if (!primitiveLiteral(fallback) && !(ts.isObjectLiteralExpression(fallback) && !fallback.properties.length) &&
        !(ts.isArrayLiteralExpression(fallback) && !fallback.elements.length)) return false;
    let value = skipParens(call);
    if (ts.isAwaitExpression(value.parent)) value = value.parent;
    while (ts.isParenthesizedExpression(value.parent) || ts.isAsExpression(value.parent) || ts.isNonNullExpression(value.parent)) value = value.parent;
    const declaration = value.parent;
    if (!ts.isVariableDeclaration(declaration) || declaration.initializer !== value) return messageUse(value);
    if (!ts.isIdentifier(declaration.name) || !(declaration.parent.flags & ts.NodeFlags.Const)) return false;
    const symbol = receivers.checker.getSymbolAtLocation(declaration.name);
    if (!symbol || isWritten(source, receivers.checker, symbol, { properties: true })) return false;
    let only = true, uses = 0;
    walk(source, item => {
      if (!only || !ts.isIdentifier(item) || item === declaration.name || receivers.checker.getSymbolAtLocation(item) !== symbol) return;
      uses++;
      if (!messageUse(item)) only = false;
    });
    return only && uses > 0;
  }
  // H triage (no verdict change): for a swallowed wait or navigation, name
  // what was waited for and whether any later assertion in the same function
  // re-checks it, and how a behavior-fault probe would decide it at runtime.
  const WAITS = new Set(['waitFor', 'waitForLoadState', 'waitForURL', 'waitForSelector', 'waitForResponse', 'waitForRequest',
    'waitForFunction', 'waitForEvent', 'waitForNavigation', 'goto']);
  // Index of the options argument for each wait, and the timeout family
  // Playwright Test applies when no `timeout` option is given.
  const WAIT_OPTIONS = { waitFor: [0, 'action'], waitForSelector: [1, 'action'], waitForResponse: [1, 'action'],
    waitForRequest: [1, 'action'], waitForEvent: [1, 'action'], waitForFunction: [2, 'action'],
    waitForLoadState: [1, 'navigation'], waitForURL: [1, 'navigation'], waitForNavigation: [0, 'navigation'], goto: [1, 'navigation'] };
  // These can reject at once on a non-timeout failure (a network error, a
  // throwing page predicate), so no timeout does not make the catch inert.
  const IMMEDIATE_REJECTION = new Set(['goto', 'waitForFunction']);
  // A `.catch` can swallow a TimeoutError only when the call has a finite
  // timeout. With none, a target that never arrives fails at the test timeout.
  function effectiveTimeout(receiver) {
    const [index, family] = WAIT_OPTIONS[receiver.name];
    const unknown = reason => ({ effective: 'unknown', reason });
    const argument = receiver.call.arguments[index] && unwrap(receiver.call.arguments[index]);
    if (argument && !(receiver.name === 'waitForEvent' && (ts.isArrowFunction(argument) || ts.isFunctionExpression(argument)))) {
      if (!ts.isObjectLiteralExpression(argument)) return unknown('the options argument is not an object literal');
      if (argument.properties.some(item => !ts.isPropertyAssignment(item) && !ts.isShorthandPropertyAssignment(item)))
        return unknown('the options object has a spread or computed member');
      const entry = argument.properties.find(item => item.name && (ts.isIdentifier(item.name) || ts.isStringLiteral(item.name)) && item.name.text === 'timeout');
      if (entry) {
        const value = ts.isPropertyAssignment(entry) ? unwrap(entry.initializer) : null;
        if (!value || !ts.isNumericLiteral(value)) return unknown('the timeout option is not a numeric literal');
        return Number(value.text) > 0 ? { effective: 'finite', source: 'option', ms: Number(value.text) } :
          { effective: 'none', source: 'option timeout: 0' };
      }
    }
    if (!framework.frameworks.includes('playwright') || framework.frameworks.includes('cypress'))
      return unknown('the file is not proven Playwright-only');
    const owner = receivers.expression(receiver.object);
    if (!owner.complete || !['page', 'locator'].includes(owner.kind)) return unknown('the receiver is not a proven Playwright page or locator');
    if (!waitTimeouts?.known) return unknown(waitTimeouts?.reason || 'the project configuration was not analyzed');
    const field = family === 'navigation' ? 'navigationTimeout' : 'actionTimeout';
    return waitTimeouts[field] > 0 ? { effective: 'finite', source: `${waitTimeouts.config} use.${field}`, ms: waitTimeouts[field] } :
      { effective: 'none', source: `${waitTimeouts.config} sets no use.${field}; the Playwright Test default is 0 (no limit)` };
  }
  function swallowedWaitTriage(call) {
    const receiver = receiverCall(call);
    if (!receiver || !WAITS.has(receiver.name)) return null;
    const text = node => node.getText(source).replace(/\s+/g, '');
    const clip = value => value.length > 80 ? `${value.slice(0, 77)}...` : value;
    const target = receiver.name === 'waitFor' ? text(receiver.object) : `${text(receiver.object)}.${receiver.name}(...)`;
    let state = null;
    if (receiver.name === 'waitFor') {
      state = 'visible';
      const options = receiver.call.arguments[0] && unwrap(receiver.call.arguments[0]);
      const entry = options && ts.isObjectLiteralExpression(options) && options.properties.find(item =>
        ts.isPropertyAssignment(item) && ts.isIdentifier(item.name) && item.name.text === 'state');
      if (entry) state = ts.isStringLiteral(unwrap(entry.initializer)) ? unwrap(entry.initializer).text : 'dynamic';
    }
    let fn = call.parent;
    while (fn && !ts.isFunctionLike(fn)) fn = fn.parent;
    const reasserted = [];
    let later = 0;
    if (fn?.body) walk(fn.body, item => {
      if (item.pos < call.end || !ts.isCallExpression(item) || !ts.isIdentifier(unwrap(item.expression)) || unwrap(item.expression).text !== 'expect') return;
      later++;
      if (receiver.name === 'waitFor' && item.arguments.length && text(item.arguments[0]) === text(receiver.object))
        reasserted.push(source.getLineAndCharacterOfPosition(item.getStart(source)).line + 1);
    });
    const subject = receiver.name === 'waitFor' ? `waited locator ${clip(target)} (state '${state}')` : `swallowed ${clip(target)}`;
    const hint = receiver.name === 'waitFor' && reasserted.length ?
      `${subject} is re-asserted only at line ${reasserted.join(', ')}, not unconditionally in the same block after the catch` :
      `${subject} is ${receiver.name === 'waitFor' ? 'never re-asserted' : 'not re-checked'} after the catch in this function; ` +
      (later ? `check whether the ${later} later assertion(s) there depend on it` : 'no assertion follows it in this function; for a helper, check what its callers assert next');
    const probe = `an e2e-skills-check probe in behavior-fault mode whose source edit keeps ${receiver.name === 'waitFor' ?
      `${clip(target)} from reaching '${state}'` : `${receiver.name} from completing`}; SURVIVED with fault_reached confirms the swallowed wait, a linked failure (DETECTED) refutes it`;
    const timeout = effectiveTimeout(receiver);
    // Only a provable no-timeout wait whose sole failure mode is waiting is
    // downgraded; goto and waitForFunction can still reject at once.
    const inert = timeout.effective === 'none' && !IMMEDIATE_REJECTION.has(receiver.name);
    const timeoutHint = timeout.effective === 'finite' ? `; finite timeout ${timeout.ms} ms (${timeout.source}), so the catch can swallow a TimeoutError` :
      inert ? `no finite timeout: cannot swallow a timeout (${timeout.source}). A target that never ${receiver.name === 'waitFor' ? `reaches '${state}'` : 'arrives'} fails at the test timeout instead of passing silently; only non-timeout errors such as a strict-mode violation or a closed page reach the catch, so this is a diagnostics issue at most. ` :
      timeout.effective === 'none' ? `; no finite timeout (${timeout.source}), but ${receiver.name} can still reject at once on a non-timeout failure` :
      `; effective timeout unknown (${timeout.reason}): establish a finite timeout before treating this as a silent pass`;
    return { shape: 'swallowed-wait', target: clip(target), ...(state ? { state } : {}), reassertedLines: reasserted, laterAssertions: later,
      timeout: { ...timeout, ...(inert ? { inert: true } : {}) }, hint: inert ? timeoutHint + hint : hint + timeoutHint, probe };
  }
  // F: the `.catch` result is what an awaited `expect.poll` callback returns,
  // and its literal fallback cannot satisfy the literal matcher, so a
  // persistent error keeps the poll failing until it times out.
  function pollFallback(call) {
    const fallback = literalFallback(call);
    if (!fallback) return false;
    let value = skipParens(call);
    if (ts.isAwaitExpression(value.parent)) value = skipParens(value.parent);
    let callback = value.parent;
    if (ts.isReturnStatement(callback)) {
      callback = callback.parent;
      while (callback && !ts.isFunctionLike(callback)) callback = callback.parent;
    } else if (!((ts.isArrowFunction(callback) || ts.isFunctionExpression(callback)) && callback.body === value)) return false;
    if (!callback || !(ts.isArrowFunction(callback) || ts.isFunctionExpression(callback)) || callback.asteriskToken) return false;
    const poll = skipParens(callback).parent;
    if (!ts.isCallExpression(poll) || poll.questionDotToken || poll.arguments[0] !== skipParens(callback) && unwrap(poll.arguments[0]) !== callback ||
        poll.arguments.length > 2) return false;
    const pollAccess = dot(poll.expression);
    if (!pollAccess || pollAccess.name.text !== 'poll' || !ts.isIdentifier(unwrap(pollAccess.expression)) ||
        quietKind(pollAccess.expression) !== 'expect') return false;
    let chain = skipParens(poll).parent, negated = false;
    if (ts.isPropertyAccessExpression(chain) && chain.name.text === 'not' && !chain.questionDotToken) { negated = true; chain = skipParens(chain).parent; }
    if (!ts.isPropertyAccessExpression(chain) || chain.questionDotToken) return false;
    const matcher = chain.name.text, assertion = chain.parent;
    if (!ts.isCallExpression(assertion) || assertion.expression !== chain || assertion.questionDotToken || !assertion.arguments.length ||
        assertion.arguments.length > 2 || !ts.isAwaitExpression(skipParens(assertion).parent)) return false;
    const expected = primitiveLiteral(assertion.arguments[0]);
    if (!expected) return false;
    const F = fallback.value, V = expected.value;
    if (['toBe', 'toEqual', 'toStrictEqual'].includes(matcher)) return negated ? Object.is(F, V) : !Object.is(F, V) && F !== V;
    if (matcher === 'toBeGreaterThan' && !negated) return typeof V === 'number' && (typeof F !== 'number' || F <= V);
    return false;
  }
  function abruptFinally(block) {
    let abrupt = false;
    (function visit(node) {
      if (abrupt || node !== block && ts.isFunctionLike(node)) return;
      if (ts.isReturnStatement(node) || ts.isBreakStatement(node) || ts.isContinueStatement(node)) abrupt = true;
      ts.forEachChild(node, visit);
    })(block);
    return abrupt;
  }
  function hasCleanup(call) {
    let found = false;
    walk(call, node => {
      if (!ts.isCallExpression(node)) return;
      const expression = unwrap(node.expression), access = member(expression);
      if ((ts.isIdentifier(expression) && ['rm','unlink'].includes(expression.text)) ||
        (access && ts.isIdentifier(unwrap(access.object)) && unwrap(access.object).text === 'fs' && ['rm','unlink'].includes(access.name))) found = true;
    });
    return found;
  }
  function returnedRejection(node) {
    node = unwrap(node);
    if (ts.isAwaitExpression(node)) node = unwrap(node.expression);
    if (!ts.isCallExpression(node)) return false;
    const access = member(node.expression);
    return access?.name === 'reject' && ts.isIdentifier(unwrap(access.object)) && unwrap(access.object).text === 'Promise';
  }
  // Local completion proof only; do not infer helper callers or outer handling.
  function trivialRethrow(clause) {
    if (!ts.isTryStatement(clause.parent) || clause.parent.finallyBlock ||
        !clause.variableDeclaration || !ts.isIdentifier(clause.variableDeclaration.name) ||
        clause.block.statements.length !== 1) return false;
    const line = clause.block.statements[0];
    if (!ts.isThrowStatement(line) || !line.expression || !ts.isIdentifier(line.expression) ||
        line.expression.text !== clause.variableDeclaration.name.text) return false;
    for (let parent = clause.parent; parent; parent = parent.parent) {
      if (ts.isFunctionLike(parent)) return !parent.asteriskToken;
    }
    return true;
  }
  // Only prove simple lexical all-path throws. A return before the final throw
  // can resolve the catch; a nested callback throw says nothing about this one.
  // Promise.reject needs additional global/mutation proof and stays a gap.
  function outcomes(statement) {
    if (ts.isThrowStatement(statement)) return new Set(['throw']);
    if (ts.isReturnStatement(statement)) return new Set([
      statement.expression && returnedRejection(statement.expression) ? 'unknown' : 'return',
    ]);
    if (ts.isBlock(statement)) {
      const result = new Set(['next']);
      for (const child of statement.statements) {
        if (!result.delete('next')) break;
        for (const value of outcomes(child)) result.add(value);
      }
      return result;
    }
    if (ts.isIfStatement(statement)) return new Set([
      ...outcomes(statement.thenStatement),
      ...(statement.elseStatement ? outcomes(statement.elseStatement) : ['next']),
    ]);
    if (ts.isExpressionStatement(statement) || ts.isVariableStatement(statement) ||
        ts.isEmptyStatement(statement) || ts.isFunctionDeclaration(statement)) return new Set(['next']);
    return new Set(['unknown']);
  }
  if (!runtimeFramework) {
    walk(source, node => {
      if (ts.isTryStatement(node)) typedHelperTry(node);
      if (ts.isCallExpression(node)) typedPomCatch(node);
    });
    return { findings, diagnostics };
  }
  walk(source, node => {
    if (ts.isTryStatement(node)) {
      directTry(node); dependentTry(node); responseTry(node); synchronousTry(node); typedHelperTry(node); timeoutTry(node); namedErrorTry(node); sourceCatchOutcome(node); cypressManualTry(node);
    }
    if (ts.isCatchClause(node)) {
      // This catch alone preserves the same thrown value. Outer catch/finally
      // constructs are still visited and keep their independent evidence.
      if (!supported.has(node) && !trivialRethrow(node)) diagnostic(node, 'unsupported #3 try/catch propagation context');
      return;
    }
    // A finally that completes normally rethrows the pending error after it
    // runs, so it can only swallow through return, break or continue.
    if (ts.isTryStatement(node) && node.finallyBlock && !supported.has(node.finallyBlock) && !abruptFinally(node.finallyBlock)) supported.add(node.finallyBlock);
    if (ts.isTryStatement(node) && node.finallyBlock && !supported.has(node.finallyBlock)) diagnostic(node.finallyBlock, 'unsupported #3 finally context');
    if (!ts.isCallExpression(node)) return;
    const callee = unwrap(node.expression), access = member(callee);
    if (access?.name === 'allSettled' && ts.isIdentifier(unwrap(access.object)) && unwrap(access.object).text === 'Promise') {
      // Stored/returned results may be checked elsewhere. A diagnostic is not
      // a swallowing finding or a claim that those paths preserve failure.
      if (!discardedSettled(node)) diagnostic(node, 'unsupported #3 Promise.allSettled context');
      return;
    }
    if (access?.name !== 'catch') return;
    if (typedPomCatch(node)) return;
    if (!ts.isPropertyAccessExpression(callee) || callee.questionDotToken || node.arguments.length !== 1) {
      diagnostic(node, 'unsupported #3 catch access or argument layout'); return;
    }
    const callback = unwrap(node.arguments[0]);
    if (!(ts.isArrowFunction(callback) || ts.isFunctionExpression(callback))) {
      diagnostic(node, 'unsupported #3 non-inline catch handler'); return;
    }
    // Parenthesized callback expressions and generators are not in the legacy
    // direct callback regex. No receiver spelling proves Promise semantics.
    if (callback !== node.arguments[0] || callback.asteriskToken) {
      diagnostic(node, 'unsupported #3 callback syntax'); return;
    }
    const start = callee.name.getStart(source), position = source.getLineAndCharacterOfPosition(start);
    const endPosition = source.getLineAndCharacterOfPosition(node.end);
    if (endPosition.line - position.line > 12) {
      diagnostic(node, 'catch callback exceeds legacy 12-line lookahead'); return;
    }
    if (hasCleanup(node) || trailingCleanup(node) || reverifiedWait(node) || collectedErrors(node) || observedOriginalAwait(node)) return;
    if (animationSettle(node) || teardownCatch(node) || pollFallback(node) || messageOnlyBody(node)) return;
    const parameterized = callback.parameters.length > 0;
    if (parameterized) {
      if (callback.parameters.length !== 1 || !ts.isIdentifier(callback.parameters[0].name) ||
          callback.parameters[0].dotDotDotToken || callback.parameters[0].initializer) {
        diagnostic(callback, 'unsupported #3 parameterized catch binding layout'); return;
      }
      const propagation = ts.isBlock(callback.body) ? outcomes(callback.body) :
        new Set([returnedRejection(callback.body) ? 'unknown' : 'return']);
      if (propagation.size === 1 && propagation.has('throw')) return;
      if (propagation.has('unknown')) {
        diagnostic(callback, 'unsupported #3 parameterized catch propagation context'); return;
      }
    }
    const variant = parameterized ? 'parameterized' :
      ts.isBlock(callback.body) && callback.body.statements.length === 0 ? 'empty' : 'fallback';
    const triage = swallowedWaitTriage(node);
    // A provably no-timeout swallowed wait cannot silently pass: P2 diagnostics.
    findings.push({ patternId: '#3', severity: triage?.timeout.inert ? 'P2' : 'P0', disposition: 'candidate', origin: 'ast', variant,
      file: filename, line: position.line + 1, column: position.character + 1, start, end: node.end, ...(triage ? { triage } : {}) });
    if (variant === 'fallback' && !triage && discardedFallback(node)) demoteToReviewHint(findings.at(-1), 'discarded-fallback');
  });
  return { findings, diagnostics };
}
