#!/usr/bin/env bash
# Run CI Python entry points with assertions enabled and ambient Python hooks off.

set -uo pipefail

for variable in \
  PYTHONOPTIMIZE \
  PYTHONPATH \
  PYTHONHOME \
  PYTHONSTARTUP \
  PYTHONINSPECT \
  PYTHONUSERBASE
do
  case "$variable" in
    PYTHONOPTIMIZE) value="${PYTHONOPTIMIZE:-}" ;;
    PYTHONPATH) value="${PYTHONPATH:-}" ;;
    PYTHONHOME) value="${PYTHONHOME:-}" ;;
    PYTHONSTARTUP) value="${PYTHONSTARTUP:-}" ;;
    PYTHONINSPECT) value="${PYTHONINSPECT:-}" ;;
    PYTHONUSERBASE) value="${PYTHONUSERBASE:-}" ;;
  esac
  if [[ -n "$value" ]]; then
    echo "ci-python: refusing ambient $variable; CI Python must run isolated" >&2
    exit 2
  fi
done

PYTHON_BIN=""
for candidate in \
  /opt/homebrew/bin/python3 \
  /usr/local/bin/python3 \
  /usr/bin/python3
do
  if [[ -x "$candidate" ]] &&
     "$candidate" -I -B -c \
       'import sys; raise SystemExit(0 if sys.version_info >= (3, 10) else 1)' \
       >/dev/null 2>&1; then
    PYTHON_BIN="$candidate"
    break
  fi
done
if [[ -z "$PYTHON_BIN" ]]; then
  echo "ci-python: trusted Python 3.10+ executable unavailable" >&2
  exit 2
fi

exec "$PYTHON_BIN" -I -B "$@"
