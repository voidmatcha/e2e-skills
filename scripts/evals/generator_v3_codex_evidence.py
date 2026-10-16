#!/usr/bin/env python3
"""Evidence extraction for generator-multimodel-v3-codex: child-agent rollouts, untruncated compliance, token accounting.
Pure functions over stored files and dicts; no network, no subprocess, no model call. Apache-2.0.

Why this module exists (diagnoses, each re-derived from stored files by an independent audit):
- Under multi_agent v2 a spawned child agent is NOT visible in the parent `codex exec --json` stream: its MCP tool calls and its
  token usage are missing from every record. The child's own rollout (`$CODEX_HOME/sessions/**/rollout-*.jsonl`) holds both, so the
  adapter persists that directory per cell and this module parses it.
- The v3 engine keeps `str(command)[:400]` per Bash command, so a long scanner invocation is missed. `compliance_from_transcript`
  reads the raw transcript instead and never truncates.

Rollout schema as observed in Codex CLI 0.157 to 0.159 rollouts on the host (read for structure only): lines of
`{"timestamp", "ordinal", "type", "payload"}`; `session_meta` carries `id`, `parent_thread_id` and
`source.subagent.thread_spawn.{parent_thread_id, depth, agent_path, agent_nickname, agent_role}`; a completed MCP call is
`event_msg` / `item_completed` with `item.type == "McpToolCall"`, `item.server`, `item.tool`, `item.status`; cumulative per-thread
usage is `event_msg` / `token_count` with `info.total_token_usage` (and `token_usage_record.thread_token_usage`). The container's
Codex build may differ; the parser therefore also accepts the older `mcp_tool_call_end` event and `function_call` items named
`mcp__<server>__<tool>`, and the live check (see the protocol) must show it finds the child's call before any freeze is relied on.
"""
from __future__ import annotations

import json
import re
from pathlib import Path

MCP_SERVER = "playwright-test"
USAGE_KEYS = ("input_tokens", "cached_input_tokens", "cache_write_input_tokens", "output_tokens", "reasoning_output_tokens", "total_tokens")
SESSIONS_DIRNAME = "codex-sessions"


# Tools of the `playwright-test` server that belong to the generator agent definition (browser_* and generator_*). The server also
# exposes test_* (test_list, test_run, test_debug) and planner_* tools; a call to those is not evidence that the generator ran.
GENERATOR_SURFACE_PREFIXES = ("generator_", "browser_")


def is_generator_surface_tool(tool) -> bool:
    return str(tool or "").startswith(GENERATOR_SURFACE_PREFIXES)


def norm_server(name) -> str:
    return str(name or "").replace("-", "_").lower()


def is_mcp_server(name) -> bool:
    return norm_server(name) == norm_server(MCP_SERVER)


# ------------------------------------------------------------------------------------------------ usage helpers

def usage_dict(raw) -> dict:
    """Normalise a Codex usage object to integers; unknown or missing keys are 0."""
    raw = raw if isinstance(raw, dict) else {}
    out = {k: int(raw.get(k) or 0) for k in USAGE_KEYS}
    if not out["total_tokens"]:
        out["total_tokens"] = out["input_tokens"] + out["output_tokens"]
    return out


def add_usage(a: dict, b: dict) -> dict:
    return {k: int(a.get(k, 0)) + int(b.get(k, 0)) for k in USAGE_KEYS}


def zero_usage() -> dict:
    return {k: 0 for k in USAGE_KEYS}


# ------------------------------------------------------------------------------------------------ rollouts

def _function_call_mcp(payload: dict):
    """`mcp__<server>__<tool>` in the function name, or namespace `mcp__<server>__` plus a bare tool name."""
    full = f"{payload.get('namespace') or ''}{payload.get('name') or ''}"
    match = re.match(r"^mcp__(.+?)__(.+)$", full)
    return (match.group(1), match.group(2)) if match else None


def _result_object(result):
    """Decode structured fallback output; prose and missing results cannot prove success."""
    if isinstance(result, str):
        try:
            return json.loads(result)
        except ValueError:
            return None
    return result


def _call_status(item_status, result=None, fallback=False) -> str:
    status = str(item_status or "").lower()
    result = _result_object(result)
    if isinstance(result, dict):
        if "Err" in result or result.get("isError") or result.get("error"):
            return "failed"
        if "Ok" in result:
            return _call_status(item_status, result["Ok"], fallback)
        if fallback and (result.get("isError") is False or isinstance(result.get("content"), list)):
            return "completed"
    return "unverified" if fallback else status or "unverified"


def _spawn_ids(result):
    result = _result_object(result)
    if not isinstance(result, dict) or result.get("error") or result.get("isError") or "Err" in result:
        return []
    ids = result.get("receiver_thread_ids")
    if ids is None:
        ids = [result.get("agent_id") or result.get("thread_id") or result.get("receiver_thread_id") or result.get("new_thread_id")]
    return sorted({value for value in ids if isinstance(value, str) and value}) if isinstance(ids, list) else []


def spawn_observation(events):
    """Unique completed spawn identities in stream/rollout dialects; unknown identities stay gaps."""
    ids, unknown, calls, outputs = set(), 0, {}, {}
    for event in events or []:
        kind = event.get("type")
        payload = event.get("payload") or {}
        item = event.get("item") or {}
        if kind == "event_msg" and payload.get("type") == "item_completed":
            item = payload.get("item") or {}
        elif kind == "event_msg" and payload.get("type") == "collab_agent_spawn_end":
            found = _spawn_ids(payload)
            ids.update(found)
            unknown += not bool(found)
        if kind == "item.completed" or (kind == "event_msg" and payload.get("type") == "item_completed"):
            if str(item.get("type") or "").lower() in ("collab_tool_call", "collabagenttoolcall") \
                    and item.get("tool") == "spawn_agent" and item.get("status") == "completed":
                found = _spawn_ids(item)
                ids.update(found)
                unknown += not bool(found)
        if kind == "response_item" and payload.get("type") == "function_call" \
                and str(payload.get("name") or "").rsplit(".", 1)[-1] == "spawn_agent":
            calls[payload.get("call_id")] = payload
        elif kind == "response_item" and payload.get("type") == "function_call_output":
            outputs[payload.get("call_id")] = payload.get("output")
    for call_id in calls:
        found = _spawn_ids(outputs.get(call_id))
        ids.update(found)
        unknown += not bool(found)
    return {"thread_ids": sorted(ids), "unresolved": unknown}



def successful_plan_shell(events):
    """Observed successful shell execution reading the staged plan; narration never counts."""
    calls, outputs, succeeded = {}, {}, 0
    def plan_command(command):
        return bool(re.search(r"\b(?:cat|ls|stat)\b", str(command)) and "specs/plan.md" in str(command))
    for event in events:
        payload = event.get("payload") or {}
        item = event.get("item") or payload.get("item") or {}
        if event.get("type") == "response_item":
            if payload.get("type") == "function_call":
                name = str(payload.get("name") or "").rsplit(".", 1)[-1]
                if name in ("exec_command", "exec") and plan_command(payload.get("arguments")):
                    calls[payload.get("call_id")] = payload
            elif payload.get("type") == "function_call_output":
                outputs[payload.get("call_id")] = payload.get("output")
        if payload.get("type") == "exec_command_end":
            succeeded += payload.get("exit_code") == 0 and plan_command(payload.get("command"))
        elif (event.get("type") == "item.completed" or payload.get("type") == "item_completed") and str(item.get("type")).lower() in ("commandexecution", "command_execution"):
            succeeded += item.get("exit_code") == 0 and plan_command(item.get("command"))
    for call_id in calls:
        output = outputs.get(call_id)
        parsed = _result_object(output)
        if isinstance(parsed, dict) and parsed.get("exit_code") == 0:
            succeeded += 1
        elif isinstance(output, str) and re.search(r"(?:Process exited with code|[Ee]xit code:)\s*0\b", output) and not re.search(r"bwrap:|requires approval|permission denied", output, re.I):
            succeeded += 1
    return succeeded


def parse_rollout(path) -> dict:
    """One rollout file -> identity, completed MCP calls and cumulative token usage. Malformed lines are counted, not fatal."""
    meta, event_calls, function_calls = {}, [], []
    cumulative, records, last_usages, malformed, lines, outputs = [], [], [], 0, 0, {}
    events = []
    models = set()
    for raw in Path(path).read_text(errors="replace").splitlines():
        if not raw.strip():
            continue
        try:
            event = json.loads(raw)
            if not isinstance(event, dict):
                raise ValueError
        except ValueError:
            malformed += 1
            continue
        lines += 1
        events.append(event)
        kind, payload = event.get("type"), event.get("payload") or {}
        if kind == "session_meta" and not meta:
            meta = payload
        elif kind == "turn_context" and payload.get("model"):
            models.add(str(payload["model"]))
        elif kind == "event_msg":
            ptype = payload.get("type")
            if ptype == "item_completed":
                item = payload.get("item") or {}
                if str(item.get("type") or "").lower() in ("mcptoolcall", "mcp_tool_call"):
                    event_calls.append({"server": item.get("server"), "tool": item.get("tool"),
                                        "status": _call_status(item.get("status"), item.get("result")), "id": item.get("id")})
            elif ptype == "mcp_tool_call_end":
                inv = payload.get("invocation") or {}
                event_calls.append({"server": inv.get("server"), "tool": inv.get("tool"),
                                    "status": _call_status("completed", payload.get("result")), "id": payload.get("call_id")})
            elif ptype == "token_count":
                info = payload.get("info") or {}
                if info.get("total_token_usage"):
                    cumulative.append(usage_dict(info["total_token_usage"]))
                if info.get("last_token_usage"):
                    last_usages.append(usage_dict(info["last_token_usage"]))
        elif kind == "token_usage_record":
            if payload.get("thread_token_usage"):
                records.append(usage_dict(payload["thread_token_usage"]))
        elif kind == "response_item" and payload.get("type") == "function_call_output":
            outputs[payload.get("call_id")] = payload.get("output")
        elif kind == "response_item" and payload.get("type") == "function_call":
            found = _function_call_mcp(payload)
            if found:
                function_calls.append({"server": found[0], "tool": found[1], "status": "requested", "id": payload.get("call_id")})
    # Cumulative usage is monotonic: the largest total is the thread total. Fall back to summing per-response usage.
    if cumulative:
        usage, usage_source = max(cumulative, key=lambda u: u["total_tokens"]), "token_count.total_token_usage"
    elif records:
        usage, usage_source = max(records, key=lambda u: u["total_tokens"]), "token_usage_record.thread_token_usage"
    elif last_usages:
        usage, usage_source = usage_dict({k: sum(u[k] for u in last_usages) for k in USAGE_KEYS}), "sum(last_token_usage)"
    else:
        usage, usage_source = None, None
    source = meta.get("source")  # a string ("exec", "cli") for a top-level thread, an object for a spawned one
    subagent = (((source.get("subagent") if isinstance(source, dict) else None) or {}).get("thread_spawn")) or {}
    subagent = subagent if isinstance(subagent, dict) else {}
    name = Path(path).name
    guessed = re.search(r"([0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12})\.jsonl$", name)
    # Event-shaped records are authoritative; function_call items are only a fallback because they are requests: one counts as
    # completed only when the matching output is structured success evidence; errors fail and prose stays unverified.
    for call in function_calls:
        call["status"] = _call_status(None, outputs[call["id"]], fallback=True) if call["id"] in outputs else "requested"
    calls, source = (event_calls, "event") if event_calls else (function_calls, "function_call") if function_calls else ([], None)
    return {"file": name, "thread_id": meta.get("id") or (guessed.group(1) if guessed else None),
            "parent_thread_id": meta.get("parent_thread_id") or subagent.get("parent_thread_id"),
            "agent_role": meta.get("agent_role") or subagent.get("agent_role"), "agent_path": meta.get("agent_path") or subagent.get("agent_path"),
            "depth": subagent.get("depth"), "has_meta": bool(meta), "models": sorted(models), "lines": lines, "malformed_lines": malformed,
            "mcp_calls": calls, "mcp_source": source, "usage": usage, "usage_source": usage_source,
            "spawns": spawn_observation(events), "plan_shell_successes": successful_plan_shell(events)}


def load_sessions(directory) -> list:
    root = Path(directory)
    if not root.is_dir():
        return []
    return [parse_rollout(f) for f in sorted(root.rglob("rollout-*.jsonl")) if f.is_file() and not f.is_symlink()]


def _tally(calls) -> dict:
    out = {}
    for call in calls:
        key = f"{call.get('server')}.{call.get('tool')}"
        slot = out.setdefault(key, {"completed": 0, "other": 0})
        slot["completed" if call.get("status") == "completed" else "other"] += 1
    return out


def summarize_sessions(rollouts, root_thread_id=None, parent_events=None) -> dict:
    """Aggregate one cell's rollouts. The cell has a private sessions directory, so every rollout in it belongs to the cell; the
    parent chain classifies each one as root, descendant (child agent) or unlinked (kept, flagged, counted as a child for cost)."""
    by_thread, unique, duplicates = {}, [], []
    for record in rollouts:
        thread = record.get("thread_id")
        if thread and thread in by_thread:
            duplicates.append(thread)
        else:
            unique.append(record)
            if thread:
                by_thread[thread] = record
    rollouts = unique
    matched = [r for r in rollouts if root_thread_id and r["thread_id"] == root_thread_id]
    parentless = [r for r in rollouts if not r.get("parent_thread_id")]
    pool = matched or parentless  # a root whose id the stream did not name is still recognisable as the only parentless rollout
    root = pool[0] if len(pool) == 1 else None
    descendants, frontier = [], ({root["thread_id"]} if root else set())
    while frontier:
        level = [r for r in rollouts if r is not root and all(r is not d for d in descendants) and r.get("parent_thread_id") in frontier]
        descendants += level
        frontier = {r["thread_id"] for r in level if r.get("thread_id")}
    linked = {id(r) for r in descendants} | ({id(root)} if root else set())
    unlinked = [r for r in rollouts if id(r) not in linked]
    # A rollout that names a parent but is not under the root still is a child agent (cost counts it); a parentless extra one is
    # not a child and is flagged instead of being counted twice.
    children = descendants + [r for r in unlinked if r.get("parent_thread_id")]
    extra_roots = [r for r in unlinked if not r.get("parent_thread_id")]
    spawn_gaps = []
    if duplicates:
        spawn_gaps.append("duplicate thread rollout(s): " + ", ".join(sorted(set(duplicates))))
    if any(not r.get("thread_id") for r in rollouts):
        spawn_gaps.append("rollout thread identity missing")
    observations = [(r.get("thread_id"), r.get("spawns") or {"thread_ids": [], "unresolved": 0}) for r in rollouts]
    parent_spawns = spawn_observation(parent_events)
    observations.append((root["thread_id"] if root else root_thread_id, parent_spawns))
    expected = set()
    for parent, observation in observations:
        unresolved = observation["unresolved"]
        expected.update((parent, child) for child in observation["thread_ids"])
        if unresolved:
            # Codex multi_agent v2 spawn outputs carry only a task name, not a thread id (observed live 2026-10-15). Resolve such
            # spawns by persisted child rollouts that name this parent and are not already accounted for; fewer children than
            # unresolved spawns stays a gap.
            claimed = {child for (_, child) in expected}
            candidates = [r.get("thread_id") for r in rollouts
                          if parent and r.get("parent_thread_id") == parent and r.get("thread_id") and r.get("thread_id") not in claimed]
            taken = candidates[:unresolved]
            expected.update((parent, child) for child in taken)
            unresolved -= len(taken)
        if unresolved:
            spawn_gaps.append("%d completed spawn(s) or spawn request(s) without resolved child identity" % unresolved)
    for parent, child in sorted(expected, key=str):
        persisted = by_thread.get(child)
        if persisted is None:
            spawn_gaps.append("spawned thread rollout missing: " + child)
        elif not parent or persisted.get("parent_thread_id") != parent:
            spawn_gaps.append("spawned thread parent mismatch: " + child)
    all_calls = [c for r in rollouts for c in r["mcp_calls"]]
    child_calls = [c for r in children for c in r["mcp_calls"]]
    done = lambda calls: [c for c in calls if c.get("status") == "completed" and is_mcp_server(c.get("server"))]
    child_usage = zero_usage()
    for r in children:
        if r["usage"]:
            child_usage = add_usage(child_usage, r["usage"])
    return {"rollouts_found": len(rollouts), "root_found": root is not None, "root_thread_id": root["thread_id"] if root else None,
            "children_linked": len(descendants), "children_unlinked": len(children) - len(descendants), "children_total": len(children),
            "extra_root_rollouts": len(extra_roots),
            "spawn_observation_gaps": spawn_gaps, "parent_stream_spawns": parent_spawns,
            "children_without_usage": sum(1 for r in children if not r["usage"]),
            "malformed_lines": sum(r["malformed_lines"] for r in rollouts),
            "mcp_calls": _tally(all_calls), "mcp_source": sorted({r["mcp_source"] for r in rollouts if r["mcp_source"]}),
            "playwright_test_completed": len(done(all_calls)),
            "generator_surface_completed": sum(1 for c in done(all_calls) if is_generator_surface_tool(c.get("tool"))),
            "other_playwright_test_completed": sum(1 for c in done(all_calls) if not is_generator_surface_tool(c.get("tool"))),
            "child_playwright_test_completed": len(done(child_calls)), "child_mcp_calls": _tally(child_calls),
            "child_plan_shell_successes": sum(r.get("plan_shell_successes", 0) for r in children),
            "generator_tool_completed": sum(1 for c in done(all_calls) if str(c.get("tool")).startswith("generator_")),
            "generator_write_test_completed": sum(1 for c in done(all_calls) if c.get("tool") == "generator_write_test"),
            "child_usage": child_usage, "root_rollout_usage": root["usage"] if root else None,
            "child_agent_roles": sorted({str(r.get("agent_role")) for r in children})}


def sessions_dir_for(rec: dict, transcripts_dir) -> Path | None:
    """The persisted sessions directory of a cell: `<transcripts dir>/../codex-sessions/<transcript stem>`."""
    stem = Path(rec.get("transcript_path") or "").stem
    return Path(transcripts_dir).parent / SESSIONS_DIRNAME / stem if stem else None


def root_thread_of(events) -> str | None:
    for event in events or []:
        if event.get("type") == "thread.started" and event.get("thread_id"):
            return event["thread_id"]
    return None


def persist_sessions(src, dest, sanitize=lambda text: text, max_file_bytes=64 * 1024 * 1024) -> dict:
    """Copy rollout files (never symlinks, never oversize files) from a per-cell sessions directory to the cell's persistent copy,
    sanitising their text. Returns a census; a missing source is an empty census, not an error."""
    src, dest = Path(src), Path(dest)
    census = {"files": 0, "bytes": 0, "skipped": [], "dir": dest.name}
    if not src.is_dir():
        return census
    for f in sorted(src.rglob("*")):
        if f.is_symlink() or not f.is_file():
            if f.is_symlink():
                census["skipped"].append(f.name + " (symlink)")
            continue
        if f.stat().st_size > max_file_bytes:
            census["skipped"].append(f.name + " (oversize)")
            continue
        target = dest / f.relative_to(src)
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(sanitize(f.read_text(errors="replace")), encoding="utf-8")
        target.chmod(0o600)
        census["files"] += 1
        census["bytes"] += target.stat().st_size
    return census


# ------------------------------------------------------------------------------------------------ untruncated compliance

CMD_RE = {
    "skill_md_read": re.compile(r"playwright-test-generator/SKILL\.md"),
    "reviewer_skill_read": re.compile(r"e2e-reviewer/SKILL\.md"),
    "preflight": re.compile(r"run-preflight-target"),
    "scanner_mention": re.compile(r"scan\.sh"),
    "scanner_exec": re.compile(r"(?:^|[\s;&|'\"(])(?:/usr/bin/bash|/bin/bash|bash|/bin/sh|sh)(?:\s+-[A-Za-z]+)*\s+\S*scan\.sh"
                               r"|(?:^|[;&|(])\s*(?:\w+=\S+\s+)*(?:\./|/)\S*scan\.sh\b"),
    "playwright_test": re.compile(r"playwright(?:\"|')?\s+test\b"),
    "repeat_each": re.compile(r"--repeat-each"),
    "exploration": re.compile(r"playwright[ -]cli|agent-browser|run-raw-aria-snapshot"),
    "git_status": re.compile(r"git status"),
}
GENERATOR_REF = re.compile(r"playwright-test-generator/([A-Za-z0-9_.-]+\.md)")
REVIEWER_REF = re.compile(r"e2e-reviewer/references/([A-Za-z0-9_./-]+\.md)")


def tool_uses(events):
    """(kind, payload) pairs from either transcript dialect. Codex: completed command_execution and collab spawn items.
    Claude stream-json: assistant tool_use blocks."""
    for event in events:
        item = event.get("item") or {}
        if event.get("type") == "item.completed":
            if item.get("type") == "command_execution":
                yield "command", str(item.get("command", ""))
            elif item.get("type") == "collab_tool_call" and item.get("tool") == "spawn_agent" and item.get("status") == "completed":
                yield "spawn", ""
        elif event.get("type") == "assistant":
            for block in (event.get("message") or {}).get("content", []) or []:
                if not isinstance(block, dict) or block.get("type") != "tool_use":
                    continue
                name, inp = block.get("name", "?"), block.get("input") or {}
                if name == "Bash":
                    yield "command", str(inp.get("command", ""))
                elif name == "Read":
                    yield "read", str(inp.get("file_path", ""))
                elif name in ("Agent", "Task"):
                    yield "spawn", ""
                elif name == "Skill":
                    yield "skill", str(inp.get("skill") or inp.get("name") or "")


def compliance_from_events(events) -> dict:
    """Deterministic, untruncated indicators of what the call did. A command is never cut: the v3 engine's `[:400]` missed long
    scanner invocations. `scanner_runs` keeps the engine's definition (the command mentions scan.sh) for comparability;
    `scanner_exec_runs` is the stricter count (scan.sh is the script of a bash/sh invocation)."""
    commands, reads, skills, spawns = [], [], [], 0
    for kind, value in tool_uses(events):
        if kind == "command":
            commands.append(value)
        elif kind == "read":
            reads.append(value)
        elif kind == "skill":
            skills.append(value)
        elif kind == "spawn":
            spawns += 1
    seen = commands + reads
    count = lambda key, pool=commands: sum(bool(CMD_RE[key].search(c)) for c in pool)
    refs = sorted({m for text in seen for m in GENERATOR_REF.findall(text) if m != "SKILL.md"})
    return {"command_count": len(commands), "read_tool_calls": len(reads), "max_command_chars": max((len(c) for c in commands), default=0),
            "commands_over_400_chars": sum(len(c) > 400 for c in commands),
            "skill_md_read": any(CMD_RE["skill_md_read"].search(t) for t in seen),
            "generator_reference_files_read": refs,
            "reviewer_skill_read": any(CMD_RE["reviewer_skill_read"].search(t) for t in seen),
            "reviewer_reference_files_read": sorted({m for text in seen for m in REVIEWER_REF.findall(text)}),
            "preflight_runs": count("preflight"), "scanner_runs": count("scanner_mention"), "scanner_exec_runs": count("scanner_exec"),
            "playwright_test_runs": count("playwright_test"), "repeat_each_runs": count("repeat_each"),
            "exploration_commands": count("exploration"), "git_status_calls": count("git_status"),
            "agent_spawns_in_stream": spawns, "skill_tool_calls": sorted(skills), "bash_commands": commands}


def read_events(path) -> list | None:
    path = Path(path) if path else None
    if not path or not path.is_file():
        return None
    out = []
    for line in path.read_text(errors="replace").splitlines():
        try:
            event = json.loads(line)
        except ValueError:
            continue
        if isinstance(event, dict):
            out.append(event)
    return out


def compliance_from_transcript(path) -> dict | None:
    events = read_events(path)
    return None if events is None else compliance_from_events(events)


# Pre-declared key steps of the arm C treatment (the skill's own workflow). `treated_core` defines the as-treated view.
C_STEPS = ("skill_md_read", "reference_read", "preflight", "exploration", "scanner", "independent_review", "self_reported_complete")


def c_treatment(comp: dict | None, structured_status=None) -> dict:
    """Arm C treatment fidelity from the raw compliance and the self-reported status. `treated_core` (the as-treated definition,
    fixed in advance) = SKILL.md read AND at least one generator reference file read AND the scanner executed at least once
    (`scanner_exec_runs`; `scanner_mentioned` keeps the looser engine definition beside it). Steps are read from the parent
    stream only: a command run by a spawned agent is not seen."""
    if comp is None:
        return {"available": False, "steps": {}, "treated_core": False, "steps_done": 0}
    steps = {"skill_md_read": bool(comp["skill_md_read"]), "reference_read": bool(comp["generator_reference_files_read"]),
             "preflight": comp["preflight_runs"] > 0, "exploration": comp["exploration_commands"] > 0, "scanner": comp["scanner_exec_runs"] > 0,
             "independent_review": bool(comp["reviewer_skill_read"]) and comp["agent_spawns_in_stream"] > 0,
             "self_reported_complete": structured_status == "complete"}
    return {"available": True, "steps": steps, "treated_core": steps["skill_md_read"] and steps["reference_read"] and steps["scanner"],
            "steps_done": sum(steps.values()), "scanner_mentioned": comp["scanner_runs"] > 0,
            "step_source": "parent stream only (commands run by spawned agents are not read)"}


def b_treatment(comp: dict | None) -> dict:
    """Arm B (reviewer call) fidelity: the reviewer SKILL.md was read and the scanner was run."""
    if comp is None:
        return {"available": False, "treated": False}
    return {"available": True, "reviewer_skill_read": bool(comp["reviewer_skill_read"]), "scanner": comp["scanner_exec_runs"] > 0,
            "scanner_mentioned": comp["scanner_runs"] > 0, "reviewer_reference_read": bool(comp["reviewer_reference_files_read"]),
            "treated": bool(comp["reviewer_skill_read"]) and comp["scanner_exec_runs"] > 0,
            "step_source": "parent stream only (commands run by spawned agents are not read)"}


# ------------------------------------------------------------------------------------------------ tokens and cost

TOKEN_FIELDS = ("uncached_input", "cached_input", "output", "reasoning_output", "child_uncached_input", "child_cached_input",
                "child_output", "processed", "total")


def _blank_tokens() -> dict:
    return {k: 0 for k in TOKEN_FIELDS}


def codex_tokens(rec: dict, sessions: dict | None) -> dict:
    """Parent usage = the parent thread's OWN rollout total when it is persisted (correct whether or not the stream folds the
    children in), else the stream (sum over turn.completed events; a single turn in `codex exec`). The other value is kept as a
    cross-check (`parent_cross_check`). Child usage comes from the descendants' rollouts. `uncached_input` = input_tokens -
    cached_input_tokens (Codex counts cached tokens inside input_tokens; cache_write_input_tokens is reported by the CLI and observed
    0, assumed inside input_tokens). `processed` = uncached input + output (cached input excluded); `total` = input + output as
    the CLI reports it."""
    turns = [u for u in (rec.get("usage_all_turns") or []) if u]
    stream, stream_source = None, None
    if turns:
        stream, stream_source = usage_dict({k: sum(int(t.get(k) or 0) for t in turns) for k in USAGE_KEYS}), "stream.turn.completed"
    elif rec.get("usage"):
        stream, stream_source = usage_dict(rec["usage"]), "stream.usage"
    rollout_usage = (sessions or {}).get("root_rollout_usage")
    if rollout_usage:
        parent, source = rollout_usage, "rollout"
    else:
        parent, source = stream, stream_source
    cross = None
    if stream and rollout_usage:
        cross = {"stream_total": stream["total_tokens"], "rollout_total": rollout_usage["total_tokens"],
                 "differs": abs(stream["total_tokens"] - rollout_usage["total_tokens"]) > 0.02 * max(stream["total_tokens"], 1)}
    out = {"family": "codex", "parent_source": source, "complete": parent is not None, "parent_turns": len(turns) or (1 if parent else 0),
           "children_included": None, "parent_cross_check": cross}
    t = _blank_tokens()
    if parent:
        t.update(uncached_input=max(0, parent["input_tokens"] - parent["cached_input_tokens"]), cached_input=parent["cached_input_tokens"],
                 output=parent["output_tokens"], reasoning_output=parent["reasoning_output_tokens"])
    if sessions is None:
        out.update(child_status="unavailable (no persisted sessions)", complete=False)
    else:
        cu = sessions["child_usage"]
        t.update(child_uncached_input=max(0, cu["input_tokens"] - cu["cached_input_tokens"]), child_cached_input=cu["cached_input_tokens"],
                 child_output=cu["output_tokens"])
        out["child_status"] = "from rollouts" if sessions["children_total"] else "no child rollouts"
        if sessions["children_without_usage"]:
            out.update(complete=False, child_status=f"{sessions['children_without_usage']} child rollout(s) without usage")
        census = (rec.get("compliance") or {}).get("sessions") or {}
        spawns = (rec.get("compliance") or {}).get("agent_spawns", 0)
        gaps = []
        if not sessions.get("root_found") or not rollout_usage:
            gaps.append("root rollout or root usage missing")
        gaps.extend(sessions.get("spawn_observation_gaps") or [])
        if spawns and "parent_stream_spawns" not in sessions:
            gaps.append("spawned child identities unavailable")
        if census.get("skipped") or census.get("error"):
            gaps.append("persistence census incomplete")
        if sessions.get("malformed_lines") or sessions.get("extra_root_rollouts") or sessions.get("children_unlinked"):
            gaps.append("rollout parsing or lineage incomplete")
        if gaps:
            out.update(complete=False, observation_gaps=gaps)
    t["processed"] = t["uncached_input"] + t["output"] + t["child_uncached_input"] + t["child_output"]
    t["total"] = t["processed"] + t["cached_input"] + t["child_cached_input"]
    out.update(t)
    return out


def claude_tokens(rec: dict) -> dict:
    """Claude record: tokens and cost from `modelUsage` (the CLI envelope's per-model block), falling back to `usage`/cost_usd.
    `uncached_input` = inputTokens + cacheCreationInputTokens (a cache write is billed as input); cached = cacheReadInputTokens."""
    mu = rec.get("model_usage") or {}
    t, cost = _blank_tokens(), 0.0
    for block in mu.values():
        t["uncached_input"] += int(block.get("inputTokens") or 0) + int(block.get("cacheCreationInputTokens") or 0)
        t["cached_input"] += int(block.get("cacheReadInputTokens") or 0)
        t["output"] += int(block.get("outputTokens") or 0)
        t["reasoning_output"] += int(block.get("thinkingTokens") or 0)
        cost += float(block.get("costUSD") or 0)
    source = "modelUsage"
    if not mu and rec.get("usage"):
        u = rec["usage"]
        t.update(uncached_input=max(0, int(u.get("input_tokens") or 0) - int(u.get("cached_input_tokens") or 0)),
                 cached_input=int(u.get("cached_input_tokens") or 0), output=int(u.get("output_tokens") or 0))
        source, cost = "usage", float(rec.get("cost_usd") or 0)
    t["processed"] = t["uncached_input"] + t["output"]
    t["total"] = t["processed"] + t["cached_input"]
    return dict(t, family="claude", parent_source=source, complete=bool(mu or rec.get("usage")), children_included=True,
                child_status="subagents are inside modelUsage", cost_usd=round(cost, 6) if (mu or rec.get("usage")) else None,
                models=sorted(mu))


def proven_skipped_reviewer(rec):
    """A runner-stamped, never-launched B call; missing observations alone prove nothing."""
    return (rec.get("arm") == "official+reviewer" and rec.get("model_call_launched") is False
            and rec.get("call_skip_reason") == "source_a_missing_spec"
            and not rec.get("attempts") and not rec.get("transcript_path")
            and not rec.get("usage") and not rec.get("usage_all_turns")
            and not rec.get("model_usage") and rec.get("num_turns", 0) == 0
            and rec.get("elapsed_ms") == 0 and not rec.get("infrastructure_error"))


def skipped_reviewer_tokens():
    return dict(_blank_tokens(), complete=True, family="codex", cost_usd=0,
                parent_source="runner: reviewer never launched", children_included=True,
                child_status="no model call", model_call_launched=False)


def cell_tokens(rec: dict, sessions: dict | None) -> dict:
    if proven_skipped_reviewer(rec):
        return skipped_reviewer_tokens()
    return claude_tokens(rec) if rec.get("model_usage") else codex_tokens(rec, sessions)


def pipeline_tokens(parts) -> dict:
    """Sum of per-cell token dicts: arm B's pipeline is its source arm A cell plus the reviewer call."""
    out = _blank_tokens()
    out["complete"] = all(p["complete"] for p in parts)
    for p in parts:
        for k in TOKEN_FIELDS:
            out[k] += p[k]
    cost = [p.get("cost_usd") for p in parts]
    out["cost_usd"] = round(sum(c for c in cost if c is not None), 6) if any(c is not None for c in cost) else None
    return out


# ------------------------------------------------------------------------------------------------ static selector reference

# Single- and double-quoted literals stay on one line; a backtick (template) literal may span lines.
STRING_LITERAL = re.compile(r"""'((?:\\.|[^'\\\n])*)'|"((?:\\.|[^"\\\n])*)"|`((?:\\.|[^`\\])*)`""")
# Hints that a selector is built at run time (concatenation or interpolation after a `#`, `.` or locator call): the static scan
# cannot read such a selector, so a cell with a hint and no literal hit is not proven clean of renamed selectors.
DYNAMIC_SELECTOR = re.compile(r"""['"`][#.][\w-]*['"`]\s*\+|\+\s*['"`][#.]|`[^`]*[#.][\w-]*\$\{|`\$\{[^}]*\}[^`]*`\s*\)|(?:locator|\$\$?)\(\s*[A-Za-z_][\w.]*\s*[+)]""")


def references_renamed_selector(texts, tokens) -> bool | None:
    """True if any string literal of the spec texts references a pre-refactor id or class that the case's refactor renames, as
    `#token`, `.token` (also after a tag, `article.over`) or an `[id=token]` / `[class*=token]` attribute selector. Only string
    literals are searched, so property access such as `data.total` is not a selector. `tokens` come from the engine's refactor
    manifest. None if there is no text to inspect or no token to look for."""
    texts = [t for t in texts if t]
    if not texts or not tokens:
        return None
    literals = [m.group(1) or m.group(2) or m.group(3) or "" for text in texts for m in STRING_LITERAL.finditer(text)]
    for token in tokens:
        escaped = re.escape(token)
        rx = re.compile(r"[#.]" + escaped + r"(?![\w-])|\[\s*(?:id|class)\s*[~|^$*]?=\s*[\"']?[^\"'\]]*(?<![\w-])" + escaped + r"(?![\w-])")
        if any(rx.search(lit) for lit in literals):
            return True
    return False


def dynamic_selector_hint(texts) -> bool:
    """True if a spec text builds a selector at run time (see DYNAMIC_SELECTOR): a conservative 'cannot tell' flag, reported beside
    the selector-hygiene table; it does not change references_renamed_selector."""
    return any(DYNAMIC_SELECTOR.search(t) for t in texts if t)


ATTR_TOKEN_SOURCES = (re.compile(r"""\b(?:class|id)\s*=\s*"([^"]*)\""""), re.compile(r"""className\s*=\s*([^;\n]+)"""),
                      re.compile(r"""classList\.\w+\(([^)]*)\)"""), re.compile(r"""\.id\s*=\s*([^;\n]+)"""),
                      re.compile(r"""\b(?:class|id)\s*=\s*\\?['"]([^'"]*)"""))
LITERAL_WORDS = re.compile(r"""["'`]([^"'`]*)["'`]""")


def attribute_tokens(text) -> set:
    """Ids and class names the markup or the script assigns: values of class=/id= attributes and the string literals on the right of
    className=, classList.*(...) and .id=."""
    out = set()
    for rx in ATTR_TOKEN_SOURCES:
        for match in rx.finditer(text):
            value = match.group(1)
            parts = LITERAL_WORDS.findall(value) if rx is not ATTR_TOKEN_SOURCES[0] and rx is not ATTR_TOKEN_SOURCES[4] else [value]
            for part in parts or [value]:
                out.update(w for w in re.split(r"\s+", part) if re.fullmatch(r"[A-Za-z][\w-]*", w))
    return out


def removed_selector_tokens(edits, manifest_tokens=()) -> list:
    """Ids and classes the refactor removes: the engine manifest's tokens (an id or class occurring in a find text but not in its
    replacement as a substring) united with the attribute-assigned tokens present in a find text and absent as a whole token from its
    replacement. The union fixes the manifest's substring blind spot (a class `deck` renamed to `deck__item` counts as renamed)."""
    removed = set(manifest_tokens)
    for edit in edits:
        removed |= attribute_tokens(edit["find"]) - attribute_tokens(edit["replace"])
    return sorted(removed)
