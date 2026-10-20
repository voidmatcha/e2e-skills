#!/bin/bash -p
# SPDX-License-Identifier: Apache-2.0
# Restore the pinned public benchmark snapshot into a NEW external directory.
# Usage: fetch-benchmark-evidence.sh --dry-run
#        fetch-benchmark-evidence.sh --output /absolute/new-directory
#        fetch-benchmark-evidence.sh --verify-only --output /absolute/existing-directory
set -euo pipefail
repo_root="$(cd "$(dirname "$0")/../.." && pwd -P)"
exec python3 -I "$repo_root/scripts/dev/fetch-benchmark-evidence.py" "$@"
