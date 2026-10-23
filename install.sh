#!/bin/bash -p
# SPDX-License-Identifier: Apache-2.0
# Public setup entry point. Run from a reviewed checkout, not through curl | bash.
set -euo pipefail
PATH=/usr/bin:/bin:/usr/sbin:/sbin
export PATH
unset BASH_ENV ENV CDPATH PYTHONPATH PYTHONHOME NODE_OPTIONS NODE_PATH
ROOT="$(cd "$(/usr/bin/dirname "$0")" && /bin/pwd -P)"
for node in /opt/homebrew/bin/node /usr/local/bin/node /usr/bin/node /bin/node; do
  if [ -x "$node" ] && "$node" -e 'const [major, minor] = process.versions.node.split(".").map(Number); process.exit(major > 22 || (major === 22 && minor >= 20) ? 0 : 1)'; then
    exec "$node" "$ROOT/scripts/dev/setup.mjs" "$@"
  fi
done
echo 'install: Node.js 22.20+ is required at a standard system or Homebrew location.' >&2
exit 2
