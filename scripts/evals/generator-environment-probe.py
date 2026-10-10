#!/usr/bin/env python3
"""Model-free, opt-in diagnostic of generator fixture ownership. Apache-2.0."""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import uuid

ROOT = Path(__file__).resolve().parents[2]
CASE = ROOT / "benchmarks/generator-skill-effect-v3/cases/v2-20"
IMAGE = "sha256:687b18c424d01c3af69efa921eaa824b48eb737d46492da334405e348da73881"
LIMITATION = "One public fixture, no model or skill arms; no quality, cost reduction, or CLI configuration claim."

# All writes and process ownership below are inside the disposable container.
PROBE = r'''
import json, pathlib, subprocess, tempfile, time, urllib.request
files = __FILES__
checks = {}
commands = []
def run(argv, cwd, timeout=45):
    commands.append(argv)
    p = subprocess.run(argv, cwd=cwd, capture_output=True, text=True, timeout=timeout)
    return {"exit": p.returncode, "stdout": p.stdout[-4000:], "stderr": p.stderr[-4000:]}
def stop(p):
    if p is not None and p.poll() is None:
        p.terminate()
        try: p.wait(timeout=5)
        except subprocess.TimeoutExpired:
            p.kill(); p.wait(timeout=5)
with tempfile.TemporaryDirectory(prefix="generator-environment-") as raw:
    project = pathlib.Path(raw)
    for name, text in files.items():
        path = project / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text.replace("__PORT__", "43819"))
    (project / "node_modules").symlink_to("/opt/fixtures/node_modules")
    # A unique container network namespace makes this fixed loopback port private.
    url = "http://127.0.0.1:43819/health"
    checks["pre_start"] = run(["curl", "--max-time", "2", "--silent", "--show-error", url], project)
    checks["default_cli"] = run(["node_modules/.bin/playwright", "cli", "open", "about:blank"], project)
    # Close only the browser session created in this isolated container.
    checks["cli_close"] = run(["node_modules/.bin/playwright", "cli", "close"], project)
    browser_js = "const {chromium}=require('playwright'); (async()=>{const b=await chromium.launch(); const p=await b.newPage(); await p.goto('about:blank'); await b.close(); console.log('installed chromium ready');})().catch(e=>{console.error(e);process.exit(1)});"
    checks["explicit_chromium"] = run(["node", "-e", browser_js], project)
    app = None
    try:
        with (project / "app.log").open("w") as log:
            app = subprocess.Popen(["node", "app.mjs"], cwd=project, stdout=log, stderr=log)
            deadline = time.monotonic() + 10
            ready = False
            while time.monotonic() < deadline and app.poll() is None:
                try:
                    with urllib.request.urlopen(url, timeout=1) as r: ready = r.status == 200
                    if ready: break
                except OSError: pass
                time.sleep(.1)
            checks["owned_app_ready"] = {"ready": ready, "exit": app.poll()}
            if ready:
                checks["duplicate_app"] = run(["node", "app.mjs"], project, timeout=10)
                checks["test_with_external_owner"] = run(["node_modules/.bin/playwright", "test", "--reporter=line"], project)
    finally:
        stop(app)
    checks["test_after_owned_cleanup"] = run(["node_modules/.bin/playwright", "test", "--repeat-each=3", "--reporter=line"], project, timeout=90)
print(json.dumps({"checks": checks, "commands": commands}))
'''


def fixture_payload():
    names = ("app.mjs", "playwright.config.mjs", "package.json", "tests/smoke.spec.mjs")
    files = {name: (CASE / name).read_text(encoding="utf-8") for name in names}
    return PROBE.replace("__FILES__", repr(files)), {
        name: hashlib.sha256(text.encode()).hexdigest() for name, text in files.items()
    }


def classify(checks):
    """Expected failing controls must fail for the exact reason, never generically."""
    cli = checks.get("default_cli", {})
    missing_chrome = cli.get("exit", 0) != 0 and "chrome" in (cli.get("stdout", "") + cli.get("stderr", "")).lower() and "not found" in (cli.get("stdout", "") + cli.get("stderr", "")).lower()
    duplicate = checks.get("duplicate_app", {})
    ownership = checks.get("test_with_external_owner", {})
    controls = {
        "pre_start_connection_refused": checks.get("pre_start", {}).get("exit") == 7,
        "default_cli_missing_chrome": missing_chrome,
        "duplicate_owner_rejected": duplicate.get("exit", 0) != 0 and "EADDRINUSE" in duplicate.get("stderr", ""),
        "webserver_rejects_external_owner": ownership.get("exit", 0) != 0 and "already used" in (ownership.get("stderr", "") + ownership.get("stdout", "")),
    }
    safe = {
        "explicit_installed_chromium": checks.get("explicit_chromium", {}).get("exit") == 0,
        "owned_server_ready": checks.get("owned_app_ready", {}).get("ready") is True,
        "three_tests_after_cleanup": checks.get("test_after_owned_cleanup", {}).get("exit") == 0 and bool(re.search(r"(?<!\d)3 passed\b", checks.get("test_after_owned_cleanup", {}).get("stdout", ""))),
    }
    return {"status": "PASS" if all(controls.values()) and all(safe.values()) else "INCONCLUSIVE", "expected_failure_controls": controls, "safe_setup": safe}


def docker_command(docker, context, name):
    if not Path(docker).is_absolute():
        raise ValueError("Docker executable must be absolute")
    return [docker, "--context", context, "run", "--pull=never", "--rm", "--interactive", "--init", "--name", name,
            "--network", "none", "--read-only", "--cap-drop", "ALL", "--security-opt", "no-new-privileges",
            "--user", "1000:1000", "--memory", "2g", "--cpus", "2", "--pids-limit", "256", "--shm-size", "512m",
            "--tmpfs", "/tmp:rw,nosuid,nodev,mode=1777,size=256m", "--env", "HOME=/tmp",
            "--env", "PLAYWRIGHT_BROWSERS_PATH=/ms-playwright", IMAGE, "python3", "-"]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--allow-browser", action="store_true")
    parser.add_argument("--context", default="colima")
    args = parser.parse_args()
    if not args.allow_browser:
        parser.error("Docker/browser execution requires --allow-browser; nothing is downloaded")
    if shutil.disk_usage(ROOT).free < 4 * 1024 ** 3:
        parser.error("disk floor: at least 4 GiB free required")
    docker = shutil.which("docker")
    if not docker:
        parser.error("Docker is not installed")
    payload, digests = fixture_payload()
    name = "generator-environment-" + uuid.uuid4().hex
    # The client needs HOME for its chosen context, not ambient API credentials.
    env = {"HOME": os.path.expanduser("~"), "PATH": "/usr/bin:/bin:/usr/sbin:/sbin"}
    try:
        result = subprocess.run(docker_command(docker, args.context, name), input=payload,
                                capture_output=True, text=True, timeout=240, env=env)
        if result.returncode:
            raise RuntimeError("container probe failed: " + result.stderr[-1000:])
        evidence = json.loads(result.stdout)
        print(json.dumps({**classify(evidence["checks"]), "image": IMAGE, "fixture": "v2-20",
                          "fixture_sha256": digests, "limitation": LIMITATION, **evidence}, indent=2))
    finally:
        cleanup = subprocess.run([docker, "--context", args.context, "rm", "--force", name],
                                 capture_output=True, text=True, timeout=30, env=env)
        if cleanup.returncode and "No such container" not in cleanup.stderr:
            raise RuntimeError("cleanup of owned probe container failed")


if __name__ == "__main__":
    main()
