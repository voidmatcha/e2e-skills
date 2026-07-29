#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
TMP="$(mktemp -d "${TMPDIR:-/tmp}/e2e-behavioral.XXXXXX")"
trap 'rm -rf "$TMP"' EXIT

cat >"$TMP/fake-runner" <<'SH'
#!/usr/bin/env bash
prompt=$(cat)
case "$prompt" in
  *"Read and follow"*"e2e-reviewer"*) echo "line 10: a bare locator object is truthy, so this assertion cannot fail." ;;
  *"Read and follow"*"cypress-debugger"*) echo "The report timed out because the element selector was not found; fix the locator after checking rendering." ;;
  *) echo "The test may need stronger validation." ;;
esac
SH
chmod +x "$TMP/fake-runner"

python3 "$ROOT/scripts/evals/run-behavioral-evals.py" \
  --runner "$TMP/fake-runner" \
  --repetitions 2 \
  --output "$TMP/report.json" >"$TMP/stdout"

python3 - "$TMP/report.json" <<'PY'
import json, pathlib, sys
report = json.loads(pathlib.Path(sys.argv[1]).read_text())
summary = report["summary"]
assert summary == {
    "with_skill_pass_rate": 1.0,
    "without_skill_pass_rate": 0.0,
    "absolute_lift": 1.0,
    "saturated_cases": [],
    "runs": 8,
}, summary
assert len(report["runs"]) == 8
assert report["complete"] is True
assert all(row["passed"] for row in report["runs"] if row["variant"] == "with_skill")
assert not any(row["passed"] for row in report["runs"] if row["variant"] == "without_skill")
PY

# Live execution must never happen accidentally in ordinary CI.
if python3 "$ROOT/scripts/evals/run-behavioral-evals.py" --runner codex \
  --repetitions 1 --output "$TMP/forbidden.json" >"$TMP/forbidden.out" 2>&1; then
  echo "test-behavioral-evals: live runner worked without --allow-live" >&2
  exit 1
fi
grep -q -- "--allow-live" "$TMP/forbidden.out"

echo "behavioral eval harness: pass"
