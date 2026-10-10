#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Zero-tool three-arm development probe on six public v9/v10 real fixes."""

import argparse
import base64
import hashlib
import importlib.util
import json
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
SKILL = ROOT / "skills/e2e-reviewer"
DOCUMENT = ROOT / "benchmarks/real-fix-probe-v1/protocol.json"
RUNNER = ROOT / "scripts/evals/run-reviewer-holdout.py"
SCHEMA = ROOT / "scripts/evals/reviewer-validation-protocol-v15.json"
MODEL = "gpt-6-sol"
BASE_FOUR_LEGEND = "#4: Vacuous assertion outside the named sub-IDs; use P0 only when the predicate cannot fail independently of product behavior."
CASES = (
    {"id": "datagrok", "acquisition": "v9", "index": 0, "framework": "playwright",
     "context": ("js-api/src/shell.ts",), "pattern": "#4", "before_lines": (437, 438, 439), "after_range": (433, 440)},
    {"id": "growi", "acquisition": "v9", "index": 1, "framework": "playwright",
     "context": (), "pattern": "#16", "before_lines": (29,), "after_range": (27, 31)},
    {"id": "opensearch", "acquisition": "v9", "index": 2, "framework": "cypress",
     "context": ("cypress/fixtures/stub_top_queries.json",), "pattern": "#4a", "before_lines": (61, 71), "after_range": (42, 90)},
    {"id": "chronograf", "acquisition": "v10", "index": 0, "framework": "cypress",
     "context": (), "pattern": "#2", "before_lines": (139,), "after_range": (134, 145)},
    {"id": "onearmy", "acquisition": "v10", "index": 1, "framework": "cypress",
     "context": ("packages/cypress/src/support/index.ts",), "pattern": "#10d", "before_lines": (31,), "after_range": (29, 40)},
    {"id": "kibana", "acquisition": "v10", "index": 2, "framework": "cypress",
     "context": ("x-pack/solutions/security/test/security_solution_cypress/cypress/screens/security_header.ts",),
     "pattern": "#4i", "before_lines": (75,), "after_range": (72, 77)},
)
ARMS = ("full", "catalog-only", "no-skill")


def sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def git_blob_hash(data: bytes) -> str:
    return hashlib.sha1(f"blob {len(data)}\0".encode() + data).hexdigest()


def api_bytes(repo: str, path: str, revision: str | None = None) -> bytes:
    endpoint = (f"repos/{repo}/git/blobs/{path}" if revision is None
                else f"repos/{repo}/contents/{path}?ref={revision}")
    result = subprocess.run(["gh", "api", endpoint], check=True, capture_output=True, text=True, timeout=60)
    payload = json.loads(result.stdout)
    if payload.get("encoding") != "base64" or not isinstance(payload.get("content"), str):
        raise ValueError(f"unexpected GitHub content encoding: {repo} {path}")
    return base64.b64decode(payload["content"], validate=False)


def load_runner():
    spec = importlib.util.spec_from_file_location("public_real_fix_runner", RUNNER)
    if spec is None or spec.loader is None:
        raise RuntimeError("cannot load holdout runner")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def save(path: Path, value: dict) -> None:
    path.write_text(json.dumps(value, indent=2, ensure_ascii=False) + "\n")


def stage(root: Path) -> tuple[dict, dict]:
    staged, sources = {}, {}
    manifests = {
        version: json.loads((ROOT / f"benchmarks/real-fix-acquisition-{version}/cases.json").read_text())
        for version in ("v9", "v10")
    }
    for case in CASES:
        acquisition = manifests[case["acquisition"]][case["index"]]
        repo, spec_path = acquisition["repository"], acquisition["spec"]
        if acquisition["pattern"] != case["pattern"]:
            raise ValueError(f"pattern drift: {case['id']}")
        for side, revision, expected_blob in (
            ("before", acquisition["parent"], acquisition["parent_spec_blob"]),
            ("after", acquisition["fix"], acquisition["fix_spec_blob"]),
        ):
            workspace = root / case["id"] / side
            workspace.mkdir(parents=True)
            shutil.copytree(SKILL, workspace / ".skill/e2e-reviewer")
            spec_data = api_bytes(repo, spec_path, revision)
            if git_blob_hash(spec_data) != expected_blob:
                raise ValueError(f"spec blob mismatch: {case['id']} {side}")
            entries = [(spec_path, spec_data)]
            for context_path in case["context"]:
                entries.append((context_path, api_bytes(repo, context_path, revision)))
            hashes = {}
            for source_path, data in entries:
                destination = workspace / source_path
                destination.parent.mkdir(parents=True, exist_ok=True)
                destination.write_bytes(data)
                hashes[source_path] = {"sha256": sha256(data), "git_blob": git_blob_hash(data)}
            staged[(case["id"], side)] = (
                workspace,
                {"id": f"case-{case['id']}-{side}", "framework": case["framework"],
                 "source_files": [{"path": path} for path, _ in entries]},
                spec_path,
            )
            sources[f"{case['id']}:{side}"] = {"revision": revision, "files": hashes}
    return staged, sources


def score(case: dict, side: str, spec_path: str, answer: dict) -> dict:
    findings = answer.get("findings")
    if not isinstance(findings, list):
        raise ValueError("missing findings array")
    for finding in findings:
        if not isinstance(finding, dict) or not isinstance(finding.get("line"), int):
            raise ValueError("invalid finding")
        if not all(isinstance(finding.get(key), str) for key in ("pattern_id", "severity", "file")):
            raise ValueError("invalid finding fields")
    hits = [f for f in findings if f["file"] == spec_path and f["pattern_id"] == case["pattern"]]
    if side == "before":
        matched = [f for f in hits if f["line"] in case["before_lines"]]
        return {"target_detected": bool(matched), "target_findings": matched,
                "other_findings_unadjudicated": len(findings) - len(matched)}
    start, end = case["after_range"]
    alarms = [f for f in hits if start <= f["line"] <= end]
    return {"mapped_after_clean": not alarms, "mapped_after_alarms": alarms,
            "other_findings_unadjudicated": len(findings) - len(alarms)}


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--runner-path", required=True, type=Path)
    parser.add_argument("--plan-only", action="store_true")
    args = parser.parse_args()
    output = args.output.resolve()
    if output.exists():
        parser.error("output exists; refusing to overwrite")
    runner_path = args.runner_path.resolve()
    if not runner_path.is_file():
        parser.error("runner path is not a file")
    runner = load_runner()
    schema = json.loads(SCHEMA.read_text())["output_schema"]["schema"]
    with tempfile.TemporaryDirectory(prefix="e2e-real-fix-v9-v10-") as temporary:
        staged, sources = stage(Path(temporary))
        schedule = [
            {"case": case["id"], "side": side, "arm": ARMS[(offset + turn) % 3]}
            for offset, case in enumerate(CASES)
            for side in ("before", "after")
            for turn in range(3)
        ]
        report = {
            "status": "INCOMPLETE",
            "claim": "one-repetition public development probe; zero-tool reviewer instruction effects only",
            "model": MODEL, "reasoning_effort": "medium", "repetitions": 1,
            "runner_version": subprocess.check_output([str(runner_path), "--version"], text=True).strip(),
            "script_sha256": sha256(Path(__file__).read_bytes()),
            "protocol_document_sha256": sha256(DOCUMENT.read_bytes()),
            "schema_sha256": sha256(SCHEMA.read_bytes()),
            "prompt_skill_sha256": runner.prompt_skill_digest(SKILL),
            "source_sha256": sources,
            "schedule": schedule,
            "calls": [],
        }
        if args.plan_only:
            print(json.dumps({k: v for k, v in report.items() if k != "calls"}, indent=2))
            return
        output.parent.mkdir(parents=True, exist_ok=True)
        save(output, report)
        try:
            for cell in schedule:
                case = next(item for item in CASES if item["id"] == cell["case"])
                workspace, runner_case, spec_path = staged[(cell["case"], cell["side"])]
                prompt = runner.render_prompt(runner_case, workspace=workspace,
                                              prompt_profile=cell["arm"], numbered_source_lines=True)
                prompt = prompt.replace("END_OUTPUT_LEGEND", BASE_FOUR_LEGEND + "\nEND_OUTPUT_LEGEND", 1)
                usage = []
                returncode, raw, elapsed_ms = runner.run_once(
                    "codex", prompt, 300, workspace, MODEL, runner_executable=str(runner_path),
                    reasoning_effort="medium", usage_sink=usage, output_schema=schema,
                )
                try:
                    answer = json.loads(raw)
                    result = score(case, cell["side"], spec_path, answer)
                    complete = returncode == 0
                except (json.JSONDecodeError, KeyError, TypeError, ValueError):
                    answer, result, complete = None, None, False
                report["calls"].append({
                    **cell, "returncode": returncode, "complete": complete,
                    "prompt_sha256": sha256(prompt.encode()), "raw_sha256": sha256(raw.encode()),
                    "answer": answer, "score": result, "usage": usage[0] if usage else None,
                    "elapsed_ms": elapsed_ms,
                })
                save(output, report)
                print(f"{cell['case']} {cell['side']} {cell['arm']}: rc={returncode} score={result}", flush=True)
                if not complete:
                    raise RuntimeError("incomplete cell; schedule stopped without retry")
        except BaseException:
            save(output, report)
            raise
        report["status"] = "COMPLETE"
        save(output, report)


if __name__ == "__main__":
    main()
