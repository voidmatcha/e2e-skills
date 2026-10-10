#!/usr/bin/env python3
"""Codex transport for the frozen generator fixture engine. Apache-2.0."""
from __future__ import annotations

import importlib.util
import json
import os
from pathlib import Path
import pwd
import re
import shutil
import signal
import subprocess
import sys
import tempfile
import time
import uuid

ROOT = Path(__file__).resolve().parents[2]
DEFAULT_MODEL = "gpt-6.1-sol"
RATE_LIMIT = re.compile(r"(?:usage|weekly|rate|quota)\s*(?:limit|exceeded)|too many requests|usage_limit_reached", re.I)


def browser_cache():
    host_home = Path(pwd.getpwuid(os.getuid()).pw_dir)
    cache = host_home / ("Library/Caches/ms-playwright" if sys.platform == "darwin" else ".cache/ms-playwright")
    if not cache.is_dir():
        raise ValueError("trusted host Playwright browser cache is unavailable")
    return cache


def helpers():
    name = "generator_codex_auth_helpers"
    if name not in sys.modules:
        spec = importlib.util.spec_from_file_location(name, ROOT / "scripts/evals/run-reviewer-holdout.py")
        module = importlib.util.module_from_spec(spec)
        sys.modules[name] = module
        spec.loader.exec_module(module)
    return sys.modules[name]


def structured(text):
    value = json.loads(text)
    if not isinstance(value, dict) or set(value) != {"spec_files", "status", "summary"}:
        raise ValueError("invalid final schema keys")
    if (not isinstance(value["spec_files"], list)
            or not all(isinstance(path, str) for path in value["spec_files"])
            or not isinstance(value["status"], str)
            or value["status"] not in {"complete", "partial_or_blocked", "nothing_written", "other"}
            or not isinstance(value["summary"], str)):
        raise ValueError("invalid final schema values")
    return value


def indicators(events, engine, paths):
    commands = [str(event.get("item", {}).get("command", "")) for event in events
                if event.get("type") == "item.completed"
                and event.get("item", {}).get("type") == "command_execution"]
    clean = [engine.sanitize(command, paths) for command in commands]
    return {
        "evidence_source": "codex-json-command-execution", "semantic_compliance": "unverified",
        "tool_counts": {"command_execution": len(commands)}, "bash_commands": clean,
        "read_generator_skill": None, "read_reviewer_skill": None, "read_lean_skill": None,
        "read_rules_only": None, "read_app_source": None, "generator_reference_files_read": [],
        "playwright_test_runs": sum("playwright test" in command for command in commands),
        "repeat_each_runs": sum("--repeat-each" in command for command in commands),
        "scanner_runs": sum("scan.sh" in command for command in commands),
        "exploration_commands": sum("playwright cli" in command or "playwright-cli" in command
                                    or "agent-browser" in command for command in commands),
        "git_status_calls": sum("git status" in command for command in commands),
        "agent_spawns": 0, "agent_spawns_verification": "unverified",
        "write_or_edit_calls": None, "writes_outside_tests": [],
        "legitimate_complete": False,
    }


def stop(proc):
    try:
        os.killpg(proc.pid, signal.SIGKILL)
    except ProcessLookupError:
        pass
    return proc.communicate()


def configure(engine):
    """Return a call_model-compatible callback; no live calls during configuration."""
    def call_model(project, work, arm, task, model, timeout, budget):
        del budget  # Codex subscription usage has no enforceable USD per-call budget.
        started = time.monotonic()
        base = {"infrastructure_error": False, "timeout": False, "error": None,
                "cost_usd": None, "cost_status": "unavailable", "num_turns": 0,
                "usage": None, "model_usage": None, "result_text": "",
                "structured_output": None, "compliance": None}
        if arm not in {"full-fixed", "no-skill"}:
            raise ValueError("Codex adapter supports only full-fixed and no-skill")
        destination = Path(engine.CODEX_TRANSCRIPTS).resolve()
        if destination == ROOT or ROOT in destination.parents:
            raise ValueError("Codex transcripts must be outside the checkout")
        destination.mkdir(parents=True, exist_ok=True)
        transcript = destination / (uuid.uuid4().hex + ".jsonl")
        prompt = engine.FRAME.format(task=task)
        if arm == "full-fixed":
            gen, rev = engine.stage_skills(work, arm)
            prompt += engine.SKILL_LINE.format(gen=gen / "SKILL.md", rev=rev / "SKILL.md")
        with tempfile.TemporaryDirectory(prefix="generator-codex-home-") as private:
            paths = (str(work), str(project), private)
            try:
                helper = helpers()
                env = helper.clean_env("codex", private)
                env["CODEX_HOME"] = str(helper.stage_codex_auth(Path(private)))
                env["PLAYWRIGHT_BROWSERS_PATH"] = str(browser_cache())
                executable = shutil.which("codex", path=env["PATH"])
                if not executable:
                    raise ValueError("codex executable is unavailable")
                schema = Path(private) / "output-schema.json"
                schema.write_text(json.dumps(engine.OUTPUT_SCHEMA), encoding="ascii")
                schema.chmod(0o600)
                command = [executable, "exec", "--json", "--ephemeral", "--ignore-user-config",
                           "--ignore-rules", "--strict-config", "--sandbox", "workspace-write",
                           "--disable", "shell_snapshot", "-c", "allow_login_shell=false",
                           "--output-schema", str(schema), "--add-dir", str(work),
                           "--model", model or DEFAULT_MODEL,
                           "-c", 'model_reasoning_effort="medium"',
                           "-c", "sandbox_workspace_write.network_access=true",
                           "--disable", "apps", "--disable", "image_generation",
                           "-c", 'web_search="disabled"',
                           "-c", 'shell_environment_policy.inherit="none"']
                # A private HOME removes ambient config; pin only the trusted runtime paths
                # needed by the disposable app. Never forward arbitrary ambient shell variables.
                for key in ("PATH", "HOME", "PLAYWRIGHT_BROWSERS_PATH"):
                    command.extend(["-c", f"shell_environment_policy.set.{key}={json.dumps(env[key])}"])
                command.append("-")
                proc = subprocess.Popen(command, cwd=project, env=env, stdin=subprocess.PIPE,
                                        stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                                        text=True, start_new_session=True)
                try:
                    stdout, stderr = proc.communicate(prompt, timeout=timeout)
                except subprocess.TimeoutExpired:
                    stdout, stderr = stop(proc)
                    base.update(timeout=True, error="wall-clock limit")
                except BaseException:
                    interrupted_stdout, _ = stop(proc)
                    transcript.write_text(engine.sanitize(interrupted_stdout, paths), encoding="utf-8")
                    transcript.chmod(0o600)
                    raise
            except (OSError, ValueError) as error:
                return {**base, "infrastructure_error": True,
                        "error": engine.sanitize(str(error), paths),
                        "elapsed_ms": round((time.monotonic() - started) * 1000)}
            # Preserve every stdout line, including malformed lines, but never private host paths.
            transcript.write_text(engine.sanitize(stdout, paths), encoding="utf-8")
            transcript.chmod(0o600)
            events = []
            malformed = False
            for line in stdout.splitlines():
                try:
                    event = json.loads(line)
                    if not isinstance(event, dict):
                        raise ValueError("event is not an object")
                    events.append(event)
                except (ValueError, json.JSONDecodeError):
                    malformed = True
            completed = [event for event in events if event.get("type") == "turn.completed"]
            finals = [event.get("item", {}).get("text", "") for event in events
                      if event.get("type") == "item.completed"
                      and event.get("item", {}).get("type") == "agent_message"]
            base.update(exit_code=proc.returncode, transcript_path=str(transcript),
                        stderr=engine.sanitize(stderr, paths),
                        transcript_events=len(events), num_turns=len(completed),
                        usage=completed[-1].get("usage") if completed else None,
                        compliance=indicators(events, engine, paths),
                        elapsed_ms=round((time.monotonic() - started) * 1000))
            if base["timeout"]:
                return base
            errors = [event for event in events if event.get("type") in {"error", "turn.failed"}]
            if RATE_LIMIT.search(stderr + "\n" + json.dumps(errors)):
                return {**base, "infrastructure_error": True, "fatal_infrastructure": True,
                        "error": "Codex usage/rate limit; stop this run"}
            try:
                if proc.returncode or malformed or errors or not completed or not finals:
                    raise ValueError("unsuccessful or incomplete Codex JSON transcript")
                base["structured_output"] = structured(engine.sanitize(finals[-1], paths))
                base["result_text"] = engine.sanitize(finals[-1], paths)
            except (ValueError, json.JSONDecodeError) as error:
                base.update(infrastructure_error=True, error=str(error))
            return base
    return call_model


def install(engine):
    engine.call_model = configure(engine)
    return engine.call_model
