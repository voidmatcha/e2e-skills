#!/usr/bin/env python3
"""Claude Code transport for generator-multimodel-v1 (host process, isolated skills and tools). Apache-2.0.

One `claude -p` call per cell with the same call_model(project, work, arm, task, model, timeout, budget) signature as the
Codex container adapter, so the runner can swap transports per model. Isolation is configured on the command line and
then VERIFIED from the stream-json `system/init` event of every call (see `check_isolation`); a call whose init event
violates the arm contract is an infrastructure error, never data.

Arm contract
  official-generator : project settings only (the `init-agents --loop=claude` `.claude/agents/*.md`), the project's
                       `.mcp.json` as the only MCP config, tools Read/Grep/Glob/Bash/Agent (no Write/Edit for the parent,
                       so the parent cannot hand-write specs) plus the `playwright-test` MCP server tools.
  official+reviewer  : no settings, no MCP, tools Read/Grep/Glob/Bash/Write/Edit/Agent; staged e2e-reviewer only.
  ours-2.0.1         : no settings, no MCP, same tools; staged playwright-test-generator + e2e-reviewer only.
All arms: --disable-slash-commands (no installed or plugin skill is visible), --strict-mcp-config, auto memory off,
subagents pinned to the matrix model through CLAUDE_CODE_SUBAGENT_MODEL, effort fixed, a deny list that blocks reading
the repository's skills/benchmarks and the saved evidence directories.
"""
from __future__ import annotations

import json
import os
from pathlib import Path
import re
import signal
import subprocess
import time
import uuid

ROOT = Path(__file__).resolve().parents[2]
HOME = Path.home()
CLAUDE_BIN = Path(os.environ.get("CLAUDE_BIN", HOME / ".local/bin/claude"))
ARM_LINES: dict = {}          # set by the runner from the frozen prompt text
BASE_TOOLS = "Read,Grep,Glob,Bash,Write,Edit,Agent"
OFFICIAL_TOOLS = "Read,Grep,Glob,Bash,Agent"
OFFICIAL_ALLOWED = OFFICIAL_TOOLS + ",mcp__playwright-test"
EFFORT = "medium"
RATE_LIMIT = re.compile(r"(?:usage|weekly|rate|quota|session)\s*(?:limit|exceeded)|too many requests|usage_limit|"
                        r"overloaded_error|credit balance", re.I)
DENY = [f"Read({p}/**)" for p in (
    str(HOME / ".cache/e2e-skills-bench"), str(HOME / ".claude"), str(HOME / ".codex"), str(HOME / ".agent"),
    str(HOME / "Documents/e2e-skills/benchmarks"), str(HOME / "Documents/e2e-skills/skills"),
    str(HOME / "Documents/e2e-skills/docs"),
    str(HOME / "Documents/e2e-skills-wt-multimodel/benchmarks"), str(HOME / "Documents/e2e-skills-wt-multimodel/skills"),
    str(HOME / "Documents/e2e-skills-wt-multimodel/docs"),
    str(HOME / "Documents/e2e-skills-wt-offgen"), str(HOME / "Documents/e2e-skills-wt-offrev"),
    str(HOME / "Documents/e2e-skills-wt-osspool"), str(HOME / "Documents/e2e-skills-wt-ablation"),
    str(HOME / "Documents/e2e-skills-wt-210"), str(HOME / "Documents/e2e-skills-bench"))]
# node_modules is reached through a symlink into wt-offrev; allow that single subtree explicitly is not possible with
# deny rules, so reading library sources through the symlink may be blocked. Running playwright via Bash is unaffected.


def settings_json():
    return json.dumps({"permissions": {"deny": DENY}}, sort_keys=True)


def command(arm, model, schema, budget, work):
    cmd = [str(CLAUDE_BIN), "-p", "--no-session-persistence", "--disable-slash-commands", "--strict-mcp-config",
           "--model", model, "--effort", EFFORT, "--output-format", "stream-json", "--verbose",
           "--json-schema", json.dumps(schema), "--max-budget-usd", str(budget), "--add-dir", str(work),
           "--settings", settings_json()]
    if arm == "official-generator":
        cmd += ["--setting-sources", "project", "--mcp-config", ".mcp.json", "--tools", OFFICIAL_TOOLS,
                "--allowedTools", OFFICIAL_ALLOWED]
    else:
        cmd += ["--setting-sources", "", "--tools", BASE_TOOLS, "--allowedTools", BASE_TOOLS]
    return cmd


def check_isolation(arm, init):
    """Return a list of contract violations found in the system/init event (empty list = isolated as specified)."""
    problems = []
    if init is None:
        return ["no system/init event"]
    if init.get("skills"):
        problems.append("skills visible: " + ",".join(map(str, init["skills"]))[:200])
    if init.get("slash_commands"):
        problems.append("slash commands visible")
    agents = set(init.get("agents") or [])
    official_agents = {a for a in agents if a.startswith("playwright-test-")}
    servers = {s.get("name"): s.get("status") for s in (init.get("mcp_servers") or [])}
    tools = set(init.get("tools") or [])
    if arm == "official-generator":
        if "playwright-test-generator" not in agents:
            problems.append("official generator subagent not loaded")
        if servers != {"playwright-test": "connected"}:
            problems.append(f"mcp servers differ: {servers}")
        if tools & {"Write", "Edit", "NotebookEdit", "WebFetch", "WebSearch"}:
            problems.append("parent has write or web tools")
    else:
        if official_agents:
            problems.append("official playwright agents visible outside the official arm")
        if servers:
            problems.append(f"unexpected mcp servers: {servers}")
        if {"WebFetch", "WebSearch"} & tools:
            problems.append("web tools visible")
        if not {"Write", "Edit"} <= tools:
            problems.append("Write/Edit missing")
    return problems


def _blocks(events):
    for event in events:
        if event.get("type") == "assistant":
            for block in (event.get("message") or {}).get("content", []) or []:
                if block.get("type") == "tool_use":
                    yield event, block


def compliance(engine, events, project, work, init, problems):
    base = engine.compliance_from_events(events, project)
    names = {}
    outside = set()
    mcp = {}
    spawns = 0
    work_s, home_s = str(work), str(HOME)
    for event, block in _blocks(events):
        name = block.get("name", "?")
        names[name] = names.get(name, 0) + 1
        inp = block.get("input") or {}
        if name in ("Agent", "Task"):
            spawns += 1
        if name.startswith("mcp__"):
            mcp[name] = mcp.get(name, 0) + 1
        for key in ("file_path", "path"):
            value = inp.get(key)
            if isinstance(value, str) and value.startswith(home_s) and not value.startswith(work_s):
                outside.add(engine.sanitize(value, (work_s,)))
        if name == "Bash":
            cmd = str(inp.get("command", ""))
            for match in re.findall(re.escape(home_s) + r"/[^\s'\"`;)|&]*", cmd):
                if not match.startswith(work_s):
                    outside.add(engine.sanitize(match, (work_s,)))
    base.update(evidence_source="claude-stream-json", tool_counts=names, agent_spawns=spawns,
                agent_spawns_verification="tool_use-count", mcp_tool_calls=mcp,
                official_write_test_calls=mcp.get("mcp__playwright-test__generator_write_test", 0),
                home_paths_touched_outside_work=sorted(outside)[:40],
                isolation={"problems": problems, "skills": (init or {}).get("skills"), "agents": (init or {}).get("agents"),
                           "mcp_servers": (init or {}).get("mcp_servers"), "model": (init or {}).get("model"),
                           "cli": (init or {}).get("claude_code_version")})
    return base


def normalized_usage(envelope):
    """Codex-comparable shape: input_tokens includes cached reads and cache writes; session total, not a last turn."""
    u = envelope.get("usage") or {}
    cached = u.get("cache_read_input_tokens", 0) or 0
    created = u.get("cache_creation_input_tokens", 0) or 0
    total = (u.get("input_tokens", 0) or 0) + cached + created
    return {"input_tokens": total, "cached_input_tokens": cached, "output_tokens": u.get("output_tokens", 0) or 0,
            "cache_creation_input_tokens": created}


def configure(engine):
    def call_model(project, work, arm, task, model, timeout, budget):
        started = time.monotonic()
        base = {"infrastructure_error": False, "timeout": False, "error": None, "cost_usd": None,
                "cost_status": "claude-total_cost_usd", "num_turns": 0, "usage": None, "model_usage": None,
                "result_text": "", "structured_output": None, "compliance": None}
        if arm not in ARM_LINES:
            raise ValueError("adapter supports only " + ", ".join(sorted(ARM_LINES)))
        work, project = Path(work).resolve(), Path(project).resolve()
        if project != work / "project" or work == ROOT or ROOT in work.parents:
            raise ValueError("Claude work must be a disposable external project parent")
        destination = Path(engine.CODEX_TRANSCRIPTS).resolve()
        if destination == ROOT or ROOT in destination.parents:
            raise ValueError("transcripts must be outside the checkout")
        destination.mkdir(parents=True, exist_ok=True)
        transcript = destination / (uuid.uuid4().hex + ".jsonl")
        prompt = engine.FRAME.format(task=task)
        if arm == "ours-2.0.1":
            gen, rev = engine.stage_skills(work, arm)
            prompt += ARM_LINES[arm].format(gen=gen / "SKILL.md", rev=rev / "SKILL.md")
        elif arm == "official+reviewer":
            prompt += ARM_LINES[arm].replace("/work/skill/e2e-reviewer", str(work / "skill/e2e-reviewer"))
        else:
            prompt += ARM_LINES[arm]
        env = {k: v for k, v in os.environ.items() if k not in ("CLAUDECODE", "CLAUDE_CODE_ENTRYPOINT")}
        env.update(CLAUDE_CODE_DISABLE_AUTO_MEMORY="1", CLAUDE_CODE_SUBAGENT_MODEL=model)
        argv = command(arm, model, engine.OUTPUT_SCHEMA, budget, work)
        try:
            proc = subprocess.Popen(argv, cwd=project, stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                                    stderr=subprocess.PIPE, text=True, env=env, start_new_session=True)
        except OSError as error:
            return {**base, "infrastructure_error": True, "error": str(error),
                    "elapsed_ms": round((time.monotonic() - started) * 1000)}
        timed_out = False
        try:
            stdout, stderr = proc.communicate(prompt, timeout=timeout)
        except subprocess.TimeoutExpired:
            timed_out = True
            try:
                os.killpg(proc.pid, signal.SIGKILL)
            except ProcessLookupError:
                pass
            stdout, stderr = proc.communicate()
        paths = (str(work), str(project))
        transcript.write_text(engine.sanitize(stdout or "", paths), encoding="utf-8")
        transcript.chmod(0o600)
        events = []
        for line in (stdout or "").splitlines():
            line = line.strip()
            if line.startswith("{"):
                try:
                    events.append(json.loads(line))
                except json.JSONDecodeError:
                    pass
        init = next((e for e in events if e.get("type") == "system" and e.get("subtype") == "init"), None)
        problems = check_isolation(arm, init)
        base.update(transcript_path=str(transcript), transcript_events=len(events), exit_code=proc.returncode,
                    elapsed_ms=round((time.monotonic() - started) * 1000), stderr=engine.sanitize((stderr or "")[-600:], paths),
                    compliance=compliance(engine, events, project, work, init, problems))
        if problems:
            return {**base, "infrastructure_error": True, "error": "isolation contract violated: " + "; ".join(problems)}
        if timed_out:
            return {**base, "timeout": True, "error": "wall-clock limit"}
        envelope = next((e for e in reversed(events) if e.get("type") == "result"), None)
        if envelope is None:
            return {**base, "infrastructure_error": True,
                    "error": f"exit {proc.returncode}: no result event: {engine.sanitize((stderr or stdout or '')[-300:], paths)}"}
        text = (envelope.get("result") or "") + "\n" + (stderr or "")
        usage = normalized_usage(envelope)
        base.update(cost_usd=envelope.get("total_cost_usd"), num_turns=envelope.get("num_turns"), usage=usage,
                    usage_all_turns=[usage], model_usage=envelope.get("modelUsage"), is_error=envelope.get("is_error"),
                    subtype=envelope.get("subtype"),
                    result_text=engine.sanitize((envelope.get("result") or "")[:3000], paths),
                    structured_output=envelope.get("structured_output"))
        if envelope.get("is_error") and RATE_LIMIT.search(text):
            return {**base, "infrastructure_error": True, "fatal_infrastructure": True,
                    "error": "Claude usage/rate limit; stop this run"}
        if proc.returncode != 0 and base["structured_output"] is None and envelope.get("subtype") not in (
                "error_max_budget_usd", "error_max_turns"):
            return {**base, "infrastructure_error": True, "error": f"exit {proc.returncode}: {envelope.get('subtype')}"}
        return base
    return call_model


def install(engine):
    engine.call_model = configure(engine)
    return engine.call_model
