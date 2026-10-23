// SPDX-License-Identifier: Apache-2.0
// Marker discovery only. Never executes or parses project configuration.
import fs from 'node:fs';
import path from 'node:path';
import {createHash} from 'node:crypto';
const FRAMEWORK= ['playwright','cypress'].flatMap(name=>['ts','js','mts','mjs','cts','cjs'].map(ext=>`${name}.config.${ext}`));
const PROJECT=['package.json',...FRAMEWORK];
const SELF=['AGENTS.md','skills/e2e-reviewer/SKILL.md','scripts/ci/test-reviewer-scanner.py'];
const ESLINT=['eslint.config.mjs','eslint.config.js','eslint.config.cjs','eslint.config.ts','eslint.config.mts','eslint.config.cts','.eslintrc','.eslintrc.json','.eslintrc.js','.eslintrc.cjs','.eslintrc.yml','.eslintrc.yaml'];
const FIELDS=['dev','ino','mode','size','mtimeNs','ctimeNs'];
const identity=s=>Object.fromEntries(FIELDS.map(key=>[key,String(s[key])]));
const same=(a,b)=>FIELDS.every(key=>a[key]===b[key]);
// Unrelated children may change directory timestamps; marker presence is
// checked separately. Identity still rejects a persistent directory swap.
const directoryIdentity=s=>Object.fromEntries(['dev','ino','mode'].map(key=>[key,String(s[key])]));
const sameDirectory=(a,b)=>['dev','ino','mode'].every(key=>a[key]===b[key]);


function observe(file,{git=false}={}){
  let stat;
  try{stat=fs.lstatSync(file,{bigint:true});}catch(error){if(error.code==='ENOENT')return {path:file,kind:'absent'};throw error;}
  if(stat.isSymbolicLink())throw new Error(`symbolic-link marker: ${file}`);
  if(git&&stat.isDirectory())return {path:file,kind:'directory',identity:directoryIdentity(stat)};
  if(!stat.isFile())throw new Error(`non-regular marker: ${file}`);
  const parent=path.dirname(file),parentBefore=directoryIdentity(fs.statSync(parent,{bigint:true}));
  function guard(){
    if(fs.realpathSync(parent)!==parent||!sameDirectory(parentBefore,directoryIdentity(fs.statSync(parent,{bigint:true}))))throw new Error(`marker parent drift: ${file}`);
  }
  guard();
  if(fs.constants.O_NOFOLLOW===undefined)throw new Error('O_NOFOLLOW unavailable');
  const fd=fs.openSync(file,fs.constants.O_RDONLY|fs.constants.O_NOFOLLOW|fs.constants.O_NONBLOCK);
  try{
    guard();const before=fs.fstatSync(fd,{bigint:true});
    if(!before.isFile()||!same(identity(stat),identity(before)))throw new Error(`marker identity drift: ${file}`);
    if(before.size>16n*1024n*1024n)throw new Error(`marker exceeds 16 MiB: ${file}`);
    const digest=createHash('sha256'),buffer=Buffer.alloc(65536);let count,total=0;
    while((count=fs.readSync(fd,buffer))!==0){total+=count;if(total>16*1024*1024)throw new Error(`marker exceeds 16 MiB: ${file}`);digest.update(buffer.subarray(0,count));}
    if(!same(identity(before),identity(fs.fstatSync(fd,{bigint:true})))||!same(identity(before),identity(fs.lstatSync(file,{bigint:true}))))throw new Error(`marker changed while reading: ${file}`);
    guard();return {path:file,kind:'file',identity:identity(before),sha256:digest.digest('hex')};
  }finally{fs.closeSync(fd);}
}
function requestedRoot(requested){
  const lexical=path.resolve(requested),stat=fs.lstatSync(lexical,{bigint:true});
  if(stat.isSymbolicLink()||!stat.isDirectory()&&!stat.isFile())throw new Error('requested scope must be a regular file or directory, not a symbolic link');
  const canonical=fs.realpathSync(lexical);
  if(lexical!==canonical)throw new Error('symbolic-link ancestor in requested scope');
  return {requested:lexical,canonical,kind:stat.isDirectory()?'directory':'file',identity:stat.isDirectory()?directoryIdentity(stat):identity(stat)};
}
export function discoverProjectContext(requested){
  const result={schema:'node-project-context-discovery-v1',complete:false,requested:null,scanRoot:null,projectRoot:null,
    selection:null,selfRepository:false,selfRepositoryScope:false,markers:[],boundaries:[],diagnostics:[]};
  try{
    const initial=requestedRoot(requested);result.requested=initial;
    const scanRoot=initial.kind==='directory'?initial.canonical:path.dirname(initial.canonical);result.scanRoot=scanRoot;
    const observations=new Map(),directories=new Map();
    function directory(dir){
      while(!directories.has(dir)){
        let stat;
        try{stat=fs.lstatSync(dir,{bigint:true});}catch(error){if(error.code!=='ENOENT')throw error;const parent=path.dirname(dir);if(parent===dir)throw error;dir=parent;continue;}
        if(stat.isSymbolicLink()||!stat.isDirectory())throw new Error(`non-canonical marker parent: ${dir}`);
        directories.set(dir,directoryIdentity(stat));break;
      }
    }
    function marker(file,git=false){directory(path.dirname(file));if(!observations.has(file))observations.set(file,observe(file,{git}));return observations.get(file);}
    function projectMarkers(dir){return PROJECT.map(name=>marker(path.join(dir,name))).filter(item=>item.kind!=='absent');}
    let cursor=scanRoot,gitRoot=null;
    // Legacy prefers the nearest Git boundary anywhere above the scan scope.
    while(true){if(marker(path.join(cursor,'.git'),true).kind!=='absent'){gitRoot=cursor;break;}const parent=path.dirname(cursor);if(parent===cursor)break;cursor=parent;}
    let selected=gitRoot;
    cursor=scanRoot;
    while(true){
      const markers=projectMarkers(cursor);
      if(markers.length)result.boundaries.push({directory:cursor,markers:markers.map(item=>item.path)});
      if(!gitRoot&&markers.length){selected=cursor;break;}
      if(cursor===gitRoot)break;
      const parent=path.dirname(cursor);if(parent===cursor)break;cursor=parent;
    }
    result.projectRoot=selected||scanRoot;result.selection=gitRoot?'nearest-git':selected?'nearest-project-marker':'scan-root-fallback';
    for(const name of ESLINT)marker(path.join(result.projectRoot,name));
    const fingerprint=SELF.map(name=>marker(path.join(result.projectRoot,name)));
    result.selfRepository=fingerprint.every(item=>item.kind==='file');
    const nestedProject=result.boundaries.some(item=>item.directory!==result.projectRoot);
    const nestedGit=[...observations.values()].some(item=>path.basename(item.path)==='.git'&&item.kind!=='absent'&&path.dirname(item.path)!==result.projectRoot);
    result.selfRepositoryScope=result.selfRepository&&!nestedProject&&!nestedGit;
    // Pin absence as well as presence, so a new nearer marker is drift.
    for(const previous of observations.values()){
      const current=observe(previous.path,{git:path.basename(previous.path)==='.git'});
      if(JSON.stringify(previous)!==JSON.stringify(current))throw new Error(`marker drift: ${previous.path}`);
    }
    for(const[dir,before]of directories)if(fs.realpathSync(dir)!==dir||!sameDirectory(before,directoryIdentity(fs.statSync(dir,{bigint:true}))))throw new Error(`context directory drift: ${dir}`);
    if(JSON.stringify(initial)!==JSON.stringify(requestedRoot(requested)))throw new Error('requested scope drift');
    result.markers=[...observations.values()];result.complete=true;
  }catch(error){result.diagnostics.push({code:'project-context-incomplete',detail:error.message});}
  return result;
}
export function revalidateProjectContext(expected){
  if(expected?.schema!=='node-project-context-discovery-v1'||expected.complete!==true||typeof expected.requested?.requested!=='string')
    return {complete:false,diagnostics:[{code:'invalid-project-context-baseline'}]};
  const current=discoverProjectContext(expected.requested.requested);
  if(current.complete&&JSON.stringify(current)!==JSON.stringify(expected))return {complete:false,diagnostics:[{code:'project-context-drift'}]};
  return current;
}
