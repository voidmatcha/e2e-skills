#!/bin/bash -p
# Current product and shared evaluation-harness checks (no historical raw data).
# Use ci-evidence.sh with a verified HF restore for frozen historical replay.

builtin set -uo pipefail

# Establish the command trust boundary before resolving the repository or
# running any external command. Non-interactive Bash imports exported
# functions before this file starts, so remove them before command dispatch.
PATH="/usr/bin:/bin:/usr/sbin:/sbin"
builtin export PATH
builtin unset CDPATH ENV BASH_ENV GLOBIGNORE
while IFS= builtin read -r imported_function; do
  builtin unset -f "$imported_function"
done < <(builtin compgen -A function)
builtin shopt -u expand_aliases
builtin unalias -a 2>/dev/null || true

QUIET=0
CI_MODE=full
CI_BASE=""
CI_PLAN=0
CI_MODE_SET=0
while [ "$#" -gt 0 ]; do
  case "$1" in
    --quiet) QUIET=1; shift ;;
    --full)
      [ "$CI_MODE_SET" = "0" ] || { echo "ci-local: conflicting modes" >&2; exit 2; }
      CI_MODE_SET=1; CI_MODE=full; shift ;;
    --changed)
      [ "$CI_MODE_SET" = "0" ] && [ "$#" -ge 2 ] && [ -n "$2" ] && [[ "$2" != --* ]] || {
        echo "ci-local: --changed requires one BASE and no other mode" >&2; exit 2;
      }
      CI_MODE_SET=1; CI_MODE=scoped; CI_BASE="$2"; shift 2 ;;
    --plan) CI_PLAN=1; shift ;;
    *) echo "usage: ci-local.sh [--quiet] [--full | --changed BASE] [--plan]" >&2; exit 2 ;;
  esac
done

SCRIPT_DIR="${BASH_SOURCE[0]%/*}"
[ "$SCRIPT_DIR" = "${BASH_SOURCE[0]}" ] && SCRIPT_DIR="."
REPO_ROOT="$(builtin cd -- "$SCRIPT_DIR/../.." && builtin pwd -P)" || {
  echo "ci-local.sh: cannot resolve repo root" >&2
  exit 1
}
builtin cd -- "$REPO_ROOT" || {
  echo "ci-local.sh: cannot cd to $REPO_ROOT" >&2
  exit 1
}

if [ "${E2E_SKILLS_SKIP_CI_LOCAL:-}" = "1" ]; then
  echo "ci-local: refusing E2E_SKILLS_SKIP_CI_LOCAL=1; the must-pass gate cannot report success without running" >&2
  exit 2
fi
if [ "${E2E_SKILLS_SKIP_SECURITY:-0}" = "1" ]; then
  echo "ci-local: refusing E2E_SKILLS_SKIP_SECURITY=1; must-pass stages cannot be skipped" >&2
  exit 2
fi
if [ "${E2E_SKILLS_SKIP_PARITY_SMOKE:-0}" = "1" ]; then
  echo "ci-local: refusing E2E_SKILLS_SKIP_PARITY_SMOKE=1; must-pass stages cannot be skipped" >&2
  exit 2
fi
if [ "${E2E_SKILLS_SKIP_SMELL_SCAN:-0}" = "1" ]; then
  echo "ci-local: refusing E2E_SKILLS_SKIP_SMELL_SCAN=1; must-pass stages cannot be skipped" >&2
  exit 2
fi

CURRENT_STEP=""
CURRENT_STEP_STARTED=0
STEP_NAMES=()
STEP_DURATIONS=()

finish_step() {
  [ "$QUIET" = "1" ] && return
  [ -n "$CURRENT_STEP" ] || return 0

  local elapsed=$((SECONDS - CURRENT_STEP_STARTED))
  echo "-- completed: $CURRENT_STEP (${elapsed}s) --"
  STEP_NAMES[${#STEP_NAMES[@]}]="$CURRENT_STEP"
  STEP_DURATIONS[${#STEP_DURATIONS[@]}]="$elapsed"
  CURRENT_STEP=""
}

step() {
  [ "$QUIET" = "1" ] && return
  finish_step
  CURRENT_STEP="$*"
  CURRENT_STEP_STARTED=$SECONDS
  echo "-- $CURRENT_STEP --"
}

print_timing_summary() {
  [ "$QUIET" = "1" ] && return
  finish_step
  echo ""
  echo "CI stage timings (slowest first):"
  {
    local index
    for ((index = 0; index < ${#STEP_NAMES[@]}; index++)); do
      printf '%d\t%s\n' "${STEP_DURATIONS[$index]}" "${STEP_NAMES[$index]}"
    done
  } | /usr/bin/sort -t $'\t' -k1,1nr | while IFS=$'\t' read -r duration name; do
    printf '  %5ss  %s\n' "$duration" "$name"
  done
}
fail() { echo "ci-local: $1 failed" >&2; exit 1; }

step "Python isolation bootstrap"
source "$REPO_ROOT/scripts/ci/lib/init-python-isolation.sh" ||
  fail "isolated Python initialization"
run_python -c 'import sys; assert __debug__; raise SystemExit(0)' ||
  fail "isolated Python runner contract"

# Full runs do not depend on the selector, preserving the default gate.
CI_GROUPS="generator verification install debuggers behavioral evidence holdout scanner harness fixtures tooling preflight postfix parity selfscan"
CI_SELECTED="$CI_GROUPS"
CI_REASON="explicit or default full CI"
if [ "$CI_MODE" = "scoped" ]; then
  if CI_SELECTION="$(run_python scripts/ci/lib/ci-scope.py --repo "$REPO_ROOT" --base "$CI_BASE")"; then
    CI_VALID=1
    {
      IFS= read -r CI_MODE &&
      IFS= read -r CI_REASON &&
      IFS= read -r CI_SELECTED &&
      ! IFS= read -r CI_EXTRA
    } <<< "$CI_SELECTION" || CI_VALID=0
    case "$CI_MODE" in full|scoped) ;; *) CI_VALID=0 ;; esac
    [ -n "$CI_REASON" ] && [ -n "$CI_SELECTED" ] || CI_VALID=0
    [ "$CI_SELECTED" = "-" ] && CI_SELECTED=""
    for CI_GROUP in $CI_SELECTED; do
      [[ " $CI_GROUPS " == *" $CI_GROUP "* ]] || CI_VALID=0
    done
    if [ "$CI_VALID" != "1" ]; then
      CI_MODE=full; CI_SELECTED="$CI_GROUPS"; CI_REASON="invalid selector result; full CI required"
    fi
  else
    CI_MODE=full; CI_SELECTED="$CI_GROUPS"; CI_REASON="selector unavailable; full CI required"
  fi
fi
[ "$CI_MODE" = "full" ] && CI_SELECTED="$CI_GROUPS"
selected() { [[ " $CI_SELECTED " == *" $1 "* ]]; }
echo "ci-local: $CI_MODE plan: $CI_REASON"
echo "ci-local: always run: isolation, shell syntax, source/security, review, documentation/release contracts"
for CI_GROUP in $CI_GROUPS; do
  if selected "$CI_GROUP"; then
    echo "ci-local: run group: $CI_GROUP"
  else
    echo "ci-local: omitted group: $CI_GROUP (changed scope)"
  fi
done
[ "$CI_PLAN" = "1" ] && exit 0

# Verification imports the eval runner to read its pinned digests. Python
# invalidates a cached .pyc by source mtime, which misses an edit made in the
# same second as the cache, so an inherited cache can serve retired pins to the
# very test that exists to catch them. Dropping the caches here is what closes
# that path: every import below then compiles from source. Exporting
# PYTHONDONTWRITEBYTECODE would not, because the eval scripts pass a strict
# environment allowlist and drop it. Caches written during this run are the
# next run's inheritance, and this line removes them then.
/usr/bin/find scripts skills -type d -name __pycache__ -prune -exec /bin/rm -rf {} + 2>/dev/null || true

step "Shell syntax"
SHELL_ENUMERATOR="$REPO_ROOT/scripts/ci/lib/enumerate-shell-files.sh"
if [ ! -x "$SHELL_ENUMERATOR" ]; then
  fail "trusted shell enumerator unavailable"
fi
if ! SHELL_FILES=$(/bin/bash -p "$SHELL_ENUMERATOR" "$REPO_ROOT"); then
  fail "shell enumeration"
fi
SHELL_FILE_COUNT=0
while IFS= read -r file; do
  [ -z "$file" ] && continue
  /bin/bash -p -n "$file" || fail "shell syntax: $file"
  SHELL_FILE_COUNT=$((SHELL_FILE_COUNT + 1))
done <<< "$SHELL_FILES"
[ "$SHELL_FILE_COUNT" -gt 0 ] || fail "shell enumeration returned zero files"
[ "$QUIET" = "1" ] || echo "  all $SHELL_FILE_COUNT shell scripts parse"

step "Source and security contracts"
run_python scripts/ci/test-shell-enumeration.py ||
  fail "test-shell-enumeration.py"
run_python scripts/ci/test-security-gates.py ||
  fail "test-security-gates.py"
run_python scripts/ci/test-python-invocation.py ||
  fail "test-python-invocation.py"
run_python scripts/ci/test-eval-schema.py ||
  fail "test-eval-schema.py"
run_python scripts/ci/test-ci-scope.py || fail "test-ci-scope.py"
run_python scripts/ci/test-self-scan-view.py ||
  fail "test-self-scan-view.py"

step "Review checks"
# Includes prompt-first installation, translated README parity, and model-specific evidence boundaries.
if [ "$QUIET" = "1" ]; then
  /bin/bash -p scripts/ci/review.sh --quiet >/dev/null 2>&1 || fail "review.sh"
else
  /bin/bash -p scripts/ci/review.sh || fail "review.sh"
fi

step "Current documentation contracts"
run_python scripts/ci/test-debugger-contracts.py || fail "test-debugger-contracts.py"

run_python scripts/ci/test-current-docs.py || fail "test-current-docs.py"

run_python scripts/ci/test-release-claims.py || fail "test-release-claims.py"
run_python scripts/ci/test-pending-markers.py || fail "test-pending-markers.py"

step "Trusted Node.js runtime"
# Node comes from an absolute, non-writable path outside the repository. The
# default list covers system and Homebrew installs; E2E_SKILLS_NODE_BIN lets a
# version-manager install (nvm, fnm, asdf) satisfy the SAME checks instead of
# being unable to run this gate at all. Values are passed as argv, not env, so
# the isolated Python runner cannot drop them.
if ! NODE_BIN="$(run_python -c '
import os
import sys
from pathlib import Path

repository = Path(sys.argv[1]).resolve()


def trusted(raw):
    if not raw.startswith("/"):
        return None
    try:
        resolved = Path(raw).resolve(strict=True)
    except OSError:
        return None
    if not resolved.is_file() or not os.access(resolved, os.X_OK):
        return None
    # Mirror the hosted gate: refuse an interpreter that group or other users can
    # rewrite, and refuse one shipped inside the repository under review.
    if resolved.stat().st_mode & 0o022:
        return None
    if resolved == repository or repository in resolved.parents:
        return None
    return resolved


override = sys.argv[2]
candidates = (override,) if override else (
    "/opt/homebrew/bin/node",
    "/usr/local/bin/node",
    "/usr/bin/node",
    "/bin/node",
)
for raw in candidates:
    accepted = trusted(raw)
    if accepted is not None:
        print(accepted)
        raise SystemExit(0)
raise SystemExit(1)
' "$REPO_ROOT" "${E2E_SKILLS_NODE_BIN:-}")"; then
  fail "trusted Node.js runtime resolution"
fi
[ -n "$NODE_BIN" ] || fail "trusted Node.js runtime unavailable"

if selected generator; then
step "Generator contracts"
run_python scripts/ci/test-generator-router.py || fail "test-generator-router.py"

fi

if selected verification; then
step "Verification-rule parity"
# Check the terminal proof boundary itself, not incidental mentions in the V6 packet instructions.
/bin/bash -p scripts/ci/check-verification-parity.sh || fail "check-verification-parity.sh"

fi

if selected install; then
step "Codex agent packaging"
/bin/bash -p scripts/ci/test-codex-agents.sh || fail "test-codex-agents.sh"
/bin/bash -p scripts/ci/test-claude-agents.sh || fail "test-claude-agents.sh"
run_python scripts/ci/test-codex-agent-install.py ||
  fail "test-codex-agent-install.py"
run_python scripts/ci/test-codex-manifest.py ||
  fail "test-codex-manifest.py"
run_python scripts/ci/test-codex-smoke-contract.py ||
  fail "test-codex-smoke-contract.py"
run_python scripts/ci/test-reinstall-skills.py ||
  fail "test-reinstall-skills.py"
run_python scripts/ci/test-all-in-one-install.py ||\
  fail "test-all-in-one-install.py"

fi

if selected behavioral; then
step "Behavioral eval harness"
/bin/bash -p scripts/ci/test-behavioral-evals.sh || fail "test-behavioral-evals.sh"
run_python scripts/ci/test-assertion-contracts.py || fail "test-assertion-contracts.py"
run_python scripts/ci/test-routing-contract.py || fail "test-routing-contract.py"
run_python scripts/ci/test-linux-script-check.py || fail "test-linux-script-check.py"
run_python scripts/ci/test-residual-redos-budget.py ||
  fail "test-residual-redos-budget.py"

fi

if selected debuggers; then
step "Debugger contracts"
run_python scripts/ci/test-cypress-debugger-artifact-download.py ||
  fail "test-cypress-debugger-artifact-download.py"
run_python scripts/ci/test-cypress-debugger-report-publish.py ||
  fail "test-cypress-debugger-report-publish.py"
run_python scripts/ci/test-playwright-debugger-artifact-download.py ||
  fail "test-playwright-debugger-artifact-download.py"
run_python scripts/ci/test-playwright-debugger-report-publish.py ||
  fail "test-playwright-debugger-report-publish.py"

fi

if selected evidence; then
step "B-lite evidence contract"
"$NODE_BIN" --test examples/react-optimistic-write/scripts/test-b-lite-evidence-tools.mjs ||
  fail "test-b-lite-evidence-tools.mjs"
"$NODE_BIN" examples/react-optimistic-write/scripts/verify-b-lite-evidence.mjs ||
  fail "verify-b-lite-evidence.mjs"

fi

if selected holdout; then
step "Labeled reviewer holdout"
LC_ALL=C LC_CTYPE=C LANG=C /bin/bash -p scripts/ci/test-reviewer-holdout.sh ||
  fail "test-reviewer-holdout.sh"

fi

if selected scanner; then
step "Reviewer scanner contracts"
run_python scripts/ci/test-scanner-scope-graph.py ||
  fail "test-scanner-scope-graph.py"
run_python scripts/ci/test-scanner-scope-watch.py ||
  fail "test-scanner-scope-watch.py"
run_python scripts/ci/test-scanner-scope-lexer.py ||
  fail "test-scanner-scope-lexer.py"
run_python scripts/ci/test-scanner-scope-paths.py ||
  fail "test-scanner-scope-paths.py"
run_python scripts/ci/test-scanner-scope-worker.py ||
  fail "test-scanner-scope-worker.py"
run_python scripts/ci/test-scanner-worker-integration.py ||
  fail "test-scanner-worker-integration.py"
run_python scripts/ci/test-scanner-catch-discovery.py ||
  fail "test-scanner-catch-discovery.py"
run_python scripts/ci/test-scanner-try-catch-v1.py ||
  fail "test-scanner-try-catch-v1.py"
run_python scripts/ci/test-scanner-conditional-discovery.py ||
  fail "test-scanner-conditional-discovery.py"
run_python scripts/ci/test-scanner-conditional-integration.py ||
  fail "test-scanner-conditional-integration.py"
run_python scripts/ci/test-scanner-assertion-token-guard.py ||
  fail "test-scanner-assertion-token-guard.py"
run_python scripts/ci/test-scanner-rule-scope-predicate-cache.py ||
  fail "test-scanner-rule-scope-predicate-cache.py"
run_python scripts/ci/test-reviewer-scanner.py ||
  fail "test-reviewer-scanner.py"

fi

if selected harness; then
step "Current evaluation harness contracts"
run_python scripts/ci/test-reviewer-harness.py || fail "test-reviewer-harness.py"
run_python scripts/ci/test-reviewer-auth-retry.py || fail "test-reviewer-auth-retry.py"
run_python scripts/ci/test-reviewer-usage-capture.py || fail "test-reviewer-usage-capture.py"

fi

if selected fixtures; then
step "Executable fixture contracts"
run_python scripts/evals/run-fixture-faults.py --validate-only >/dev/null ||
  fail "run-fixture-faults.py --validate-only"
run_python scripts/ci/test-fixture-faults.py ||
  fail "test-fixture-faults.py"
run_python scripts/ci/test-external-evidence.py ||
  fail "test-external-evidence.py"
run_python scripts/evals/run-playwright-semantic-probes.py --validate-only >/dev/null ||
  fail "run-playwright-semantic-probes.py --validate-only"
run_python scripts/ci/test-playwright-semantic-probes.py ||
  fail "test-playwright-semantic-probes.py"
run_python scripts/evals/run-playwright-timeout-zero-probe.py --validate-only >/dev/null ||
  fail "run-playwright-timeout-zero-probe.py --validate-only"
run_python scripts/ci/test-playwright-timeout-zero-probe.py ||
  fail "test-playwright-timeout-zero-probe.py"
run_python scripts/evals/run-cypress-timeout-zero-probe.py --validate-only >/dev/null ||
  fail "run-cypress-timeout-zero-probe.py --validate-only"
run_python scripts/ci/test-cypress-timeout-zero-probe.py ||
  fail "test-cypress-timeout-zero-probe.py"

fi

if selected tooling; then
step "Local ESLint path"
run_python scripts/ci/test-eslint-import-resolution.py --node "$NODE_BIN" ||
  fail "test-eslint-import-resolution.py"
/bin/bash -p scripts/ci/test-local-eslint-path.sh || fail "test-local-eslint-path.sh"
run_python scripts/ci/test-reviewer-trust-contract.py ||
  fail "test-reviewer-trust-contract.py"
run_python scripts/ci/test-reviewer-check.py ||
  fail "test-reviewer-check.py"
run_python scripts/ci/test-reviewer-probe.py ||
  fail "test-reviewer-probe.py"
run_python scripts/evals/hybrid-check-pilot/check-docker-matrix/test_notepad_adapter_v1.py ||
  fail "test_notepad_adapter_v1.py"
run_python scripts/evals/hybrid-check-pilot/check-docker-matrix/test_passport_adapter_v1.py ||
  fail "test_passport_adapter_v1.py"
run_python scripts/dev/reviewer-contract.py ||
  fail "reviewer-contract.py"
run_python scripts/ci/test-reviewer-output-discipline-v2.py ||
  fail "test-reviewer-output-discipline-v2.py"
run_python scripts/ci/test-scanner-bounded-rule-v1.py ||
  fail "test-scanner-bounded-rule-v1.py"
run_python scripts/ci/test-scanner-vendored-bundle-v1.py ||
  fail "test-scanner-vendored-bundle-v1.py"
run_python scripts/ci/test-scanner-determinism-v1.py ||
  fail "test-scanner-determinism-v1.py"
run_python scripts/ci/test-scanner-manifest-v1.py ||
  fail "test-scanner-manifest-v1.py"

fi

if selected preflight; then
step "PR preflight contracts"
run_python scripts/ci/test-pr-preflight.py || fail "test-pr-preflight.py"

fi

if selected postfix; then
step "Post-fix verifier"
run_python scripts/ci/test-verify-fixes.py || fail "test-verify-fixes.py"

fi

if selected parity; then
step "Pattern parity drift smoke test"
run_python scripts/ci/test-parity-wrapper.py ||
  fail "test-parity-wrapper.py"
if [ "$QUIET" = "1" ]; then
  /bin/bash -p scripts/ci/test-parity.sh >/dev/null 2>&1 || fail "test-parity.sh"
else
  /bin/bash -p scripts/ci/test-parity.sh || fail "test-parity.sh"
fi

fi

if selected selfscan; then
step "E2E smell scan"
# Self-scan checks the repository-owned JS/TS surfaces. `testbed/` is an
# intentionally gitignored collection of third-party repositories used for
# manual validation; scanning `.` with --no-ignore would make their findings
# part of this bundle's release gate. Target-project ESLint is default-off;
# test-local-eslint-path.sh separately exercises its explicit trust opt-in.
# scan.sh runs Tier 2 only when ast-grep resolves from E2E_SMELL_AST_GREP_BIN or
# its fixed candidate paths. Hosted CI installs it; a host without it passes
# this gate on Tier 3 alone, so make that visible instead of silent.
SELF_SCAN_AST_GREP=""
for SELF_SCAN_AST_CANDIDATE in "${E2E_SMELL_AST_GREP_BIN:-}" \
  /opt/homebrew/bin/ast-grep /usr/local/bin/ast-grep /usr/bin/ast-grep; do
  if [ -n "$SELF_SCAN_AST_CANDIDATE" ] && [ -x "$SELF_SCAN_AST_CANDIDATE" ]; then
    SELF_SCAN_AST_GREP="$SELF_SCAN_AST_CANDIDATE"
    break
  fi
done
if [ -z "$SELF_SCAN_AST_GREP" ]; then
  echo "ci-local: WARNING: ast-grep not found; the self-scan P0 gate below covers Tier 3 only (hosted CI also runs Tier 2)" >&2
fi
# The fixed Notepad pilot is an intentional negative control required by the
# adapter contracts. Verify its original findings, then scan an identity-checked
# temporary view excluding only that exact frozen file. Product bytes and the
# p0-candidate threshold remain unchanged; drift or any other candidate fails.
if [ "$QUIET" = "1" ]; then
  run_python scripts/ci/lib/self-scan-view.py "$REPO_ROOT" >/dev/null 2>&1 ||
    fail "repository self-scan view"
else
  run_python scripts/ci/lib/self-scan-view.py "$REPO_ROOT" ||
    fail "repository self-scan view"
fi

fi

if [ "$QUIET" = "1" ] && [ "$CI_MODE" = "scoped" ]; then
  echo "ci-local: scoped checks passed (full CI not run)"
fi
[ "$QUIET" = "1" ] || {
  print_timing_summary
  echo ""
  echo "========================================"
  if [ "$CI_MODE" = "full" ]; then
    echo "  ci-local: all checks passed"
  else
    echo "  ci-local: scoped checks passed (full CI not run)"
  fi
  echo "========================================"
}
exit 0
