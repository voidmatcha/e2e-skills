#!/bin/bash -p
# Run the shipped scripts' test suites on Linux before they reach hosted CI.
#
# Local ci-local.sh runs on macOS, so Linux-only behavior shipped unseen: from
# 1.11.0 to 1.17.0 the scanner ran /usr/bin/sg -- the shadow-utils group
# command on Debian and Ubuntu -- as ast-grep. This check copies the committed
# tree (`git archive`, which is what a push sends) into a digest-pinned
# Ubuntu image and runs the reviewer scanner and debugger script suites as a
# non-root user, because root would make the unreadable-file fail-closed tests
# pass for the wrong reason.
#
# Usage: scripts/dev/linux-script-check.sh [<revision>]   (default: HEAD)
# Needs a running Docker daemon and network access for apt.
# Exit 1: a suite failed or is missing. Exit 2: Docker or the revision is
# unavailable. Any other status is a container or package-install failure.
builtin set -euo pipefail

PATH="/opt/homebrew/bin:/usr/local/bin:/usr/bin:/bin:/usr/sbin:/sbin"
builtin export PATH
builtin unset CDPATH ENV BASH_ENV GLOBIGNORE

IMAGE="ubuntu@sha256:b3cc40b72b93588182b5410f723c7aaf142363311c2aa993d8a453ddcbb3ae15"
REPO_ROOT="$(/usr/bin/git rev-parse --show-toplevel)"
REV="${1:-HEAD}"
REV_SHA="$(/usr/bin/git -C "$REPO_ROOT" rev-parse --verify --quiet "$REV^{commit}")" || {
  echo "linux-script-check: not a commit: $REV" >&2
  exit 2
}

DOCKER=""
for candidate in /usr/local/bin/docker /opt/homebrew/bin/docker /usr/bin/docker; do
  if [ -x "$candidate" ]; then
    DOCKER="$candidate"
    break
  fi
done
if [ -z "$DOCKER" ]; then
  echo "linux-script-check: docker not found" >&2
  exit 2
fi
if ! "$DOCKER" info >/dev/null 2>&1; then
  echo "linux-script-check: docker daemon is not running" >&2
  exit 2
fi

echo "==> linux-script-check: ${REV_SHA:0:7} in $IMAGE"
/usr/bin/git -C "$REPO_ROOT" archive --format=tar "$REV_SHA" |
  "$DOCKER" run --rm -i --network=bridge "$IMAGE" /bin/bash -c '
    set -euo pipefail
    export DEBIAN_FRONTEND=noninteractive
    apt-get update -qq >/dev/null
    apt-get install -y -qq --no-install-recommends python3 ripgrep nodejs npm git ca-certificates >/dev/null
    useradd --create-home checker
    install -d -o checker -g checker /srv/repo
    tar -x -C /srv/repo --no-same-owner
    chown -R checker:checker /srv/repo
    # The scanner finds its project root from the Git worktree boundary, as a
    # hosted checkout provides; without .git it falls back to the nearest
    # package root and the self-repo fixture exclusion does not apply.
    su checker -s /bin/bash -c "cd /srv/repo && git init -q && git add -A &&
      git -c user.name=linux-script-check -c user.email=check@localhost commit -qm snapshot"
    if [ -e /usr/bin/sg ]; then
      echo "note: /usr/bin/sg is $(readlink -f /usr/bin/sg), not ast-grep"
    fi
    cd /srv/repo
    for suite in \
      scripts/ci/test-reviewer-scanner.py \
      scripts/ci/test-debugger-contracts.py \
      scripts/ci/test-playwright-debugger-artifact-download.py \
      scripts/ci/test-playwright-debugger-report-publish.py \
      scripts/ci/test-cypress-debugger-artifact-download.py \
      scripts/ci/test-cypress-debugger-report-publish.py; do
      echo "--- $suite"
      if [ ! -f "$suite" ]; then
        echo "linux-script-check: missing suite: $suite" >&2
        exit 1
      fi
      # umask 022 matches the hosted runner; Ubuntu gives new users 002, which
      # makes test-created tool directories group-writable and correctly refused.
      # Any suite failure exits 1, which the pre-push hook treats as blocking.
      su checker -s /bin/bash -c "umask 022 && python3 $suite" || exit 1
    done
  '
echo "==> linux-script-check: pass"
