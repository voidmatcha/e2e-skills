#!/usr/bin/env python3
"""Event audit true-positive and false-positive guards. Apache-2.0."""
import importlib.util
import json
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
spec = importlib.util.spec_from_file_location("audit", ROOT / "scripts/evals/audit-generator-codex-transcripts.py")
audit = importlib.util.module_from_spec(spec)
spec.loader.exec_module(audit)


class AuditTests(unittest.TestCase):
    def test_failed_output_not_command_mentions_or_success(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            transcript = root / "one.jsonl"
            def command(code, output, text=""):
                return {"type": "item.completed", "item": {
                    "type": "command_execution", "exit_code": code,
                    "aggregated_output": output, "command": text}}
            events = [command(1, "Chromium distribution 'chrome' is not found"),
                      command(0, "EADDRINUSE"), command(1, "", "echo EADDRINUSE"),
                      {"type": "item.completed", "item": {"type": "collab_tool_call", "tool": "spawn_agent"}},
                      {"type": "item.started", "item": {"type": "collab_tool_call", "tool": "spawn_agent"}}]
            transcript.write_text("\n".join(json.dumps(event) for event in events) + '\n{"truncated":\n')
            report = root / "report.json"
            row = {"call_id": "one", "arm": "skill", "attempts": [{"transcript_path": "/normalized/one.jsonl"}]}
            report.write_text(json.dumps({"runs": [row]}))
            result = audit.audit(report, root)["arms"]["skill"]
            self.assertEqual(result["missing_default_chrome"]["events"], 1)
            self.assertEqual(result["port_in_use"]["events"], 0)
            self.assertEqual(result["spawn_agent_events"]["events"], 1)
            self.assertEqual(result["invalid_json_lines"]["events"], 1)
            report.write_text(json.dumps({"runs": [row, row]}))
            with self.assertRaisesRegex(ValueError, "duplicate"):
                audit.audit(report, root)


if __name__ == "__main__":
    unittest.main()
