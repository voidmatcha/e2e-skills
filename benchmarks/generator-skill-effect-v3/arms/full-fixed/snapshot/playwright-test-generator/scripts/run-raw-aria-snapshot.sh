#!/bin/bash -p
# SPDX-License-Identifier: Apache-2.0

# This launcher is the environment and executable boundary before the
# project-installed Playwright package runs.
set -f
IFS=' '

safe_home=${HOME-}
unset BASH_ENV ENV CDPATH PATH
for startup_name in \
  ${!BASH_FUNC_@} \
  ${!NODE@} \
  ${!NPM_@} \
  ${!npm_@} \
  ${!DYLD@} \
  ${!LD_@}
do
  unset "$startup_name"
done

fail() {
  printf 'run-raw-aria-snapshot: %s\n' "$1" >&2
  exit "${2:-126}"
}

case $0 in
  /*) launcher=$0 ;;
  *) fail 'invoke this launcher by its absolute path' ;;
esac

case $#:$1 in
  1:--framed-stdin) ;;
  *) fail 'use --framed-stdin; the target URL belongs on stdin' 2 ;;
esac

case $safe_home in
  /*) ;;
  *) fail 'HOME must be an absolute path' ;;
esac
case $safe_home in
  *$'\n'*|*$'\r'*) fail 'HOME contains an unsafe line break' ;;
esac
[[ -d $safe_home ]] || fail 'HOME must name an existing directory'
[[ -x /usr/bin/env ]] || fail '/usr/bin/env is unavailable'

minimal_path=/usr/bin:/bin
project_root=$(pwd -P) || fail 'cannot resolve the target project root'
node=
for candidate in \
  /opt/homebrew/bin/node \
  /usr/local/bin/node \
  /usr/bin/node \
  /bin/node
do
  [[ -f $candidate && -x $candidate ]] || continue
  resolved=$(
    /usr/bin/env -i \
      HOME="$safe_home" \
      PATH="$minimal_path" \
      "$candidate" -e '
const fs = require("node:fs");
const executable = fs.realpathSync(process.execPath);
const metadata = fs.statSync(executable);
if (!metadata.isFile() || (metadata.mode & 0o022) !== 0) process.exit(1);
process.stdout.write(executable);
' </dev/null
  ) || continue
  case $resolved in
    /*) ;;
    *) continue ;;
  esac
  case $resolved in
    *$'\n'*|*$'\r'*) continue ;;
  esac
  case $resolved in
    "$project_root"|"$project_root"/*) continue ;;
  esac
  node=$resolved
  break
done

[[ -n $node ]] ||
  fail 'no fixed-path, non-project, non-group-writable Node executable is available'

helper_candidate=${launcher%/*}/raw-aria-snapshot.cjs
helper=$(
  /usr/bin/env -i \
    HOME="$safe_home" \
    PATH="$minimal_path" \
    "$node" -e '
const fs = require("node:fs");
const path = require("node:path");
const launcher = fs.realpathSync(process.argv[1]);
const helper = fs.realpathSync(process.argv[2]);
if (
  path.basename(launcher) !== "run-raw-aria-snapshot.sh" ||
  path.basename(helper) !== "raw-aria-snapshot.cjs" ||
  path.dirname(launcher) !== path.dirname(helper)
) process.exit(1);
for (const [file, executable] of [[launcher, true], [helper, false]]) {
  const metadata = fs.statSync(file);
  if (
    !metadata.isFile() ||
    (metadata.mode & 0o022) !== 0 ||
    (executable && (metadata.mode & 0o111) === 0)
  ) process.exit(1);
}
process.stdout.write(helper);
' "$launcher" "$helper_candidate" </dev/null
) || fail 'unsafe raw-ARIA launcher bundle identity'

exec /usr/bin/env -i \
  HOME="$safe_home" \
  PATH="$minimal_path" \
  "$node" "$helper" --framed-stdin
