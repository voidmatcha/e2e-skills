#!/usr/bin/env bash
# SPDX-License-Identifier: Apache-2.0
# Restore both faults. Idempotent; edits only src/LikeButton.jsx.
set -euo pipefail
cd "$(dirname "$0")"
./break-post.sh restore
./break.sh restore
