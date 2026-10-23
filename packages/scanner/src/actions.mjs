// SPDX-License-Identifier: Apache-2.0
// Bounded raw #5b force-option slice. Caller owns suppression and accounting.
import { member, unwrap, ts, walk } from './source.mjs';
import { createReceivers } from './receivers.mjs';
import { createCypressChains } from './cypress-chain-aliases.mjs';

const OPTIONS = new Map(Object.entries({click:0,dblclick:0,tap:0,fill:1,clear:0,type:1,press:1,
  pressSequentially:1,check:0,uncheck:0,setChecked:1,selectOption:1,setInputFiles:1,
  hover:0,focus:0,dragTo:1,drop:1,dispatchEvent:2,scrollIntoViewIfNeeded:0,selectText:0}));
const CYPRESS_REQUIRED = new Map(Object.entries({click:0,dblclick:0,type:1,press:1,clear:0,
  check:0,uncheck:0,focus:0}));

export function actions(bytes, filename, {scope} = {}) {
  const receivers = createReceivers(bytes, filename, {scope});
  if (receivers.diagnostics.length) return {findings:[],diagnostics:receivers.diagnostics};
  if (!scope) return {findings:[],diagnostics:[{message:'pinned project scope is required for action provenance'}]};
  const {source}=receivers;
  const findings=[], diagnostics=[];
  const chains = createCypressChains({ source, checker: receivers.checker, scope, filename });
  walk(source,node=>{
    if (!ts.isCallExpression(node) || node.questionDotToken) return;
    const method=member(node.expression);
    if (!method || !ts.isPropertyAccessExpression(node.expression) || node.expression.questionDotToken || !OPTIONS.has(method.name)) return;
    let options;
    const cypress=CYPRESS_REQUIRED.has(method.name) ? chains.expression(method.object) : null;
    if (cypress && !cypress.complete) {diagnostics.push({message:cypress.reasons.join('; ')});return;}
    if (cypress?.kind==='cypress-runtime') {
      if (node.arguments.length<=CYPRESS_REQUIRED.get(method.name)) return;
      options=node.arguments.at(-1);
    } else {
      const receiver=receivers.expression(method.object);
      if (!receiver.complete) {diagnostics.push({message:receiver.reasons.join('; ')});return;}
      if (!['page','locator'].includes(receiver.kind)) return;
      const index=OPTIONS.get(method.name)+Number(receiver.kind==='page');
      options=node.arguments[index];
      if (!options) return;
    }
    options=unwrap(options);
    if (!ts.isObjectLiteralExpression(options)) {
      // Cypress positional coordinates/values are ordinary arguments. A
      // variable in the options position remains unresolved rather than clean.
      if (ts.isStringLiteral(options) || ts.isNumericLiteral(options)) return;
      diagnostics.push({message:'force option requires a literal options object'});return;
    }
    const entries=options.properties.filter(property=>ts.isPropertyAssignment(property) &&
      (ts.isIdentifier(property.name)||ts.isStringLiteral(property.name)) && property.name.text==='force');
    if (options.properties.some(ts.isSpreadAssignment) || entries.length>1) {
      diagnostics.push({message:'spread or duplicate force prevents proven action options'});return;
    }
    if (!entries.length) return;
    const entry=entries[0], value=unwrap(entry.initializer);
    if (value.kind===ts.SyntaxKind.FalseKeyword) return;
    if (value.kind!==ts.SyntaxKind.TrueKeyword) {
      diagnostics.push({message:'dynamic force option is outside the literal-true slice'});return;
    }
    const start=entry.name.getStart(source), position=source.getLineAndCharacterOfPosition(start);
    const actionLine=source.getLineAndCharacterOfPosition(node.expression.name.getStart(source)).line;
    if (position.line-actionLine>8) {
      diagnostics.push({message:'force option exceeds legacy eight-line lookback'});return;
    }
    // Legacy reports a location per physical force-property line.
    if (!findings.some(finding=>finding.line===position.line+1)) findings.push({patternId:'#5b',severity:'P1',
      disposition:'confirmed',origin:'ast',file:filename,line:position.line+1,column:position.character+1,start,end:entry.end});
  });
  return {findings,diagnostics:[...new Map(diagnostics.map(item=>[item.message,item])).values()]};
}
