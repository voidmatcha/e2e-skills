#!/usr/bin/env python3
"""Transcript signals and their offline validation for generator-ablation-v1. Apache-2.0.

Nothing here calls a model, a browser or the network. It reads saved Codex (`item.completed`) or Claude Code
(`stream-json`) parent transcripts and answers two different questions about each cell:

* `detect`  - the DETECTORS the protocol freezes: one regex per component, applied to the text of the parent's tool
  calls (`where: command`) or tool results (`where: tool_output`). This is what the live analysis uses.
* `truth`   - GROUND TRUTH re-derived from the tool-call events themselves, with a shell parse of each command and,
  for the reading signals, the line range each read command or `Read` call covers (checked against the real file).
  It is deliberately a different computation from the regexes, so that precision and recall mean something.

`validate()` joins the two over a set of stored cells and returns the confusion counts per component.
"""
import json
import re
import shlex
from pathlib import Path

COMPONENTS = ("L", "E", "P", "R", "V")
HEREDOC = re.compile(r"<<-?\s*(['\"]?)([A-Za-z_][A-Za-z0-9_]*)\1")
SEPARATORS = {"&&", "||", ";", "|", "&", ";;", "|&"}
ENV_ASSIGN = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*=")
WRAPPERS = {"command", "exec", "time", "nohup", "builtin"}
SHELLS = {"bash", "sh", "zsh", "dash"}
NAV_SUBCOMMANDS = {"open", "goto", "snapshot"}
SPAWN_TOOLS = ("collab:spawn_agent", "Agent", "Task")
REVIEW_BRIEF = re.compile(r"\breview(?:er)?\b|\bV6\b|e2e-reviewer", re.I)  # not "reviewed": a task text can say "cards reviewed"
READ_PROGRAMS = {"cat", "nl", "bat", "head", "tail", "sed", "rg", "grep", "less", "more", "awk", "perl", "python", "python3", "node", "xxd", "od"}


# --------------------------------------------------------------------------------------------------------- loading

def _flat(content):
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        return "\n".join(x.get("text", "") if isinstance(x, dict) else str(x) for x in content)
    return str(content)


def load_events(path, runner):
    """Parent-only events as dicts {tool, input, out, ok}. Child agents are invisible (Codex) or skipped (Claude)."""
    path = Path(path)
    events = []
    if runner == "codex":
        for line in path.read_text(errors="replace").splitlines():
            if not line.strip():
                continue
            e = json.loads(line)
            if e.get("type") != "item.completed":
                continue
            item = e.get("item") or {}
            if item.get("type") == "command_execution":
                events.append({"tool": "Bash", "input": {"command": item.get("command", "")},
                               "out": item.get("aggregated_output") or "", "ok": item.get("exit_code") == 0})
            elif item.get("type") == "collab_tool_call":
                states = item.get("agents_states") or {}
                msgs = "\n".join(str((s or {}).get("message") or "") for s in states.values())
                events.append({"tool": "collab:" + str(item.get("tool")), "input": {"prompt": item.get("prompt") or ""},
                               "out": msgs, "ok": True})
        return events
    if runner == "claude":
        pending = {}
        for line in path.read_text(errors="replace").splitlines():
            if not line.strip():
                continue
            e = json.loads(line)
            if e.get("parent_tool_use_id"):
                continue
            if e.get("type") == "assistant":
                for block in (e.get("message") or {}).get("content", []):
                    if block.get("type") == "tool_use":
                        rec = {"tool": block["name"], "input": block.get("input") or {}, "out": "", "ok": None}
                        events.append(rec)
                        pending[block["id"]] = rec
            elif e.get("type") == "user":
                content = (e.get("message") or {}).get("content")
                for block in content if isinstance(content, list) else []:
                    if block.get("type") == "tool_result" and block.get("tool_use_id") in pending:
                        rec = pending[block["tool_use_id"]]
                        rec["ok"] = not block.get("is_error", False)
                        rec["out"] = _flat(block.get("content"))
        return events
    raise ValueError("unknown runner " + repr(runner))


# -------------------------------------------------------------------------------------------------------- detectors

def detect(events, signals):
    """Frozen detectors: component -> bool. `command` looks at Bash command text, `tool_output` at any tool result."""
    out = {}
    for comp, spec in signals.items():
        rx = re.compile(spec["regex"])
        if spec["where"] == "command":
            hit = any(rx.search(str(e["input"].get("command", ""))) for e in events if e["tool"] == "Bash")
        elif spec["where"] == "tool_output":
            hit = any(rx.search(e["out"] or "") for e in events if e["tool"] not in ("Write", "Edit", "StructuredOutput"))
        else:
            raise ValueError("unknown signal location " + repr(spec["where"]))
        out[comp] = hit
    return out


# ------------------------------------------------------------------------------------------------ shell parse (truth)

def _strip_heredocs(text):
    """Drop heredoc bodies so they are not mistaken for commands."""
    out, lines, i = [], text.split("\n"), 0
    while i < len(lines):
        line = lines[i]
        out.append(line)
        m = HEREDOC.search(line)
        i += 1
        if m:
            while i < len(lines) and lines[i].strip() != m.group(2):
                i += 1
            i += 1
    return "\n".join(out)


def _newlines_to_semicolons(text):
    out, quote, esc = [], None, False
    for ch in text:
        if esc:
            out.append(ch)
            esc = False
        elif ch == "\\" and quote != "'":
            out.append(ch)
            esc = True
        elif quote:
            out.append(ch)
            if ch == quote:
                quote = None
        elif ch in "'\"":
            out.append(ch)
            quote = ch
        elif ch == "\n":
            out.append(" ; ")
        else:
            out.append(ch)
    return "".join(out)


PLACEHOLDER = re.compile(r"<(work|project|home|tmp)>")


def _tokens(text):
    """Stored transcripts are sanitized to `<work>`-style placeholders; shlex would read their angle brackets as redirects."""
    text = PLACEHOLDER.sub(lambda m: "/" + m.group(1), text)
    lex = shlex.shlex(_newlines_to_semicolons(_strip_heredocs(text)), posix=True, punctuation_chars=True)
    lex.whitespace_split = True
    return list(lex)


def simple_commands(command, _depth=0):
    """argv lists of every simple command in a shell string; `bash -c '...'` wrappers are unwrapped recursively.

    Returns (list_of_argv, parsed_ok). A string that cannot be tokenized returns ([], False)."""
    try:
        tokens = _tokens(command)
    except ValueError:
        return [], False
    groups, cur = [], []
    for tok in tokens:
        if tok in SEPARATORS:
            if cur:
                groups.append(cur)
            cur = []
        else:
            cur.append(tok)
    if cur:
        groups.append(cur)
    result = []
    for argv in groups:
        argv = _normalize(argv)
        if not argv:
            continue
        prog = Path(argv[0]).name
        if prog in SHELLS and _depth < 4:
            flags = [i for i, a in enumerate(argv[1:], 1) if re.fullmatch(r"-[A-Za-z]*c[A-Za-z]*", a)]
            if flags and flags[0] + 1 < len(argv):
                inner, ok = simple_commands(argv[flags[0] + 1], _depth + 1)
                result.extend(inner)
                if not ok:
                    return result, False
                continue
        result.append(argv)
    return result, True


def _normalize(argv):
    argv = list(argv)
    while argv:
        head = argv[0]
        if ENV_ASSIGN.match(head):
            argv.pop(0)
        elif Path(head).name == "env":
            argv.pop(0)
            while argv and (argv[0].startswith("-") or ENV_ASSIGN.match(argv[0])):
                flag = argv.pop(0)
                if flag in ("-u", "--unset", "-C", "-S"):
                    if argv:
                        argv.pop(0)
        elif head in WRAPPERS:
            argv.pop(0)
        elif head == "timeout" and len(argv) > 1:
            argv = argv[2:]
        else:
            break
    return argv


def _is_playwright(argv):
    """True and the remaining args when argv launches the Playwright binary (directly or through npx/pnpm/yarn)."""
    if not argv:
        return False, []
    prog = Path(argv[0]).name
    if prog == "playwright":
        return True, argv[1:]
    if prog in ("npx", "pnpm", "yarn", "bunx", "npm"):
        rest = argv[1:]
        while rest and (rest[0].startswith("-") or rest[0] in ("exec", "dlx")):
            rest = rest[1:]
        if rest and Path(rest[0]).name == "playwright":
            return True, rest[1:]
    return False, []


def explored(argv):
    """The command opens or drives a browser to look at the app: a Playwright CLI open/goto/snapshot or agent-browser."""
    is_pw, rest = _is_playwright(argv)
    if is_pw and "cli" in rest[:3]:
        args = rest[rest.index("cli") + 1:]
        return not any(a in ("--help", "-h", "help") for a in args) and bool(NAV_SUBCOMMANDS & set(args))
    prog = Path(argv[0]).name if argv else ""
    if prog == "agent-browser":
        return not any(a in ("--help", "-h", "help") for a in argv[1:]) and len(argv) > 1
    if prog == "run-raw-aria-snapshot.sh":
        return True
    return prog in SHELLS and not _no_exec(argv) and any(Path(a).name == "run-raw-aria-snapshot.sh" for a in argv[1:])


def _no_exec(argv):
    """A shell invoked with a syntax-check flag (`bash -n script`) parses the script and never runs it. Only the shell's own
    flags count: everything from the first non-flag word on belongs to the script."""
    for a in argv[1:]:
        if not a.startswith("-"):
            return False
        if a == "--noexec" or re.fullmatch(r"-[A-Za-z]*n[A-Za-z]*", a):
            return True
    return False


def executes_script(argv, script):
    """The command runs `script` (bash/sh <path>/script, or the path itself) rather than reading or listing it."""
    if not argv:
        return False
    prog = Path(argv[0]).name
    if prog == script:
        return True
    if prog in SHELLS:
        if _no_exec(argv):
            return False
        rest = [a for a in argv[1:] if not a.startswith("-")]
        return bool(rest) and Path(rest[0]).name == script
    return False


# ----------------------------------------------------------------------------------------------------- read coverage

def _sed_lines(script, lines):
    """Lines (1-based set) printed by a `sed -n` script made of `ADDR p` commands; None if the script is not understood."""
    total = len(lines)

    def addr(token, after=0):
        token = token.strip()
        if token == "$":
            return total
        if token.isdigit():
            return int(token)
        m = re.fullmatch(r"/(.*)/", token)
        if m:
            rx = re.compile(m.group(1))
            for i in range(max(after, 1), total + 1):
                if rx.search(lines[i - 1]):
                    return i
            return total + 1
        return None

    picked = set()
    for part in re.split(r"[;\n]", script):
        part = part.strip()
        if not part:
            continue
        m = re.fullmatch(r"(.+?)p", part)
        if not m:
            return None
        spec = m.group(1)
        pieces = re.split(r",(?=(?:/|\d|\$))", spec) if "," in spec else [spec]
        if len(pieces) == 1:
            a = addr(pieces[0])
            if a is None:
                return None
            picked.add(a)
        elif len(pieces) == 2:
            start = addr(pieces[0])
            if start is None:
                return None
            end = addr(pieces[1], after=start + 1) if not pieces[1].strip().isdigit() else addr(pieces[1])
            if end is None:
                return None
            picked.update(range(start, min(end, total) + 1))
        else:
            return None
    return {i for i in picked if 1 <= i <= total}


def _target_index(argv, name):
    for i, a in enumerate(argv):
        if Path(a).name == name:
            return i
    return None


NON_READ = {"ls", "wc", "stat", "file", "test", "[", "find", "git", "cp", "mv", "rm", "chmod", "du", "realpath", "dirname", "basename",
            "echo", "printf", "cd", "touch", "mkdir", "diff", "cmp", "shasum", "md5", "sha256sum", "tee"}


def command_coverage(argv, name, lines):
    """(status, set) for one simple command against file `name`: status in {"none","covered","unknown"}.

    "none" means the command does not read that file; "covered" carries the set of lines it prints."""
    if not argv:
        return "none", set()
    prog = Path(argv[0]).name
    idx = _target_index(argv, name)
    if idx is None:
        return "none", set()
    total = len(lines)
    everything = set(range(1, total + 1))
    if prog in NON_READ:
        return "none", set()
    if prog in ("cat", "bat", "nl", "less", "more"):
        return "covered", everything
    if prog == "sed":
        script = None
        quiet = any(a == "-n" or (a.startswith("-") and not a.startswith("--") and "n" in a and "e" not in a) for a in argv[1:idx])
        for j, a in enumerate(argv[1:idx], 1):
            if a == "-e" and j + 1 < len(argv):
                script = argv[j + 1]
        if script is None:
            script = next((a for a in argv[1:idx] if not a.startswith("-")), None)
        if not quiet or script is None:
            return ("covered", everything) if script is not None and not quiet else ("unknown", set())
        got = _sed_lines(script, lines)
        return ("covered", got) if got is not None else ("unknown", set())
    if prog in ("head", "tail"):
        n = 10
        plus = False
        args = argv[1:idx]
        for j, a in enumerate(args):
            if a in ("-n", "--lines") and j + 1 < len(args):
                val = args[j + 1]
            elif re.fullmatch(r"-n.+", a):
                val = a[2:]
            elif re.fullmatch(r"-\d+", a):
                val = a[1:]
            else:
                continue
            plus = val.startswith("+")
            if not re.fullmatch(r"\+?\d+", val):
                return "unknown", set()
            n = int(val.lstrip("+"))
        if prog == "head":
            return "covered", set(range(1, min(n, total) + 1))
        return ("covered", set(range(n, total + 1))) if plus else ("covered", set(range(max(total - n, 0) + 1, total + 1)))
    if prog in ("rg", "grep"):
        pattern = None
        flags = re.I if any(a in ("-i", "--ignore-case") for a in argv[1:idx]) else 0
        if any(a.startswith(("-A", "-B", "-C", "--context", "--after", "--before", "-o", "--only")) for a in argv[1:idx]):
            return "unknown", set()
        rest = [a for a in argv[1:idx] if not a.startswith("-")]
        if rest:
            pattern = rest[0]
        if pattern is None:
            return "unknown", set()
        try:
            rx = re.compile(pattern, flags)
        except re.error:
            return "unknown", set()
        return "covered", {i for i, text in enumerate(lines, 1) if rx.search(text)}
    return "unknown", set()


def read_status(events, name, lines):
    """(covered_lines, unknown_touches) for file `name` over all parent events.

    The Claude `Read` tool reports `file_path`, `offset` and `limit`. Anything else that names the file is parsed from the
    shell; a command that names the file but is not understood counts as `unknown`."""
    covered, unknown = set(), 0
    total = len(lines)
    for e in events:
        if e["tool"] == "Read" and Path(str(e["input"].get("file_path", ""))).name == name:
            start = int(e["input"].get("offset") or 1)
            limit = int(e["input"].get("limit") or 2000)
            covered |= set(range(max(start, 1), min(start + limit - 1, total) + 1))
        elif e["tool"] == "Bash":
            cmds, ok = simple_commands(str(e["input"].get("command", "")))
            touched = False
            for argv in cmds:
                status, got = command_coverage(argv, name, lines)
                if status == "covered":
                    covered |= got
                    touched = True
                elif status == "unknown":
                    unknown += 1
                    touched = True
            if not ok and name in str(e["input"].get("command", "")) and not touched:
                unknown += 1
    return covered, unknown


# ------------------------------------------------------------------------------------------------------------ truth

def truth(events, tree):
    """Ground truth per component: True / False / None (the read could not be resolved). `tree` maps file -> text of the
    skill variant the cell was given (the shared base for the stored full-skill cells)."""
    out = {}
    cmds = []
    for e in events:
        if e["tool"] == "Bash":
            parsed, _ = simple_commands(str(e["input"].get("command", "")))
            cmds.extend(parsed)
    out["R"] = any(executes_script(argv, "scan.sh") for argv in cmds)
    out["E"] = any(explored(argv) for argv in cmds)

    def reading(name, markers):
        text = tree[name].split("\n")
        wanted = {i for i, line in enumerate(text, 1) if any(m in line for m in markers)}
        covered, unknown = read_status(events, name, text)
        if wanted & covered:
            return True
        return None if unknown else False

    out["L"] = reading("code-rules.md", ("Text-bearing elements without a role",))
    out["P"] = reading("scenario-design.md", ("Distinct risk:",))
    out["V_read"] = reading("verification-rules.md", ("V-RULE-CONTRACT", "Completion status matrix"))  # the provisional V signal's truth
    # V is behavioral: the independent re-review was attempted, i.e. the parent spawned a reviewer agent. Reading
    # verification-rules.md is not V, because Step 4 (which minus-V keeps) sends the writer to its "Command effect labels".
    # A spawn counts only when its brief mentions a review: the first-party generator arm spawns a generator agent.
    out["V"] = any(e["tool"] in SPAWN_TOOLS and REVIEW_BRIEF.search(str(e["input"].get("prompt", "")) + str(e["input"].get("description", "")))
                   for e in events)
    return out


# ------------------------------------------------------------------------------------------------------- validation

def confusion(pairs):
    """pairs: list of (detected, truth) with truth None excluded. Returns counts and precision/recall (None if undefined)."""
    tp = sum(1 for d, t in pairs if d and t)
    fp = sum(1 for d, t in pairs if d and not t)
    fn = sum(1 for d, t in pairs if not d and t)
    tn = sum(1 for d, t in pairs if not d and not t)
    precision = tp / (tp + fp) if tp + fp else None
    recall = tp / (tp + fn) if tp + fn else None
    return {"tp": tp, "fp": fp, "fn": fn, "tn": tn, "n": len(pairs),
            "precision": None if precision is None else round(precision, 4),
            "recall": None if recall is None else round(recall, 4)}


def validate(cells, signals, tree, truth_keys=None):
    """cells: iterable of dicts {model, arm, call_id, events}. Returns per-component confusion and the disagreements.

    truth_keys maps a component to the truth entry it is judged against (default: its own); the provisional V detector,
    which looked for the verification-rules text, is judged against `V_read`."""
    truth_keys = truth_keys or {}
    rows = []
    for cell in cells:
        det = detect(cell["events"], signals)
        tru = truth(cell["events"], tree)
        rows.append({"model": cell["model"], "arm": cell["arm"], "call_id": cell["call_id"], "detected": det, "truth": tru})
    per = {}
    for comp in signals:
        truth_key = truth_keys.get(comp, comp)
        pairs = [(r["detected"][comp], r["truth"][truth_key]) for r in rows if r["truth"][truth_key] is not None]
        per[comp] = confusion(pairs) | {"unresolved_cells": sum(1 for r in rows if r["truth"][truth_key] is None)}
    disagreements = [{"call_id": r["call_id"], "model": r["model"], "arm": r["arm"], "component": c,
                      "detected": r["detected"][c], "truth": r["truth"][truth_keys.get(c, c)]}
                     for r in rows for c in signals if r["truth"][truth_keys.get(c, c)] is not None
                     and r["detected"][c] != r["truth"][truth_keys.get(c, c)]]
    return {"per_component": per, "rows": rows, "disagreements": disagreements}


def rate(rows, comp, arm, source="detected"):
    """Share of the cells of `arm` in which `comp` is detected (source "detected") or true (source "truth")."""
    sel = [r for r in rows if r["arm"] == arm and r[source][comp] is not None]
    if not sel:
        return None
    return round(sum(1 for r in sel if r[source][comp]) / len(sel), 4)
