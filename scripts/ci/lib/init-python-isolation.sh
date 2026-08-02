#!/usr/bin/env bash
# Pin CI shell scripts and their descendants to the isolated Python runner.

if [[ -z "${REPO_ROOT:-}" ]]; then
  echo "ci-python: REPO_ROOT must be set before loading Python isolation" >&2
  return 2
fi

PYTHON_RUNNER="$REPO_ROOT/scripts/ci/lib/run-python-isolated.sh"
if [[ ! -f "$PYTHON_RUNNER" || ! -x "$PYTHON_RUNNER" ]]; then
  echo "ci-python: trusted isolated Python runner unavailable" >&2
  return 2
fi
if ! "$PYTHON_RUNNER" -c \
  'import sys; assert __debug__ and sys.flags.isolated == 1' >/dev/null; then
  echo "ci-python: trusted isolated Python runner unusable" >&2
  return 2
fi

run_python() {
  "$PYTHON_RUNNER" "$@"
}

# Some established CI shell gates still invoke `python3` internally. Override
# both PATH lookup and any imported/exported function before those calls, then
# export the trusted wrapper so transitive shell children inherit the contract.
python3() {
  "$PYTHON_RUNNER" "$@"
}
export PYTHON_RUNNER
export -f python3
readonly -f python3
