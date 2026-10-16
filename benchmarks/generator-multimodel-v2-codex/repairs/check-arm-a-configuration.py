#!/usr/bin/env python3
"""Check the pending arm-A repair in memory without changing frozen files. Apache-2.0."""
import argparse
import importlib.machinery
from pathlib import Path
import re
import sys
import types
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[3]
PATCH = Path(__file__).with_name("arm-a-configuration.patch")
SUITES = (
    "test-generator-multimodel-v2-codex.py",
    "test-generator-v2-codex-harness-fixes.py",
    "test-generator-v2-codex-smoke.py",
    "test-generator-codex-container-adapter.py",
    "test-generator-oss-eval-v1.py",
)


def candidates():
    """Apply exact-context unified hunks to strings, failing on source drift."""
    lines = PATCH.read_text().splitlines(keepends=True)
    result, index = {}, 0
    while index < len(lines):
        if not lines[index].startswith("--- a/"):
            raise ValueError("unexpected patch header")
        path = ROOT / lines[index][6:].strip()
        if not path.is_relative_to(ROOT) or not path.is_file():
            raise ValueError("invalid patch target")
        source, rewritten, cursor = path.read_text().splitlines(keepends=True), [], 0
        index += 2
        while index < len(lines) and not lines[index].startswith("--- a/"):
            match = re.fullmatch(r"@@ -(\d+)(?:,\d+)? \+\d+(?:,\d+)? @@.*\n", lines[index])
            if not match:
                raise ValueError("invalid hunk header")
            start = int(match[1]) - 1
            if start < cursor:
                raise ValueError("overlapping hunks")
            rewritten.extend(source[cursor:start])
            cursor, index = start, index + 1
            while index < len(lines) and not lines[index].startswith(("@@", "--- a/")):
                line = lines[index]
                if line[0] in " -":
                    if cursor >= len(source) or source[cursor] != line[1:]:
                        raise ValueError("patch context drift: " + str(path.relative_to(ROOT)))
                    cursor += 1
                if line[0] in " +":
                    rewritten.append(line[1:])
                index += 1
        rewritten.extend(source[cursor:])
        result[path] = "".join(rewritten)
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--suite", choices=SUITES, default=SUITES[0])
    args = parser.parse_args()
    proposed = candidates()
    original_text, original_bytes = Path.read_text, Path.read_bytes
    original_code = importlib.machinery.SourceFileLoader.get_code

    def read_text(path, *a, **kw):
        return proposed[path] if path in proposed else original_text(path, *a, **kw)

    def read_bytes(path, *a, **kw):
        return proposed[path].encode() if path in proposed else original_bytes(path, *a, **kw)

    def get_code(loader, name):
        path = Path(loader.path)
        return compile(proposed[path], str(path), "exec") if path in proposed else original_code(loader, name)

    target = ROOT / "scripts/ci" / args.suite
    with patch.object(Path, "read_text", read_text), patch.object(Path, "read_bytes", read_bytes), \
            patch.object(importlib.machinery.SourceFileLoader, "get_code", get_code):
        module = types.ModuleType("__main__")
        module.__file__ = str(target)
        sys.modules["__main__"] = module
        sys.argv = [str(target)]
        exec(compile(read_text(target), str(target), "exec"), module.__dict__)


if __name__ == "__main__":
    main()
