// SPDX-License-Identifier: Apache-2.0
// Experimental trusted-project bridge. Not imported by the product CLI.
import fs from 'node:fs';
import path from 'node:path';
import {createRequire} from 'node:module';
import {pathToFileURL} from 'node:url';
import {spawnSync} from 'node:child_process';
import {createHash} from 'node:crypto';

export function runLocalEslint({projectRoot, files, workDir, framework='playwright',
  trustProjectCode=false, timeoutMs=30_000, maxOutputBytes=1024*1024}={}) {
  // Deliberately before path resolution, package inspection, and workdir creation.
  if (trustProjectCode !== true) return {status:'skipped', reason:'project-code-execution-not-authorized', executed:false};
  if (framework !== 'playwright') return {status:'unsupported', reason:'this canary only implements Playwright', executed:false};
  if (!Number.isInteger(timeoutMs) || timeoutMs<1 || timeoutMs>300_000 ||
      !Number.isInteger(maxOutputBytes) || maxOutputBytes<1 || maxOutputBytes>8*1024*1024) throw new TypeError('invalid execution limits');
  const root=fs.realpathSync(projectRoot), modules=path.join(root,'node_modules');
  if (!Array.isArray(files) || !files.length) throw new TypeError('explicit framework-proven files required');
  const targets=files.map(file=>{
    const resolved=fs.realpathSync(file), relative=path.relative(root,resolved);
    if (!relative || relative.startsWith('..'+path.sep) || path.isAbsolute(relative) ||
        !/\.(?:ts|tsx|js|jsx|mts|mjs|cts|cjs)$/.test(resolved) ||
        relative.split(path.sep).some(part=>['node_modules','.git','dist','build','.next','out','coverage','playwright-report','test-results'].includes(part)) ||
        /\.min\.(?:js|ts)$/.test(resolved)) throw new TypeError('target outside supported source boundary');
    return resolved;
  });
  const binary=path.join(modules,'.bin','eslint');
  try {fs.accessSync(binary,fs.constants.X_OK);} catch {return {status:'skipped',reason:'local-eslint-unavailable',executed:false};}
  const require=createRequire(path.join(root,'package.json'));
  const identities={};
  function resolveLocal(name) {
    const packageDir=fs.realpathSync(path.join(modules,name));
    const resolved=fs.realpathSync(require.resolve(name));
    const relative=path.relative(packageDir,resolved);
    if (relative.startsWith('..'+path.sep) || path.isAbsolute(relative)) throw new Error('nonlocal module resolution: '+name);
    identities[name]={entry:resolved,sha256:createHash('sha256').update(fs.readFileSync(resolved)).digest('hex')};
    return pathToFileURL(resolved).href;
  }
  let plugin,parser;
  try {plugin=resolveLocal('eslint-plugin-playwright');parser=resolveLocal('@typescript-eslint/parser');}
  catch(error) {return {status:'skipped',reason:'local-plugin-or-parser-unavailable',detail:error.message,executed:false};}
  // Exact executable from this project's existing local tree; no npm/npx calls.
  identities.eslint={entry:fs.realpathSync(binary),sha256:createHash('sha256').update(fs.readFileSync(binary)).digest('hex')};
  if (fs.existsSync(workDir)) throw new Error('workDir must be new');
  fs.mkdirSync(workDir,{recursive:true});
  for (const name of ['home','tmp','config','cache']) fs.mkdirSync(path.join(workDir,name));
  const projectConfig=['eslint.config.mjs','eslint.config.js','eslint.config.cjs'].map(name=>path.join(root,name)).find(file=>fs.existsSync(file));
  const config=path.join(workDir,'eslint.config.mjs');
  fs.writeFileSync(config,`import playwright from ${JSON.stringify(plugin)};\nimport parser from ${JSON.stringify(parser)};\n`+
    (projectConfig?`import projectConfig from ${JSON.stringify(pathToFileURL(projectConfig).href)};\n`:'')+
    `export default [ {ignores:['**/node_modules/**','**/dist/**','**/build/**','**/.next/**','**/out/**','**/coverage/**','**/*.min.js','**/*.min.ts']},\n`+
    `{files:['**/*.{ts,tsx,js,jsx,mts,mjs,cts,cjs}'],plugins:{playwright},languageOptions:{parser,ecmaVersion:'latest',sourceType:'module',parserOptions:{ecmaFeatures:{jsx:true}}},rules:{...(playwright.configs['flat/recommended']??playwright.configs.recommended).rules}},\n`+
    (projectConfig?'...(Array.isArray(projectConfig)?projectConfig:[projectConfig]),\n':'')+'];\n');
  const env={PATH:path.dirname(process.execPath)+':/usr/bin:/bin:/usr/sbin:/sbin',HOME:path.join(workDir,'home'),
    TMPDIR:path.join(workDir,'tmp'),TMP:path.join(workDir,'tmp'),TEMP:path.join(workDir,'tmp'),
    XDG_CONFIG_HOME:path.join(workDir,'config'),XDG_CACHE_HOME:path.join(workDir,'cache'),
    npm_config_userconfig:path.join(workDir,'empty.npmrc'),npm_config_globalconfig:path.join(workDir,'global.npmrc'),
    npm_config_cache:path.join(workDir,'cache'),npm_config_offline:'true',npm_config_ignore_scripts:'true',
    CI:'1',NO_COLOR:'1',LANG:'C',LC_ALL:'C',ESLINT_USE_FLAT_CONFIG:'true'};
  fs.writeFileSync(env.npm_config_userconfig,'');fs.writeFileSync(env.npm_config_globalconfig,'');
  const result=spawnSync(binary,['--no-config-lookup','--no-error-on-unmatched-pattern','-c',config,'--format','json','--',...targets],
    {cwd:root,env,encoding:'utf8',timeout:timeoutMs,maxBuffer:maxOutputBytes,killSignal:'SIGKILL',shell:false});
  // Node can capture a final pipe chunk beyond maxBuffer before terminating.
  // Bound retained evidence per stream too, rather than retaining that overshoot.
  const bounded=value=>{
    let text=Buffer.from(value??'').subarray(0,maxOutputBytes).toString('utf8');
    while(Buffer.byteLength(text)>maxOutputBytes) text=text.slice(0,-1);
    return text;
  };
  const stdout=bounded(result.stdout),stderr=bounded(result.stderr);
  let messages=null;
  try {messages=JSON.parse(stdout);} catch {}
  const complete=!result.error && [0,1].includes(result.status) && Array.isArray(messages);
  return {status:complete?'complete':'incomplete',executed:true,exitCode:result.status,signal:result.signal,
    error:result.error?.message,stdout,stderr,messages,identities,
    projectConfig:projectConfig??null,targets,envKeys:Object.keys(env),configSha256:createHash('sha256').update(fs.readFileSync(config)).digest('hex')};
}
