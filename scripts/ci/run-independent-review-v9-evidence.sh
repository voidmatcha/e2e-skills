#!/bin/bash -p
set -euo pipefail

unset PYTHONPATH PYTHONHOME PYTHONUSERBASE PYTHONSTARTUP PYTHONINSPECT \
  PYTHONOPTIMIZE PYTHONWARNINGS PYTHONBREAKPOINT PYTHONDEBUG \
  PYTHONDONTWRITEBYTECODE PYTHONNOUSERSITE PYTHONSAFEPATH \
  PIP_CONFIG_FILE PIP_INDEX_URL PIP_EXTRA_INDEX_URL PIP_REQUIRE_VIRTUALENV

repo_root=$(cd -- "${BASH_SOURCE[0]%/*}/../.." && pwd -P)
archive="$repo_root/benchmarks/independent-product-review-v9-remediation"
validator="$repo_root/scripts/ci/test-independent-review-v9-evidence.py"
lock="$repo_root/scripts/evals/requirements-independent-review-v9-tokenizer.txt"

python312=
for candidate in /opt/homebrew/bin/python3.12 /usr/local/bin/python3.12 /usr/bin/python3.12; do
  [ -x "$candidate" ] || continue
  real_candidate=$(/usr/bin/env -i PATH=/usr/bin:/bin "$candidate" -I -B -c \
    'import os,sys; print(os.path.realpath(sys.argv[1]))' "$candidate")
  case "$real_candidate" in
    /opt/homebrew/Cellar/python@3.12/*/bin/python3.12|/opt/homebrew/Cellar/python@3.12/*/Frameworks/Python.framework/Versions/3.12/bin/python3.12|/usr/local/*/python3.12|/usr/bin/python3.12) ;;
    *) continue ;;
  esac
  [ -f "$real_candidate" ] && [ -x "$real_candidate" ] && [ ! -L "$real_candidate" ] || continue
  /usr/bin/env -i PATH=/usr/bin:/bin "$real_candidate" -I -B -c \
    'import sys; raise SystemExit(0 if sys.version_info[:2] == (3, 12) else 1)' || continue
  python312=$real_candidate
  break
done
[ -n "$python312" ] || {
  echo "v9 frozen evidence requires CPython 3.12" >&2
  exit 1
}
if [ ! -e "$archive" ]; then
  exec /usr/bin/env -i PATH=/usr/bin:/bin:/usr/sbin:/sbin \
    "$python312" -I -B "$validator"
fi
replay_env=$(mktemp -d "${TMPDIR:-/tmp}/e2e-v9-token-replay.XXXXXX")
trap 'rm -rf -- "$replay_env"' EXIT
/usr/bin/env -i PATH=/usr/bin:/bin "$python312" -I -B -m venv "$replay_env"
replay_python="$replay_env/bin/python"
/usr/bin/env -i PATH="$replay_env/bin:/usr/bin:/bin" PIP_CONFIG_FILE=/dev/null \
  "$replay_python" -I -B -m pip install --disable-pip-version-check --require-hashes -r "$lock" >/dev/null
/usr/bin/env -i PATH="$replay_env/bin:/usr/bin:/bin" \
  "$replay_python" -I -B "$validator"
