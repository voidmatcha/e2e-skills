#!/usr/bin/env python3
"""Model-free opt-in check of explicit Chromium CLI and owned-server lifecycle. Apache-2.0."""
from __future__ import annotations

import importlib.util
import json
from pathlib import Path
import re

_spec = importlib.util.spec_from_file_location("environment_probe", Path(__file__).with_name("generator-environment-probe.py"))
base = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(base)

LIMITATION = "One public fixture; model-free environment readiness only, not quality equivalence or measured cost reduction."
PROBE = r'''
import json, pathlib, subprocess, tempfile, time, urllib.request, uuid
files = __FILES__
checks = {}
commands = []
def run(argv, cwd, timeout=45):
    commands.append(argv)
    p = subprocess.run(argv, cwd=cwd, capture_output=True, text=True, timeout=timeout)
    return {"exit": p.returncode, "stdout": p.stdout, "stderr": p.stderr}
def stop(p):
    if p is not None and p.poll() is None:
        p.terminate()
        try: p.wait(timeout=5)
        except subprocess.TimeoutExpired:
            p.kill(); p.wait(timeout=5)
with tempfile.TemporaryDirectory(prefix="generator-successor-environment-") as raw:
    project = pathlib.Path(raw)
    for name, text in files.items():
        path = project / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text.replace("__PORT__", "43819"))
    (project / "node_modules").symlink_to("/opt/fixtures/node_modules")
    cli = ["node_modules/.bin/playwright", "cli"]
    checks["cli_help"] = run(cli + ["open", "--help"], project)
    checks["pre_start_health"] = run(["curl", "--max-time", "2", "--silent", "--show-error", "http://127.0.0.1:43819/health"], project)
    guard = pathlib.Path(tempfile.mkdtemp(prefix="cli-guard-"))
    config = guard / "config.json"
    config.write_text(json.dumps({"network": {"allowedOrigins": ["http://127.0.0.1:43819"]}}))
    cli = [str(project / "node_modules/.bin/playwright"), "cli", "-s=successor-probe-" + uuid.uuid4().hex]
    app = None
    url = "http://127.0.0.1:43819/health"
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
                checks["explicit_cli"] = run(cli + ["open", "about:blank", "--browser", "chromium", "--config", str(config)], guard)
                if checks["explicit_cli"]["exit"] == 0:
                    checks["browser_identity"] = run(cli + ["eval", "navigator.userAgent"], guard)
                    checks["guard_fetch"] = run(cli + ["eval", "fetch('http://127.0.0.1:9/').catch(e => String(e))"], guard)
                    checks["guard_requests"] = run(cli + ["requests"], guard)
                    if any("http://127.0.0.1:9/" in line and "net::ERR_BLOCKED_BY_CLIENT" in line for line in checks["guard_requests"]["stdout"].splitlines()) and checks["guard_fetch"]["exit"] == 0 and checks["guard_requests"]["exit"] == 0:
                        checks["goto"] = run(cli + ["goto", "http://127.0.0.1:43819"], guard)
                        checks["snapshot"] = run(cli + ["snapshot"], guard)
    finally:
        checks["cli_close"] = run(cli + ["close"], guard)
        stop(app)
        checks["owned_app_stopped"] = {"stopped": app is not None and app.poll() is not None}
    checks["post_cleanup_health"] = run(["curl", "--max-time", "2", "--silent", "--show-error", url], project)
    checks["test_after_owned_cleanup"] = run(["node_modules/.bin/playwright", "test", "--repeat-each=3", "--reporter=line"], project, timeout=90)
print(json.dumps({"checks": checks, "commands": commands}))
'''


def fixture_payload():
    _, digests = _original_fixture_payload()
    names = ("app.mjs", "playwright.config.mjs", "package.json", "tests/smoke.spec.mjs")
    files = {name: (base.CASE / name).read_text(encoding="utf-8") for name in names}
    return PROBE.replace("__FILES__", repr(files)), digests


def classify(checks):
    opened = checks.get("explicit_cli", {})
    snapshot = checks.get("snapshot", {})
    tested = checks.get("test_after_owned_cleanup", {})
    safe = {
        "pre_start_connection_refused": checks.get("pre_start_health", {}).get("exit") == 7,
        "cli_help_available": checks.get("cli_help", {}).get("exit") == 0 and "--browser" in checks.get("cli_help", {}).get("stdout", ""),
        "owned_server_ready": checks.get("owned_app_ready", {}).get("ready") is True,
        "explicit_chromium_cli_open": opened.get("exit") == 0 and "Page URL: about:blank" in opened.get("stdout", "") and checks.get("browser_identity", {}).get("exit") == 0 and "HeadlessChrome" in checks.get("browser_identity", {}).get("stdout", ""),
        "deny_unapproved_origin": checks.get("guard_fetch", {}).get("exit") == 0 and checks.get("guard_requests", {}).get("exit") == 0 and any("http://127.0.0.1:9/" in line and "net::ERR_BLOCKED_BY_CLIENT" in line for line in checks.get("guard_requests", {}).get("stdout", "").splitlines()),
        "approved_origin_navigation": checks.get("goto", {}).get("exit") == 0 and "Page URL: http://127.0.0.1:43819/" in checks.get("goto", {}).get("stdout", ""),
        "cli_snapshot": snapshot.get("exit") == 0 and "Snapshot" in snapshot.get("stdout", ""),
        "cli_closed": checks.get("cli_close", {}).get("exit") == 0,
        "owned_app_stopped": checks.get("owned_app_stopped", {}).get("stopped") is True,
        "owned_port_released": checks.get("post_cleanup_health", {}).get("exit") == 7,
        "three_tests_after_cleanup": tested.get("exit") == 0 and bool(re.search(r"(?<!\d)3 passed\b", tested.get("stdout", ""))),
    }
    return {"status": "PASS" if all(safe.values()) else "INCONCLUSIVE", "safe_setup": safe}


_original_fixture_payload = base.fixture_payload


def main():
    # Reuse the reviewed opt-in, disk floor, strict environment, immutable image,
    # mount-free container bounds, and exact owned-container cleanup unchanged.
    base.fixture_payload = fixture_payload
    base.classify = classify
    base.LIMITATION = LIMITATION
    base.main()


if __name__ == "__main__":
    main()
