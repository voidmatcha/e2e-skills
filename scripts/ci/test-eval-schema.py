#!/usr/bin/env python3
"""Adversarial schema checks for public skill eval metadata."""

from __future__ import annotations

import json
from pathlib import Path
import subprocess
import tempfile


ROOT = Path(__file__).resolve().parents[2]
VALIDATOR = ROOT / "scripts/validate-evals.sh"


def run_validator(workspace: Path) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["/bin/bash", str(VALIDATOR)],
        cwd=workspace,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        check=False,
    )


def valid_payload() -> dict[str, object]:
    return {
        "skill_name": "demo",
        "evals": [
            {
                "id": 1,
                "prompt": "Review the attached fixture.",
                "expected_output": "One evidence-backed finding.",
                "assertions": ["Cites fixture.spec.ts:1"],
                "files": ["fixture.spec.ts"],
            }
        ],
    }


def main() -> None:
    with tempfile.TemporaryDirectory(prefix="e2e-eval-schema-") as temp:
        workspace = Path(temp)
        skill = workspace / "skills/demo"
        eval_dir = workspace / "scripts/evals/skills/demo"
        skill.mkdir(parents=True)
        (skill / "SKILL.md").write_text("# Demo skill\n")
        eval_dir.mkdir(parents=True)
        (eval_dir / "fixture.spec.ts").write_text("test.only('x', () => {});\n")
        metadata = eval_dir / "evals.json"

        metadata.write_text(json.dumps(valid_payload()), encoding="utf-8")
        valid = run_validator(workspace)
        assert valid.returncode == 0, valid.stdout
        assert "total: 1 eval(s)" in valid.stdout

        invalid_payloads = (
            (
                '{"skill_name":"demo","skill_name":"shadow",'
                '"evals":[]}',
                "duplicate JSON object key",
            ),
            (
                '{"skill_name":"demo","evals":[],"unknown":true}',
                "unknown=['unknown']",
            ),
            (
                json.dumps(
                    {
                        **valid_payload(),
                        "evals": [
                            {
                                **valid_payload()["evals"][0],
                                "unknown": True,
                            }
                        ],
                    }
                ),
                "unknown=['unknown']",
            ),
            (
                json.dumps(
                    {
                        **valid_payload(),
                        "evals": [
                            valid_payload()["evals"][0],
                            valid_payload()["evals"][0],
                        ],
                    }
                ),
                "duplicate eval id",
            ),
        )
        for payload, marker in invalid_payloads:
            metadata.write_text(payload, encoding="utf-8")
            result = run_validator(workspace)
            assert result.returncode != 0, result.stdout
            assert marker in result.stdout, result.stdout

        mismatch_payload = valid_payload()
        mismatch_payload['skill_name'] = 'wrong-skill'
        metadata.write_text(json.dumps(mismatch_payload), encoding="utf-8")
        mismatch = run_validator(workspace)
        assert mismatch.returncode != 0, mismatch.stdout
        assert "skill_name must match eval directory" in mismatch.stdout

        metadata.write_text(json.dumps(valid_payload()), encoding="utf-8")
        (eval_dir / "fixture.spec.ts").unlink()
        missing_fixture = run_validator(workspace)
        assert missing_fixture.returncode != 0, missing_fixture.stdout
        assert "references missing fixture" in missing_fixture.stdout

        # Old shipped metadata cannot mask an absent developer eval tree.
        old_dir = skill / "evals"
        old_dir.mkdir()
        (old_dir / "evals.json").write_text(json.dumps(valid_payload()))
        metadata.unlink()
        missing_suite = run_validator(workspace)
        assert missing_suite.returncode != 0, missing_suite.stdout

    print("eval schema: pass (strict JSON, exact keys, duplicate IDs, directory identity, relocated fixtures, missing suites)")


if __name__ == "__main__":
    main()
