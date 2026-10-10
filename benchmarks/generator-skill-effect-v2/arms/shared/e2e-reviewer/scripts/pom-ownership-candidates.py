#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Surface exact-selector POM ownership leads; never issue a #13 verdict."""

import argparse
import json
import re
import sys
from pathlib import Path


RAW_ACTION = re.compile(
    r"\b(?:cy\.get|cy\.getByTestId|page\.locator|page\.getByTestId)\s*\(\s*"
    r"(?P<quote>['\"`])(?P<selector>(?:(?!(?P=quote))[^\\\n])+)(?P=quote)"
    r"(?:\s*,\s*\{[^{}()\n]*\})?\s*\)"
    r"(?:\s*\.\s*(?:should|scrollIntoView)\s*\([^()\n]*\))*"
    r"\s*\.\s*(?P<action>click|dblclick|fill|type|press|check|uncheck|select|selectOption)\s*\(",
    re.MULTILINE,
)
SOURCE_SUFFIXES = {".js", ".jsx", ".ts", ".tsx", ".mjs", ".cjs", ".mts", ".cts"}
MAX_CANDIDATES = 20


def line_number(source: str, offset: int) -> int:
    return source.count("\n", 0, offset) + 1


def source_files(root: Path):
    if root.is_symlink():
        raise ValueError(f"context root is a symlink: {root}")
    for path in sorted(root.rglob("*")):
        if path.is_symlink():
            raise ValueError(f"context contains a symlink: {path}")
        if path.is_file() and path.suffix in SOURCE_SUFFIXES:
            yield path


def collect(spec: Path, context):
    if spec.is_symlink() or not spec.is_file():
        raise ValueError("spec must be a regular file")
    contexts = (context,) if isinstance(context, Path) else tuple(context)
    if not contexts or any(root.is_symlink() or not root.is_dir() for root in contexts):
        raise ValueError("context roots must be regular directories")
    source = spec.read_text(encoding="utf-8", errors="replace")
    actions = [
        {"line": line_number(source, match.start("action")), "selector": match.group("selector")}
        for match in RAW_ACTION.finditer(source)
    ]
    selectors = {action["selector"] for action in actions}
    matches = {selector: [] for selector in selectors}
    literals = {
        selector: re.compile(r"(?P<quote>['\"`])" + re.escape(selector) + r"(?P=quote)")
        for selector in selectors
    }
    for path in (path for root in contexts for path in source_files(root)):
        if path.resolve() == spec.resolve():
            continue
        content = path.read_text(encoding="utf-8", errors="replace")
        for selector in selectors:
            if not literals[selector].search(content):
                continue
            lines = content.splitlines()
            for number, line in enumerate(lines, 1):
                if not literals[selector].search(line):
                    continue
                fields = re.findall(r"\b([A-Za-z_$][\w$]*)\s*=\s*['\"`]" + re.escape(selector) + r"['\"`]", line)
                usage = []
                for field in fields:
                    usage.extend(
                        {"line": used_number, "source": used_line.strip()[:180]}
                        for used_number, used_line in enumerate(lines, 1)
                        if re.search(r"\bthis\." + re.escape(field) + r"\b", used_line)
                    )
                matches[selector].append(
                    {"path": str(path), "line": number, "source": line.strip()[:180], "field_uses": usage[:8], "field_uses_truncated": len(usage) > 8}
                )
                if sum(map(len, matches.values())) > MAX_CANDIDATES:
                    raise ValueError("too many exact-selector leads; narrow --context-root")
    return [
        {"spec": str(spec), "line": action["line"], "selector": action["selector"], "leads": matches[action["selector"]]}
        for action in actions
        if matches[action["selector"]]
    ]


def cypress_context_roots(spec: Path):
    for parent in spec.parents:
        if parent.name == "e2e" and parent.parent.name == "cypress":
            roots = []
            for candidate in sorted(parent.parent.iterdir()):
                if candidate.name.casefold() not in {"support", "pageobjects"}:
                    continue
                if candidate.is_symlink():
                    raise ValueError(f"context root is a symlink: {candidate}")
                if candidate.is_dir():
                    roots.append(candidate)
            return tuple(roots)
    return ()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--spec", type=Path, required=True)
    context = parser.add_mutually_exclusive_group(required=True)
    context.add_argument("--context-root", type=Path)
    context.add_argument("--auto-cypress-support", action="store_true")
    parser.add_argument("--format", choices=("json", "scanner"), default="json")
    args = parser.parse_args()
    try:
        context_roots = cypress_context_roots(args.spec) if args.auto_cypress_support else (args.context_root,)
        if not context_roots:
            print("#13 ownership leads: unavailable (no regular Cypress POM/support root)")
            return 0
        candidates = collect(args.spec, context_roots)
    except (OSError, ValueError) as exc:
        print(f"INCOMPLETE: {exc}", file=sys.stderr)
        return 2
    if args.format == "scanner":
        print(f"#13 ownership leads (exact selectors, candidates only): {len(candidates)}")
        for candidate in candidates:
            print(f"#13 lead {candidate['spec']}:{candidate['line']} selector {candidate['selector']!r}")
            for lead in candidate["leads"]:
                print(f"  source {lead['path']}:{lead['line']}: {lead['source']}")
                for field_use in lead["field_uses"]:
                    print(f"  field use {lead['path']}:{field_use['line']}: {field_use['source']}")
                if lead["field_uses_truncated"]:
                    print("  further field uses omitted; inspect source before a verdict")
    else:
        print(json.dumps({"status": "candidates-only", "count": len(candidates), "candidates": candidates}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
