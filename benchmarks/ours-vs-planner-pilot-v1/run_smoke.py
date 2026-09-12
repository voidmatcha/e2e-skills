#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Smoke stage for benchmarks/ours-vs-planner-pilot-v1 (protocol.json -> schedule.smoke_cells).

Runs the four UNSCORED smoke cells (2 targets x 2 arms) on the smoke scenario
"the application shell loads and the primary navigation is visible", which is
deliberately NOT one of the six frozen scenarios. Each cell proves, end to end:

  fetch pinned SHA -> dependency install -> dev server reachable (own step)
  -> [planner arm only] `playwright init-agents --loop=claude` (hashed)
  -> one disposable Claude Code generation session in that checkout
  -> harness-side native run of the produced candidate spec
  -> git-based drift check -> cleanup of checkout + runner home

Nothing here freezes the protocol, writes freeze-record.json, touches the six
frozen scenarios, or scores anything. Results go to smoke-results.json after
every cell (crash-safe atomic replace); per-cell durable artifacts (redacted
session transcript, candidate spec copy, native-run output, planner delta) go
to smoke-artifacts/<cell_id>/.

Credential handling and process isolation are NOT re-implemented here: this
script calls the shared helpers in scripts/evals/run-reviewer-holdout.py
(clean_env, claude_runner_credentials, _validate_claude_oauth_token,
communicate_bounded, stop_process_group, resolve_runner_executable) and
scripts/evals/eval_security.py (sanitize_model_output, credential patterns,
replace_atomic_and_sync_parent), exactly as run-generator-faultkill.py does.
"""

from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import platform
import pwd
import re
import shlex
import shutil
import signal
import socket
import subprocess
import sys
import tempfile
import time
from typing import Any
import urllib.error
import urllib.request


ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts/ci/lib"))
sys.path.insert(0, str(ROOT / "scripts/evals"))

import eval_security  # noqa: E402
from eval_security import replace_atomic_and_sync_parent, sanitize_model_output  # noqa: E402


def load_module(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"cannot import shared module: {path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


REVIEWER = load_module("run_reviewer_holdout", ROOT / "scripts/evals/run-reviewer-holdout.py")

PILOT_DIR = ROOT / "benchmarks/ours-vs-planner-pilot-v1"
PROTOCOL_PATH = PILOT_DIR / "protocol.json"
RESULTS_PATH = PILOT_DIR / "smoke-results.json"
ARTIFACTS_DIR = PILOT_DIR / "smoke-artifacts"
SKILLS_DIR = ROOT / "skills"
STAGED_SKILLS = ("playwright-test-generator", "e2e-reviewer", "playwright-debugger", "cypress-debugger")

SMOKE_SCENARIO = "the application shell loads and the primary navigation is visible"
CANDIDATE_RELATIVE = "e2e/smoke-shell.spec.ts"
PLANNER_DELTA_RELATIVE = "specs/smoke-planner-delta.md"
ARMS = ("ours_only", "planner_plus_ours")
UPSTREAM_PORT = 5173  # both targets hardcode this; it collides with a tailscale serve route on this host
PORT_SEARCH_START = 5174  # operator-chosen replacement; the first wildcard-bindable port from here is used
PORT_SEARCH_END = 5199
PORT = PORT_SEARCH_START  # reassigned in main() after the dynamic port selection
PATCHED_CONFIG_FILES = ("playwright.config.ts", "vite.config.ts")

FETCH_TIMEOUT_S = 900
INSTALL_TIMEOUT_S = 900
DEV_SERVER_READY_TIMEOUT_S = 180
INIT_AGENTS_TIMEOUT_S = 300
# Aligned with protocol.json cost_ceiling.hard_ceiling.per_cell_wall_minutes (45 / 60). The first
# smoke pass used 30 / 40 and censored smoke-B-planner_plus_ours mid-way through its fifth V6
# review round; that cell's single infrastructure-only retry ran at the protocol cap.
SESSION_TIMEOUT_S = {"ours_only": 45 * 60, "planner_plus_ours": 60 * 60}
SESSION_MAX_TURNS = 250
SESSION_MAX_BUDGET_USD = "40"
NATIVE_RUN_TIMEOUT_S = 600
SETUP_RETRIES = 1  # protocol cost_ceiling.retries.infrastructure_only

# Session-side extras layered on top of REVIEWER.clean_env (none is a credential).
TOOLCHAIN_ENV = {
    "NO_COLOR": "1",
    "COREPACK_ENABLE_STRICT": "0",
    "COREPACK_ENABLE_DOWNLOAD_PROMPT": "0",
    "npm_config_update_notifier": "false",
    "npm_config_fund": "false",
    "npm_config_audit": "false",
}
CLAUDE_SESSION_ENV = {
    "DISABLE_AUTOUPDATER": "1",
    "CLAUDE_CODE_DISABLE_NONESSENTIAL_TRAFFIC": "1",
}


def utc_now() -> str:
    return dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds")


def sha256_bytes(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def sha256_file(path: Path) -> str:
    return sha256_bytes(path.read_bytes())


def write_results(report: dict[str, Any]) -> None:
    with tempfile.NamedTemporaryFile("w", encoding="utf-8", dir=RESULTS_PATH.parent, delete=False) as handle:
        json.dump(report, handle, indent=2, sort_keys=False, allow_nan=False, ensure_ascii=False)
        handle.write("\n")
        handle.flush()
        os.fsync(handle.fileno())
        temporary = Path(handle.name)
    replace_atomic_and_sync_parent(temporary, RESULTS_PATH)


def log(message: str) -> None:
    print(f"[{utc_now()}] {message}", flush=True)


# --------------------------------------------------------------------------- toolchain


def select_node_bin() -> Path:
    """Pick one Node >= 24 bin dir; REVIEWER.trusted_runner_search_path() lists nvm
    dirs in lexical order (v18 first), so the target-required Node 24 must be
    fronted explicitly. Prefers the ambient default `node` when it qualifies."""
    home = Path(pwd.getpwuid(os.getuid()).pw_dir)
    required = ("node", "npm", "npx", "pnpm")

    def qualifies(directory: Path) -> bool:
        return all((directory / tool).exists() for tool in required)

    ambient = shutil.which("node")
    if ambient:
        candidate = Path(ambient).resolve().parent
        if candidate.name == "bin" and candidate.parent.name.startswith("v24") and qualifies(candidate):
            return candidate
    candidates = sorted(
        (path / "bin" for path in (home / ".nvm/versions/node").glob("v24.*")),
        key=lambda p: tuple(int(x) for x in p.parent.name[1:].split(".")),
    )
    for candidate in reversed(candidates):
        if qualifies(candidate):
            return candidate
    raise RuntimeError("no Node 24 toolchain with node/npm/npx/pnpm found under ~/.nvm")


def short_tmpdir(runner_home: Path) -> str:
    """One short, private (0700) temp dir per runner home, e.g. /tmp/ovp-XXXXXX, recorded in
    runner_home/tmp-link so cleanup can find and remove it."""
    marker = runner_home / "short-tmpdir"
    if marker.is_file():
        return marker.read_text(encoding="utf-8").strip()
    path = tempfile.mkdtemp(prefix="ovp-", dir="/tmp")
    os.chmod(path, 0o700)
    marker.write_text(path, encoding="utf-8")
    return path


def build_env(runner_home: Path, node_bin: Path, cache: dict[str, Path], *, claude: bool = False,
              credentials: dict[str, str] | None = None, extra: dict[str, str] | None = None) -> dict[str, str]:
    environment = REVIEWER.clean_env("claude" if claude else None, str(runner_home))
    environment["PATH"] = os.pathsep.join([str(node_bin), environment["PATH"]])
    environment.update(TOOLCHAIN_ENV)
    environment.pop("CI", None)  # CI is set only per-target for the harness-side native run
    environment["npm_config_cache"] = str(cache["npm"])
    environment["npm_config_store_dir"] = str(cache["pnpm"])
    environment["COREPACK_HOME"] = str(cache["corepack"])
    environment["PLAYWRIGHT_BROWSERS_PATH"] = str(cache["browsers"])
    # Always a short path: tsx (target B's dev script) creates a Unix IPC socket under TMPDIR and
    # macOS caps socket paths at ~104 bytes; a TMPDIR inside the runner home hit EINVAL. Short by
    # default rather than discovering the OS limit at runtime (operator guidance 2026-09-11).
    environment["TMPDIR"] = short_tmpdir(runner_home)
    if claude:
        if credentials is None or set(credentials) != {"CLAUDE_CODE_OAUTH_TOKEN"}:
            raise ValueError("Claude sessions require exactly one minimal OAuth credential")
        environment["CLAUDE_CODE_OAUTH_TOKEN"] = REVIEWER._validate_claude_oauth_token(
            credentials["CLAUDE_CODE_OAUTH_TOKEN"]
        )
        environment.update(CLAUDE_SESSION_ENV)
    if extra:
        environment.update(extra)
    return environment


def run_bounded(command: list[str], cwd: Path, env: dict[str, str], timeout: int,
                stdin_text: str | None = None) -> dict[str, Any]:
    """Popen in its own session + REVIEWER.communicate_bounded (1 MiB cap, group kill on timeout)."""
    started = time.monotonic()
    record: dict[str, Any] = {"command": command, "cwd": str(cwd), "timeout_s": timeout}
    with tempfile.TemporaryFile(mode="w+b") as stdin_file:
        stdin_file.write((stdin_text or "").encode())
        stdin_file.seek(0)
        process = subprocess.Popen(
            command, cwd=cwd, env=env, stdin=stdin_file,
            stdout=subprocess.PIPE, stderr=subprocess.PIPE, start_new_session=True,
        )
        try:
            stdout, stderr = REVIEWER.communicate_bounded(process, command, timeout)
            record.update(returncode=process.returncode, timed_out=False)
        except subprocess.TimeoutExpired as exc:
            stdout, stderr = exc.stdout or "", exc.stderr or ""
            record.update(returncode=None, timed_out=True,
                          cleanup_failures=getattr(exc, "cleanup_failures", []))
        except ValueError as exc:  # output cap exceeded; group already stopped
            stdout, stderr = "", ""
            record.update(returncode=None, timed_out=False, error=str(exc),
                          cleanup_failures=getattr(exc, "cleanup_failures", []))
        finally:
            for stream in (process.stdout, process.stderr):
                if stream is not None:
                    stream.close()
    record["elapsed_s"] = round(time.monotonic() - started, 1)
    record["stdout"] = stdout
    record["stderr"] = stderr
    return record


def summarize(record: dict[str, Any], tail_chars: int = 1500) -> dict[str, Any]:
    """Results-file view of a run_bounded record: no full output, only tails + digests."""
    out = {k: v for k, v in record.items() if k not in {"stdout", "stderr"}}
    for name in ("stdout", "stderr"):
        text = record.get(name, "")
        out[f"{name}_sha256"] = sha256_bytes(text.encode())
        out[f"{name}_bytes"] = len(text.encode())
        out[f"{name}_tail"] = text[-tail_chars:]
    return out


def git(args: list[str], cwd: Path, timeout: int = 300) -> subprocess.CompletedProcess[str]:
    return subprocess.run(["/usr/bin/git", *args], cwd=cwd, capture_output=True, text=True,
                          check=False, timeout=timeout,
                          env={"PATH": "/usr/bin:/bin", "HOME": str(cwd), "GIT_TERMINAL_PROMPT": "0"})


# --------------------------------------------------------------------------- port + dev server


def port_free() -> bool:
    for family, address in ((socket.AF_INET, "127.0.0.1"), (socket.AF_INET6, "::1")):
        sock = socket.socket(family, socket.SOCK_STREAM)
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        try:
            sock.bind((address, PORT))
        except OSError:
            return False
        finally:
            sock.close()
    return True


def wildcard_port_precondition() -> dict[str, Any]:
    """Vite checks port availability with a wildcard listen, so a socket bound to ANY
    interface address on PORT (e.g. a `tailscale serve` route on the tailnet address,
    invisible to a loopback bind probe and to unprivileged lsof) makes it hop to another
    port and breaks both targets' hardcoded http://localhost:5173 baseURL/webServer."""
    failures = {}
    for family, address in ((socket.AF_INET, "0.0.0.0"), (socket.AF_INET6, "::")):
        sock = socket.socket(family, socket.SOCK_STREAM)
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        try:
            sock.bind((address, PORT))
            sock.listen(1)
        except OSError as exc:
            failures[address] = str(exc)
        finally:
            sock.close()
    if not failures:
        return {"ok": True}
    netstat = subprocess.run(["/usr/sbin/netstat", "-an"], capture_output=True, text=True, check=False, timeout=30)
    bound = [line.strip() for line in netstat.stdout.splitlines() if f".{PORT} " in line and "LISTEN" in line]
    hint = None
    tailscale = Path("/Applications/Tailscale.app/Contents/MacOS/Tailscale")
    if tailscale.is_file():
        status = subprocess.run([str(tailscale), "serve", "status"], capture_output=True, text=True, check=False, timeout=30)
        routes = [line.strip() for line in status.stdout.splitlines() if f":{PORT} " in line or f":{PORT}\n" in line + "\n"]
        if routes:
            hint = {"tailscale_serve_routes_on_port": routes,
                    "resolution": f"operator must remove the tailscale serve route on {PORT} (or the whole "
                                  f"listener) before the smoke stage can run; the harness never mutates host state"}
    return {"ok": False, "wildcard_bind_failures": failures, "listening_sockets": bound, "hint": hint}


def select_port() -> dict[str, Any]:
    """First port in [PORT_SEARCH_START, PORT_SEARCH_END] that is bindable on the wildcard
    AND loopback addresses (5174/5175 are held by unrelated operator dev servers here)."""
    global PORT
    rejected = {}
    for candidate in range(PORT_SEARCH_START, PORT_SEARCH_END + 1):
        PORT = candidate
        precondition = wildcard_port_precondition()
        if precondition["ok"] and port_free():
            return {"chosen_port": candidate, "search_start": PORT_SEARCH_START, "rejected": rejected}
        rejected[candidate] = precondition.get("listening_sockets") or "loopback busy"
    raise RuntimeError(f"no free port in {PORT_SEARCH_START}-{PORT_SEARCH_END}: {rejected}")


def patch_ports(workspace: Path) -> dict[str, Any]:
    """Operator-authorized port substitution inside the DISPOSABLE checkout only:
    playwright.config.ts: every literal 5173 -> PORT (baseURL + webServer.url);
    vite.config.ts: inject `port: PORT, strictPort: true` so Vite serves exactly PORT
    (neither target sets server.port, so a plain text replace alone would leave Vite on 5173).
    The upstream repository is never touched; the checkout is deleted after the cell."""
    touched = []
    for name in PATCHED_CONFIG_FILES:
        path = workspace / name
        if not path.is_file():
            touched.append({"file": name, "status": "absent"})
            continue
        before = path.read_text(encoding="utf-8")
        after = before.replace(str(UPSTREAM_PORT), str(PORT))
        if name == "vite.config.ts":
            injection = f"port: {PORT}, strictPort: true, /* smoke-harness port substitution */\n"
            if re.search(r"\bserver:\s*\{", after):
                after = re.sub(r"(\bserver:\s*\{)", lambda m: m.group(1) + "\n    " + injection, after, count=1)
            elif "defineConfig({" in after:
                after = after.replace("defineConfig({", "defineConfig({\n  server: { " + injection.rstrip("\n") + " },", 1)
            else:
                return {"ok": False, "error": "vite.config.ts has no defineConfig({ to inject a server port into", "files": touched}
        path.write_text(after, encoding="utf-8")
        touched.append({"file": name, "status": "patched", "sha256_before": sha256_bytes(before.encode()),
                        "sha256_after": sha256_bytes(after.encode()),
                        "occurrences_of_upstream_port_remaining": after.count(str(UPSTREAM_PORT)),
                        "occurrences_of_new_port": after.count(str(PORT))})
    ok = all(t["status"] == "patched" and t["occurrences_of_upstream_port_remaining"] == 0 and t["occurrences_of_new_port"] > 0
             for t in touched)
    return {"ok": ok, "upstream_port": UPSTREAM_PORT, "new_port": PORT, "files": touched,
            "scope": "disposable checkout only; upstream repository untouched; checkout deleted after the cell"}


def port_listeners() -> list[dict[str, Any]]:
    result = subprocess.run(["/usr/sbin/lsof", "-nP", f"-tiTCP:{PORT}", "-sTCP:LISTEN"],
                            capture_output=True, text=True, check=False, timeout=30)
    listeners = []
    for token in result.stdout.split():
        try:
            pid = int(token)
        except ValueError:
            continue
        cwd = subprocess.run(["/usr/sbin/lsof", "-a", "-p", str(pid), "-d", "cwd", "-Fn"],
                             capture_output=True, text=True, check=False, timeout=30)
        cwd_path = next((line[1:] for line in cwd.stdout.splitlines() if line.startswith("n")), "")
        cmd = subprocess.run(["/bin/ps", "-o", "command=", "-p", str(pid)],
                             capture_output=True, text=True, check=False, timeout=30)
        listeners.append({"pid": pid, "cwd": cwd_path, "command": cmd.stdout.strip()[:200]})
    return listeners


def sweep_port(workspace: Path) -> dict[str, Any]:
    """Kill only listeners whose cwd is inside this cell's workspace. Foreign listeners are
    reported, never killed (this machine has unrelated dev servers on nearby ports)."""
    real_ws = os.path.realpath(workspace)
    killed, foreign = [], []
    for listener in port_listeners():
        if listener["cwd"] and os.path.realpath(listener["cwd"]).startswith(real_ws):
            for sig in (signal.SIGTERM, signal.SIGKILL):
                try:
                    os.kill(listener["pid"], sig)
                except ProcessLookupError:
                    break
                time.sleep(1.5)
            killed.append(listener)
        else:
            foreign.append(listener)
    return {"killed_workspace_listeners": killed, "foreign_listeners": foreign, "port_free_after": port_free()}


def http_status(url: str) -> int | None:
    try:
        with urllib.request.urlopen(url, timeout=3) as response:  # noqa: S310 - loopback only
            return response.status
    except urllib.error.HTTPError as exc:
        return exc.code
    except (urllib.error.URLError, OSError, ValueError):
        return None


def dev_server_check(target: dict[str, Any], workspace: Path, env: dict[str, str]) -> dict[str, Any]:
    """Own verifiable step: start dev server, wait until base_url answers 200, stop it, confirm port free."""
    base_url = target["dev_server"]["base_url"]
    record: dict[str, Any] = {"base_url": base_url, "command": target["dev_server"]["command"]}
    if not port_free():
        record.update(ok=False, error="port busy before start", listeners=port_listeners())
        return record
    started = time.monotonic()
    with tempfile.TemporaryFile(mode="w+b") as sink:
        process = subprocess.Popen(shlex.split(target["dev_server"]["command"]), cwd=workspace, env=env,
                                   stdin=subprocess.DEVNULL, stdout=sink, stderr=subprocess.STDOUT,
                                   start_new_session=True)
        status = None
        while time.monotonic() - started < DEV_SERVER_READY_TIMEOUT_S:
            if process.poll() is not None:
                break
            status = http_status(base_url + "/")
            if status == 200:
                break
            time.sleep(2)
        ready_s = round(time.monotonic() - started, 1)
        exited_early = process.poll() is not None
        REVIEWER.stop_process_group(process)
        sink.seek(0)
        output = sink.read().decode(errors="replace")
    deadline = time.monotonic() + 20
    while not port_free() and time.monotonic() < deadline:
        time.sleep(1)
    record.update(
        ok=(status == 200 and not exited_early and port_free()),
        http_status=status, ready_after_s=ready_s, exited_early=exited_early,
        port_free_after_stop=port_free(), output_tail=output[-800:],
        served_on_expected_port=(f"localhost:{PORT}" in output or f"127.0.0.1:{PORT}" in output),
    )
    if record["ok"] and not record["served_on_expected_port"]:
        record["ok"] = False
        record["error"] = "dev server output does not show the expected port"
    return record


# --------------------------------------------------------------------------- checkout + install


def fetch(repo: str, sha: str, dest: Path) -> dict[str, Any]:
    url = f"https://github.com/{repo}.git"
    started = time.monotonic()
    steps = (
        ["init", "--quiet", str(dest)],
        ["remote", "add", "origin", url],
        ["fetch", "--quiet", "--depth", "1", "--filter=blob:none", "origin", sha],
        ["checkout", "--quiet", "FETCH_HEAD"],
    )
    for index, args in enumerate(steps):
        result = git(args, cwd=dest if index else dest.parent, timeout=FETCH_TIMEOUT_S)
        if result.returncode != 0:
            return {"ok": False, "error": f"git {args[0]} failed: {result.stderr.strip()[:300]}"}
    head = git(["rev-parse", "HEAD"], cwd=dest).stdout.strip()
    return {"ok": head == sha, "head": head, "expected": sha, "elapsed_s": round(time.monotonic() - started, 1),
            "error": None if head == sha else "checked-out HEAD does not match pinned SHA"}


def install(target: dict[str, Any], workspace: Path, env: dict[str, str]) -> dict[str, Any]:
    commands = [shlex.split(part) for part in target["install_command"].split(" && ")]
    runs = []
    for command in commands:
        record = run_bounded(command, workspace, env, INSTALL_TIMEOUT_S)
        runs.append(summarize(record, 600))
        if record.get("returncode") != 0:
            return {"ok": False, "runs": runs, "error": f"install step failed: {' '.join(command)}"}
    return {"ok": True, "runs": runs}


def tracked_state(workspace: Path) -> dict[str, Any]:
    porcelain = git(["status", "--porcelain=v1", "-uall"], cwd=workspace).stdout
    diff = git(["diff", "HEAD", "--binary"], cwd=workspace).stdout
    return {
        "porcelain": porcelain.splitlines(),
        "tracked_diff_sha256": sha256_bytes(diff.encode()),
        "tracked_diff_bytes": len(diff.encode()),
        "modified_tracked": [line[3:] for line in porcelain.splitlines() if line[:2].strip() not in {"??", ""}],
        "untracked": [line[3:] for line in porcelain.splitlines() if line.startswith("??")],
    }


TEST_DIR = "e2e/"  # both targets: playwright.config.ts testDir './e2e'
RUNTIME_ARTIFACT_PREFIXES = ("test-results/", "playwright-report/", ".playwright-cli/")
CONTROL_FILE_MARKERS = (".claude/", ".codex/", ".agents/", ".mcp.json", "AGENTS.md", "CLAUDE.md")
SPEC_FILE_RE = re.compile(r"\.(spec|test)\.[cm]?[jt]sx?$")


def numstat(workspace: Path) -> dict[str, tuple[int | None, int | None]]:
    out = {}
    for line in git(["diff", "--numstat", "HEAD"], cwd=workspace).stdout.splitlines():
        parts = line.split("\t")
        if len(parts) == 3:
            added, deleted, path = parts
            out[path] = (None if added == "-" else int(added), None if deleted == "-" else int(deleted))
    return out


def classify_changes(workspace: Path, arm: str, pre_untracked: set[str], harness_patched: set[str],
                     init_digests: dict[str, str] | None) -> dict[str, Any]:
    """protocol.json schedule.candidate_completion_surface, applied literally and fail-closed.
    Every post-session change lands in exactly one bucket; anything in `drift` fails the cell."""
    post = tracked_state(workspace)
    stats = numstat(workspace)
    buckets: dict[str, list[Any]] = {
        "candidate_spec": [], "new_test_dir_files": [], "planner_specs_output": [], "runtime_artifacts": [],
        "additive_test_dir_edits": [], "harness_patched": [], "drift": [],
    }
    for line in post["porcelain"]:
        code, path = line[:2], line[3:]
        if code == "??":
            if path in pre_untracked:
                continue  # init-agents setup files, hashed separately below
            if path == CANDIDATE_RELATIVE:
                buckets["candidate_spec"].append(path)
            elif path.startswith(RUNTIME_ARTIFACT_PREFIXES):
                buckets["runtime_artifacts"].append(path)
            elif any(marker in path for marker in CONTROL_FILE_MARKERS):
                buckets["drift"].append({"path": path, "reason": "new control file"})
            elif arm == "planner_plus_ours" and path.startswith("specs/") and path.endswith(".md"):
                buckets["planner_specs_output"].append(path)
            elif path.startswith(TEST_DIR) and SPEC_FILE_RE.search(path):
                buckets["drift"].append({"path": path, "reason": "extra spec file under testDir (temporary verifier leftover or undeclared scenario)"})
            elif path.startswith(TEST_DIR):
                buckets["new_test_dir_files"].append(path)
            else:
                buckets["drift"].append({"path": path, "reason": "new file outside testDir/specs"})
            continue
        if "D" in code or "R" in code or "C" in code:
            buckets["drift"].append({"path": path, "reason": f"tracked file deleted/renamed (status {code!r})"})
            continue
        # modified tracked file
        if path in harness_patched:
            buckets["harness_patched"].append(path)
        elif any(marker in path for marker in CONTROL_FILE_MARKERS):
            buckets["drift"].append({"path": path, "reason": "control file modified"})
        elif path.startswith(TEST_DIR) and SPEC_FILE_RE.search(path):
            buckets["drift"].append({"path": path, "reason": "existing spec file modified"})
        elif path.startswith(TEST_DIR):
            added, deleted = stats.get(path, (None, None))
            if deleted == 0:
                buckets["additive_test_dir_edits"].append({"path": path, "lines_added": added})
            else:
                buckets["drift"].append({"path": path, "reason": f"non-additive edit of existing test-dir file (deleted={deleted})"})
        else:
            buckets["drift"].append({"path": path, "reason": "tracked file outside testDir modified"})
    if init_digests:
        after = hash_files(workspace, list(init_digests))
        for path, digest in after.items():
            if digest != init_digests[path]:
                buckets["drift"].append({"path": path, "reason": "init-agents control file digest changed"})
    return {"rule": "protocol.json schedule.candidate_completion_surface", "buckets": buckets,
            "tracked_diff_sha256": post["tracked_diff_sha256"], "porcelain": post["porcelain"],
            "within_surface": not buckets["drift"]}


def hash_files(workspace: Path, relatives: list[str]) -> dict[str, str]:
    digests = {}
    for relative in relatives:
        path = workspace / relative
        digests[relative] = sha256_file(path) if path.is_file() else "<missing>"
    return digests


# --------------------------------------------------------------------------- planner arm setup


def init_agents(target: dict[str, Any], workspace: Path, env: dict[str, str]) -> dict[str, Any]:
    exec_prefix = ["pnpm", "exec"] if target["package_manager"] == "pnpm" else ["npx", "--no-install"]
    help_run = run_bounded([*exec_prefix, "playwright", "help", "init-agents"], workspace, env, 120)
    if help_run.get("returncode") != 0 or "init-agents" not in help_run["stdout"]:
        return {"ok": False, "status": "UNAVAILABLE", "error": "playwright help init-agents not exposed",
                "help": summarize(help_run, 400)}
    run = run_bounded([*exec_prefix, "playwright", "init-agents", "--loop=claude"], workspace, env,
                      INIT_AGENTS_TIMEOUT_S)
    state = tracked_state(workspace)
    created = state["untracked"]
    digests = hash_files(workspace, created)
    agents: dict[str, Any] = {}
    for path in sorted((workspace / ".claude/agents").glob("*.md")) if (workspace / ".claude/agents").is_dir() else []:
        text = path.read_text(encoding="utf-8")
        match = re.match(r"^---\n(.*?)\n---\n(.*)$", text, re.S)
        if not match:
            continue
        front: dict[str, str] = {}
        for line in match.group(1).splitlines():
            key, _, value = line.partition(":")
            front[key.strip()] = value.strip()
        definition = {"description": front.get("description", "").strip("'\""), "prompt": match.group(2).strip()}
        if front.get("tools"):
            definition["tools"] = [tool.strip() for tool in front["tools"].split(",") if tool.strip()]
        if front.get("model"):
            definition["model"] = front["model"]
        agents[front.get("name", path.stem)] = definition
    planner_tools = set(agents.get("playwright-test-planner", {}).get("tools", []))
    has_planner_tools = {"mcp__playwright-test__planner_setup_page", "mcp__playwright-test__planner_save_plan"} <= planner_tools
    mcp_config = workspace / ".mcp.json"
    ok = run.get("returncode") == 0 and mcp_config.is_file() and "playwright-test-planner" in agents and has_planner_tools
    return {
        "ok": ok, "status": "READY" if ok else "UNAVAILABLE",
        "run": summarize(run, 800),
        "created_files": created, "control_file_sha256": digests,
        "agents_passed_via_flag": sorted(agents), "planner_agent_declares_setup_and_save_tools": has_planner_tools,
        "mcp_config": str(mcp_config) if mcp_config.is_file() else None,
        "agents_json": agents if ok else None,
        "modified_tracked_by_init": state["modified_tracked"],
    }


# --------------------------------------------------------------------------- session


def stage_skills(runner_home: Path) -> dict[str, str]:
    destination = runner_home / ".claude/skills"
    destination.mkdir(parents=True)
    for name in STAGED_SKILLS:
        shutil.copytree(SKILLS_DIR / name, destination / name, symlinks=False)
    digests = {}
    for relative in ("playwright-test-generator/SKILL.md", "playwright-test-generator/playwright-agents.md",
                     "e2e-reviewer/SKILL.md", "e2e-reviewer/references/pattern-reference.md"):
        digests[f"skills/{relative}"] = sha256_file(destination / relative)
    (runner_home / "tmp").mkdir()
    return digests


def render_prompt(target: dict[str, Any], arm: str, cell_id: str, init: dict[str, Any] | None) -> str:
    pm = target["package_manager"]
    test_cmd = target["native_test_command"]
    dev_cmd = target["dev_server"]["command"]
    base_url = target["dev_server"]["base_url"]
    planner_section = ""
    if arm == "planner_plus_ours" and not (init and init.get("ok")):
        reason = (init or {}).get("error") or (init or {}).get("status") or "harness could not initialize the planner"
        planner_section = f"""
ARM-SPECIFIC STEP (planner_plus_ours): the harness attempted
`playwright init-agents --loop=claude` in this checkout and it was NOT usable
({reason}). Per protocol this is UNAVAILABLE, never an application failure and
never a reason to upgrade or patch the target. Write `{PLANNER_DELTA_RELATIVE}`
containing the single line `PLANNER_UNAVAILABLE: {reason}`, set planner_status to
"UNAVAILABLE" in your final JSON, and complete the normal pipeline.
"""
    elif arm == "planner_plus_ours":
        control_files = "\n".join(f"  - {path}  sha256={digest}" for path, digest in sorted(init["control_file_sha256"].items()))
        planner_section = f"""
ARM-SPECIFIC STEP (planner_plus_ours) — run this between Step 4 and Step 5, per
`playwright-agents.md` section "Recommended auxiliary mode: harden the plan":
- The harness already ran `{'pnpm exec' if pm == 'pnpm' else 'npx --no-install'} playwright init-agents --loop=claude`
  in this checkout (setup cost, unscored). These control files exist and are hashed;
  NEVER edit them:
{control_files}
- The `playwright-test-planner` subagent from those files is registered for this
  session (delegate with the Agent/Task tool, subagent_type "playwright-test-planner").
  Its MCP server `playwright-test` is configured. Apply the admission gate: the
  delegated planner must confirm it can see BOTH `planner_setup_page` and
  `planner_save_plan` and that its browser launches. If it cannot, write
  `{PLANNER_DELTA_RELATIVE}` containing the single line `PLANNER_UNAVAILABLE: <reason>`,
  set planner_status to "UNAVAILABLE", and continue with the normal pipeline —
  never upgrade or patch the target to make the planner available.
- Ask the planner to PRESERVE the frozen scenario scope (exactly one scenario,
  the smoke scenario below, route `/`) and return plan deltas only, saved with
  `planner_save_plan` under `specs/`. The app must be reachable at {base_url}
  before you delegate: start it with the approved `{dev_cmd}` in the background
  and stop it again before Step 7.
- Reconcile per playwright-agents.md steps 2-4 and write the ledger to
  `{PLANNER_DELTA_RELATIVE}`: every delta classified as `observed` (resolved on the
  live page by the planner), `inference` (source/seed only), `verification
  condition`, or `limitation`; which were absorbed; and every scenario-changing
  delta listed as RETURNED_TO_APPROVAL_GATE (not applied — there is no human to
  approve it). Inferred locators must not reach the final test.
- Then implement the hardened plan yourself (Step 5 onward). Do NOT invoke the
  first-party generator or healer agents.
"""
    return f"""You are running one unscored SMOKE cell ({cell_id}) of a preregistered
benchmark harness. There is NO human in this session: every question the
`playwright-test-generator` skill would normally ask the user is answered by this
brief. If a decision genuinely outside this brief is needed, stop and report
BLOCKED with the exact question instead of guessing.

Invoke the `playwright-test-generator` skill with the Skill tool and follow it end
to end (Step 1 -> Step 3 -> Step 4 -> Step 5 -> Step 6 -> Step 7). It is installed at
$HOME/.claude/skills/playwright-test-generator (that directory is SKILL_ROOT). The
`e2e-reviewer` skill is installed alongside it for Step 6. Step 2 (coverage-gap
analysis) is skipped because the target is given below ($ARGUMENT).

TARGET (already approved as a trusted, local/disposable stack; loopback fixture,
ALLOW_LOOPBACK=1): this repository checkout, {target['repository']} at
{target['pinned_sha'][:12]}, served at {base_url}. Dependencies are installed and
Chromium is installed (PLAYWRIGHT_BROWSERS_PATH is set). Route under test: `/`.
Do not follow off-origin links; no network beyond {base_url} is permitted.

APPROVED SCENARIO (frozen; exactly one; do not add, split, or reword it):
## Scenario 1: Application shell loads with primary navigation
- Given: the application is served at {base_url}
- When: a user opens `/`
- Then: {SMOKE_SCENARIO}
Fill in the scenario admission block and the V1-V6 verification contract from
your own live-browser observations (V4: N/A, read-only). Choose the primary
navigation locator from what you OBSERVE in the browser, not from source alone.

APPROVED TARGET-CONTROLLED COMMANDS (exact strings; nothing else may run from
the target's package scripts):
| Exact command | Purpose |
| `{dev_cmd}` | serve the app for Step 3 exploration (run in background; stop it before Step 7 unless the config reuses it) |
| `{test_cmd}` | Step 7 native run of the candidate |
Host tools that are NOT target-controlled and may be used freely: the standalone
`playwright-cli` on PATH (preferred Step 3 source), `agent-browser` on PATH,
`{pm}` for the approved scripts only. Never install packages, never let npx
download anything, never edit package.json, playwright.config.*, or lockfiles.

CONTROL-FILE MUTATIONS: skip all (no AGENTS.md / CLAUDE.md changes; Step 5b is skipped).

OUTPUT CONTRACT:
- Write the candidate spec at exactly `{CANDIDATE_RELATIVE}` (testDir is ./e2e).
  Match the repository's existing spec style; if the project already has a POM
  directory you may add one page object there, otherwise keep the spec flat.
  Create no other files outside e2e/, specs/, test-results/, playwright-report/.
- The e2e-reviewer gate (zero P0) and V1-V6 apply as written in the skill; report
  CANNOT_VERIFY honestly where a rule cannot be satisfied in this session.
- Stop every background process you started before finishing.
- End your final message with the skill's completion (or PARTIAL/BLOCKED) report
  followed by exactly one fenced ```json block:
  {{"cell": "{cell_id}", "arm": "{arm}", "outcome": "<Complete|PARTIAL/BLOCKED|CANNOT_COMPLETE/BLOCKED|UNAVAILABLE>",
   "candidate_files": ["<paths you created>"], "browser_source": "<playwright-cli|agent-browser|mcp|aria-fallback|none>",
   "planner_status": "<N/A|READY|UNAVAILABLE>", "native_run_command": "<exact command>",
   "native_run_passed": <true|false>, "verification": {{"V1": "..", "V2": "..", "V3": "..", "V4": "..", "V5": "..", "V6": ".."}}}}
{planner_section}"""


def session_command(claude: str, arm: str, workspace: Path, init: dict[str, Any] | None) -> list[str]:
    command = [
        claude, "-p",
        "--output-format", "json",
        "--setting-sources", "user",
        "--strict-mcp-config",
        "--dangerously-skip-permissions",
        "--model", MODEL,
        "--max-turns", str(SESSION_MAX_TURNS),
        "--max-budget-usd", SESSION_MAX_BUDGET_USD,
    ]
    if arm == "planner_plus_ours" and init and init.get("ok"):
        command += ["--mcp-config", init["mcp_config"], "--agents", json.dumps(init["agents_json"])]
    return command


def redact(text: str, credentials: dict[str, str]) -> tuple[str, bool, bool]:
    """Transcript redaction using the SAME credential patterns as eval_security."""
    detected = False
    for value in credentials.values():
        if len(value) >= 8 and value in text:
            text = text.replace(value, eval_security.REDACTION)
            detected = True
    for pattern in eval_security._CREDENTIAL_PATTERNS:
        text, count = pattern.subn(eval_security.REDACTION, text)
        detected = detected or count > 0
    residual = any(pattern.search(text) for pattern in eval_security._CREDENTIAL_PATTERNS)
    return text, detected, residual


def persist_transcript(runner_home: Path, artifacts: Path, credentials: dict[str, str]) -> dict[str, Any]:
    projects = runner_home / ".claude/projects"
    files = [p for p in projects.rglob("*.jsonl") if "memory" not in p.parts] if projects.is_dir() else []
    if not files:
        return {"path": None, "error": "no session transcript found in runner home"}
    files.sort(key=lambda p: p.stat().st_size, reverse=True)
    raw = files[0].read_text(encoding="utf-8", errors="replace")
    text, detected, residual = redact(raw, credentials)
    if residual:
        return {"path": None, "withheld": True, "reason": "credential-shaped content could not be fully redacted",
                "raw_sha256": sha256_bytes(raw.encode()), "raw_bytes": len(raw.encode())}
    destination = artifacts / "transcript.jsonl"
    destination.write_text(text, encoding="utf-8")
    return {"path": str(destination.relative_to(ROOT)), "bytes": len(text.encode()),
            "sha256": sha256_file(destination), "raw_sha256": sha256_bytes(raw.encode()),
            "redactions_applied": detected, "lines": text.count("\n")}


def parse_session_result(stdout: str) -> dict[str, Any]:
    try:
        payload = json.loads(stdout.strip())
    except json.JSONDecodeError:
        return {"parsed": False}
    if not isinstance(payload, dict):
        return {"parsed": False}
    text = payload.get("result") if isinstance(payload.get("result"), str) else ""
    block = None
    for match in re.finditer(r"```json\s*\n(.*?)\n\s*```", text, re.S):
        try:
            block = json.loads(match.group(1))
        except json.JSONDecodeError:
            continue
    return {
        "parsed": True,
        "subtype": payload.get("subtype"), "is_error": payload.get("is_error"),
        "num_turns": payload.get("num_turns"), "duration_ms": payload.get("duration_ms"),
        "duration_api_ms": payload.get("duration_api_ms"),
        "total_cost_usd_reported": payload.get("total_cost_usd"),
        "usage": payload.get("usage"), "model_usage": payload.get("modelUsage"),
        "session_id": payload.get("session_id"),
        "final_text_sha256": sha256_bytes(text.encode()), "final_text_bytes": len(text.encode()),
        "self_report": block,
    }


# --------------------------------------------------------------------------- cell


def run_cell(cell: dict[str, Any], target: dict[str, Any], context: dict[str, Any]) -> None:
    cell_id, arm = cell["cell_id"], cell["arm"]
    artifacts = ARTIFACTS_DIR / cell_id
    artifacts.mkdir(parents=True, exist_ok=True)
    cell["artifacts_dir"] = str(artifacts.relative_to(ROOT))
    cell["started_at"] = utc_now()
    cell_start = time.monotonic()
    attempts: list[dict[str, Any]] = []
    cell["setup_attempts"] = attempts

    for attempt in range(1, SETUP_RETRIES + 2):
        steps: dict[str, Any] = {"attempt": attempt}
        attempts.append(steps)
        runner_home = Path(tempfile.mkdtemp(prefix=f"ovp-smoke-home-{cell_id}-"))
        runner_home.chmod(0o700)
        workspace_parent = Path(tempfile.mkdtemp(prefix=f"ovp-smoke-ws-{cell_id}-"))
        workspace = workspace_parent / target["repository"].split("/")[1]
        steps["runner_home"] = str(runner_home)
        steps["workspace"] = str(workspace)
        model_call_made = False
        try:
            if not port_free():
                steps["port"] = {"ok": False, "listeners": port_listeners()}
                raise RuntimeError(f"port {PORT} busy before cell start (foreign listener not killed)")
            steps["skill_snapshot"] = stage_skills(runner_home)
            tool_env = build_env(runner_home, context["node_bin"], context["cache"])

            log(f"{cell_id}: fetch {target['repository']}@{target['pinned_sha'][:10]} (attempt {attempt})")
            steps["fetch"] = fetch(target["repository"], target["pinned_sha"], workspace)
            if not steps["fetch"]["ok"]:
                raise RuntimeError(f"fetch: {steps['fetch']['error']}")

            steps["port_substitution"] = patch_ports(workspace)
            if not steps["port_substitution"]["ok"]:
                raise RuntimeError(f"port substitution: {steps['port_substitution']}")
            target = {**target, "dev_server": {**target["dev_server"], "base_url": f"http://localhost:{PORT}"}}
            steps["port_substitution"]["effective_base_url"] = target["dev_server"]["base_url"]
            # The patched config files are tracked, so they are the ONLY expected tracked modification.
            expected_modified = {t["file"] for t in steps["port_substitution"]["files"] if t["status"] == "patched"}

            log(f"{cell_id}: install")
            steps["install"] = install(target, workspace, tool_env)
            if not steps["install"]["ok"]:
                raise RuntimeError(f"install: {steps['install']['error']}")

            log(f"{cell_id}: dev server check")
            steps["dev_server"] = dev_server_check(target, workspace, tool_env)
            if not steps["dev_server"]["ok"]:
                raise RuntimeError(f"dev server: {steps['dev_server'].get('error') or steps['dev_server']}")

            init = None
            if arm == "planner_plus_ours":
                log(f"{cell_id}: init-agents --loop=claude")
                init = init_agents(target, workspace, tool_env)
                steps["init_agents"] = {k: v for k, v in init.items() if k != "agents_json"}
                if not init["ok"]:
                    # UNAVAILABLE is a recorded outcome, never a setup retry (protocol arms[].unavailable_rule).
                    cell["planner_availability"] = "UNAVAILABLE"
                else:
                    cell["planner_availability"] = "READY"

            steps["pre_session_state"] = tracked_state(workspace)
            allowed_pre_untracked = set(steps["pre_session_state"]["untracked"])

            prompt = render_prompt(target, arm, cell_id, init)
            (artifacts / "prompt.md").write_text(prompt, encoding="utf-8")
            steps["prompt_sha256"] = sha256_bytes(prompt.encode())
            command = session_command(context["claude"], arm, workspace, init)
            steps["session_command"] = [c if not c.startswith("{") else "<agents-json>" for c in command]
            session_env = build_env(runner_home, context["node_bin"], context["cache"], claude=True,
                                    credentials=context["credentials"], extra={"PWD": str(workspace)})

            log(f"{cell_id}: launching disposable Claude Code session (timeout {SESSION_TIMEOUT_S[arm]}s)")
            model_call_made = True
            context["report"]["model_calls_made"] += 1
            write_results(context["report"])
            session = run_bounded(command, workspace, session_env, SESSION_TIMEOUT_S[arm], stdin_text=prompt)
            session["command"] = steps["session_command"]
            sanitized_stdout, credential_detected = sanitize_model_output(session["stdout"], context["credentials"])
            parsed = parse_session_result(session["stdout"])
            steps["session"] = {
                **{k: v for k, v in summarize(session, 0).items() if not k.endswith("_tail")},
                "credential_shaped_output_detected": credential_detected,
                "result": parsed,
            }
            (artifacts / "session-result.json").write_text(sanitized_stdout + "\n", encoding="utf-8")
            if session["stderr"]:
                stderr_text, _, residual = redact(session["stderr"], context["credentials"])
                if not residual:
                    (artifacts / "session-stderr.txt").write_text(stderr_text, encoding="utf-8")
            log(f"{cell_id}: session exit={session.get('returncode')} timed_out={session.get('timed_out')} "
                f"turns={parsed.get('num_turns')} cost={parsed.get('total_cost_usd_reported')} "
                f"elapsed={session['elapsed_s']}s")

            steps["post_session_port_sweep"] = sweep_port(workspace)
            steps["transcript"] = persist_transcript(runner_home, artifacts, context["credentials"])

            surface = classify_changes(
                workspace, arm, allowed_pre_untracked, expected_modified,
                init["control_file_sha256"] if init and init.get("ok") else None,
            )
            steps["post_session_state"] = {**surface, "expected_modified_by_harness": sorted(expected_modified)}
            new_untracked = [p for p in surface["porcelain"] if p.startswith("??") and p[3:] not in allowed_pre_untracked]
            new_untracked = [p[3:] for p in new_untracked]
            candidate = workspace / CANDIDATE_RELATIVE
            candidates = [p for p in new_untracked if SPEC_FILE_RE.search(p) and not p.endswith("seed.spec.ts")]
            steps["candidate"] = {"expected_path": CANDIDATE_RELATIVE, "exists": candidate.is_file(),
                                  "spec_files_created": candidates}
            for relative in candidates:
                source = workspace / relative
                if source.is_file():
                    destination = artifacts / "candidate" / relative
                    destination.parent.mkdir(parents=True, exist_ok=True)
                    shutil.copy2(source, destination)
            if candidate.is_file():
                steps["candidate"]["sha256"] = sha256_file(candidate)
            delta = workspace / PLANNER_DELTA_RELATIVE
            if arm == "planner_plus_ours":
                steps["planner_delta"] = {"exists": delta.is_file()}
                if delta.is_file():
                    shutil.copy2(delta, artifacts / "smoke-planner-delta.md")
                    steps["planner_delta"]["sha256"] = sha256_file(delta)
                    steps["planner_delta"]["unavailable_marker"] = delta.read_text(encoding="utf-8").startswith("PLANNER_UNAVAILABLE")
                specs_dir = workspace / "specs"
                if specs_dir.is_dir():
                    for plan in specs_dir.glob("*.md"):
                        if plan.name != "README.md":
                            shutil.copy2(plan, artifacts / f"specs__{plan.name}")

            if candidate.is_file():
                if not port_free():
                    steps["native_run"] = {"ok": False, "error": "port busy before native run", "listeners": port_listeners()}
                else:
                    log(f"{cell_id}: harness-side native run of {CANDIDATE_RELATIVE}")
                    native_env = build_env(runner_home, context["node_bin"], context["cache"],
                                           extra=target.get("native_run_env") or {})
                    native = run_bounded(shlex.split(target["native_test_command"]), workspace, native_env,
                                         NATIVE_RUN_TIMEOUT_S)
                    passed = native.get("returncode") == 0 and re.search(r"\b[1-9]\d* passed\b", native["stdout"]) is not None
                    steps["native_run"] = {**summarize(native, 2000), "ok": passed,
                                           "env_overrides": target.get("native_run_env") or {}}
                    (artifacts / "native-run.txt").write_text(native["stdout"] + "\n--- stderr ---\n" + native["stderr"], encoding="utf-8")
                    steps["post_native_port_sweep"] = sweep_port(workspace)
            else:
                steps["native_run"] = {"ok": False, "error": "no candidate spec at expected path"}

            reasons = []
            if session.get("timed_out"):
                reasons.append("session timed out")
            if session.get("returncode") != 0:
                reasons.append(f"session exit {session.get('returncode')}")
            if credential_detected:
                reasons.append("credential-shaped session output")
            if not candidate.is_file():
                reasons.append("no candidate spec")
            if not steps["native_run"].get("ok"):
                reasons.append("native run did not pass")
            if not surface["within_surface"]:
                reasons.append("source-tree drift outside candidate_completion_surface: "
                               + "; ".join(f"{d['path']} ({d['reason']})" for d in surface["buckets"]["drift"]))
            if steps["post_session_port_sweep"]["killed_workspace_listeners"]:
                reasons.append("session left a dev server running (killed by harness)")
            if steps["transcript"].get("path") is None:
                reasons.append("transcript missing or withheld")
            cell["status"] = "PASS" if not reasons else "FAIL"
            cell["fail_reasons"] = reasons
            break
        except Exception as exc:  # noqa: BLE001 - recorded as evidence
            steps["error"] = f"{type(exc).__name__}: {exc}"
            log(f"{cell_id}: attempt {attempt} error: {steps['error']}")
            if model_call_made:
                cell["status"] = "FAIL"
                cell["fail_reasons"] = [steps["error"]]
                break
            if attempt > SETUP_RETRIES:
                cell["status"] = "SETUP_FAILED"
                cell["fail_reasons"] = [steps["error"]]
        finally:
            cleanup: dict[str, Any] = {"port_sweep": sweep_port(workspace)}
            marker = runner_home / "short-tmpdir"
            short_tmp = Path(marker.read_text(encoding="utf-8").strip()) if marker.is_file() else None
            targets_to_remove = [("workspace", workspace_parent), ("runner_home", runner_home)]
            if short_tmp is not None and short_tmp.name.startswith("ovp-") and short_tmp.parent == Path("/tmp"):
                targets_to_remove.append(("short_tmpdir", short_tmp))
            for label, path in targets_to_remove:
                shutil.rmtree(path, ignore_errors=True)
                cleanup[label] = "removed" if not path.exists() else "REMAINS"
            steps["cleanup"] = cleanup
            cell["finished_at"] = utc_now()
            cell["wall_time_s"] = round(time.monotonic() - cell_start, 1)
            write_results(context["report"])


# --------------------------------------------------------------------------- main


MODEL = "claude-opus-5"


def assess_under_corrected_rule(cell: dict[str, Any]) -> dict[str, Any]:
    """Re-read a record produced under the pre-correction drift rule ('any drift outside the
    generated spec path') and say what schedule.candidate_completion_surface would conclude.
    Returns verdict PASS / FAIL / UNDETERMINED; UNDETERMINED means the old record lacks the
    evidence the corrected rule needs (numstat additivity), so the cell must be rerun."""
    if cell.get("status") not in {"PASS", "FAIL"}:
        return {"verdict": cell.get("status"), "reason": "no session record to reassess"}
    attempt = cell["setup_attempts"][-1]
    post = attempt.get("post_session_state") or {}
    if "buckets" in post:
        return {"verdict": cell["status"], "reason": "record already produced under the corrected rule"}
    other = [r for r in cell.get("fail_reasons", []) if r not in {"tracked files modified", "unexpected untracked files", "init-agents control files edited"}]
    harness = set(post.get("expected_modified_by_harness", []))
    drift, undetermined = [], []
    for path in post.get("modified_tracked", []):
        if path in harness:
            continue
        if any(m in path for m in CONTROL_FILE_MARKERS) or not path.startswith(TEST_DIR) or SPEC_FILE_RE.search(path):
            drift.append(path)
        else:
            undetermined.append(path)  # additive-only cannot be checked from the old record
    for path in post.get("new_untracked", []):
        if path == CANDIDATE_RELATIVE or path.startswith(RUNTIME_ARTIFACT_PREFIXES):
            continue
        if any(m in path for m in CONTROL_FILE_MARKERS):
            drift.append(path)
        elif cell["arm"] == "planner_plus_ours" and path.startswith("specs/") and path.endswith(".md"):
            continue
        elif path.startswith(TEST_DIR) and SPEC_FILE_RE.search(path):
            drift.append(path)
        elif not path.startswith(TEST_DIR):
            drift.append(path)
    if post.get("init_control_file_drift"):
        drift.extend(post["init_control_file_drift"])
    if other:
        verdict = "FAIL"
    elif drift:
        verdict = "FAIL"
    elif undetermined:
        verdict = "UNDETERMINED"
    else:
        verdict = "PASS"
    return {"verdict": verdict, "drift_under_corrected_rule": drift, "needs_numstat_check": undetermined,
            "non_drift_fail_reasons": other, "old_status": cell["status"], "old_fail_reasons": cell.get("fail_reasons", [])}


def cli_version(executable: str) -> str:
    result = subprocess.run([executable, "--version"], capture_output=True, text=True, check=False, timeout=30,
                            env={"PATH": REVIEWER.trusted_runner_search_path(), "HOME": pwd.getpwuid(os.getuid()).pw_dir})
    return result.stdout.strip().splitlines()[0] if result.stdout.strip() else f"<exit {result.returncode}>"


def version_tuple(text: str) -> tuple[int, ...]:
    match = re.search(r"(\d+)\.(\d+)\.(\d+)", text)
    return tuple(int(g) for g in match.groups()) if match else ()


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--cache-dir", type=Path, default=None,
                        help="content-addressed caches (npm, pnpm store, corepack, Playwright browsers); "
                             "a caller-provided directory is kept, a temporary one is deleted at exit")
    parser.add_argument("--cells", default="A:ours_only,A:planner_plus_ours,B:ours_only,B:planner_plus_ours")
    parser.add_argument("--rerun", action="store_true",
                        help="merge into the existing smoke-results.json: rerun only --cells, keep every other cell's "
                             "record, keep the superseded record of each rerun cell under superseded_runs")
    parser.add_argument("--rerun-reason", default="verdict under the corrected drift rule (protocol.json corrections[0]) "
                        "differs from or is undetermined by the record produced under the old rule",
                        help="recorded verbatim in reruns[] so every rerun carries its proven cause")
    parser.add_argument("--assess-only", action="store_true",
                        help="no run: annotate every cell in smoke-results.json with its verdict under the corrected "
                             "drift rule (assess_under_corrected_rule) and exit")
    args = parser.parse_args()

    if args.assess_only:
        report = json.loads(RESULTS_PATH.read_text(encoding="utf-8"))
        for cell in report["cells"]:
            cell["corrected_rule_assessment"] = assess_under_corrected_rule(cell)
            print(f"{cell['cell_id']}: old={cell['status']} corrected={cell['corrected_rule_assessment']['verdict']}")
        report["assessed_at"] = utc_now()
        write_results(report)
        return 0

    protocol = json.loads(PROTOCOL_PATH.read_text(encoding="utf-8"))
    protocol_sha = sha256_file(PROTOCOL_PATH)
    if (PILOT_DIR / "freeze-record.json").exists():
        raise SystemExit("freeze-record.json exists; the smoke stage must not run against a frozen protocol from this script")
    targets: dict[str, dict[str, Any]] = {}
    for entry in protocol["targets"]:
        pm = "pnpm" if entry["install_command"].startswith("pnpm") else "npm"
        exec_prefix = "pnpm exec" if pm == "pnpm" else "npx --no-install"
        targets[entry["target_id"]] = {
            **entry, "package_manager": pm,
            "native_test_command": f"{exec_prefix} playwright test {CANDIDATE_RELATIVE} --project=chromium --retries=0 --reporter=list",
            # Target A's config is headed + reuseExistingServer unless CI is set; CI=1 makes the
            # harness-side run headless with reuseExistingServer=false (protocol: must be false).
            # Target B's config switches baseURL/command under CI, so it must NOT get CI.
            "native_run_env": {"CI": "1"} if entry["target_id"] == "A" else {},
        }
    for target in targets.values():
        assert target["dev_server"]["base_url"] == f"http://localhost:{UPSTREAM_PORT}"
    port_selection = select_port()  # sets the module-level PORT used by every helper below

    caller_cache = args.cache_dir is not None
    cache_root = args.cache_dir.expanduser().resolve() if caller_cache else Path(tempfile.mkdtemp(prefix="ovp-smoke-cache-"))
    cache = {name: cache_root / sub for name, sub in
             (("npm", "npm-cache"), ("pnpm", "pnpm-store"), ("corepack", "corepack"), ("browsers", "pw-browsers"))}
    for path in cache.values():
        path.mkdir(parents=True, exist_ok=True)

    node_bin = select_node_bin()
    claude = REVIEWER.resolve_runner_executable("claude")
    claude_version = cli_version(claude)
    minimum = protocol["execution_identity"]["hosts"][0]["minimum_version"]
    host_settings = Path(pwd.getpwuid(os.getuid()).pw_dir) / ".claude/settings.json"
    settings_digest = sha256_file(host_settings) if host_settings.is_file() else None
    credentials = REVIEWER.claude_runner_credentials()

    schedule = []
    for index, token in enumerate(args.cells.split(","), start=1):
        target_id, arm = token.split(":")
        if arm not in ARMS or target_id not in targets:
            raise SystemExit(f"bad cell token: {token}")
        schedule.append({"cell_id": f"smoke-{target_id}-{arm}", "order": index, "target_id": target_id,
                         "repository": targets[target_id]["repository"], "pinned_sha": targets[target_id]["pinned_sha"],
                         "arm": arm, "status": "NOT_RUN"})

    report: dict[str, Any] = {
        "schema_version": 1,
        "spdx_license_identifier": "Apache-2.0",
        "protocol_id": protocol["protocol_id"],
        "protocol_sha256": protocol_sha,
        "stage": "smoke_cells",
        "scored": False,
        "excluded_from_every_denominator": True,
        "smoke_scenario": SMOKE_SCENARIO,
        "frozen_scenarios_touched": False,
        "freeze_record_written": False,
        "started_at": utc_now(),
        "finished_at": None,
        "host": {
            "platform": platform.platform(),
            "claude_executable": claude,
            "claude_version": claude_version,
            "protocol_minimum_version": minimum,
            "claude_version_meets_minimum": version_tuple(claude_version) >= version_tuple(minimum),
            "model": MODEL,
            "node_bin": str(node_bin),
            "node_version": cli_version(str(node_bin / "node")),
            "port_substitution": {
                **port_selection,
                "upstream_port": UPSTREAM_PORT,
                "operator_decision": "do not touch this machine's Tailscale networking (a tailscale serve route holds "
                                     "5173 on the tailnet address); patch each disposable checkout's playwright.config.ts "
                                     "and vite.config.ts to the chosen port instead; 5174 requested, first free port >= 5174 used",
                "patched_files_per_checkout": list(PATCHED_CONFIG_FILES),
            },
            "host_settings_sha256_before": settings_digest,
            "host_settings_sha256_after": None,
            "session_flags": ["-p", "--output-format json", "--setting-sources user (runner-home only)",
                              "--strict-mcp-config", "--dangerously-skip-permissions", f"--model {MODEL}",
                              f"--max-turns {SESSION_MAX_TURNS}", f"--max-budget-usd {SESSION_MAX_BUDGET_USD}",
                              "planner arm: --mcp-config <workspace>/.mcp.json --agents <init-agents definitions>"],
            "session_timeouts_s": SESSION_TIMEOUT_S,
            "isolation": "fresh runner HOME per cell (skills staged from ./skills), fresh blobless checkout per cell, "
                         "REVIEWER.clean_env allowlist + Node 24 bin fronted, single OAuth token from keychain via "
                         "REVIEWER.claude_runner_credentials, output capped by REVIEWER.communicate_bounded",
            "shared_caches": {k: str(v) for k, v in cache.items()},
            "shared_caches_note": "content-addressed package/browser caches only; deleted at exit unless --cache-dir was given",
        },
        "skill_sha256_at_preparation": protocol["evaluated_snapshot"]["sha256_at_preparation"],
        "model_calls_made": 0,
        "cells": schedule,
        "summary": None,
    }
    if args.rerun:
        prior = json.loads(RESULTS_PATH.read_text(encoding="utf-8"))
        prior_by_id = {c["cell_id"]: c for c in prior["cells"]}
        merged = []
        for old in prior["cells"]:
            fresh = next((c for c in schedule if c["cell_id"] == old["cell_id"]), None)
            if fresh is None:
                merged.append(old)
            else:
                fresh["order"] = old.get("order", fresh["order"])
                fresh["superseded_runs"] = [*old.get("superseded_runs", []),
                                            {k: v for k, v in old.items() if k != "superseded_runs"}]
                merged.append(fresh)
        for fresh in schedule:
            if fresh["cell_id"] not in prior_by_id:
                merged.append(fresh)
        report = {**prior, "host": {**prior["host"], "port_substitution": report["host"]["port_substitution"],
                                    "claude_version": claude_version},
                  "protocol_sha256": protocol_sha, "cells": merged, "finished_at": None,
                  "reruns": [*prior.get("reruns", []),
                             {"started_at": utc_now(), "cells": [c["cell_id"] for c in schedule],
                              "reason": args.rerun_reason,
                              "session_timeouts_s": SESSION_TIMEOUT_S,
                              "protocol_sha256_at_rerun": protocol_sha}]}
        schedule = [c for c in merged if any(c["cell_id"] == s["cell_id"] for s in schedule)]
    write_results(report)
    context = {"report": report, "node_bin": node_bin, "cache": cache, "claude": claude, "credentials": credentials}
    log(f"claude={claude} ({claude_version}); node_bin={node_bin}; cache={cache_root}")

    blocked = False
    try:
        precondition = wildcard_port_precondition()
        report["host"]["port_precondition"] = precondition
        if not precondition["ok"]:
            blocked = True
            for cell in schedule:
                cell["status"] = "NOT_RUN"
                cell["fail_reasons"] = [f"host precondition failed: port {PORT} is bound on a non-loopback interface; "
                                        f"no checkout, install, or model call was attempted for this cell"]
            log(f"BLOCKED: {json.dumps(precondition)}")
        for cell in ([] if blocked else schedule):
            run_cell(cell, targets[cell["target_id"]], context)
            log(f"{cell['cell_id']}: status={cell['status']} reasons={cell.get('fail_reasons')}")
    finally:
        report["finished_at"] = utc_now()
        report["host"]["host_settings_sha256_after"] = sha256_file(host_settings) if host_settings.is_file() else None
        report["host"]["host_settings_unchanged"] = report["host"]["host_settings_sha256_after"] == settings_digest
        all_cells = report["cells"]  # on --rerun this includes the cells that were not rerun
        # Spend is cumulative over every run ever made, superseded runs included.
        all_runs = [run for cell in all_cells for run in (*cell.get("superseded_runs", []), cell)]
        staged = {}
        for run in all_runs:
            for attempt in run.get("setup_attempts", []):
                staged = attempt.get("skill_snapshot") or staged
        report["skill_sha256_staged"] = staged
        report["skill_digest_matches_protocol"] = all(
            staged.get(path) == digest for path, digest in report["skill_sha256_at_preparation"].items()
        ) if staged else None
        costs = [a.get("session", {}).get("result", {}).get("total_cost_usd_reported")
                 for run in all_runs for a in run.get("setup_attempts", [])]
        costs = [c for c in costs if isinstance(c, (int, float))]
        report["summary"] = {
            "cells_total": len(all_cells),
            "cells_pass": sum(1 for c in all_cells if c["status"] == "PASS"),
            "cells_fail": sum(1 for c in all_cells if c["status"] == "FAIL"),
            "cells_setup_failed": sum(1 for c in all_cells if c["status"] == "SETUP_FAILED"),
            "cells_not_run": sum(1 for c in all_cells if c["status"] == "NOT_RUN"),
            "model_calls_made": report["model_calls_made"],
            "total_wall_time_s_including_superseded": round(sum(r.get("wall_time_s", 0) for r in all_runs), 1),
            "total_cost_usd_reported_by_cli_including_superseded": round(sum(costs), 4) if costs else None,
            "cost_note": "subscription-billed host; CLI-reported USD is nominal, per protocol cost_ceiling.monetary",
            "smoke_gate": "BLOCKED_HOST_PRECONDITION" if blocked
            else ("PASS" if all(c["status"] == "PASS" for c in all_cells) else "FAIL"),
        }
        if not caller_cache:
            shutil.rmtree(cache_root, ignore_errors=True)
        report["host"]["shared_caches_deleted"] = not cache_root.exists()
        write_results(report)
        log(f"smoke_gate={report['summary']['smoke_gate']} -> {RESULTS_PATH.relative_to(ROOT)}")
    return {"PASS": 0, "FAIL": 1}.get(report["summary"]["smoke_gate"], 2)


if __name__ == "__main__":
    sys.exit(main())
