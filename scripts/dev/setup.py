#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Explicit host setup; reuse the verified skill/agent installers.

Project configuration is planned and collision-checked before global writes.
Official agents are generated against a temporary config, never the user's
executable config. No tests, browsers, project dependency installs, or MCP
servers run during setup. Restart/approval and live tool discovery are separate.
"""

import argparse
import json
import os
from pathlib import Path
import re
import shlex
import subprocess
import sys
import tempfile
import tomllib

ROOT = Path(__file__).resolve().parents[2]
AGENTS = ("e2e-finding-verifier", "e2e-failure-classifier")
NODE_PATHS = ("/opt/homebrew/bin/node", "/usr/local/bin/node", "/usr/bin/node", "/bin/node")
# Session tools needed by the official planner/generator/healer definitions.
# Keep the broad upstream server's unrelated tools out of the Codex catalog.
CODEX_TOOLS = sorted("browser_click browser_close browser_console_messages browser_drag browser_evaluate browser_file_upload browser_generate_locator browser_handle_dialog browser_hover browser_navigate browser_navigate_back browser_network_request browser_network_requests browser_press_key browser_run_code_unsafe browser_select_option browser_snapshot browser_take_screenshot browser_type browser_verify_element_visible browser_verify_list_visible browser_verify_text_visible browser_verify_value browser_wait_for generator_read_log generator_setup_page generator_write_test planner_save_plan planner_setup_page test_debug test_list test_run".split())


def safe_path(path):
    """Reject redirected destination files and every redirected parent."""
    for part in (path, *path.parents):
        if part.is_symlink():
            raise ValueError(f"refusing symlinked destination: {part}")
        if part != path and part.exists() and not part.is_dir():
            raise ValueError(f"destination parent is not a directory: {part}")
    if path.exists() and not path.is_file():
        raise ValueError(f"destination is not a regular file: {path}")


def clean_env():
    # Do not forward ambient credentials, Node/Python injection, or force flags.
    env = {"PATH": "/usr/bin:/bin:/usr/sbin:/sbin", "HOME": str(Path.home()), "LANG": "en_US.UTF-8"}
    for key in ("CODEX_HOME", "CLAUDE_CONFIG_DIR"):
        if key in os.environ:
            env[key] = os.environ[key]
    return env


def run(command, cwd, env):
    return subprocess.run(command, cwd=cwd, env=env, check=True, text=True,
                          stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=120)


def dedicated_preflight(host, env):
    base = Path(env.get("CODEX_HOME", str(Path.home() / ".codex"))) if host == "codex" else Path(env.get("CLAUDE_CONFIG_DIR", str(Path.home() / ".claude")))
    if not base.is_absolute():
        raise ValueError("host configuration directory must be absolute")
    suffix = ".toml" if host == "codex" else ".md"
    source = ROOT / (".codex/agents" if host == "codex" else "agents")
    for name in AGENTS:
        target = base / "agents" / (name + suffix)
        safe_path(target)
        if target.exists() and target.read_bytes() != (source / (name + suffix)).read_bytes():
            # Upgrades of installer-owned agents are handled by the existing
            # transactional installer, but foreign definitions must survive.
            text = target.read_text()
            marker = r"^# e2e-skills Codex(/OMX)? native agent:" if host == "codex" else r"^<!-- e2e-skills Claude Code native agent:"
            owned = re.search(marker, text, re.MULTILINE) is not None
            if not owned:
                raise ValueError(f"dedicated agent conflicts with an existing file: {target}")


def plan_file(plan, target, content):
    safe_path(target)
    before = target.read_bytes() if target.exists() else None
    if before is not None and before != content:
        raise ValueError(f"existing file differs; preserve it and resolve manually: {target}")
    plan[target] = (before, content)


def plan_mcp(plan, project, host, node, cli, config):
    args = [str(cli), "run-test-mcp-server", "--headless", "--config", str(config)]
    server = {"command": str(node), "args": args}
    if host == "codex":
        target = project / ".codex/config.toml"
        safe_path(target)
        before = target.read_bytes() if target.exists() else None
        text = before.decode() if before is not None else ""
        parsed = tomllib.loads(text)
        if not isinstance(parsed.get("mcp_servers", {}), dict):
            raise ValueError(f"invalid mcp_servers table: {target}")
        existing = parsed.get("mcp_servers", {}).get("playwright-test")
        desired = {**server, "cwd": str(project), "required": True, "enabled_tools": CODEX_TOOLS}
        if existing is not None:
            if existing != desired:
                raise ValueError(f"existing playwright-test MCP differs: {target}")
            plan[target] = (before, before)
            return
        section = '\n[mcp_servers.playwright-test]\n'
        for key, value in desired.items():
            section += f"{key} = {json.dumps(value, ensure_ascii=False)}\n"
        content = (text.rstrip() + "\n" + section).encode()
        tomllib.loads(content.decode())
    else:
        target = project / ".mcp.json"
        safe_path(target)
        before = target.read_bytes() if target.exists() else None
        parsed = json.loads(before) if before is not None else {}
        if not isinstance(parsed, dict) or not isinstance(parsed.get("mcpServers", {}), dict):
            raise ValueError(f"invalid MCP configuration: {target}")
        servers = parsed.setdefault("mcpServers", {})
        if "playwright-test" in servers:
            if servers["playwright-test"] != server:
                raise ValueError(f"existing playwright-test MCP differs: {target}")
            plan[target] = (before, before)
            return
        servers["playwright-test"] = server
        content = (json.dumps(parsed, ensure_ascii=False, indent=2) + "\n").encode()
    plan[target] = (before, content)


def project_plan(project, host, env, dry_run):
    node = next((Path(p).resolve() for p in NODE_PATHS if Path(p).is_file() and os.access(p, os.X_OK)), None)
    if node is None:
        raise ValueError("no Node executable found at a standard system or Homebrew location")
    # Resolve installed packages without executing repository code. Workspaces
    # may hoist node_modules to a parent directory.
    cli = None
    for parent in (project, *project.parents):
        package = parent / "node_modules/playwright"
        if (package / "cli.js").is_file():
            metadata = json.loads((package / "package.json").read_text())
            if metadata.get("name") != "playwright":
                raise ValueError(f"unexpected Playwright package: {package}")
            cli = (package / "cli.js").resolve()
            break
    if cli is None:
        raise ValueError("project-local Playwright is not installed; install the project's dependencies first")
    config = next((project / ("playwright.config" + ext) for ext in (".ts", ".js", ".mts", ".mjs", ".cts", ".cjs") if (project / ("playwright.config" + ext)).is_file()), None)
    if config is None:
        raise ValueError("--project must name the directory containing playwright.config.*")
    plan = {}
    plan_mcp(plan, project, host, node, cli, config)
    print("Official agent generation (temporary workspace): " + shlex.join([str(node), str(cli), "init-agents", "--loop=" + host]))
    if dry_run:
        print("Dry run does not execute the project CLI; official agent conflicts and loop support remain unchecked.")
        return plan
    with tempfile.TemporaryDirectory(prefix="e2e-skills-setup-") as name:
        stage = Path(name)
        (stage / "playwright.config.cjs").write_text("module.exports = {testDir: './tests'};\n")
        help_text = run([str(node), str(cli), "init-agents", "--help"], stage, env).stdout
        if host not in help_text:
            raise ValueError(f"installed Playwright does not advertise init-agents support for {host}")
        run([str(node), str(cli), "init-agents", "--loop=" + host], stage, env)
        folder = ".codex/agents" if host == "codex" else ".claude/agents"
        extension = "toml" if host == "codex" else "md"
        for role in ("planner", "generator", "healer"):
            stem = f"playwright_test_{role}" if host == "codex" else f"playwright-test-{role}"
            generated = stage / folder / f"{stem}.{extension}"
            if generated.is_symlink() or not generated.is_file():
                raise ValueError(f"official agent not generated: {generated.name}")
            content = generated.read_bytes()
            if host == "codex":
                tomllib.loads(content.decode())
                # Keep the official instructions/tool allowlist, but use the
                # installed local CLI in children as well as the parent MCP.
                prefix, separator, mcp = content.decode().rpartition("\n[mcp_servers.playwright-test]\n")
                if not separator:
                    raise ValueError("unsupported official Codex MCP layout")
                mcp = re.sub(r"^command = .*?$", "command = " + json.dumps(str(node)), mcp, flags=re.MULTILINE)
                args = [str(cli), "run-test-mcp-server", "--headless", "--config", str(config)]
                mcp = re.sub(r"^args = .*?$", lambda _: "args = " + json.dumps(args), mcp, flags=re.MULTILINE)
                content = (prefix + separator + mcp).encode()
                tomllib.loads(content.decode())
            plan_file(plan, project / folder / generated.name, content)
    return plan


def preflight_backups(plan):
    for target, (before, content) in plan.items():
        if before is not None and before != content:
            backup = target.with_name(target.name + ".e2e-skills-backup")
            safe_path(backup)
            if backup.exists():
                raise ValueError(f"recovery backup already exists; preserve it and resolve manually: {backup}")


def apply_plan(plan):
    # Recheck the whole snapshot after the global installers, before local writes.
    for target, (before, _) in plan.items():
        safe_path(target)
        current = target.read_bytes() if target.exists() else None
        if current != before:
            raise ValueError(f"configuration changed during installation: {target}")
    for target, (before, content) in plan.items():
        if before == content:
            continue
        target.parent.mkdir(parents=True, exist_ok=True)
        # Exclusive creation prevents replacing a newly-created foreign file.
        if before is None:
            with target.open("xb") as output:
                output.write(content)
        else:
            # Preserve an exact recovery copy before merging an existing config.
            backup = target.with_name(target.name + ".e2e-skills-backup")
            with os.fdopen(os.open(backup, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600), "wb") as output:
                output.write(before)
            target.write_bytes(content)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--host", required=True, choices=("claude", "codex"))
    parser.add_argument("--project", type=Path, help="existing Playwright config directory; omit for skills/agents only")
    parser.add_argument("--dry-run", action="store_true", help="preview without executing installers or project code")
    opts = parser.parse_args(argv)
    env = clean_env()
    dedicated_preflight(opts.host, env)
    plan = {}
    if opts.project is not None:
        if not opts.project.is_dir():
            raise ValueError("--project is not an existing directory")
        plan = project_plan(opts.project.resolve(), opts.host, env, opts.dry_run)
    preflight_backups(plan)
    # The pinned CLI writes the shared canonical store through its Codex
    # projection. The existing verified installer requires that store as well
    # as Claude's copies; a Claude-only CLI call creates no canonical store.
    env["E2E_SKILLS_AGENTS"] = "-a claude-code -a codex" if opts.host == "claude" else "-a codex"
    claude_default = Path(env["HOME"]) / ".claude"
    if opts.host == "claude" and Path(env.get("CLAUDE_CONFIG_DIR", str(claude_default))) != claude_default:
        raise ValueError("custom CLAUDE_CONFIG_DIR is not supported by the verified skills installer")
    env["E2E_SKILLS_INSTALL_CODEX_AGENTS"] = "1" if opts.host == "codex" else "0"
    commands = [["/bin/bash", "-p", str(ROOT / "scripts/dev/reinstall-skills.sh")]]
    if opts.host == "claude":
        commands.append(["/bin/bash", "-p", str(ROOT / "scripts/dev/install-claude-agents.sh")])
    for command in commands:
        print("Install: " + shlex.join(command))
    for target, (before, after) in plan.items():
        print(("Keep: " if before == after else "Prepare: ") + str(target))
    if opts.dry_run:
        print("Dry run: no files changed.")
        return 0
    for command in commands:
        subprocess.run(command, cwd=ROOT, env=env, check=True)
    apply_plan(plan)
    print("Installed four skills and two dedicated agents for " + opts.host + ".")
    if opts.project:
        print("Official planner/generator/healer definitions and project-scoped playwright-test MCP configured.")
        print("No project config executed, no seed/spec files copied, and no tests or browsers run.")
        print("Use the project's existing auth/seed fixtures; browser availability remains unchecked.")
        print("Restart the host in this trusted project, approve the MCP tools, and confirm generator_write_test is visible.")
        print("Live agent/tool discovery is NOT verified by installation.")
    else:
        print("Playwright agents/MCP not configured; rerun with --project to prepare them.")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (ValueError, OSError, subprocess.SubprocessError) as error:
        print(f"install: {error}", file=sys.stderr)
        print("Completed earlier stages may remain installed; no success is claimed for unfinished stages.", file=sys.stderr)
        raise SystemExit(1)
