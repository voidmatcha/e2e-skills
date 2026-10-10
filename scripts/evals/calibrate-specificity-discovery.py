#!/usr/bin/env python3
"""Apache-2.0. Synthetic development calibration, never benchmark evidence."""

import argparse
import importlib.util
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
spec = importlib.util.spec_from_file_location("calibration_pilot", ROOT / "scripts/evals/pilot-specificity-semantic.py")
P = importlib.util.module_from_spec(spec)
spec.loader.exec_module(P)


def cases():
    base = {"test.spec.ts": "import { test, expect } from '@playwright/test';\ntest('title', async ({ page }) => { await page.goto('/'); await expect(page).toHaveTitle('Home'); });\n"}
    config = "import { defineConfig } from '@playwright/test';\nexport default defineConfig({ projects: [\n  { name: 'setup', testMatch: 'auth.setup.ts' },\n  { name: 'browser', dependencies: ['setup'], use: { storageState: 'auth/state.json' } }\n] });\n"
    setup = "import { test as setup } from '@playwright/test';\nsetup('authenticate', async ({ request }) => {\n  await request.post('/login', { data: { username: 'fixture' } });\n  await request.storageState({ path: 'auth/state.json' });\n});\n"
    return [
        {"id": "cal-001", "expected": "candidate", "files": {**base, "playwright.config.ts": config, "auth.setup.ts": setup}},
        {"id": "cal-002", "expected": "absent", "files": {**base, "playwright.config.ts": "export default {};\n"}},
        {"id": "cal-003", "expected": "insufficient-context", "files": {**base, "playwright.config.ts": config}},
    ]


def run(output, executable, credentials):
    if output.exists() or output.resolve().is_relative_to(ROOT):
        raise ValueError("require fresh external output")
    fixtures = cases()
    reference = P.C.PATTERNS.read_text()
    manifest = {"cases": fixtures, "schedule": [f"{version}/{case['id']}" for version in ("v1", "v2") for case in fixtures],
                "scored_pattern": "#21", "maximum_calls": 6, "model": "gpt-5.6-sol",
                "runner_version": P.R.runner_identity_output("codex", [executable, "--version"]),
                "evaluation_allowed": False, "code_sha256": {p.name: P.C.digest(p.read_bytes()) for p in
                    [Path(__file__), Path(P.__file__), P.C.RUNNER]}, "reference_sha256": P.C.digest(reference.encode())}
    P.C.write_json(output / "inputs.json", manifest)
    report = {"status": "incomplete", "evaluation_allowed": False, "calls": []}
    P.C.write_json(output / "report.json", report)
    for version in ("v1", "v2"):
        for case in fixtures:
            # Expected labels and fixture IDs never enter the model prompt.
            result = P.model_call(output, version + "-" + case["id"], P.discovery_prompt(case, reference, contract=version),
                                  "gpt-5.6-sol", executable, credentials,
                                  lambda raw: P.validate_discovery(raw, case), runner="codex")
            actual = next(row["status"] for row in result["patterns"] if row["pattern_id"] == "#21")
            report["calls"].append({"contract": version, "case_id": case["id"], "actual": actual,
                                    "expected": case["expected"], "matched": actual == case["expected"], "result": result})
            P.C.write_json(output / "report.json", report)
    report["status"] = "complete"
    report["v2_gate"] = all(row["matched"] for row in report["calls"] if row["contract"] == "v2")
    P.C.write_json(output / "report.json", report)
    print({"status": "complete", "v2_gate": report["v2_gate"]})
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--runner-path", type=Path, required=True)
    parser.add_argument("--allow-live", action="store_true")
    args = parser.parse_args()
    if not args.allow_live:
        raise ValueError("explicit live opt-in required")
    executable = P.R.resolve_runner_executable("codex", args.runner_path)
    run(args.output, executable, P.R.inherited_runner_credentials("codex"))


if __name__ == "__main__":
    main()
