#!/usr/bin/env python3
"""Read-only whole-matrix replay for the retained Notepad split transfer. Apache-2.0."""

import hashlib
import json
from pathlib import Path
import subprocess

from verify_notepad_split import APP_IMAGE, TEST_IMAGE, validate_cell


HERE = Path(__file__).resolve().parent
ROOT = HERE / "notepad-split-v3"
SCHEDULE = ["weak-normal-canary"] + [f"{strength}-{phase}"
    for strength in ("weak", "strong") for phase in ("normal", "fault", "recovery")]


def require_exact_environment(actual: list[str], image: list[str], additions: dict[str, str]) -> None:
    expected = {item.split("=", 1)[0]: item for item in image}
    if len(expected) != len(image):
        raise RuntimeError("image environment has duplicate keys")
    expected.update({key: f"{key}={value}" for key, value in additions.items()})
    observed = {item.split("=", 1)[0]: item for item in actual}
    if len(observed) != len(actual) or observed != expected:
        raise RuntimeError("container environment mismatch")


def require_exact_tmpfs(actual: object) -> None:
    if actual != {"/tmp": "rw,nosuid,nodev,size=128m"}:
        raise RuntimeError("container tmpfs mismatch")


def verify_environments(cell: Path, strength: str, phase: str,
                        app_image_env: list[str], test_image_env: list[str]) -> None:
    for kind, image, additions in (
        ("app", APP_IMAGE, {}),
        ("test", TEST_IMAGE, {"HOME": "/tmp", "PLAYWRIGHT_BROWSERS_PATH": "/ms-playwright",
                              "SECOND_STRENGTH": strength, "SECOND_PHASE": phase}),
    ):
        identifier = (cell / f"{kind}.id").read_text().strip()
        details = json.loads(subprocess.check_output(["docker", "inspect", identifier], text=True))[0]
        if details["Image"] != image:
            raise RuntimeError(f"{kind} image mismatch")
        require_exact_tmpfs(details["HostConfig"].get("Tmpfs"))
        require_exact_environment(details["Config"]["Env"],
                                  app_image_env if kind == "app" else test_image_env,
                                  additions)


def main() -> None:
    result = json.loads((ROOT / "results.json").read_text())
    if (result.get("status") != "PASS" or result.get("unique_source_defects") != 1
            or result.get("model_calls") != 0
            or [cell.get("name") for cell in result.get("cells", [])] != SCHEDULE
            or any(cell.get("verified") is not True for cell in result["cells"])):
        raise RuntimeError("matrix result/schedule mismatch")
    if (ROOT / "failure.json").exists():
        raise RuntimeError("matrix retains a failure marker")
    if json.loads((ROOT / "unrelated-before.json").read_text()) != json.loads((ROOT / "unrelated-after.json").read_text()):
        raise RuntimeError("unrelated container state drift")
    frozen = json.loads((ROOT / "artifacts-sha256.json").read_text())
    actual = {str(path.relative_to(ROOT)): hashlib.sha256(path.read_bytes()).hexdigest()
              for path in ROOT.rglob("*") if path.is_file() and path.name != "artifacts-sha256.json"}
    if actual != frozen:
        raise RuntimeError("artifact set or hash mismatch")
    cells = [validate_cell(ROOT, name) for name in SCHEDULE]
    image_envs = {}
    for image in (APP_IMAGE, TEST_IMAGE):
        details = json.loads(subprocess.check_output(["docker", "image", "inspect", image], text=True))[0]
        if details["Id"] != image:
            raise RuntimeError("pinned image identity mismatch")
        image_envs[image] = details["Config"]["Env"]
    for name in SCHEDULE:
        strength, phase = ("weak", "normal") if name.endswith("canary") else name.split("-", 1)
        verify_environments(ROOT / name, strength, phase,
                            image_envs[APP_IMAGE], image_envs[TEST_IMAGE])
    if ([cell["native"] for cell in cells] != ["passed"] * 5 + ["failed", "passed"]
            or [cell["hits"] for cell in cells] != [0, 0, 1, 0, 0, 1, 0]):
        raise RuntimeError("native outcome/fault sequence mismatch")
    print(json.dumps({"status": "PASS", "valid_cells": 6, "canary": 1,
                      "weak_fault": "SURVIVED", "strong_fault": "DETECTED",
                      "unique_app_defect": 1, "model_calls": 0}))


if __name__ == "__main__":
    main()
