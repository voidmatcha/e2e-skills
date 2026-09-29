#!/usr/bin/env python3
"""Apache-2.0. Offline calibration schedule and label-separation checks."""

import importlib.util
import json
from pathlib import Path
import tempfile
from unittest import mock

ROOT = Path(__file__).resolve().parents[2]
spec = importlib.util.spec_from_file_location("calibration", ROOT / "scripts/evals/calibrate-specificity-discovery.py")
M = importlib.util.module_from_spec(spec)
spec.loader.exec_module(M)


def main():
    fixtures = M.cases()
    prompts = []
    def fake(runner, prompt, *args, **kwargs):
        index = len(prompts) % 3
        prompts.append(prompt)
        assert '"expected"' not in prompt and 'cal-001' not in prompt
        assert runner == "codex" and kwargs["codex_json_output"]
        status = fixtures[index]["expected"]
        result = {"patterns": [{"pattern_id": p, "status": status if p == "#21" else "absent",
                                "rationale": "Fixture rationale", "anchors": [{"file": "test.spec.ts", "line": 1}]}
                               for p in M.P.PATTERNS]}
        return 0, json.dumps(result), 1
    with tempfile.TemporaryDirectory() as directory:
        with mock.patch.object(M.P.R, "run_once", side_effect=fake), \
                mock.patch.object(M.P.R, "runner_identity_output", return_value="fixture"):
            result = M.run(Path(directory) / "output", "/fake", {})
        assert len(prompts) == 6 and result["v2_gate"]
        assert all("DISCOVERY CONTRACT V2" not in p for p in prompts[:3])
        assert all("DISCOVERY CONTRACT V2" in p for p in prompts[3:])
        assert not result["evaluation_allowed"]
    print("discovery calibration: frozen six-call schedule, hidden labels, three statuses and development-only gate passed")


if __name__ == "__main__":
    main()
