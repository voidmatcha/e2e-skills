// SPDX-License-Identifier: Apache-2.0
// Pure pinned-source observations; kept separate from standalone FS discovery.
import path from 'node:path';
import {createScope} from './scope.mjs';
const FRAMEWORK= ['playwright','cypress'].flatMap(name=>['ts','js','mts','mjs','cts','cjs'].map(ext=>`${name}.config.${ext}`));
const ESLINT=['eslint.config.mjs','eslint.config.js','eslint.config.cjs','.eslintrc','.eslintrc.json','.eslintrc.js','.eslintrc.cjs','.eslintrc.yml','.eslintrc.yaml'];
const category=name=>FRAMEWORK.includes(name)?'framework':ESLINT.includes(name)?'eslint':name==='package.json'?'package':null;

// This API observes only the supplied inventory: not-observed never means absent.
export function projectContext({manifest,sources}={}){
  const check=createScope({manifest,sources}).validate();
  if(!check.complete)return {schema:'node-pinned-project-context-v1',snapshotValid:false,discoveryComplete:false,observations:[],diagnostics:[{code:'invalid-pinned-snapshot'}]};
  return {schema:'node-pinned-project-context-v1',snapshotValid:true,discoveryComplete:false,
    observations:manifest.candidates.filter(item=>category(path.basename(item.path))).map(item=>({path:item.path,
      directory:path.dirname(item.path),kind:category(path.basename(item.path)),sha256:item.identity.sha256})),
    diagnostics:[{code:'pinned-candidates-only',detail:'Non-code markers and ancestors are not covered by this observation.'}]};
}
