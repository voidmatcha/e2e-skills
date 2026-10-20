#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Fresh-output, fixed Passport adapter; never executes caller-supplied commands.

The frozen runners remain byte-identical. Private phase processes relocate only
their output globals and re-admit each result with the hardened independent
verifiers. This is an internal trusted-input adapter, not an arbitrary project
sandbox or an artifact authenticity claim for malicious test programs.
"""

import hashlib
import importlib
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys

ADAPTER_ID = "passport-cypress-v1"
PROMISE_ID = "clear-all-completed"
PROMISE_TEXT = "Clear completed"
TEST_SELECTORS = ("weak", "strong")
PHASES = ("normal", "fault", "recovery")
HERE = Path(__file__).resolve().parent
IMAGE = "cypress/included@sha256:a10a311fdac6a850603a4092842198356702ce77117569670dffe9f04ec8fd12"
SOURCE = HERE.parents[1] / "check-cypress-canary/passport-cypress-matrix-v1"
PINNED_FILES = {
    "run_passport_weak_split.py": "60094c4a08be8fba1a8c136664527b3e5d1e747e7e19bcc95b300cdb2cb0d5f7",
    "run_passport_split_home_v3.py": "f4422555b1c317660dfc1786ff051080dba23e5a20e80e0a7a84e0daac644a2d",
    "run_passport_split_controls.py": "ebc492c1e76b41a5c2630a2d99db3aca719be2561d744f5e7671f64ba410bf5f",
    "verify_passport_weak_split.py": "1f21882704324fc69f2c0f73d083e607426d9bf864fcf718d00585bb7f4517ce",
    "verify_passport_split_home_v3.py": "f6cf370b70e5b9d9deac1fe70cc279245245cd870001dccaefed47d19244c82f",
    "verify_passport_split_controls.py": "651a30c1e77081e3064e58c8c567349e93283a2f34a35fc56da2a9ff25915526",
}
SOURCE_PINS = {
    "matrix-freeze.json": "e12977f32c7088357b0e083e3c8696d1603564bf5ac8a473397df0f815fe382a",
    "verify.py": "b8f82f012e9976fbb47aa3ccdef40bfcf6969208053df8d08b32d032f29fe73d",
    "protocol.json": "03e2e152269a7a090a7f3d9568023cc55c2ec66194958377247fc530657e802a",
}
INPUT_MANIFEST_PINS = {
    "passport-weak-split-normal-v1-home": "6cec489957b434e85a501725ddc0a87857e06fddbb5f8eec26faf0fb24105ef3",
    "passport-weak-split-fault-v1-home": "2d1ac6c4325814e6e62d8dfde988cf46824fc83907ae13e8102edac5a5bcec79",
    "passport-weak-split-recovery-v1-home": "6cec489957b434e85a501725ddc0a87857e06fddbb5f8eec26faf0fb24105ef3",
    "passport-split-normal-v1-home": "4e92cb41eb203a9975f726ae069214de54cdb7620b8bf4a212bb88b37e36fd8b",
    "passport-split-fault-v3-home": "5b605333458896933c0f559c89eb6e0a0f43467f1749c0b0e321d75120a7bffd",
    "passport-split-recovery-v1-home": "4e92cb41eb203a9975f726ae069214de54cdb7620b8bf4a212bb88b37e36fd8b",
}


def _hash(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def descriptor() -> dict:
    """Return the fixed execution description used by the caller's approval digest."""
    docker = shutil.which("docker")
    return {
        "adapter_id": ADAPTER_ID, "promise_id": PROMISE_ID,
        "test_selectors": list(TEST_SELECTORS), "phases": list(PHASES),
        "image": IMAGE, "source_matrix": str(SOURCE),
        "runner_verifier_sha256": dict(PINNED_FILES),
        "source_sha256": dict(SOURCE_PINS),
        "pinned_input_manifests": dict(INPUT_MANIFEST_PINS),
        "python": str(Path(sys.executable).resolve()),
        "docker": docker,
        "host_environment": _host_environment(docker),
        "private_phase_argv": [str(Path(sys.executable).resolve()), "-B", str(Path(__file__).resolve()),
                               "--private-phase", "<fresh-output>", "<exact-selector>",
                               "<normal|fault|recovery>", "<run|verify>"],
        "container_argv": {"seed": ["node", "/seed.cjs"],
                           "app": ["node", "/serve.cjs"],
                           "browser": ["node", "/run.cjs"]},
        "container_environment": {"browser": ["HOME=/work/home"], "others": []},
        "network": "none; browser/probe share app network namespace",
        "writable_mounts": {"app": ["/app/var/db"], "browser": ["/work"]},
        "trusted_inputs_only": True, "retries": 0, "model_calls": 0,
    }


def _host_environment(docker) -> dict:
    if docker is None:
        return {}
    return {"HOME": str(Path.home()),
            "PATH": os.pathsep.join((str(Path(sys.executable).parent), str(Path(docker).parent), os.defpath)),
            "LANG": "C.UTF-8", "PYTHONDONTWRITEBYTECODE": "1"}


def _check_pins() -> None:
    for name, expected in PINNED_FILES.items():
        if _hash(HERE / name) != expected:
            raise RuntimeError(f"registered runner/verifier drift: {name}")
    for name, expected in SOURCE_PINS.items():
        if _hash(SOURCE / name) != expected:
            raise RuntimeError(f"registered source admission drift: {name}")
    for name, expected in INPUT_MANIFEST_PINS.items():
        if _hash(HERE / name / "input-hashes.json") != expected:
            raise RuntimeError(f"registered input manifest drift: {name}")
    freeze = json.loads((SOURCE / "matrix-freeze.json").read_text())
    for relative, expected in freeze["inputs"].items():
        path = SOURCE / relative
        if not path.resolve().is_relative_to(SOURCE.resolve()) or _hash(path) != expected:
            raise RuntimeError("pinned source input drift")


def _cell_name(selector: str, phase: str) -> str:
    if selector == "weak":
        return f"passport-weak-split-{phase}-v1-home"
    return "passport-split-fault-v3-home" if phase == "fault" else f"passport-split-{phase}-v1-home"


def _modules(selector: str, phase: str, output: Path):
    # Imports are confined to a private phase process; frozen argv parsing cannot
    # alter the parent process or another adapter's module globals.
    sys.path.insert(0, str(HERE))
    sys.argv = ["passport-registered-phase", phase]
    base = importlib.import_module("run_passport_split_home_v3")
    fault = importlib.import_module("verify_passport_split_home_v3")
    if selector == "weak":
        runner = importlib.import_module("run_passport_weak_split")
        verifier = importlib.import_module("verify_passport_weak_split")
        setattr(verifier, "HERE", output)
    elif phase == "fault":
        runner, verifier = base, fault
    else:
        runner = importlib.import_module("run_passport_split_controls")
        verifier = importlib.import_module("verify_passport_split_controls")
        setattr(verifier, "HERE", output)
    setattr(runner, "ROOT", output / _cell_name(selector, phase))
    return runner, verifier


def _admit(runner, verifier, selector: str, phase: str) -> None:
    if selector == "strong" and phase == "fault":
        verifier.main()
    else:
        roots = {"app": runner.SOURCE_CELL / "app", "project": runner.SOURCE_CELL / "project",
                 "dependencies": runner.DEPENDENCIES, "cache": runner.CACHE, "adapter": runner.ADAPTER}
        verifier.verify_cell(phase, {name: runner.digest_tree(path) for name, path in roots.items()})
    root = runner.ROOT
    # Independently capture raw container configuration, after containers exit.
    for name in ("seed", "app", "network-probe", "browser"):
        identifier = (root / f"{name}.id").read_text().strip()
        if re.fullmatch(r"[0-9a-f]{64}", identifier) is None:
            raise RuntimeError("invalid container identifier")
        raw = subprocess.check_output(["docker", "inspect", identifier], timeout=20)
        (root / f"{name}-inspect.json").write_bytes(raw)


def _worker(output: Path, selector: str, phase: str, verify_only: bool) -> None:
    _check_pins()
    runner, verifier = _modules(selector, phase, output)
    roots = {"app": runner.SOURCE_CELL / "app", "project": runner.SOURCE_CELL / "project",
             "dependencies": runner.DEPENDENCIES, "cache": runner.CACHE, "adapter": runner.ADAPTER}
    current = {name: runner.digest_tree(path) for name, path in roots.items()}
    expected = json.loads((HERE / _cell_name(selector, phase) / "input-hashes.json").read_text())
    if current != expected:
        raise RuntimeError("registered source/dependencies/cache/adapter input drift")
    if not verify_only:
        runner.main()
    _admit(runner, verifier, selector, phase)
    _check_pins()


def _launch(output: Path, selector: str, phase: str, verify_only: bool = False) -> None:
    command = [str(Path(sys.executable).resolve()), "-B", str(Path(__file__).resolve()), "--private-phase",
               str(output), selector, phase, "verify" if verify_only else "run"]
    suffix = "replay" if verify_only else "run"
    # Avoid caller runtime injection; the only executable selection is the fixed
    # Python interpreter and installed Docker, recorded in descriptor().
    docker = shutil.which("docker")
    if docker is None:
        raise RuntimeError("Docker is unavailable")
    environment = _host_environment(docker)
    with (output / f"{phase}-{suffix}.stdout").open("wb") as stdout, (output / f"{phase}-{suffix}.stderr").open("wb") as stderr:
        result = subprocess.run(command, env=environment, stdout=stdout, stderr=stderr,
                                timeout=300, check=False)
    if result.returncode != 0:
        raise RuntimeError(f"{phase} {suffix} failed; see retained stderr")


def _stop_owned(output: Path, selector: str) -> None:
    """Stop only exact IDs emitted by this invocation; never remove containers."""
    docker = shutil.which("docker")
    if docker is None:
        return
    for phase in PHASES:
        for name in ("browser", "app", "network-probe", "seed"):
            path = output / _cell_name(selector, phase) / f"{name}.id"
            if path.is_file():
                identifier = path.read_text().strip()
                if re.fullmatch(r"[0-9a-f]{64}", identifier):
                    try:
                        subprocess.run([docker, "stop", "--timeout", "5", identifier],
                                       stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                                       timeout=15, check=False)
                    except subprocess.TimeoutExpired:
                        pass


def _artifact_hashes(output: Path) -> dict:
    return {str(path.relative_to(output)): _hash(path) for path in sorted(output.rglob("*"))
            if path.is_file() and not path.is_symlink() and path.name != "adapter-result.json"}


def run(output_dir: Path, test_selector: str) -> dict:
    """Run one registered test through three fresh cells; fail closed on gaps."""
    if test_selector not in TEST_SELECTORS:
        raise ValueError("unknown registered test selector")
    output = Path(output_dir).absolute()
    if output.exists() or output.is_symlink():
        raise FileExistsError("adapter output must be a fresh directory")
    if not output.parent.is_dir() or output.parent.resolve() != output.parent:
        raise ValueError("output parent must exist without symlink components")
    if output.is_relative_to(HERE.parents[3]):
        raise ValueError("adapter output must be outside the repository and retained artifacts")
    output.mkdir(exist_ok=False)
    result = {"adapter_id": ADAPTER_ID, "promise_id": PROMISE_ID,
              "test_selector": test_selector, "verdict": "CANNOT_VERIFY", "cells": []}
    try:
        _check_pins()
        result["descriptor"] = descriptor()
        for phase in PHASES:
            _launch(output, test_selector, phase)
            result["cells"].append({"phase": phase, "admitted": True,
                                    "directory": _cell_name(test_selector, phase)})
        identifiers = [(output / _cell_name(test_selector, phase) / f"{name}.id").read_text().strip()
                       for phase in PHASES for name in ("seed", "app", "network-probe", "browser")]
        if len(set(identifiers)) != 12:
            raise RuntimeError("container reuse across phases")
        # A later cell must not be able to invalidate an earlier admitted one.
        for phase in PHASES:
            _launch(output, test_selector, phase, verify_only=True)
        _check_pins()
        result["verdict"] = "SURVIVED" if test_selector == "weak" else "DETECTED"
    except (OSError, RuntimeError, ValueError, KeyError, subprocess.SubprocessError) as error:
        result["reason"] = str(error)
        _stop_owned(output, test_selector)
    result["evidence"] = {"root": str(output), "sha256": _artifact_hashes(output)}
    (output / "adapter-result.json").write_text(json.dumps(result, indent=2) + "\n")
    return result


if __name__ == "__main__":
    if (len(sys.argv) != 6 or sys.argv[1] != "--private-phase"
            or sys.argv[3] not in TEST_SELECTORS or sys.argv[4] not in PHASES
            or sys.argv[5] not in ("run", "verify")):
        raise SystemExit("registered adapter private phase only")
    _worker(Path(sys.argv[2]).resolve(), sys.argv[3], sys.argv[4], sys.argv[5] == "verify")
