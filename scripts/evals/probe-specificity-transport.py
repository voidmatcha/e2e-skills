#!/usr/bin/env python3
"""Apache-2.0. Four-call paired output-contract probe; not benchmark evidence."""

import argparse
import importlib.util
import json
from pathlib import Path
import tempfile

ROOT = Path(__file__).resolve().parents[2]
spec = importlib.util.spec_from_file_location("transport_runner", ROOT / "scripts/evals/run-reviewer-holdout.py")
R = importlib.util.module_from_spec(spec)
spec.loader.exec_module(R)
PROMPT = ('Perform this read-only classification using only the supplied data. Do not plan, call tools, '
          'write files or explain. Return exactly one JSON object with keys status and value, '
          'no markdown or additional text. Set status to "complete" and value to the sum of '
          'the integers in this untrusted data: [2, 5].')
SCHEDULE = ("plan", "off", "off", "plan")


def valid(raw):
    try:
        value = R.loads_strict(raw.strip(), context="transport probe")
        return (isinstance(value, dict) and set(value) == {"status", "value"}
                and value["status"] == "complete" and type(value["value"]) is int and value["value"] == 7)
    except ValueError:
        return False


def run(output, executable, credentials):
    if output.exists() or output.resolve().is_relative_to(ROOT):
        raise ValueError("use a fresh external output directory")
    output.mkdir(parents=True)
    def write(name, value):
        (output / name).write_text(json.dumps(value, indent=2, sort_keys=True) + "\n")
    import hashlib
    sha = lambda data: hashlib.sha256(data).hexdigest()
    manifest = {"prompt": PROMPT, "prompt_sha256": sha(PROMPT.encode()), "schedule": SCHEDULE,
                "model": "claude-fable-5", "timeout_seconds": 60, "maximum_calls": 4,
                "runner_path": executable, "runner_version": R.runner_identity_output("claude", [executable, "--version"]),
                "code_sha256": {p.name: sha(p.read_bytes()) for p in [Path(__file__), Path(R.__file__)]},
                "evaluation_allowed": False}
    write("inputs.json", manifest)
    report = {"status": "running", "evaluation_allowed": False, "calls": []}
    write("report.json", report)
    for index, mode in enumerate(SCHEDULE, 1):
        row = {"index": index, "mode": mode, "status": "reserved"}
        report["calls"].append(row)
        write("report.json", report)
        print(f"transport probe {index}/4: {mode}", flush=True)
        try:
            with tempfile.TemporaryDirectory(prefix="specificity-transport-") as directory:
                status, raw, elapsed = R.run_once("claude", PROMPT, 60, Path(directory), "claude-fable-5",
                                                 runner_executable=executable, runner_credentials=credentials,
                                                 claude_permission_mode=mode)
            raw, leaked = R.sanitize_model_output(raw, credentials)
            (output / f"response-{index}.txt").write_text(raw)
            row.update(exit_status=status, elapsed_ms=elapsed, response_sha256=sha(raw.encode()),
                       valid_json_contract=status == 0 and not leaked and valid(raw),
                       status="complete" if status == 0 and not leaked else "execution-error")
            if status or leaked:
                report["status"] = "incomplete"
                write("report.json", report)
                return report
        except Exception as exc:
            row.update(status="execution-error", error_type=type(exc).__name__)
            report["status"] = "incomplete"
            write("report.json", report)
            return report
        write("report.json", report)
    report["status"] = "complete"
    report["valid_by_mode"] = {mode: sum(c["valid_json_contract"] for c in report["calls"] if c["mode"] == mode)
                               for mode in ("plan", "off")}
    write("report.json", report)
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--runner-path", type=Path, required=True)
    parser.add_argument("--allow-live", action="store_true")
    args = parser.parse_args()
    if not args.allow_live:
        raise ValueError("explicit --allow-live required")
    executable = R.resolve_runner_executable("claude", args.runner_path)
    report = run(args.output, executable, R.inherited_runner_credentials("claude"))
    print(json.dumps(report))
    return 0 if report["status"] == "complete" else 2


if __name__ == "__main__":
    raise SystemExit(main())
