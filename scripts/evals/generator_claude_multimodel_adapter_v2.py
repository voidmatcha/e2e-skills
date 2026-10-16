#!/usr/bin/env python3
"""Claude Code transport for generator-multimodel-v2-claude (host process, real project skills). Apache-2.0.

Imports the frozen v1 adapter (generator_claude_multimodel_adapter.py) UNCHANGED and overrides only what has to change:

  * skills: arm B installs the e2e-reviewer and arm C the playwright-test-generator and e2e-reviewer as REAL project skills
    (`.claude/skills/<name>/` inside the cell project, staged by the runner before the baseline commit). B and C keep the Skill
    tool and drop `--disable-slash-commands`; arm A keeps `--disable-slash-commands` and has no skills at all.
  * isolation: the contract is verified on EVERY `system/init` event of a call (a background subagent produces a second one),
    for the intended skills, agents, tools, MCP servers and plugins of the arm; a violating call is an infrastructure error.
  * generation-phase port split: arm A's MCP server gets its own copy of the project's MCP config with one extra env variable
    (E2E_APP_PORT) so its app server and the parent's `playwright test` never share a port. The scoring harness is not touched.
  * compliance and fidelity are computed from the full raw stream-json (no command truncation), including subagent events,
    and cost comes from `modelUsage` (session total including sub-agents) instead of the last turn's `usage`. The call record keeps the
    full final message, and a cross-check compares `modelUsage` with the tokens visible in the stream (subagent messages included).
  * strict fidelity (the lessons of the Codex v3 harness): a generator tool call counts only when it COMPLETED (its tool_result is
    present and not flagged is_error); attempted-but-failed or denied calls are recorded separately (`*_attempted`, `mcp_tools_denied`).
    `generator_surface_completed` is the Codex v3 `official-tool` evidence (a completed generator_* or browser_* call of the
    `playwright-test` server, parent or subagent) and `minimal_generator_use` marks the weakest way to satisfy it (no browser call).

Nothing here starts a model call unless `call_model` is invoked by the runner under `--allow-live`.
"""
from __future__ import annotations

import json
import os
import posixpath
import re
import signal
import subprocess
import sys
import time
import uuid
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import generator_claude_multimodel_adapter as v1a  # noqa: E402  (frozen v1 adapter, imported unchanged)

ROOT, HOME, CLAUDE_BIN = v1a.ROOT, v1a.HOME, v1a.CLAUDE_BIN
ARM_A, ARM_B, ARM_C = "official-generator", "official+reviewer", "ours-2.0.1"
ARM_LINES: dict = {}                       # set by the runner from the frozen prompt text
SKILLS_BY_ARM = {ARM_A: (), ARM_B: ("e2e-reviewer",), ARM_C: ("playwright-test-generator", "e2e-reviewer")}
BASE_TOOLS_V2 = v1a.BASE_TOOLS + ",Skill"
PORT_ENV = "E2E_APP_PORT"                  # read by the generation-phase app and config only; never set for the parent process
MCP_PORT_SHIFT = 20000                     # the MCP server's app port = the project's port + this shift
BUNDLED_SKILLS_ALLOWED: set = set()        # bundled (non-project) skills a live init may list; filled by the runner from the protocol
GENERATOR_REFS = ("best-practices.md", "scenario-design.md", "code-rules.md", "verification-rules.md", "exploration-preflight.md",
                  "conventions-template.md", "imported-test-cases.md", "playwright-agents.md", "recommended-lint.md")
HOT_REFS = ("best-practices.md", "scenario-design.md", "code-rules.md", "verification-rules.md")
MIN_HOT_REFS_FOR_TREATED = 2
STORED_COMMAND_CAP = 8000                  # storage cap only; every counter below is computed on the full command
PORT_CONFLICT_RE = re.compile(r"is already used|EADDRINUSE|address already in use", re.I)
MCP_PREFIX = "mcp__playwright-test__"
BROWSER_MUTATING = ("browser_click", "browser_type", "browser_fill_form", "browser_navigate", "browser_navigate_back", "browser_press_key",
                    "browser_select_option", "browser_drag", "browser_hover", "browser_file_upload", "browser_handle_dialog",
                    "browser_evaluate", "browser_run_code")
DENIED_RE = re.compile(r"permission|not allowed|denied|requires approval|not been granted|haven't granted", re.I)
PLAYWRIGHT_TEST_RE = re.compile(r"playwright(?:\"|')?\s+test\b|playwright\s+test\b")                # MENTION only (recorded, never a step)
EXPLORATION_RE = re.compile(r"playwright\s+cli|playwright-cli|agent-browser|run-raw-aria-snapshot")        # MENTION only
BASH_EDIT_RE = re.compile(r"sed\s+-i|perl\s+-p?i|\btee\s|>>?\s*\S*tests/|python3?\s+-?\s*<<|open\([^)]*['\"]w['\"]|\bcat\s*>\s*|\bmv\s+\S+\s+\S*tests/")
REVIEW_PROMPT_RE = re.compile(r"review|e2e-reviewer|\bV6\b", re.I)                                          # loose: recorded as review_mentions_after_write
REVIEWER_NAMED_RE = re.compile(r"e2e-reviewer|\bV6\b", re.I)                                               # strict: the spawn names the reviewer skill or the V6 gate
SPEC_BASH_WRITE_RE = re.compile(r"(?:\bcat\s*>>?\s*|\btee\s+(?:-a\s+)?|>>?\s*)\S*tests/\S+\.(?:spec|test)\.|open\([^)]*['\"]w['\"]")
SPEC_PATH_RE = re.compile(r"(?:^|/)tests/[^\s'\"]*\.(?:spec|test)\.(?:mjs|cjs|js|ts|mts)$")
SHELLS = ("bash", "sh", "zsh", "dash", "ksh")
INTERPRETERS = ("python", "python3", "node", "ruby", "perl")
READ_VERBS = ("cat", "sed", "head", "tail", "less", "more", "bat", "nl", "awk", "grep", "egrep", "fgrep", "rg", "tac", "cut", "strings", "xxd", "od")
SKIP_PREFIX = ("do", "then", "else", "elif", "while", "until", "if", "!", "{", "}", "time", "nohup", "command", "builtin", "exec", "sudo", "nice", "stdbuf", "caffeinate")
ASSIGNMENT_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*=")
HEREDOC_RE = re.compile(r"<<(?!<)-?\s*(['\"]?)([A-Za-z_][\w]*)\1")


# ------------------------------------------------------------------------------------------------ command and environment

def deny_rules():
    """v1's deny list plus the checkout this runner is started from (so a renamed worktree is covered without a home path)."""
    extra = [f"Read({ROOT}/{d}/**)" for d in ("benchmarks", "skills", "docs")]
    return list(v1a.DENY) + [rule for rule in extra if rule not in v1a.DENY]


def settings_json():
    return json.dumps({"permissions": {"deny": deny_rules()}}, sort_keys=True)


def _replace_value(cmd, flag, value):
    out = list(cmd)
    out[out.index(flag) + 1] = value
    return out


def allowed_tools(arm):
    if arm == ARM_A:
        return v1a.OFFICIAL_ALLOWED
    return v1a.BASE_TOOLS + "," + ",".join(f"Skill({name})" for name in SKILLS_BY_ARM[arm])


def command(arm, model, schema, budget, work, mcp_config=None):
    """The v1 argv with the minimum set of changes. Built from the frozen v1 `command` so any other flag stays byte-identical."""
    cmd = v1a.command(arm, model, schema, budget, work)
    cmd = _replace_value(cmd, "--settings", settings_json())
    if arm == ARM_A:
        if mcp_config is None:
            raise ValueError("arm A needs the MCP config path")
        return _replace_value(cmd, "--mcp-config", str(mcp_config))
    if arm not in SKILLS_BY_ARM:
        raise ValueError("unknown arm " + str(arm))
    cmd.remove("--disable-slash-commands")                     # B and C use the installed project skills
    cmd = _replace_value(cmd, "--setting-sources", "project")  # project skills live under .claude/skills of the cell project
    cmd = _replace_value(cmd, "--tools", BASE_TOOLS_V2)
    return _replace_value(cmd, "--allowedTools", allowed_tools(arm))


def build_env(model, base_env=None):
    """Process environment for one call. PORT_ENV is removed so the parent's runs always use the config default port."""
    drop = ("CLAUDECODE", "CLAUDE_CODE_ENTRYPOINT", PORT_ENV)
    env = {k: v for k, v in (os.environ if base_env is None else base_env).items() if k not in drop}
    env.update(CLAUDE_CODE_DISABLE_AUTO_MEMORY="1", CLAUDE_CODE_SUBAGENT_MODEL=model)
    return env


def app_port_of(project):
    """The project's app port, read from the (generation-phase) app.mjs the runner staged."""
    match = re.search(r"const PORT = (?:Number\(process\.env\.%s \?\? )?(\d+)" % PORT_ENV, (Path(project) / "app.mjs").read_text())
    if not match:
        raise ValueError("cannot read the app port from app.mjs")
    return int(match.group(1))


def write_mcp_config(project, work, app_port):
    """A copy of the project's `.mcp.json` outside the project with E2E_APP_PORT set for the MCP server only."""
    source = json.loads((Path(project) / ".mcp.json").read_text())
    servers = source.get("mcpServers") or {}
    if set(servers) != {"playwright-test"}:
        raise ValueError("unexpected MCP servers in .mcp.json: " + ",".join(sorted(servers)))
    config = json.loads(json.dumps(source))
    entry = config["mcpServers"]["playwright-test"]
    entry["env"] = {**(entry.get("env") or {}), PORT_ENV: str(app_port + MCP_PORT_SHIFT)}
    path = Path(work) / "mcp.json"
    path.write_text(json.dumps(config, indent=2) + "\n")
    return path


# ------------------------------------------------------------------------------------------------ init-event verification

def _bare(value):
    return value.get("name") if isinstance(value, dict) else value


def check_init(arm, init, model=None, project=None, bundled_allowed=None):
    """Contract violations of ONE system/init event (empty list = the arm is configured as specified)."""
    bundled = set(BUNDLED_SKILLS_ALLOWED if bundled_allowed is None else bundled_allowed)
    problems = []
    if not isinstance(init, dict):
        return ["no system/init event"]
    skills = [str(_bare(s)) for s in init.get("skills") or []]
    agents = set(init.get("agents") or [])
    servers = {s.get("name"): s.get("status") for s in (init.get("mcp_servers") or [])}
    tools = set(init.get("tools") or [])
    plugins = init.get("plugins") or []
    intended = set(SKILLS_BY_ARM.get(arm, ()))
    if arm not in SKILLS_BY_ARM:
        return ["unknown arm " + str(arm)]
    if model and str(init.get("model") or "").split("[")[0] != model:
        problems.append(f"init model {init.get('model')!r} is not the requested {model!r}")
    if project is not None and init.get("cwd") and "<work>" not in str(init.get("cwd")):
        if Path(str(init["cwd"])).resolve() != Path(project).resolve():
            problems.append("init cwd is not the cell project")
    if any(_bare(p) is None or (isinstance(p, dict) and p.get("path") != "builtin") for p in plugins):
        problems.append("a non-builtin plugin is loaded: " + ",".join(str(_bare(p)) for p in plugins if isinstance(p, dict) and p.get("path") != "builtin"))
    missing, extra = sorted(intended - set(skills)), sorted(set(skills) - intended - bundled)
    if missing:
        problems.append("intended skills not listed: " + ",".join(missing))
    if extra:
        problems.append("unintended skills listed: " + ",".join(extra)[:200])
    if "Skill" in tools and arm == ARM_A:
        problems.append("arm A has the Skill tool")
    if arm == ARM_A:
        if skills:
            problems.append("arm A lists skills: " + ",".join(skills)[:200])
        if init.get("slash_commands"):
            problems.append("arm A lists slash commands")
        if "playwright-test-generator" not in agents:
            problems.append("official generator subagent not loaded")
        if servers != {"playwright-test": "connected"}:
            problems.append(f"mcp servers differ: {servers}")
        if tools & {"Write", "Edit", "NotebookEdit", "WebFetch", "WebSearch"}:
            problems.append("arm A parent has write or web tools")
        gen_tools = {"mcp__playwright-test__generator_setup_page", "mcp__playwright-test__generator_write_test"}
        if not gen_tools <= tools:
            problems.append("generator MCP tools missing from the tool list")
    else:
        if {a for a in agents if a.startswith("playwright-test-")}:
            problems.append("official playwright agents visible outside arm A")
        if servers or any(t.startswith("mcp__") for t in tools):
            problems.append(f"unexpected mcp servers or tools: {servers}")
        if {"WebFetch", "WebSearch"} & tools:
            problems.append("web tools visible")
        if not {"Write", "Edit", "Skill"} <= tools:
            problems.append("Write, Edit or Skill missing from the tool list")
    return problems


def check_isolation(arm, inits, model=None, project=None, bundled_allowed=None):
    """Verify every init event of a call. `inits` is the list of system/init events in stream order."""
    if not inits:
        return ["no system/init event"]
    out = []
    for i, init in enumerate(inits):
        out += [(f"[init {i + 1}] " if len(inits) > 1 else "") + p for p in check_init(arm, init, model, project, bundled_allowed)]
    return out


# ------------------------------------------------------------------------------------------------ shell command parsing

def strip_heredocs(text):
    """Remove here-document bodies (the lines between `<<WORD` and its terminator): their content is data, never commands."""
    out, pending = [], []
    for line in str(text).split("\n"):
        if pending:
            if line.strip() == pending[0]:
                pending.pop(0)
            continue
        out.append(line)
        pending.extend(m.group(2) for m in HEREDOC_RE.finditer(line))
    return "\n".join(out)


def split_simple_commands(text):
    """Quote-aware split of a shell command text into simple commands (lists of words). Separators: ; newline && || | & ( ) `...` $( .
    Quotes are removed from the words; comments are skipped; here-document bodies are dropped. Not a full shell: no expansion, no
    functions, no loops over values (a command inside a variable or a `for` list is not seen)."""
    text = strip_heredocs(text).replace("\\\n", " ")
    commands, words, word, started, quote = [], [], [], False, None
    i, n = 0, len(text)

    def end_word():
        nonlocal word, started
        if started:
            words.append("".join(word))
        word, started = [], False

    def end_command():
        nonlocal words
        end_word()
        if words:
            commands.append(words)
        words = []
    while i < n:
        ch = text[i]
        if quote == "'":
            if ch == "'":
                quote = None
            else:
                word.append(ch)
        elif quote == '"':
            if ch == "\\" and i + 1 < n:
                word.append(text[i + 1])
                i += 1
            elif ch == '"':
                quote = None
            else:
                word.append(ch)
        elif ch in "'\"":
            quote, started = ch, True
        elif ch == "\\" and i + 1 < n:
            word.append(text[i + 1])
            started = True
            i += 1
        elif ch == "#" and not started:
            while i < n and text[i] != "\n":
                i += 1
            continue
        elif ch in " \t\r":
            end_word()
        elif ch in ";\n`()":
            end_command()
        elif ch == "$" and text[i + 1:i + 2] == "(":
            end_command()
            i += 1
        elif ch == "|" or (ch == "&" and text[i - 1:i] not in (">", "<") and text[i + 1:i + 2] != ">"):
            end_command()
            if text[i + 1:i + 2] == ch:
                i += 1
        else:
            word.append(ch)
            started = True
        i += 1
    end_command()
    return commands


def _skip_flags(words, pair_flags=()):
    i = 0
    while i < len(words) and words[i].startswith("-") and words[i] != "-":
        i += 2 if words[i] in pair_flags else 1
    return words[i:]


def unwrap_command(words):
    """The program and arguments of a simple command after leading assignments and transparent wrappers (env, timeout, time, nohup,
    sudo, command, npx and friends, `npm|pnpm|yarn|bun exec`). Reserved words that start a command (do, then, ...) are skipped."""
    w = list(words)
    while w:
        head, base = w[0], posixpath.basename(w[0])
        if ASSIGNMENT_RE.match(head):
            w = w[1:]
        elif head in SKIP_PREFIX or base in SKIP_PREFIX:
            w = _skip_flags(w[1:])
        elif base == "env":
            w = _skip_flags(w[1:], ("-u", "-S", "-C"))
            while w and ASSIGNMENT_RE.match(w[0]):
                w = w[1:]
        elif base == "timeout":
            w = _skip_flags(w[1:], ("-k", "-s", "--signal", "--kill-after"))[1:]
        elif base in ("npx", "pnpx", "bunx"):
            w = _skip_flags(w[1:])
        elif base in ("npm", "pnpm", "yarn", "bun") and len(w) > 1 and w[1] in ("exec", "x", "dlx"):
            w = _skip_flags(w[2:])
        elif base == "yarn" and len(w) > 1:
            w = _skip_flags(w[1:])
        else:
            break
    return w


def describe_invocation(argv):
    """(kind, name, rest): `prog` for an ordinary program, `script` when a shell or interpreter runs a script file, `nested` for
    `bash -c '<text>'` (name is then the text). name is the program or script path, rest the remaining words."""
    if not argv:
        return ("empty", "", [])
    base = posixpath.basename(argv[0])
    if base in SHELLS:
        if any(w.startswith("-") and not w.startswith("--") and "n" in w[1:] for w in argv[1:3]):
            return ("syntax_check", argv[0], argv[1:])      # `bash -n script` parses without running it
        for i, word in enumerate(argv[1:], 1):
            if word.startswith("-") and not word.startswith("--") and "c" in word[1:] and i + 1 < len(argv):
                return ("nested", argv[i + 1], argv[i + 2:])
        rest = _skip_flags(argv[1:])
        return ("script", rest[0], rest[1:]) if rest else ("prog", argv[0], [])
    if base in INTERPRETERS:
        rest = _skip_flags(argv[1:], ("-e", "-c", "-m", "-r"))
        return ("script", rest[0], rest[1:]) if rest and rest[0] != "-" else ("prog", argv[0], argv[1:])
    return ("prog", argv[0], argv[1:])


class ShellWalker:
    """Walk the simple commands of Bash tool calls in stream order, tracking the working directory (the Bash tool's shell persists
    it between calls). One walker per stream; the state is kept per issuing agent (parent or subagent)."""

    def __init__(self):
        self.cwd = {}

    def walk(self, text, agent=None, depth=0):
        """Yield (invocation, raw words, cwd) per simple command; recurses into `bash -c '...'` (depth 3)."""
        for words in split_simple_commands(text):
            argv = unwrap_command(words)
            if not argv:
                continue
            kind, name, rest = describe_invocation(argv)
            if posixpath.basename(argv[0]) == "cd" and kind == "prog":
                target = (_skip_flags(argv[1:]) or ["~"])[0]
                base = self.cwd.get(agent, "")
                if target[:1] in ("~", "$", "-"):
                    self.cwd[agent] = ""
                else:
                    self.cwd[agent] = posixpath.normpath(target if target.startswith("/") or not base else posixpath.join(base, target))
                continue
            if kind == "nested" and depth < 3:
                yield from self.walk(name, agent, depth + 1)
                continue
            yield (kind, name, rest, argv), words, self.cwd.get(agent, "")


def _script_base(kind, name):
    return posixpath.basename(name) if kind in ("script", "prog") else ""


def classify_invocation(invocation):
    """The harness-relevant kinds of ONE executed simple command: scan, preflight, playwright_test, exploration, start_server.
    A word that only appears as an argument of cat, ls, grep, echo and the like is not an execution."""
    kind, name, rest, argv = invocation
    base = _script_base(kind, name)
    out = set()
    if base == "scan.sh":
        out.add("scan")
    if base in ("run-preflight-target.sh", "preflight_target.py"):
        out.add("preflight")
    if base.startswith("run-raw-aria-snapshot") or base in ("playwright-cli", "agent-browser"):
        out.add("exploration")
    if base == "playwright" and rest[:1] == ["cli"]:
        out.add("exploration")
    if base == "playwright" and rest[:1] == ["test"]:
        out.add("playwright_test")
    if posixpath.basename(argv[0]) == "node" and base == "app.mjs":
        out.add("start_server")
    return out


def _read_targets(invocation, cwd):
    """Resolved path words a read verb (cat, sed, head, grep ...) is given. Relative paths are joined to the tracked working directory."""
    kind, name, rest, argv = invocation
    if kind != "prog" or posixpath.basename(argv[0]) not in READ_VERBS:
        return []
    out = []
    for word in argv[1:]:
        if word.startswith("-") or word in ("", "-"):
            continue
        absolute = word.startswith(("/", "$", "~"))
        out.append(word if absolute or not cwd else posixpath.normpath(posixpath.join(cwd, word)))
    return out


def bash_reference_reads(invocations):
    """(generator reference files, e2e-reviewer reference files, skill SKILL.md files) read through Bash read verbs. A reference file
    counts when its path names the skill directory or starts with a shell variable, or when it is resolved through a `cd` into the skill
    directory; a glob (`*.md`, `*`) in the skill directory counts as all nine generator references."""
    generator, reviewer, skill_md = set(), set(), set()
    for invocation, _words, cwd in invocations:
        for path in _read_targets(invocation, cwd):
            parts = path.split("/")
            base = parts[-1]
            in_generator = "playwright-test-generator" in parts[:-1]
            if base in GENERATOR_REFS and (in_generator or path.startswith("$")):
                generator.add(base)
            elif base in ("*.md", "*") and in_generator:
                generator |= set(GENERATOR_REFS)
            if base == "SKILL.md" and len(parts) > 1 and parts[-2] in ("playwright-test-generator", "e2e-reviewer"):
                skill_md.add(parts[-2])
            if "e2e-reviewer" in parts[:-1] and "references" in parts[:-1] and base.endswith(".md"):
                reviewer.add(base)
    return generator, reviewer, skill_md


# ------------------------------------------------------------------------------------------------ stream analysis

def _content(event):
    content = (event.get("message") or {}).get("content")
    return content if isinstance(content, list) else []


def tool_uses(events):
    """Yield (stream index, event, block) for every tool_use block, parent and subagent alike, in stream order."""
    for index, event in enumerate(events):
        if event.get("type") == "assistant":
            for block in _content(event):
                if isinstance(block, dict) and block.get("type") == "tool_use":
                    yield index, event, block


def result_texts(events):
    """tool_use_id -> concatenated text of its tool_result."""
    out = {}
    for event in events:
        if event.get("type") != "user":
            continue
        for block in _content(event):
            if isinstance(block, dict) and block.get("type") == "tool_result":
                body = block.get("content")
                if isinstance(body, list):
                    body = "\n".join(str(b.get("text", "")) for b in body if isinstance(b, dict))
                out[block.get("tool_use_id")] = str(body or "")
    return out


def result_errors(events):
    """tool_use_id -> True if its tool_result is flagged is_error (a denied or failed call)."""
    out = {}
    for event in events:
        if event.get("type") == "user":
            for block in _content(event):
                if isinstance(block, dict) and block.get("type") == "tool_result":
                    out[block.get("tool_use_id")] = bool(block.get("is_error"))
    return out


def skill_name_of(inp):
    for key in ("skill", "name", "skill_name", "command"):
        if isinstance(inp.get(key), str) and inp[key].strip():
            return inp[key].strip().lstrip("/")
    return ""


def _path_of(name, inp):
    return str(inp.get("file_path") or inp.get("path") or "") if name in ("Read", "Write", "Edit", "Grep", "Glob") else ""


def _is_spec_write(name, inp):
    path = _path_of(name, inp)
    return name in ("Write", "Edit") and bool(SPEC_PATH_RE.search(path.replace("\\", "/"))) and not path.endswith("seed.spec.ts")


def _tool_ref_hits(name, inp):
    """Generator reference files read through the Read tool (absolute path inside the skill directory)."""
    if name != "Read":
        return set()
    path = _path_of(name, inp)
    return {f for f in GENERATOR_REFS if path.endswith("/playwright-test-generator/" + f)}


def analyze_events(events, arm, project=None, work=None, sanitize=None):
    """Everything the harness records about what the call did, from the raw stream (parent and subagents, no truncation).

    Steps are counted only for EXECUTED commands: the program or script of a simple shell command (after assignments and wrappers such
    as env, timeout, npx) is scan.sh, run-preflight-target.sh or `playwright test`. A word that only appears as an argument of cat, ls,
    grep, echo or inside a here-document is a MENTION and is recorded in the separate `*_mentions` fields. A reference file counts as
    read only through the Read tool or a read verb (cat, sed, head, grep ...), resolving a `cd` of the same or an earlier Bash call."""
    sanitize = sanitize or (lambda text, extra=(): text)
    results, errors, walker = result_texts(events), result_errors(events), ShellWalker()
    counts, children = {}, {}
    cmds, reads, writes, mcp, spawns, skill_calls, outside = [], [], [], {}, [], [], set()
    mcp_done, mcp_denied = {}, 0
    skill_errors = 0
    ref_tool, ref_bash, rev_refs, skill_md_bash, mention_refs = set(), set(), set(), set(), set()
    first_spec_write = None
    steps = {"preflight": 0, "exploration": 0, "scan_sh": 0, "scan_pinned": 0, "pw_test": 0, "pw_test_before_write": 0,
             "pw_test_after_write": 0, "bash_edits": 0, "review_agents_after_write": 0, "review_mentions_after_write": 0,
             "child_reviewer_skill_after_write": 0, "server_started_by_model": 0, "port_conflicts": 0, "repeat_each": 0, "git_status": 0,
             "scan_mentions": 0, "pw_test_mentions": 0, "preflight_mentions": 0, "exploration_mentions": 0}
    work_s, home_s = str(work or ""), str(HOME)
    for index, event, block in tool_uses(events):
        name, inp = block.get("name", "?"), block.get("input") or {}
        agent = event.get("parent_tool_use_id")
        counts[name] = counts.get(name, 0) + 1
        if agent:
            children[name] = children.get(name, 0) + 1
        if name in ("Agent", "Task"):
            blob = str(inp.get("description") or "") + " " + str(inp.get("prompt") or "")
            named = bool(REVIEWER_NAMED_RE.search(blob)) or "reviewer" in str(inp.get("subagent_type") or "").lower()
            spawns.append({"type": inp.get("subagent_type"), "description": str(inp.get("description") or "")[:200],
                           "review_like": bool(REVIEW_PROMPT_RE.search(blob)), "reviewer_named": named,
                           "stream_index": index, "after_spec_write": first_spec_write is not None})
            if first_spec_write is not None:
                steps["review_mentions_after_write"] += spawns[-1]["review_like"]
                steps["review_agents_after_write"] += named
        elif name == "Skill":
            skill_calls.append(skill_name_of(inp))
            skill_errors += bool(errors.get(block.get("id")))
            if agent and skill_name_of(inp) == "e2e-reviewer" and first_spec_write is not None:
                steps["child_reviewer_skill_after_write"] += 1
        elif name.startswith("mcp__"):
            mcp[name] = mcp.get(name, 0) + 1
            if block.get("id") in errors and not errors[block.get("id")]:
                mcp_done[name] = mcp_done.get(name, 0) + 1                       # completed: a result is present and is not an error
            elif errors.get(block.get("id")) and name.startswith(MCP_PREFIX) and DENIED_RE.search(results.get(block.get("id"), "")):
                mcp_denied += 1
        if name == "Read":
            reads.append(_path_of(name, inp))
        if name in ("Write", "Edit"):
            writes.append(_path_of(name, inp))
            if first_spec_write is None and _is_spec_write(name, inp):
                first_spec_write = index
        ref_tool |= _tool_ref_hits(name, inp)
        text = str(inp.get("command", "")) if name == "Bash" else ""
        if name == "Read" and "/e2e-reviewer/references/" in _path_of(name, inp):
            rev_refs.add(Path(_path_of(name, inp)).name)
        if name == "Bash":
            cmds.append(text)
            invocations = list(walker.walk(text, agent))
            gen_refs, reviewer_refs, md = bash_reference_reads(invocations)
            ref_bash |= gen_refs
            rev_refs |= reviewer_refs
            skill_md_bash |= md
            mention_refs |= {f for f in GENERATOR_REFS if f in text}
            kinds = [classify_invocation(inv) for inv, _w, _c in invocations]
            steps["scan_mentions"] += "scan.sh" in text
            steps["preflight_mentions"] += "run-preflight-target.sh" in text or "preflight_target.py" in text
            steps["exploration_mentions"] += bool(EXPLORATION_RE.search(text))
            steps["pw_test_mentions"] += bool(PLAYWRIGHT_TEST_RE.search(text))
            steps["preflight"] += sum("preflight" in k for k in kinds)
            steps["exploration"] += sum("exploration" in k for k in kinds)
            scans = [(inv, words) for (inv, words, _c), k in zip(invocations, kinds) if "scan" in k]
            steps["scan_sh"] += len(scans)
            steps["scan_pinned"] += sum("E2E_SMELL_ALLOW_PROJECT_ESLINT=0" in words for _i, words in scans)
            steps["server_started_by_model"] += sum("start_server" in k for k in kinds)
            if BASH_EDIT_RE.search(text) and re.search(r"tests/", text):
                steps["bash_edits"] += 1
                if first_spec_write is None and SPEC_BASH_WRITE_RE.search(text):
                    first_spec_write = index   # a spec written through Bash (heredoc, tee) is a spec write for the baseline/targeted split
            for (inv, words, _c), k in zip(invocations, kinds):
                if "playwright_test" in k:
                    steps["pw_test"] += 1
                    steps["pw_test_before_write" if first_spec_write is None else "pw_test_after_write"] += 1
                    steps["repeat_each"] += "--repeat-each" in words
                    if PORT_CONFLICT_RE.search(results.get(block.get("id"), "")):
                        steps["port_conflicts"] += 1
            steps["git_status"] += "git status" in text
            for match in re.findall(re.escape(home_s) + r"/[^\s'\"`;)|&]*", text) if home_s != "/" else []:
                if not (work_s and match.startswith(work_s)):
                    outside.add(sanitize(match, (work_s,) if work_s else ()))
        else:
            value = _path_of(name, inp)
            if isinstance(value, str) and value.startswith(home_s) and not (work_s and value.startswith(work_s)):
                outside.add(sanitize(value, (work_s,) if work_s else ()))
    any_conflict = sum(bool(PORT_CONFLICT_RE.search(t)) for t in results.values())
    last_result = next((e for e in reversed(events) if e.get("type") == "result"), None) or {}
    skill_md = {s for s in ("playwright-test-generator", "e2e-reviewer") if any(r.endswith(f"/{s}/SKILL.md") for r in reads)} | skill_md_bash
    gen_calls = lambda suffix: mcp_done.get(MCP_PREFIX + "generator_" + suffix, 0)          # COMPLETED calls (strict)
    gen_attempted = lambda suffix: mcp.get(MCP_PREFIX + "generator_" + suffix, 0)
    browser = sum(v for k, v in mcp_done.items() if k.startswith(MCP_PREFIX + "browser_"))
    browser_attempted = sum(v for k, v in mcp.items() if k.startswith(MCP_PREFIX + "browser_"))
    browser_mutating = sum(v for k, v in mcp_done.items() if k.startswith(MCP_PREFIX) and k[len(MCP_PREFIX):] in BROWSER_MUTATING)
    surface = sum(v for k, v in mcp_done.items() if k.startswith((MCP_PREFIX + "generator_", MCP_PREFIX + "browser_")))
    intended = set(SKILLS_BY_ARM.get(arm, ()))
    review_agents = steps["review_agents_after_write"] or (1 if steps["child_reviewer_skill_after_write"] else 0)
    fidelity = {
        "arm": arm, "stream_tool_uses": sum(counts.values()), "child_tool_uses": sum(children.values()),
        "init_events": sum(1 for e in events if e.get("type") == "system" and e.get("subtype") == "init"),
        "result_events": sum(1 for e in events if e.get("type") == "result"),
        "agent_spawns": len(spawns), "agent_types": sorted({str(s["type"]) for s in spawns}),
        "skill_tool_calls": sorted(skill_calls), "unintended_skill_calls": sorted({c for c in skill_calls if c not in intended}),
        "skill_call_errors": skill_errors, "skill_md_read": sorted(skill_md),
        "generator_skill_loaded": "playwright-test-generator" in skill_calls or "playwright-test-generator" in skill_md,
        "reviewer_skill_loaded": "e2e-reviewer" in skill_calls or "e2e-reviewer" in skill_md,
        "generator_refs_via_read_tool": sorted(ref_tool), "generator_refs_via_bash": sorted(ref_bash),
        "generator_refs_read": sorted(ref_tool | ref_bash), "hot_refs_read": sorted((ref_tool | ref_bash) & set(HOT_REFS)),
        "generator_refs_mentioned": sorted(mention_refs), "hot_refs_mentioned": sorted(mention_refs & set(HOT_REFS)),
        "reviewer_refs_read": sorted(rev_refs),
        "preflight_runs": steps["preflight"], "exploration_runs": steps["exploration"] + browser,
        "scan_sh_runs": steps["scan_sh"], "scan_sh_pinned_runs": steps["scan_pinned"],
        "baseline_runs": steps["pw_test_before_write"], "targeted_runs": steps["pw_test_after_write"],
        "playwright_test_runs": steps["pw_test"], "repeat_each_runs": steps["repeat_each"],
        "independent_review_agents": review_agents, "reviewer_named_spawns_after_write": steps["review_agents_after_write"],
        "child_reviewer_skill_calls_after_write": steps["child_reviewer_skill_after_write"],
        "review_mentions_after_write": steps["review_mentions_after_write"],
        "scan_sh_mentions": steps["scan_mentions"], "preflight_mentions": steps["preflight_mentions"],
        "exploration_mentions": steps["exploration_mentions"], "playwright_test_mentions": steps["pw_test_mentions"],
        "spec_write_or_edit_calls": sum(1 for p in writes if SPEC_PATH_RE.search(p.replace("\\", "/"))),
        "write_or_edit_calls": len(writes), "bash_edit_calls": steps["bash_edits"],
        "generator_setup_page_calls": gen_calls("setup_page"), "generator_read_log_calls": gen_calls("read_log"),
        "generator_write_test_calls": gen_calls("write_test"), "browser_tool_calls": browser,
        "generator_setup_page_attempted": gen_attempted("setup_page"), "generator_write_test_attempted": gen_attempted("write_test"),
        "browser_tool_attempted": browser_attempted, "browser_mutating_calls": browser_mutating,
        "generator_surface_completed": surface, "minimal_generator_use": bool(surface) and browser == 0, "mcp_tools_denied": mcp_denied,
        "planner_or_healer_used": any(str(s["type"]).startswith("playwright-test-") and str(s["type"]) != "playwright-test-generator" for s in spawns),
        "generator_spawned": any(s["type"] == "playwright-test-generator" for s in spawns),
        "port_conflicts_in_playwright_test": steps["port_conflicts"], "port_conflict_results_any": any_conflict,
        "server_started_by_model": steps["server_started_by_model"],
        "subagent_stats": last_result.get("subagent_stats"), "stop_reason": last_result.get("terminal_reason")}
    fidelity.update(treatment_flags(arm, fidelity))
    full = [sanitize(c, (work_s,) if work_s else ()) for c in cmds]
    capped = [c if len(c) <= STORED_COMMAND_CAP else c[:STORED_COMMAND_CAP] for c in full]
    outside_tests = sorted({w for w in writes if w and not (SPEC_PATH_RE.search(w.replace("\\", "/")) or "/tests/" in w or w.startswith("tests/"))})
    return {
        "evidence_source": "claude-stream-json-full", "tool_counts": counts, "child_tool_counts": children,
        "agent_spawns": len(spawns), "agent_spawn_detail": spawns, "agent_spawns_verification": "tool_use-count",
        "mcp_tool_calls": mcp, "mcp_tool_calls_completed": mcp_done, "official_write_test_calls": gen_calls("write_test"),
        "read_generator_skill": "playwright-test-generator" in skill_md, "read_reviewer_skill": "e2e-reviewer" in skill_md,
        "read_app_source": any(r.endswith("/app.mjs") or r == "app.mjs" for r in reads),
        "generator_reference_files_read": fidelity["generator_refs_read"],
        "playwright_test_runs": steps["pw_test"], "repeat_each_runs": steps["repeat_each"], "scanner_runs": steps["scan_sh"],
        "scanner_mentions": steps["scan_mentions"],
        "exploration_commands": steps["exploration"], "git_status_calls": steps["git_status"],
        "write_or_edit_calls": len(writes), "writes_outside_tests": [sanitize(w, (work_s,) if work_s else ()) for w in outside_tests],
        "bash_commands": capped, "bash_commands_over_cap": sum(len(c) > STORED_COMMAND_CAP for c in full),
        "bash_command_max_chars": max((len(c) for c in full), default=0),
        "home_paths_touched_outside_work": sorted(outside)[:40], "fidelity": fidelity}


def treatment_flags(arm, f):
    """invoked / treated per arm, defined before any v2 data exists (see the protocol's fidelity section)."""
    if arm == ARM_A:
        invoked = f["generator_setup_page_calls"] >= 1 or f["generator_write_test_calls"] >= 1
        treated = f["generator_setup_page_calls"] >= 1 and f["generator_write_test_calls"] >= 1
    elif arm == ARM_B:
        invoked = f["reviewer_skill_loaded"]
        treated = f["reviewer_skill_loaded"] and f["scan_sh_runs"] >= 1 and f["playwright_test_runs"] >= 1
    else:
        invoked = f["generator_skill_loaded"]
        treated = (f["generator_skill_loaded"] and len(f["hot_refs_read"]) >= MIN_HOT_REFS_FOR_TREATED and f["scan_sh_runs"] >= 1
                   and f["targeted_runs"] >= 1 and f["independent_review_agents"] >= 1)
    return {"invoked": bool(invoked), "treated": bool(treated)}


def fidelity_from_events(events, arm):
    """Offline re-derivation of the per-cell fidelity record from a stored (sanitized or raw) stream."""
    return analyze_events(events, arm)["fidelity"]


# ------------------------------------------------------------------------------------------------ cost

def cost_summary(model_usage, total_cost_usd=None):
    """Session totals from `modelUsage` (cumulative, includes sub-agents) split into the four token kinds."""
    by_model, tot = {}, {"uncached_input": 0, "cache_read": 0, "cache_creation": 0, "output": 0, "cost_usd": 0.0}
    for name, u in (model_usage or {}).items():
        row = {"uncached_input": u.get("inputTokens", 0) or 0, "cache_read": u.get("cacheReadInputTokens", 0) or 0,
               "cache_creation": u.get("cacheCreationInputTokens", 0) or 0, "output": u.get("outputTokens", 0) or 0,
               "cost_usd": u.get("costUSD", 0.0) or 0.0}
        by_model[name] = row
        for key, value in row.items():
            tot[key] += value
    tot["processed_tokens"] = tot["uncached_input"] + tot["cache_creation"] + tot["output"]   # excludes cache reads (the co-primary denominator)
    tot["total_tokens"] = tot["processed_tokens"] + tot["cache_read"]
    tot["cost_usd"] = round(tot["cost_usd"], 6)
    tot["by_model"] = by_model
    tot["envelope_total_cost_usd"] = total_cost_usd
    tot["cost_matches_envelope"] = None if total_cost_usd is None else abs(tot["cost_usd"] - total_cost_usd) < 1e-4
    return tot


def partial_usage(events):
    """Lower bound of a call's tokens from the assistant `usage` fields of a stream that has no result event (a timed-out call). Parent
    and subagent messages alike, one entry per message id with the largest value seen for each field (streamed copies of a message repeat
    its usage). Output tokens of a streamed message are partial, so the sum is a LOWER BOUND; the cost in USD is unknown (None)."""
    best = {}
    for event in events:
        if event.get("type") != "assistant":
            continue
        message = event.get("message") or {}
        usage = message.get("usage") or {}
        row = best.setdefault(message.get("id") or f"anon-{len(best)}", {})
        for key in ("input_tokens", "cache_creation_input_tokens", "cache_read_input_tokens", "output_tokens"):
            row[key] = max(row.get(key, 0), usage.get(key, 0) or 0)
    if not best:
        return None
    total = {key: sum(r.get(key, 0) for r in best.values()) for key in ("input_tokens", "cache_creation_input_tokens", "cache_read_input_tokens", "output_tokens")}
    tot = {"uncached_input": total["input_tokens"], "cache_read": total["cache_read_input_tokens"], "cache_creation": total["cache_creation_input_tokens"],
           "output": total["output_tokens"], "cost_usd": 0.0, "by_model": {}, "envelope_total_cost_usd": None, "cost_matches_envelope": None,
           "lower_bound": True, "messages": len(best)}
    tot["processed_tokens"] = tot["uncached_input"] + tot["cache_creation"] + tot["output"]
    tot["total_tokens"] = tot["processed_tokens"] + tot["cache_read"]
    return tot


def cost_cross_check(events, cost):
    """Does `modelUsage` (the record's token source) cover everything visible in the stream, subagent messages included? The stream's
    per-message usage is a lower bound (streamed output counts are partial), so a session total BELOW it means a part of the work, such
    as a subagent, is missing from `modelUsage`. Informational: it is recorded per call and counted in the cost table, never a filter."""
    stream = partial_usage(events)
    if not stream or not cost:
        return {"checked": False, "stream_messages": 0}
    sub = sum(1 for e in events if e.get("type") == "assistant" and e.get("parent_tool_use_id"))
    return {"checked": True, "stream_messages": stream["messages"], "subagent_messages": sub,
            "stream_processed_lower_bound": stream["processed_tokens"], "stream_total_lower_bound": stream["total_tokens"],
            "model_usage_processed": cost["processed_tokens"], "model_usage_total": cost["total_tokens"],
            "model_usage_covers_stream": cost["processed_tokens"] >= stream["processed_tokens"] and cost["total_tokens"] >= stream["total_tokens"]}


def normalized_usage(envelope):
    """Codex-comparable shape built from modelUsage: input_tokens includes cached reads and cache writes."""
    c = cost_summary(envelope.get("modelUsage"), envelope.get("total_cost_usd"))
    return {"input_tokens": c["uncached_input"] + c["cache_read"] + c["cache_creation"], "cached_input_tokens": c["cache_read"],
            "output_tokens": c["output"], "cache_creation_input_tokens": c["cache_creation"], "uncached_input_tokens": c["uncached_input"]}


# ------------------------------------------------------------------------------------------------ the call

def parse_events(stdout):
    events = []
    for line in (stdout or "").splitlines():
        line = line.strip()
        if line.startswith("{"):
            try:
                events.append(json.loads(line))
            except json.JSONDecodeError:
                pass
    return events


def configure(engine):
    def call_model(project, work, arm, task, model, timeout, budget):
        started = time.monotonic()
        base = {"infrastructure_error": False, "timeout": False, "error": None, "cost_usd": None,
                "cost_status": "claude-total_cost_usd+modelUsage", "num_turns": 0, "usage": None, "model_usage": None,
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
        prompt = engine.FRAME.format(task=task) + ARM_LINES[arm]
        mcp_config = write_mcp_config(project, work, app_port_of(project)) if arm == ARM_A else None
        argv = command(arm, model, engine.OUTPUT_SCHEMA, budget, work, mcp_config)
        env = build_env(model)
        try:
            proc = subprocess.Popen(argv, cwd=project, stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                                    text=True, env=env, start_new_session=True)
        except OSError as error:
            return {**base, "infrastructure_error": True, "error": str(error), "elapsed_ms": round((time.monotonic() - started) * 1000)}
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
        events = parse_events(stdout)
        inits = [e for e in events if e.get("type") == "system" and e.get("subtype") == "init"]
        problems = check_isolation(arm, inits, model, project)
        comp = analyze_events(events, arm, project, work, engine.sanitize)
        first = inits[0] if inits else {}
        comp["isolation"] = {"problems": problems, "init_events": len(inits), "skills": first.get("skills"), "agents": first.get("agents"),
                             "mcp_servers": first.get("mcp_servers"), "model": first.get("model"), "cli": first.get("claude_code_version"),
                             "slash_commands": first.get("slash_commands"), "tools_count": len(first.get("tools") or [])}
        base.update(transcript_path=str(transcript), transcript_events=len(events), exit_code=proc.returncode,
                    elapsed_ms=round((time.monotonic() - started) * 1000), stderr=engine.sanitize((stderr or "")[-600:], paths),
                    compliance=comp)
        if problems:   # systematic, not transient: stop the campaign after this call instead of retrying (the call is lost, the row is kept)
            return {**base, "infrastructure_error": True, "fatal_infrastructure": True, "isolation_violation": True,
                    "error": "isolation contract violated: " + "; ".join(problems)}
        f = comp["fidelity"]
        if arm == ARM_A and f["port_conflicts_in_playwright_test"] and not f["server_started_by_model"]:
            base["harness_port_conflict"] = True   # the generation-phase port split did not hold; a harness defect, not a model outcome
            return {**base, "infrastructure_error": True, "error": "port conflict in the parent's playwright test run without a model-started server"}
        if timed_out:   # no result event: the tokens are a lower bound from the stream (None if no assistant message was seen)
            return {**base, "timeout": True, "error": "wall-clock limit", "cost": partial_usage(events)}
        envelope = next((e for e in reversed(events) if e.get("type") == "result"), None)
        if envelope is None:
            return {**base, "infrastructure_error": True,
                    "error": f"exit {proc.returncode}: no result event: {engine.sanitize((stderr or stdout or '')[-300:], paths)}"}
        text = (envelope.get("result") or "") + "\n" + (stderr or "")
        usage = normalized_usage(envelope)
        cost = cost_summary(envelope.get("modelUsage"), envelope.get("total_cost_usd"))
        base.update(cost_usd=envelope.get("total_cost_usd"), num_turns=envelope.get("num_turns"), usage=usage, usage_all_turns=[usage],
                    model_usage=envelope.get("modelUsage"), cost=cost, cost_cross_check=cost_cross_check(events, cost),
                    is_error=envelope.get("is_error"), subtype=envelope.get("subtype"),
                    result_text=engine.sanitize(envelope.get("result") or "", paths),
                    structured_output=envelope.get("structured_output"))
        if envelope.get("is_error") and v1a.RATE_LIMIT.search(text):
            return {**base, "infrastructure_error": True, "fatal_infrastructure": True, "error": "Claude usage/rate limit; stop this run"}
        if proc.returncode != 0 and base["structured_output"] is None and envelope.get("subtype") not in ("error_max_budget_usd", "error_max_turns"):
            return {**base, "infrastructure_error": True, "error": f"exit {proc.returncode}: {envelope.get('subtype')}"}
        return base
    return call_model


def install(engine):
    engine.call_model = configure(engine)
    return engine.call_model
