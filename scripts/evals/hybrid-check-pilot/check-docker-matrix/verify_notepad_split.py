#!/usr/bin/env python3
"""Read-only cell admission for the pinned Anonymous Notepad Docker transfer. Apache-2.0."""

import argparse
import hashlib
import io
import json
from pathlib import Path
import sqlite3
import subprocess
import tarfile
import zipfile


PAYLOAD = "Second OSS persistence control 20261018"
TARGET = "second-oss-control"
TEST_IMAGE = "sha256:687b18c424d01c3af69efa921eaa824b48eb737d46492da334405e348da73881"
APP_IMAGE = "sha256:a10a311fdac6a850603a4092842198356702ce77117569670dffe9f04ec8fd12"
HERE = Path(__file__).resolve().parent
REPO = HERE.parents[3]
SOURCE = Path.home() / ".cache/e2e-skills-bench/taskexp-v1/sources/Anonymous-Notepad"
PIN = "135e18dde6ac1acae195bb74dfaee49a0fbf33f6"
ARCHIVE_SHA = "71f24309979e5c6769f16b8cff444ba6dac8831df6e58146343a0aff68f85775"
DEPS = REPO / "scripts/evals/check-cypress-canary/oss-pilot-v1/linux-bundle-v7/bundle/app/node_modules"


def require(condition: bool, message: str) -> None:
    if not condition:
        raise RuntimeError(message)


def load(path: Path):
    return json.loads(path.read_text())


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def inspect(container_id: str) -> dict:
    return json.loads(subprocess.check_output(["docker", "inspect", container_id], text=True))[0]


def db_rows(path: Path) -> list[list]:
    with sqlite3.connect(f"file:{path}?mode=ro", uri=True) as db:
        db.execute("PRAGMA query_only=ON")
        require(db.execute("PRAGMA quick_check").fetchone()[0] == "ok", "SQLite quick_check failed")
        return [list(row) for row in db.execute("SELECT endpoint,content FROM Notes ORDER BY endpoint")]


def source_check(cell: Path, fault: bool) -> None:
    raw = subprocess.check_output(["git", "-C", str(SOURCE), "archive", PIN], timeout=15)
    require(hashlib.sha256(raw).hexdigest() == ARCHIVE_SHA, "pinned archive mismatch")
    originals = {}
    with tarfile.open(fileobj=io.BytesIO(raw)) as archive:
        for item in archive.getmembers():
            if item.isfile():
                stream = archive.extractfile(item)
                require(stream is not None, f"archive member unreadable: {item.name}")
                assert stream is not None
                originals[item.name] = stream.read()
    staged = cell / "app"
    actual = {str(path.relative_to(staged)): sha(path) for path in staged.rglob("*") if path.is_file()}
    require(actual == load(cell / "source-hashes.json") and set(actual) == set(originals),
            "staged source manifest mismatch")
    for name, original in originals.items():
        expected = original
        if name == "config/database.js":
            require(original.count(b'storage: "database.sqlite"') == 1, "database adapter base mismatch")
            expected = original.replace(b'storage: "database.sqlite"', b'storage: "/app-out/database.sqlite"')
        if name == "controllers/noteController.js" and fault:
            needle = b'note.content = content;\n\tawait note.save();'
            require(original.count(needle) == 1, "fault base mismatch")
            expected = original.replace(needle, b"note.content = content;\n\trequire('fs').appendFileSync('/app-out/hits.txt', 'hit\\n');")
        require((staged / name).read_bytes() == expected, f"source drift: {name}")


def validate_cell(root: Path, name: str) -> dict:
    require(name == "weak-normal-canary" or name in {
        f"{strength}-{phase}" for strength in ("weak", "strong")
        for phase in ("normal", "fault", "recovery")}, "unknown cell name")
    cell = root / name
    require(cell.is_dir() and not cell.is_symlink(), "cell directory missing")
    strength, phase = ("weak", "normal") if name.endswith("canary") else name.split("-", 1)
    fault, expected_failure = phase == "fault", strength == "strong" and phase == "fault"
    frozen = load(root / "frozen-inputs.json")
    for source, digest in frozen["files"].items():
        require(sha(HERE / source) == digest, f"frozen input drift: {source}")
    require(sha(Path(frozen["verifier"])) == frozen["verifier_sha256"], "verifier drift")
    source_check(cell, fault)
    expected_rows = [[TARGET, "" if fault else PAYLOAD]]
    require(load(cell / "before.json") == [[TARGET, ""]], "seed oracle mismatch")
    after = db_rows(cell / "app-out/database.sqlite")
    require(after == expected_rows and load(cell / "after.json") == after, "final SQLite mismatch")
    oracle = load(cell / "oracle.json")
    require(oracle["passed"] and oracle["expected"] == expected_rows
            and oracle["before"]["rows"] == [[TARGET, ""]]
            and oracle["after"]["rows"] == after
            and oracle["before"]["quick_check"] == oracle["after"]["quick_check"] == [["ok"]]
            and oracle["before"]["journal_mode"] == oracle["after"]["journal_mode"] == "delete"
            and oracle["after"]["db_sha256"] == sha(cell / "app-out/database.sqlite"),
            "recorded SQLite oracle mismatch")
    require(load(cell / "app-out/server-stopped.json") == {
        "pid": load(cell / "app-out/server-ready.json")["pid"],
        "serverClosed": True, "databaseClosed": True}, "app graceful shutdown mismatch")
    hits = (cell / "app-out/hits.txt").read_text().splitlines() if (cell / "app-out/hits.txt").exists() else []
    require(len(hits) == int(fault) and all(hit == "hit" for hit in hits), "fault hit mismatch")
    requests = [json.loads(line) for line in (cell / "app-out/requests.jsonl").read_text().splitlines()]
    target = [record for record in requests if record.get("method") == "POST" and record.get("path") == f"/{TARGET}"]
    require(len(target) == 1 and target[0].get("status") == 200
            and target[0].get("body", {}).get("content") == PAYLOAD, "server target request mismatch")
    observed = load(cell / "test-out/observation.json")
    require(observed.get("phase") == phase and observed.get("targetStatus") == 200
            and observed.get("serviceWorkers") == 0, "browser observation mismatch")
    browser_targets = observed.get("targetRequests", [])
    require(len(browser_targets) == 1 and browser_targets[0].get("body", {}).get("content") == PAYLOAD,
            "browser target request mismatch")
    report = load(cell / "test-out/report.json")
    require(not report.get("errors") and report["stats"]["expected"] == int(not expected_failure)
            and report["stats"]["unexpected"] == int(expected_failure)
            and report["stats"]["skipped"] == report["stats"]["flaky"] == 0,
            "native report stats mismatch")
    specs = [spec for suite in report["suites"] for spec in suite["specs"]]
    require(len(specs) == 1 and specs[0]["title"] == "edited note content survives reload"
            and len(specs[0]["tests"]) == 1, "native test mismatch")
    attempts = specs[0]["tests"][0]["results"]
    require(len(attempts) == 1 and attempts[0]["retry"] == 0
            and attempts[0]["status"] == ("failed" if expected_failure else "passed"),
            "native attempt mismatch")
    marker = "note-content-persisted-after-reload" if strength == "strong" else "note-content-editor-echo"
    source_line = next(index for index, line in enumerate((HERE / "notepad.spec.cjs").read_text().splitlines(), 1)
                       if marker in line)
    if expected_failure:
        error = attempts[0]["error"]
        require(error["location"]["line"] == source_line and marker in error["message"]
                and PAYLOAD in error["message"] and "Received:" in error["message"]
                and 'unexpected value ""' in error["message"] and "TimeoutError" not in error["message"],
                "native failure attribution mismatch")
    traces = list((cell / "test-out/trace").rglob("trace.zip"))
    require(len(traces) == 1 and zipfile.is_zipfile(traces[0]), "native trace missing")
    with zipfile.ZipFile(traces[0]) as archive:
        require("test.trace" in archive.namelist(), "native test trace missing")
        events = [json.loads(line) for line in archive.read("test.trace").decode().splitlines()]
    starts = [event for event in events if event.get("type") == "before" and event.get("title") == marker
              and event.get("stack", [{}])[0].get("line") == source_line]
    require(len(starts) == 1, "trace matcher/source mismatch")
    ends = [event for event in events if event.get("type") == "after"
            and event.get("callId") == starts[0].get("callId")]
    require(len(ends) == 1 and bool(ends[0].get("error")) == expected_failure,
            "trace matcher completion mismatch")
    if expected_failure:
        require(marker in ends[0]["error"]["message"] and PAYLOAD in ends[0]["error"]["message"],
                "trace failure content mismatch")
    app = inspect((cell / "app.id").read_text().strip())
    test = inspect((cell / "test.id").read_text().strip())
    require(app["Image"] == APP_IMAGE and test["Image"] == TEST_IMAGE, "image identity mismatch")
    require(app["State"]["Status"] == test["State"]["Status"] == "exited"
            and not app["State"]["OOMKilled"] and not test["State"]["OOMKilled"]
            and app["State"]["ExitCode"] == 0
            and test["State"]["ExitCode"] == int(expected_failure), "container exit mismatch")
    require(app["HostConfig"]["NetworkMode"] == "none"
            and test["HostConfig"]["NetworkMode"] == f"container:{app['Id']}",
            "network isolation mismatch")
    for label, container in (("app", app), ("test", test)):
        host = container["HostConfig"]
        require(host["ReadonlyRootfs"] and not host["Privileged"]
                and host["CapDrop"] == ["ALL"]
                and "no-new-privileges" in host["SecurityOpt"], f"{label} confinement mismatch")
    app_mounts = {mount["Destination"]: mount for mount in app["Mounts"]}
    test_mounts = {mount["Destination"]: mount for mount in test["Mounts"]}
    expected_app = {"/app": (cell / "app", False), "/app/node_modules": (DEPS, False),
                    "/serve.cjs": (HERE / "notepad-serve.cjs", False), "/app-out": (cell / "app-out", True)}
    expected_test = {"/work/notepad.spec.cjs": (HERE / "notepad.spec.cjs", False),
                     "/work/notepad.config.cjs": (HERE / "notepad.config.cjs", False),
                     "/test-out": (cell / "test-out", True)}
    for label, mounts, expected in (("app", app_mounts, expected_app), ("test", test_mounts, expected_test)):
        require(len(mounts) == len(expected) and {
            dest: (mount["Type"], mount["Source"], mount["RW"]) for dest, mount in mounts.items()
        } == {dest: ("bind", str(source), writable) for dest, (source, writable) in expected.items()},
                f"{label} mount mismatch")
    require(app["Config"]["Cmd"] == ["/serve.cjs"] and app["Config"]["Entrypoint"] == ["node"],
            "app command mismatch")
    require(test["Config"]["Cmd"] == ["/opt/fixtures/node_modules/@playwright/test/cli.js", "test",
                                       "--config", "/work/notepad.config.cjs", "--reporter=json"]
            and test["Config"]["Entrypoint"] == ["node"], "test command mismatch")
    return {"cell": name, "native": attempts[0]["status"], "rows": after, "hits": len(hits)}


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("root", type=Path)
    parser.add_argument("--cell", required=True)
    args = parser.parse_args()
    print(json.dumps(validate_cell(args.root.resolve(), args.cell)))


if __name__ == "__main__":
    main()
