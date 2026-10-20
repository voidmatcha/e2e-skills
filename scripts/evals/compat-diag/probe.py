#!/usr/bin/env python3
"""Diagnostic probe (NOT part of any frozen protocol): rerun ONE arm-A style call with a modified Codex argv.

Reads the frozen multimodel runner/adapters unchanged and monkeypatches only in-process. Output goes under
MULTIMODEL_V1_DIR (set it to ~/.cache/e2e-skills-bench/compat-diag-v1/<variant>). Apache-2.0.

Variants (--variant):
  control        frozen argv
  no-ephemeral   drop --ephemeral
  v1-agents      no-ephemeral + --disable multi_agent_v2 (force the stable v1 multi_agent tools)
  v2-agents      no-ephemeral + --enable multi_agent_v2
  toolscan-v1    toolscan + --disable multi_agent_v2 (ephemeral kept)
  ephemeral-v1   --disable multi_agent_v2 only, ephemeral kept, real generation prompt
  toolscan-cat   toolscan + model_catalog_json override (multi_agent_version v1 for the model)
  cat-v1         real generation prompt + catalog override (ephemeral kept)
  toolscan       frozen argv, but the prompt asks the model only to enumerate its tools, then stop
"""
from __future__ import annotations

import argparse
import importlib.util
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
os.environ.setdefault("MULTIMODEL_V1_DIR", str(Path.home() / ".cache/e2e-skills-bench/compat-diag-v1/default"))
sys.path.insert(0, str(ROOT / "scripts/evals"))


def load_runner():
    spec = importlib.util.spec_from_file_location("mm_runner", ROOT / "scripts/evals/run-generator-multimodel-v1.py")
    mod = importlib.util.module_from_spec(spec)
    sys.modules["mm_runner"] = mod
    spec.loader.exec_module(mod)
    return mod


TOOLSCAN = (
    "\n\nDiagnostic override: do NOT generate tests. Reply with the final JSON object only. In `summary` list, verbatim, "
    "the exact names of every tool/function you can call in this session (including any agent/spawn/wait/close tools "
    "and any MCP tools), and for any agent-spawning tool its parameter names. Use status `other`, spec_files []."
)


SPAWNDESC = (
    "\n\nDiagnostic override: do NOT generate tests and do NOT call any tool. Reply with the final JSON object only. In `summary` "
    "quote VERBATIM the complete description text and the complete parameter schema (names, types, descriptions, enums) of the "
    "agent-spawning tool, including any list of available agent types/roles it mentions. Use status `other`, spec_files []."
)


HINT = (
    "\n\nNote for this Codex build: the spawn tool takes no agent-type selector; a spawned agent gets the same tools as you. "
    "The initialized generator's MCP server (`playwright-test`) is therefore also declared in the project `.codex/config.toml`, "
    "so you and the agent you spawn both have its tools. Spawn a generic agent (task_name e.g. `generator`) and give it the "
    "generator definition from `.codex/agents/playwright_test_generator.toml` as its instructions."
)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--model", required=True)
    ap.add_argument("--variant", required=True,
                    choices=["control", "no-ephemeral", "v1-agents", "v2-agents", "toolscan", "toolscan-v1", "ephemeral-v1", "toolscan-cat", "cat-v1", "spawndesc", "spawndesc-cat", "mcp-project", "mcp-project-hint", "fix-nohint", "fix-hint", "toolscan-mcp", "mcp-only", "c-scratch", "compat-adapter"])
    ap.add_argument("--case", default="v2-01")
    ap.add_argument("--arm", default="A", choices=["A", "C"])
    ap.add_argument("--runner", default="codex")
    a = ap.parse_args()
    if a.variant == "compat-adapter":
        spec = importlib.util.spec_from_file_location("generator_codex_official_adapter", ROOT / "scripts/evals/generator_codex_official_adapter_compat.py")
        compat = importlib.util.module_from_spec(spec)
        sys.modules["generator_codex_official_adapter"] = compat
        spec.loader.exec_module(compat)
    mm = load_runner()
    import generator_codex_official_adapter as adapter
    if a.variant == "compat-adapter":
        orig_cfg5 = mm.configure

        def configure5(args, p, m):
            r = orig_cfg5(args, p, m)
            adapter.ARM_LINES[mm.ARM_A] = (ROOT / "scripts/evals/compat-diag/official-line-v2.txt").read_text().rstrip("\n")
            return r

        mm.configure = configure5

    orig_command = adapter.command

    def command(engine, work, private, name, model, *rest):
        argv = orig_command(engine, work, private, name, model, *rest)
        if a.variant in ("no-ephemeral", "v1-agents", "v2-agents", "fix-nohint", "fix-hint", "toolscan-mcp"):
            argv = [x for x in argv if x != "--ephemeral"]
        if a.variant in ("v1-agents", "toolscan-v1", "ephemeral-v1"):
            argv[argv.index("--strict-config"):argv.index("--strict-config")] = ["--disable", "multi_agent_v2"]
        if a.variant == "v2-agents":
            argv[argv.index("--strict-config"):argv.index("--strict-config")] = ["--enable", "multi_agent_v2"]
        if a.variant in ("toolscan-cat", "cat-v1", "spawndesc-cat"):
            cat = str(Path.home() / ".cache/e2e-skills-bench/compat-diag-v1/catalog")
            i = argv.index(engine.CODEX_CONTAINER_IMAGE)
            argv[i:i] = ["--mount", f"type=bind,src={cat},dst=/catalog,readonly"]
            j = argv.index("--strict-config")
            argv[j:j] = ["-c", 'model_catalog_json="/catalog/catalog-v1.json"']
        if a.variant in ("toolscan-mcp", "fix-hint", "fix-nohint", "mcp-only"):
            j = argv.index("--strict-config")
            argv[j:j] = ["-c", 'mcp_servers.playwright-test.command="npx"', "-c", 'mcp_servers.playwright-test.args=["playwright","run-test-mcp-server"]',
                              "-c", 'mcp_servers.playwright-test.env.PLAYWRIGHT_BROWSERS_PATH="/ms-playwright"',
                              "-c", 'mcp_servers.playwright-test.env.HOME="/codex-home"']
        print("ARGV(codex part):", " ".join(argv[argv.index("container-codex"):])[:600], flush=True)
        return argv

    adapter.command = command
    if a.variant in ("spawndesc", "spawndesc-cat"):
        orig_cfg2 = mm.configure

        def configure2(args, p, m):
            r = orig_cfg2(args, p, m)
            adapter.ARM_LINES[mm.ARM_A] = adapter.ARM_LINES[mm.ARM_A] + SPAWNDESC
            return r

        mm.configure = configure2
    if a.variant in ("toolscan", "toolscan-v1", "toolscan-cat", "toolscan-mcp"):
        orig_cfg = mm.configure

        def configure(args, p, m):
            r = orig_cfg(args, p, m)
            adapter.ARM_LINES[mm.ARM_A] = adapter.ARM_LINES[mm.ARM_A] + TOOLSCAN
            return r

        mm.configure = configure
    # keep clear of the running campaign's port ranges (6300+, 6700+)
    base_ports = mm.engine.Ports
    mm.engine.Ports = lambda _base: base_ports(7300)
    (Path(os.environ["MULTIMODEL_V1_DIR"]) / "_preflight" / a.model).mkdir(parents=True, exist_ok=True)
    if a.variant in ("mcp-project", "mcp-project-hint", "fix-nohint", "fix-hint", "toolscan-mcp", "mcp-only"):
        orig_init = mm.init_agents

        def init_agents(project, runner, p):
            out = orig_init(project, runner, p)
            toml = (project / ".codex/agents/playwright_test_generator.toml").read_text()
            block = toml[toml.index("[mcp_servers.playwright-test]"):]
            (project / ".codex/config.toml").write_text(block)
            out["compat_diag"] = "copied [mcp_servers.playwright-test] block into project .codex/config.toml"
            return out

        mm.init_agents = init_agents
    if a.variant in ("mcp-project-hint", "fix-hint"):
        orig_cfg3 = mm.configure

        def configure3(args, p, m):
            r = orig_cfg3(args, p, m)
            adapter.ARM_LINES[mm.ARM_A] = adapter.ARM_LINES[mm.ARM_A] + HINT
            return r

        mm.configure = configure3
    if a.variant == "c-scratch":
        orig_cfg4 = mm.configure

        def configure4(args, p, m):
            r = orig_cfg4(args, p, m)
            adapter.ARM_LINES[mm.ARM_C] = adapter.ARM_LINES[mm.ARM_C] + (
                " Writing the skill's temporary exploration/guard config and scratch files outside the project directory "
                "(for example under /tmp) is also approved; it does not count as editing files outside tests/ in the project.")
            return r

        mm.configure = configure4
    sys.argv = ["x", "preflight", "--model", a.model, "--case", a.case, "--runner", a.runner, "--arms", a.arm, "--allow-live"]
    return mm.main()


if __name__ == "__main__":
    raise SystemExit(main())
