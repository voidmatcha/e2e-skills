#!/bin/bash -p
# Run the shipped scripts' test suites on Linux before they reach hosted CI.
#
# Local ci-local.sh runs on macOS, so Linux-only behavior shipped unseen: from
# 1.11.0 to 1.17.0 the scanner ran /usr/bin/sg -- the shadow-utils group
# command on Debian and Ubuntu -- as ast-grep. This check copies the committed
# tree (`git archive`, which is what a push sends) into an official Node image
# pinned by digest and runs the reviewer scanner and debugger script suites as a
# non-root user, because root would make the unreadable-file fail-closed tests
# pass for the wrong reason.
#
# Usage: scripts/dev/linux-script-check.sh [--validate-inputs-only] [<revision>]
# A default HEAD run rejects relevant worktree changes because git archive
# cannot include them. An explicit revision is intentionally commit-only for
# pre-push use and ignores the current worktree.
# Needs a running Docker daemon and network access for apt.
# Exit 1: a suite failed or is missing. Exit 2: Docker or the revision is
# unavailable. Any other status is a container or package-install failure.
builtin set -euo pipefail

PATH="/opt/homebrew/bin:/usr/local/bin:/usr/bin:/bin:/usr/sbin:/sbin"
builtin export PATH
builtin unset CDPATH ENV BASH_ENV GLOBIGNORE

# Official node:22-bookworm-slim OCI index, verified at registry-1.docker.io
# on 2026-10-22; includes Linux amd64 and arm64. Node comes from this immutable
# image, never the distribution nodejs package. See github.com/nodejs/docker-node.
IMAGE="node@sha256:3ed98443660ff48413b5af19ecefce3b9d50845a901a43420d47cc63a9fddbe9"
REPO_ROOT="$(/usr/bin/git rev-parse --show-toplevel)"
VALIDATE_INPUTS_ONLY=0
if [ "${1:-}" = "--validate-inputs-only" ]; then
  VALIDATE_INPUTS_ONLY=1
  shift
fi
if [ "$#" -gt 1 ]; then
  echo "linux-script-check: usage: $0 [--validate-inputs-only] [<revision>]" >&2
  exit 2
fi
EXPLICIT_REVISION=0
if [ "$#" -eq 1 ]; then
  EXPLICIT_REVISION=1
fi
REV="${1:-HEAD}"
REV_SHA="$(/usr/bin/git -C "$REPO_ROOT" rev-parse --verify --quiet "$REV^{commit}")" || {
  echo "linux-script-check: not a commit: $REV" >&2
  exit 2
}

LINUX_INPUT_PATHS=(
  ':(glob)skills/**'
  ':(glob)README*.md'
  .github/workflows/e2e-smell-scan.yml
  scripts/ci/ci-local.sh
  scripts/ci/test-reviewer-scanner.py
  scripts/ci/test-eslint-import-resolution.py
  scripts/ci/test-local-eslint-path.sh
  scripts/ci/test-local-eslint-node.py
  scripts/ci/test-linux-script-check.py
  ':(glob)packages/scanner/**'
  ':(glob)scripts/ci/test-*scanner*.py'
  ':(glob)scripts/ci/fixtures/legacy-scanner/**'
  ':(glob)scripts/ci/lib/**'
  ':(glob)scripts/evals/files/**'
  ':(glob)scripts/evals/skills/**'
  scripts/dev/build-scanner-runtime.py
  scripts/dev/scanner-launcher.sh
  scripts/ci/test-debugger-contracts.py
  ':(glob)scripts/ci/test-*-debugger-*.py'
  scripts/dev/linux-script-check.sh
)

print_input_scope() {
  echo "linux-script-check: relevant input scope:"
  echo "  skills/**"
  echo "  README*.md"
  echo "  .github/workflows/e2e-smell-scan.yml"
  echo "  scripts/ci/ci-local.sh"
  echo "  scripts/ci/test-reviewer-scanner.py"
  echo "  scripts/ci/test-eslint-import-resolution.py"
  echo "  scripts/ci/test-local-eslint-path.sh"
  echo "  scripts/ci/test-local-eslint-node.py"
  echo "  scripts/ci/test-linux-script-check.py"
  echo "  packages/scanner/**"
  echo "  scripts/ci/test-*scanner*.py"
  echo "  scripts/ci/fixtures/legacy-scanner/**"
  echo "  scripts/ci/lib/**"
  echo "  scripts/evals/files/**"
  echo "  scripts/evals/skills/**"
  echo "  scripts/dev/build-scanner-runtime.py"
  echo "  scripts/dev/scanner-launcher.sh"
  echo "  scripts/ci/test-debugger-contracts.py"
  echo "  scripts/ci/test-*-debugger-*.py"
  echo "  scripts/dev/linux-script-check.sh"
}

if [ "$EXPLICIT_REVISION" -eq 0 ]; then
  relevant_status="$(/usr/bin/git -c core.quotePath=true -C "$REPO_ROOT" status \
    --short --untracked-files=all -- "${LINUX_INPUT_PATHS[@]}")" || {
      echo "linux-script-check: cannot inspect relevant worktree inputs" >&2
      exit 2
    }
  if [ -n "$relevant_status" ]; then
    echo "linux-script-check: default HEAD snapshot excludes these relevant dirty or untracked worktree inputs:" >&2
    printf '%s\n' "$relevant_status" >&2
    print_input_scope >&2
    echo "linux-script-check: commit the relevant inputs, then rerun; or pass an explicit commit only when intentionally validating that immutable revision" >&2
    exit 2
  fi
  if [ "$VALIDATE_INPUTS_ONLY" -eq 1 ]; then
    echo "linux-script-check: validated default HEAD snapshot; relevant worktree inputs are clean"
    print_input_scope
    exit 0
  fi
elif [ "$VALIDATE_INPUTS_ONLY" -eq 1 ]; then
  echo "linux-script-check: validated explicit commit-only revision $REV_SHA; worktree changes intentionally ignored"
  print_input_scope
  exit 0
fi

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
  "$DOCKER" run --init --rm -i --network=bridge "$IMAGE" /bin/bash -c '
    set -euo pipefail
    export DEBIAN_FRONTEND=noninteractive
    export PATH=/usr/local/bin:/usr/bin:/bin:/usr/sbin:/sbin
    # The launcher uses this trusted standard path; reject an incompatible image
    # before package installation, source extraction, or any test can run.
    /usr/local/bin/node -e "if (Number(process.versions.node.split(\".\")[0]) < 22) process.exit(2)"
    apt-get update -qq >/dev/null
    apt-get install -y -qq --no-install-recommends python3 ripgrep git ca-certificates >/dev/null
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
    # Freshness is mandatory before testing copied installed-skill consumers.
    su checker -s /bin/bash -c "umask 022 && python3 -I -B scripts/dev/build-scanner-runtime.py --check"
    for suite in \
      scripts/ci/test-scanner-runtime.py \
      scripts/ci/test-scanner-launcher.py \
      scripts/ci/test-scanner-node-performance.py \
      scripts/ci/test-reviewer-scanner.py \
      scripts/ci/test-eslint-import-resolution.py \
      scripts/ci/test-local-eslint-node.py \
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
      # umask 022 matches the hosted runner; user defaults may be 002, which
      # makes test-created tool directories group-writable and correctly refused.
      # Any suite failure exits 1, which the pre-push hook treats as blocking.
      case "$suite" in
        *.sh) suite_command="/bin/bash -p $suite" ;;
        *) suite_command="python3 -B $suite" ;;
      esac
      su checker -s /bin/bash -c "umask 022 && $suite_command" || exit 1
    done
  '
echo "==> linux-script-check: pass"
