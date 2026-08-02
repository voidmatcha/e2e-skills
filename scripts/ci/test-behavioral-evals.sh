#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
REPO_ROOT="$ROOT"
source "$REPO_ROOT/scripts/ci/lib/init-python-isolation.sh" || exit 2
TMP="$(mktemp -d "${TMPDIR:-/tmp}/e2e-behavioral.XXXXXX")"
trap 'rm -rf "$TMP"' EXIT

cat >"$TMP/fake-runner" <<'SH'
#!/usr/bin/env bash
prompt=$(cat)
case "$prompt" in
  *"BEGIN_TRUSTED_SKILL_SNAPSHOT e2e-reviewer/SKILL.md"*) echo "line 10: a bare locator object is truthy, so this assertion cannot fail." ;;
  *"BEGIN_TRUSTED_SKILL_SNAPSHOT cypress-debugger/SKILL.md"*) echo "The report timed out because the element selector was not found; fix the locator after checking rendering." ;;
  *) echo "The test may need stronger validation." ;;
esac
SH
chmod +x "$TMP/fake-runner"

PYTHONDONTWRITEBYTECODE=1 python3 - \
  "$ROOT/scripts/evals/run-behavioral-evals.py" "$TMP/isolated-home" <<'PY'
import importlib.util
import os
import pathlib
import subprocess
import sys
import tempfile
import time
from unittest.mock import patch

path = pathlib.Path(sys.argv[1])
spec = importlib.util.spec_from_file_location("behavioral_eval_runner", path)
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)

ambient = {
    "PATH": "/usr/bin:/bin",
    "LANG": "C",
    "TMPDIR": "/ambient/tmp",
    "HOME": "/ambient/home",
    "XDG_CONFIG_HOME": "/ambient/config",
    "BASH_ENV": "/ambient/bash-env",
    "ENV": "/ambient/shell-env",
    "NODE_OPTIONS": "--require=/ambient/injected.js",
    "HTTP_PROXY": "http://proxy.invalid",
    "AWS_SECRET_ACCESS_KEY": "ambient-cloud-secret",
    "GENERIC_TOKEN": "ambient-generic-secret",
    "CODEX_HOME": "/auth/codex",
    "OPENAI_API_KEY": "codex-auth",
    "CLAUDE_CONFIG_DIR": "/auth/claude",
    "ANTHROPIC_API_KEY": "claude-auth",
    "CLAUDE_CODE_OAUTH_TOKEN": "claude-oauth-token-123456",
}
home = sys.argv[2]
with patch.dict(os.environ, ambient, clear=True):
    codex = module.clean_env("codex", home)
    claude = module.clean_env("claude", home)
    custom = module.clean_env("/custom/runner", home)
    claude_credentials = module.inherited_runner_credentials("claude")

assert codex["HOME"] == claude["HOME"] == custom["HOME"] == home
assert claude_credentials == {
    "CLAUDE_CODE_OAUTH_TOKEN": ambient["CLAUDE_CODE_OAUTH_TOKEN"]
}
for environment in (codex, claude, custom):
    for blocked in (
        "XDG_CONFIG_HOME", "BASH_ENV", "ENV", "NODE_OPTIONS", "HTTP_PROXY",
        "AWS_SECRET_ACCESS_KEY", "GENERIC_TOKEN", "CODEX_HOME",
        "OPENAI_API_KEY", "CLAUDE_CONFIG_DIR", "ANTHROPIC_API_KEY",
        "CLAUDE_CODE_OAUTH_TOKEN",
    ):
        assert blocked not in environment
for credential in module.CODEX_ENV_KEYS | module.CLAUDE_ENV_KEYS:
    assert credential not in custom

with tempfile.TemporaryDirectory() as case_dir:
    cases_path = pathlib.Path(case_dir) / "cases.json"
    cases_path.write_text(
        '{"schema_version":1,"cases":[{"id":"escape","skill":"../e2e-reviewer",'
        '"task":"x","assertions":[{"type":"contains","value":"x"}]}]}',
        encoding="utf-8",
    )
    try:
        module.load_cases(cases_path)
    except ValueError as exc:
        assert "allowlist" in str(exc)
    else:
        raise AssertionError("skill path traversal unexpectedly accepted")
    cases_path.write_text(
        '{"schema_version":1,"cases":[{"id":"invalid-regex",'
        '"skill":"e2e-reviewer","task":"x","assertions":'
        '[{"type":"regex","value":"("}]}]}',
        encoding="utf-8",
    )
    try:
        module.load_cases(cases_path)
    except ValueError as exc:
        assert "invalid grading regex" in str(exc)
    else:
        raise AssertionError("invalid grading regex unexpectedly accepted")
    for payload, marker in (
        (
            '{"schema_version":1,"schema_version":1,"cases":[]}',
            "duplicate JSON object key",
        ),
        (
            '{"schema_version":1,"cases":[],"unknown":true}',
            "unknown=['unknown']",
        ),
        (
            '{"schema_version":1,"cases":[{"id":"unknown-case",'
            '"skill":"e2e-reviewer","task":"x","assertions":[],'
            '"unknown":true}]}',
            "unknown=['unknown']",
        ),
        (
            '{"schema_version":1,"cases":[{"id":"unknown-assertion",'
            '"skill":"e2e-reviewer","task":"x","assertions":'
            '[{"type":"contains","value":"x","unknown":true}]}]}',
            "unknown=['unknown']",
        ),
    ):
        cases_path.write_text(payload, encoding="utf-8")
        try:
            module.load_cases(cases_path)
        except ValueError as exc:
            assert marker in str(exc), str(exc)
        else:
            raise AssertionError(f"off-schema behavioral JSON accepted: {payload}")

assert module.grade(
    "abc123",
    [{"type": "regex", "value": r"abc\d+"}],
)[0]["passed"] is True
started = time.monotonic()
try:
    module.grade(
        ("a" * 50_000) + "!",
        [{"type": "regex", "value": r"(a+)+$"}],
    )
except module.GradingRegexError as exc:
    assert "timed out" in str(exc)
    assert time.monotonic() - started < 1.0
else:
    raise AssertionError("catastrophic grading regex was not bounded")

class Process:
    returncode = 0
    pid = 12345
    def communicate(self, input=None, timeout=None):
        return "ok", ""
    def poll(self):
        return 0

class CleanupStream:
    def __init__(self, fd):
        self.fd = fd
    def fileno(self):
        return self.fd

class CleanupProcess:
    pid = 24680
    stdout = CleanupStream(10)
    stderr = CleanupStream(11)
    def __init__(self):
        self.wait_calls = 0
    def wait(self, timeout=None):
        self.wait_calls += 1
        if self.wait_calls == 1:
            raise subprocess.TimeoutExpired("runner", timeout)
        return 0
    def poll(self):
        return None

class SelectorKey:
    def __init__(self, fileobj, data):
        self.fileobj = fileobj
        self.data = data

class CleanupSelector:
    def __init__(self, emit_chunk=False):
        self.keys = []
        self.emit_chunk = emit_chunk
    def register(self, stream, _events, name):
        self.keys.append(SelectorKey(stream, name))
    def get_map(self):
        return {index: key for index, key in enumerate(self.keys)}
    def select(self, _timeout):
        return [(self.keys[0], None)] if self.emit_chunk else []
    def close(self):
        pass

def cleanup_killpg(calls, deny_sigterm):
    def killpg(_pid, sig):
        calls.append(sig)
        if deny_sigterm and sig == module.signal.SIGTERM:
            raise PermissionError("operation not permitted")
    return killpg

timeout_process = CleanupProcess()
timeout_signals = []
with patch.object(module.selectors, "DefaultSelector", CleanupSelector), patch.object(
    module.os, "set_blocking"
), patch.object(
    module.time, "monotonic", side_effect=[0.0, 2.0]
), patch.object(
    module.os, "killpg", side_effect=cleanup_killpg(timeout_signals, True)
):
    try:
        module.communicate_bounded(timeout_process, ["runner"], 1)
    except subprocess.TimeoutExpired as exc:
        assert exc.cleanup_attempted is True
        assert any(
            failure.startswith("SIGTERM: PermissionError:")
            for failure in exc.cleanup_failures
        )
    else:
        raise AssertionError("behavioral timeout unexpectedly completed")
assert timeout_signals == [module.signal.SIGTERM, module.signal.SIGKILL]
assert timeout_process.wait_calls == 2

successful_process = CleanupProcess()
successful_signals = []
with patch.object(module.selectors, "DefaultSelector", CleanupSelector), patch.object(
    module.os, "set_blocking"
), patch.object(
    module.time, "monotonic", side_effect=[0.0, 2.0]
), patch.object(
    module.os, "killpg", side_effect=cleanup_killpg(successful_signals, False)
):
    try:
        module.communicate_bounded(successful_process, ["runner"], 1)
    except subprocess.TimeoutExpired as exc:
        assert exc.cleanup_attempted is True
        assert getattr(exc, "cleanup_failures", []) == []
    else:
        raise AssertionError("behavioral timeout unexpectedly completed")
assert successful_signals == [module.signal.SIGTERM, module.signal.SIGKILL]
assert successful_process.wait_calls == 2

output_process = CleanupProcess()
output_signals = []
with patch.object(
    module.selectors, "DefaultSelector", lambda: CleanupSelector(True)
), patch.object(
    module.os, "set_blocking"
), patch.object(
    module.os, "read", return_value=b"x" * (module.MAX_RUNNER_OUTPUT_BYTES + 1)
), patch.object(
    module.time, "monotonic", side_effect=[0.0, 0.1]
), patch.object(
    module.os, "killpg", side_effect=cleanup_killpg(output_signals, True)
):
    try:
        module.communicate_bounded(output_process, ["runner"], 1)
    except ValueError as exc:
        assert "runner output exceeded" in str(exc)
        assert exc.cleanup_attempted is True
        assert any(
            failure.startswith("SIGTERM: PermissionError:")
            for failure in exc.cleanup_failures
        )
    else:
        raise AssertionError("oversized output unexpectedly completed")
assert output_signals == [module.signal.SIGTERM, module.signal.SIGKILL]
assert output_process.wait_calls == 2

case = {
    "id": "reviewer-always-true-locator",
    "skill": "e2e-reviewer",
    "task": "Review {repo}/scripts/ci/fixtures/codex-smoke/silent.spec.ts.",
    "assertions": [{"type": "contains", "value": "ok"}],
}
with patch.object(module.subprocess, "Popen", return_value=Process()) as popen:
    rc, output, _elapsed, evidence = module.run_once(
        "/custom/runner", case, "with_skill", 1,
        runner_executable="/custom/runner",
    )
assert rc == 0 and output == "ok"
command = popen.call_args.args[0]
workspace = pathlib.Path(popen.call_args.kwargs["cwd"])
assert command == ["/custom/runner"]
assert popen.call_args.kwargs["start_new_session"] is True
assert popen.call_args.kwargs["env"]["HOME"] != ambient["HOME"]
assert popen.call_args.kwargs["env"]["PWD"] == str(workspace)
assert evidence["workspace_sha256_before"] == evidence["workspace_sha256_after"]
assert evidence["original_inputs_sha256_before"] == evidence["original_inputs_sha256_after"]
assert evidence["workspace_sha256_before"]

with patch.object(
    module.SHARED_RUNNER,
    "stage_codex_auth",
    side_effect=lambda home: home / ".codex",
), patch.object(module.subprocess, "Popen", return_value=Process()) as popen:
    module.run_once(
        "codex", case, "with_skill", 1,
        runner_executable="/trusted/codex",
        runner_credentials={},
    )
codex_command = popen.call_args.args[0]
assert codex_command[0:8] == [
    "/trusted/codex", "exec", "--ephemeral", "--ignore-user-config",
    "--ignore-rules", "--strict-config", "--skip-git-repo-check", "--sandbox",
]
assert codex_command[-1] == "-"
assert "shell_tool" in codex_command
assert "multi_agent" in codex_command
assert "tools.web_search=false" in codex_command
assert popen.call_args.kwargs["env"]["CODEX_HOME"].endswith("/.codex")
assert "OPENAI_API_KEY" not in popen.call_args.kwargs["env"]
assert popen.call_args.kwargs["start_new_session"] is True

with patch.object(module.subprocess, "Popen", return_value=Process()) as popen:
    module.run_once(
        "claude", case, "with_skill", 1,
        runner_executable="/trusted/claude",
        runner_credentials={"CLAUDE_CODE_OAUTH_TOKEN": "oauth-token-123456789"},
    )
assert popen.call_args.args[0] == [
    "/trusted/claude", "-p", "--safe-mode", "--setting-sources", "",
    "--strict-mcp-config", "--no-session-persistence", "--tools", "",
    "--permission-mode", "plan",
]
claude_env = popen.call_args.kwargs["env"]
assert claude_env["CLAUDE_CODE_OAUTH_TOKEN"] == "oauth-token-123456789"
assert "CLAUDE_CONFIG_DIR" not in claude_env
assert "ANTHROPIC_API_KEY" not in claude_env
assert popen.call_args.kwargs["start_new_session"] is True

with tempfile.TemporaryDirectory() as prompt_dir:
    prompt_workspace = pathlib.Path(prompt_dir)
    module.prepare_workspace(case, prompt_workspace)
    with_skill_prompt = module.render_prompt(case, "with_skill", prompt_workspace)
    without_skill_prompt = module.render_prompt(
        case, "without_skill", prompt_workspace
    )
assert "BEGIN_TRUSTED_SKILL_SNAPSHOT e2e-reviewer/SKILL.md" in with_skill_prompt
assert "BEGIN_UNTRUSTED_TASK_ARTIFACT scripts/ci/fixtures/codex-smoke/silent.spec.ts" in with_skill_prompt
assert "expect(page.locator('[data-testid=\"order-summary\"]'))" in with_skill_prompt
assert "You have no shell, filesystem, network, app, image, or subagent tools" in with_skill_prompt
assert "BEGIN_TRUSTED_SKILL_SNAPSHOT" not in without_skill_prompt
assert "BEGIN_UNTRUSTED_TASK_ARTIFACT" in without_skill_prompt

with patch.dict(module.os.environ, {"PATH": "/attacker/bin"}, clear=False), patch.object(
    module.shutil, "which", return_value=None
) as which:
    try:
        module.resolve_runner_executable("claude")
    except ValueError as exc:
        assert "explicit --runner-path" in str(exc)
    else:
        raise AssertionError("ambient PATH unexpectedly bound credentialed runner")
    assert "/attacker/bin" not in which.call_args.kwargs["path"]
PY

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
assert all(
    row["workspace_sha256_before"] == row["workspace_sha256_after"]
    for row in report["runs"]
)
assert all(
    row["original_inputs_sha256_before"] == row["original_inputs_sha256_after"]
    for row in report["runs"]
)
PY

cat >"$TMP/redos-cases.json" <<'JSON'
{
  "schema_version": 1,
  "cases": [
    {
      "id": "redos",
      "skill": "e2e-reviewer",
      "task": "Review {repo}/scripts/ci/fixtures/codex-smoke/silent.spec.ts.",
      "assertions": [{"type": "regex", "value": "(a+)+$"}]
    }
  ]
}
JSON
cat >"$TMP/redos-runner" <<'SH'
#!/usr/bin/env bash
cat >/dev/null
head -c 50000 /dev/zero | tr '\0' a
printf '!\n'
SH
chmod +x "$TMP/redos-runner"
if python3 "$ROOT/scripts/evals/run-behavioral-evals.py" \
  --cases "$TMP/redos-cases.json" \
  --runner "$TMP/redos-runner" \
  --repetitions 1 \
  --output "$TMP/redos-report.json" >/dev/null 2>&1; then
  echo "test-behavioral-evals: catastrophic grading regex was scoreable" >&2
  exit 1
fi
python3 - "$TMP/redos-report.json" <<'PY'
import json, pathlib, sys
report = json.loads(pathlib.Path(sys.argv[1]).read_text())
assert len(report["runs"]) == 2
for row in report["runs"]:
    assert row["passed"] is False
    assert row["exit_code"] == 125
    assert "grading regex timed out" in row["error"]
    assert row["assertions"][0]["passed"] is False
    assert "grading regex timed out" in row["assertions"][0]["error"]
PY

cat >"$TMP/oversized-output-runner" <<'SH'
#!/usr/bin/env bash
set -euo pipefail
cat >/dev/null
head -c 1048577 /dev/zero | tr '\0' x
SH
chmod +x "$TMP/oversized-output-runner"
if python3 "$ROOT/scripts/evals/run-behavioral-evals.py" \
  --case reviewer-always-true-locator \
  --runner "$TMP/oversized-output-runner" \
  --repetitions 1 \
  --output "$TMP/oversized-output-report.json" >/dev/null 2>&1; then
  echo "test-behavioral-evals: oversized output was scoreable" >&2
  exit 1
fi
python3 - "$TMP/oversized-output-report.json" <<'PY'
import json, pathlib, sys
report = json.loads(pathlib.Path(sys.argv[1]).read_text())
assert report["complete"] is True
assert len(report["runs"]) == 2
for row in report["runs"]:
    assert row["passed"] is False
    assert row["exit_code"] == 125
    assert row["output"] == ""
    assert row["error"] == "runner output exceeded 1048576 byte capture limit"
    assert row["cleanup_attempted"] is True
    assert row["cleanup_failures"] == []
    assert row["workspace_sha256_before"] == row["workspace_sha256_after"]
    assert row["original_inputs_sha256_before"] == row[
        "original_inputs_sha256_after"
    ]
PY

cat >"$TMP/workspace-writer" <<'SH'
#!/usr/bin/env bash
cat >/dev/null
printf '\nmutated\n' >> scripts/ci/fixtures/codex-smoke/silent.spec.ts
echo "ok"
SH
chmod +x "$TMP/workspace-writer"
if python3 "$ROOT/scripts/evals/run-behavioral-evals.py" \
  --case reviewer-always-true-locator \
  --runner "$TMP/workspace-writer" \
  --repetitions 1 \
  --output "$TMP/mutation-report.json" >/dev/null 2>&1; then
  echo "test-behavioral-evals: staged workspace mutation was not rejected" >&2
  exit 1
fi
python3 - "$TMP/mutation-report.json" <<'PY'
import json, pathlib, sys
report = json.loads(pathlib.Path(sys.argv[1]).read_text())
assert all(
    row["error"] == "staged workspace mutated during runner execution"
    for row in report["runs"]
)
assert all(
    row["workspace_sha256_before"] != row["workspace_sha256_after"]
    for row in report["runs"]
)
assert all(
    row["original_inputs_sha256_before"] == row["original_inputs_sha256_after"]
    for row in report["runs"]
)
PY

cat >"$TMP/timeout-runner" <<SH
#!/usr/bin/env bash
trap '' TERM
(
  trap '' TERM
  while :; do sleep 1; done
) &
echo "\$!" >"$TMP/timeout-child.pid"
while :; do sleep 1; done
SH
chmod +x "$TMP/timeout-runner"
PYTHONDONTWRITEBYTECODE=1 python3 - \
  "$ROOT/scripts/evals/run-behavioral-evals.py" "$TMP/timeout-runner" <<'PY'
import importlib.util
import pathlib
import subprocess
import sys

path = pathlib.Path(sys.argv[1])
spec = importlib.util.spec_from_file_location("behavioral_eval_runner", path)
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)
case = {
    "id": "reviewer-always-true-locator",
    "skill": "e2e-reviewer",
    "task": "Review {repo}/scripts/ci/fixtures/codex-smoke/silent.spec.ts.",
    "assertions": [{"type": "contains", "value": "x"}],
}
try:
    module.run_once(sys.argv[2], case, "with_skill", 1)
except subprocess.TimeoutExpired as exc:
    evidence = exc.evidence
    assert exc.cleanup_attempted is True
    assert getattr(exc, "cleanup_failures", []) == []
    assert evidence["workspace_sha256_before"] == evidence["workspace_sha256_after"]
    assert evidence["original_inputs_sha256_before"] == evidence["original_inputs_sha256_after"]
else:
    raise AssertionError("timeout runner unexpectedly completed")
PY
timeout_child="$(cat "$TMP/timeout-child.pid")"
if kill -0 "$timeout_child" 2>/dev/null; then
  echo "test-behavioral-evals: timeout left child process $timeout_child alive" >&2
  exit 1
fi

# Live execution must never happen accidentally in ordinary CI.
if python3 "$ROOT/scripts/evals/run-behavioral-evals.py" --runner codex \
  --repetitions 1 --output "$TMP/forbidden.json" >"$TMP/forbidden.out" 2>&1; then
  echo "test-behavioral-evals: live runner worked without --allow-live" >&2
  exit 1
fi
grep -q -- "--allow-live" "$TMP/forbidden.out"

echo "behavioral eval harness: pass"
