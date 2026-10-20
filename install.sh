#!/bin/bash -p
# SPDX-License-Identifier: Apache-2.0
# Public setup entry point. Run from a reviewed checkout, not through curl | bash.
set -euo pipefail
PATH=/usr/bin:/bin:/usr/sbin:/sbin
export PATH
unset BASH_ENV ENV CDPATH PYTHONPATH PYTHONHOME NODE_OPTIONS NODE_PATH
ROOT="$(cd "$(/usr/bin/dirname "$0")" && /bin/pwd -P)"
for python in /opt/homebrew/bin/python3 /usr/local/bin/python3 /usr/bin/python3; do
  if [ -x "$python" ] && "$python" -I -S -c 'import sys; sys.exit(sys.version_info < (3, 11))'; then
    exec "$python" -I -S "$ROOT/scripts/dev/setup.py" "$@"
  fi
done
echo 'install: Python 3.11+ is required at a standard system or Homebrew location.' >&2
exit 2
