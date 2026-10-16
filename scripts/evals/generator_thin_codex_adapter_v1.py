#!/usr/bin/env python3
"""Successor-owned thin Codex adapter, derived from the v3 compatibility adapter.
Only the evidence dependency changes; execution arguments remain identical.
The frozen shared container primitives remain unchanged. Apache-2.0.
"""
from __future__ import annotations

import importlib.util
import json
import os
from pathlib import Path
import pwd
import re
import subprocess
import tempfile
import time
import uuid

ROOT = Path(__file__).resolve().parents[2]
spec = importlib.util.spec_from_file_location("generator_codex_container_shared", ROOT / "scripts/evals/generator_codex_adapter_v2.py")
shared = importlib.util.module_from_spec(spec)
spec.loader.exec_module(shared)
spec_ev = importlib.util.spec_from_file_location("generator_thin_codex_evidence_v1", ROOT / "scripts/evals/generator_thin_codex_evidence_v1.py")
evidence = importlib.util.module_from_spec(spec_ev)
spec_ev.loader.exec_module(evidence)

# Task text is delivered on stdin, never interpolated in this fixed shell script.
START = """set -eu
mkdir -p /codex-home/.codex
chmod 700 /codex-home /codex-home/.codex
cp /auth-source/.codex/auth.json /codex-home/.codex/auth.json
chmod 600 /codex-home/.codex/auth.json
test -L /work/project/node_modules
rm /work/project/node_modules
ln -s /opt/fixtures/node_modules /work/project/node_modules
exec /usr/bin/codex "$@"
"""
# Persistence of the container's CODEX_HOME sessions directory (v2 harness fix 3): the child agents' rollouts live there and are
# invisible in the parent JSON stream. The host directory is bind-mounted at /sessions-out and symlinked into CODEX_HOME so that no
# root-owned intermediate directory is created inside the /codex-home tmpfs. Used only when `command(..., sessions=...)` is given;
# without it the script is byte-identical to START (the frozen adapter's script).
START_SESSIONS = START.replace("chmod 700 /codex-home /codex-home/.codex\n",
                               "chmod 700 /codex-home /codex-home/.codex\nln -s /sessions-out /codex-home/.codex/sessions\n")
assert START_SESSIONS != START
HARNESS_CHECK_ARM = "harness-check"  # live-check arm: declares the playwright-test MCP server like arm A, takes its own prompt line
ARM_LINES = {}  # set by the runner from the frozen prompt text; keys are the two pilot arms (plus HARNESS_CHECK_ARM)
CONTAINER_ENV = {
    "HOME": "/codex-home", "CODEX_HOME": "/codex-home/.codex",
    "PATH": "/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin",
    "PLAYWRIGHT_BROWSERS_PATH": "/ms-playwright",
}
# Copied from the pinned Playwright generator agent's MCP tool list, not the planner/healer surface.
GENERATOR_TOOLS = (
    "browser_click", "browser_drag", "browser_evaluate", "browser_file_upload", "browser_handle_dialog",
    "browser_hover", "browser_navigate", "browser_press_key", "browser_select_option", "browser_snapshot", "browser_type",
    "browser_verify_element_visible", "browser_verify_list_visible", "browser_verify_text_visible", "browser_verify_value",
    "browser_wait_for", "generator_read_log", "generator_setup_page", "generator_write_test",
)
MODELS = ("gpt-6-sol", "gpt-6-astra", "gpt-6.1-sol", "gpt-6-luna", "gpt-5.6-sol", "gpt-5.6-terra")


def docker_prefix(engine):
    executable = Path(engine.CODEX_DOCKER)
    if not executable.is_absolute():
        raise ValueError("Docker executable must be absolute")
    image = engine.CODEX_CONTAINER_IMAGE
    if not re.fullmatch(r"(?:[^\s@]+@)?sha256:[0-9a-f]{64}", image):
        raise ValueError("Docker image must be an immutable sha256 identity")
    prefix = [str(executable)]
    context = getattr(engine, "CODEX_DOCKER_CONTEXT", None)
    if context:
        prefix += ["--context", context]
    return prefix


def command(engine, work, private, name, model, arm=None, sessions=None):
    model = model or MODELS[0]
    if model not in MODELS:
        raise ValueError("model is not in the Codex catalog-v2 roster")
    argv = docker_prefix(engine) + [
        "run", "--rm", "--name", name, "--interactive", "--init",
        "--user", f"{os.getuid()}:{os.getgid()}", "--cap-drop", "ALL",
        "--security-opt", "no-new-privileges", "--read-only",
        "--cpus", "2", "--memory", "4g", "--pids-limit", "512",
        "--tmpfs", "/tmp:rw,nosuid,nodev,mode=1777,size=1g",
        "--tmpfs", f"/codex-home:rw,nosuid,nodev,mode=0700,uid={os.getuid()},gid={os.getgid()},size=1g",
        "--shm-size", "512m", "--network", "bridge",
        "--mount", f"type=bind,src={work},dst=/work",
        "--mount", f"type=bind,src={private},dst=/auth-source,readonly",
        "--workdir", "/work/project",
    ]
    if sessions is not None:
        argv += ["--mount", f"type=bind,src={sessions},dst=/sessions-out"]
    for key, value in CONTAINER_ENV.items():
        argv += ["--env", f"{key}={value}"]
    argv += [engine.CODEX_CONTAINER_IMAGE, "/bin/sh", "-c", START if sessions is None else START_SESSIONS, "container-codex",
             "exec", "--json", "--ignore-user-config", "--ignore-rules",  # compat: no --ephemeral (v2 spawn_agent forks the parent rollout; ephemeral -> "no rollout found")
             "--strict-config", "--sandbox", "danger-full-access", "--disable", "shell_snapshot",
             "-c", "allow_login_shell=false", "--output-schema", "/auth-source/output-schema.json",
             "--model", model, "-c", 'model_reasoning_effort="medium"',
             "--disable", "apps", "--disable", "image_generation", "-c", 'web_search="disabled"',
             "-c", 'shell_environment_policy.inherit="none"',
             "-c", 'projects."/work/project".trust_level="trusted"']
    for key, value in CONTAINER_ENV.items():
        argv += ["-c", f"shell_environment_policy.set.{key}={json.dumps(value)}"]
    if arm in ("official-generator", HARNESS_CHECK_ARM):
        # compat: v2 spawn_agent has no agent-type selector, so the role-scoped [mcp_servers.playwright-test] of the generator
        # TOML is unreachable; declare the same server session-wide (same command as the TOML) with the browser env. Arm A only.
        argv += ["-c", 'approval_policy="never"',
                 "-c", 'mcp_servers.playwright-test.command="npx"',
                 "-c", 'mcp_servers.playwright-test.args=["playwright","run-test-mcp-server"]',
                 "-c", 'mcp_servers.playwright-test.env.PLAYWRIGHT_BROWSERS_PATH="/ms-playwright"',
                 "-c", 'mcp_servers.playwright-test.env.HOME="/codex-home"',
                 "-c", 'mcp_servers.playwright-test.default_tools_approval_mode="approve"',
                 "-c", "mcp_servers.playwright-test.enabled_tools=" + json.dumps(GENERATOR_TOOLS, separators=(",", ":"))]
    return argv + ["-"]


def agent_indicators(events, engine, paths):
    """Deterministic event census; semantic compliance is not claimed."""
    types, mcp, collab = {}, {}, {}
    for event in events:
        item = event.get("item") or {}
        if event.get("type") == "item.completed":
            kind = item.get("type", "?")
            types[kind] = types.get(kind, 0) + 1
            if kind == "mcp_tool_call":
                key = f"{item.get('server', '?')}.{item.get('tool', '?')}:{item.get('status', '?')}"
                mcp[key] = mcp.get(key, 0) + 1
            elif kind == "collab_tool_call":
                key = f"{item.get('tool', '?')}:{item.get('status', '?')}"
                collab[key] = collab.get(key, 0) + 1
    return {"item_type_counts": types, "mcp_tool_calls": mcp, "collab_tool_calls": collab,
            "agent_spawns": collab_spawns(collab),
            "agent_spawns_verification": "event-count",
            "unparsed_event_types": sorted({str(e.get("type")) for e in events} - {"thread.started", "turn.started", "turn.completed", "item.started", "item.completed", "item.updated", "error", "turn.failed"})}


def collab_spawns(collab):
    return sum(count for key, count in collab.items() if key.startswith("spawn_agent") and key.endswith(":completed"))


def persist_cell_sessions(engine, sessions, transcript, paths):
    """Copy the cell's CODEX_HOME sessions (rollouts of the parent and every child agent) next to the transcripts directory, as
    `<transcripts>/../codex-sessions/<transcript stem>/`, sanitised like the transcript. Never raises: a persistence failure is
    recorded in the census and the fidelity classifier then falls back to its secondary evidence."""
    dest = Path(engine.CODEX_TRANSCRIPTS).resolve().parent / evidence.SESSIONS_DIRNAME / transcript.stem
    try:
        return evidence.persist_sessions(sessions, dest, lambda text: engine.sanitize(text, paths))
    except OSError as error:
        return {"files": 0, "bytes": 0, "skipped": [], "dir": None, "error": engine.sanitize(str(error), paths)}


def remove_container(engine, name, env):
    result = subprocess.run(docker_prefix(engine) + ["rm", "--force", name],
                            env=env, capture_output=True, text=True, timeout=30)
    if result.returncode and "No such container" not in result.stderr:
        raise RuntimeError("could not clean up owned generator container")


def configure(engine):
    """Return the frozen v3 engine's call_model callback; configuration is offline."""
    def call_model(project, work, arm, task, model, timeout, budget):
        del budget  # Subscription token usage has no available USD cost.
        started = time.monotonic()
        base = {"infrastructure_error": False, "timeout": False, "error": None,
                "cost_usd": None, "cost_status": "unavailable", "num_turns": 0,
                "usage": None, "model_usage": None, "result_text": "",
                "structured_output": None, "compliance": None}
        if arm not in ARM_LINES:
            raise ValueError("official-pilot adapter supports only " + ", ".join(sorted(ARM_LINES)))
        work, project = Path(work).resolve(), Path(project).resolve()
        if project != work / "project" or work == ROOT or ROOT in work.parents:
            raise ValueError("Docker work must be a disposable external project parent")
        if not (project / ".git").is_dir() or (project / ".git").is_symlink():
            raise ValueError("Codex requires a disposable project-local Git repository")
        modules = project / "node_modules"
        if not modules.is_symlink():
            raise ValueError("disposable fixture node_modules must be an owned symlink")
        original_modules = os.readlink(modules)
        destination = Path(engine.CODEX_TRANSCRIPTS).resolve()
        if destination == ROOT or ROOT in destination.parents:
            raise ValueError("Codex transcripts must be outside the checkout")
        destination.mkdir(parents=True, exist_ok=True)
        transcript = destination / (uuid.uuid4().hex + ".jsonl")
        prompt = engine.FRAME.format(task=task)
        if arm == "ours-2.0.1":
            gen, rev = engine.stage_skills(work, arm)
            prompt += ARM_LINES[arm].format(gen=Path("/work") / gen.resolve().relative_to(work) / "SKILL.md",
                                            rev=Path("/work") / rev.resolve().relative_to(work) / "SKILL.md")
        else:
            prompt += ARM_LINES[arm]
        name = "generator-codex-" + uuid.uuid4().hex
        with tempfile.TemporaryDirectory(prefix="generator-container-auth-") as private, \
                tempfile.TemporaryDirectory(prefix="generator-container-sessions-") as sessions:
            os.chmod(sessions, 0o700)
            paths = (str(work), str(project), private, sessions, "/work/project", "/work", "/auth-source", "/sessions-out", "/codex-home")
            session_census = {"files": 0, "bytes": 0, "skipped": [], "dir": None}
            helper = shared.helpers()
            env = helper.clean_env(None, pwd.getpwuid(os.getuid()).pw_dir)
            try:
                helper.stage_codex_auth(Path(private))
                schema = Path(private) / "output-schema.json"
                schema.write_text(json.dumps(engine.OUTPUT_SCHEMA), encoding="ascii")
                schema.chmod(0o600)
                argv = command(engine, work, private, name, model, arm, sessions)
                proc = subprocess.Popen(argv, env=env, stdin=subprocess.PIPE,
                                        stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                                        text=True, start_new_session=True)
                try:
                    stdout, stderr = proc.communicate(prompt, timeout=timeout)
                except subprocess.TimeoutExpired:
                    stdout, stderr = shared.stop(proc)
                    base.update(timeout=True, error="wall-clock limit")
                except BaseException:
                    stdout, _ = shared.stop(proc)
                    transcript.write_text(engine.sanitize(stdout, paths), encoding="utf-8")
                    transcript.chmod(0o600)
                    raise
                finally:
                    if "stdout" in locals():
                        transcript.write_text(engine.sanitize(stdout, paths), encoding="utf-8")
                        transcript.chmod(0o600)
                    try:
                        remove_container(engine, name, env)
                    finally:  # the container is gone (or force-removed), so its rollouts are complete on the bind-mounted host directory
                        session_census = persist_cell_sessions(engine, sessions, transcript, paths)
            except (OSError, ValueError, RuntimeError, subprocess.TimeoutExpired) as error:
                return {**base, "infrastructure_error": True,
                        "transcript_path": str(transcript) if transcript.exists() else None,
                        "compliance": {"sessions": session_census},
                        "error": engine.sanitize(str(error), paths),
                        "elapsed_ms": round((time.monotonic() - started) * 1000)}
            finally:
                # Restore only the exact infrastructure-owned link; never delete model output.
                if modules.is_symlink() and os.readlink(modules) == "/opt/fixtures/node_modules":
                    modules.unlink()
                    modules.symlink_to(original_modules)
            transcript.write_text(engine.sanitize(stdout, paths), encoding="utf-8")
            transcript.chmod(0o600)
            events, malformed = [], False
            for line in stdout.splitlines():
                try:
                    event = json.loads(line)
                    if not isinstance(event, dict):
                        raise ValueError("event is not an object")
                    events.append(event)
                except ValueError:
                    malformed = True
            completed = [event for event in events if event.get("type") == "turn.completed"]
            finals = [event.get("item", {}).get("text", "") for event in events
                      if event.get("type") == "item.completed"
                      and event.get("item", {}).get("type") == "agent_message"]
            errors = [event for event in events if event.get("type") in {"error", "turn.failed"}]
            base.update(exit_code=proc.returncode, transcript_path=str(transcript),
                        stderr=engine.sanitize(stderr, paths), transcript_events=len(events),
                        num_turns=len(completed), usage=completed[-1].get("usage") if completed else None,
                        usage_all_turns=[event.get("usage") for event in completed],
                        compliance={**shared.indicators(events, engine, paths), **agent_indicators(events, engine, paths),
                                    "sessions": session_census},
                        elapsed_ms=round((time.monotonic() - started) * 1000))
            if base["timeout"]:
                return base
            if shared.RATE_LIMIT.search(stderr + "\n" + json.dumps(errors)):
                return {**base, "infrastructure_error": True, "fatal_infrastructure": True,
                        "error": "Codex usage/rate limit; stop this run"}
            try:
                if proc.returncode or malformed or errors or not completed or not finals:
                    raise ValueError("unsuccessful or incomplete Codex JSON transcript")
                base["structured_output"] = shared.structured(engine.sanitize(finals[-1], paths))
                base["result_text"] = engine.sanitize(finals[-1], paths)
            except ValueError as error:
                base.update(infrastructure_error=True, error=str(error))
            return base
    return call_model


def install(engine):
    engine.call_model = configure(engine)
    return engine.call_model
