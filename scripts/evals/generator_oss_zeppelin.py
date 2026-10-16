#!/usr/bin/env python3
"""Serialized Zeppelin plumbing for generator-oss-eval-v1. Apache-2.0.

Importing this module performs no process query, network call or live setup. The
existing development loop supplies the proxy server, project stage and browser
runner; this module adds campaign ownership and strict per-cell note cleanup.
"""
from __future__ import annotations

from contextlib import contextmanager
import fcntl
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import re
import shutil
import shlex
import socket
import subprocess
import tempfile
import threading
import time
import urllib.request
import urllib.error
import uuid

DEV_TASKS = ("zep-sidebar", "zep-note-rename")
PORT = 14210
UPSTREAM = "http://127.0.0.1:18080"
SHARED_LOCK = Path("/tmp/e2e-skills-zeppelin-18080.lock")

NOTE_CREATION_POLICY = ("\nNote creation policy: REST POST /api/notebook must use the notePath field "
                        "(never name), with value '{folder}/<note-name>'. In the UI, put "
                        "every created note under that same folder, including renamed notes.\n")

# Interpose only a private readiness endpoint; serving and proxying still use
# the frozen loop harness. Each child gets a fresh token bound to its variant.
OWNED_SERVER_WRAPPER = r"""
const http = require('node:http');
const {pathToFileURL} = require('node:url');
const original = http.createServer;
const identity = JSON.parse(process.env.E2E_OSS_SERVER_IDENTITY);
http.createServer = (handler) => original((req, res) => {
  if (req.url === '/__e2e_oss_ready/' + identity.token) {
    res.writeHead(200, {'content-type': 'application/json', 'cache-control': 'no-store'});
    return res.end(JSON.stringify(identity));
  }
  return handler(req, res);
});
// serve.mjs reads dist, port and upstream from argv.slice(2).
const harness = process.argv[1];
process.argv = [process.argv[0], harness, ...process.argv.slice(2)];
import(pathToFileURL(harness).href).catch(error => { console.error(error); process.exit(1); });
"""


class OwnedVariantServer:
    """Refuse occupied ports and accept only our living variant-specific child."""

    def __init__(self, loop, variant, port):
        self.loop, self.variant, self.port = loop, variant, port
        self.proc = None
        self.dist = (loop.ZEP_DISTS / variant).resolve()
        self.identity = {"token": uuid.uuid4().hex, "variant": variant, "dist": str(self.dist)}

    def __enter__(self):
        if not (self.dist / "index.html").is_file():
            raise ValueError("missing Zeppelin variant build")
        # This is a bind probe, never a request or signal to an existing server.
        # A race after closing the probe is caught by child liveness + token.
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as probe:
            probe.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            try:
                probe.bind(("127.0.0.1", self.port))
            except OSError as error:
                raise ValueError("Zeppelin proxy port occupied; existing process left untouched") from error
        env = {**os.environ, "ZEPPELIN_WEB_NODE_MODULES": str(self.loop.ZEP_SRC / "node_modules"),
               "E2E_OSS_SERVER_IDENTITY": json.dumps(self.identity)}
        self.proc = subprocess.Popen(["node", "--input-type=commonjs", "-e", OWNED_SERVER_WRAPPER,
            str(self.loop.BENCH / "harness/serve.mjs"), str(self.dist), str(self.port), UPSTREAM],
            env=env, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        try:
            for _ in range(60):
                if self.proc.poll() is not None:
                    raise RuntimeError("owned Zeppelin variant child exited before readiness")
                try:
                    with urllib.request.urlopen(
                        f"http://127.0.0.1:{self.port}/__e2e_oss_ready/{self.identity['token']}", timeout=2) as response:
                        ready = response.status == 200 and json.loads(response.read(4096)) == self.identity
                except (OSError, ValueError):
                    ready = False
                if self.proc.poll() is not None:
                    raise RuntimeError("owned Zeppelin variant child exited during readiness")
                if ready:
                    return self
                time.sleep(0.5)
            raise RuntimeError("owned Zeppelin variant identity was not confirmed")
        except BaseException:
            self.__exit__()
            raise

    def __exit__(self, *exc):
        if self.proc is not None:
            if self.proc.poll() is None:
                self.proc.terminate()
            try:
                self.proc.wait(timeout=15)
            except subprocess.TimeoutExpired:
                self.proc.kill()
                self.proc.wait(timeout=15)
            self.proc = None


def load_loop(path):
    """Load only the dev loop's code/protocol; never discover task directories."""
    path = Path(path).resolve()
    spec = importlib.util.spec_from_file_location("generator_oss_dev_loop", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class CampaignPaused(ValueError):
    """A competing real driver pauses before a cell; no infrastructure row is spent."""


def driver_processes():
    """Match real Python driver argv, excluding this runner and its ancestors."""
    result = subprocess.run(["ps", "-axo", "pid=,ppid=,command="], capture_output=True,
                            text=True, check=True, timeout=10)
    processes = {}
    for line in result.stdout.splitlines():
        fields = line.strip().split(maxsplit=2)
        if len(fields) == 3 and fields[0].isdigit() and fields[1].isdigit():
            processes[int(fields[0])] = (int(fields[1]), fields[2])
    ancestors, pid = {os.getpid()}, os.getppid()
    while pid and pid not in ancestors:
        ancestors.add(pid)
        pid = processes.get(pid, (0, ""))[0]
    found = []
    for pid, (_, command) in processes.items():
        if pid in ancestors:
            continue
        try:
            argv = shlex.split(command)
        except ValueError:
            continue
        if not argv or not re.fullmatch(r"python(?:[0-9]+(?:\.[0-9]+)*)?", Path(argv[0]).name):
            continue
        # Interpreter flags are permitted; wrappers, grep and editor commands are not.
        script = 1
        while script < len(argv) and argv[script].startswith("-"):
            flag = argv[script]
            if flag in {"-c", "-m"}:
                script = len(argv)
                break
            script += 2 if flag in {"-W", "-X", "--check-hash-based-pycs"} else 1
            if flag == "--":
                break
        if script + 1 >= len(argv):
            continue
        if (re.fullmatch(r"run-generator-[\w-]+\.py", Path(argv[script]).name)
                and argv[script + 1] in {"drive", "run", "preflight", "score", "smoke", "harness-check", "final-eval", "calibrate", "canary"}):
            found.append(pid)
    return found


class CampaignLock:
    """Exclusive file ownership, refusing stale files rather than stealing them."""

    def __init__(self, path=SHARED_LOCK, process_probe=None, campaign_id="generator-oss-eval-v1"):
        self.path = Path(path)
        self.process_probe = process_probe or driver_processes
        self.campaign_id = campaign_id
        self.handle = None

    def __enter__(self):
        self.path.parent.mkdir(parents=True, exist_ok=True)
        try:
            self.handle = self.path.open("x")
        except FileExistsError as error:
            raise ValueError("Zeppelin campaign lock already exists; refusing concurrent or stale ownership") from error
        try:
            fcntl.flock(self.handle, fcntl.LOCK_EX | fcntl.LOCK_NB)
            if self.process_probe():
                raise ValueError("another generator benchmark driver process exists; Zeppelin use is exclusive")
            self.handle.write(json.dumps({"pid": os.getpid(), "campaign_id": self.campaign_id}) + "\n")
            self.handle.flush()
            return self
        except BaseException:
            self.__exit__()
            raise

    def __exit__(self, *exc):
        if self.handle is not None:
            try:
                # Refuse to unlink a replacement file installed by another actor.
                if self.path.exists() and self.path.stat().st_ino == os.fstat(self.handle.fileno()).st_ino:
                    self.path.unlink()
            finally:
                self.handle.close()
                self.handle = None


def namespace(campaign_id, cell_id):
    """One stable namespace per cell, including its model, arm and repetition."""
    if not campaign_id or not cell_id:
        raise ValueError("campaign and cell identifiers are required for note isolation")
    campaign = hashlib.sha256(str(campaign_id).encode()).hexdigest()[:16]
    cell = hashlib.sha256(str(cell_id).encode()).hexdigest()[:24]
    return f"E2E_OSS_EVAL/{campaign}/{cell}"


def owned_path(path, folder):
    normalized = path.lstrip("/")
    return normalized.startswith(folder + "/") or normalized.startswith("~Trash/" + folder + "/")


def delete_and_verify(api, note_ids):
    """DELETE 500 can mean success on this build; listing alone proves deletion."""
    remaining = set(note_ids)
    for _ in range(2):
        for note_id in sorted(remaining):
            if not re.fullmatch(r"[A-Za-z0-9_-]+", note_id):
                raise RuntimeError("malformed owned note ID; cleanup cannot proceed")
            try:
                api("DELETE", f"/api/notebook/{note_id}")
            except (urllib.error.HTTPError, urllib.error.URLError, OSError):
                pass
        remaining &= set(note_snapshot(api))
        if not remaining:
            return
    raise RuntimeError("Zeppelin notes remain after cell cleanup; stop campaign")


def clean_namespace(api, folder):
    """Delete namespace and its trash descendants; verify by listing, retry once."""
    if not re.fullmatch(r"E2E_OSS_EVAL/[0-9a-f]{16}/[0-9a-f]{24}", folder):
        raise ValueError("refusing cleanup outside a cell-owned note namespace")
    notes = [note_id for note_id, path in note_snapshot(api).items() if owned_path(path, folder)]
    delete_and_verify(api, notes)
    return len(notes)


def note_snapshot(api):
    """Read stable IDs and paths only, without fetching notebook contents."""
    response = api("GET", "/api/notebook")
    if not isinstance(response, dict) or not isinstance(response.get("body"), list):
        raise RuntimeError("cannot snapshot Zeppelin notes for cell isolation")
    notes = {}
    for note in response["body"]:
        if not isinstance(note, dict):
            raise RuntimeError("malformed Zeppelin note list during isolation snapshot")
        note_id, path = note.get("id"), note.get("path")
        if not isinstance(note_id, str) or not re.fullmatch(r"[A-Za-z0-9_-]+", note_id) or not isinstance(path, str):
            raise RuntimeError("malformed Zeppelin note identity during isolation snapshot")
        if note_id in notes:
            raise RuntimeError("duplicate Zeppelin note identity during isolation snapshot")
        notes[note_id] = path.lstrip("/")
    return notes


def isolation_violations(before, after, folder):
    """Observe surviving escapes or changes to pre-existing foreign notes.

    This is validation, not a network security boundary: a transient note
    created and removed between snapshots cannot be observed. Unknown foreign
    IDs are never deleted, renamed or fetched by this check.
    """
    violations = []
    for note_id, path in before.items():
        if note_id not in after:
            violations.append({"kind": "preexisting_note_removed", "note_id": note_id})
        elif after[note_id] != path:
            violations.append({"kind": "preexisting_note_path_changed", "note_id": note_id})
    for note_id, path in after.items():
        if note_id not in before and not owned_path(path, folder):
            violations.append({"kind": "new_note_outside_namespace", "note_id": note_id})
    return violations


def failing_titles(data):
    """Persist title chains only; grader messages and defect text stay private."""
    titles = []
    def visit(suite, parents):
        chain = parents + ([suite["title"]] if suite.get("title") else [])
        for spec in suite.get("specs", []):
            if any(test.get("status") in {"unexpected", "flaky"} or
                   any(result.get("status") in {"failed", "timedOut", "interrupted"}
                       for result in test.get("results", [])) for test in spec.get("tests", [])):
                titles.append(" > ".join(chain + [spec.get("title", "")]))
        for child in suite.get("suites", []):
            visit(child, chain)
    for suite in data.get("suites", []):
        visit(suite, [])
    return titles


def run_playwright_records(project, specs, timeout, env_extra, expected_failure=None):
    """The same JSON reporter scoring command, with minimal failure attribution."""
    started = time.monotonic()
    result = {"exit": None, "passed": 0, "failed": 0, "skipped": 0,
              "errors": [], "ok": False, "failing_test_titles": []}
    try:
        done = subprocess.run([str(project / "node_modules/.bin/playwright"), "test", *specs, "--reporter=json"],
            cwd=project, capture_output=True, text=True, timeout=timeout,
            env={**os.environ, "CI": "1", **env_extra})
        result["exit"] = done.returncode
        data = json.loads(done.stdout[done.stdout.index("{"):])
        stats = data.get("stats", {})
        result.update(passed=stats.get("expected", 0), failed=stats.get("unexpected", 0) + stats.get("flaky", 0),
                      skipped=stats.get("skipped", 0), errors=["reporter global error" for _ in data.get("errors", [])],
                      failing_test_titles=failing_titles(data))
        if expected_failure is not None:
            matched = []
            def visit(suite, parents):
                chain = parents + ([suite["title"]] if suite.get("title") else [])
                for spec in suite.get("specs", []):
                    title = " > ".join(chain + [spec.get("title", "")])
                    if title != expected_failure["failing_test_title"]:
                        continue
                    for test in spec.get("tests", []):
                        for run in test.get("results", []):
                            if run.get("status") in {"failed", "timedOut", "interrupted"}:
                                matched.append(any(re.search(expected_failure["reason_regex"], error.get("message", ""))
                                                   for error in run.get("errors", [])))
                for child in suite.get("suites", []):
                    visit(child, chain)
            for suite in data.get("suites", []):
                visit(suite, [])
            # Title and defect reason must belong to the same failed result.
            result["calibration_reason_matched"] = any(matched)
        result["ok"] = done.returncode == 0 and result["passed"] >= 1 and result["failed"] == 0 and not result["errors"]
    except subprocess.TimeoutExpired:
        result["errors"] = ["harness timeout"]
    except (ValueError, json.JSONDecodeError):
        result["errors"] = ["no JSON report"]
    result["seconds"] = round(time.monotonic() - started, 1)
    return result


def scoring_result(clean_runs, faults, refactor):
    """Offline-compatible metric calculation for the fixed 3/5/1 score shape."""
    if len(clean_runs) != 3 or len(faults) != 5:
        raise ValueError("Zeppelin scores require exactly three clean runs and five defects")
    clean = all(bool(run.get("ok")) for run in clean_runs)
    kills = []
    for run in faults.values():
        run["killed"] = bool(run.get("failed", 0) >= 1 and not run.get("errors"))
        kills.append(run["killed"])
    kill_rate = round(sum(kills) / 5, 4)
    survival = bool(clean and refactor.get("ok"))
    return {"clean_runs": clean_runs, "clean": clean, "faults": faults, "refactor": refactor,
            "kill_rate": kill_rate, "primary": kill_rate if clean else 0.0,
            "effective_fault_kill": kill_rate if clean else 0.0,
            "refactor_pass": bool(refactor.get("ok")) if clean else None,
            "refactor_score": float(survival)}


class ZeppelinRuntime:
    """Imported dev runtime with one proxy port and strictly serial phases.

    Every live phase requires campaign(). The same port is reused only after
    the previous phase's proxy has exited. Generation and scoring can never
    overlap, including in another thread using this runtime object.
    """

    def __init__(self, loop_runner, pool, dists, source, fixture_modules,
                 lock_path=SHARED_LOCK, campaign_id="generator-oss-eval-v1",
                 *, process_probe=None, loop=None, engine=None, task_ids=DEV_TASKS):
        self.loop_runner = Path(loop_runner)
        self.pool = Path(pool)
        self.dists = Path(dists)
        self.source = Path(source)
        self.fixture_modules = Path(fixture_modules)
        self.lock_path = Path(lock_path)
        self.campaign_id = campaign_id
        self.process_probe = process_probe
        self.loop = loop
        self.engine = engine
        self.task_ids = tuple(task_ids)
        self.lock = None
        self.phase = None
        self._phase_lock = threading.Lock()
        self.note_isolation_violations = []

    def _configured_loop(self):
        if self.loop is None:
            self.loop = load_loop(self.loop_runner)
        loop = self.loop
        # Keep serve.mjs in the imported loop; never copy it into the protocol.
        loop.ZEP_DISTS, loop.ZEP_SRC, loop.ZEP_UPSTREAM = self.dists, self.source, UPSTREAM
        if self.engine is not None:
            loop.engine = self.engine
        loop.engine.FIXTURE_MODULES = self.fixture_modules
        return loop

    @contextmanager
    def campaign(self):
        if self.lock is not None:
            raise ValueError("Zeppelin campaign is already active")
        with CampaignLock(self.lock_path, self.process_probe, self.campaign_id) as lock:
            self.inherit_lock(lock)
            try:
                yield self
            finally:
                self.lock = None

    def inherit_lock(self, lock):
        """Attach the parent driver's already-held shared lock without reentry."""
        if self.lock is not None:
            raise ValueError("Zeppelin runtime already has a campaign lock")
        if not isinstance(lock, CampaignLock) or lock.handle is None or lock.handle.closed:
            raise ValueError("Zeppelin runtime requires an open owned CampaignLock")
        if lock.path.resolve() != self.lock_path.resolve():
            raise ValueError("Zeppelin runtime cannot inherit a different campaign lock path")
        if lock.path.stat().st_ino != os.fstat(lock.handle.fileno()).st_ino:
            raise ValueError("Zeppelin campaign lock file no longer matches its held handle")
        if json.loads(lock.path.read_text()).get("pid") != os.getpid():
            raise ValueError("Zeppelin campaign lock was not acquired by this driver")
        self.lock = lock

    def _validate_notes(self, loop, before, folder, phase):
        violations = isolation_violations(before, note_snapshot(loop.zep_api), folder)
        if violations:
            self.note_isolation_violations.extend({**item, "phase": phase} for item in violations)
            escapes = [v["note_id"] for v in violations if v["kind"] == "new_note_outside_namespace"]
            # Exclusive ownership makes new IDs cell-owned, even when the model
            # ignored notePath. Never delete a preexisting ID.
            delete_and_verify(loop.zep_api, escapes)
            if any(v["kind"].startswith("preexisting_") for v in violations):
                raise RuntimeError("Zeppelin cell note isolation violated; preexisting notes changed, stop campaign")

    def _require_lock(self):
        if self.lock is None or self.lock.handle is None:
            raise ValueError("Zeppelin live phase requires the shared campaign lock")
        if self.lock.process_probe():
            raise CampaignPaused("another generator benchmark driver appeared; pause before shared Zeppelin phase")

    @contextmanager
    def _phase(self, phase, cell_id):
        self._require_lock()
        folder = namespace(self.campaign_id, cell_id)
        if not self._phase_lock.acquire(blocking=False):
            raise ValueError("generation or scoring is active; refusing overlapping Zeppelin use")
        self.phase = phase
        try:
            loop = self._configured_loop()
            clean_namespace(loop.zep_api, folder)
            before = note_snapshot(loop.zep_api)
            yield loop, folder
        finally:
            try:
                if "loop" in locals():
                    try:
                        if "before" in locals():
                            self._validate_notes(loop, before, folder, phase)
                    finally:
                        clean_namespace(loop.zep_api, folder)
            finally:
                self.phase = None
                self._phase_lock.release()

    @contextmanager
    def generation(self, cell_id):
        with self._phase("generation", cell_id) as (loop, folder):
            with OwnedVariantServer(loop, "clean", PORT):
                yield {"base": f"http://host.docker.internal:{PORT}", "folder": folder}

    def stage(self, work, base, folder):
        """Project stage from the loop, with only note ownership text adjusted."""
        loop = self._configured_loop()
        project = loop.zep_stage(Path(work), base)
        readme = project / "README.md"
        readme.write_text(readme.read_text().replace("E2E_LOOP/", folder + "/"))
        return project

    def prompt(self, scope, base, folder):
        frame = self._configured_loop().ZEP_FRAME.format(task=scope, base=base, folder=folder)
        return frame + NOTE_CREATION_POLICY.format(folder=folder)

    def generation_config(self, project):
        text = (Path(project) / "playwright.config.ts").read_text()
        normalized = re.sub(r"(https?://(?:127\.0\.0\.1|host\.docker\.internal):)\d+", r"\1PORT", text)
        digest = hashlib.sha256(normalized.encode()).hexdigest()
        return {"reuse_existing_server": True, "external_server": True, "stages": 1,
                "config_sha256_port_normalized": [digest],
                "scoring_config_sha256_port_normalized": [digest]}

    def evaluate(self, case, tests_src, specs, cell_id, expected_failures=None):
        if case not in self.task_ids:
            raise ValueError("task is outside this runtime's explicit task allowlist")
        patches = sorted((self.pool / "tasks" / case / "patches").glob("D*.patch"))
        if len(patches) != 5 or {p.stem.split("-", 1)[0] for p in patches} != {"D1", "D2", "D3", "D4", "D5"}:
            raise ValueError("task must supply exactly D1-D5")
        refactor = self.pool / "tasks" / case / "patches/R1-markup-refactor.patch"
        if not refactor.is_file():
            raise ValueError("task must supply R1-markup-refactor.patch")
        with self._phase("scoring", cell_id) as (loop, folder):
            def run(variant):
                loop.engine.wait_for_load({})
                clean_namespace(loop.zep_api, folder)
                before = note_snapshot(loop.zep_api)
                try:
                    with OwnedVariantServer(loop, variant, PORT):
                        with tempfile.TemporaryDirectory(prefix="generator-oss-score-") as temp:
                            project = self.stage(Path(temp).resolve(), f"http://127.0.0.1:{PORT}", folder)
                            shutil.rmtree(project / "tests")
                            shutil.copytree(tests_src, project / "tests")
                            # Literal Docker-host URLs must address the same proxy from
                            # the host scorer. Normalize scratch copies only, identically
                            # for every variant; retain original delivered bytes.
                            for test_file in (project / "tests").rglob("*"):
                                if test_file.is_file():
                                    test_file.write_text(test_file.read_text().replace(
                                        f"http://host.docker.internal:{PORT}", f"http://127.0.0.1:{PORT}"))
                            kwargs = {"timeout": 600, "env_extra": {"PLAYWRIGHT_BASE_URL": f"http://127.0.0.1:{PORT}", "E2E_NOTE_FOLDER": folder}}
                            defect = variant.split("--", 1)[-1].split("-", 1)[0]
                            if expected_failures and defect in expected_failures:
                                kwargs["expected_failure"] = expected_failures[defect]
                            result = run_playwright_records(project, specs, **kwargs)
                            escapes = isolation_violations(before, note_snapshot(loop.zep_api), folder)
                            if escapes:
                                result.update(ok=False, isolation_violations=escapes)
                            result["load_1m"] = round(os.getloadavg()[0], 2)
                            return result
                finally:
                    try:
                        self._validate_notes(loop, before, folder, "scoring:" + variant)
                    finally:
                        clean_namespace(loop.zep_api, folder)
            clean_runs = [run("clean") for _ in range(3)]
            faults = {p.stem: run(f"{case}--{p.stem}") for p in patches}
            return scoring_result(clean_runs, faults, run(f"{case}--R1-markup-refactor"))
