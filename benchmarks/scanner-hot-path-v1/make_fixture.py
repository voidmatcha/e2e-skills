#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Generate the pinned dense-hit fixture used by scanner-hot-path-v1.

One spec whose every third line is a scanner hit, so the measurement is
dominated by per-hit work rather than by file discovery.

    make_fixture.py <output-dir> [--hits 300]
"""

from __future__ import annotations

import argparse
from pathlib import Path


def spec(hits: int) -> str:
    lines = [
        "import { test, expect } from '@playwright/test';",
        "test('dense', async ({ page }) => {",
    ]
    for index in range(hits):
        lines.append(f"  await page.locator('#row{index}').first().click();")
        lines.append(f"  await expect(page.locator('#row{index}')).toBeVisible();")
        lines.append(f"  const value{index} = await page.locator('#v{index}').textContent();")
    lines.append("});")
    return "\n".join(lines) + "\n"


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("output", type=Path)
    parser.add_argument("--hits", type=int, default=300)
    args = parser.parse_args()
    tests = args.output / "tests"
    tests.mkdir(parents=True, exist_ok=True)
    (tests / "dense.spec.ts").write_text(spec(args.hits), encoding="utf-8")
    print(f"wrote {tests / 'dense.spec.ts'} ({args.hits} hit rows)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
