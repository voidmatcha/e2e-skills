#!/usr/bin/env python3
"""Offline guards for generator-multimodel-v2-claude: schedule, freeze drift, per-arm argv and environment, init-event verifier, fidelity
and cost extraction (synthetic and stored v1 claude-sonnet-5-5 cells), the generation-phase port split and its isolation from scoring,
real-skill staging, decision and pooled rules, secondary refactor edits, v1 immutability, live refusals. No network, no model call, no
container, no execution of any built argv (Popen is faked where the call path is exercised). Apache-2.0."""
import argparse
import contextlib
import hashlib
import html.parser
import importlib.util
import io
import json
import re
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[2]


def load(name, rel):
    spec = importlib.util.spec_from_file_location(name, ROOT / rel)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


m = load("gmm_v2c_under_test", "scripts/evals/run-generator-multimodel-v2-claude.py")
ad = m.adapter
v1a = ad.v1a
SONNET = Path.home() / ".cache/e2e-skills-bench/multimodel-v1/claude-sonnet-5-5"   # a FINISHED v1 model; final.json and transcripts only
A, B, C = m.ARM_A, m.ARM_B, m.ARM_C
TASKS = m.protocol()["tasks"]
V1_FILES = {"protocol": "benchmarks/generator-multimodel-v1/protocol.json", "runner": "scripts/evals/run-generator-multimodel-v1.py",
            "claude_adapter": "scripts/evals/generator_claude_multimodel_adapter.py",
            "codex_official_adapter": "scripts/evals/generator_codex_official_adapter.py",
            "codex_shared_adapter": "scripts/evals/generator_codex_adapter_v2.py", "auth_helper": "scripts/evals/run-reviewer-holdout.py",
            "original_runner": "scripts/evals/run-generator-official-pilot-v1.py",
            "original_protocol": "benchmarks/generator-official-pilot-v1/protocol.json",
            "original_freeze": "benchmarks/generator-official-pilot-v1/freeze.json",
            "reviewer_runner": "scripts/evals/run-generator-official-reviewer-pilot-v1.py",
            "reviewer_protocol": "benchmarks/generator-official-reviewer-pilot-v1/protocol.json",
            "reviewer_freeze": "benchmarks/generator-official-reviewer-pilot-v1/freeze.json",
            "dockerfile": "scripts/evals/generator-codex-container/Dockerfile", "fixture_package": "scripts/evals/fixtures/package.json",
            "fixture_lock": "scripts/evals/fixtures/package-lock.json"}


def sha256(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def flip_last_byte(target):
    """A digest function that behaves like orig.digest except that `target` hashes as if its last byte had changed."""
    real = m.orig.digest

    def digest(path):
        if Path(path).resolve() == Path(target).resolve():
            data = Path(path).read_bytes()
            return hashlib.sha256(data[:-1] + bytes([data[-1] ^ 1])).hexdigest()
        return real(path)
    return digest


# ------------------------------------------------------------------------------------------------ synthetic stream helpers

def init(arm, **over):
    base = {"type": "system", "subtype": "init", "cwd": "/w/project", "model": "claude-sonnet-5-5", "slash_commands": [], "skills": [],
            "mcp_servers": [], "agents": ["claude", "Explore", "general-purpose", "Plan"],
            "plugins": [{"name": "cc-plugin-agents-md", "path": "builtin", "source": "x@builtin"}],
            "tools": ["Task", "Bash", "Edit", "Glob", "Grep", "Read", "StructuredOutput", "Write", "Skill"]}
    if arm == A:
        base.update(agents=base["agents"] + ["playwright-test-generator", "playwright-test-healer", "playwright-test-planner"],
                    mcp_servers=[{"name": "playwright-test", "status": "connected"}],
                    tools=["Task", "Bash", "Glob", "Grep", "Read", "StructuredOutput", "mcp__playwright-test__generator_setup_page",
                           "mcp__playwright-test__generator_write_test", "mcp__playwright-test__browser_click"])
    elif arm == B:
        base["skills"] = ["e2e-reviewer"]
    else:
        base["skills"] = ["playwright-test-generator", "e2e-reviewer"]
    base.update(over)
    return base


def use(name, inp, uid, parent=None):
    return {"type": "assistant", "parent_tool_use_id": parent, "message": {"content": [{"type": "tool_use", "id": uid, "name": name, "input": inp}]}}


def res(uid, text):
    return {"type": "user", "message": {"content": [{"type": "tool_result", "tool_use_id": uid, "content": text}]}}


def result_event(status="complete", usage=None, cost=0.5):
    return {"type": "result", "subtype": "success", "is_error": False, "num_turns": 3, "total_cost_usd": cost,
            "modelUsage": usage or {"claude-sonnet-5-5": {"inputTokens": 10, "outputTokens": 200, "cacheReadInputTokens": 1000,
                                                          "cacheCreationInputTokens": 50, "costUSD": cost}},
            "usage": {"input_tokens": 1, "output_tokens": 2}, "structured_output": {"spec_files": ["tests/a.spec.ts"], "status": status, "summary": "s"}}


LONG_SCAN = ("cd /w/project/.claude/skills/e2e-reviewer/.. && cd /w/project && " + "E2E_SMELL_ALLOW_PROJECT_ESLINT=0 E2E_SMELL_NO_ESLINT_DOWNLOAD=1 E2E_SMELL_NO_AST_GREP_DOWNLOAD=1 "
             "E2E_SMELL_DISABLE_AST_GREP=1 /usr/bin/env -u E2E_SMELL_RG_BIN -u E2E_SMELL_NODE_BIN -u E2E_SMELL_NPX_BIN -u E2E_SMELL_AST_GREP_BIN "
             "-u E2E_SMELL_PYTHON_BIN -u E2E_SMELL_TIMEOUT_BIN -u E2E_SMELL_EXTRA_BIN "
             "/bin/bash -p /w/project/.claude/skills/e2e-reviewer/scripts/scan.sh tests/a.spec.ts")


def c_stream():
    sk = "/w/project/.claude/skills/playwright-test-generator/"
    return [init(C),
            use("Skill", {"skill": "playwright-test-generator"}, "s1"),
            use("Read", {"file_path": sk + "code-rules.md"}, "r1"),
            use("Bash", {"command": f"sed -n 1,200p {sk}verification-rules.md"}, "r2"),
            use("Bash", {"command": f"{sk}scripts/run-preflight-target.sh http://127.0.0.1:1/ /"}, "p1"),
            use("Bash", {"command": "npx --no-install playwright cli open http://127.0.0.1:1/"}, "x1"),
            use("Bash", {"command": "node_modules/.bin/playwright test tests/smoke.spec.mjs"}, "b1"),
            use("Write", {"file_path": "/w/project/tests/a.spec.ts", "content": "x"}, "w1"),
            use("Bash", {"command": LONG_SCAN}, "sc1"),
            use("Bash", {"command": "node_modules/.bin/playwright test tests/a.spec.ts --repeat-each 2"}, "t1"),
            use("Agent", {"subagent_type": "general-purpose", "description": "Independent V6 review", "prompt": "Apply the e2e-reviewer skill"}, "ag1"),
            result_event()]


class ArgvAndEnvironment(unittest.TestCase):
    schema = m.engine.OUTPUT_SCHEMA

    def v1(self, arm):
        return v1a.command(arm, "claude-sonnet-5-5", self.schema, 30.0, "/w")

    def v2(self, arm):
        return ad.command(arm, "claude-sonnet-5-5", self.schema, 30.0, "/w", "/w/mcp.json" if arm == A else None)

    @staticmethod
    def pairs(cmd):
        out, i = {}, 0
        while i < len(cmd):
            if cmd[i].startswith("--") and i + 1 < len(cmd) and not cmd[i + 1].startswith("--"):
                out[cmd[i]] = cmd[i + 1]
                i += 2
            else:
                out[cmd[i]] = True
                i += 1
        return out

    def test_arm_a_differs_from_v1_only_by_the_mcp_config_path_and_the_settings_deny_list(self):
        a, b = self.pairs(self.v1(A)), self.pairs(self.v2(A))
        self.assertEqual({k for k in a if a[k] != b.get(k)} | {k for k in b if k not in a}, {"--mcp-config", "--settings"})
        self.assertEqual((a["--mcp-config"], b["--mcp-config"]), (".mcp.json", "/w/mcp.json"))
        for flag in ("--disable-slash-commands", "--strict-mcp-config"):
            self.assertIn(flag, self.v2(A))
        self.assertEqual(b["--tools"], v1a.OFFICIAL_TOOLS)
        self.assertNotIn("Skill", b["--allowedTools"])
        self.assertEqual(b["--setting-sources"], "project")

    def test_arms_b_and_c_install_real_skills_and_differ_from_v1_in_exactly_these_flags(self):
        for arm, rules in ((B, ["Skill(e2e-reviewer)"]), (C, ["Skill(playwright-test-generator)", "Skill(e2e-reviewer)"])):
            a, b = self.pairs(self.v1(arm)), self.pairs(self.v2(arm))
            changed = {k for k in a if a[k] != b.get(k)} | {k for k in b if k not in a}
            self.assertEqual(changed, {"--disable-slash-commands", "--setting-sources", "--tools", "--allowedTools", "--settings"}, arm)
            self.assertNotIn("--disable-slash-commands", self.v2(arm))
            self.assertEqual((a["--setting-sources"], b["--setting-sources"]), ("", "project"))
            self.assertEqual(b["--tools"], v1a.BASE_TOOLS + ",Skill")
            self.assertEqual(b["--allowedTools"], v1a.BASE_TOOLS + "," + ",".join(rules))
            self.assertNotIn("--mcp-config", self.v2(arm))
            self.assertIn("--strict-mcp-config", self.v2(arm))

    def test_settings_deny_list_extends_v1_with_the_running_checkout(self):
        for arm in (A, B, C):
            deny = json.loads(self.pairs(self.v2(arm))["--settings"])["permissions"]["deny"]
            self.assertTrue(set(v1a.DENY) <= set(deny))
            self.assertIn(f"Read({ROOT}/skills/**)", deny)

    def test_environment_never_carries_the_port_variable_and_pins_the_subagent_model(self):
        env = ad.build_env("claude-sonnet-5-5", {"PATH": "/bin", ad.PORT_ENV: "9999", "CLAUDECODE": "1", "CLAUDE_CODE_ENTRYPOINT": "x"})
        self.assertNotIn(ad.PORT_ENV, env)
        self.assertNotIn("CLAUDECODE", env)
        self.assertEqual((env["CLAUDE_CODE_SUBAGENT_MODEL"], env["CLAUDE_CODE_DISABLE_AUTO_MEMORY"], env["PATH"]), ("claude-sonnet-5-5", "1", "/bin"))

    def test_mcp_config_copy_adds_the_port_env_and_leaves_the_project_file_alone(self):
        with tempfile.TemporaryDirectory() as tmp:
            project, work = Path(tmp) / "project", Path(tmp)
            project.mkdir()
            original = json.dumps({"mcpServers": {"playwright-test": {"command": "npx", "args": ["playwright", "run-test-mcp-server"]}}})
            (project / ".mcp.json").write_text(original)
            path = ad.write_mcp_config(project, work, 12345)
            cfg = json.loads(path.read_text())["mcpServers"]["playwright-test"]
            self.assertEqual((cfg["command"], cfg["args"], cfg["env"]), ("npx", ["playwright", "run-test-mcp-server"], {ad.PORT_ENV: "32345"}))
            self.assertEqual((project / ".mcp.json").read_text(), original)
            self.assertNotIn(project, path.parents)
            (project / ".mcp.json").write_text(json.dumps({"mcpServers": {"playwright-test": {}, "other": {}}}))
            with self.assertRaises(ValueError):
                ad.write_mcp_config(project, work, 1)

    def test_building_the_argv_executes_nothing(self):
        with patch("subprocess.run", side_effect=AssertionError("executed")), patch("subprocess.Popen", side_effect=AssertionError("executed")):
            for arm in (A, B, C):
                self.v2(arm)
            ad.build_env("x")
        with self.assertRaises(ValueError):
            ad.command(A, "x", self.schema, 1.0, "/w")

    def test_arm_lines(self):
        lines = m.arm_lines()
        self.assertEqual(lines[A], m.v1.CLAUDE_OFFICIAL_LINE)
        for arm, names in ((B, ("e2e-reviewer",)), (C, ("playwright-test-generator", "e2e-reviewer"))):
            for name in names:
                self.assertIn(f"`{name}` skill", lines[arm])
            self.assertNotIn("/SKILL.md", lines[arm])                   # the prompt does not point at file paths
            self.assertNotIn("`Skill` tool is not available", lines[arm])
        self.assertIn("Then FIX every finding", lines[B])
        self.assertTrue(lines[B].endswith(m.rev.REVIEW_LINE[m._FIX_START:]))
        self.assertTrue(lines[C].endswith(m.C_SCRATCH))
        lock = m.read(m.V1_LOCK)["bindings"]["prompt_lines"]
        self.assertEqual(m.orig.sha(m.A_LINE), lock["official_claude"])
        for text in (lines[B], lines[C]):
            self.assertNotIn(str(Path.home()), text)


class InitVerifier(unittest.TestCase):
    def ok(self, arm, **over):
        return ad.check_init(arm, init(arm, **over), "claude-sonnet-5-5", bundled_allowed=set())

    def test_intended_configuration_passes_for_every_arm(self):
        for arm in (A, B, C):
            self.assertEqual(self.ok(arm), [], arm)

    def test_arm_a_violations(self):
        self.assertTrue(any("lists skills" in p for p in self.ok(A, skills=["e2e-reviewer"])))
        self.assertTrue(any("Skill tool" in p for p in self.ok(A, tools=init(A)["tools"] + ["Skill"])))
        self.assertTrue(any("write or web" in p for p in self.ok(A, tools=init(A)["tools"] + ["Write"])))
        self.assertTrue(any("generator subagent" in p for p in self.ok(A, agents=["claude"])))
        self.assertTrue(any("mcp servers differ" in p for p in self.ok(A, mcp_servers=[])))
        self.assertTrue(any("slash commands" in p for p in self.ok(A, slash_commands=["review"])))
        self.assertTrue(any("generator MCP tools" in p for p in self.ok(A, tools=["Task", "Bash", "Read"])))

    def test_arms_b_and_c_violations(self):
        for arm in (B, C):
            self.assertTrue(any("intended skills not listed" in p for p in self.ok(arm, skills=[])))
            self.assertTrue(any("unintended skills" in p for p in self.ok(arm, skills=init(arm)["skills"] + ["frontend-design"])))
            self.assertTrue(any("Skill missing" in p for p in self.ok(arm, tools=[t for t in init(arm)["tools"] if t != "Skill"])))
            self.assertTrue(any("playwright agents" in p for p in self.ok(arm, agents=["claude", "playwright-test-generator"])))
            self.assertTrue(any("mcp" in p for p in self.ok(arm, mcp_servers=[{"name": "playwright-test", "status": "connected"}])))
            self.assertTrue(any("web tools" in p for p in self.ok(arm, tools=init(arm)["tools"] + ["WebFetch"])))
        self.assertTrue(any("e2e-reviewer" in p for p in self.ok(C, skills=["playwright-test-generator"])))
        self.assertEqual(self.ok(B, skills=["e2e-reviewer", "playwright-test-generator"]) != [], True)   # the generator skill must not leak into B

    def test_model_plugins_and_prefixed_skills(self):
        self.assertTrue(any("init model" in p for p in self.ok(B, model="claude-haiku-5-5")))
        self.assertEqual(self.ok(B, model="claude-sonnet-5-5[1m]"), [])
        self.assertTrue(any("non-builtin plugin" in p for p in self.ok(B, plugins=[{"name": "local", "path": "/x", "source": "y"}])))
        self.assertTrue(any("unintended" in p for p in self.ok(B, skills=["e2e-reviewer", "e2e-skills:e2e-reviewer"])))
        alone = self.ok(B, skills=["e2e-skills:e2e-reviewer"])      # a plugin-prefixed skill is not the project skill
        self.assertTrue(any("intended skills not listed" in p for p in alone) and any("unintended" in p for p in alone))

    def test_bundled_skills_are_allowed_only_when_declared(self):
        extra = init(B, skills=["e2e-reviewer", "simplify"])
        self.assertTrue(ad.check_init(B, extra, bundled_allowed=set()))
        self.assertEqual(ad.check_init(B, extra, bundled_allowed={"simplify"}), [])
        self.assertTrue(ad.check_init(B, init(B, skills=["simplify"]), bundled_allowed={"simplify"}))   # intended skill still required

    def test_every_init_event_is_checked_and_no_init_is_a_violation(self):
        bad = init(A, skills=["x"])
        out = ad.check_isolation(A, [init(A), bad], "claude-sonnet-5-5", bundled_allowed=set())
        self.assertTrue(out and out[0].startswith("[init 2]"))
        self.assertEqual(ad.check_isolation(A, [init(A), init(A)], "claude-sonnet-5-5", bundled_allowed=set()), [])
        self.assertEqual(ad.check_isolation(A, [], "x"), ["no system/init event"])

    @unittest.skipUnless((SONNET / "final.json").is_file(), "stored v1 claude-sonnet-5-5 cells not present")
    def test_stored_v1_init_events(self):
        report = m.read(SONNET / "final.json")
        seen = {A: 0, B: 0, C: 0}
        for rec in report["runs"]:
            events = m.transcript_events(rec, SONNET / "final-transcripts")
            inits = [e for e in events if e.get("type") == "system" and e.get("subtype") == "init"]
            problems = ad.check_isolation(rec["arm"], inits, "claude-sonnet-5-5", bundled_allowed=set())
            seen[rec["arm"]] += 1
            if rec["arm"] == A:
                self.assertEqual(problems, [], rec["call_id"])           # v1 arm A satisfies the v2 arm A contract on every init event
            else:
                self.assertTrue(any("intended skills not listed" in p for p in problems), rec["call_id"])   # v1 B and C had no skills
                self.assertTrue(any("Skill missing" in p for p in problems))
        self.assertEqual(seen, {A: 12, B: 12, C: 12})
        self.assertGreaterEqual(sum(1 for r in report["runs"] if r["arm"] == A and
                                    len([e for e in m.transcript_events(r, SONNET / "final-transcripts") if e.get("subtype") == "init"]) == 2), 10)

    @unittest.skipUnless((SONNET / "final.json").is_file(), "stored v1 claude-sonnet-5-5 cells not present")
    def test_inspect_init_subcommand_on_a_stored_stream(self):
        rec = next(r for r in m.read(SONNET / "final.json")["runs"] if r["arm"] == C)
        path = SONNET / "final-transcripts" / Path(rec["transcript_path"]).name
        with contextlib.redirect_stdout(io.StringIO()):
            self.assertEqual(m.inspect_init(argparse.Namespace(arm="C", file=str(path), model="claude-sonnet-5-5")), 5)
            rec_a = next(r for r in m.read(SONNET / "final.json")["runs"] if r["arm"] == A)
            self.assertEqual(m.inspect_init(argparse.Namespace(arm="A", file=str(SONNET / "final-transcripts" / Path(rec_a["transcript_path"]).name), model="claude-sonnet-5-5")), 0)


class Fidelity(unittest.TestCase):
    def test_arm_c_steps_from_a_synthetic_stream(self):
        out = ad.analyze_events(c_stream(), C)
        f = out["fidelity"]
        self.assertTrue(f["generator_skill_loaded"] and f["invoked"] and f["treated"])
        self.assertEqual((f["generator_refs_via_read_tool"], f["generator_refs_via_bash"]), (["code-rules.md"], ["verification-rules.md"]))
        self.assertEqual(f["hot_refs_read"], ["code-rules.md", "verification-rules.md"])
        self.assertEqual((f["preflight_runs"], f["exploration_runs"], f["scan_sh_runs"], f["scan_sh_pinned_runs"]), (1, 1, 1, 1))
        self.assertEqual((f["baseline_runs"], f["targeted_runs"], f["repeat_each_runs"], f["independent_review_agents"]), (1, 1, 1, 1))
        flags = m.step_flags(C, f, "complete")
        self.assertEqual(list(flags), m.STEP_NAMES[C])
        self.assertTrue(all(flags.values()))
        self.assertFalse(m.step_flags(C, f, "partial_or_blocked")["final_status_complete"])

    def test_the_engine_truncates_long_commands_and_the_adapter_does_not(self):
        events = c_stream()
        self.assertGreater(len(LONG_SCAN), 400)
        self.assertEqual(m.engine.compliance_from_events(events, Path("/w/project"))["scanner_runs"], 0)    # v1 / engine: missed
        out = ad.analyze_events(events, C)
        self.assertEqual((out["scanner_runs"], out["fidelity"]["scan_sh_runs"]), (1, 1))                    # v2: counted on the full command
        self.assertGreater(out["bash_command_max_chars"], 400)

    def test_untreated_c_stream_and_review_agents_before_the_first_write_do_not_count(self):
        events = [init(C), use("Read", {"file_path": "/w/project/.claude/skills/playwright-test-generator/SKILL.md"}, "r"),
                  use("Agent", {"subagent_type": "Explore", "description": "review the page", "prompt": "x"}, "a"),
                  use("Write", {"file_path": "/w/project/tests/a.spec.ts", "content": "x"}, "w"), result_event("partial_or_blocked")]
        f = ad.analyze_events(events, C)["fidelity"]
        self.assertEqual((f["generator_skill_loaded"], f["invoked"], f["treated"], f["independent_review_agents"], f["agent_spawns"]), (True, True, False, 0, 1))

    def test_a_spec_written_through_bash_splits_baseline_and_targeted_runs(self):
        events = [init(C), use("Bash", {"command": "node_modules/.bin/playwright test"}, "b"),
                  use("Bash", {"command": "cat > tests/a.spec.ts <<'EOF'\nimport x\nEOF\nnode_modules/.bin/playwright test tests/a.spec.ts"}, "w"),
                  use("Bash", {"command": "python3 - <<'E'\np='tests/a.spec.ts'\ns=open(p).read()\nE"}, "r"), result_event()]
        f = ad.analyze_events(events, C)["fidelity"]
        self.assertEqual((f["baseline_runs"], f["targeted_runs"], f["playwright_test_runs"]), (1, 1, 2))
        read_only = [init(C), use("Bash", {"command": "python3 - <<'E'\np='tests/a.spec.ts'\ns=open(p).read()\nE"}, "r"),
                     use("Bash", {"command": "node_modules/.bin/playwright test"}, "b"), result_event()]
        self.assertEqual(ad.analyze_events(read_only, C)["fidelity"]["baseline_runs"], 1)       # a read-only heredoc is not a write

    def test_arm_a_counts_child_tool_calls_and_the_port_conflict(self):
        pre = "mcp__playwright-test__"
        events = [init(A), use("Agent", {"subagent_type": "playwright-test-generator", "description": "g", "prompt": "p"}, "ag"),
                  use(pre + "generator_setup_page", {}, "c1", parent="ag"), use(pre + "browser_click", {}, "c2", parent="ag"),
                  use(pre + "generator_write_test", {"fileName": "tests/a.spec.ts", "code": "x"}, "c3", parent="ag"),
                  res("c1", "page set up"), res("c2", "clicked"), res("c3", "written"),
                  use("Bash", {"command": "node_modules/.bin/playwright test tests/a.spec.ts 2>&1 | tail -30"}, "pt"),
                  res("pt", "Error: http://127.0.0.1:6304/health is already used, make sure that nothing is running on the port/url"), result_event()]
        f = ad.analyze_events(events, A)["fidelity"]
        self.assertEqual((f["generator_spawned"], f["generator_setup_page_calls"], f["generator_write_test_calls"], f["browser_tool_calls"]), (True, 1, 1, 1))
        self.assertEqual((f["child_tool_uses"], f["stream_tool_uses"], f["port_conflicts_in_playwright_test"], f["server_started_by_model"]), (3, 5, 1, 0))
        self.assertTrue(f["invoked"] and f["treated"])
        flags = m.step_flags(A, f, "other")
        self.assertEqual((flags["write_test"], flags["port_conflict"], flags["planner_or_healer_used"]), (True, True, False))
        self.assertFalse(ad.analyze_events([init(A), use("Agent", {"subagent_type": "playwright-test-generator"}, "x"), result_event()], A)["fidelity"]["treated"])

    def test_arm_b_steps(self):
        events = [init(B), use("Skill", {"skill": "e2e-reviewer"}, "s"), use("Read", {"file_path": "/w/project/.claude/skills/e2e-reviewer/references/semantic-review.md"}, "r"),
                  use("Bash", {"command": "/bin/bash -p .claude/skills/e2e-reviewer/scripts/scan.sh tests/a.spec.ts"}, "sc"),
                  use("Edit", {"file_path": "/w/project/tests/a.spec.ts", "old_string": "a", "new_string": "b"}, "e"),
                  use("Bash", {"command": "node_modules/.bin/playwright test tests/a.spec.ts"}, "t"), result_event()]
        f = ad.analyze_events(events, B)["fidelity"]
        self.assertTrue(f["reviewer_skill_loaded"] and f["treated"])
        self.assertEqual(f["reviewer_refs_read"], ["semantic-review.md"])
        self.assertEqual(list(m.step_flags(B, f, "complete")), m.STEP_NAMES[B])
        self.assertTrue(m.step_flags(B, f, "complete")["edit_calls"])
        self.assertFalse(ad.analyze_events([init(B), use("Skill", {"skill": "e2e-reviewer"}, "s"), result_event()], B)["fidelity"]["treated"])

    def test_home_paths_outside_the_work_directory_are_audited(self):
        home = str(Path.home())
        events = [init(C), use("Read", {"file_path": f"{home}/secret/x"}, "r"), use("Bash", {"command": f"cat {home}/other/y; ls /w/project"}, "b"), result_event()]
        out = ad.analyze_events(events, C, Path("/w/project"), Path("/w"))
        self.assertEqual(len(out["home_paths_touched_outside_work"]), 2)

    @unittest.skipUnless((SONNET / "final.json").is_file(), "stored v1 claude-sonnet-5-5 cells not present")
    def test_stored_sonnet_cells_reproduce_the_audit(self):
        report = m.read(SONNET / "final.json")
        fid = {A: [], B: [], C: []}
        engine_scan = 0
        for rec in report["runs"]:
            events = m.transcript_events(rec, SONNET / "final-transcripts")
            fid[rec["arm"]].append((rec, ad.analyze_events(events, rec["arm"])["fidelity"]))
            engine_scan += rec["arm"] == C and rec["compliance"]["scanner_runs"] > 0
        count = lambda arm, pred: sum(bool(pred(f)) for _, f in fid[arm])
        # arm C (audit: reference reads 0/12, scan.sh 6/12 vs the engine's 2/12, independent review 1/12, self-reported complete 0/12)
        self.assertEqual(count(C, lambda f: f["generator_refs_via_read_tool"]), 0)
        self.assertEqual(count(C, lambda f: f["generator_refs_via_bash"]), 3)       # sed/cat through Bash: invisible to a Read-tool-only count
        self.assertEqual(count(C, lambda f: f["scan_sh_runs"] >= 1), 6)
        self.assertEqual(engine_scan, 2)
        self.assertEqual(count(C, lambda f: f["independent_review_agents"] >= 1), 1)
        self.assertEqual(sum((r["structured_output"] or {}).get("status") == "complete" for r, _ in fid[C]), 0)
        self.assertEqual(count(C, lambda f: f["generator_skill_loaded"]), 12)
        self.assertEqual((count(C, lambda f: f["preflight_runs"]), count(C, lambda f: f["exploration_runs"])), (0, 0))
        self.assertEqual(count(C, lambda f: f["treated"]), 1)
        # arm A (audit: generator tools 12/12, port-in-use 12/12)
        self.assertEqual(count(A, lambda f: f["generator_setup_page_calls"] >= 1 and f["generator_write_test_calls"] >= 1), 12)
        self.assertEqual(count(A, lambda f: f["port_conflicts_in_playwright_test"] >= 1), 12)
        self.assertEqual(count(A, lambda f: f["server_started_by_model"]), 0)
        self.assertEqual(count(A, lambda f: f["child_tool_uses"] > 0), 12)
        self.assertEqual(count(A, lambda f: f["treated"]), 12)
        # arm B
        self.assertEqual(count(B, lambda f: f["reviewer_skill_loaded"] and f["scan_sh_runs"] >= 1 and f["playwright_test_runs"] >= 1), 12)
        self.assertEqual(count(B, lambda f: f["write_or_edit_calls"] + f["bash_edit_calls"] >= 1), 9)
        # about 55 s per C cell
        secs = sorted(r["elapsed_ms"] / 1000 for r, _ in fid[C])
        self.assertTrue(40 <= (secs[5] + secs[6]) / 2 <= 70, secs)

    @unittest.skipUnless((SONNET / "scores.json").is_file(), "stored v1 claude-sonnet-5-5 scores not present")
    def test_stored_sonnet_primary_metric_decomposition(self):
        report, scores = m.read(SONNET / "final.json"), m.read(SONNET / "scores.json")
        by = {m.v1.identity(r): r for r in report["runs"]}
        tokens = {t: m.renamed_tokens(t) for t in TASKS}
        table = {}
        for s in scores["scores"]:
            if s["clean"]:
                ref = m.selector_reference(SONNET, by[m.v1.identity(s)], tokens[s["case"]])
                table[(ref, bool(s["refactor_score"]))] = table.get((ref, bool(s["refactor_score"])), 0) + 1
        self.assertEqual(table, {(True, False): 8, (False, True): 25})     # naming a renamed selector always failed, naming none always survived


class SelectorHeuristic(unittest.TestCase):
    def test_literals_skip_comments_and_see_selectors(self):
        self.assertEqual(m.string_literals("a = 'x'; // it's\nb = \"y\\\"z\" /* ' */ `t`"), ["'x'", '"y\\"z"', "`t`"])
        for text, token, expected in (("page.locator('article.deck')", "deck", True), ("page.locator('#fc-flip')", "fc-flip", True),
                                      ("page.locator('[id=\"fc-flip\"]')", "fc-flip", True), ("getByText('Session done')", "done", False),
                                      ("expect(stats.done)", "done", False), ("// '.deck'\npage.getByRole('button')", "deck", False),
                                      ("page.locator('.decks')", "deck", False)):
            self.assertEqual(m.references_token(text, token), expected, text)

    def test_tokens_include_classes_set_from_script_and_bare_edits(self):
        self.assertIn("deck", m.renamed_tokens("v3-09"))
        self.assertIn("track", m.renamed_tokens("v3-04"))
        self.assertIn("chip", m.renamed_tokens("v2-06"))
        self.assertTrue(set(m.engine.refactor_manifest((m.engine.CASES / "v3-09" / "app.mjs").read_text(), m.engine.load_truth("v3-09")["refactor"])
                            ["renamed_ids_and_classes"]) <= set(m.renamed_tokens("v3-09")))

    def test_decomposition_table(self):
        mk = lambda clean, ref, score: {"clean": clean, "aborted": False, "references_renamed_selector": ref, "refactor_score": score}
        cells = [mk(True, True, 0.0), mk(True, True, 0.0), mk(True, False, 1.0), mk(True, False, 1.0), mk(True, False, 0.0), mk(False, None, 0.0), mk(True, None, 1.0)]
        d = m.decomposition(cells)
        self.assertEqual((d["clean_cells"], d["clean_with_selector_status"], d["clean_referencing_renamed_selector"], d["clean_referencing_failed_refactor"],
                          d["clean_not_referencing"], d["clean_not_referencing_failed_refactor"]), (6, 5, 2, 2, 3, 1))
        self.assertEqual(d["clean_conditional_survival"], round(3 / 6, 4))
        self.assertEqual(d["primary_survival"], round(3 / 7, 4))


class CostAccounting(unittest.TestCase):
    def test_model_usage_aggregation_includes_every_model(self):
        usage = {"claude-sonnet-5-5": {"inputTokens": 10, "outputTokens": 100, "cacheReadInputTokens": 1000, "cacheCreationInputTokens": 50, "costUSD": 0.3},
                 "claude-haiku-5-5": {"inputTokens": 5, "outputTokens": 20, "cacheReadInputTokens": 200, "cacheCreationInputTokens": 0, "costUSD": 0.1}}
        c = ad.cost_summary(usage, 0.4)
        self.assertEqual((c["uncached_input"], c["cache_read"], c["cache_creation"], c["output"], c["processed_tokens"], c["total_tokens"]), (15, 1200, 50, 120, 185, 1385))
        self.assertEqual((c["cost_usd"], c["cost_matches_envelope"]), (0.4, True))
        self.assertEqual(ad.normalized_usage({"modelUsage": usage, "total_cost_usd": 0.4}),
                         {"input_tokens": 1265, "cached_input_tokens": 1200, "output_tokens": 120, "cache_creation_input_tokens": 50, "uncached_input_tokens": 15})
        rec_cost = m.cost_of({"model_usage": usage, "cost_usd": 0.4})
        self.assertEqual((rec_cost["processed"], rec_cost["total_tokens"], rec_cost["measured"]), (185, 1385, True))
        self.assertEqual(m.cost_of({})["measured"], False)

    def cells(self):
        def cell(arm, rep, processed, total, score, secs, measured=True):
            return {"case": "t", "arm": arm, "repetition": rep, "refactor_score": score, "elapsed_s": secs, "_model": "x", "models_used": [],
                    "invoked": True, "treated": True, "load_flagged": False,
                    "cost": {"uncached_input": processed, "cache_creation": 0, "cache_read": total - processed, "output": 0, "processed": processed,
                             "total_tokens": total, "cost_usd": total / 1e6, "measured": measured}}
        return [cell(A, 1, 100000, 400000, 0.0, 30), cell(B, 1, 50000, 100000, 1.0, 20), cell(C, 1, 150000, 300000, 1.0, 40)]

    def test_pipeline_totals_and_quality_per_100k(self):
        cells = self.cells()
        m.attach_pipeline(cells)
        self.assertEqual([(c["pipeline_processed"], c["pipeline_total"], c["pipeline_seconds"], c["pipeline_complete"]) for c in cells],
                         [(100000, 400000, 30.0, True), (150000, 500000, 50.0, True), (150000, 300000, 40.0, True)])
        table = m.cost_table(cells)
        self.assertEqual(table[A]["quality_per_100k_processed"], 0.0)
        self.assertEqual(table[B]["quality_per_100k_processed"], round(100000 * 1.0 / 150000, 4))     # B is charged for A plus the reviewer
        self.assertEqual(table[B]["quality_per_100k_total"], round(100000 * 1.0 / 500000, 4))
        self.assertEqual(table[C]["pipeline"]["seconds_per_cell"], 40.0)
        self.assertEqual(table[C]["pipeline"]["seconds_per_survivor"], 40.0)
        self.assertIsNone(table[A]["pipeline"]["seconds_per_survivor"])                                 # no survivor
        self.assertEqual(m.metric_value([cells[1]], "quality_per_100k_processed"), 100000 / 150000)
        self.assertEqual(m.metric_value([cells[1]], "quality_per_100k_total"), 100000 / 500000)

    def test_incomplete_token_records_are_counted_and_excluded_from_the_ratio_of_sums(self):
        cells = self.cells()
        cells[0]["cost"]["measured"] = False                       # the source A cell has no modelUsage: the B pipeline is incomplete too
        m.attach_pipeline(cells)
        self.assertEqual([c["pipeline_complete"] for c in cells], [False, False, True])
        table = m.cost_table(cells)
        self.assertEqual((table[B]["cells"], table[B]["cells_with_complete_tokens"], table[B]["quality_per_100k_processed"]), (1, 0, None))
        self.assertIsNone(m.metric_value([cells[1]], "quality_per_100k_processed"))
        self.assertEqual(table[C]["quality_per_100k_processed"], round(100000 / 150000, 4))

    @unittest.skipUnless((SONNET / "final.json").is_file(), "stored v1 claude-sonnet-5-5 cells not present")
    def test_stored_cells_cost_from_model_usage_includes_the_async_subagent(self):
        report = m.read(SONNET / "final.json")
        for rec in report["runs"]:
            cost = ad.cost_summary(rec["model_usage"], rec["cost_usd"])
            self.assertTrue(cost["cost_matches_envelope"], rec["call_id"])
        rec = next(r for r in report["runs"] if r["arm"] == A)
        cost = ad.cost_summary(rec["model_usage"], rec["cost_usd"])
        self.assertGreater(cost["total_tokens"], rec["usage"]["input_tokens"] + rec["usage"]["output_tokens"])   # the v1 'usage' is the last turn only


class PortSplit(unittest.TestCase):
    def staged(self, case):
        tmp = Path(tempfile.mkdtemp(prefix="v2c-test-")).resolve()
        self.addCleanup(shutil.rmtree, tmp, True)
        return m.engine.stage(m.engine.CASES / case, 6304, tmp, git=False)

    def test_scoring_stage_is_untouched_and_the_generation_transform_is_a_pure_addition(self):
        for case in TASKS + [m.protocol()["preflight_task"]["task"]]:
            project = self.staged(case)
            cfg0, app0 = (project / "playwright.config.mjs").read_text(), (project / "app.mjs").read_text()
            self.assertIn("reuseExistingServer: false", cfg0)
            self.assertNotIn(ad.PORT_ENV, cfg0 + app0)
            self.assertEqual(cfg0, (m.engine.CASES / case / "playwright.config.mjs").read_text().replace("__PORT__", "6304"))
            summary = m.gen_transform(project, 6304)
            cfg1, app1 = (project / "playwright.config.mjs").read_text(), (project / "app.mjs").read_text()
            self.assertEqual(summary, {"mode": "split-port", "port": 6304, "mcp_port": 26304})
            self.assertIn("reuseExistingServer: false", cfg1)                       # the generation config keeps it too
            self.assertEqual(cfg1.count(ad.PORT_ENV), 2)
            self.assertEqual(app1.count(ad.PORT_ENV), 1)
            self.assertIn("process.env.E2E_APP_PORT ?? 6304", app1)
            # with the variable unset every expression evaluates to the original port: evaluating the defaults restores the original text
            evaluated = re.sub(r"`(http://127\.0\.0\.1:)\$\{process\.env\.E2E_APP_PORT \?\? 6304\}([^`]*)`", r'"\g<1>6304\g<2>"', cfg1)
            self.assertEqual(evaluated, cfg0)
            self.assertEqual(app1, app0.replace("const PORT = 6304;", "const PORT = Number(process.env.E2E_APP_PORT ?? 6304);"))
            # a second scoring-side stage of the same case is unaffected
            self.assertEqual((self.staged(case) / "playwright.config.mjs").read_text(), cfg0)

    def test_transform_parses_as_javascript(self):
        node = shutil.which("node")
        if not node:
            self.skipTest("node not available")
        for case in TASKS[:2]:
            project = self.staged(case)
            m.gen_transform(project, 6304)
            for name in ("app.mjs", "playwright.config.mjs"):
                done = subprocess.run([node, "--check", str(project / name)], capture_output=True, text=True, timeout=60)
                self.assertEqual(done.returncode, 0, done.stderr)

    def test_fail_closed_when_a_marker_is_missing_or_repeated(self):
        project = self.staged(TASKS[0])
        (project / "app.mjs").write_text((project / "app.mjs").read_text().replace("const PORT = 6304;", "const PORT = 1;"))
        with self.assertRaisesRegex(ValueError, "PORT constant"):
            m.gen_transform(project, 6304)
        with self.assertRaises(ValueError):
            m.gen_transform(self.staged(TASKS[0]), 6304, "bogus")

    def test_reuse_fallback_flips_only_that_line(self):
        project = self.staged(TASKS[0])
        before = (project / "playwright.config.mjs").read_text()
        m.gen_transform(project, 6304, "reuse")
        self.assertEqual((project / "playwright.config.mjs").read_text(), before.replace("reuseExistingServer: false,", "reuseExistingServer: true,"))
        self.assertNotIn(ad.PORT_ENV, (project / "app.mjs").read_text())

    def test_the_transform_has_a_single_call_site_and_scoring_functions_are_the_engines(self):
        source = Path(m.__file__).read_text()
        self.assertEqual(len(re.findall(r"\bgen_transform\(", source)), 2)            # its definition and build_cell_project
        self.assertIn("gen_transform(project, port, p[\"port_fix\"][\"mode\"])", source)
        for name in ("stage", "evaluate_specs", "run_playwright", "apply_edits"):
            self.assertTrue(getattr(m.engine, name).__code__.co_filename.endswith("run-generator-skill-effect-v3.py"), name)
        stage_before = m.engine.stage
        m.bind_v1()
        m.unbind_v1()
        self.assertIs(m.engine.stage, stage_before)
        self.assertIs(m.engine.Ports, m._PORTS)

    def test_cell_builder_applies_the_transform_before_the_baseline_commit_to_every_arm(self):
        calls = []
        real = m.gen_transform

        def spy(project, port, mode):
            calls.append((Path(project).name, port, mode, (Path(project) / ".git").exists()))
            return real(project, port, mode)
        p = m.protocol()
        with patch.object(m, "gen_transform", spy), patch.object(m, "arm_setup", lambda project, arm, pp: {"status": "ready", "setup_s": 0}), \
                patch.object(m.v1, "baseline", lambda project, case: None):
            for arm in (A, B, C):
                source = None
                if arm == B:
                    source = Path(tempfile.mkdtemp())
                    self.addCleanup(shutil.rmtree, source, True)
                work, project, setup = m.build_cell_project(TASKS[0], arm, 6304, p, source)
                self.addCleanup(shutil.rmtree, work, True)
                self.assertEqual(setup["port_fix"]["mode"], "split-port")
        self.assertEqual([c[1:] for c in calls], [(6304, "split-port", False)] * 3)   # one per arm, before any git state


class RealCellBuilder(unittest.TestCase):
    """The real staging, skill install, port transform and git baseline (local file and git operations only; no npx, no model)."""

    def git(self, project, *args):
        return subprocess.run(["git", *args], cwd=project, capture_output=True, text=True, check=True).stdout

    def test_skills_and_the_transform_are_in_the_baseline_commit_so_nothing_is_an_out_of_scope_write(self):
        p = m.protocol()
        stub = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, stub, True)
        (stub / "stub.spec.ts").write_text("import { test } from '@playwright/test';\ntest('stub', async () => {});\n")
        for arm, names in ((C, ("playwright-test-generator", "e2e-reviewer")), (B, ("e2e-reviewer",))):
            work, project, setup = m.build_cell_project(TASKS[0], arm, 6304, p, stub if arm == B else None)
            self.addCleanup(shutil.rmtree, work, True)
            self.assertEqual(sorted(setup["skills_installed"]), sorted(names))
            tracked = self.git(project, "ls-files").split()
            for name in names:
                self.assertIn(f".claude/skills/{name}/SKILL.md", tracked)
            self.assertIn("playwright.config.mjs", tracked)
            status = self.git(project, "status", "--porcelain", "--untracked-files=all").splitlines()
            self.assertEqual(status, ["?? tests/stub.spec.ts"] if arm == B else [], arm)     # only the reviewer's input is untracked
            self.assertIn(ad.PORT_ENV, (project / "app.mjs").read_text())
            self.assertIn("reuseExistingServer: false", (project / "playwright.config.mjs").read_text())
            dest = Path(tempfile.mkdtemp())
            self.addCleanup(shutil.rmtree, dest, True)
            found = m.engine.collect_deliverable(project, dest)
            self.assertEqual((found["out_of_scope_writes"], [x for x in found["spec_files"] if "stub" not in x]), ([], []))
            self.assertTrue((project / "specs/plan.md").is_file() and (project / "tests/seed.spec.ts").is_file())

    def test_arm_a_gets_no_skills_directory_and_keeps_the_official_setup_unchanged(self):
        p = m.protocol()
        calls = []
        fake = lambda project, runner, proto: calls.append((runner, sorted(proto["transports"]["claude_official_arm"]["init_agents_file_sha256"]))) or {"status": "ready"}
        with patch.object(m.v1, "init_agents", fake):
            work, project, setup = m.build_cell_project(TASKS[0], A, 6304, p)
        self.addCleanup(shutil.rmtree, work, True)
        self.assertEqual(calls[0][0], "claude")
        self.assertEqual(calls[0][1], [".claude/agents/playwright-test-generator.md", ".claude/agents/playwright-test-healer.md",
                                       ".claude/agents/playwright-test-planner.md", ".mcp.json"])
        self.assertFalse((project / ".claude/skills").exists())
        self.assertEqual(setup["port_fix"]["mcp_port"], 26304)


class SkillInstall(unittest.TestCase):
    def test_skills_are_installed_as_real_project_skills_per_arm(self):
        for arm, names in ((A, ()), (B, ("e2e-reviewer",)), (C, ("playwright-test-generator", "e2e-reviewer"))):
            with tempfile.TemporaryDirectory() as tmp:
                done = m.install_skills(tmp, arm) if names else {}
                root = Path(tmp) / ".claude/skills"
                self.assertEqual(sorted(done), sorted(names))
                self.assertEqual(sorted(p.name for p in root.iterdir()) if root.exists() else [], sorted(names))
                for name in names:
                    self.assertTrue((root / name / "SKILL.md").is_file())
                    self.assertEqual((root / name / "SKILL.md").read_bytes(), (m.orig.OURS_SKILLS / name / "SKILL.md").read_bytes())
                    self.assertFalse((root / name / "evals").exists())
                    self.assertEqual(m.orig.tree(root / name), m.orig.tree(m.orig.OURS_SKILLS / name))
        with self.assertRaises(KeyError):
            m.install_skills("/nonexistent", "other")
        self.assertEqual({a: tuple(s) for a, s in m.protocol()["skills"]["by_arm"].items()}, ad.SKILLS_BY_ARM)

    def test_skill_scripts_named_in_the_prompts_exist_in_the_installed_tree(self):
        for rel in ("playwright-test-generator/scripts/run-preflight-target.sh", "playwright-test-generator/scripts/write-utf8-frame.sh",
                    "e2e-reviewer/scripts/scan.sh"):
            self.assertTrue((m.orig.OURS_SKILLS / rel).is_file(), rel)
            self.assertIn(".claude/skills/" + rel, m.C_LINE + m.B_LINE)


class ScheduleAndProtocol(unittest.TestCase):
    def test_36_cells_complete_unique_and_ordered(self):
        rows = m.schedule()
        self.assertEqual(len(rows), 36)
        self.assertEqual({(r["case"], r["arm"], r["repetition"]) for r in rows}, {(t, a, r) for t in TASKS for a in (A, B, C) for r in (1, 2)})
        self.assertEqual([r["ordinal"] for r in rows], list(range(1, 37)))
        self.assertTrue(all(r["arm"] != B for r in rows[:24]) and all(r["arm"] == B for r in rows[24:]))
        by_id = {(r["case"], r["arm"], r["repetition"]): r["ordinal"] for r in rows}
        for r in rows[24:]:
            self.assertGreater(r["ordinal"], by_id[(r["case"], A, r["repetition"])])
        self.assertEqual(rows, m.schedule())
        self.assertEqual(rows, m.read(m.V1_LOCK)["schedule"])

    def test_protocol_contract_and_roster(self):
        p, base = m.protocol(), m._V1["protocol"]()
        for key in ("tasks", "seed", "repetitions", "timeout_s", "reasoning_effort", "workers", "call_budget_usd_claude_safety_cap"):
            self.assertEqual(p[key], base[key])
        self.assertEqual(p["status"], "NOT_RUN")
        self.assertEqual([x["id"] for x in p["models"]], ["claude-sonnet-5-5", "claude-haiku-5-5", "claude-opus-5-5", "claude-fable-5-1"])
        self.assertEqual({x["id"] for x in p["models"]}, {x["id"] for x in base["models"] if x["family"] == "claude"})
        self.assertTrue(all(x["family"] == "claude" and x["runner"] == "claude" for x in p["models"]))
        self.assertIn("re-run under v2", p["models"][0]["v1_status"])
        self.assertIn("never merged", p["sonnet_rule"])
        self.assertIn("12 of 12", p["sonnet_rule"])
        self.assertNotIn(p["preflight_task"]["task"], p["tasks"])
        self.assertEqual(p["decision"]["cross_model"]["min_models"], 4)
        self.assertEqual(p["load"]["flag_threshold"], 40)
        self.assertEqual(p["execution_identity"]["version_policy"], "minimum")
        self.assertEqual(p["pooled_analysis"]["cluster_bootstrap"]["seed"], p["seed"])
        self.assertIs(p["pooled_analysis"]["owner_approval"]["inference"], False)
        allowed = p["skills"]["bundled_allowed"]       # empty until init-check; then the bundled names pasted before the freeze
        self.assertIsInstance(allowed, list)
        self.assertTrue(all(isinstance(x, str) and x and ":" not in x and " " not in x for x in allowed) and allowed == sorted(set(allowed)))
        for view in p["pooled_analysis"]["views"]:
            self.assertIn(view, m.VIEWS)
        for metric in p["pooled_analysis"]["metrics"]:
            self.assertIn(metric, m.METRICS)

    def test_protocol_validation_rejects_changes(self):
        good = m.read(m.PROTOCOL)
        for mutate in (lambda d: d.update(seed=1), lambda d: d["models"].pop(), lambda d: d["models"][0].update(family="codex"),
                       lambda d: d["port_fix"].update(mode="x"), lambda d: d["skills"]["by_arm"].update({"official-generator": ["e2e-reviewer"]}),
                       lambda d: d["decision"].update(min_delivered=5), lambda d: d.update(preflight_task={"task": TASKS[0]})):
            data = json.loads(json.dumps(good))
            mutate(data)
            with tempfile.TemporaryDirectory() as tmp:
                path = Path(tmp) / "p.json"
                path.write_text(json.dumps(data))
                with patch.object(m, "PROTOCOL", path), self.assertRaises((ValueError, KeyError)):
                    m.protocol()

    def test_cli_floor(self):
        self.assertEqual(m.parse_version("2.1.299 (Claude Code)"), (2, 1, 299))
        self.assertGreaterEqual(m.parse_version("2.2.0"), m.CLI_FLOOR)
        self.assertLess(m.parse_version("2.1.298"), m.CLI_FLOOR)
        self.assertEqual(tuple(m.protocol()["execution_identity"]["claude_cli_minimum"]), m.CLI_FLOOR)


class FreezeAndV1(unittest.TestCase):
    def test_v1_frozen_files_still_match_their_freeze(self):
        lock = m.read(m.V1_LOCK)["bindings"]
        for key, rel in V1_FILES.items():
            self.assertEqual(sha256(ROOT / rel), lock[key], f"v1 file changed: {rel}")
        self.assertTrue(m.v1_unchanged())
        for rel in ("benchmarks/generator-multimodel-v1/README.md", "benchmarks/generator-multimodel-v1/freeze.json", "benchmarks/generator-multimodel-v1/protocol.json"):
            self.assertTrue((ROOT / rel).is_file())

    def test_this_work_edits_no_v1_file_it_only_adds_files(self):
        v2_files = [ROOT / "scripts/evals/run-generator-multimodel-v2-claude.py", ROOT / "scripts/evals/generator_claude_multimodel_adapter_v2.py",
                    ROOT / "scripts/ci/test-generator-multimodel-v2-claude.py"]
        for path in v2_files:
            self.assertTrue(path.is_file())
            self.assertFalse(path.name.endswith("-v1.py") or path.name == "generator_claude_multimodel_adapter.py")
        self.assertNotIn(str(m.ADAPTER), [str(ROOT / V1_FILES["claude_adapter"])])

    def test_freeze_roundtrip_and_one_byte_drift_detection(self):
        with tempfile.TemporaryDirectory() as tmp:
            lock = Path(tmp) / "freeze.json"
            with self.assertRaises((ValueError, FileNotFoundError)):
                with patch.object(m, "LOCK", lock):
                    m.frozen()
            with patch.object(m, "LOCK", lock):
                data = m.build_freeze(lock)
                self.assertEqual(m.frozen()["bindings"], data["bindings"])
                with self.assertRaisesRegex(ValueError, "already frozen"):
                    m.build_freeze(lock)
                bound = {"protocol": m.PROTOCOL, "runner": Path(m.__file__), "claude adapter v2": m.ADAPTER, "refactors": m.REFACTORS,
                         "v1 runner": ROOT / V1_FILES["runner"], "v1 frozen adapter": ROOT / V1_FILES["claude_adapter"],
                         "v1 protocol": ROOT / V1_FILES["protocol"], "v1 freeze": m.V1_LOCK, "pilot scorer": ROOT / V1_FILES["original_runner"],
                         "pilot source protocol": m.orig.SOURCE / "protocol.json", "pilot source validation": m.orig.SOURCE / "reports/validation.json"}
                for label, path in bound.items():
                    with patch.object(m.orig, "digest", flip_last_byte(path)):
                        with self.assertRaises(ValueError, msg=f"one-byte change not detected: {label}"):
                            m.frozen()
                for name in ("A_LINE", "B_LINE", "C_LINE", "C_SCRATCH", "APP_PORT_TEMPLATE", "CFG_BASE_TEMPLATE", "CFG_URL_TEMPLATE"):
                    with patch.object(m, name, getattr(m, name) + "."), self.assertRaises(ValueError, msg=name):
                        m.frozen()
                with patch.object(m.adapter, "HOT_REFS", m.adapter.HOT_REFS[:-1]), self.assertRaises(ValueError):
                    m.frozen()
                tampered = json.loads(lock.read_text())
                tampered["schedule"][0]["ordinal"] = 99
                lock.write_text(json.dumps(tampered))
                with self.assertRaises(ValueError):
                    m.frozen()

    def test_freeze_refuses_when_a_v1_file_differs(self):
        with tempfile.TemporaryDirectory() as tmp, patch.object(m.orig, "digest", flip_last_byte(ROOT / V1_FILES["claude_adapter"])):
            with self.assertRaisesRegex(ValueError, "v1 freeze"):
                m.build_freeze(Path(tmp) / "freeze.json")
            self.assertFalse((Path(tmp) / "freeze.json").exists())

    def test_every_file_the_runner_imports_or_reads_is_bound(self):
        b = m.bindings()
        self.assertTrue({"protocol", "readme_before_results", "runner", "claude_adapter_v2", "refactors", "v1_freeze", "v1_bindings", "prompt_lines",
                         "port_fix_templates", "fidelity_spec"} <= set(b))
        self.assertTrue(set(V1_FILES) <= set(b["v1_bindings"]))

    def test_results_appended_below_the_heading_do_not_break_the_freeze_but_edits_above_do(self):
        with tempfile.TemporaryDirectory() as tmp:
            readme, lock = Path(tmp) / "README.md", Path(tmp) / "freeze.json"
            readme.write_text(m.README.read_text())
            with patch.object(m, "README", readme), patch.object(m, "LOCK", lock):
                m.build_freeze(lock)
                readme.write_text(readme.read_text() + "\nResult table\n")
                m.frozen()
                readme.write_text(readme.read_text().replace("Status:", "Statuz:", 1))
                with self.assertRaises(ValueError):
                    m.frozen()
                readme.write_text("no results heading")
                with self.assertRaisesRegex(ValueError, "Results"):
                    m.frozen()

    def test_bind_and_unbind_restore_the_frozen_v1_module(self):
        before = {name: getattr(m.v1, name) for name in m._V1}
        m.bind_v1()
        self.assertIs(m.v1.one_call, m.one_call)
        m.unbind_v1()
        self.assertEqual({name: getattr(m.v1, name) for name in m._V1}, before)


def cell(case, arm, rep, score, delivered=True, clean=True, kill=1.0, p0=0, p12=0, aborted=False, flagged=False, invoked=True, treated=True,
         tokens=100000, secs=10.0, sec_text=None, sec_structure=None, ref=None, complete=True):
    return {"case": case, "arm": arm, "repetition": rep, "refactor_score": score, "clean": clean, "effective_fault_kill": kill, "scan_p0": p0,
            "scan_p1p2": p12, "deliverable": delivered, "aborted": aborted, "load_flagged": flagged, "invoked": invoked, "treated": treated,
            "pipeline_processed": tokens, "pipeline_total": tokens * 2, "pipeline_complete": complete, "pipeline_seconds": secs,
            "sec_text_label": sec_text, "sec_structure": sec_structure, "references_renamed_selector": ref}


def table(a_scores, c_scores, b_scores=None, **over):
    cells = []
    for i, t in enumerate(TASKS):
        for rep in (1, 2):
            cells.append(cell(t, A, rep, a_scores[i], **over.get("a", {})))
            cells.append(cell(t, C, rep, c_scores[i], **over.get("c", {})))
            b = cell(t, B, rep, (b_scores or a_scores)[i], **over.get("b", {}))
            b.update(source_invoked=True, source_treated=True, source_load_flagged=False)
            cells.append(b)
    return cells


class Rules(unittest.TestCase):
    def label(self, cells, view="itt", contrast="C_minus_A"):
        return m.view_results(cells, view, TASKS)["labels"][contrast]

    def test_suggestive_needs_five_of_six_and_not_worse_guards(self):
        won = self.label(table([0] * 6, [1] * 6))
        self.assertEqual((won["label"], won["leader"]), (f"suggestive: {C} better", C))
        self.assertEqual(self.label(table([0] * 6, [1] * 5 + [0]))["leader"], C)
        self.assertIsNone(self.label(table([0] * 6, [1] * 4 + [0, 0]))["leader"])
        self.assertIsNone(self.label(table([1] * 6, [1] * 6))["leader"])
        self.assertIsNone(self.label(table([1, 1, 1, 0, 0, 0], [0, 0, 0, 1, 1, 1]))["leader"])
        worse = self.label(table([0] * 6, [1] * 6, c={"p0": 1}))
        self.assertEqual((worse["leader"], worse["guards_not_worse_x"]), (None, False))
        self.assertIsNone(self.label(table([0] * 6, [1] * 6, c={"clean": False}))["leader"])
        self.assertEqual(self.label(table([1] * 6, [0] * 6))["leader"], A)

    def test_not_evaluable_with_too_few_delivered_or_shared_tasks(self):
        few = table([0] * 6, [1] * 6)
        for c in few:
            if c["arm"] == A and c["case"] in TASKS[:4]:
                c["deliverable"] = False
        self.assertFalse(self.label(few)["eligible"])

    def test_views_itt_invoked_as_treated_and_load_clean(self):
        cells = table([0] * 6, [1] * 6)
        for c in cells:
            if c["arm"] == A and c["repetition"] == 2:
                c.update(treated=False, invoked=False, refactor_score=1.0)
            if c["arm"] == B and c["repetition"] == 2:
                c.update(source_treated=False, source_invoked=False)
            if c["arm"] == C and c["case"] == TASKS[0]:
                c.update(invoked=True, treated=False)
        sizes = lambda v: m.view_results(cells, v, TASKS)["cells_in_view"]
        self.assertEqual(sizes("itt"), {A: 12, B: 12, C: 12})
        self.assertEqual(sizes("as_treated"), {A: 6, B: 6, C: 10})
        self.assertEqual(sizes("invoked"), {A: 6, B: 6, C: 12})
        self.assertEqual(self.label(cells, "as_treated")["leader"], C)
        cells[0]["aborted"], cells[1]["load_flagged"] = True, True
        self.assertEqual(sizes("itt"), {A: 12, B: 12, C: 12})
        self.assertEqual(sizes("load_clean")[A], 11)
        self.assertEqual(sizes("as_treated")[A], 5)

    def test_b_cell_follows_its_source_a_cell(self):
        cells = table([0] * 6, [1] * 6)
        for c in cells:
            if c["arm"] == B and c["case"] == TASKS[0]:
                c.update(source_treated=False)
        self.assertEqual(m.view_results(cells, "as_treated", TASKS)["cells_in_view"][B], 10)

    def test_task_metric_diffs_and_missing_values(self):
        cells = table([0] * 6, [1, 1, 1, 1, 1, 0], c={"tokens": 200000, "secs": 40.0})
        d = m.task_metric_diffs(cells, C, A, TASKS, "refactor_score")
        self.assertEqual([d[t] for t in TASKS], [1, 1, 1, 1, 1, 0])
        self.assertEqual(m.task_metric_diffs(cells, C, A, TASKS, "pipeline_seconds")[TASKS[0]], 30.0)
        self.assertIsNone(m.task_metric_diffs(cells, C, A, TASKS, "sec_text_label")[TASKS[0]])          # secondary not scored yet
        cells[0]["clean"] = False
        self.assertIsNone(m.task_metric_diffs([c for c in cells if c["arm"] == A and c["case"] != TASKS[0]] + [c for c in cells if c["arm"] == C], C, A, TASKS,
                                              "refactor_score")[TASKS[0]])

    def test_clean_conditional_and_secondary_metrics(self):
        cells = [cell("t", A, 1, 0.0, clean=False), cell("t", A, 2, 1.0, clean=True, sec_text=0.0, sec_structure=1.0),
                 cell("t", C, 1, 1.0, sec_text=1.0, sec_structure=1.0), cell("t", C, 2, 0.0, clean=False, sec_text=0.0, sec_structure=0.0)]
        self.assertEqual(m.metric_value([c for c in cells if c["arm"] == A], "refactor_score"), 0.5)
        self.assertEqual(m.metric_value([c for c in cells if c["arm"] == A], "refactor_given_clean"), 1.0)
        self.assertEqual(m.metric_value([c for c in cells if c["arm"] == C], "sec_structure"), 0.5)
        self.assertEqual(m.metric_value([c for c in cells if c["arm"] == C], "sec_text_label"), 0.5)
        self.assertEqual(m.sec_value(None, "x", "text_label"), None)
        self.assertEqual(m.sec_value({"rows": {"x": {"text_label": True, "structure": False}}}, "x", "text_label"), 1.0)
        self.assertEqual(m.sec_value({"rows": {}}, "y", "structure"), 0.0)


def result(complete, leader, eligible=True, view="itt", contrast="C_minus_A"):
    return {"complete": complete, "views": {view: {"labels": {contrast: {"eligible": eligible, "leader": leader}}}}}


class CrossModel(unittest.TestCase):
    ids = [x["id"] for x in m.protocol()["models"]]

    def verdict(self, leaders, **kw):
        results = {i: result(kw.get("complete", {}).get(i, True), l, kw.get("eligible", {}).get(i, True)) for i, l in zip(self.ids, leaders)}
        return m.cross_model(results, m.protocol(), "itt", "C_minus_A")["verdict"]

    def test_floor_threshold_and_opposition(self):
        self.assertTrue(self.verdict([C, C, C]).startswith("not evaluable (fewer than 4"))
        self.assertEqual(self.verdict([C, C, None, None]), f"consistent: {C} better in 2 of 4 models")
        self.assertEqual(self.verdict([C, None, None, None]), "not consistent")
        self.assertEqual(self.verdict([C, C, A, None]), "not consistent")
        self.assertEqual(self.verdict([A, None, A, None]), f"consistent: {A} better in 2 of 4 models")
        self.assertTrue(self.verdict([C, C, C, C], complete={self.ids[0]: False}).startswith("not evaluable"))
        self.assertTrue(self.verdict([C, C, C, C], eligible={self.ids[1]: False}).startswith("not evaluable"))


class PooledAnalysis(unittest.TestCase):
    cfg = {"min_models": 2, "owner_approval": {"inference": False}, "cluster_bootstrap": {"replicates": 500, "seed": 7, "level": 0.95}}

    def test_sign_flip_exact_values(self):
        s = m.sign_flip([1.0, 1.0, 1.0])
        self.assertEqual((s["patterns"], s["p_two_sided"], s["p_one_sided_positive"], s["min_attainable_p"]), (8, 0.25, 0.125, 0.25))
        s4 = m.sign_flip([0.2, 0.3, 0.1, 0.4])
        self.assertEqual((s4["p_two_sided"], s4["min_attainable_p"]), (0.125, 0.125))                  # four models can never reach 0.05
        mixed = m.sign_flip([1.0, -1.0])
        self.assertEqual((mixed["p_two_sided"], mixed["p_one_sided_positive"]), (1.0, 0.75))
        self.assertEqual(m.sign_flip([0.0, 0.0])["p_two_sided"], 1.0)
        self.assertAlmostEqual(m.sign_flip([3.0, 1.0, -1.0])["p_two_sided"], 0.75)                    # observed sum 3; six of the eight sign vectors reach |sum| >= 3
        self.assertIsNone(m.sign_flip([])["p_two_sided"])
        with self.assertRaises(ValueError):
            m.sign_flip([0.1] * 17)
        self.assertEqual(m.sign_flip([1.0] * 10)["min_attainable_p"], 2 / 1024)

    def per_model(self, effects, missing=None):
        return {f"m{i}": {t: (None if (missing and (i, t) in missing) else e) for t in TASKS} for i, e in enumerate(effects)}

    def test_unweighted_mean_over_models_and_the_descriptive_label(self):
        out = m.pooled_report(self.per_model([0.5, 0.0, -0.1]), self.cfg, {"m0": "claude", "m1": "claude", "m2": "codex"}, {"m0": "a", "m1": "a", "m2": "b"}, TASKS)
        self.assertEqual(out["status"], "descriptive")
        self.assertTrue(out["descriptive_only"])
        self.assertEqual(out["label"], "descriptive (inference not approved)")
        self.assertEqual(out["estimate_unweighted_over_models"], round((0.5 + 0.0 - 0.1) / 3, 4))
        self.assertEqual((out["models_positive"], out["models_negative"]), (1, 1))
        self.assertEqual(out["family_means"], {"claude": 0.25, "codex": -0.1})
        self.assertEqual(out["lineage_means"], {"a": 0.25, "b": -0.1})
        self.assertEqual(out["sign_flip"]["patterns"], 8)
        self.assertEqual(out["leave_one_model_out"]["m0"], round((0.0 - 0.1) / 2, 4))
        self.assertEqual(set(out["task_profile"]), set(TASKS))
        lo, hi = out["cluster_bootstrap"]["ci"]
        self.assertLessEqual(lo, out["estimate_unweighted_over_models"])
        self.assertGreaterEqual(hi, out["estimate_unweighted_over_models"])
        approved = dict(self.cfg, owner_approval={"inference": True})
        self.assertEqual(m.pooled_report(self.per_model([0.5, 0.0]), approved)["label"], "inference (owner-approved)")

    def test_models_without_any_value_are_excluded_and_missing_cells_skipped(self):
        miss = {(1, t) for t in TASKS}
        out = m.pooled_report(self.per_model([0.2, 0.4, 0.6], missing=miss), self.cfg)
        self.assertEqual((out["models_excluded"], out["models_included"]), (["m1"], ["m0", "m2"]))
        one_missing = m.pooled_report(self.per_model([0.2, 0.4], missing={(1, TASKS[0])}), self.cfg)
        self.assertEqual(one_missing["models_excluded"], [])
        self.assertEqual(one_missing["model_effects"], {"m0": 0.2, "m1": 0.4})                    # a missing task is skipped, not imputed
        self.assertTrue(m.pooled_report(self.per_model([0.2]), self.cfg)["status"].startswith("not evaluable"))

    def test_bootstrap_is_deterministic_and_degenerate_cases_are_exact(self):
        grid = self.per_model([0.5, 0.25, 0.75])
        a, b = m.cluster_bootstrap(grid, 500, 7), m.cluster_bootstrap(grid, 500, 7)
        self.assertEqual(a, b)
        self.assertEqual((a["reps"], a["skipped"], a["level"]), (500, 0, 0.95))
        self.assertEqual(m.cluster_bootstrap(self.per_model([0.5, 0.5, 0.5]), 500, 7)["ci"], [0.5, 0.5])
        self.assertEqual(len(m.cluster_bootstrap(grid, 500, 8)["ci"]), 2)
        self.assertIsNone(m.cluster_bootstrap({}, 10, 1)["ci"])
        empty = {"m0": {t: None for t in TASKS}}
        self.assertEqual(m.cluster_bootstrap(empty, 20, 1), {"reps": 20, "skipped": 20, "ci": None, "level": 0.95})

    def test_eligibility_and_the_two_family_combination(self):
        p = m.protocol()
        mk = lambda e, eligible=True, complete=True: {"complete": complete, "lineage": "claude-5", "views": {"itt": {
            "labels": {"C_minus_A": {"eligible": eligible}}, "task_metric_diffs": {"C_minus_A": {"refactor_score": {t: e for t in TASKS}}}}}}
        out = m.pooled_results({"a": mk(0.5), "b": mk(0.25), "c": mk(0.9, eligible=False), "d": mk(0.9, complete=False)}, p, "itt", "C_minus_A", "refactor_score")
        self.assertEqual((out["models_included"], out["estimate_unweighted_over_models"]), (["a", "b"], 0.375))
        self.assertTrue(m.pooled_results({}, p, "itt", "C_minus_A", "refactor_score")["status"].startswith("not evaluable"))
        codex_cells = []
        for t in TASKS:
            for rep in (1, 2):
                codex_cells.append(dict(cell(t, A, rep, 0.0), fidelity_class="official-tool"))
                codex_cells.append(dict(cell(t, C, rep, 1.0), fidelity_class=None))
        codex = {"gpt-6-sol": {"complete": True, "lineage": "gpt-6", "cells": codex_cells,
                               "views": {"itt": {"labels": {"C_minus_A": {"eligible": True}}}, "primary": {"labels": {"C_minus_A": {"eligible": True}}}}},
                 "gpt-6-luna": {"complete": True, "lineage": "gpt-6", "cells": codex_cells,
                                "views": {"itt": {"labels": {"C_minus_A": {"eligible": False}}}, "primary": {"labels": {"C_minus_A": {"eligible": False}}}}}}
        out = m.combined_descriptive({"a": mk(0.5)}, codex, p, "itt", "itt", "C_minus_A", "refactor_score")
        self.assertEqual((out["models_included"], out["family_means"], out["lineage_means"]), (["a", "gpt-6-sol"], {"claude": 0.5, "codex": 1.0}, {"claude-5": 0.5, "gpt-6": 1.0}))
        self.assertEqual(out["sign_flip"]["patterns"], 4)
        out = m.combined_descriptive({"a": mk(0.5)}, codex, p, "itt", "primary", "C_minus_A", "refactor_score")
        self.assertEqual(out["status"], "descriptive")
        for metric in m.COMBINED_METRICS:
            self.assertIn(metric, m.METRICS)

    def test_the_definitions_match_the_codex_pooled_module_when_it_is_present(self):
        path = ROOT / "scripts/evals/generator_v2_codex_pooled.py"
        if not path.is_file():
            self.skipTest("Codex pooled module not present")
        other = load("codex_pooled_for_parity", "scripts/evals/generator_v2_codex_pooled.py")
        grid = {"m0": {"a": 0.5, "b": 0.0, "c": None, "d": -0.25}, "m1": {"a": 0.1, "b": 0.2, "c": 0.3, "d": 0.4}, "m2": {"a": -0.3, "b": 0.0, "c": 0.2, "d": 0.2}}
        theirs, mine = other.sign_flip_exact([0.2, -0.1, 0.05]), m.sign_flip([0.2, -0.1, 0.05])
        self.assertEqual((theirs["p_two_sided"], theirs["min_attainable_p"], theirs["patterns"]), (mine["p_two_sided"], mine["min_attainable_p"], mine["patterns"]))
        self.assertEqual(other.cluster_bootstrap(grid, 300, 20261016)["ci"], m.cluster_bootstrap(grid, 300, 20261016)["ci"])
        self.assertEqual(other.pooled_estimate(grid), m._mean(m._mean(d.values()) for d in grid.values()))


class SecondaryRefactors(unittest.TestCase):
    data = json.loads(m.REFACTORS.read_text())

    class Census(html.parser.HTMLParser):
        INTEREST = {"button", "input", "select", "a", "h1", "h2", "label", "ul", "ol", "li", "section", "main", "form", "p"}

        def __init__(self):
            super().__init__()
            self.stack, self.items = [], []

        VOID = {"input", "br", "img", "hr", "meta", "link"}

        def handle_starttag(self, tag, attrs):
            if tag in self.VOID:
                if tag in self.INTEREST:
                    self.items.append((tag, dict(attrs).get("aria-label"), dict(attrs).get("role"), ""))
                return
            self.stack.append({"tag": tag, "attrs": dict(attrs), "text": ""})

        def handle_data(self, data):
            for frame in self.stack:
                frame["text"] += data

        def handle_endtag(self, tag):
            while self.stack:
                frame = self.stack.pop()
                if frame["tag"] in self.INTEREST:
                    self.items.append((frame["tag"], frame["attrs"].get("aria-label"), frame["attrs"].get("role"), " ".join(frame["text"].split())))
                if frame["tag"] == tag:
                    break

    def mutated(self, cls, case):
        app = (m.engine.CASES / case / "app.mjs").read_text().replace("__PORT__", "1")
        for e in self.data["classes"][cls]["cases"][case]:
            self.assertEqual(app.count(e["find"]), e["count"], (cls, case, e["find"]))
            app = app.replace(e["find"], e["replace"])
        return app

    @staticmethod
    def page(app):
        return app.split("const page = `", 1)[1].split("`;", 1)[0]

    def test_classes_cover_every_task_and_markers_match_the_declared_counts(self):
        self.assertEqual(tuple(self.data["classes"]), m.SECONDARY_CLASSES)
        for cls in m.SECONDARY_CLASSES:
            self.assertEqual(sorted(self.data["classes"][cls]["cases"]), sorted(TASKS))
            for case in TASKS:
                self.assertTrue(self.mutated(cls, case))
        self.assertEqual(m.refactor_edits()["schema_version"], 1)

    def test_edits_parse_as_javascript(self):
        node = shutil.which("node")
        if not node:
            self.skipTest("node not available")
        with tempfile.TemporaryDirectory() as tmp:
            for cls in m.SECONDARY_CLASSES:
                for case in TASKS:
                    path = Path(tmp) / f"{cls}-{case}.mjs"
                    path.write_text(self.mutated(cls, case))
                    done = subprocess.run([node, "--check", str(path)], capture_output=True, text=True, timeout=60)
                    self.assertEqual(done.returncode, 0, (cls, case, done.stderr[:200]))

    def test_text_class_changes_text_and_nothing_structural(self):
        ids_classes = lambda app: sorted(m.snippet_tokens(app))
        for case in TASKS:
            base = (m.engine.CASES / case / "app.mjs").read_text().replace("__PORT__", "1")
            after = self.mutated("text_label", case)
            self.assertEqual(ids_classes(base), ids_classes(after), case)                         # ids and classes unchanged
            for e in self.data["classes"]["text_label"]["cases"][case]:
                self.assertIn(e["old_text"], e["find"])
                self.assertIn(e["new_text"], e["replace"])
                self.assertNotIn(e["old_text"].lower(), e["new_text"].lower(), (case, e))        # substring role-name matching cannot survive by accident
            self.assertNotEqual(self.page(base), self.page(after), case)

    def test_structure_class_keeps_ids_classes_roles_names_and_text(self):
        for case in TASKS:
            base = (m.engine.CASES / case / "app.mjs").read_text().replace("__PORT__", "1")
            after = self.mutated("structure", case)
            old_tokens, new_tokens = m.snippet_tokens(base), m.snippet_tokens(after)
            self.assertTrue(old_tokens <= new_tokens, (case, old_tokens - new_tokens))            # nothing removed, wrappers may add classes
            cb, ca = self.Census(), self.Census()
            cb.feed(self.page(base)), ca.feed(self.page(after))
            self.assertEqual(sorted(map(str, cb.items)), sorted(map(str, ca.items)), case)       # static roles, names and text identical
            self.assertGreater(len(self.page(after)) + len(after), len(self.page(base)) + len(base))
            # the existing spec of the case (smoke) is structure-independent by construction: it uses roles
            self.assertNotEqual(base, after)

    def test_classes_are_orthogonal_to_the_primary_refactor_tokens(self):
        for case in TASKS:
            primary = m.renamed_tokens(case)
            for cls in m.SECONDARY_CLASSES:
                for e in self.data["classes"][cls]["cases"][case]:
                    gone = m.snippet_tokens(e["find"]) - m.snippet_tokens(e["replace"])
                    self.assertFalse(gone, (cls, case, "a secondary class must not rename an id or class", gone, primary[:3]))


class PowerAndText(unittest.TestCase):
    def test_recorded_simulation_is_reproducible(self):
        rec = m.read(m.PROTOCOL)["power_simulation"]["recorded"]
        self.assertEqual(rec["params"], m.POWER)
        for key in ("effect_2.4|treated1.0", "null|treated0.5"):
            scenario, treated = key.split("|")
            self.assertEqual(m.power_cell(scenario, float(treated.replace("treated", ""))), rec["cells"][key], key)
        self.assertEqual(rec["min_attainable_sign_flip_p_two_sided"]["4"], 0.125)
        full = rec["cells"]["effect_2.4|treated1.0"]
        self.assertTrue(0.15 < full["per_model_label_rate"]["X"] < 0.35)          # about the audit's 23% per model
        for k, v in rec["cells"].items():
            if k.startswith("null"):
                self.assertLessEqual(v["pooled_bootstrap_ci_lower_above_zero"], 0.02)
                self.assertLessEqual(v["cross_model_rule"]["X"] + v["cross_model_rule"]["Y"], 0.005)

    def test_docs_state_the_required_contract(self):
        text = m.README.read_text()
        for needle in ("harness-limited descriptive", "re-run under v2", "split-port", "reuseExistingServer", "Skill tool", "init event", "as_treated", "invoked",
                       "quality per 100k tokens", "clean-conditional", "text_label", "structure", "unweighted mean over models", "exact sign-flip", "cluster bootstrap",
                       "0.125", "descriptive", "Open owner decisions", "No model is dropped", "Not verified offline", "## Results", "executed", "mention",
                       "in-sample", "lower bound", "discordance", "not authored blind", "init-check` result exists"):
            self.assertIn(needle, text, needle)
        out_of_scope = "Pupp" + "eteer"   # built from fragments: the framework-scope CI scan flags the literal word in scripts/
        for path in (m.README, m.PROTOCOL, m.REFACTORS, Path(m.__file__), m.ADAPTER, Path(__file__)):
            body = path.read_text()
            self.assertNotIn(out_of_scope, body, path.name)
            self.assertNotIn("/Users" + "/", body, path.name)
            self.assertTrue(all(ord(ch) < 128 for ch in body), path.name)            # English-only public surface
        self.assertEqual(set(m.read(m.PROTOCOL)["fidelity"]["steps"]), set(m.ARMS3))
        for arm in m.ARMS3:
            self.assertEqual(m.read(m.PROTOCOL)["fidelity"]["steps"][arm], m.STEP_NAMES[arm])

    def test_phase_ports_do_not_collide_with_v1_or_the_codex_successor(self):
        self.assertEqual(m.PORT_OFFSET, 6000)
        self.assertEqual(m.engine.Ports(5300).take(), 5301)       # unbound: v1 numbering
        m.bind_v1()
        try:
            self.assertEqual(m.engine.Ports(6300).take(), 12301)
            self.assertGreater(12301 + ad.MCP_PORT_SHIFT, 12301)
            self.assertLess(7300 + m.PORT_OFFSET + 1000 + ad.MCP_PORT_SHIFT, 49152)
        finally:
            m.unbind_v1()


class LiveRefusals(unittest.TestCase):
    def test_live_commands_refuse_without_allow_live_and_touch_nothing(self):
        before = m.BASE.exists()
        with patch("subprocess.run", side_effect=AssertionError("no subprocess before the flag check")), \
                patch("subprocess.Popen", side_effect=AssertionError("no subprocess before the flag check")):
            for call, args in ((m.drive, argparse.Namespace(allow_live=False, only=None)),
                               (m.preflight, argparse.Namespace(allow_live=False, model="claude-sonnet-5-5", arms=["A"])),
                               (m.init_check, argparse.Namespace(allow_live=False, model="claude-sonnet-5-5", arms=["A"]))):
                with self.assertRaisesRegex(ValueError, "--allow-live"):
                    call(args)
            for argv in (["x", "drive"], ["x", "preflight", "--model", "claude-sonnet-5-5", "--arms", "A"], ["x", "init-check", "--model", "claude-sonnet-5-5"]):
                with patch("sys.argv", argv), self.assertRaisesRegex(ValueError, "--allow-live"):
                    m.main()
            with patch("sys.argv", ["x", "validate-refactors"]), self.assertRaisesRegex(ValueError, "--allow-local"):
                m.main()
        self.assertEqual(m.BASE.exists(), before)

    def test_drive_needs_a_freeze(self):
        with tempfile.TemporaryDirectory() as tmp, patch.object(m, "LOCK", Path(tmp) / "freeze.json"), self.assertRaisesRegex(ValueError, "not frozen"):
            m.drive(argparse.Namespace(allow_live=True, only=None))

    def test_campaign_lock(self):
        clean = {"conflicts": [], "coexisting": [], "own_ranges": {}, "lsof_available": True, "output_root": "x"}
        busy = dict(clean, conflicts=[{"kind": "zeppelin", "reason": "oss eval owns Zeppelin", "pid": 4242}])
        with tempfile.TemporaryDirectory() as tmp, patch.object(m, "BASE", Path(tmp)):
            with patch.object(m, "guard_report", return_value=busy), self.assertRaisesRegex(ValueError, "true conflict.*zeppelin.*pid 4242"):
                m.campaign_lock()
            with patch.object(m, "guard_report", return_value=clean):
                handle = m.campaign_lock()
                try:
                    with self.assertRaisesRegex(ValueError, "campaign lock"):
                        m.campaign_lock()
                finally:
                    handle.close()
                m.campaign_lock().close()

    def test_scoring_and_validation_verbs_take_the_same_lock_and_guard(self):
        with tempfile.TemporaryDirectory() as tmp, patch.object(m, "BASE", Path(tmp)):
            for argv in (["x", "score", "--model", "claude-sonnet-5-5"], ["x", "score-secondary", "--model", "claude-sonnet-5-5"],
                         ["x", "validate-refactors", "--allow-local"]):
                with patch("sys.argv", argv), patch.object(m, "campaign_lock", side_effect=ValueError("true conflict: test")), \
                        patch.object(m.v1, "score_model", side_effect=AssertionError("must not score")), \
                        patch.object(m, "score_secondary", side_effect=AssertionError("must not score")), \
                        self.assertRaisesRegex(ValueError, "true conflict"):
                    m.main()
                m.unbind_v1()

    def test_drive_refuses_without_a_matching_init_check(self):
        with tempfile.TemporaryDirectory() as tmp, patch.object(m, "BASE", Path(tmp)), patch.object(m, "frozen", return_value={}), \
                patch.object(m, "current_cli", return_value="2.1.299 (Claude Code)"), patch.object(m, "campaign_lock", side_effect=AssertionError("must not lock first")):
            with self.assertRaisesRegex(ValueError, "init-check gate: no init-check result"):
                m.drive(argparse.Namespace(allow_live=True, only=None))

    def test_init_check_gate_needs_the_installed_cli_all_arms_and_a_covering_allow_list(self):
        p = json.loads(json.dumps(m.protocol()))
        p["skills"]["bundled_allowed"] = []          # independent of the list the operator pastes before the freeze
        cli = "2.1.299 (Claude Code)"

        def report(cli_=cli, drop=None, b_skills=("e2e-reviewer",)):
            arms = {"A": {"raw_inits": [init(A)]}, "B": {"raw_inits": [init(B, skills=list(b_skills))]}, "C": {"raw_inits": [init(C)]}}
            arms.pop(drop, None)
            return {"cli": cli_, "model": "claude-sonnet-5-5", "arms": arms}
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self.assertFalse(m.init_check_gate(p, cli, root)[0])                                     # nothing there
            target = root / "_init_check/claude-sonnet-5-5"
            target.mkdir(parents=True)

            def put(rep):
                (target / "init-check.json").write_text(json.dumps(rep))
                return m.init_check_gate(p, cli, root)
            self.assertEqual(put(report()), (True, "ok"))
            self.assertIn("installed is", put(report(cli_="2.1.300 (Claude Code)"))[1])           # a CLI upgrade voids the check
            self.assertIn("not all three arms", put(report(drop="C"))[1])
            ok, why = put(report(b_skills=("e2e-reviewer", "simplify")))
            self.assertFalse(ok)
            self.assertIn("unintended skills", why)                                                   # a bundled skill must be allow-listed first
            allowed = json.loads(json.dumps(p))
            allowed["skills"]["bundled_allowed"] = ["simplify"]
            self.assertTrue(m.init_check_gate(allowed, cli, root)[0])

    def test_init_probe_wiring_with_a_faked_process(self):
        class Fake:
            returncode = 0
            pid = 1

            def __init__(self, argv, **kw):
                Fake.argv, Fake.env = argv, kw.get("env")

            def communicate(self, prompt, timeout=None):
                events = [init(B, skills=["e2e-reviewer", "simplify"]), result_event()]
                return "\n".join(json.dumps(e) for e in events), ""
        with tempfile.TemporaryDirectory() as tmp:
            work = Path(tmp)
            project = work / "project"
            project.mkdir()
            with patch.object(ad.subprocess, "Popen", Fake), patch.object(m.subprocess, "Popen", Fake):
                out = m.run_init_probe(B, "claude-sonnet-5-5", project, work, {"status": "ready"})
            self.assertEqual(out["suggest_bundled_allowed"], ["simplify"])
            self.assertEqual(len(out["raw_inits"]), 1)                           # stored so that the drive gate can re-check them under the final allow-list
            self.assertTrue(out["violations"])                                   # 'simplify' is not allowed yet
            self.assertNotIn(ad.PORT_ENV, Fake.env)
            self.assertIn("--setting-sources", Fake.argv)
            self.assertEqual(Fake.argv[Fake.argv.index("--setting-sources") + 1], "project")


class CallModelPath(unittest.TestCase):
    """Runs the real adapter.call_model with a faked process: isolation violations, harness port conflicts and the success record."""

    def run_call(self, arm, events, returncode=0):
        class Fake:
            pid = 1

            def __init__(self, argv, **kw):
                Fake.argv, Fake.env, self.returncode = argv, kw.get("env"), returncode

            def communicate(self, prompt, timeout=None):
                Fake.prompt = prompt
                return "\n".join(json.dumps(e) for e in events), ""
        tmp = Path(tempfile.mkdtemp(prefix="v2c-call-")).resolve()
        self.addCleanup(shutil.rmtree, tmp, True)
        project = tmp / "project"
        project.mkdir()
        (project / "app.mjs").write_text("const PORT = Number(process.env.E2E_APP_PORT ?? 6304);\n")
        (project / ".mcp.json").write_text(json.dumps({"mcpServers": {"playwright-test": {"command": "npx", "args": ["playwright", "run-test-mcp-server"]}}}))
        events = [dict(e, cwd=str(project)) if e.get("subtype") == "init" else e for e in events]
        engine = SimpleNamespace(CODEX_TRANSCRIPTS=tmp / "transcripts", FRAME=m.engine.FRAME, OUTPUT_SCHEMA=m.engine.OUTPUT_SCHEMA, sanitize=m.engine.sanitize)
        ad.ARM_LINES.update(m.arm_lines())
        call = ad.configure(engine)
        with patch.object(ad.subprocess, "Popen", Fake):
            rec = call(project, tmp, arm, "TASK", "claude-sonnet-5-5", 60, 1.0)
        return rec, Fake

    def test_good_calls_produce_cost_usage_fidelity_and_the_arm_prompt(self):
        rec, fake = self.run_call(C, c_stream())
        self.assertFalse(rec["infrastructure_error"])
        self.assertEqual(rec["cost"]["total_tokens"], 10 + 1000 + 50 + 200)
        self.assertEqual(rec["usage"]["input_tokens"], 1060)
        self.assertEqual(rec["usage_all_turns"], [rec["usage"]])
        self.assertTrue(rec["compliance"]["fidelity"]["treated"])
        self.assertEqual(rec["compliance"]["isolation"]["problems"], [])
        self.assertTrue(fake.prompt.endswith(m.C_LINE))
        self.assertTrue(fake.prompt.startswith("You are adding Playwright"))
        self.assertTrue(Path(rec["transcript_path"]).is_file())

    def test_an_isolation_violation_is_an_infrastructure_error_not_data(self):
        events = [init(B, skills=[]), result_event()]
        rec, _ = self.run_call(B, events)
        self.assertTrue(rec["infrastructure_error"])
        self.assertIn("isolation contract violated", rec["error"])
        self.assertTrue(rec["fatal_infrastructure"] and rec["isolation_violation"])         # systematic: no second attempt, the campaign stops
        self.assertIsNone(rec["structured_output"])
        events = [init(A), init(A, skills=["e2e-reviewer"]), result_event()]
        rec, _ = self.run_call(A, events)
        self.assertIn("[init 2]", rec["error"])

    def conflict_stream(self, model_started=False):
        pre = "mcp__playwright-test__"
        events = [init(A), use("Agent", {"subagent_type": "playwright-test-generator"}, "ag"), use(pre + "generator_setup_page", {}, "c1", parent="ag"),
                  use(pre + "generator_write_test", {}, "c2", parent="ag")]
        if model_started:
            events.append(use("Bash", {"command": "node app.mjs &"}, "srv"))
        events += [use("Bash", {"command": "node_modules/.bin/playwright test tests/a.spec.ts"}, "pt"),
                   res("pt", "Error: http://127.0.0.1:6304/health is already used, make sure that nothing is running"), result_event()]
        return events

    def test_a_port_conflict_without_a_model_started_server_is_a_harness_defect(self):
        rec, fake = self.run_call(A, self.conflict_stream())
        self.assertTrue(rec["infrastructure_error"] and rec["harness_port_conflict"])
        self.assertIn("port conflict", rec["error"])
        self.assertNotIn(ad.PORT_ENV, fake.env)
        mcp = Path(fake.argv[fake.argv.index("--mcp-config") + 1])
        self.assertEqual(json.loads(mcp.read_text())["mcpServers"]["playwright-test"]["env"], {ad.PORT_ENV: "26304"})

    def test_a_model_caused_conflict_is_not_an_infrastructure_error(self):
        rec, _ = self.run_call(A, self.conflict_stream(model_started=True))
        self.assertFalse(rec["infrastructure_error"])
        self.assertEqual(rec["compliance"]["fidelity"]["port_conflicts_in_playwright_test"], 1)

    def test_rate_limit_is_fatal_and_no_result_event_is_an_error(self):
        err = dict(result_event(), is_error=True, result="usage limit exceeded")
        rec, _ = self.run_call(C, [init(C), err], returncode=1)
        self.assertTrue(rec["infrastructure_error"] and rec.get("fatal_infrastructure"))
        rec, _ = self.run_call(C, [init(C)], returncode=1)
        self.assertTrue(rec["infrastructure_error"])
        self.assertIn("no result event", rec["error"])


class RealOneCall(unittest.TestCase):
    """The runner's own one_call with a faked model call: staging, retry, record assembly, infrastructure and unavailable marking."""

    def fake_model(self, behaviour):
        calls = []

        def call_model(project, work, arm, task, model, timeout, budget):
            calls.append((arm, Path(project), task))
            return behaviour(len(calls), Path(project), arm)
        return call_model, calls

    def ok_result(self, n, project, arm):
        (project / "tests").mkdir(exist_ok=True)
        (project / "tests" / "new.spec.ts").write_text("import { test } from '@playwright/test';\ntest('x', async () => {});\n")
        events = c_stream() if arm == C else [init(arm), result_event()]
        usage = events[-1]["modelUsage"]
        return {"infrastructure_error": False, "timeout": False, "error": None, "elapsed_ms": 4000, "cost_usd": 0.5, "num_turns": 3,
                "usage": {"input_tokens": 1}, "usage_all_turns": [{"input_tokens": 1}], "model_usage": usage, "cost": ad.cost_summary(usage, 0.5),
                "structured_output": {"status": "complete"}, "result_text": "", "transcript_path": None, "compliance": ad.analyze_events(events, arm)}

    def run_one(self, arm, behaviour, setup=None, artifacts=None):
        p = m.protocol()
        item = {"case": TASKS[0], "arm": arm, "repetition": 1, "ordinal": 1}
        call_model, calls = self.fake_model(behaviour)
        tmp = Path(tempfile.mkdtemp()).resolve()
        self.addCleanup(shutil.rmtree, tmp, True)
        patches = [patch.object(m.engine, "call_model", call_model), patch.object(m.engine, "wait_for_load", lambda rec: rec.update(load_at_start=1.0))]
        if setup is not None:
            patches.append(patch.object(m, "arm_setup", setup))
        elif arm == A:
            patches.append(patch.object(m, "arm_setup", lambda project, a, pp: {"status": "ready", "setup_s": 0}))
        for pt in patches:
            pt.start()
            self.addCleanup(pt.stop)
        rec = m.one_call(item, SimpleNamespace(model="claude-sonnet-5-5", timeout=60, call_budget=1.0), m.engine.Ports(6300), artifacts or tmp / "artifacts", None, p)
        return rec, calls, tmp

    def test_a_good_arm_c_cell_is_collected_with_cost_fidelity_and_timing(self):
        rec, calls, tmp = self.run_one(C, self.ok_result)
        self.assertEqual((rec["infrastructure_error"], rec["deliverable"], rec["spec_files"], rec["out_of_scope_writes"]), (False, True, ["tests/new.spec.ts"], []))
        self.assertEqual(rec["cost"]["total_tokens"], 1260)
        self.assertTrue(rec["compliance"]["fidelity"]["treated"])
        self.assertIsInstance(rec["port"], int)
        self.assertEqual(len(rec["attempts"]), 1)
        self.assertTrue(all(rec[k] for k in ("cell_started_utc", "cell_finished_utc")) and rec["load_at_start"] == 1.0)
        self.assertTrue(calls[0][2].endswith(m.orig.PLAN_LINE))
        self.assertTrue((tmp / "artifacts" / "v2-06-ours-2.0.1-r1" / "tests" / "new.spec.ts").is_file())

    def test_infrastructure_errors_are_retried_once_on_a_new_port_then_recorded(self):
        def bad(n, project, arm):
            return {"infrastructure_error": True, "timeout": False, "error": "isolation contract violated: x", "elapsed_ms": 1, "compliance": None}
        rec, calls, _ = self.run_one(B, bad, artifacts=self.artifacts_with_a_spec())
        self.assertEqual(len(calls), 2)
        self.assertTrue(rec["infrastructure_error"] and not rec["deliverable"])
        self.assertEqual(len(rec["attempts"]), 2)
        self.assertNotEqual(calls[0][1], calls[1][1])
        self.assertTrue(m.is_aborted(rec))

    def artifacts_with_a_spec(self):
        root = Path(tempfile.mkdtemp()).resolve()
        self.addCleanup(shutil.rmtree, root, True)
        (root / "v2-06-official-generator-r1" / "tests").mkdir(parents=True)
        (root / "v2-06-official-generator-r1" / "tests" / "a.spec.ts").write_text("import { test } from '@playwright/test';\ntest('a', async () => {});\n")
        return root

    def test_a_fatal_usage_limit_is_not_retried(self):
        fatal = lambda n, project, arm: {"infrastructure_error": True, "fatal_infrastructure": True, "timeout": False, "error": "limit", "elapsed_ms": 1}
        rec, calls, _ = self.run_one(C, fatal)
        self.assertEqual(len(calls), 1)
        self.assertTrue(rec["infrastructure_error"])

    def test_arm_b_without_a_source_deliverable_is_unavailable_not_aborted_and_makes_no_call(self):
        rec, calls, _ = self.run_one(B, self.ok_result)
        self.assertEqual(calls, [])
        self.assertTrue(rec["unavailable"].startswith("this model's arm A"))
        self.assertFalse(rec["infrastructure_error"] or m.is_aborted(rec))

    def test_arm_b_reviews_the_copied_source_specs_as_untracked_files(self):
        def review(n, project, arm):
            status = subprocess.run(["git", "status", "--porcelain", "--untracked-files=all"], cwd=project, capture_output=True, text=True).stdout.splitlines()
            self.assertEqual(status, ["?? tests/a.spec.ts"])
            (project / "tests" / "a.spec.ts").write_text("// reviewed\n")
            return dict(self.ok_result(n, project, arm), compliance=None)
        rec, calls, _ = self.run_one(B, review, artifacts=self.artifacts_with_a_spec())
        self.assertEqual(len(calls), 1)
        self.assertIn("tests/a.spec.ts", rec["spec_files"])
        self.assertTrue(calls[0][2].endswith(m.rev.TASK_LINE))

    def test_arm_a_setup_unavailable_makes_no_call_and_is_an_infrastructure_outcome(self):
        rec, calls, _ = self.run_one(A, self.ok_result, setup=lambda project, arm, p: {"status": "UNAVAILABLE", "reason": "init-agents failed", "setup_s": 1})
        self.assertEqual(calls, [])
        self.assertTrue(rec["infrastructure_error"] and rec["setup_unavailable"] and m.is_aborted(rec))
        self.assertEqual(rec["unavailable"], "init-agents failed")


class DryIntegration(unittest.TestCase):
    """Drives the imported v1 run_model/analyze path with stubbed calls (no model, no scoring) to prove the wiring."""

    def stub_call(self, item, args, ports, artifacts, mcfg, p):
        arm, ordinal = item["arm"], item["ordinal"]
        files = [] if (arm == A and ordinal % 5 == 0) else [f"tests/{item['case']}.spec.ts"]
        events = {A: [init(A), use("Agent", {"subagent_type": "playwright-test-generator"}, "x"), use("mcp__playwright-test__generator_setup_page", {}, "y", parent="x"),
                      use("mcp__playwright-test__generator_write_test", {}, "z", parent="x"), res("y", "ok"), res("z", "ok"), result_event()],
                  B: [init(B), use("Skill", {"skill": "e2e-reviewer"}, "s"), result_event()], C: c_stream()}[arm]
        comp = ad.analyze_events(events, arm)
        cost = ad.cost_summary(events[-1]["modelUsage"], 0.5)
        return dict(item, attempts=[], call_id=f"{item['case']}-{arm}-r{item['repetition']}", spec_files=files, tests_files=files, out_of_scope_writes=[],
                    elapsed_ms=20000, timeout=False, num_turns=1, usage={"input_tokens": 1, "cached_input_tokens": 0, "output_tokens": 1},
                    usage_all_turns=[{"input_tokens": 1, "cached_input_tokens": 0, "output_tokens": 1}], cost=cost, cost_usd=0.5,
                    model_usage=events[-1]["modelUsage"], structured_output={"summary": "stub", "status": "complete"}, result_text=None, compliance=comp,
                    setup={"setup_s": 1.0}, load_at_start=41.0 if ordinal == 5 else 12.0, transcript_path=None, infrastructure_error=False,
                    deliverable=bool(files), cell_started_utc="t0", cell_finished_utc="t1", load_at_finish=10.0)

    def prepared(self, tmp):
        """Freeze in tmp, bind the v1 module to the v2 protocol and run the 36 stubbed cells of one model; returns the model directory."""
        m.build_freeze(tmp / "freeze.json")
        m.bind_v1()
        self.addCleanup(m.unbind_v1)
        m.v1.configure = lambda a, p, c: (tmp, None, "2.1.299 (Claude Code)")
        ns = argparse.Namespace(allow_live=True, resume=True, output=None)
        m.v1.run_model("claude-sonnet-5-5", ns, {})
        return tmp / "claude-sonnet-5-5", ns

    def write_scores(self, d, tmp, rows=()):
        scores = {"report": "final.json", "scores": list(rows), "report_sha256": m.digest(d / "final.json"), "freeze_sha256": m.digest(tmp / "freeze.json")}
        (d / "scores.json").write_text(json.dumps(scores))

    def test_run_freeze_resume_analyze_and_summary_wiring(self):
        with tempfile.TemporaryDirectory() as tmp, contextlib.redirect_stdout(io.StringIO()):
            tmp = Path(tmp).resolve()
            with patch.object(m, "BASE", tmp), patch.object(m, "LOCK", tmp / "freeze.json"), patch.object(m, "one_call", self.stub_call):
                d, ns = self.prepared(tmp)
                report = m.read(d / "final.json")
                self.assertEqual((report["protocol_id"], report["completed_calls"], len(report["runs"])), (m.PROTOCOL_ID, 36, 36))
                self.assertEqual(report["freeze_sha256"], m.digest(tmp / "freeze.json"))
                m.v1.run_model("claude-sonnet-5-5", ns, {})            # resume is a no-op
                self.write_scores(d, tmp)
                views = m.analyze_model("claude-sonnet-5-5")
                res_ = m.read(d / "results.json")
                self.assertEqual(set(views), set(m.VIEWS))
                self.assertTrue(res_["complete"])
                self.assertEqual(len(res_["cells"]), 36)
                self.assertFalse(res_["secondary_scored"])
                self.assertEqual(res_["fidelity_table"][A]["treated"], 12)          # the stub's A streams carry both generator tools
                self.assertEqual(res_["fidelity_table"][C]["treated"], 12)
                self.assertEqual(res_["fidelity_table"][B]["treated"], 0)           # the stub's B streams have no scanner run
                self.assertEqual(res_["load_flagged_cells"], 1)
                self.assertEqual(res_["views"]["itt"]["cells_in_view"], {A: 12, B: 12, C: 12})
                self.assertEqual(res_["views"]["as_treated"]["cells_in_view"][B], 0)
                self.assertEqual(res_["cost_table"][C]["own"]["total"], 12 * 1260)
                self.assertEqual(res_["cost_table"][C]["own"]["processed"], 12 * 260)
                self.assertEqual(res_["cost_table"][B]["pipeline"]["total_tokens"], 12 * 1260 * 2)
                self.assertIn("task_metric_diffs", res_["views"]["itt"])
                (d / "secondary.json").write_text(json.dumps({"rows": {}, "report_sha256": "x", "freeze_sha256": "y"}))
                with self.assertRaisesRegex(ValueError, "secondary scores are not bound"):
                    m.analyze_model("claude-sonnet-5-5")
                (d / "secondary.json").unlink()
                m.summary_cmd(None, None)
                text = (tmp / "summary.md").read_text()
                for needle in ("Fidelity", "Pre-registered pooled analysis", "Family cross-model rule", "quality/100k processed", "No inference is claimed"):
                    self.assertIn(needle, text)
                self.assertTrue((tmp / "summary.json").is_file())

    def test_secondary_scoring_flow_and_the_two_family_summary(self):
        with tempfile.TemporaryDirectory() as tmp, contextlib.redirect_stdout(io.StringIO()):
            tmp = Path(tmp).resolve()
            with patch.object(m, "BASE", tmp), patch.object(m, "LOCK", tmp / "freeze.json"), patch.object(m, "one_call", self.stub_call):
                d, ns = self.prepared(tmp)
                runs = {m.v1.identity(r): r for r in m.read(d / "final.json")["runs"]}
                rows = []
                for r in sorted(runs.values(), key=lambda r: r["ordinal"]):
                    row = dict(m.v1.synthetic_row(r), deliverable=bool(r["spec_files"]), spec_files=r["spec_files"], clean=r["arm"] == C, refactor_score=1.0 if r["arm"] == C else 0.0)
                    rows.append(row)
                self.write_scores(d, tmp, rows)
                seen = []

                def fake_variant(case, src, specs, edits, ports):
                    seen.append((case, edits[0]["find"]))
                    return {"ok": not any(e["find"] == "<main>" for e in edits)}      # True for the text class, False for the structure class
                with patch.object(m, "run_variant", fake_variant):
                    m.score_secondary("claude-sonnet-5-5")
                sec = m.read(d / "secondary.json")
                self.assertTrue(sec["complete"])
                self.assertEqual(sec["report_sha256"], m.digest(d / "final.json"))
                self.assertEqual(len(seen), 12 * 2)                                   # only the clean arm C cells, two classes each
                c_row = next(v for k, v in sec["rows"].items() if "-ours-2.0.1-" in k)
                a_row = next(v for k, v in sec["rows"].items() if "-official-generator-" in k)
                self.assertEqual((a_row["text_label"], a_row["structure"]), (None, None))
                self.assertEqual((c_row["text_label"], c_row["structure"]), (True, False))   # the fake passes the text class and fails the structure class
                with patch.object(m, "run_variant", side_effect=AssertionError("resume must not rerun scored cells")):
                    m.score_secondary("claude-sonnet-5-5")
                partial = m.read(d / "secondary.json")
                (d / "secondary.json").write_text(json.dumps(dict(partial, complete=False)))
                with self.assertRaisesRegex(ValueError, "incomplete"):
                    m.analyze_model("claude-sonnet-5-5")
                (d / "secondary.json").write_text(json.dumps(partial))
                m.analyze_model("claude-sonnet-5-5")
                res_ = m.read(d / "results.json")
                self.assertTrue(res_["secondary_scored"])
                c_cells = [c for c in res_["cells"] if c["arm"] == C]
                self.assertEqual({(c["sec_text_label"], c["sec_structure"]) for c in c_cells}, {(1.0, 0.0)})
                self.assertEqual({(c["sec_text_label"], c["sec_structure"]) for c in res_["cells"] if c["arm"] == A}, {(0.0, 0.0)})
                diffs = res_["views"]["itt"]["task_metric_diffs"]["C_minus_A"]
                self.assertEqual(set(diffs["sec_text_label"].values()), {1.0})
                self.assertEqual(set(diffs["sec_structure"].values()), {0.0})
                # a Codex-style output root beside the Claude one: the combined table is descriptive and lists both families
                codex_root = tmp / "codex-root"
                (codex_root / "gpt-6-sol").mkdir(parents=True)
                cells = []
                for t in TASKS:
                    for rep in (1, 2):
                        cells.append(dict(cell(t, A, rep, 0.0), fidelity_class="official-tool", as_treated=True))
                        cells.append(dict(cell(t, C, rep, 1.0), fidelity_class=None, as_treated=True))
                labels = {n: {"eligible": True} for n in ("C_minus_A", "B_minus_A", "C_minus_B")}
                (codex_root / "gpt-6-sol/results.json").write_text(json.dumps({"complete": True, "cells": cells, "model": "gpt-6-sol", "family": "codex", "lineage": "gpt-6",
                                                                                "views": {"itt": {"labels": labels}, "primary": {"labels": labels}, "as_treated": {"labels": labels}}}))
                m.summary_cmd(None, str(codex_root))
                text = (tmp / "summary.md").read_text()
                self.assertIn("Both families, descriptive only", text)
                self.assertIn("codex", text)
                combined = m.read(tmp / "summary.json")["pooled"]["combined|itt/itt|C_minus_A|refactor_score"]
                self.assertEqual(combined["models_included"], ["claude-sonnet-5-5", "gpt-6-sol"])
                self.assertEqual(sorted(combined["family_means"]), ["claude", "codex"])
                pooled = m.read(tmp / "summary.json")["pooled"]
                for key in ("combined|as_treated/as_treated|C_minus_A|refactor_score", "combined|itt/primary|C_minus_A|refactor_score"):
                    self.assertIn(key, pooled)
                self.assertNotIn("combined|as_treated/primary|C_minus_A|refactor_score", pooled)      # the mis-pairing is gone
                self.assertIn("Discordance between views", text)

class ExecutedNotMentioned(unittest.TestCase):
    """Review finding F1: a step counts only when the command is executed; text that merely mentions a script does not."""
    SK = "/w/project/.claude/skills/"

    def fid(self, arm, *events):
        return ad.analyze_events([init(arm)] + list(events) + [result_event()], arm)["fidelity"]

    def bash(self, command, uid="b", parent=None):
        return use("Bash", {"command": command}, uid, parent=parent)

    def test_cat_ls_echo_grep_bash_n_and_here_document_text_are_mentions_only(self):
        sk = self.SK
        f = self.fid(B, use("Skill", {"skill": "e2e-reviewer"}, "s"),
                     self.bash(f"cat {sk}e2e-reviewer/scripts/scan.sh | head -5", "a"),
                     self.bash("echo 'node_modules/.bin/playwright test' > /dev/null", "b"),
                     self.bash(f"ls -la {sk}playwright-test-generator/best-practices.md {sk}playwright-test-generator/code-rules.md", "c"),
                     self.bash(f"bash -n {sk}e2e-reviewer/scripts/scan.sh", "d"),
                     self.bash("cat > notes.txt <<'EOF'\nbash scan.sh x\nnode_modules/.bin/playwright test\nrun-preflight-target.sh\nEOF", "e"),
                     self.bash("grep -n 'playwright test' package.json", "f"),
                     self.bash(f"echo {sk}playwright-test-generator/scripts/run-preflight-target.sh agent-browser", "g"))
        self.assertEqual((f["scan_sh_runs"], f["playwright_test_runs"], f["preflight_runs"], f["exploration_runs"]), (0, 0, 0, 0))
        self.assertGreaterEqual(f["scan_sh_mentions"], 3)
        self.assertGreaterEqual(f["playwright_test_mentions"], 3)
        self.assertGreaterEqual(f["preflight_mentions"], 2)
        self.assertEqual((f["hot_refs_read"], f["hot_refs_mentioned"]), ([], ["best-practices.md", "code-rules.md"]))      # ls is not a read
        self.assertFalse(f["treated"])
        self.assertTrue(f["invoked"])

    def test_real_executions_in_their_usual_forms_are_counted(self):
        sk = self.SK
        pin = "E2E_SMELL_ALLOW_PROJECT_ESLINT=0 /usr/bin/env -u E2E_SMELL_RG_BIN /bin/bash -p "
        commands = [f"{pin}{sk}e2e-reviewer/scripts/scan.sh tests/a.spec.ts",                     # the pinned form
                    f"E2E_SMELL_NO_AST_GREP_DOWNLOAD=1 bash {sk}e2e-reviewer/scripts/scan.sh tests/b.spec.ts",
                    f"cd /w/project && bash -c 'cd tests && /bin/bash -p {sk}e2e-reviewer/scripts/scan.sh a.spec.ts'",     # nested
                    f"{sk}e2e-reviewer/scripts/scan.sh tests/c.spec.ts",                              # direct
                    f"timeout 60 {sk}e2e-reviewer/scripts/scan.sh tests/d.spec.ts"]
        f = self.fid(B, *[self.bash(c, f"s{i}") for i, c in enumerate(commands)])
        self.assertEqual((f["scan_sh_runs"], f["scan_sh_pinned_runs"]), (5, 1))
        runs = ["timeout 120 npx --no-install playwright test a", "npx playwright test", "pnpm exec playwright test", "yarn playwright test",
                "cd /w/project && ./node_modules/.bin/playwright test --repeat-each 2", "node node_modules/.bin/playwright test",
                "for f in a b; do playwright test $f; done", "playwright test 2>&1 | tail -30", "CI=1 npm exec -- playwright test x"]
        f = self.fid(C, *[self.bash(c, f"t{i}") for i, c in enumerate(runs)])
        self.assertEqual((f["playwright_test_runs"], f["repeat_each_runs"], f["baseline_runs"]), (len(runs), 1, len(runs)))
        f = self.fid(C, self.bash(f"{sk}playwright-test-generator/scripts/run-preflight-target.sh http://127.0.0.1:1/ /", "p"),
                     self.bash("npx --no-install playwright cli open http://127.0.0.1:1/", "x"), self.bash("playwright-cli snapshot", "y"))
        self.assertEqual((f["preflight_runs"], f["exploration_runs"]), (1, 2))

    def test_reference_reads_resolve_cd_across_calls_and_need_a_read_verb(self):
        sk = self.SK
        f = self.fid(C, self.bash(f"cd {sk}playwright-test-generator", "a"), self.bash("cat best-practices.md code-rules.md", "b"))
        self.assertEqual(f["hot_refs_read"], ["best-practices.md", "code-rules.md"])                 # cd in one call, cat in the next
        f = self.fid(C, self.bash(f"cd {sk}playwright-test-generator && cat *.md | wc -l", "a"))
        self.assertEqual(sorted(f["generator_refs_read"]), sorted(ad.GENERATOR_REFS))               # a glob in the skill directory
        f = self.fid(C, self.bash(f"cd {sk}playwright-test-generator", "a"), self.bash("cd /w/project/docs && cat best-practices.md", "b"))
        self.assertEqual(f["generator_refs_read"], [])                                              # another directory
        f = self.fid(C, self.bash("cat docs/best-practices.md", "a"), self.bash("sed -n 1,50p $SKILL_ROOT/scenario-design.md", "b"))
        self.assertEqual(f["generator_refs_read"], ["scenario-design.md"])                           # a project file is not a skill reference
        f = self.fid(C, self.bash(f"head -20 {sk}playwright-test-generator/SKILL.md", "a"), self.bash(f"echo {sk}e2e-reviewer/SKILL.md", "b"))
        self.assertEqual((f["generator_skill_loaded"], f["reviewer_skill_loaded"]), (True, False))

    def test_independent_review_needs_a_reviewer_naming_spawn_not_the_word_review(self):
        write = use("Write", {"file_path": "/w/project/tests/a.spec.ts", "content": "x"}, "w")
        f = self.fid(C, write, use("Agent", {"subagent_type": "general-purpose", "description": "check output", "prompt": "Please review the test run output"}, "ag"))
        self.assertEqual((f["independent_review_agents"], f["review_mentions_after_write"]), (0, 1))
        f = self.fid(C, write, use("Agent", {"subagent_type": "general-purpose", "description": "V6 reviewer", "prompt": "x"}, "ag"))
        self.assertEqual((f["independent_review_agents"], f["reviewer_named_spawns_after_write"]), (1, 1))
        f = self.fid(C, write, use("Agent", {"subagent_type": "general-purpose", "description": "g", "prompt": "Apply the e2e-reviewer skill"}, "ag"))
        self.assertEqual(f["independent_review_agents"], 1)
        f = self.fid(C, write, use("Skill", {"skill": "e2e-reviewer"}, "sk", parent="ag"))              # the subagent itself loads the reviewer skill
        self.assertEqual((f["independent_review_agents"], f["child_reviewer_skill_calls_after_write"]), (1, 1))
        f = self.fid(C, use("Agent", {"subagent_type": "general-purpose", "description": "V6 reviewer", "prompt": "x"}, "ag"), write)
        self.assertEqual(f["independent_review_agents"], 0)                                          # before the first spec write

    def test_shell_split_handles_quotes_comments_and_substitution(self):
        split = ad.split_simple_commands
        self.assertEqual(split("a 'b && c' \"d ; e\" # f g\nh && i | j"), [["a", "b && c", "d ; e"], ["h"], ["i"], ["j"]])
        self.assertEqual(split("x=$(playwright test) ; echo `ls`"), [["x="], ["playwright", "test"], ["echo"], ["ls"]])
        self.assertEqual(split("cmd 2>&1 &> out >&2"), [["cmd", "2>&1", "&>", "out", ">&2"]])
        self.assertEqual(split("cat > f <<'EOF'\nplaywright test\nEOF\nls"), [["cat", ">", "f", "<<EOF"], ["ls"]])
        self.assertEqual(ad.unwrap_command(["FOO=1", "env", "-u", "X", "timeout", "-k", "5", "10", "npx", "--no-install", "playwright", "test"]), ["playwright", "test"])

    def test_unintended_skill_calls_and_denials_are_recorded(self):
        f = self.fid(B, use("Skill", {"skill": "e2e-reviewer"}, "s1"), use("Skill", {"skill": "simplify"}, "s2"),
                     {"type": "user", "message": {"content": [{"type": "tool_result", "tool_use_id": "s2", "is_error": True, "content": "denied"}]}})
        self.assertEqual((f["unintended_skill_calls"], f["skill_call_errors"]), (["simplify"], 1))
        self.assertEqual(self.fid(A)["unintended_skill_calls"], [])
        self.assertEqual(self.fid(A, use("Skill", {"skill": "e2e-reviewer"}, "s"))["unintended_skill_calls"], ["e2e-reviewer"])      # arm A has no skills at all


class SelectorReader(unittest.TestCase):
    """Review finding F6: selector literals only, no property access in interpolations, substring selectors that survive are not counted."""

    def test_property_access_prose_and_interpolations_are_not_selectors(self):
        for text, token in (("await expect(page.getByText(`${track.title}`)).toBeVisible();", "title"),
                            ("await expect(page.getByText(`${items.length} left`)).toBeVisible();", "length"),
                            ("const label = 'Back to list.'; await page.getByRole('button', { name: 'Back to list.' });", "list"),
                            ("const n = data.length; // '.length'", "length"),
                            ("await page.goto('/v3.title');", "title")):
            self.assertFalse(m.references_token(text, token), text)
        for text, token in (("await page.locator('ul.items').click();", "items"), ("const SEL = { deck: '.deck' };", "deck"),
                            ("await page.locator(`#row-${id} .title`).click();", "title"), ("await page.$('[id=\"fc-flip\"]');", "fc-flip"),
                            ("await page.click('button#fc-flip')", "fc-flip")):
            self.assertTrue(m.references_token(text, token), text)

    def test_css_like_literals(self):
        for lit, expected in ((".deck", True), ("article.deck", True), ("ul > li.item", True), ("[data-x]", True), ("#a, #b", True),
                              ("Back to list.", False), ("tests/a.spec.ts", False), ("done", False), ("Session done", False), ("", False), ("a.b c", True)):
            self.assertEqual(m.css_like(lit), expected, lit)

    def test_substring_attribute_selectors_that_survive_the_rename_are_not_counted(self):
        text = "await page.locator('[class*=\"deck\"]').first().click();"
        self.assertTrue(m.references_token(text, "deck"))                                            # deck was renamed to something without the token
        self.assertFalse(m.references_token(text, "deck", kept=["tile--deck"]))                     # tile--deck still contains it
        self.assertTrue(m.references_token("await page.locator('[class~=\"deck\"]').first();", "deck", kept=["tile--deck"]))   # whole-word selector breaks

    def test_dynamic_selector_hint(self):
        self.assertTrue(m.dynamic_selector_hint(["await page.locator('#row-' + id).click();"]))
        self.assertTrue(m.dynamic_selector_hint(["await page.locator(`#row-${id}`).click();"]))
        self.assertFalse(m.dynamic_selector_hint(["await page.locator('#row-1').click();", None]))


class TimeoutAndDiscordance(unittest.TestCase):
    def test_timed_out_call_keeps_a_lower_bound_token_record(self):
        msg = lambda mid, **u: {"type": "assistant", "message": {"id": mid, "usage": u, "content": [{"type": "text", "text": "x"}]}}
        events = [init(C), msg("m1", input_tokens=2, cache_creation_input_tokens=100, cache_read_input_tokens=0, output_tokens=5),
                  msg("m1", input_tokens=2, cache_creation_input_tokens=100, cache_read_input_tokens=0, output_tokens=16),      # streamed copy of m1
                  msg("m2", input_tokens=3, cache_creation_input_tokens=10, cache_read_input_tokens=100, output_tokens=7)]
        got = ad.partial_usage(events)
        self.assertEqual((got["uncached_input"], got["cache_creation"], got["cache_read"], got["output"]), (5, 110, 100, 23))
        self.assertEqual((got["processed_tokens"], got["total_tokens"], got["lower_bound"], got["messages"]), (138, 238, True, 2))
        self.assertIsNone(ad.partial_usage([init(C)]))
        rec_cost = m.cost_of({"cost": got})
        self.assertEqual((rec_cost["measured"], rec_cost["lower_bound"], rec_cost["processed"]), (True, True, 138))
        self.assertFalse(m.cost_of({"cost": ad.cost_summary({"x": {"inputTokens": 1}}, None)})["lower_bound"])

    def test_the_call_path_returns_the_partial_record_on_a_wall_clock_timeout(self):
        tmp = Path(tempfile.mkdtemp(prefix="v2c-timeout-")).resolve()
        self.addCleanup(shutil.rmtree, tmp, True)
        project = tmp / "project"
        project.mkdir()
        stream = "\n".join(json.dumps(e) for e in [init(C, cwd=str(project)), {"type": "assistant", "message": {
            "id": "m1", "usage": {"input_tokens": 4, "output_tokens": 9}, "content": []}}])

        class Fake:
            pid = 1
            returncode = -9
            calls = 0

            def __init__(self, argv, **kw):
                pass

            def communicate(self, prompt=None, timeout=None):
                Fake.calls += 1
                if Fake.calls == 1:
                    raise subprocess.TimeoutExpired("claude", timeout)
                return stream, ""
        engine = SimpleNamespace(CODEX_TRANSCRIPTS=tmp / "transcripts", FRAME=m.engine.FRAME, OUTPUT_SCHEMA=m.engine.OUTPUT_SCHEMA, sanitize=m.engine.sanitize)
        ad.ARM_LINES.update(m.arm_lines())
        with patch.object(ad.subprocess, "Popen", Fake), patch.object(ad.os, "killpg"):
            rec = ad.configure(engine)(project, tmp, C, "TASK", "claude-sonnet-5-5", 1, 1.0)
        self.assertEqual((rec["timeout"], rec["infrastructure_error"], rec["error"]), (True, False, "wall-clock limit"))
        self.assertEqual((rec["cost"]["output"], rec["cost"]["uncached_input"], rec["cost"]["lower_bound"]), (9, 4, True))
        self.assertTrue(m.cost_of(rec)["measured"])

    def test_cost_table_keeps_timed_out_cells_in_the_ratio_and_reports_them(self):
        base = CostAccounting().cells()
        cells = [dict(c, cost=dict(c["cost"], lower_bound=False), timeout=False) for c in base]
        cells[2].update(timeout=True, elapsed_s=1500.0)
        cells[2]["cost"].update(lower_bound=True)
        m.attach_pipeline(cells)
        t = m.cost_table(cells)[C]
        self.assertEqual((t["timeouts"], t["timeout_seconds"], t["cells_with_lower_bound_tokens"], t["cells_with_complete_tokens"]), (1, 1500.0, 1, 1))
        self.assertEqual(t["quality_per_100k_processed"], round(100000 / 150000, 4))
        self.assertEqual(m.cost_table(cells)[A]["timeouts"], 0)

    def test_discordance_lists_the_views_that_differ_from_itt(self):
        names = [n for n, _, _ in m.CONTRASTS]
        mk = lambda label: {"labels": {n: {"label": label if n == "C_minus_A" else "nothing (rule not met)"} for n in names}}
        results = {"x": {"views": {v: mk("suggestive: C better" if v in ("itt", "invoked") else "nothing (rule not met)") for v in m.VIEWS}}}
        verdicts = {f"{v}|{n}": {"verdict": "consistent: C better in 2 of 4 models" if (v in ("itt", "load_clean") and n == "C_minus_A") else "not consistent"}
                    for v in m.VIEWS for n in names}
        d = m.discordance(results, verdicts)
        self.assertEqual(d["family"]["C_minus_A"], ["invoked", "as_treated"])
        self.assertEqual(d["family"]["B_minus_A"], [])
        self.assertEqual(d["models"]["x C_minus_A"], {"as_treated": "nothing (rule not met)", "load_clean": "nothing (rule not met)"})
        self.assertEqual(d["models"]["x B_minus_A"], {})


class CodexViewPairing(unittest.TestCase):
    """Review finding F2: the Claude as_treated is paired with the Codex as_treated view, the Codex primary view is a separate analogue."""

    def codex_result(self):
        t = TASKS[0]
        mk = lambda arm, score, fc, treated: dict(cell(t, arm, 1, score), fidelity_class=fc, as_treated=treated)
        cells = [mk(A, 0.0, "official-tool", True), mk(A, 1.0, "unverified", False), mk(C, 1.0, None, False), mk(C, 0.0, None, True)]
        return {"cells": cells}

    def test_view_semantics_on_codex_shaped_cells(self):
        res = self.codex_result()
        diff = lambda view: m.codex_task_diffs(res, view, "C_minus_A", [TASKS[0]], "refactor_score")[TASKS[0]]
        self.assertEqual(diff("itt"), 0.0)             # A mean 0.5, C mean 0.5
        self.assertEqual(diff("as_treated"), 0.0)      # A: the official-tool cell (0), C: the treated cell (0) -- every arm gated
        self.assertEqual(diff("primary"), 0.5)         # A: the official-tool cell (0), C: BOTH cells (0.5) -- arm C is not gated
        self.assertEqual([c["arm"] for c in m.codex_cells(res, "as_treated")], [A, C])
        self.assertEqual(len(m.codex_cells(res, "primary")), 3)
        with self.assertRaises(ValueError):
            m.codex_cells(res, "upper")

    def test_pairs_and_documents(self):
        self.assertEqual(m.CODEX_PAIRS, (("itt", "itt"), ("as_treated", "as_treated"), ("itt", "primary")))
        proto = m.read(m.PROTOCOL)
        for text in (proto["views"]["mapping_to_codex_v2"], proto["pooled_analysis"]["view_mapping_to_codex_successor"], m.README.read_text()):
            self.assertNotIn("its primary (official-tool) view", text)
            self.assertNotIn("its `primary` as-treated view", text)
        self.assertIn("as_treated", proto["views"]["mapping_to_codex_v2"])
        codex_runner = ROOT / "scripts/evals/run-generator-multimodel-v2-codex.py"
        if codex_runner.is_file():                    # the pairing relies on these view names existing in the Codex successor
            body = codex_runner.read_text()
            self.assertIn('VIEWS = ("primary", "itt", "upper", "load_clean", "as_treated")', body)
            self.assertIn('cell.get("as_treated")', body)
            self.assertIn('fidelity_class"] in PRIMARY_CLASSES', body)

    def test_combined_descriptive_accepts_the_as_treated_pair(self):
        p = m.protocol()
        mkc = lambda e: {"complete": True, "lineage": "claude-5", "views": {"as_treated": {"labels": {"C_minus_A": {"eligible": True}},
                         "task_metric_diffs": {"C_minus_A": {"refactor_score": {t: e for t in TASKS}}}}}}
        cells = []
        for t in TASKS:
            cells += [dict(cell(t, A, 1, 0.0), fidelity_class="official-tool", as_treated=True), dict(cell(t, C, 1, 1.0), fidelity_class=None, as_treated=True)]
        codex = {"gpt-6-sol": {"complete": True, "lineage": "gpt-6", "cells": cells, "views": {"as_treated": {"labels": {"C_minus_A": {"eligible": True}}}}}}
        out = m.combined_descriptive({"a": mkc(0.5)}, codex, p, "as_treated", "as_treated", "C_minus_A", "refactor_score")
        self.assertEqual((out["models_included"], out["family_means"]), (["a", "gpt-6-sol"], {"claude": 0.5, "codex": 1.0}))



# ------------------------------------------------------------------------------------------------ coexistence with the Codex campaign

CLAUDE_DRIVER = "python3 -B scripts/evals/run-generator-multimodel-v2-claude.py drive --allow-live"
CODEX_V3_DRIVER = "/usr/bin/python3 -B scripts/evals/run-generator-multimodel-v3-codex.py drive --allow-live"   # the argv seen on this host


def counting_ports():
    return m.engine.Ports(0)


class CampaignGuard(unittest.TestCase):
    """The guard refuses only for a TRUE conflict and lets the Codex container campaign run beside this one."""

    def ps(self, *rows):
        return "\n".join(f"{pid} {ppid} {cmd}" for pid, ppid, cmd in rows)

    def report(self, rows, listening="", env_lookup=None, root=None, pid=999999):
        return m.guard_report(self.ps(*rows), listening_text=listening, env_lookup=env_lookup, mine_root=root or m.BASE, pid=pid)

    def test_the_running_codex_v3_driver_is_not_a_conflict(self):
        out = self.report([(3874, 1, CODEX_V3_DRIVER)])
        self.assertEqual(out["conflicts"], [])
        self.assertEqual([(c["script"], c["verb"]) for c in out["coexisting"]], [("run-generator-multimodel-v3-codex.py", "drive")])
        for script in ("v2-codex", "v4-codex"):
            self.assertEqual(self.report([(5, 1, f"python3 scripts/evals/run-generator-multimodel-{script}.py harness-check --allow-live")])["conflicts"], [])
        self.assertEqual(self.report([(6, 1, "python3 scripts/evals/run-generator-ablation-v2.py drive --allow-live")])["conflicts"], [])

    def test_true_conflicts_are_claude_family_zeppelin_and_unclassified(self):
        cases = {"claude-family": ["python3 scripts/evals/run-generator-multimodel-v2-claude.py drive --allow-live",
                                   "python3 scripts/evals/run-generator-multimodel-v1.py run --model claude-sonnet-5-5 --allow-live"],
                 "zeppelin": ["python3 scripts/evals/run-generator-oss-eval-v1.py drive --allow-live",
                              "python3 scripts/evals/run-generator-thin-eval-v1.py drive --allow-live",
                              "python3 scripts/evals/run-generator-loop-v2.py run --allow-live"],
                 "unclassified": ["python3 scripts/evals/run-generator-skill-effect-v8.py run --allow-live",
                                  "python3 scripts/evals/run-generator-brand-new-driver.py drive"]}
        for kind, commands in cases.items():
            for command in commands:
                out = self.report([(77, 1, command)])
                self.assertEqual([c["kind"] for c in out["conflicts"]], [kind], command)
                self.assertEqual(out["conflicts"][0]["pid"], 77)

    def test_matching_is_by_argument_vector_and_excludes_own_ancestors(self):
        rows = [(300, 200, CLAUDE_DRIVER),                                          # this process
                (200, 1, f"timeout 900 {CLAUDE_DRIVER}"),                            # its wrapper: an ancestor
                (60, 1, "vim scripts/evals/run-generator-multimodel-v2-claude.py notes"),   # not a live verb
                (61, 1, "grep -r run-generator-multimodel-v2-claude.py drive src"),         # no python interpreter before the script
                (62, 1, "bash -c python3 scripts/evals/run-generator-oss-eval-v1.py drive"),  # ps flattens a wrapper's text: it is the parent of a real driver
                (63, 1, "python3 scripts/evals/run-generator-oss-eval-v1.py"),               # no verb
                (64, 1, "caffeinate -i python3 scripts/evals/run-generator-oss-eval-v1.py preflight --allow-live"),   # a real wrapped driver
                (65, 1, "python3 scripts/evals/run-generator-multimodel-v2-claude.py init-check --model z --allow-live"),
                (None, None, "not a ps row")]
        text = "\n".join(f"{a} {b} {c}" if a else c for a, b, c in rows)
        found = m.running_drivers(text)
        self.assertEqual([d["pid"] for d in found], [300, 200, 62, 64, 65])
        out = m.guard_report(text, listening_text="", mine_root=m.BASE, pid=300)
        self.assertEqual(sorted(c["pid"] for c in out["conflicts"]), [62, 64, 65])
        for verb in ("drive", "run", "preflight", "init-check", "harness-check", "score", "validate-refactors"):
            self.assertIn(verb, m.CAMPAIGN_VERBS)

    def test_a_driver_that_overrides_its_root_onto_this_one_is_a_conflict(self):
        mine = m.BASE
        lookup = lambda pid, name: str(mine / "nested") if name == "MULTIMODEL_V3_CODEX_DIR" else None
        out = self.report([(3874, 1, CODEX_V3_DRIVER)], env_lookup=lookup)
        self.assertEqual([c["kind"] for c in out["conflicts"]], ["output-root"])
        self.assertEqual(self.report([(3874, 1, CODEX_V3_DRIVER)], env_lookup=lambda pid, name: None)["conflicts"], [])
        self.assertEqual(m.env_value("python3 x.py drive A=1 MULTIMODEL_V3_CODEX_DIR=/some/dir B=2", "MULTIMODEL_V3_CODEX_DIR"), "/some/dir")
        self.assertIsNone(m.env_value("python3 x.py drive XMULTIMODEL_V3_CODEX_DIR=/d", "MULTIMODEL_V3_CODEX_DIR"))
        self.assertTrue(m.roots_overlap("/a/b", "/a/b/c") and m.roots_overlap("/a/b/c", "/a/b") and m.roots_overlap("/a/b", "/a/b"))
        self.assertFalse(m.roots_overlap("/a/b", "/a/bc"))

    def test_an_overlapping_port_range_of_a_foreign_driver_is_a_conflict(self):
        clash = dict(m.KNOWN_DRIVERS["run-generator-multimodel-v3-codex.py"], bases=(m.port_plan()["generation"][0] - 5,), offsets=(0,))
        with patch.dict(m.KNOWN_DRIVERS, {"run-generator-multimodel-v3-codex.py": clash}):
            out = self.report([(3874, 1, CODEX_V3_DRIVER)])
            self.assertEqual({c["kind"] for c in out["conflicts"]}, {"ports"})
            self.assertTrue(any(c["pid"] == 3874 and "may use host ports" in c["reason"] for c in out["conflicts"]))
            self.assertTrue(m.static_conflicts(m.BASE, m.own_ranges()))      # the static check sees it with no process at all
            self.assertTrue(self.report([])["conflicts"])

    def test_a_socket_listening_inside_this_campaigns_ranges_is_a_conflict(self):
        plan = m.port_plan()
        inside, outside = plan["scoring"][0] + 3, plan["scoring"][0] - 1
        lsof = f"p100\nn127.0.0.1:{outside}\np4321\nn*:{inside}\nn[::1]:{inside}\np5\nnlocalhost:http"
        self.assertEqual(m.listening_ports(lsof), {outside: 100, inside: 4321})
        out = self.report([], listening=lsof)
        self.assertEqual([(c["kind"], c["pid"]) for c in out["conflicts"]], [("ports", 4321)])
        self.assertIn(str(inside), out["conflicts"][0]["reason"])
        self.assertEqual(self.report([], listening="p1\nn*:22")["conflicts"], [])
        with patch.object(m, "lsof_text", return_value=None):                                  # lsof unavailable: reported, not a conflict
            out = m.guard_report(self.ps(), mine_root=m.BASE, pid=1)
        self.assertEqual((out["conflicts"], out["lsof_available"]), ([], False))

    def test_the_shipped_constants_have_no_static_conflict(self):
        self.assertEqual(m.static_conflicts(m.BASE, m.own_ranges()), [])
        self.assertEqual(m.static_conflicts(m.CACHE_ROOT / "multimodel-v3-codex", m.own_ranges())[0]["kind"], "output-root")
        with patch.object(m, "PORT_OFFSET", 3000):
            kinds = {c["kind"] for c in m.static_conflicts(m.BASE, m.own_ranges())}
        self.assertEqual(kinds, {"ports"})                   # the Codex offset would collide
        with patch.object(m, "PORT_OFFSET", 40000):
            self.assertTrue(any("ephemeral" in c["reason"] for c in m.static_conflicts(m.BASE, m.own_ranges())))

    def test_the_drive_still_takes_one_flock_per_output_root(self):
        with tempfile.TemporaryDirectory() as tmp, patch.object(m, "BASE", Path(tmp)), \
                patch.object(m, "guard_report", return_value={"conflicts": [], "coexisting": [], "own_ranges": {}, "lsof_available": True, "output_root": tmp}):
            first = m.campaign_lock()
            self.addCleanup(first.close)
            with self.assertRaisesRegex(ValueError, "same output root"):
                m.campaign_lock()

    def test_every_other_run_generator_script_is_unclassified_so_a_new_driver_fails_closed(self):
        scripts = sorted(x.name for x in (ROOT / "scripts/evals").glob("run-generator-*.py"))
        self.assertTrue(set(m.KNOWN_DRIVERS) <= set(scripts))
        unknown = [x for x in scripts if x not in m.KNOWN_DRIVERS]
        self.assertTrue(unknown)
        for script in unknown:
            verdict = m.classify_driver({"pid": 1, "script": script, "verb": "drive"}, m.BASE, m.own_ranges())
            self.assertEqual(verdict["kind"], "unclassified", script)


class PortDisjointness(unittest.TestCase):
    """The exact port ranges of the full schedule, derived from the engine's own consumption, against the Codex campaign's."""

    @classmethod
    def setUpClass(cls):
        cls.plan = m.port_plan()
        cls.p = m.protocol()

    def fake_run(self, project, specs, *a, **k):
        return {"exit": 1, "passed": 0, "failed": 0, "skipped": 0, "errors": ["webServer timed out"], "ok": False, "seconds": 0}

    def test_scoring_consumes_at_most_the_planned_ports_worst_case(self):
        rows = m.schedule(self.p)
        total = 0
        with patch.object(m.engine, "run_playwright", self.fake_run), patch.object(m.engine, "wait_for_load", lambda record: None):
            for task in sorted({r["case"] for r in rows}):
                ports = counting_ports()
                m.engine.evaluate_specs(task, m.engine.CASES / task, None, ["tests/x.spec.ts"], ports)
                per_cell = 2 * (3 + len(m.engine.load_truth(task)["faults"]) + 1)
                self.assertEqual(ports.next, per_cell, task)         # every run retried once: the worst case equals the formula
                total += per_cell * sum(r["case"] == task for r in rows)
        lo, hi = self.plan["scoring"]
        self.assertEqual((lo, hi - lo + 1), (5300 + m.PORT_OFFSET + 1, total))

    def test_generation_and_secondary_consumption_match_the_plan(self):
        rows = m.schedule(self.p)
        ports, tmp = counting_ports(), Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, tmp, True)

        def build(case, arm, port, p, source=None):
            work = Path(tempfile.mkdtemp())
            (work / "project").mkdir()
            return work, work / "project", {"status": "ready", "setup_s": 0}
        bad = lambda *a, **k: {"infrastructure_error": True, "timeout": False, "error": "x", "elapsed_ms": 1}
        with patch.object(m, "build_cell_project", build), patch.object(m.engine, "call_model", bad), \
                patch.object(m.engine, "wait_for_load", lambda r: None), patch.object(m, "host_pressure", lambda: {}):
            m.one_call({"case": TASKS[0], "arm": C, "repetition": 1, "ordinal": 1}, SimpleNamespace(model="x", timeout=1, call_budget=1.0), ports, tmp, None, self.p)
        self.assertEqual(ports.next, 2)                                # two attempts per cell
        self.assertEqual(self.plan["generation"][1] - self.plan["generation"][0] + 1, 2 * len(rows))
        sec, stub = counting_ports(), Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, stub, True)
        (stub / "a.spec.ts").write_text("x")
        data = m.refactor_edits()
        with patch.object(m.engine, "run_playwright", self.fake_run), patch.object(m.engine, "wait_for_load", lambda r: None):
            for cls in m.SECONDARY_CLASSES:
                m.run_variant(TASKS[0], stub, ["tests/a.spec.ts"], data["classes"][cls]["cases"][TASKS[0]], sec)
        self.assertEqual(sec.next, 4)                                  # two classes x two attempts
        self.assertEqual(self.plan["secondary"][1] - self.plan["secondary"][0] + 1, 4 * len(rows))

    def test_the_ranges_are_disjoint_from_each_other_and_below_the_ephemeral_space(self):
        spans = sorted(self.plan.values())
        for (a_lo, a_hi), (b_lo, b_hi) in zip(spans, spans[1:]):
            self.assertLess(a_hi, b_lo)
        self.assertLess(spans[-1][1], m.EPHEMERAL_FLOOR)
        for fixed in m.ZEPPELIN_FIXED_PORTS:
            self.assertFalse(any(lo <= fixed <= hi for lo, hi in spans))

    def source_bases(self, name):
        return {int(x) for x in re.findall(r"Ports\((\d+)\)", (ROOT / "scripts/evals" / name).read_text())}

    def test_the_driver_table_matches_the_sources(self):
        engine_source = (ROOT / "benchmarks/generator-skill-effect-v3/../../scripts/evals/run-generator-skill-effect-v3.py").read_text()
        self.assertIn("Ports(5300)", engine_source)
        v1_bases = self.source_bases("run-generator-multimodel-v1.py")
        self.assertEqual(v1_bases, {6300, 6700})
        for name in ("v2-codex", "v3-codex", "v4-codex"):
            script = f"run-generator-multimodel-{name}.py"
            offset = int(re.search(r"^PORT_OFFSET = (\d+)", (ROOT / "scripts/evals" / script).read_text(), re.M).group(1))
            self.assertEqual(m.KNOWN_DRIVERS[script]["offsets"], (offset,), script)
            self.assertEqual(set(m.KNOWN_DRIVERS[script]["bases"]), {5300} | v1_bases | self.source_bases(script), script)
        mine = {5300} | v1_bases | self.source_bases("run-generator-multimodel-v2-claude.py")
        self.assertEqual(set(m.KNOWN_DRIVERS["run-generator-multimodel-v2-claude.py"]["bases"]), mine)
        self.assertEqual(m.KNOWN_DRIVERS["run-generator-multimodel-v2-claude.py"]["offsets"], (m.PORT_OFFSET,))
        for script, info in m.KNOWN_DRIVERS.items():
            self.assertTrue(self.source_bases(script) <= set(info["bases"]), script)
        self.assertEqual(self.source_bases("run-generator-loop-v2.py"), {23000, 24000})
        zeppelin = (ROOT / "scripts/evals/generator_oss_zeppelin.py").read_text()
        self.assertIn("PORT = %d" % m.ZEPPELIN_FIXED_PORTS[0], zeppelin)
        self.assertIn(":%d" % m.ZEPPELIN_FIXED_PORTS[1], zeppelin)

    @unittest.skipUnless((ROOT / "benchmarks/generator-multimodel-v3-codex/protocol.json").is_file(), "Codex v3 protocol not present")
    def test_the_full_codex_v3_schedule_is_disjoint_from_the_full_claude_schedule(self):
        codex = json.loads((ROOT / "benchmarks/generator-multimodel-v3-codex/protocol.json").read_text())
        offset = m.KNOWN_DRIVERS["run-generator-multimodel-v3-codex.py"]["offsets"][0]
        cells = [(t, r, a) for t in codex["tasks"] for r in range(codex["repetitions"]) for a in range(3)]
        faults = {t: len(m.engine.load_truth(t)["faults"]) for t in codex["tasks"]}
        scoring = sum(2 * (3 + faults[t] + 1) for t, _r, _a in cells)
        theirs = {"scoring": (5300 + offset + 1, 5300 + offset + scoring), "generation": (6300 + offset + 1, 6300 + offset + 2 * len(cells)),
                  "harness_and_preflight": (6700 + offset + 1, 6700 + offset + 12)}
        self.assertEqual(len(cells), 72)
        for name, (lo, hi) in theirs.items():                          # container-only ranges are checked too: the strongest reading
            for mine_name, (mlo, mhi) in self.plan.items():
                self.assertFalse(m.ranges_overlap((lo, hi), (mlo, mhi)), f"codex {name} {lo}-{hi} vs claude {mine_name} {mlo}-{mhi}")
        self.assertLess(max(hi for _lo, hi in theirs.values()), min(lo for lo, _hi in self.plan.values()))

    def test_every_known_driver_hull_is_disjoint_from_this_campaign(self):
        for script, info in m.KNOWN_DRIVERS.items():
            if script == "run-generator-multimodel-v2-claude.py":
                continue
            for rng in m.driver_ranges(info):
                for name, mine in self.plan.items():
                    self.assertFalse(m.ranges_overlap(rng, mine), f"{script} {rng} vs {name} {mine}")

    def test_the_machine_wide_probes_of_the_codex_runners_do_not_see_a_claude_driver(self):
        for name in ("run-generator-multimodel-v2-codex.py", "run-generator-multimodel-v3-codex.py", "run-generator-multimodel-v4-codex.py",
                     "generator_thin_codex_integration_v1.py"):
            pattern = re.search(r'"pgrep", "-f", r"([^"]+)"', (ROOT / "scripts/evals" / name).read_text()).group(1)
            self.assertIsNone(re.search(pattern, CLAUDE_DRIVER), name)
            if "v3" in pattern:
                self.assertIsNotNone(re.search(pattern, CODEX_V3_DRIVER), name)   # the probe is not vacuous

    def test_the_zeppelin_driver_probe_does_see_a_claude_driver(self):
        """Documented consequence: a Zeppelin campaign pauses while a Claude driver runs, so this guard refuses the other way too."""
        spec = importlib.util.spec_from_file_location("zeppelin_probe_under_test", ROOT / "scripts/evals/generator_oss_zeppelin.py")
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        ps = f"401 1 /usr/bin/python3 -B scripts/evals/run-generator-multimodel-v2-claude.py drive --allow-live\n402 1 {CODEX_V3_DRIVER}\n"
        with patch.object(module.subprocess, "run", return_value=SimpleNamespace(stdout=ps)):
            self.assertEqual(sorted(module.driver_processes()), [401, 402])


# ------------------------------------------------------------------------------------------------ lessons of the Codex v3 harness

def done(uid, text="ok", error=False):
    return {"type": "user", "message": {"content": [{"type": "tool_result", "tool_use_id": uid, "content": text, "is_error": error}]}}


class StrictFidelityAndCost(unittest.TestCase):
    pre = "mcp__playwright-test__"

    def a_stream(self, setup="ok", write="ok", click=True):
        ev = [init(A), use("Agent", {"subagent_type": "playwright-test-generator", "description": "g", "prompt": "p"}, "ag"),
              use(self.pre + "generator_setup_page", {}, "c1", parent="ag"), use(self.pre + "generator_write_test", {"code": "x"}, "c3", parent="ag")]
        if click:
            ev.append(use(self.pre + "browser_click", {}, "c2", parent="ag"))
        results = {"c1": setup, "c3": write, "c2": "ok"}
        ev += [done(uid, text, error=text != "ok") for uid, text in results.items() if uid != "c2" or click]
        return ev + [result_event()]

    def test_only_completed_generator_calls_count(self):
        f = ad.analyze_events(self.a_stream(setup="Error: Tool mcp__playwright-test__generator_setup_page is not allowed"), A)["fidelity"]
        self.assertEqual((f["generator_setup_page_calls"], f["generator_setup_page_attempted"], f["generator_write_test_calls"]), (0, 1, 1))
        self.assertEqual(f["mcp_tools_denied"], 1)
        self.assertFalse(f["treated"])
        unanswered = [e for e in self.a_stream() if not (e.get("type") == "user" and e["message"]["content"][0]["tool_use_id"] == "c3")]
        g = ad.analyze_events(unanswered, A)["fidelity"]
        self.assertEqual((g["generator_write_test_calls"], g["generator_write_test_attempted"]), (0, 1))   # a call with no result is not completed
        full = ad.analyze_events(self.a_stream(), A)
        self.assertEqual(full["mcp_tool_calls_completed"][self.pre + "browser_click"], 1)
        self.assertEqual(full["fidelity"]["generator_surface_completed"], 3)

    def test_minimal_generator_use_is_recorded_beside_the_official_tool_class(self):
        f = ad.analyze_events(self.a_stream(click=False), A)["fidelity"]
        self.assertTrue(f["minimal_generator_use"] and f["treated"])
        self.assertEqual((f["browser_tool_calls"], f["browser_mutating_calls"]), (0, 0))
        g = ad.analyze_events(self.a_stream(click=True), A)["fidelity"]
        self.assertEqual((g["minimal_generator_use"], g["browser_mutating_calls"]), (False, 1))
        rec = {"arm": A, "deliverable": True}
        self.assertEqual(m.fidelity_class(rec, f, False), "official-tool")
        self.assertEqual(m.fidelity_class(rec, {"generator_surface_completed": 0, "mcp_tools_denied": 2}, False), "manual-follow")
        self.assertEqual(m.fidelity_class(rec, {"generator_surface_completed": 0}, False), "unverified")
        self.assertEqual(m.fidelity_class({"arm": A, "deliverable": False}, {"generator_surface_completed": 0}, False), "blocked")
        self.assertEqual(m.fidelity_class(rec, f, True), "aborted")
        self.assertIsNone(m.fidelity_class({"arm": C}, f, False))

    def test_the_fidelity_table_counts_classes_and_minimal_use(self):
        base = dict(cell(TASKS[0], A, 1, 1.0), fidelity_class="official-tool", mcp_artifact_files=3, cost_covers_stream=True,
                    fidelity={"minimal_generator_use": True, "mcp_tools_denied": 0})
        other = dict(cell(TASKS[0], A, 2, 1.0), fidelity_class="unverified", mcp_artifact_files=0, cost_covers_stream=False, fidelity={"mcp_tools_denied": 1})
        table = m.fidelity_table([dict(base, aborted=False, steps={}, invoked=True, treated=True), dict(other, aborted=False, steps={}, invoked=False, treated=False)])[A]
        self.assertEqual((table["official_tool"], table["minimal_generator_use"], table["mcp_tools_denied"], table["mcp_artifact_files"]), (1, 1, 1, 3))
        self.assertEqual(table["classes"]["unverified"], 1)
        self.assertEqual(table["cells_where_model_usage_misses_stream_tokens"], 1)

    def test_cost_cross_check_flags_a_subagent_missing_from_model_usage(self):
        def msg(mid, parent, inp, out):
            return {"type": "assistant", "parent_tool_use_id": parent, "message": {"id": mid, "content": [], "usage": {"input_tokens": inp, "output_tokens": out,
                    "cache_creation_input_tokens": 0, "cache_read_input_tokens": 100}}}
        events = [msg("m1", None, 10, 50), msg("m2", "ag", 20, 400), result_event()]
        usage = {"claude-sonnet-5-5": {"inputTokens": 30, "outputTokens": 450, "cacheReadInputTokens": 200, "cacheCreationInputTokens": 0, "costUSD": 0.1}}
        ok = ad.cost_cross_check(events, ad.cost_summary(usage, 0.1))
        self.assertTrue(ok["model_usage_covers_stream"] and ok["subagent_messages"] == 1)
        parent_only = {"claude-sonnet-5-5": {"inputTokens": 10, "outputTokens": 50, "cacheReadInputTokens": 100, "cacheCreationInputTokens": 0, "costUSD": 0.1}}
        self.assertFalse(ad.cost_cross_check(events, ad.cost_summary(parent_only, 0.1))["model_usage_covers_stream"])
        self.assertEqual(ad.cost_cross_check([result_event()], ad.cost_summary(usage, 0.1)), {"checked": False, "stream_messages": 0})

    @unittest.skipUnless((SONNET / "final-transcripts").is_dir(), "stored v1 claude-sonnet-5-5 transcripts not present")
    def test_model_usage_covers_the_stream_on_every_stored_v1_cell_including_subagent_cells(self):
        checked = with_subagents = 0
        for path in sorted((SONNET / "final-transcripts").glob("*.jsonl")):
            events = ad.parse_events(path.read_text(errors="replace"))
            result = next((e for e in reversed(events) if e.get("type") == "result"), None)
            if not result:
                continue
            check = ad.cost_cross_check(events, ad.cost_summary(result.get("modelUsage"), result.get("total_cost_usd")))
            self.assertTrue(check["checked"] and check["model_usage_covers_stream"], path.name)
            checked += 1
            with_subagents += check["subagent_messages"] > 0
        self.assertGreaterEqual(checked, 30)
        self.assertGreater(with_subagents, 0)          # the claim is only meaningful where a subagent produced messages

    def test_the_full_final_message_and_long_commands_are_kept_untruncated(self):
        long_command = "echo " + "x" * 20000 + "; /bin/bash -p .claude/skills/e2e-reviewer/scripts/scan.sh tests/a.spec.ts"
        out = ad.analyze_events([init(C), use("Bash", {"command": long_command}, "b"), result_event()], C)
        self.assertEqual(out["fidelity"]["scan_sh_runs"], 1)          # counted on the full command
        self.assertEqual((out["bash_commands_over_cap"], out["bash_command_max_chars"] > 20000), (1, True))
        source = Path(ad.__file__).read_text()
        self.assertNotIn('[:3000]', source)

    def test_mcp_snapshot_files_are_tool_output_not_out_of_scope_writes(self):
        rec = m.split_mcp_artifacts({"out_of_scope_writes": [".playwright-mcp/page-1.yml", ".playwright-mcp/page-2.yml", "package.json"]})
        self.assertEqual((rec["out_of_scope_writes"], rec["mcp_artifact_files"]), (["package.json"], 2))
        self.assertEqual(m.split_mcp_artifacts({})["mcp_artifact_files"], 0)

    def test_host_pressure_parses_swap_and_never_raises(self):
        self.assertEqual(m.parse_swapusage("total = 15360.00M  used = 13629.38M  free = 1730.62M  (encrypted)"),
                         {"swap_used_mb": 13629.4, "swap_total_mb": 15360.0})
        self.assertEqual(m.parse_swapusage("total = 2.00G used = 512.00K free = 1.00G")["swap_total_mb"], 2048.0)
        self.assertEqual(m.parse_swapusage("garbage"), {"swap_used_mb": None, "swap_total_mb": None})
        with patch("subprocess.run", side_effect=OSError("no sysctl")):
            self.assertEqual(m.host_pressure()["swap_used_mb"], None)


# ------------------------------------------------------------------------------------------------ configuration gate and canary

class ConfigurationAndCanary(unittest.TestCase):
    def fake_init_agents(self, project, runner, proto):
        (project / ".claude/agents").mkdir(parents=True)
        for name in ("generator", "healer", "planner"):
            (project / f".claude/agents/playwright-test-{name}.md").write_text("---\nname: x\nmodel: inherit\n---\n")
        (project / ".mcp.json").write_text(json.dumps({"mcpServers": {"playwright-test": {"command": "npx", "args": ["playwright", "run-test-mcp-server"]}}}))
        return {"status": "ready"}

    def verify(self, **patches):
        stack = contextlib.ExitStack()
        self.addCleanup(stack.close)
        stack.enter_context(patch.object(m.v1, "init_agents", self.fake_init_agents))
        for target, value in patches.items():
            stack.enter_context(patch.object(m, target, value))
        return m.verify_config()

    def test_a_correctly_loaded_configuration_passes_for_every_arm(self):
        report = self.verify()
        self.assertEqual(report["problems"], [])
        self.assertTrue(report["ok"] and all(a["ok"] for a in report["arms"].values()))
        self.assertEqual(report["arms"][A]["facts"]["mcp_app_port"], str(m.port_plan()["preflight"][0] + ad.MCP_PORT_SHIFT))
        self.assertIn("Skill(playwright-test-generator)", report["arms"][C]["facts"]["allowed"])

    def test_the_gate_reads_content_so_a_misloaded_arm_fails_even_if_another_arm_satisfies_the_same_words(self):
        report = self.verify(install_skills=lambda project, arm: {})                       # B and C get no real skill
        self.assertFalse(report["ok"])
        self.assertTrue(any(x.startswith(f"{B}: installed project skills") for x in report["problems"]))
        self.assertTrue(any(x.startswith(f"{C}: installed project skills") for x in report["problems"]))
        self.assertFalse(any(x.startswith(f"{A}:") for x in report["problems"]))
        real = ad.command

        def wrong(arm, model, schema, budget, work, mcp=None):
            cmd = real(arm, model, schema, budget, work, mcp)
            if arm == A:                                                                 # arm A silently gains the write tool and the Skill tool
                cmd[cmd.index("--tools") + 1] += ",Write,Skill"
            return cmd
        with patch.object(ad, "command", wrong):
            report = self.verify()
        self.assertTrue(any(x.startswith(f"{A}: arm A parent has a write") for x in report["problems"]))

    def test_the_split_port_and_scoring_path_are_checked(self):
        with patch.object(m, "gen_transform", lambda project, port, mode="split-port": {"mode": mode}):    # the transform silently does nothing
            report = self.verify()
        self.assertTrue(any("split-port transform missing" in x for x in report["problems"]))
        real_stage = m.engine.stage

        def leaky(case_dir, port, work, git):
            project = real_stage(case_dir, port, work, git)
            cfg = project / "playwright.config.mjs"
            cfg.write_text(cfg.read_text().replace("reuseExistingServer: false", "reuseExistingServer: true"))
            return project
        with patch.object(m.engine, "stage", leaky):
            self.assertTrue(any("scoring" in x or "reuseExistingServer" in x for x in self.verify()["problems"]))

    def fid(self, arm, **over):
        base = {A: dict(generator_setup_page_calls=2, generator_write_test_calls=1, port_conflicts_in_playwright_test=0, port_conflict_results_any=False,
                        playwright_test_runs=1),
                C: dict(skill_tool_calls=["e2e-reviewer", "playwright-test-generator"], skill_call_errors=0, preflight_runs=1, exploration_runs=2)}[arm]
        return dict(base, **over)

    def rec(self, arm, call_id="c", **over):
        return dict({"arm": arm, "call_id": call_id, "attempts": [{}], "infrastructure_error": False, "model_usage": {"m": {}},
                     "cost_cross_check": {"model_usage_covers_stream": True}, "compliance": {"isolation": {"problems": []}}}, **over)

    def test_canary_cell_arm_a(self):
        ok = m.canary_cell(A, self.rec(A), self.fid(A))
        self.assertEqual(ok, ("pass", []))
        # a cell where the model did not use the official tools is not harness evidence: pending (a later arm A cell can show it); denied tools fail
        self.assertEqual(m.canary_cell(A, self.rec(A), self.fid(A, generator_setup_page_calls=0))[0], "pending")
        self.assertEqual(m.canary_cell(A, self.rec(A), self.fid(A, generator_write_test_calls=0))[0], "pending")
        self.assertEqual(m.canary_cell(A, self.rec(A), self.fid(A, generator_write_test_calls=0, mcp_tools_denied=2))[0], "fail")
        self.assertEqual(m.canary_cell(A, self.rec(A), self.fid(A, mcp_tools_denied=1))[0], "fail")
        verdict, why = m.canary_cell(A, self.rec(A), self.fid(A, port_conflicts_in_playwright_test=1))
        self.assertEqual(verdict, "fail")
        self.assertIn("already used", why[0])
        self.assertEqual(m.canary_cell(A, self.rec(A), self.fid(A, port_conflict_results_any=True))[0], "fail")
        self.assertEqual(m.canary_cell(A, self.rec(A, attempts=[{"harness_port_conflict": True}]), self.fid(A))[0], "fail")
        self.assertEqual(m.canary_cell(A, self.rec(A), self.fid(A, playwright_test_runs=0))[0], "pending")   # nothing to verify the split with
        self.assertEqual(m.canary_cell(A, self.rec(A, cost_cross_check={"model_usage_covers_stream": False}), self.fid(A))[0], "fail")
        self.assertEqual(m.canary_cell(A, self.rec(A, model_usage=None), self.fid(A))[0], "fail")
        self.assertEqual(m.canary_cell(A, self.rec(A, infrastructure_error=True, attempts=[{"error": "boom"}]), self.fid(A))[0], "fail")
        self.assertEqual(m.canary_cell(A, self.rec(A, compliance={"isolation": {"problems": ["x"]}}), self.fid(A))[0], "fail")
        retried = self.rec(A, attempts=[{"infrastructure_error": True, "error": "transient"}, {}])      # retried successfully by the inherited loop
        self.assertEqual(m.canary_cell(A, retried, self.fid(A)), ("pass", []))
        self.assertEqual(m.canary_cell(A, self.rec(A), None)[0], "fail")

    def test_canary_cell_arm_c_needs_the_real_skill_through_the_skill_tool(self):
        self.assertEqual(m.canary_cell(C, self.rec(C), self.fid(C)), ("pass", []))
        verdict, why = m.canary_cell(C, self.rec(C), self.fid(C, skill_tool_calls=["e2e-reviewer"]))     # a Read of SKILL.md is not the Skill tool
        self.assertEqual(verdict, "fail")
        self.assertIn("Skill tool", why[0])
        self.assertEqual(m.canary_cell(C, self.rec(C), self.fid(C, skill_call_errors=1))[0], "fail")
        # low adherence (no preflight or exploration step) is observed and reported, not a harness failure: warn, never fail
        verdict, why = m.canary_cell(C, self.rec(C), self.fid(C, preflight_runs=0))
        self.assertEqual(verdict, "warn")
        self.assertIn("preflight", why[0])
        self.assertEqual(m.canary_cell(C, self.rec(C), self.fid(C, exploration_runs=0))[0], "warn")
        self.assertEqual(m.canary_cell(C, self.rec(C), self.fid(C, preflight_runs=0, exploration_runs=0))[1].__len__(), 2)
        self.assertEqual(m.canary_cell(C, self.rec(C), self.fid(C, preflight_runs=0, skill_call_errors=1))[0], "fail")   # harness evidence wins
        self.assertEqual(m.canary_cell(C, self.rec(C), self.fid(C, preflight_runs=0, skill_tool_calls=[]))[0], "fail")

    def test_canary_evaluate_waits_for_both_arms_and_looks_at_up_to_three_arm_a_cells(self):
        with patch.object(m, "fidelity_of", side_effect=lambda rec, d: rec["_fid"]):
            def row(arm, fid, cid):
                return dict(self.rec(arm, cid), _fid=fid)
            rows = [row(A, self.fid(A, playwright_test_runs=0), "a1")]
            self.assertEqual(m.canary_evaluate(rows, "x")["verdict"], "pending")                          # arm C missing, arm A unverifiable so far
            rows += [row(C, self.fid(C), "c1")]
            self.assertEqual(m.canary_evaluate(rows, "x")["arms"]["C"]["verdict"], "pass")
            rows += [row(A, self.fid(A), "a2")]
            self.assertEqual(m.canary_evaluate(rows, "x")["verdict"], "pass")                             # the second A cell verified the split
            bad = [row(A, self.fid(A), "a1"), row(A, self.fid(A, port_conflicts_in_playwright_test=1), "a2"), row(C, self.fid(C), "c1")]
            self.assertEqual(m.canary_evaluate(bad, "x")["arms"]["A"]["verdict"], "fail")                 # any port conflict fails
            three = [row(A, self.fid(A, playwright_test_runs=0), f"a{i}") for i in range(3)] + [row(C, self.fid(C), "c1")]
            self.assertIn("unverified", m.canary_evaluate(three, "x")["arms"]["A"]["reasons"][0])
            self.assertEqual(m.canary_evaluate(three, "x")["verdict"], "fail")
            nogen = [row(A, self.fid(A, generator_write_test_calls=0), "a1"), row(C, self.fid(C), "c1")]       # one A cell without the official tools: wait, not abort
            self.assertEqual(m.canary_evaluate(nogen, "x")["arms"]["A"]["verdict"], "pending")
            self.assertEqual(m.canary_evaluate(nogen + [row(A, self.fid(A), "a2")], "x")["verdict"], "pass")
            lowc = [row(A, self.fid(A), "a1"), row(C, self.fid(C, preflight_runs=0, exploration_runs=0), "c1")]   # a legitimate low-adherence first C cell must not stop the night
            report = m.canary_evaluate(lowc, "x")
            self.assertEqual(report["verdict"], "pass")
            self.assertEqual(len(report["warnings"]), 2)
            self.assertEqual(m.canary_evaluate(rows, "x")["warnings"], [])
            only_b = [dict(self.rec(B, "b1"), _fid={})]
            self.assertEqual(m.canary_evaluate(only_b, "x")["verdict"], "pending")

    def test_canary_cmd_exit_codes_and_the_offline_verbs(self):
        with patch.object(m, "canary_rows", return_value=([], Path("/nonexistent"))), contextlib.redirect_stdout(io.StringIO()):
            self.assertEqual(m.canary_cmd(SimpleNamespace(model="x", source="final")), 5)
            for argv, code in ((["x", "guard"], 0),):
                with patch("sys.argv", argv), patch.object(m, "guard_report", return_value={"conflicts": [], "coexisting": []}):
                    self.assertEqual(m.main(), code)
            with patch("sys.argv", ["x", "guard"]), patch.object(m, "guard_report", return_value={"conflicts": [{"kind": "zeppelin"}], "coexisting": []}):
                self.assertEqual(m.main(), 4)

    def test_status_and_canary_read_this_campaigns_root_not_the_v1_root(self):
        with tempfile.TemporaryDirectory() as tmp, patch.object(m, "BASE", Path(tmp)), \
                patch.object(m, "frozen", side_effect=ValueError("not frozen: x")), patch.object(m, "current_cli", return_value="2.1.299 (Claude Code)"), \
                patch("subprocess.run", side_effect=AssertionError("no subprocess")), contextlib.redirect_stdout(io.StringIO()) as out:
            root = Path(tmp)
            self.assertNotEqual(m.v1.BASE, root)                     # v1 stays unbound: its model_dir would point at the v1 data
            (root / "claude-haiku-5-5").mkdir()
            (root / "claude-haiku-5-5/final.json").write_text(json.dumps({"completed_calls": 7, "runs": [{"arm": A, "call_id": "x"}]}))
            self.assertEqual(m.status_cmd(None), 0)
            rows, transcripts = m.canary_rows("claude-haiku-5-5", "final")
            self.assertEqual((rows, transcripts), ([{"arm": A, "call_id": "x"}], root / "claude-haiku-5-5/final-transcripts"))
            self.assertEqual(m.canary_rows("claude-sonnet-5-5", "final")[0], [])         # nothing of the v1 sonnet run leaks in
            self.assertEqual(m.canary_rows("claude-sonnet-5-5", "preflight")[0], [])
        data = json.loads(out.getvalue())
        self.assertEqual((data["frozen"], data["init_check"]["ok"], data["bundled_allowed"] is not None), (False, False, True))
        self.assertEqual(list(data["models"]), [x["id"] for x in m.protocol()["models"]])
        self.assertEqual((data["models"]["claude-haiku-5-5"]["completed_calls"], data["models"]["claude-sonnet-5-5"]["completed_calls"]), (7, 0))


if __name__ == "__main__":
    unittest.main()
