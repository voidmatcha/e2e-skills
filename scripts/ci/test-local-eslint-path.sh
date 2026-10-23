#!/usr/bin/env bash
# SPDX-License-Identifier: Apache-2.0
# Compatibility entry point for the installed Node scanner's local ESLint gate.
# Historical .bin/output mocks are replaced by API-level scope and trust checks.
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
exec python3 "$ROOT/scripts/ci/test-local-eslint-node.py" "$@"
