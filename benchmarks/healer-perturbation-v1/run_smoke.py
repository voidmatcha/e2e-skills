#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Run only the two unscored Codex smoke cells for healer-perturbation-v1."""

from __future__ import annotations

import sys

from run_healer import main


if __name__ == "__main__":
    raise SystemExit(main(["--stage", "smoke", *sys.argv[1:]]))
