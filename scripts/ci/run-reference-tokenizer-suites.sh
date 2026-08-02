#!/bin/bash -p
# Run independent-review unit suites inside the pinned reference-tokenizer venv.
#
# Several adversarial checks in those suites (frozen fake-attestation rejection,
# the public --prepare-only/freeze integration, and the measurer's exact
# end-to-end contract) can only execute when tiktoken 0.11.0 is importable. The
# ordinary ci-local Python runner has never had it, so the checks used to skip
# themselves silently. The suites now fail closed instead, and this wrapper is
# the supported way to give them the interpreter they require: one venv built
# from the hash-locked requirements file, reused for every suite passed in.
set -euo pipefail

unset PYTHONPATH PYTHONHOME PYTHONUSERBASE PYTHONSTARTUP PYTHONINSPECT \
  PYTHONOPTIMIZE PYTHONWARNINGS PYTHONBREAKPOINT PYTHONDEBUG \
  PYTHONDONTWRITEBYTECODE PYTHONNOUSERSITE PYTHONSAFEPATH \
  PIP_CONFIG_FILE PIP_INDEX_URL PIP_EXTRA_INDEX_URL PIP_REQUIRE_VIRTUALENV

repo_root=$(cd -- "${BASH_SOURCE[0]%/*}/../.." && pwd -P)
lock="$repo_root/scripts/evals/requirements-independent-review-v10-reference-tokenizer.txt"

if [ "$#" -eq 0 ]; then
  echo "usage: run-reference-tokenizer-suites.sh <suite.py> [suite.py ...]" >&2
  exit 2
fi
for suite in "$@"; do
  case "$suite" in
    /*|*..*) echo "reference-tokenizer suites: refusing suite path $suite" >&2; exit 2 ;;
  esac
  [ -f "$repo_root/$suite" ] || {
    echo "reference-tokenizer suites: missing suite $suite" >&2
    exit 2
  }
done

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
  echo "reference-tokenizer suites require CPython 3.12" >&2
  exit 1
}

replay_env=$(mktemp -d "${TMPDIR:-/tmp}/e2e-reference-tokenizer-suites.XXXXXX")
trap 'rm -rf -- "$replay_env"' EXIT
/usr/bin/env -i PATH=/usr/bin:/bin "$python312" -I -B -m venv "$replay_env"
replay_python="$replay_env/bin/python"
/usr/bin/env -i PATH="$replay_env/bin:/usr/bin:/bin" PIP_CONFIG_FILE=/dev/null \
  "$replay_python" -I -B -m pip install --disable-pip-version-check --require-hashes -r "$lock" >/dev/null

# Fail closed before running anything: an empty or broken venv must not let the
# suites' tokenizer-gated checks turn back into no-ops.
"$replay_python" -I -B -c \
  'import tiktoken,sys; raise SystemExit(0 if tiktoken.__version__ == "0.11.0" else 1)' || {
  echo "reference-tokenizer suites: pinned tiktoken 0.11.0 unavailable in the replay venv" >&2
  exit 1
}

status=0
for suite in "$@"; do
  if ! (cd -- "$repo_root" && "$replay_python" -I -B "$suite"); then
    echo "reference-tokenizer suites: FAILED $suite" >&2
    status=1
  fi
done
exit "$status"
