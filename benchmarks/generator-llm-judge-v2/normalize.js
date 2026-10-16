#!/usr/bin/env node
// Meaning-preserving normaliser for generator-llm-judge-v2 (M2).
// stdin : JSON {"parts":[{"label":"File 1","code":"..."}, ...]}
// stdout: JSON {"ok":bool,"problems":[...],"code":"<one merged file>","stats":{...}}
// Removes comments, blank lines and trailing whitespace; merges imports (deduplicated, sorted) and the bodies of all
// files into one file. Verified by comparing comment-free, location-free ASTs of the original bodies (imports
// excluded) with the AST of the merged body, and the union of imported bindings before and after.
const path = require("path");
const HERE = __dirname;
const BUNDLE = process.env.BABEL_BUNDLE ||
  path.resolve(HERE, "../../scripts/evals/fixtures/node_modules/playwright/lib/transform/babelBundle.js");
const { babelParse } = require(BUNDLE);

const DROP = new Set(["start", "end", "loc", "range", "extra", "leadingComments", "trailingComments", "innerComments", "comments", "errors", "tokens"]);

function parse(src) {
  const ast = babelParse(src, "x.ts", false);
  if (ast.errors && ast.errors.length) throw new Error("parse errors: " + ast.errors.length);
  return ast;
}

function stripComments(src, ast) {
  const cs = (ast.comments || []).slice().sort((a, b) => a.start - b.start);
  let out = "", pos = 0;
  for (const c of cs) {
    out += src.slice(pos, c.start) + (c.type === "CommentBlock" ? " " : "");
    pos = c.end;
  }
  return out + src.slice(pos);
}

function templateRanges(ast) {
  const r = [];
  (function walk(n) {
    if (!n || typeof n !== "object") return;
    if (Array.isArray(n)) return n.forEach(walk);
    if (n.type === "TemplateLiteral" || n.type === "TemplateElement") r.push([n.start, n.end]);
    for (const k of Object.keys(n)) if (!DROP.has(k)) walk(n[k]);
  })(ast.program);
  return r;
}

function squeeze(src) {
  const ast = parse(src);
  const tr = templateRanges(ast);
  const inTpl = (o) => tr.some(([s, e]) => o > s && o < e);
  const lines = src.split("\n");
  let off = 0, out = [];
  for (const l of lines) {
    const start = off;
    off += l.length + 1;
    if (inTpl(start)) { out.push(l); continue; }
    const t = l.replace(/[ \t]+$/, "");
    if (t.trim() === "") continue;
    out.push(t);
  }
  return out.join("\n");
}

function fingerprint(stmts) {
  const clean = (n) => {
    if (Array.isArray(n)) return n.map(clean);
    if (n && typeof n === "object") {
      const o = {};
      for (const k of Object.keys(n)) if (!DROP.has(k)) o[k] = clean(n[k]);
      // keep raw text of template quasis and string/numeric literal values through value/raw fields already in node
      return o;
    }
    return n;
  };
  return JSON.stringify(stmts.map(clean));
}

function importInfo(node) {
  return {
    source: node.source.value, kind: node.importKind || "value",
    specs: node.specifiers.map((s) => ({
      t: s.type, local: s.local.name,
      imported: s.type === "ImportSpecifier" ? (s.imported.name || s.imported.value) : null,
      kind: s.importKind || "value",
    })),
  };
}

function declaredNames(stmts) {
  const names = [];
  for (const s of stmts) {
    let d = s;
    if ((s.type === "ExportNamedDeclaration" || s.type === "ExportDefaultDeclaration") && s.declaration) d = s.declaration;
    if (d.type === "VariableDeclaration") for (const v of d.declarations) if (v.id.type === "Identifier") names.push(v.id.name);
    if ((d.type === "FunctionDeclaration" || d.type === "ClassDeclaration" || d.type === "TSInterfaceDeclaration" || d.type === "TSTypeAliasDeclaration" || d.type === "TSEnumDeclaration") && d.id) names.push(d.id.name);
  }
  return names;
}

function q(s) { return "'" + s.replace(/\\/g, "\\\\").replace(/'/g, "\\'") + "'"; }

function printImports(infos) {
  const bySrc = new Map();
  for (const i of infos) {
    const k = i.source + "|" + i.kind;
    if (!bySrc.has(k)) bySrc.set(k, { source: i.source, kind: i.kind, def: new Set(), ns: new Set(), named: new Map(), side: i.specs.length === 0 });
    const g = bySrc.get(k);
    if (i.specs.length) g.side = false;
    for (const s of i.specs) {
      if (s.t === "ImportDefaultSpecifier") g.def.add(s.local);
      else if (s.t === "ImportNamespaceSpecifier") g.ns.add(s.local);
      else g.named.set((s.kind === "type" ? "type " : "") + s.imported + " as " + s.local, s);
    }
  }
  const rel = (s) => (s.startsWith(".") ? 1 : 0);
  const groups = [...bySrc.values()].sort((a, b) => rel(a.source) - rel(b.source) || a.source.localeCompare(b.source) || a.kind.localeCompare(b.kind));
  const lines = [];
  for (const g of groups) {
    const kw = g.kind === "type" ? "import type " : "import ";
    if (g.side) { lines.push(`import ${q(g.source)};`); continue; }
    const bits = [];
    if (g.def.size) bits.push([...g.def].sort().join(", "));
    if (g.ns.size) bits.push("* as " + [...g.ns].sort().join(", "));
    if (g.named.size) {
      const ns = [...g.named.values()].map((s) => (s.kind === "type" ? "type " : "") + (s.imported === s.local ? s.local : `${s.imported} as ${s.local}`)).sort();
      bits.push("{ " + ns.join(", ") + " }");
    }
    lines.push(`${kw}${bits.join(", ")} from ${q(g.source)};`);
  }
  return lines;
}

function bindingSet(infos) {
  const s = new Set();
  for (const i of infos) {
    if (!i.specs.length) s.add(`${i.kind}|${i.source}|side`);
    for (const x of i.specs) s.add(`${i.kind}|${i.source}|${x.t}|${x.kind}|${x.imported}|${x.local}`);
  }
  return [...s].sort().join("\n");
}

function main(input) {
  const problems = [];
  const parts = input.parts;
  const origBodies = [], origImports = [], bodies = [];
  for (const p of parts) {
    let ast, code1, ast1;
    try { ast = parse(p.code); } catch (e) { return { ok: false, problems: [`${p.label}: ${e.message}`], code: null }; }
    origBodies.push(...ast.program.body.filter((n) => n.type !== "ImportDeclaration"));
    origImports.push(...ast.program.body.filter((n) => n.type === "ImportDeclaration").map(importInfo));
    code1 = stripComments(p.code, ast);
    try { ast1 = parse(code1); } catch (e) { return { ok: false, problems: [`${p.label}: after comment strip: ${e.message}`], code: null }; }
    let body = "", pos = 0;
    for (const n of ast1.program.body) if (n.type === "ImportDeclaration") { body += code1.slice(pos, n.start); pos = n.end; }
    body += code1.slice(pos);
    try { bodies.push(squeeze(body)); } catch (e) { return { ok: false, problems: [`${p.label}: after import removal: ${e.message}`], code: null }; }
  }
  const imports = printImports(origImports);
  const merged = (imports.length ? imports.join("\n") + "\n\n" : "") + bodies.filter((b) => b.trim()).join("\n\n") + "\n";
  let mast;
  try { mast = parse(merged); } catch (e) { return { ok: false, problems: ["merged file does not parse: " + e.message], code: null }; }
  const mbody = mast.program.body.filter((n) => n.type !== "ImportDeclaration");
  const mimports = mast.program.body.filter((n) => n.type === "ImportDeclaration").map(importInfo);
  if (fingerprint(origBodies) !== fingerprint(mbody)) problems.push("body AST differs after normalisation");
  if (bindingSet(origImports) !== bindingSet(mimports)) problems.push("import bindings differ after normalisation");
  const names = declaredNames(mbody);
  const dup = names.filter((n, i) => names.indexOf(n) !== i);
  if (dup.length) problems.push("duplicate top-level names after merge: " + [...new Set(dup)].join(","));
  const locals = {};
  for (const i of mimports) for (const s of i.specs) { if (locals[s.local] && locals[s.local] !== i.source) problems.push("local name imported from two sources: " + s.local); locals[s.local] = i.source; }
  if ((mast.comments || []).length) problems.push("comments remain after normalisation: " + mast.comments.length);
  const relImports = mimports.filter((i) => i.source.startsWith(".")).length;
  return { ok: problems.length === 0, problems, code: merged, stats: { files_in: parts.length, relative_imports_after: relImports } };
}

let buf = "";
process.stdin.on("data", (d) => (buf += d));
process.stdin.on("end", () => process.stdout.write(JSON.stringify(main(JSON.parse(buf)))));
