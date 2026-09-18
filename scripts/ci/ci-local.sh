#!/bin/bash -p
# Local mirror of the e2e-skills GitHub Actions checks.

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
[ "${1:-}" = "--quiet" ] && QUIET=1

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

# Verification imports the eval runner to read its pinned digests. Python
# invalidates a cached .pyc by source mtime, which misses an edit made in the
# same second as the cache, so an inherited cache can serve retired pins to the
# very test that exists to catch them. Dropping the caches here is what closes
# that path: every import below then compiles from source. Exporting
# PYTHONDONTWRITEBYTECODE would not, because the eval scripts pass a strict
# environment allowlist and drop it. Caches written during this run are the
# next run's inheritance, and this line removes them then.
/usr/bin/find scripts skills -type d -name __pycache__ -prune -exec /bin/rm -rf {} + 2>/dev/null || true

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

step "Evidence freshness preflight"
# A stale evaluated-skill digest is a release blocker and takes well under a
# second to detect. Keep it immediately after the shell trust-boundary check
# and ahead of the multi-minute review stages.
run_python scripts/ci/test-reviewer-evidence-v3.py ||
  fail "test-reviewer-evidence-v3.py"

step "Source and security contracts"
run_python scripts/ci/test-shell-enumeration.py ||
  fail "test-shell-enumeration.py"
run_python scripts/ci/test-security-gates.py ||
  fail "test-security-gates.py"
run_python scripts/ci/test-python-invocation.py ||
  fail "test-python-invocation.py"
run_python scripts/ci/test-eval-schema.py ||
  fail "test-eval-schema.py"
run_python scripts/ci/test-evidence-ledger.py ||
  fail "test-evidence-ledger.py"

step "Release contract preflight"
# Keep cheap, high-signal release blockers ahead of the multi-minute review
# checks. These checks are independent and still run exactly once; this changes
# red-path latency without weakening the green path.
run_python scripts/ci/test-reviewer-release-v1.py ||
  fail "test-reviewer-release-v1.py"
run_python scripts/ci/test-reviewer-release-runner-v1.py ||
  fail "test-reviewer-release-runner-v1.py"
run_python scripts/ci/test-runner-version-resolution-v1.py ||
  fail "test-runner-version-resolution-v1.py"

step "Review checks"
if [ "$QUIET" = "1" ]; then
  /bin/bash -p scripts/ci/review.sh --quiet >/dev/null 2>&1 || fail "review.sh"
else
  /bin/bash -p scripts/ci/review.sh || fail "review.sh"
fi

step "Generator contracts"
run_python scripts/ci/test-generator-contracts.py ||
  fail "test-generator-contracts.py"

step "Verification-rule parity"
/bin/bash -p scripts/ci/check-verification-parity.sh || fail "check-verification-parity.sh"

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

step "Behavioral eval harness"
/bin/bash -p scripts/ci/test-behavioral-evals.sh || fail "test-behavioral-evals.sh"
run_python scripts/ci/test-debugger-contracts.py || fail "test-debugger-contracts.py"
run_python scripts/ci/test-routing-contract.py || fail "test-routing-contract.py"
run_python scripts/ci/test-residual-redos-budget.py ||
  fail "test-residual-redos-budget.py"
run_python scripts/ci/test-cypress-debugger-artifact-download.py ||
  fail "test-cypress-debugger-artifact-download.py"
run_python scripts/ci/test-cypress-debugger-report-publish.py ||
  fail "test-cypress-debugger-report-publish.py"
run_python scripts/ci/test-playwright-debugger-artifact-download.py ||
  fail "test-playwright-debugger-artifact-download.py"
run_python scripts/ci/test-playwright-debugger-report-publish.py ||
  fail "test-playwright-debugger-report-publish.py"

step "B-lite evidence contract"
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
"$NODE_BIN" --test examples/react-optimistic-write/scripts/test-b-lite-evidence-tools.mjs ||
  fail "test-b-lite-evidence-tools.mjs"
"$NODE_BIN" examples/react-optimistic-write/scripts/verify-b-lite-evidence.mjs ||
  fail "verify-b-lite-evidence.mjs"

step "Labeled reviewer holdout"
LC_ALL=C LC_CTYPE=C LANG=C /bin/bash -p scripts/ci/test-reviewer-holdout.sh ||
  fail "test-reviewer-holdout.sh"

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

step "Reviewer benchmark contracts"
run_python scripts/ci/test-reviewer-holdout-v3.py ||
  fail "test-reviewer-holdout-v3.py"
run_python scripts/ci/test-reviewer-fault-causal.py ||
  fail "test-reviewer-fault-causal.py"
run_python scripts/ci/test-reviewer-holdout-v4.py ||
  fail "test-reviewer-holdout-v4.py"
run_python scripts/ci/test-reviewer-fault-causal-v2.py ||
  fail "test-reviewer-fault-causal-v2.py"
run_python scripts/ci/test-reviewer-holdout-v5.py ||
  fail "test-reviewer-holdout-v5.py"
run_python scripts/ci/test-reviewer-fault-causal-v3.py ||
  fail "test-reviewer-fault-causal-v3.py"
run_python scripts/ci/test-debugger-holdout-v1.py ||
  fail "test-debugger-holdout-v1.py"
run_python scripts/ci/test-generator-faultkill-v1.py ||
  fail "test-generator-faultkill-v1.py"
run_python scripts/ci/test-generator-faultkill-runner.py ||
  fail "test-generator-faultkill-runner.py"

step "Independent review contracts"
run_python scripts/ci/test-independent-review.py ||
  fail "test-independent-review.py"
run_python scripts/ci/test-independent-review-evidence.py ||
  fail "test-independent-review-evidence.py"
run_python scripts/ci/test-independent-review-v5-evidence.py ||
  fail "test-independent-review-v5-evidence.py"
run_python scripts/ci/test-independent-review-v6.py ||
  fail "test-independent-review-v6.py"
run_python scripts/ci/test-independent-review-v6-evidence.py ||
  fail "test-independent-review-v6-evidence.py"
# The v7, v8, v10 and v11 unit suites carry adversarial checks that require the
# pinned reference tokenizer. run_python's interpreter has never had it, so those
# checks used to skip themselves silently; the suites now fail closed and run
# inside one hash-locked replay venv instead.
#
# v10 was briefly dropped from this list because its freeze integration rebuilt
# the packet from the working tree and then enforced the caps recorded when the
# phase froze, which left 61 tokens of headroom and failed unrelated product
# edits. It now reproduces its packet from the frozen source snapshot, the way
# v5 and v6 already did, so the archived round no longer budgets live work.
#
# v10 stays in this list after its supersession: its runner, validator and
# canonical archive are frozen byte-for-byte, and its suite still exercises those
# frozen contracts and replays that archive through its evidence wrapper.
# v11 completes the v10 schedule with the consumed v10 r1 attempt carried, and
# reads the inherited v10 packet by digest instead of rebuilding it. Without
# E2E_SKILLS_V11_PINNED_CLAUDE_PATH the v11 suite prints one explicit SKIP for
# its strict live-path round trip; every other check runs.
step "Reference tokenizer contracts"
/bin/bash -p scripts/ci/run-reference-tokenizer-suites.sh \
  scripts/ci/test-independent-review-v7.py \
  scripts/ci/test-independent-review-v8.py \
  scripts/ci/test-independent-review-v10.py \
  scripts/ci/test-independent-review-v11.py ||
  fail "run-reference-tokenizer-suites.sh"
# Each unit suite above also invokes its matching standalone evidence wrapper
# under a poisoned environment and asserts the canonical result. Repeating the
# same four wrappers here rebuilt four identical hash-locked venvs without
# adding coverage. The wrappers remain standalone reproduction commands.

step "Reviewer evidence contracts"
run_python scripts/ci/test-reviewer-evidence.py ||
  fail "test-reviewer-evidence.py"

step "Executable fixture contracts"
run_python scripts/evals/run-fixture-faults.py --validate-only >/dev/null ||
  fail "run-fixture-faults.py --validate-only"
run_python scripts/ci/test-fixture-faults.py ||
  fail "test-fixture-faults.py"
run_python benchmarks/healer-perturbation-v1/test_perturbations.py ||
  fail "healer-perturbation-v1/test_perturbations.py"
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

step "Local ESLint path"
/bin/bash -p scripts/ci/test-local-eslint-path.sh || fail "test-local-eslint-path.sh"
run_python scripts/ci/test-reviewer-trust-contract.py ||
  fail "test-reviewer-trust-contract.py"
run_python scripts/ci/test-reviewer-doc-contracts.py ||
  fail "test-reviewer-doc-contracts.py"
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

step "PR preflight contracts"
run_python scripts/ci/test-pr-preflight.py || fail "test-pr-preflight.py"

step "Post-fix verifier"
run_python scripts/ci/test-verify-fixes.py || fail "test-verify-fixes.py"

step "Pattern parity drift smoke test"
run_python scripts/ci/test-parity-wrapper.py ||
  fail "test-parity-wrapper.py"
if [ "$QUIET" = "1" ]; then
  /bin/bash -p scripts/ci/test-parity.sh >/dev/null 2>&1 || fail "test-parity.sh"
else
  /bin/bash -p scripts/ci/test-parity.sh || fail "test-parity.sh"
fi

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
for SELF_SCAN_ROOT in skills scripts; do
  if [ "$QUIET" = "1" ]; then
    E2E_SMELL_NO_ESLINT_DOWNLOAD=1 E2E_SMELL_FAIL_ON=p0-candidate /bin/bash -p ./skills/e2e-reviewer/scripts/scan.sh "$SELF_SCAN_ROOT" >/dev/null 2>&1 ||
      fail "skills/e2e-reviewer/scripts/scan.sh $SELF_SCAN_ROOT"
  else
    E2E_SMELL_NO_ESLINT_DOWNLOAD=1 E2E_SMELL_FAIL_ON=p0-candidate /bin/bash -p ./skills/e2e-reviewer/scripts/scan.sh "$SELF_SCAN_ROOT" ||
      fail "skills/e2e-reviewer/scripts/scan.sh $SELF_SCAN_ROOT"
  fi
done

[ "$QUIET" = "1" ] || {
  print_timing_summary
  echo ""
  echo "========================================"
  echo "  ci-local: all checks passed"
  echo "========================================"
}
exit 0
