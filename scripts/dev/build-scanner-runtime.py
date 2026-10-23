#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Build/check the skill's source-only scanner; never install or download tools."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile

REPOSITORY = Path(__file__).resolve().parents[2]
VERSION = "6.0.3"
# SHA-256 of the original files in the exact TypeScript 6.0.3 npm artifact.
UPSTREAM = {
    "lib/typescript.js": "569177652966bd528c319171c7dd22860dbf72bde116cbc4f644f1d02bb12e39",
    "LICENSE.txt": "a7d00bfd54525bc694b6e32f64c7ebcf5e6b7ae3657be5cc12767bce74654a47",
    "ThirdPartyNoticeText.txt": "1af3c68039c57e539422da82a4faada506ce6d0ea6f90e0b699d02dbcdb7a90c",
}
VENDOR_PATHS = {
    "lib/typescript.js": "vendor/typescript/typescript.cjs",
    "LICENSE.txt": "vendor/typescript/LICENSE.txt",
    "ThirdPartyNoticeText.txt": "vendor/typescript/ThirdPartyNoticeText.txt",
}
OLD_IMPORT = b"import ts from 'typescript';"
NEW_IMPORT = b"import ts from '../vendor/typescript/typescript.cjs';"
NODE_PATHS = ("/opt/homebrew/bin/node", "/usr/local/bin/node", "/usr/bin/node", "/bin/node")

# The parser only sees source bytes supplied through stdin. It neither resolves
# project imports nor consults configuration. Verify its pinned bytes BEFORE Node.
CLOSURE = r"""
const fs = require('node:fs');
if (Number(process.versions.node.split('.')[0]) < 22) throw Error('Node.js 22+ is required');
const ts = require(process.argv[1]);
if (ts.version !== '6.0.3') throw Error('unexpected parser version');
const sources = JSON.parse(fs.readFileSync(0, 'utf8'));
const queue = ['cli.mjs'], seen = new Set(), edges = [];
while (queue.length) {
  const name = queue.shift();
  if (seen.has(name)) continue;
  if (!Object.hasOwn(sources, name)) throw Error('missing source module: ' + name);
  seen.add(name);
  const file = ts.createSourceFile(name, sources[name], ts.ScriptTarget.Latest, true);
  if (file.parseDiagnostics.length) throw Error('invalid source syntax: ' + name);
  function edge(literal) {
    if (!literal || !ts.isStringLiteral(literal)) throw Error('nonliteral import: ' + name);
    const specifier = literal.text;
    edges.push({from: name, specifier});
    if (specifier.startsWith('node:')) return;
    if (specifier === 'typescript' && name === 'source.mjs') return;
    if (!/^\.\/[a-zA-Z0-9_-]+\.mjs$/.test(specifier)) throw Error('unsupported dependency: ' + name);
    queue.push(specifier.slice(2));
  }
  function visit(node) {
    if ((ts.isImportDeclaration(node) || ts.isExportDeclaration(node)) && node.moduleSpecifier) edge(node.moduleSpecifier);
    if (ts.isCallExpression(node) && node.expression.kind === ts.SyntaxKind.ImportKeyword) {
      if (node.arguments.length !== 1) throw Error('unsupported import arguments: ' + name);
      edge(node.arguments[0]);
    }
    ts.forEachChild(node, visit);
  }
  visit(file);
}
process.stdout.write(JSON.stringify({files: [...seen].sort(), edges}));
"""


def digest(data):
    return hashlib.sha256(data).hexdigest()


def physical(path):
    value = Path(os.path.abspath(path))
    if value.resolve() != value:
        raise ValueError("symbolic-link path is unsupported: " + str(value))
    return value


def regular_bytes(path):
    if path.is_symlink() or not path.is_file():
        raise ValueError("missing or nonregular file: " + str(path))
    return path.read_bytes()


def vendor_files(dependency, output, write):
    result = {}
    for original, expected in UPSTREAM.items():
        selected = dependency / original if write else output / VENDOR_PATHS[original]
        data = regular_bytes(physical(selected))
        if digest(data) != expected:
            raise ValueError("TypeScript original hash mismatch: " + original)
        result[VENDOR_PATHS[original]] = data
    if write:
        metadata = json.loads(regular_bytes(dependency / "package.json"))
        if metadata.get("name") != "typescript" or metadata.get("version") != VERSION:
            raise ValueError("exact TypeScript 6.0.3 is required")
    return result


def trusted_node(source, environment):
    # Match CI's executable trust boundary and the installed launcher's fixed
    # search paths. PATH and project-local/version-manager overrides are not inputs.
    for raw in NODE_PATHS:
        try:
            node = Path(raw).resolve(strict=True)
            if not node.is_file() or not os.access(node, os.X_OK) or node.stat().st_mode & 0o022:
                continue
            if any(node == root or root in node.parents for root in (REPOSITORY, source)):
                continue
            probe = subprocess.run([str(node), "-e",
                                    'process.exit(Number(process.versions.node.split(".")[0]) >= 22 ? 0 : 2)'],
                                   capture_output=True, env=environment, timeout=5)
            if probe.returncode == 0:
                return str(node)
        except (OSError, RuntimeError, subprocess.SubprocessError):
            continue
    raise ValueError("Node.js 22+ is required at a trusted standard system or Homebrew path")


def closure(source, parser):
    source_bytes = {}
    for file in sorted((source / "src").glob("*.mjs")):
        source_bytes[file.name] = regular_bytes(physical(file))
    # No shell, npm, target config, or ambient Node startup hooks participate.
    environment = dict(os.environ)
    for name in ("NODE_OPTIONS", "NODE_PATH", "BASH_ENV", "ENV", "LD_PRELOAD", "LD_LIBRARY_PATH",
                 "DYLD_INSERT_LIBRARIES", "DYLD_LIBRARY_PATH"):
        environment.pop(name, None)
    node = trusted_node(source, environment)
    run = subprocess.run([node, "--input-type=commonjs", "-e", CLOSURE, str(parser)],
                         input=json.dumps({name: data.decode("utf-8") for name, data in source_bytes.items()}),
                         text=True, capture_output=True, env=environment, timeout=30)
    if run.returncode:
        raise ValueError("source dependency closure failed: " + run.stderr[:1200])
    graph = json.loads(run.stdout)
    if "source.mjs" not in graph["files"]:
        raise ValueError("scanner parser module is missing from closure")
    return graph, source_bytes


def expected_payload(source, parser, vendor):
    graph, originals = closure(source, parser)
    payload = dict(vendor)
    mapping = []
    for name in graph["files"]:
        before = originals[name]
        after = before
        if name == "source.mjs":
            if before.count(OLD_IMPORT) != 1:
                raise ValueError("parser import rewrite must match exactly once")
            after = before.replace(OLD_IMPORT, NEW_IMPORT)
        payload["src/" + name] = after
        mapping.append({"source": "src/" + name, "output": "src/" + name,
                        "source_sha256": digest(before), "output_sha256": digest(after),
                        "rewrite": "explicit-vendored-parser" if before != after else None})
    for name in ("LICENSE", "NOTICE"):
        payload[name] = regular_bytes(physical(source / name))
        mapping.append({"source": name, "output": name,
                        "source_sha256": digest(payload[name]), "output_sha256": digest(payload[name]), "rewrite": None})
    manifest = {
        "schema": "e2e-skills-scanner-runtime-v1",
        "entrypoint": "src/cli.mjs",
        "generated_by": "scripts/dev/build-scanner-runtime.py",
        "manifest_hash_policy": "manifest.json is excluded from its own payload hashes",
        "typescript": {"version": VERSION, "upstream": "npm:typescript@" + VERSION,
                       "files": [{"source": name, "output": VENDOR_PATHS[name], "sha256": value}
                                 for name, value in sorted(UPSTREAM.items())]},
        "source_mapping": mapping,
        "import_edges": graph["edges"],
        "files": {name: {"sha256": digest(data), "bytes": len(data)} for name, data in sorted(payload.items())},
    }
    payload["manifest.json"] = (json.dumps(manifest, indent=2, sort_keys=True) + "\n").encode()
    return payload


def output_files(output):
    if not output.exists():
        return set()
    if output.is_symlink() or not output.is_dir():
        raise ValueError("runtime output must be a regular directory")
    result = set()
    for directory, dirs, files in os.walk(output, followlinks=False):
        for name in dirs + files:
            path = Path(directory) / name
            if path.is_symlink() or not (path.is_dir() or path.is_file()):
                raise ValueError("unsupported runtime entry: " + str(path))
        for name in files:
            result.add(str((Path(directory) / name).relative_to(output)))
    return result


def build(args):
    source = physical(args.source_root)
    output = physical(args.output)
    dependency = physical(args.typescript_dir) if args.typescript_dir else None
    if args.write:
        if dependency is None:
            raise ValueError("--write requires --typescript-dir /absolute/external/typescript")
        if not Path(args.typescript_dir).is_absolute():
            raise ValueError("--typescript-dir must be absolute")
        if dependency == REPOSITORY or REPOSITORY in dependency.parents or dependency == source or source in dependency.parents:
            raise ValueError("TypeScript dependency must be outside the source checkout")
    elif dependency is not None:
        raise ValueError("--check is offline and does not accept --typescript-dir")
    vendor = vendor_files(dependency, output, args.write)
    # Use a private copy of verified parser bytes so a changed external file is
    # never the executable input. The .cjs suffix fixes its module format.
    with tempfile.TemporaryDirectory(prefix="scanner-runtime-parser-") as temporary:
        parser = Path(temporary) / "typescript.cjs"
        parser.write_bytes(vendor[VENDOR_PATHS["lib/typescript.js"]])
        payload = expected_payload(source, parser, vendor)
    actual = output_files(output)
    extras = actual - set(payload)
    if extras:
        raise ValueError("unexpected runtime files (not deleted): " + ", ".join(sorted(extras)))
    if args.write:
        output.mkdir(parents=True, exist_ok=True)
        for name, data in sorted(payload.items()):
            target = output / name
            target.parent.mkdir(parents=True, exist_ok=True)
            if target.exists() and regular_bytes(target) == data:
                continue
            # Replace only known generated paths; unrelated files are never removed.
            descriptor, temporary = tempfile.mkstemp(prefix=".runtime-", dir=target.parent)
            try:
                with os.fdopen(descriptor, "wb") as handle:
                    handle.write(data)
                os.chmod(temporary, 0o644)
                os.replace(temporary, target)
            finally:
                if os.path.exists(temporary):
                    os.unlink(temporary)
    else:
        missing = set(payload) - actual
        changed = [name for name in sorted(actual) if regular_bytes(output / name) != payload[name]]
        if missing or changed:
            raise ValueError("runtime drift: missing=" + ",".join(sorted(missing)) + "; changed=" + ",".join(changed))
    return {"mode": "write" if args.write else "check", "files": len(payload),
            "bytes": sum(map(len, payload.values())), "manifest_sha256": digest(payload["manifest.json"]), "complete": True}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--write", action="store_true")
    mode.add_argument("--check", action="store_true")
    parser.add_argument("--typescript-dir", help="explicit external typescript package directory; --write only")
    parser.add_argument("--source-root", default=str(REPOSITORY / "packages/scanner"), help="scanner package root")
    parser.add_argument("--output", default=str(REPOSITORY / "skills/e2e-reviewer/scripts/scanner"))
    args = parser.parse_args()
    try:
        print(json.dumps(build(args), sort_keys=True))
    except (ValueError, OSError, subprocess.SubprocessError, UnicodeError, json.JSONDecodeError) as error:
        print("scanner-runtime: " + str(error), file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
