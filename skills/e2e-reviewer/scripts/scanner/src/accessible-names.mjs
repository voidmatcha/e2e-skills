// SPDX-License-Identifier: Apache-2.0
// Bounded raw #10c P1 candidates. Dynamic-content collisions and container scope
// require semantic review. Preserve legacy page/cy direct spelling, same-line
// calls, and its exclusion of any explicit exact property (including false).
// Do not reinterpret Cypress string names as substring matching. Legacy's
// Cypress regex slice excludes any leading ^, not only fully anchored regexes.
import {createReceivers} from './receivers.mjs';
import {unwrap, walk, ts} from './source.mjs';
const PW_METHODS = new Set(['getByRole','getByLabel','getByPlaceholder']);
export function accessibleNames(bytes, filename, {scope} = {}) {
  const receivers=createReceivers(bytes,filename,{scope}),{source}=receivers;
  const findings=[],diagnostics=[...receivers.diagnostics];
  if(diagnostics.length)return {findings,diagnostics};
  if(!scope)return {findings,diagnostics:[{message:'pinned scope is required for accessible-name provenance'}]};
  function diagnostic(node,message){const start=node.getStart(source);diagnostics.push({start,length:node.end-start,message});}
  walk(source,node=>{
    if(!ts.isCallExpression(node)||node.questionDotToken)return;
    const callee=unwrap(node.expression);
    if(!ts.isPropertyAccessExpression(callee)||callee.questionDotToken)return;
    const receiver=unwrap(callee.expression),method=callee.name.text;
    if(!ts.isIdentifier(receiver))return;
    const pw=receiver.text==='page'&&PW_METHODS.has(method),cy=receiver.text==='cy'&&method==='findByRole';
    if(!pw&&!cy)return;
    const proof=cy?scope.cypressGlobal(filename,receiver):receivers.expression(receiver);
    if(!proof.complete){diagnostic(receiver,proof.reasons.join('; '));return;}
    if(proof.kind!==(cy?'cypress-runtime':'page'))return;
    if(node.arguments.length<2)return;
    if(node.arguments.length!==2||node.arguments.some(ts.isSpreadElement)){
      diagnostic(node,'accessible-name call signature is outside the direct two-argument slice');return;
    }
    const options=unwrap(node.arguments[1]);
    if(!ts.isObjectLiteralExpression(options)){diagnostic(options,'accessible-name options require a direct literal object');return;}
    if(options.properties.some(p=>ts.isSpreadAssignment(p)||p.name&&ts.isComputedPropertyName(p.name))){
      diagnostic(options,'spread/computed accessible-name options are unresolved');return;
    }
    const properties=name=>options.properties.filter(p=>p.name&&p.name.text===name);
    const names=properties('name'),exact=properties('exact');
    if(names.length>1||exact.length>1||[...names,...exact].some(p=>!ts.isPropertyAssignment(p))){
      diagnostic(options,'duplicate/accessor accessible-name options are unresolved');return;
    }
    if(!names.length)return;
    const name=unwrap(names[0].initializer);
    if(!ts.isStringLiteral(name)&&!ts.isRegularExpressionLiteral(name)){
      diagnostic(name,'dynamic accessible name is outside the literal-name slice');return;
    }
    if(pw&&exact.length){
      if(![ts.SyntaxKind.TrueKeyword,ts.SyntaxKind.FalseKeyword].includes(unwrap(exact[0].initializer).kind))
        diagnostic(exact[0],'dynamic exact option is unresolved');
      return;
    }
    if(cy){
      if(!ts.isRegularExpressionLiteral(name))return;
      // Exact existing discovery shape: an unescaped slash or ) in the regex
      // is outside the legacy same-line regex, not a new AST expansion.
      if(name.text.startsWith('/^'))return;
      if(!/^\/[^/\n)]+\/[a-z]*$/.test(name.text)){diagnostic(name,'regex is outside legacy Cypress discovery');return;}
    }
    const start=callee.getStart(source),position=source.getLineAndCharacterOfPosition(start);
    if(source.getLineAndCharacterOfPosition(node.end).line!==position.line||
       source.text.slice(callee.end+1,node.end-1).includes(')')){
      diagnostic(node,'accessible-name call is outside legacy same-line discovery');return;
    }
    const raw=source.text.slice(start,node.end);
    const legacyShape=pw ? /^page\.(getByRole|getByLabel|getByPlaceholder)\((?:(?!exact:)[^)])*name:(?:(?!exact:)[^)])*\)$/.test(raw) :
      /^cy\.findByRole\([^\n)]*\bname\s*:\s*\/(?!\^)[^/\n]+\/[a-z]*\s*[,}]/.test(raw);
    if(!legacyShape){diagnostic(node,'accessible-name spelling is outside legacy discovery');return;}
    if(!findings.some(f=>f.line===position.line+1))findings.push({patternId:'#10c',severity:'P1',disposition:'candidate',
      origin:'ast',file:filename,line:position.line+1,column:position.character+1,start,end:node.end});
  });
  return {findings,diagnostics};
}
