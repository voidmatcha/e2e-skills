#!/bin/bash -p
# SPDX-License-Identifier: Apache-2.0

# This launcher is the security boundary before preflight_target.py starts.
# Keep every operation before the fixed interpreter selection a Bash builtin.
set -f
IFS=' '
unset BASH_ENV ENV CDPATH PATH VIRTUAL_ENV __PYVENV_LAUNCHER__
for startup_name in ${!PYTHON@} ${!DYLD@} ${!LD_@}; do
  unset "$startup_name"
done

case $0 in
  /*) launcher=$0 ;;
  *)
    printf '%s\n' \
      'run-preflight-target: invoke this launcher by its absolute path' >&2
    exit 126
    ;;
esac

python=
for candidate in \
  /usr/bin/python3 \
  /usr/local/bin/python3 \
  /opt/homebrew/bin/python3
do
  if [[ -f $candidate && -x $candidate ]] &&
    "$candidate" -I -B -c \
      'import sys; raise SystemExit(not (sys.version_info >= (3, 10) and sys.flags.isolated == 1 and sys.flags.dont_write_bytecode == 1 and sys.flags.optimize == 0 and __debug__))' \
      </dev/null >/dev/null 2>&1
  then
    python=$candidate
    break
  fi
done

if [[ -z $python ]]; then
  printf '%s\n' \
    'run-preflight-target: no trusted Python 3.10+ interpreter is available' >&2
  exit 126
fi

case $#:$1 in
  1:--framed-stdin|1:--help) ;;
  *)
    printf '%s\n' \
      'run-preflight-target: use --framed-stdin; URL values belong on stdin' >&2
    exit 2
    ;;
esac

exec "$python" -I -B -c '
import os
import stat
import sys


def fail(message):
    print(f"run-preflight-target: {message}", file=sys.stderr)
    raise SystemExit(126)


candidate = sys.argv[1]
launcher = sys.argv[2]
arguments = sys.argv[3:]
if not (
    sys.version_info >= (3, 10)
    and sys.flags.isolated == 1
    and sys.flags.dont_write_bytecode == 1
    and sys.flags.optimize == 0
    and __debug__
):
    fail("unsafe Python runtime flags")
if not os.path.isabs(candidate) or not os.path.isabs(launcher):
    fail("interpreter and launcher paths must be absolute")

executable = os.path.realpath(sys.executable)
if executable != os.path.realpath(candidate):
    fail("interpreter identity mismatch")
try:
    executable_stat = os.stat(executable)
except OSError as exc:
    fail(f"cannot stat interpreter: {exc}")
if (
    not stat.S_ISREG(executable_stat.st_mode)
    or executable_stat.st_mode & (stat.S_IWGRP | stat.S_IWOTH)
):
    fail("unsafe interpreter identity")

try:
    project_root = os.path.realpath(os.getcwd())
except OSError as exc:
    fail(f"cannot resolve the target project root: {exc}")
if not os.path.isabs(project_root) or not os.path.isdir(project_root):
    fail("target project root must be the physical invocation directory")
try:
    if os.path.commonpath((executable, project_root)) == project_root:
        fail("interpreter resolves inside the target project")
except ValueError:
    fail("interpreter and target project are on incompatible roots")

required_flags = ("O_DIRECTORY", "O_NOFOLLOW")
if any(not hasattr(os, name) for name in required_flags):
    fail("secure descriptor-relative path APIs are unavailable")
if os.open not in getattr(os, "supports_dir_fd", set()):
    fail("secure descriptor-relative path APIs are unavailable")

directory_flags = os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW
entry_flags = os.O_RDONLY | os.O_NOFOLLOW
if hasattr(os, "O_CLOEXEC"):
    directory_flags |= os.O_CLOEXEC
    entry_flags |= os.O_CLOEXEC

components = launcher.split("/")
if (
    components[0] != ""
    or len(components) < 3
    or any(component in ("", ".", "..") for component in components[1:])
):
    fail("launcher path must be a normalized absolute path")
if components[-1] != "run-preflight-target.sh":
    fail("unexpected launcher name")

directory_fd = -1
launcher_fd = -1
helper_fd = -1
script = os.path.join(os.path.dirname(launcher), "preflight_target.py")
try:
    directory_fd = os.open("/", directory_flags)
    for component in components[1:-1]:
        try:
            next_fd = os.open(component, directory_flags, dir_fd=directory_fd)
        except OSError as exc:
            fail(f"unsafe launcher ancestry: {exc}")
        os.close(directory_fd)
        directory_fd = next_fd

    try:
        launcher_fd = os.open(
            "run-preflight-target.sh",
            entry_flags,
            dir_fd=directory_fd,
        )
        helper_fd = os.open(
            "preflight_target.py",
            entry_flags,
            dir_fd=directory_fd,
        )
    except OSError as exc:
        fail(f"cannot open launcher bundle safely: {exc}")

    launcher_stat = os.fstat(launcher_fd)
    helper_stat = os.fstat(helper_fd)
    if (
        not stat.S_ISREG(launcher_stat.st_mode)
        or not launcher_stat.st_mode & 0o111
        or launcher_stat.st_mode & (stat.S_IWGRP | stat.S_IWOTH)
    ):
        fail("unsafe launcher identity")
    if (
        not stat.S_ISREG(helper_stat.st_mode)
        or helper_stat.st_mode & (stat.S_IWGRP | stat.S_IWOTH)
    ):
        fail("unsafe sibling helper identity")

    with os.fdopen(helper_fd, "rb", closefd=True) as source:
        helper_fd = -1
        code = compile(source.read(), script, "exec")
finally:
    for descriptor in (helper_fd, launcher_fd, directory_fd):
        if descriptor >= 0:
            os.close(descriptor)

sys.argv = [script, *arguments]
namespace = {
    "__name__": "__main__",
    "__file__": script,
    "__builtins__": __builtins__,
    "__package__": None,
    "__spec__": None,
}
exec(code, namespace, namespace)
' "$python" "$launcher" "$1"
