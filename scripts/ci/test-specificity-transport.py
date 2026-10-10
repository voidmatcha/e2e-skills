#!/usr/bin/env python3
"""Apache-2.0. Verify one-variable probe isolation and bounded execution."""

import importlib.util
from pathlib import Path
import tempfile
from unittest import mock

ROOT = Path(__file__).resolve().parents[2]
spec = importlib.util.spec_from_file_location("probe", ROOT / "scripts/evals/probe-specificity-transport.py")
P = importlib.util.module_from_spec(spec)
spec.loader.exec_module(P)


def main():
    assert P.valid('{"status":"complete","value":7}')
    for raw in ('ExitPlanMode\n{"plan":"text"}', '{"status":"complete","value":true}',
                '{"status":"complete","value":7,"value":7}', '```json\n{}\n```'):
        assert not P.valid(raw)
    commands = [P.R.runner_invocation("claude", "/fake", P.PROMPT, "claude-fable-5",
                                      claude_permission_mode=mode)[0] for mode in ("plan", "off")]
    plan = commands[0].copy()
    pos = plan.index("--permission-mode")
    del plan[pos:pos + 2]
    assert plan == commands[1]
    for command in commands:
        assert command[command.index("--tools") + 1] == ""
        assert "--safe-mode" in command and "--strict-mcp-config" in command
    with tempfile.TemporaryDirectory() as directory:
        with mock.patch.object(P.R, "runner_identity_output", return_value="fixture"), \
                mock.patch.object(P.R, "run_once", return_value=(0, '{"status":"complete","value":7}', 1)) as runner:
            report = P.run(Path(directory) / "good", "/fake", {})
            assert report["valid_by_mode"] == {"plan": 2, "off": 2}
            assert [c.kwargs["claude_permission_mode"] for c in runner.call_args_list] == list(P.SCHEDULE)
            assert {c.args[1] for c in runner.call_args_list} == {P.PROMPT}
        with mock.patch.object(P.R, "runner_identity_output", return_value="fixture"), \
                mock.patch.object(P.R, "run_once", side_effect=TimeoutError) as runner:
            assert P.run(Path(directory) / "failed", "/fake", {})["status"] == "incomplete"
            assert runner.call_count == 1
    print("transport probe: exact prompt, single option delta, safety flags, strict output and bounded failure passed")


if __name__ == "__main__":
    main()
