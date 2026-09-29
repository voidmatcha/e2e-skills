#!/usr/bin/env python3
"""Run the shared collector under the frozen lazy v4 selection contract."""

import importlib.util
from pathlib import Path


def main():
    source = Path(__file__).with_name("collect-reviewer-specificity-v3.py")
    spec = importlib.util.spec_from_file_location("specificity_collector", source)
    collector = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(collector)
    collector.PROTOCOL = source.with_name("reviewer-specificity-protocol-v4.json")
    try:
        return collector.main()
    except (ValueError, OSError, collector.GitHubRetryExhausted) as exc:
        print(f"error: {exc}", file=collector.sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
