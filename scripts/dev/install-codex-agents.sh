#!/bin/bash -p
# Install the optional named Codex-native e2e agents from this checkout.

set -euo pipefail
set -f

# This installer writes global configuration. Do not resolve any utility through
# the caller's PATH or shell startup environment.
PATH="/usr/bin:/bin:/usr/sbin:/sbin"
export PATH
unset BASH_ENV ENV CDPATH

DIRNAME=/usr/bin/dirname
PWD_CMD=/bin/pwd
RM=/bin/rm
CP=/bin/cp
MV=/bin/mv
MKDIR=/bin/mkdir
MKTEMP=/usr/bin/mktemp
CHMOD=/bin/chmod
CMP=/usr/bin/cmp
GREP=/usr/bin/grep
SED=/usr/bin/sed
HEAD=/usr/bin/head

REPO_ROOT="$(cd "$("$DIRNAME" "$0")/../.." && "$PWD_CMD" -P)"
CODEX_HOME_DIR="${CODEX_HOME:-$HOME/.codex}"
DEST="$CODEX_HOME_DIR/agents"
AGENTS=(e2e-finding-verifier e2e-failure-classifier)
TRANSACTION_ROOT=
COMMIT_STARTED=0

cleanup_transaction() {
  if [ -n "$TRANSACTION_ROOT" ] && [ -e "$TRANSACTION_ROOT" ]; then
    "$RM" -rf -- "$TRANSACTION_ROOT"
  fi
}

rollback_transaction() {
  local rollback_status=0
  local name
  local dst
  local restore_tmp

  [ "$COMMIT_STARTED" -eq 1 ] || return 0
  for name in "${AGENTS[@]}"; do
    dst="$DEST/$name.toml"
    if [ -f "$TRANSACTION_ROOT/snapshot/$name.toml" ]; then
      restore_tmp="$DEST/.${name}.toml.restore.$$"
      if "$CP" -p "$TRANSACTION_ROOT/snapshot/$name.toml" "$restore_tmp" &&
         "$MV" -f "$restore_tmp" "$dst"; then
        :
      else
        "$RM" -f -- "$restore_tmp"
        rollback_status=1
      fi
    elif ! "$RM" -f -- "$dst"; then
      rollback_status=1
    fi
  done
  return "$rollback_status"
}

handle_exit() {
  local original_status=$?
  local rollback_status=0
  local cleanup_status=0

  trap - EXIT
  if [ "$original_status" -ne 0 ] && [ "$COMMIT_STARTED" -eq 1 ]; then
    rollback_transaction || rollback_status=$?
    if [ "$rollback_status" -eq 0 ]; then
      echo "install-codex-agents: interrupted commit rolled back to the previous agent state" >&2
    else
      echo "install-codex-agents: rollback failed while exiting after status $original_status; manual recovery required" >&2
    fi
  fi
  cleanup_transaction || cleanup_status=$?
  if [ "$rollback_status" -ne 0 ] || [ "$cleanup_status" -ne 0 ]; then
    exit 1
  fi
  exit "$original_status"
}

handle_signal() {
  local signal=$1
  local signal_number=$2
  local rollback_status=0

  trap - EXIT HUP INT TERM
  rollback_transaction || rollback_status=$?
  cleanup_transaction || true
  if [ "$rollback_status" -ne 0 ]; then
    echo "install-codex-agents: rollback failed while handling $signal; manual recovery required" >&2
  fi
  trap - "$signal"
  kill -s "$signal" "$$"
  exit $((128 + signal_number))
}

trap handle_exit EXIT
trap 'handle_signal HUP 1' HUP
trap 'handle_signal INT 2' INT
trap 'handle_signal TERM 15' TERM

# Preflight every source and destination before staging or replacing a file.
case "$CODEX_HOME_DIR" in
  /*) ;;
  *)
    echo "install-codex-agents: CODEX_HOME must be an absolute directory" >&2
    exit 1
    ;;
esac
if [ -L "$CODEX_HOME_DIR" ] ||
   { [ -e "$CODEX_HOME_DIR" ] && [ ! -d "$CODEX_HOME_DIR" ]; }; then
  echo "install-codex-agents: refusing redirected Codex home: $CODEX_HOME_DIR" >&2
  exit 1
fi
[ ! -L "$DEST" ] || {
  echo "install-codex-agents: refusing symlinked destination directory: $DEST" >&2
  exit 1
}
if [ -e "$DEST" ] && [ ! -d "$DEST" ]; then
  echo "install-codex-agents: destination is not a real directory: $DEST" >&2
  exit 1
fi

for name in "${AGENTS[@]}"; do
  src="$REPO_ROOT/.codex/agents/$name.toml"
  dst="$DEST/$name.toml"
  [ -f "$src" ] && [ ! -L "$src" ] || {
    echo "install-codex-agents: source is not a regular non-symlink file: $src" >&2
    exit 1
  }
  if [ -L "$dst" ]; then
    echo "install-codex-agents: refusing symlinked destination file: $dst" >&2
    exit 1
  fi
  if [ -e "$dst" ] && [ ! -f "$dst" ]; then
    echo "install-codex-agents: refusing non-regular destination file: $dst" >&2
    exit 1
  fi
  if [ -f "$dst" ] && ! "$CMP" -s "$src" "$dst"; then
    if ! "$GREP" -q '^# e2e-skills Codex/OMX native agent:' "$dst" &&
       [ "${E2E_SKILLS_FORCE_CODEX_AGENTS:-0}" != "1" ]; then
      echo "install-codex-agents: refusing to overwrite non-e2e-skills file: $dst" >&2
      echo "set E2E_SKILLS_FORCE_CODEX_AGENTS=1 only if replacement is intentional" >&2
      exit 1
    fi
  fi
done

"$MKDIR" -p "$DEST"
[ -d "$DEST" ] && [ ! -L "$DEST" ] || {
  echo "install-codex-agents: destination is not a real directory: $DEST" >&2
  exit 1
}
TRANSACTION_ROOT="$("$MKTEMP" -d "$DEST/.e2e-skills-agents.XXXXXX")"
"$MKDIR" -p "$TRANSACTION_ROOT/staged" "$TRANSACTION_ROOT/snapshot"

# Stage and validate both new files, then snapshot the complete prior state.
for name in "${AGENTS[@]}"; do
  src="$REPO_ROOT/.codex/agents/$name.toml"
  staged="$TRANSACTION_ROOT/staged/$name.toml"
  dst="$DEST/$name.toml"
  "$CP" "$src" "$staged"
  "$CHMOD" 0644 "$staged"
  discovered=$("$SED" -n 's/^name = "\([^"]*\)"[[:space:]]*$/\1/p' "$staged" | "$HEAD" -1)
  if [ "$discovered" != "$name" ]; then
    echo "install-codex-agents: source discovery validation failed for $name" >&2
    exit 1
  fi
  if [ -f "$dst" ]; then
    "$CP" -p "$dst" "$TRANSACTION_ROOT/snapshot/$name.toml"
  fi
done

COMMIT_STARTED=1
for name in "${AGENTS[@]}"; do
  staged="$TRANSACTION_ROOT/staged/$name.toml"
  dst="$DEST/$name.toml"
  if "$MV" -f "$staged" "$dst"; then
    echo "install-codex-agents: installed $dst"
  else
    commit_status=$?
    if ! rollback_transaction; then
      echo "install-codex-agents: commit failed with status $commit_status and rollback failed; manual recovery required" >&2
      exit 1
    fi
    COMMIT_STARTED=0
    echo "install-codex-agents: commit failed with status $commit_status; previous agent state restored" >&2
    exit "$commit_status"
  fi
done

for name in "${AGENTS[@]}"; do
  discovered=$("$SED" -n 's/^name = "\([^"]*\)"[[:space:]]*$/\1/p' "$DEST/$name.toml" | "$HEAD" -1)
  if [ "$discovered" != "$name" ]; then
    echo "install-codex-agents: discovery validation failed for $name" >&2
    exit 1
  fi
done
COMMIT_STARTED=0
echo "install-codex-agents: discovery files valid"

echo "Restart Codex sessions opened outside this repository so the named agents are rediscovered."
