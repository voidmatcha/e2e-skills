#!/usr/bin/env bash
# Local mirror of the e2e-skills GitHub Actions checks.

set -uo pipefail

QUIET=0
[ "${1:-}" = "--quiet" ] && QUIET=1

REPO_ROOT="$(cd "$(dirname "$0")/../.." && pwd)" || {
  echo "ci-local.sh: cannot resolve repo root" >&2
  exit 1
}
cd "$REPO_ROOT" || {
  echo "ci-local.sh: cannot cd to $REPO_ROOT" >&2
  exit 1
}

if [ "${E2E_SKILLS_SKIP_CI_LOCAL:-}" = "1" ]; then
  echo "ci-local skipped via E2E_SKILLS_SKIP_CI_LOCAL=1" >&2
  exit 0
fi

step() { [ "$QUIET" = "1" ] || echo "-- $* --"; }
fail() { echo "ci-local: $1 failed" >&2; exit 1; }

step "Shell syntax"
while IFS= read -r file; do
  [ -z "$file" ] && continue
  bash -n "$file" || fail "shell syntax: $file"
done < <(find scripts -name '*.sh' -type f 2>/dev/null)
[ "$QUIET" = "1" ] || echo "  all shell scripts parse"

step "Review checks"
if [ "$QUIET" = "1" ]; then
  bash scripts/ci/review.sh --quiet >/dev/null 2>&1 || fail "review.sh"
else
  bash scripts/ci/review.sh || fail "review.sh"
fi

if [ "${E2E_SKILLS_SKIP_PARITY_SMOKE:-}" != "1" ]; then
  step "Pattern parity drift smoke test"
  if [ "$QUIET" = "1" ]; then
    bash scripts/ci/test-parity.sh >/dev/null 2>&1 || fail "test-parity.sh"
  else
    bash scripts/ci/test-parity.sh || fail "test-parity.sh"
  fi
fi

if [ "${E2E_SKILLS_SKIP_SMELL_SCAN:-}" != "1" ]; then
  step "E2E smell scan"
  if [ "$QUIET" = "1" ]; then
    E2E_SMELL_FAIL_ON=p0 ./skills/e2e-reviewer/scripts/scan.sh . >/dev/null 2>&1 || fail "skills/e2e-reviewer/scripts/scan.sh"
  else
    E2E_SMELL_FAIL_ON=p0 ./skills/e2e-reviewer/scripts/scan.sh . || fail "skills/e2e-reviewer/scripts/scan.sh"
  fi
fi

[ "$QUIET" = "1" ] || {
  echo ""
  echo "========================================"
  echo "  ci-local: all checks passed"
  echo "========================================"
}
exit 0
