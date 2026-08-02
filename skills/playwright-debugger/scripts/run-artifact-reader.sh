#!/bin/sh
# SPDX-License-Identifier: Apache-2.0

set -eu

fail() {
  printf '%s\n' "artifact-reader launcher: $*" >&2
  exit 1
}

resolve_path() {
  candidate=$1
  hops=0
  while [ -L "$candidate" ]; do
    hops=$((hops + 1))
    [ "$hops" -le 16 ] || return 1
    target=$(/usr/bin/readlink "$candidate") || return 1
    case "$target" in
      /*) candidate=$target ;;
      *)
        parent=${candidate%/*}
        [ "$parent" != "$candidate" ] || parent=.
        physical_parent=$(CDPATH= cd -P -- "$parent" 2>/dev/null && pwd) || return 1
        candidate=$physical_parent/$target
        ;;
    esac
  done
  parent=${candidate%/*}
  base=${candidate##*/}
  [ "$parent" != "$candidate" ] || parent=.
  physical_parent=$(CDPATH= cd -P -- "$parent" 2>/dev/null && pwd) || return 1
  printf '%s/%s\n' "$physical_parent" "$base"
}

file_owner_uid() {
  /usr/bin/stat -c '%u' "$1" 2>/dev/null ||
    /usr/bin/stat -f '%u' "$1" 2>/dev/null
}

file_mode() {
  /usr/bin/stat -c '%a' "$1" 2>/dev/null ||
    /usr/bin/stat -f '%Lp' "$1" 2>/dev/null
}

is_root_owned_system_path() {
  checked=$1
  while :; do
    owner_uid=$(file_owner_uid "$checked") || return 1
    [ "$owner_uid" = 0 ] || return 1
    mode=$(file_mode "$checked") || return 1
    case "$mode" in *[!0-9]*|'') return 1 ;; esac
    group_digit=$(((mode / 10) % 10))
    other_digit=$((mode % 10))
    [ "$group_digit" -ne 2 ] && [ "$group_digit" -ne 3 ] &&
      [ "$group_digit" -ne 6 ] && [ "$group_digit" -ne 7 ] || return 1
    [ "$other_digit" -ne 2 ] && [ "$other_digit" -ne 3 ] &&
      [ "$other_digit" -ne 6 ] && [ "$other_digit" -ne 7 ] || return 1
    [ "$checked" != / ] || break
    checked=${checked%/*}
    [ -n "$checked" ] || checked=/
  done
}

[ "${1-}" = "--project-root" ] ||
  fail "expected --project-root <absolute-directory> [--reader <name>] [--pass-env NAME]... -- <script arguments>"
[ "$#" -ge 4 ] || fail "missing project root or reader arguments"
project_root_input=$2
shift 2
reader_name=read-playwright-artifact.py
if [ "${1-}" = "--reader" ]; then
  [ "$#" -ge 3 ] || fail "missing reader name"
  reader_name=$2
  shift 2
fi

# Every bundled entry point this launcher may start, with the closed set of
# environment variables each one is allowed to receive.
#
# Readers get nothing: they only read already-validated files.
# The publisher gets PATH, and only PATH, because its own --pass-env contract
#   hands the operator-approved PATH to a project-local Node launcher; the
#   publisher builds the child environment itself from os.defpath plus the
#   names it was told to pass.
# The downloader gets HOME plus the two gh token names: gh resolves stored
#   credentials under HOME and cannot authenticate without one of them. The
#   downloader already refuses a HOME resolving inside the target project and
#   pins its own fixed child PATH, so PATH is deliberately NOT allowed here.
# Nothing else is forwarded. PYTHON* in particular never crosses this boundary.
case "$reader_name" in
  read-playwright-artifact.py) pass_env_allowlist='' ;;
  publish-json-report.py) pass_env_allowlist='PATH' ;;
  download-playwright-report.py) pass_env_allowlist='HOME GH_TOKEN GITHUB_TOKEN' ;;
  *) fail "reader is not allowlisted" ;;
esac

requested_env=''
while [ "${1-}" = "--pass-env" ]; do
  [ "$#" -ge 3 ] || fail "missing environment variable name"
  requested=$2
  shift 2
  allowed=no
  for allowlisted_name in $pass_env_allowlist; do
    [ "$requested" = "$allowlisted_name" ] || continue
    allowed=yes
    break
  done
  [ "$allowed" = yes ] ||
    fail "environment variable is not allowlisted for $reader_name: $requested"
  for seen_name in $requested_env; do
    [ "$seen_name" != "$requested" ] ||
      fail "environment variable requested more than once: $requested"
  done
  requested_env="$requested_env $requested"
done

[ "${1-}" = "--" ] || fail "expected -- before reader arguments"
shift
[ "$#" -gt 0 ] || fail "missing reader arguments"

case "$0" in
  /*) ;;
  *) fail "launcher must be invoked by an absolute path" ;;
esac
case "$project_root_input" in
  /*) ;;
  *) fail "project root must be absolute" ;;
esac
[ -d "$project_root_input" ] && [ ! -L "$project_root_input" ] ||
  fail "project root must be a real directory, not a symlink"
project_root=$(CDPATH= cd -P -- "$project_root_input" 2>/dev/null && pwd) ||
  fail "cannot resolve project root"

launcher_path=$(resolve_path "$0") || fail "cannot resolve launcher path"
launcher_dir=${launcher_path%/*}
reader=$launcher_dir/$reader_name
[ -f "$reader" ] && [ ! -L "$reader" ] || fail "bundled reader is not a regular non-symlink file"
case "$reader" in
  /*) ;;
  *) fail "bundled reader path is not absolute" ;;
esac
case "$launcher_path" in
  "$project_root"|"$project_root"/*)
    fail "launcher resolves inside the target project" ;;
esac
case "$reader" in
  "$project_root"|"$project_root"/*)
    fail "bundled reader resolves inside the target project" ;;
esac

interpreter=
for fixed_candidate in \
  /usr/bin/python3 \
  /bin/python3
do
  [ -e "$fixed_candidate" ] || continue
  resolved_candidate=$(resolve_path "$fixed_candidate") || continue
  [ -f "$resolved_candidate" ] && [ ! -L "$resolved_candidate" ] &&
    [ -x "$resolved_candidate" ] || continue
  is_root_owned_system_path "$resolved_candidate" || continue
  case "$resolved_candidate" in
    "$project_root"|"$project_root"/*) continue ;;
  esac
  interpreter=$resolved_candidate
  break
done

[ -n "$interpreter" ] ||
  fail "no root-owned executable system Python outside the project root"

# Build the exec vector explicitly. The interpreter was chosen from the bounded
# absolute candidate list above, never from PATH, and `env -i` still clears the
# whole environment; only the names validated against the per-script allowlist
# are re-added, by literal name, with no indirect expansion.
set -- "$interpreter" -I -B "$reader" "$@"
for forwarded_name in $requested_env; do
  case "$forwarded_name" in
    PATH)
      [ -n "${PATH+set}" ] || fail "requested environment variable is not set: PATH"
      set -- "PATH=$PATH" "$@" ;;
    HOME)
      [ -n "${HOME+set}" ] || fail "requested environment variable is not set: HOME"
      set -- "HOME=$HOME" "$@" ;;
    GH_TOKEN)
      [ -n "${GH_TOKEN+set}" ] ||
        fail "requested environment variable is not set: GH_TOKEN"
      set -- "GH_TOKEN=$GH_TOKEN" "$@" ;;
    GITHUB_TOKEN)
      [ -n "${GITHUB_TOKEN+set}" ] ||
        fail "requested environment variable is not set: GITHUB_TOKEN"
      set -- "GITHUB_TOKEN=$GITHUB_TOKEN" "$@" ;;
    *) fail "environment variable is not allowlisted: $forwarded_name" ;;
  esac
done

exec /usr/bin/env -i "$@"
