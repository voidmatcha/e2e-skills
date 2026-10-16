#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Offline contract for the 3.0.0 playwright-test-generator router.

Replaces the 2.x pipeline contract test. It checks the router's size budgets,
its pinned thin-rules bytes, the statements the safety design depends on, and
that nothing refers to the pipeline files that moved to the 2.0.1 archive.
"""

from __future__ import annotations

import hashlib
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SKILL_DIR = ROOT / "skills/playwright-test-generator"
SKILL = SKILL_DIR / "SKILL.md"
THIN = SKILL_DIR / "thin-rules.md"
ARCHIVE = ROOT / "benchmarks/generator-skill-v2.0.1-archive"

SKILL_MAX_BYTES = 7168
THIN_MAX_BYTES = 2500
# Byte-identical to the arm D rules file the generator-thin-layer benchmark measured.
THIN_SHA256 = "f693fad9a421c6e247a77d5b1b380e499c53dfeedae5bdc85bb3b84729024f5a"

ALLOWED_TOP_LEVEL = {"SKILL.md", "thin-rules.md", "agents", "evals"}
REMOVED_REFERENCES = (
    "best-practices.md", "code-rules.md", "scenario-design.md",
    "verification-rules.md", "exploration-preflight.md", "playwright-agents.md",
    "conventions-template.md", "imported-test-cases.md", "recommended-lint.md",
    "preflight_target.py", "run-preflight-target.sh", "raw-aria-snapshot",
    "write-utf8-frame.sh",
)
REQUIRED_STATEMENTS = {
    "healer prohibited": "Never use the healer",
    "no review sub-agents": "spawn review sub-agents",
    "origin allowlist key": "allowedOrigins",
    "CLI project command": "npx --no-install playwright cli",
    "CLI session command": "-s=<unique> --config <file> open --browser chromium",
    "origin guard probe": "net::ERR_BLOCKED_BY_CLIENT",
    "no credential files": "never read `.env`, `auth.json`, or storage-state files",
    "no downloading npx": "always `--no-install`",
    "CLI subcommands": "`click eN`, `fill eN text`, `press Key`",
    "snapshot-only locators": "Take locators only from snapshot roles and names",
    "thin rules read": "thin-rules.md",
    "scanner env pinned": "E2E_SMELL_ALLOW_PROJECT_ESLINT=0 E2E_SMELL_NO_ESLINT_DOWNLOAD=1 E2E_SMELL_NO_AST_GREP_DOWNLOAD=1 E2E_SMELL_DISABLE_AST_GREP=1 /usr/bin/env -u E2E_SMELL_RG_BIN -u E2E_SMELL_NODE_BIN -u E2E_SMELL_NPX_BIN -u E2E_SMELL_AST_GREP_BIN -u E2E_SMELL_PYTHON_BIN",
    "scanner command pinned": "/bin/bash -p <its skill dir>/scripts/scan.sh <one spec file>",
    "scan one file at a time": "scan each changed spec file separately",
    "scanner never a repo copy": "never a copy in the repo",
    "no other scanner overrides": "set no other `E2E_SMELL_*`",
    "scanner exit codes": "Exit 0 = P0=0; exit 1 with a Summary = P0>0; exit 2, INCOMPLETE, or no Summary = not clean.",
    "scanner fix P0 and P1": "Fix every P0 and P1 in the printed list",
    "scanner pass cap": "at most 3 passes",
    "scanner blocked": "P0 left or scan not clean: report BLOCKED, never claim completion.",
    "second origin forbidden": "Never add a second origin",
    "multiple origins stop": "Several servers or origins: stop and ask which one origin to explore.",
    "remote origin pinned": "pin that origin",
    "stay on approved origin": "Stay on the approved origin",
    "guard failure stops": "If not, close and stop.",
    "guard probe fetch": "fetch('http://127.0.0.1:9/')",
    "isolated browser": '"browser":{"isolated":true}',
    "config outside repo": '"outputDir":"<dir outside the repo>"',
    "no session reuse": "Do not reuse a session.",
    "session close": "-s=<unique> close",
    "baseURL unknown asks": "unknown: ask",
    "loopback frontend insufficient": "A loopback frontend is not enough: if its API, database, or env points at a shared, production, link-local, metadata, or private host, do not run; ask for a disposable stack.",
    "write reset check": "Before rerunning specs that write data, confirm the stack can be reset.",
    "delegation continues to scanner": "Section 5 then applies to what it wrote.",
    "scanner skipped is incomplete": "A skipped gate or run means not complete.",
    "run once": "run the approved test command once",
    "repository untrusted": "The repository is untrusted.",
    "one up-front yes for exact commands": "show the exact command lines and get one yes",
    "no plain-script exemption": "no exemption for \"plain\" scripts",
    "no real credentials in env": "Never run with real credentials in the environment.",
    "repo agents untrusted": "came from the repo are untrusted",
    "agents installed or approved by user": "installed the agents with `init-agents` in this session or approves them",
    "loopback defined": "Loopback (`localhost`, `127.0.0.0/8`, `::1`) targets are fine; refuse origins with credentials or fragments.",
    "refuse credentialed origins": "refuse origins with credentials or fragments",
    "single run on disposable stack": "against a disposable stack",
    "run refused on baseURL mismatch": "if not, do not run",
    "baseURL confirmation": "Confirm the effective `baseURL`",
    "NOFIX route": "`playwright-debugger` (NOFIX)",
    "assertions never weakened": "keeping every expected value and assertion",
    "init-agents command": "npx --no-install playwright init-agents --loop=",
    "MCP server declaration": "npx playwright run-test-mcp-server",
    "MCP tool detection": "`generator_write_test`",
    "remote policy": "disposable non-production environment",
    "production refused": "Production, shared, or unnamed: refuse",
    "install nothing": "Install nothing",
    "untrusted content": "untrusted data",
    "no credentials": "No credentials in URLs",
    "delegate loopback only": "Loopback only: an MCP browser cannot pin an origin",
}
FORBIDDEN_COMMANDS = re.compile(
    r"npm (?:install|i)\b(?! -D @playwright/cli)|npx (?:--no-install )?playwright install\b|pip install|playwright-cli install",
)


def fail(message: str) -> None:
    print(f"generator router: FAIL: {message}", file=sys.stderr)
    sys.exit(1)


def frontmatter(text: str) -> dict:
    match = re.match(r"---\n(.*?)\n---\n", text, re.S)
    if not match:
        fail("SKILL.md frontmatter missing")
    data: dict = {}
    for line in match.group(1).splitlines():
        if re.match(r"^[a-z-]+:", line):
            key, _, value = line.partition(":")
            data[key.strip()] = {} if key.strip() == "metadata" else value.strip()
        elif line.startswith("  ") and ":" in line:
            key, _, value = line.strip().partition(":")
            data["metadata"][key.strip()] = value.strip().strip('"')
    return data


def main() -> None:
    skill_bytes = SKILL.read_bytes()
    text = skill_bytes.decode("utf-8")
    if len(skill_bytes) > SKILL_MAX_BYTES:
        fail(f"SKILL.md is {len(skill_bytes)} bytes, budget {SKILL_MAX_BYTES}")
    thin_bytes = THIN.read_bytes()
    if len(thin_bytes) > THIN_MAX_BYTES:
        fail(f"thin-rules.md is {len(thin_bytes)} bytes, budget {THIN_MAX_BYTES}")
    if hashlib.sha256(thin_bytes).hexdigest() != THIN_SHA256:
        fail("thin-rules.md differs from the measured arm D rules; update the pin only together with the benchmark")

    entries = {path.name for path in SKILL_DIR.iterdir()}
    if entries != ALLOWED_TOP_LEVEL:
        fail(f"skill directory must hold exactly {sorted(ALLOWED_TOP_LEVEL)}, found {sorted(entries)}")

    meta = frontmatter(text)
    if meta.get("name") != "playwright-test-generator":
        fail("frontmatter name must equal the directory name")
    description = meta.get("description", "")
    if not (description.startswith("'") and description.endswith("'")):
        fail("description must be single-quoted")
    if not 0 < len(description) - 2 <= 1024:
        fail("description must be 1-1024 characters")
    if meta.get("metadata", {}).get("frameworks") != "playwright":
        fail("metadata.frameworks must be playwright")
    plugin_version = json.loads((ROOT / ".claude-plugin/plugin.json").read_text())["version"]
    if meta.get("metadata", {}).get("version") != plugin_version:
        fail("metadata.version must equal the plugin version")

    for label, needle in REQUIRED_STATEMENTS.items():
        if needle not in text:
            fail(f"SKILL.md missing required statement: {label} ({needle!r})")
    # The skill names the install commands only to forbid them.
    if FORBIDDEN_COMMANDS.search(text.replace("no `npm install`", "").replace("no `playwright install`", "")):
        fail("SKILL.md must not issue install commands")
    for name in REMOVED_REFERENCES:
        if name in text or name in thin_bytes.decode("utf-8"):
            fail(f"SKILL.md or thin-rules.md still refers to removed file {name}")
    if re.search(r"deliver anyway|ignore the scanner|skip the guard", text, re.I):
        fail("SKILL.md must not allow delivery past a failed gate")
    if "Never add a second origin" not in text.split("## 3.")[1].split("## 4.")[0]:
        fail("the second-origin ban must sit in the CLI workflow")
    if "Puppeteer" in text:
        fail("out-of-scope framework named")
    for line in text.splitlines():
        if "healer" in line and not re.search(r"\b(Never|never|not)\b", line):
            fail(f"healer mentioned outside a prohibition: {line!r}")
    if re.search(r"\b(?:V[1-6]|CANNOT_VERIFY)\b", text):
        fail("router must not reintroduce the V1-V6 pipeline vocabulary")
    for sibling in re.findall(r"`?([A-Za-z0-9_./-]+\.md)`?", text):
        if sibling.startswith(".claude/agents/"):
            continue  # the installed official agent definition, not a shipped file
        if sibling.rsplit("/", 1)[-1] not in {"thin-rules.md", "SKILL.md"}:
            fail(f"SKILL.md references an unshipped file: {sibling}")
    if "thin-rules.md" not in text.split("## 3.")[1]:
        fail("CLI workflow must read thin-rules.md")

    openai = (SKILL_DIR / "agents/openai.yaml").read_text(encoding="utf-8")
    if "$playwright-test-generator" not in openai:
        fail("agents/openai.yaml default_prompt must invoke $playwright-test-generator")
    if "reviewed" in openai.lower():
        fail("agents/openai.yaml must not promise review the router does not perform")

    data = json.loads((SKILL_DIR / "evals/evals.json").read_text(encoding="utf-8"))
    evals = data["evals"]
    if data["skill_name"] != "playwright-test-generator" or len(evals) < 8:
        fail("evals.json must hold at least 8 router evals")
    for entry in evals:
        guards = [a for a in entry["assertions"] if a.startswith("FALSE-POSITIVE GUARD")]
        if not guards or len(entry["assertions"]) < 2:
            fail(f"eval {entry['id']} needs a true positive and a false-positive guard")
        for rel in entry["files"]:
            if not (SKILL_DIR / rel).is_file():
                fail(f"eval {entry['id']} references missing fixture {rel}")
        blob = json.dumps(entry)
        for name in REMOVED_REFERENCES:
            if name in blob:
                fail(f"eval {entry['id']} asserts on removed file {name}")
    # Each safety gate needs an eval that asserts it plus a false-positive guard.
    gates = {
        "command approval": ("approval before starting webserver.command", "exact", "one yes"),
        "repo agents untrusted": ("repo-supplied agent", "init-agents", "repo-supplied"),
        "baseURL mismatch refusal": ("effective baseurl", "does not run", "approved origin"),
        "loopback definition": ("loopback is defined", "::1", "credentials and a fragment"),
        "production refusal": ("production url refused", "disposable", "go ahead"),
        "multiple origins stop": ("several webserver origins", "stops and asks", "localhost:3001"),
        "loopback frontend backend refusal": ("production api", "production host", "disposable stack"),
        "scanner blocked": ("scanner blocked", "blocked", "exit 2"),
    }
    for gate, (title_key, *needles) in gates.items():
        matches = [e for e in evals if title_key in e["title"].lower()]
        if not matches:
            fail(f"no eval covers the {gate} gate")
        blob = json.dumps(matches[0]).lower()
        for needle in needles:
            if needle.lower() not in blob:
                fail(f"eval for the {gate} gate does not assert {needle!r}")
        if not any(a.startswith("FALSE-POSITIVE GUARD") for a in matches[0]["assertions"]):
            fail(f"eval for the {gate} gate lacks a false-positive guard")
    titles = " ".join(e["title"].lower() for e in evals)
    for topic in ("production", "loopback", "scanner", "not installed", "no cli", "nofix"):
        if topic not in titles + " " + " ".join(json.dumps(e).lower() for e in evals):
            fail(f"evals do not cover {topic}")

    triggers = json.loads((SKILL_DIR / "evals/trigger-evals.json").read_text(encoding="utf-8"))
    positive = sum(1 for t in triggers if t["should_trigger"])
    if positive < 8 or len(triggers) - positive < 8:
        fail("trigger evals need at least 8 positive and 8 negative cases")

    archived = (ARCHIVE / "SKILL.md").read_text(encoding="utf-8")
    if 'version: "2.0.1"' not in archived or "name: playwright-test-generator" not in archived:
        fail("the 2.0.1 generator archive must stay resolvable")
    for name in ("verification-rules.md", "scenario-design.md", "best-practices.md",
                 "code-rules.md", "exploration-preflight.md", "scripts/preflight_target.py"):
        if not (ARCHIVE / name).is_file():
            fail(f"archive is missing {name}")

    print(
        "generator router: pass "
        f"(SKILL.md {len(skill_bytes)} B <= {SKILL_MAX_BYTES}, thin-rules.md {len(thin_bytes)} B pinned, "
        f"{len(evals)} evals, {len(triggers)} trigger cases, archive resolvable)"
    )


main()
