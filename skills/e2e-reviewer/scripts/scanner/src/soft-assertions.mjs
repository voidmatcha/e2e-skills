// SPDX-License-Identifier: Apache-2.0
// Raw #18 semantic candidates, never a verdict based on soft-call counts.
// Preserve legacy's unawaited physical-line-start discovery boundary. Proven
// awaited/returned/inline/multiline calls are coverage-gap diagnostics only.
// Independent terminal details remain legitimate; review must prove a critical
// prerequisite and dependent work without an intervening hard gate.
// Configured expect calls, optional/computed access and extracted soft aliases
// are outside this direct-call slice. Suppression belongs to the caller.
import { sourceModel, unwrap, walk, ts } from './source.mjs';

export function softAssertions(bytes, filename, {scope} = {}) {
  const {source, diagnostics: parseErrors} = sourceModel(bytes, filename);
  const findings = [], diagnostics = [...parseErrors];
  if (diagnostics.length) return {findings, diagnostics};
  if (!scope) return {findings, diagnostics:[{message:'pinned scope is required for soft-assertion provenance'}]};
  walk(source, node => {
    if (!ts.isCallExpression(node) || node.questionDotToken) return;
    const callee = unwrap(node.expression);
    if (!ts.isPropertyAccessExpression(callee) || callee.questionDotToken || callee.name.text !== 'soft') return;
    const binding = scope.expression(filename, callee.expression);
    if (!binding.complete) {
      const start = callee.expression.getStart(source);
      diagnostics.push({start,length:callee.expression.end-start,message:binding.reasons.join('; ')});
      return;
    }
    if (binding.kind !== 'playwright-expect') return;
    if (node.arguments.length < 1 || node.arguments.length > 2 || node.arguments.some(ts.isSpreadElement)) {
      const start = node.getStart(source);
      diagnostics.push({start,length:node.end-start,message:'soft assertion call signature is outside the direct-call slice'});
      return;
    }
    const start = callee.getStart(source), position = source.getLineAndCharacterOfPosition(start);
    const lineStart = source.getPositionOfLineAndCharacter(position.line,0);
    const prefix = source.text.slice(lineStart,start);
    const opening = source.text.slice(start,node.arguments.pos);
    if (!/^[ \t\r]*$/.test(prefix) ||
        !/^[A-Za-z_$][A-Za-z0-9_$]*(?:[ \t]*\.[ \t]*expect)?[ \t]*\.[ \t]*soft[ \t]*\([ \t]*$/.test(opening)) {
      diagnostics.push({start,length:node.end-start,message:'soft assertion is outside legacy unawaited physical-line-start discovery; semantic review required'});
      return;
    }
    findings.push({patternId:'#18',severity:'P1',disposition:'candidate',origin:'ast',file:filename,
      line:position.line+1,column:position.character+1,start,end:node.end});
  });
  return {findings,diagnostics};
}
