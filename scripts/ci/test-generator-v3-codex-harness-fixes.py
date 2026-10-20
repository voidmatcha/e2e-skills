#!/usr/bin/env python3
"""Offline guards for the harness fixes of generator-multimodel-v3-codex: generation-phase config, untruncated compliance, child
rollouts as the primary fidelity signal, the harness live check, cost endpoints, fidelity and as-treated views, the pooled analysis.
Synthetic data and read-only stored cells only. No network, no model, no container, no browser, no listening port. Apache-2.0."""
import argparse
import contextlib
import hashlib
import importlib.util
import io
import json
import re
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


m = load("gmm_v2_fixes_under_test", "scripts/evals/run-generator-multimodel-v3-codex.py")
ev, pool, compat = m.evidence, m.pooled, m.compat
frozen_adapter = load("frozen_official_adapter_for_fixes", "scripts/evals/generator_codex_official_adapter.py")
A, B, C = m.ARM_A, m.ARM_B, m.ARM_C
TASKS = m.protocol()["tasks"]
DATA = Path.home() / ".cache/e2e-skills-bench"
SONNET, SOL = DATA / "multimodel-v1/claude-sonnet-5-5", DATA / "multimodel-v1/gpt-6-sol"
UUIDS = [f"01a0e6d0-e77a-75f1-928b-{i:012d}" for i in range(1, 9)]


@contextlib.contextmanager
def memory_freeze(path):
    """Exercise freeze bindings using virtual I/O; never create a freeze file, even in a temporary directory."""
    path = Path(path)
    state = {"text": None}
    originals = {name: getattr(Path, name) for name in ("open", "exists", "is_file", "read_text", "read_bytes", "write_text")}

    class Buffer(io.StringIO):
        def close(self):
            if not self.closed:
                state["text"] = self.getvalue()
            super().close()

    def virtual_open(candidate, mode="r", *args, **kwargs):
        if candidate != path:
            return originals["open"](candidate, mode, *args, **kwargs)
        if mode == "x":
            if state["text"] is not None:
                raise FileExistsError(path)
            return Buffer()
        if state["text"] is None:
            raise FileNotFoundError(path)
        return io.StringIO(state["text"])

    def contents(candidate, *args, **kwargs):
        if candidate != path:
            return originals["read_text"](candidate, *args, **kwargs)
        if state["text"] is None:
            raise FileNotFoundError(path)
        return state["text"]

    def write(candidate, text, *args, **kwargs):
        if candidate != path:
            return originals["write_text"](candidate, text, *args, **kwargs)
        state["text"] = text
        return len(text)

    with contextlib.ExitStack() as stack:
        stack.enter_context(patch.object(Path, "open", virtual_open))
        for name in ("exists", "is_file"):
            stack.enter_context(patch.object(Path, name, lambda candidate, method=name: state["text"] is not None if candidate == path else originals[method](candidate)))
        stack.enter_context(patch.object(Path, "read_text", contents))
        stack.enter_context(patch.object(Path, "read_bytes", lambda candidate: contents(candidate).encode() if candidate == path else originals["read_bytes"](candidate)))
        stack.enter_context(patch.object(Path, "write_text", write))
        yield state


def jl(path, events):
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    Path(path).write_text("\n".join(json.dumps(e) for e in events) + "\n")
    return Path(path)


def usage(i, c, o, r=0, w=0):
    return {"input_tokens": i, "cached_input_tokens": c, "cache_write_input_tokens": w, "output_tokens": o, "reasoning_output_tokens": r,
            "total_tokens": i + o}


def mcp_item(tool="test_list", server="playwright-test", status="completed", n=1):
    return {"type": "event_msg", "payload": {"type": "item_completed", "item": {"type": "McpToolCall", "id": f"exec-{n}", "server": server,
                                                                                 "tool": tool, "status": status, "result": {"content": []}}}}


def spawn_item(*children):
    return {"type": "item.completed", "item": {"type": "collab_tool_call", "tool": "spawn_agent", "status": "completed",
                                                "receiver_thread_ids": list(children)}}


def function_result(tool, output, call_id="fallback"):
    return [{"type": "response_item", "payload": {"type": "function_call", "name": "mcp__playwright-test__" + tool, "call_id": call_id}},
            {"type": "response_item", "payload": {"type": "function_call_output", "call_id": call_id, "output": output}}]


def rollout(root, i, parent=None, calls=(), tokens=None, extra=(), role="default"):
    thread = UUIDS[i]
    meta = {"id": thread, "parent_thread_id": parent, "agent_role": role,
            "source": {"subagent": {"thread_spawn": {"parent_thread_id": parent, "depth": 1, "agent_role": role}}} if parent else "exec"}
    events = [{"type": "session_meta", "payload": meta}, {"type": "turn_context", "payload": {"model": "gpt-6-sol"}}]
    events += [mcp_item(tool, server, status, n) for n, (server, tool, status) in enumerate(calls)]
    events += list(extra)
    if tokens:
        events += [{"type": "event_msg", "payload": {"type": "token_count", "info": {"total_token_usage": usage(1, 0, 1), "last_token_usage": usage(1, 0, 1)}}},
                   {"type": "event_msg", "payload": {"type": "token_count", "info": {"total_token_usage": usage(*tokens), "last_token_usage": usage(1, 0, 1)}}}]
    return jl(Path(root) / "2026/10/14" / f"rollout-2026-10-14T00-00-0{i}-{thread}.jsonl", events)


def stream(thread_index=0, mcp=0, status="completed", messages=()):
    events = [{"type": "thread.started", "thread_id": UUIDS[thread_index]}, {"type": "turn.started"}]
    events += [{"type": "item.completed", "item": {"type": "mcp_tool_call", "server": "playwright-test", "tool": "generator_setup_page", "status": status}}] * mcp
    events += [{"type": "item.completed", "item": {"type": "agent_message", "text": t}} for t in messages]
    return events


def make_cell_files(tmp, events, rollouts=None, name="t"):
    """transcripts: <tmp>/final-transcripts/<name>.jsonl; sessions: <tmp>/codex-sessions/<name>/ (the adapter's layout)."""
    tdir = Path(tmp) / "final-transcripts"
    jl(tdir / f"{name}.jsonl", events)
    sdir = Path(tmp) / "codex-sessions" / name
    sdir.mkdir(parents=True, exist_ok=True)
    for build in rollouts or []:
        build(sdir)
    return tdir, sdir


def arm_rec(**over):
    base = {"arm": A, "transcript_path": "/elsewhere/t.jsonl", "spec_files": ["tests/a.spec.ts"], "out_of_scope_writes": []}
    return dict(base, **over)


# ------------------------------------------------------------------------------------------------ (a) generation-phase config

class GenerationConfig(unittest.TestCase):
    def run_arm(self, tmp, arm, call_model, rep=1):
        case = TASKS[0]
        item = {"case": case, "arm": arm, "repetition": rep, "ordinal": 1}
        artifacts = Path(tmp) / "artifacts"
        if arm == B:
            src = artifacts / f"{case}-{A}-r{rep}" / "tests"
            src.mkdir(parents=True, exist_ok=True)
            (src / "a.spec.ts").write_text("// stub\n")
        args = SimpleNamespace(model="x", timeout=1, call_budget=None)
        with patch.object(m.engine, "call_model", call_model), patch.object(m.engine, "wait_for_load", lambda record: None), \
                patch.object(m.v1, "init_agents", lambda project, runner, p: {"status": "ready"}), patch.object(tempfile, "tempdir", str(tmp)):
            return m.one_call(item, args, m.engine.Ports(9100), artifacts, {"runner": "codex"}, m.protocol())

    def capture(self, seen):
        def call_model(project, work, arm, task, model, timeout, budget):
            seen.append((arm, (project / "playwright.config.mjs").read_text()))
            return {"infrastructure_error": False, "timeout": False, "elapsed_ms": 1, "num_turns": 1, "usage": None, "structured_output": None,
                    "result_text": "", "compliance": None, "cost_usd": None}
        return call_model

    def test_generation_config_is_true_for_every_arm_identical_and_scoring_config_stays_false(self):
        with tempfile.TemporaryDirectory() as tmp:
            seen, recs = [], {}
            for arm in (A, B, C):
                recs[arm] = self.run_arm(tmp, arm, self.capture(seen))
            self.assertEqual([a for a, _ in seen], [A, B, C])
            norm = lambda text: re.sub(r"127\.0\.0\.1:\d+", "127.0.0.1:__PORT__", text)
            for _, text in seen:
                self.assertEqual(text.count("reuseExistingServer: true"), 1)
                self.assertNotIn("reuseExistingServer: false", text)
            self.assertEqual(len({norm(t) for _, t in seen}), 1)  # one generation config for A, B and C
            digests = {a: recs[a]["generation_config"] for a in recs}
            for arm, g in digests.items():
                self.assertTrue(g["reuse_existing_server"], arm)
                self.assertEqual(g["stages"], 1)
            self.assertEqual(len({tuple(g["config_sha256_port_normalized"]) for g in digests.values()}), 1)
            self.assertEqual(len({tuple(g["scoring_config_sha256_port_normalized"]) for g in digests.values()}), 1)
            # the scoring path stages the frozen config: false, and equal to the generation config except for that one token
            self.assertIs(m.engine.stage, m._REAL_STAGE)
            work = Path(tmp) / "score"
            project = m.engine.stage(m.engine.CASES / TASKS[0], 4242, work, git=False)
            scoring = (project / "playwright.config.mjs").read_text()
            self.assertEqual(scoring.count("reuseExistingServer: false"), 1)
            self.assertNotIn("reuseExistingServer: true", scoring)
            self.assertEqual(norm(scoring).replace("reuseExistingServer: false", "reuseExistingServer: true"), norm(seen[0][1]))
            self.assertEqual(m.orig.sha(norm(scoring)), digests[A]["scoring_config_sha256_port_normalized"][0])

    def test_wrapper_is_restored_after_an_exception_and_scoring_refuses_while_active(self):
        def boom(*a, **k):
            raise RuntimeError("model call failed")
        with tempfile.TemporaryDirectory() as tmp:
            with self.assertRaises(RuntimeError):
                self.run_arm(tmp, C, boom)
        self.assertIs(m.engine.stage, m._REAL_STAGE)
        self.assertFalse(m.GENERATION["active"])
        with m.generation_staging():
            self.assertIsNot(m.engine.stage, m._REAL_STAGE)
            with self.assertRaisesRegex(ValueError, "generation staging is active"):
                m.scoring_guard()
            with self.assertRaises(RuntimeError):  # not reentrant
                with m.generation_staging():
                    pass
        self.assertEqual(m.scoring_guard(), {"reuse_existing_server": False, "cases_checked": 6})

    def test_score_model_runs_the_guard_around_the_frozen_scorer(self):
        order = []
        with patch.object(m.v1, "score_model", lambda mid: order.append(("score", m.engine.stage is m._REAL_STAGE, m.GENERATION["active"]))), \
                patch.object(m, "scoring_guard", lambda *a: order.append("guard")):
            m.score_model("gpt-6-sol")
        self.assertEqual(order, ["guard", ("score", True, False), "guard"])
        with patch.object(m, "scoring_guard", side_effect=ValueError("no")), patch.object(m.v1, "score_model", side_effect=AssertionError("scored")):
            with self.assertRaises(ValueError):
                m.score_model("gpt-6-sol")

    def test_config_policy_text_and_frozen_case_configs(self):
        for case in TASKS:
            text = (m.engine.CASES / case / "playwright.config.mjs").read_text()
            self.assertEqual(text.count(m.SCORING_REUSE), 1, case)
            generation = m.generation_config_text(text)
            self.assertEqual(generation.replace(m.GENERATION_REUSE, m.SCORING_REUSE), text)
        for bad in ("export default {}", "reuseExistingServer: false, reuseExistingServer: false", "reuseExistingServer: false, // reuseExistingServer: true"):
            with self.assertRaises(ValueError):
                m.generation_config_text(bad)

    def test_scoring_guard_refuses_a_tampered_case_config(self):
        with tempfile.TemporaryDirectory() as tmp:
            cases = Path(tmp) / "cases"
            for case in TASKS:
                (cases / case).mkdir(parents=True)
                (cases / case / "playwright.config.mjs").write_text((m.engine.CASES / case / "playwright.config.mjs").read_text())
            with patch.object(m.engine, "CASES", cases):
                m.scoring_guard()
                f = cases / TASKS[2] / "playwright.config.mjs"
                f.write_text(f.read_text().replace("reuseExistingServer: false", "reuseExistingServer: true"))
                with self.assertRaisesRegex(ValueError, TASKS[2]):
                    m.scoring_guard()

    def test_generation_uniformity_detects_a_different_config_for_one_arm(self):
        g = lambda sha: {"stages": 1, "reuse_existing_server": True, "config_sha256_port_normalized": [sha], "scoring_config_sha256_port_normalized": ["s"]}
        cells = [{"case": "c1", "generation_config": g("x")} for _ in range(3)]
        self.assertEqual(m.generation_uniformity(cells), {"c1": {"generation": ["x"], "scoring_base": ["s"]}})
        with self.assertRaisesRegex(ValueError, "not identical"):
            m.generation_uniformity(cells + [{"case": "c1", "generation_config": g("y")}])
        off = dict(g("x"), reuse_existing_server=False)
        with self.assertRaises(ValueError):
            m.generation_uniformity([{"case": "c1", "generation_config": off}])
        self.assertEqual(m.generation_uniformity([{"case": "c1", "generation_config": None}]), {})


# ------------------------------------------------------------------------------------------------ (b) compliance without truncation

class Compliance(unittest.TestCase):
    LONG = "cd /work/project && " + "echo " + "x" * 450 + " && /bin/bash -p /work/skill/e2e-reviewer/scripts/scan.sh tests"

    def test_a_long_command_is_not_cut_and_the_engine_cut_is_reproduced(self):
        codex = [{"type": "item.completed", "item": {"type": "command_execution", "command": self.LONG}}]
        claude = [{"type": "assistant", "message": {"content": [{"type": "tool_use", "name": "Bash", "input": {"command": self.LONG}}]}}]
        self.assertGreater(len(self.LONG), 400)
        self.assertEqual(m.engine.compliance_from_events(claude, Path("/p"))["scanner_runs"], 0)  # the engine keeps [:400]
        for events in (codex, claude):
            comp = ev.compliance_from_events(events)
            self.assertEqual((comp["scanner_runs"], comp["scanner_exec_runs"], comp["commands_over_400_chars"]), (1, 1, 1))
            self.assertEqual(comp["max_command_chars"], len(self.LONG))
            self.assertEqual(comp["bash_commands"][0], self.LONG)

    def test_scanner_steps_use_the_executed_count_and_keep_the_mention_count(self):
        def comp(*commands):
            return ev.compliance_from_events([{"type": "item.completed", "item": {"type": "command_execution", "command": c}} for c in commands])
        cat = comp("cat skills/e2e-reviewer/scripts/scan.sh", "grep -n P0 skills/e2e-reviewer/scripts/scan.sh")
        self.assertEqual((cat["scanner_runs"], cat["scanner_exec_runs"]), (2, 0))
        for run in ("/bin/bash -p skills/e2e-reviewer/scripts/scan.sh tests", "cd x && bash ./scan.sh t", "./scan.sh t", "cd x; /abs/path/scan.sh t", "FOO=1 ./scan.sh t"):
            self.assertEqual(comp(run)["scanner_exec_runs"], 1, run)
        self.assertEqual(ev.c_treatment(cat)["steps"]["scanner"], False)
        self.assertTrue(ev.c_treatment(cat)["scanner_mentioned"])
        self.assertFalse(ev.b_treatment(dict(cat, reviewer_skill_read=True))["treated"])
        ran = comp("bash skills/e2e-reviewer/scripts/scan.sh t", "cat e2e-reviewer/SKILL.md")
        self.assertTrue(ev.b_treatment(ran)["treated"])
        self.assertIn("parent stream only", ev.b_treatment(ran)["step_source"])

    def test_the_campaign_guard_also_sees_a_running_harness_check(self):
        source = (ROOT / "scripts/evals/run-generator-multimodel-v3-codex.py").read_text()
        pattern = re.search(r'"pgrep", "-f", r"([^"]+)"', source).group(1)
        for sub_command in ("drive", "run", "preflight", "harness-check", "smoke"):
            self.assertTrue(re.search(pattern, f"python3 scripts/evals/run-generator-multimodel-v3-codex.py {sub_command} --allow-live"), sub_command)
        self.assertFalse(re.search(pattern, "python3 scripts/evals/run-generator-multimodel-v3-codex.py summary"))

    def test_mention_versus_execution_and_other_indicators(self):
        cmds = ["cat /work/skill/e2e-reviewer/scripts/scan.sh", "/bin/bash -p /work/skill/e2e-reviewer/scripts/scan.sh tests",
                "node_modules/.bin/playwright test tests/a.spec.ts --repeat-each=3", "bash /work/skill/playwright-test-generator/scripts/run-preflight-target.sh x",
                "playwright-cli open http://127.0.0.1:1", "git status --porcelain", "cat /work/skill/playwright-test-generator/code-rules.md",
                "cat /work/skill/playwright-test-generator/SKILL.md /work/skill/e2e-reviewer/SKILL.md"]
        events = [{"type": "item.completed", "item": {"type": "command_execution", "command": c}} for c in cmds]
        events += [{"type": "item.completed", "item": {"type": "collab_tool_call", "tool": "spawn_agent", "status": "completed"}}]
        comp = ev.compliance_from_events(events)
        self.assertEqual((comp["scanner_runs"], comp["scanner_exec_runs"]), (2, 1))
        self.assertEqual((comp["playwright_test_runs"], comp["repeat_each_runs"], comp["preflight_runs"], comp["exploration_commands"], comp["git_status_calls"]),
                         (1, 1, 1, 1, 1))
        self.assertTrue(comp["skill_md_read"] and comp["reviewer_skill_read"])
        self.assertEqual(comp["generator_reference_files_read"], ["code-rules.md"])
        self.assertEqual(comp["agent_spawns_in_stream"], 1)

    def test_claude_read_and_agent_tool_uses_and_c_treatment(self):
        blocks = [{"type": "tool_use", "name": "Read", "input": {"file_path": "/w/skill/playwright-test-generator/SKILL.md"}},
                  {"type": "tool_use", "name": "Read", "input": {"file_path": "/w/skill/playwright-test-generator/scenario-design.md"}},
                  {"type": "tool_use", "name": "Read", "input": {"file_path": "/w/skill/e2e-reviewer/SKILL.md"}},
                  {"type": "tool_use", "name": "Agent", "input": {}}, {"type": "tool_use", "name": "Skill", "input": {"skill": "playwright-test-generator"}},
                  {"type": "tool_use", "name": "Bash", "input": {"command": "/bin/bash -p /w/skill/e2e-reviewer/scripts/scan.sh tests"}}]
        comp = ev.compliance_from_events([{"type": "assistant", "message": {"content": blocks}}])
        self.assertEqual((comp["agent_spawns_in_stream"], comp["skill_tool_calls"], comp["generator_reference_files_read"]), (1, ["playwright-test-generator"], ["scenario-design.md"]))
        tr = ev.c_treatment(comp, "complete")
        self.assertEqual(tr["steps"], {"skill_md_read": True, "reference_read": True, "preflight": False, "exploration": False, "scanner": True,
                                       "independent_review": True, "self_reported_complete": True})
        self.assertTrue(tr["treated_core"])
        self.assertEqual(tr["steps_done"], 5)
        minimal = ev.c_treatment(ev.compliance_from_events([{"type": "assistant", "message": {"content": blocks[:1]}}]), None)
        self.assertFalse(minimal["treated_core"])
        self.assertEqual(ev.c_treatment(None)["available"], False)
        self.assertTrue(ev.b_treatment(comp)["treated"])
        self.assertFalse(ev.b_treatment(ev.compliance_from_events([]))["treated"])

    @unittest.skipUnless((SONNET / "final.json").is_file(), "stored sonnet cells not present")
    def test_stored_sonnet_arm_c_reproduces_the_audit(self):
        report = m.read(SONNET / "final.json")
        rows = [r for r in report["runs"] if r["arm"] == C]
        self.assertEqual(len(rows), 12)
        comps = [ev.compliance_from_events(m.transcript_events(r, SONNET / "final-transcripts")) for r in rows]
        steps = [ev.c_treatment(c, (r.get("structured_output") or {}).get("status"))["steps"] for c, r in zip(comps, rows)]
        count = lambda key: sum(bool(s[key]) for s in steps)
        self.assertEqual((count("skill_md_read"), count("reference_read"), count("preflight"), count("exploration"), count("scanner"),
                          count("independent_review"), count("self_reported_complete")), (12, 0, 0, 0, 6, 1, 0))
        self.assertEqual(sum((r.get("compliance") or {}).get("scanner_runs", 0) > 0 for r in rows), 2)  # the engine's truncated count
        self.assertGreater(sum(c["commands_over_400_chars"] > 0 for c in comps), 0)


# ------------------------------------------------------------------------------------------------ (c) rollouts

class Rollouts(unittest.TestCase):
    def test_parse_events_usage_and_identity(self):
        with tempfile.TemporaryDirectory() as tmp:
            f = rollout(tmp, 1, parent=UUIDS[0], calls=[("playwright-test", "test_list", "completed"), ("playwright-test", "generator_write_test", "failed"),
                                                        ("other", "x", "completed")], tokens=(5000, 4000, 300, 40))
            r = ev.parse_rollout(f)
        self.assertEqual((r["thread_id"], r["parent_thread_id"], r["agent_role"], r["depth"], r["models"]), (UUIDS[1], UUIDS[0], "default", 1, ["gpt-6-sol"]))
        self.assertEqual(r["mcp_source"], "event")
        self.assertEqual([(c["tool"], c["status"]) for c in r["mcp_calls"]], [("test_list", "completed"), ("generator_write_test", "failed"), ("x", "completed")])
        self.assertEqual((r["usage"]["input_tokens"], r["usage"]["cached_input_tokens"], r["usage"]["output_tokens"], r["usage"]["total_tokens"]), (5000, 4000, 300, 5300))
        self.assertEqual(r["usage_source"], "token_count.total_token_usage")

    def test_older_and_fallback_schemas_and_malformed_lines(self):
        with tempfile.TemporaryDirectory() as tmp:
            old = jl(Path(tmp) / f"rollout-a-{UUIDS[2]}.jsonl", [
                {"type": "event_msg", "payload": {"type": "mcp_tool_call_end", "call_id": "c1", "invocation": {"server": "playwright-test", "tool": "test_list"},
                                                   "result": {"Ok": {"isError": False}}}},
                {"type": "event_msg", "payload": {"type": "mcp_tool_call_end", "call_id": "c2", "invocation": {"server": "playwright-test", "tool": "test_run"},
                                                   "result": {"Err": "boom"}}},
                {"type": "token_usage_record", "payload": {"thread_token_usage": usage(10, 2, 3)}}])
            old.write_text(old.read_text() + "not json\n")
            fallback = jl(Path(tmp) / f"rollout-b-{UUIDS[3]}.jsonl", [
                {"type": "response_item", "payload": {"type": "function_call", "name": "mcp__playwright-test__generator_setup_page", "call_id": "k1"}},
                {"type": "response_item", "payload": {"type": "function_call", "namespace": "mcp__playwright-test__", "name": "generator_write_test", "call_id": "k2"}},
                {"type": "response_item", "payload": {"type": "function_call_output", "call_id": "k1", "output": '{"content": [], "isError": false}'}}])
            a, b = ev.parse_rollout(old), ev.parse_rollout(fallback)
        self.assertEqual([c["status"] for c in a["mcp_calls"]], ["completed", "failed"])
        self.assertEqual((a["malformed_lines"], a["usage"]["total_tokens"], a["usage_source"], a["thread_id"]), (1, 13, "token_usage_record.thread_token_usage", UUIDS[2]))
        self.assertEqual(b["mcp_source"], "function_call")
        self.assertEqual([(c["tool"], c["status"]) for c in b["mcp_calls"]], [("generator_setup_page", "completed"), ("generator_write_test", "requested")])
        self.assertTrue(ev.is_mcp_server("playwright_test") and ev.is_mcp_server("Playwright-Test") and not ev.is_mcp_server("other"))

    def test_tree_root_child_grandchild_unlinked_and_usage(self):
        with tempfile.TemporaryDirectory() as tmp:
            rollout(tmp, 0, tokens=(1000, 800, 100))
            rollout(tmp, 1, parent=UUIDS[0], calls=[("playwright-test", "generator_setup_page", "completed"), ("playwright-test", "generator_write_test", "completed")],
                    tokens=(5000, 4000, 300))
            rollout(tmp, 2, parent=UUIDS[1], calls=[("playwright-test", "test_list", "completed")], tokens=(200, 0, 20))  # grandchild
            rollout(tmp, 3, parent=UUIDS[7], tokens=(7, 0, 1))  # names a parent that is not in the cell: still a child for cost
            sess = ev.summarize_sessions(ev.load_sessions(tmp), UUIDS[0])
        self.assertEqual((sess["rollouts_found"], sess["root_found"], sess["children_linked"], sess["children_unlinked"], sess["children_total"]), (4, True, 2, 1, 3))
        self.assertEqual((sess["playwright_test_completed"], sess["child_playwright_test_completed"], sess["generator_tool_completed"],
                          sess["generator_write_test_completed"]), (3, 3, 2, 1))
        self.assertEqual(sess["child_usage"]["input_tokens"], 5000 + 200 + 7)
        self.assertEqual(sess["root_rollout_usage"]["input_tokens"], 1000)
        self.assertEqual(sess["mcp_calls"]["playwright-test.generator_setup_page"], {"completed": 1, "other": 0})

    def test_root_found_without_a_thread_id_and_extra_roots_are_flagged_not_counted(self):
        with tempfile.TemporaryDirectory() as tmp:
            rollout(tmp, 0, tokens=(10, 0, 1))
            rollout(tmp, 1, parent=UUIDS[0], tokens=(20, 0, 2))
            self.assertTrue(ev.summarize_sessions(ev.load_sessions(tmp), None)["root_found"])
            rollout(tmp, 4, tokens=(99, 0, 9))  # a second parentless rollout
            sess = ev.summarize_sessions(ev.load_sessions(tmp), UUIDS[0])
            self.assertEqual((sess["root_found"], sess["extra_root_rollouts"], sess["children_total"], sess["child_usage"]["input_tokens"]), (True, 1, 1, 20))
            self.assertFalse(ev.summarize_sessions(ev.load_sessions(tmp), None)["root_found"])  # two parentless candidates: ambiguous

    def test_persist_sessions_sanitises_skips_symlinks_and_oversize(self):
        with tempfile.TemporaryDirectory() as tmp:
            src, dest = Path(tmp) / "src", Path(tmp) / "out/cell"
            f = rollout(src, 0, tokens=(1, 0, 1), extra=[{"type": "event_msg", "payload": {"type": "x", "text": "path /private/secret/dir here"}}])
            (src / "link").symlink_to(f)
            big = src / "big.jsonl"
            big.write_text("x" * 20000)
            census = ev.persist_sessions(src, dest, lambda text: text.replace("/private/secret/dir", "<work>"), max_file_bytes=10000)
            copied = list(dest.rglob("rollout-*.jsonl"))
            self.assertEqual((census["files"], len(copied)), (1, 1))
            self.assertIn("<work>", copied[0].read_text())
            self.assertNotIn("/private/secret/dir", copied[0].read_text())
            self.assertEqual(sorted(census["skipped"]), ["big.jsonl (oversize)", "link (symlink)"])
            self.assertEqual(copied[0].stat().st_mode & 0o777, 0o600)
            self.assertEqual(ev.persist_sessions(Path(tmp) / "absent", dest)["files"], 0)

    def test_adapter_mount_script_and_layout(self):
        eng = SimpleNamespace(CODEX_DOCKER="/usr/bin/docker", CODEX_DOCKER_CONTEXT="colima", CODEX_CONTAINER_IMAGE=m.protocol()["container_image"])
        plain = compat.command(eng, "/w", "/p", "c1", "gpt-6-sol", A)
        withs = compat.command(eng, "/w", "/p", "c1", "gpt-6-sol", A, "/host/sessions")
        extra = [x for x in withs if x not in plain]
        self.assertIn("type=bind,src=/host/sessions,dst=/sessions-out", extra)
        self.assertIn(compat.START_SESSIONS, extra)
        self.assertEqual(len(withs) - len(plain), 2)  # one --mount pair; the script replaces the script (same length)
        self.assertEqual(withs[withs.index(compat.START_SESSIONS) + 1:], plain[plain.index(compat.START) + 1:])
        self.assertIn("ln -s /sessions-out /codex-home/.codex/sessions", compat.START_SESSIONS)
        self.assertEqual(compat.START_SESSIONS.replace("ln -s /sessions-out /codex-home/.codex/sessions\n", ""), compat.START)
        self.assertEqual(frozen_adapter.START, compat.START)  # without the sessions argument the script is the frozen one
        harness = compat.command(eng, "/w", "/p", "c1", "gpt-6-sol", compat.HARNESS_CHECK_ARM)
        self.assertEqual(sum("mcp_servers.playwright-test" in x for x in harness), 6)
        configs = [harness[i + 1] for i, token in enumerate(harness[:-1]) if token == "-c"]
        allow = next(c for c in configs if c.startswith("mcp_servers.playwright-test.enabled_tools="))
        self.assertEqual(json.loads(allow.split("=", 1)[1]), list(compat.GENERATOR_TOOLS))
        self.assertEqual(harness[harness.index("--sandbox") + 1], "danger-full-access")
        self.assertEqual(sum("mcp_servers" in x for x in compat.command(eng, "/w", "/p", "c1", "gpt-6-sol", C)), 0)
        self.assertIn(compat.HARNESS_CHECK_ARM, m.arm_lines())
        with tempfile.TemporaryDirectory() as tmp:
            engine = SimpleNamespace(CODEX_TRANSCRIPTS=Path(tmp) / "final-transcripts", sanitize=lambda text, paths: text.replace("/host", "<h>"))
            src = Path(tmp) / "s"
            rollout(src, 0, tokens=(1, 0, 1))
            census = compat.persist_cell_sessions(engine, src, Path("/x/abc123.jsonl"), ("/host",))
            self.assertEqual((census["files"], census["dir"]), (1, "abc123"))
            rec = {"transcript_path": "/anywhere/abc123.jsonl"}
            self.assertEqual(ev.sessions_dir_for(rec, Path(tmp) / "final-transcripts"), Path(tmp) / "codex-sessions" / "abc123")
            self.assertEqual(len(ev.load_sessions(ev.sessions_dir_for(rec, Path(tmp) / "final-transcripts"))), 1)


class FidelityFromRollouts(unittest.TestCase):
    def classify(self, events, rollouts, **rec):
        with tempfile.TemporaryDirectory() as tmp:
            tdir, _ = make_cell_files(tmp, events, rollouts)
            return m.classify_fidelity(arm_rec(**rec), tdir)

    def child_call(self, tool="generator_setup_page", status="completed"):
        return [lambda d: rollout(d, 0, tokens=(10, 0, 1)), lambda d: rollout(d, 1, parent=UUIDS[0], calls=[("playwright-test", tool, status)], tokens=(50, 0, 5))]

    def test_a_child_agent_call_is_the_primary_signal_and_invisible_to_the_parent_stream(self):
        out = self.classify(stream(), self.child_call())
        self.assertEqual((out["class"], out["evidence"]["strength"], out["evidence"]["primary_signal"]), ("official-tool", "hard", "rollout"))
        self.assertEqual(out["evidence"]["mcp_tool_events"], {})  # nothing in the parent stream
        self.assertTrue(m.admits(out))
        self.assertEqual(self.classify(stream(), self.child_call(), spec_files=[])["class"], "official-tool")  # not delivered, still positive

    def test_failed_or_other_server_calls_do_not_count(self):
        self.assertEqual(self.classify(stream(), self.child_call(status="failed"))["class"], "unverified")
        other = [lambda d: rollout(d, 0, tokens=(1, 0, 1)), lambda d: rollout(d, 1, parent=UUIDS[0], calls=[("other", "x", "completed")], tokens=(1, 0, 1))]
        self.assertEqual(self.classify(stream(), other)["class"], "unverified")

    def test_observed_absence_beats_headers_messages_and_artifacts(self):
        absent = [lambda d: rollout(d, 0, tokens=(10, 0, 1)), lambda d: rollout(d, 1, parent=UUIDS[0], tokens=(5, 0, 1))]
        said = ["The agent confirmed the approved Playwright generator tools are working."]
        out = self.classify(stream(messages=said), absent, out_of_scope_writes=[".playwright-mcp/p.yml"])
        self.assertEqual(out["class"], "unverified")
        self.assertEqual((out["evidence"]["primary_signal"], out["evidence"]["signal_conflict"], out["evidence"]["tools_affirmed_messages"]), ("rollout-absence", True, 1))
        self.assertFalse(m.admits(out))
        denied = self.classify(stream(messages=["The generator tools were not exposed in this session."]), absent)
        self.assertEqual((denied["class"], denied["evidence"]["signal_conflict"]), ("manual-follow", False))
        self.assertEqual(self.classify(stream(), absent, spec_files=[])["class"], "blocked")

    def test_without_rollouts_the_secondary_evidence_applies_as_before(self):
        said = self.classify(stream(messages=["The agent confirmed the approved Playwright generator tools are working."]), None)
        self.assertEqual((said["class"], said["evidence"]["strength"], said["evidence"]["primary_signal"]), ("official-tool", "message", "message"))
        self.assertFalse(m.admits(said))
        files = self.classify(stream(), None, out_of_scope_writes=[".playwright-mcp/p.yml"])
        self.assertEqual((files["class"], files["evidence"]["strength"], files["evidence"]["primary_signal"]), ("official-tool", "hard", "artifact"))
        self.assertTrue(m.admits(files))

    def test_parent_stream_call_is_observed_and_rollout_without_root_is_not_complete(self):
        out = self.classify(stream(mcp=2), [lambda d: rollout(d, 0, tokens=(1, 0, 1))])
        self.assertEqual((out["class"], out["evidence"]["primary_signal"]), ("official-tool", "parent-stream"))
        two_roots = [lambda d: rollout(d, 0), lambda d: rollout(d, 5)]  # ambiguous root: absence is not an observation
        out = self.classify(stream(thread_index=7, messages=["The agent confirmed the approved Playwright generator tools are working."]), two_roots)
        self.assertEqual((out["class"], out["evidence"]["primary_signal_complete"]), ("official-tool", False))

    def test_rollout_summary_enters_the_cell_extras_and_tokens(self):
        with tempfile.TemporaryDirectory() as tmp:
            tdir, _ = make_cell_files(tmp, stream(), self.child_call())
            rec = arm_rec(usage={"input_tokens": 100, "cached_input_tokens": 60, "output_tokens": 10}, usage_all_turns=[{"input_tokens": 100, "cached_input_tokens": 60, "output_tokens": 10}])
            out = m.cell_extras(rec, tdir, tmp)
        self.assertEqual(out["rollouts"]["children_total"], 1)
        self.assertEqual((out["tokens"]["uncached_input"], out["tokens"]["child_uncached_input"], out["tokens"]["child_output"]), (10, 50, 5))  # parent from its own rollout
        self.assertEqual(out["tokens"]["parent_source"], "rollout")
        self.assertNotIn("bash_commands", out["compliance_raw"])
        self.assertEqual(out["treatment"], {"mcp_class": "official-tool"})


    # Review findings F1 and F2: the primary signal is a generator-tool call, and a missing rollout is not an absence.

    def test_only_generator_surface_tools_are_evidence_negative_controls(self):
        for tool in ("test_run", "test_list", "test_debug", "planner_setup_page", "planner_save_plan"):
            out = self.classify(stream(), self.child_call(tool=tool))
            self.assertEqual(out["class"], "unverified", tool)
            self.assertFalse(m.admits(out), tool)
            self.assertEqual((out["evidence"]["primary_signal"], out["evidence"]["other_playwright_test_calls"], out["evidence"]["generator_surface_calls"]),
                             ("rollout-absence", 1, 0), tool)
        for tool in ("generator_setup_page", "generator_write_test", "generator_read_log", "browser_snapshot", "browser_click"):
            out = self.classify(stream(), self.child_call(tool=tool))
            self.assertEqual((out["class"], out["evidence"]["strength"], m.admits(out)), ("official-tool", "hard", True), tool)
        wrong_stream = [{"type": "thread.started", "thread_id": UUIDS[0]},
                        {"type": "item.completed", "item": {"type": "mcp_tool_call", "server": "playwright-test", "tool": "test_run", "status": "completed"}}]
        out = self.classify(wrong_stream, [lambda d: rollout(d, 0, tokens=(1, 0, 1))])
        self.assertEqual((out["class"], out["evidence"]["other_playwright_test_calls"]), ("unverified", 1))
        # a test_* call does not turn a missing record into a positive either, and an affirming message still cannot override it
        out = self.classify(wrong_stream, None)
        self.assertEqual(out["class"], "unverified")
        mixed = [lambda d: rollout(d, 0, tokens=(1, 0, 1)),
                 lambda d: rollout(d, 1, parent=UUIDS[0], calls=[("playwright-test", "test_run", "completed"), ("playwright-test", "generator_setup_page", "completed")], tokens=(1, 0, 1))]
        self.assertEqual(self.classify(stream(), mixed)["evidence"]["generator_surface_calls"], 1)

    def test_a_lost_child_rollout_is_not_an_observed_absence(self):
        """The parent stream shows a completed spawn, but only the root rollout was persisted: no signal, no absence."""
        spawn = spawn_item(UUIDS[1])
        events = stream(messages=["The agent confirmed the approved Playwright generator tools are working."]) + [spawn]
        root_only = [lambda d: rollout(d, 0, tokens=(1, 0, 1))]
        out = self.classify(events, root_only)
        ev_ = out["evidence"]
        self.assertFalse(ev_["primary_signal_complete"])
        self.assertTrue(any("spawned thread rollout missing" in g for g in ev_["observation_gaps"]))
        self.assertEqual((out["class"], ev_["strength"], ev_["primary_signal"], ev_["signal_conflict"]), ("official-tool", "message", "message", False))
        self.assertFalse(m.admits(out))  # a message never admits
        self.assertTrue(ev_["observation_incomplete"])
        bare = self.classify(stream() + [spawn], root_only)
        self.assertEqual(bare["class"], "unverified")
        self.assertTrue(bare["evidence"]["observation_incomplete"])
        with_child = self.classify(stream() + [spawn], self.child_call(tool="test_list"))  # the spawn has its rollout: a complete absence
        self.assertEqual((with_child["evidence"]["primary_signal_complete"], with_child["evidence"]["observation_incomplete"]), (True, False))
        # a skipped file or a copy error in the persistence census breaks completeness too
        for census in ({"files": 1, "bytes": 1, "skipped": ["rollout-x.jsonl (symlink)"], "dir": "t"}, {"files": 0, "bytes": 0, "skipped": [], "dir": None, "error": "disk full"}):
            out = self.classify(stream(), [lambda d: rollout(d, 0, tokens=(1, 0, 1))], compliance={"sessions": census})
            self.assertFalse(out["evidence"]["primary_signal_complete"])
            self.assertTrue(out["evidence"]["observation_incomplete"])
        clean = self.classify(stream(), [lambda d: rollout(d, 0, tokens=(1, 0, 1))], compliance={"sessions": {"files": 1, "bytes": 1, "skipped": [], "dir": "t"}})
        self.assertTrue(clean["evidence"]["primary_signal_complete"])
        # a v2 record (it carries a census) with no rollouts at all is incomplete; a stored v1 record (no census) keeps the old path
        v2 = self.classify(stream(), None, compliance={"sessions": {"files": 0, "bytes": 0, "skipped": [], "dir": "t"}})
        self.assertTrue(v2["evidence"]["observation_incomplete"])
        self.assertFalse(self.classify(stream(), None)["evidence"]["observation_incomplete"])

    def test_the_entry_loop_does_not_count_an_incomplete_observation_as_an_attempt(self):
        spawn = spawn_item(UUIDS[1])
        rule = {"max_attempts": 2, "max_aborted_reruns": 1}
        with tempfile.TemporaryDirectory() as tmp, patch.object(m, "BASE", Path(tmp)):
            def call(n, tdir):
                jl(tdir / "t.jsonl", stream() + [spawn])
                rollout(tdir.parent / "codex-sessions" / "t", 0, tokens=(1, 0, 1))  # the child rollout was lost
                return arm_rec(transcript_path=str(tdir / "t.jsonl"))
            decision, state = m.run_entry("gpt-6-sol", rule, Path(tmp) / "root", call)
        self.assertIsNone(decision)  # undecided, never excluded
        self.assertEqual((len(state["attempts"]), state["aborted_calls"]), (0, 2))
        self.assertIn("observation incomplete", state["last_abort"]["error"][0])

    def test_failed_and_ambiguous_fallback_results_never_admit(self):
        for output in ({"isError": True, "content": []}, '{"isError": true}', {"Err": "failed"},
                       {"Ok": {"isError": True}}, {"error": "failed"}, "Error: tool unavailable", "ok", None, {}):
            builds = [lambda d: rollout(d, 0, tokens=(1, 0, 1)),
                      lambda d: rollout(d, 1, parent=UUIDS[0], tokens=(2, 0, 1),
                                        extra=function_result("generator_setup_page", output))]
            out = self.classify(stream() + [spawn_item(UUIDS[1])], builds)
            self.assertEqual(out["class"], "unverified", output)
            self.assertFalse(m.admits(out), output)
        good = [lambda d: rollout(d, 0, tokens=(1, 0, 1)),
                lambda d: rollout(d, 1, parent=UUIDS[0], tokens=(2, 0, 1),
                                  extra=function_result("generator_setup_page", '{"content": [], "isError": false}'))]
        self.assertTrue(m.admits(self.classify(stream() + [spawn_item(UUIDS[1])], good)))

    def test_explicit_result_errors_override_completed_parent_and_rollout_events(self):
        events = stream(mcp=1)
        events[-1]["item"]["result"] = {"isError": True}
        self.assertFalse(m.admits(self.classify(events, [lambda d: rollout(d, 0, tokens=(1, 0, 1))])))
        failed = mcp_item("generator_setup_page")
        failed["payload"]["item"]["result"] = '{"isError": true}'
        self.assertFalse(m.admits(self.classify(stream(), [lambda d: rollout(d, 0, tokens=(1, 0, 1), extra=[failed])])))

    def test_missing_sessions_with_affirmation_leave_entry_undecided(self):
        for census in (None, {"files": 0, "skipped": []}):
            with tempfile.TemporaryDirectory() as tmp, patch.object(m, "BASE", Path(tmp)):
                def call(n, tdir):
                    jl(tdir / "t.jsonl", stream(messages=["Browser setup succeeded."]))
                    return arm_rec(transcript_path=str(tdir / "t.jsonl"), compliance={"sessions": census} if census else {})
                decision, state = m.run_entry("gpt-6-sol", {"max_attempts": 2, "max_aborted_reruns": 1}, Path(tmp) / "root", call)
                self.assertIsNone(decision)
                self.assertEqual((len(state["attempts"]), state["aborted_calls"]), (0, 2))
                self.assertFalse(m.entry_path("gpt-6-sol").exists())

    def test_hard_evidence_can_admit_despite_missing_sessions(self):
        with tempfile.TemporaryDirectory() as tmp, patch.object(m, "BASE", Path(tmp)):
            def call(n, tdir):
                jl(tdir / "t.jsonl", stream(mcp=1))
                return arm_rec(transcript_path=str(tdir / "t.jsonl"), compliance={"sessions": {"files": 0, "skipped": []}})
            decision, state = m.run_entry("gpt-6-sol", {"max_attempts": 2, "max_aborted_reruns": 1}, Path(tmp) / "root", call)
        self.assertEqual((decision, len(state["attempts"]), state["aborted_calls"]), ("admitted", 1, 0))


# ------------------------------------------------------------------------------------------------ live check

class HarnessCheck(unittest.TestCase):
    def test_failed_or_ambiguous_fallback_test_list_never_passes(self):
        for output in ('{"isError": true, "content": []}', {"Err": "failed"}, {"Ok": {"isError": True}}, "ok", None, {}):
            builds = [lambda d: rollout(d, 0, tokens=(1, 0, 1)),
                      lambda d: rollout(d, 1, parent=UUIDS[0], tokens=(2, 0, 1), extra=function_result("test_list", output))]
            result = self.evaluate(stream() + [spawn_item(UUIDS[1])], builds)
            self.assertNotEqual(result["status"], "pass", output)
            self.assertFalse(result["criteria"]["child_called_generator_setup_page"], output)

    def evaluate(self, events, rollouts, **rec):
        with tempfile.TemporaryDirectory() as tmp:
            tdir, _ = make_cell_files(tmp, events, rollouts)
            return m.evaluate_harness_check(arm_rec(**rec), tdir)

    good = [lambda d: rollout(d, 0, tokens=(300, 200, 20)),
            lambda d: rollout(d, 1, parent=UUIDS[0], calls=[("playwright-test", "generator_setup_page", "completed"), ("playwright-test", "browser_navigate", "completed")], tokens=(120, 0, 12), extra=[{"type":"event_msg","payload":{"type":"exec_command_end","command":["ls","specs/plan.md"],"exit_code":0}}])]

    def test_pass_requires_every_criterion(self):
        out = self.evaluate(stream(), self.good, usage={"input_tokens": 300, "cached_input_tokens": 200, "output_tokens": 20},
                            usage_all_turns=[{"input_tokens": 300, "cached_input_tokens": 200, "output_tokens": 20}])
        self.assertEqual(out["status"], "pass")
        self.assertTrue(all(out["criteria"][k] for k in m.HARNESS_REQUIRED))
        self.assertTrue(out["info"]["parent_stream_blind_to_child"])
        self.assertTrue(out["info"]["parent_usage_matches_root_rollout"])
        self.assertEqual((out["info"]["child_generator_setup_page_calls"], out["info"]["child_total_tokens"]), (1, 132))

    def test_inconclusive_when_no_child_or_no_call_and_fail_when_persistence_or_usage_is_broken(self):
        no_child = self.evaluate(stream(), [lambda d: rollout(d, 0, tokens=(1, 0, 1))])
        self.assertEqual(no_child["status"], "inconclusive")
        no_call = self.evaluate(stream(), [lambda d: rollout(d, 0, tokens=(1, 0, 1)), lambda d: rollout(d, 1, parent=UUIDS[0], tokens=(2, 0, 1))])
        self.assertEqual(no_call["status"], "inconclusive")
        wrong_tool = self.evaluate(stream(), [lambda d: rollout(d, 0, tokens=(1, 0, 1)),
                                              lambda d: rollout(d, 1, parent=UUIDS[0], calls=[("playwright-test", "test_run", "completed")], tokens=(2, 0, 1))])
        self.assertEqual(wrong_tool["status"], "inconclusive")
        self.assertEqual(self.evaluate(stream(), None)["status"], "fail")  # nothing persisted
        no_usage = self.evaluate(stream(), [lambda d: rollout(d, 0, tokens=(1, 0, 1)),
                                            lambda d: rollout(d, 1, parent=UUIDS[0], calls=[("playwright-test", "test_list", "completed")])])
        self.assertEqual((no_usage["status"], no_usage["criteria"]["child_token_usage_present"]), ("fail", False))
        self.assertEqual(self.evaluate(stream(), self.good, infrastructure_error=True)["status"], "aborted")  # rate limit, schema error, container error
        self.assertEqual(self.evaluate(stream(), self.good, timeout=True)["status"], "fail")
        self.assertFalse(self.evaluate(stream(mcp=1), self.good)["info"]["parent_stream_blind_to_child"])  # premise broken: recorded

    def test_a_spawn_without_a_child_rollout_or_a_dirty_census_is_a_fail_not_an_inconclusive(self):
        spawn = spawn_item(UUIDS[1])
        root_only = [lambda d: rollout(d, 0, tokens=(1, 0, 1))]
        lost = self.evaluate(stream() + [spawn], root_only)
        self.assertEqual((lost["status"], lost["criteria"]["spawns_have_rollouts"], lost["info"]["spawns_in_parent_stream"]), ("fail", False, 1))
        self.assertEqual(self.evaluate(stream(), root_only)["status"], "inconclusive")  # nothing spawned: still model behaviour
        skipped = {"files": 2, "bytes": 1, "skipped": ["rollout-x.jsonl (oversize)"], "dir": "t"}
        self.assertEqual(self.evaluate(stream(), self.good, compliance={"sessions": skipped})["status"], "fail")
        self.assertEqual(self.evaluate(stream(), root_only, compliance={"sessions": skipped})["status"], "fail")  # not inconclusive either
        ok = {"files": 2, "bytes": 1, "skipped": [], "dir": "t"}
        self.assertEqual(self.evaluate(stream() + [spawn], self.good, compliance={"sessions": ok})["status"], "pass")

    def test_child_shell_and_mutating_tool_success_are_both_required(self):
        for shell_code, navigation in ((1, "completed"), (0, "failed"), (1, "failed")):
            builds = [lambda d: rollout(d, 0, tokens=(1, 0, 1)),
                      lambda d: rollout(d, 1, parent=UUIDS[0], tokens=(2, 0, 1),
                        calls=[("playwright-test", "generator_setup_page", "completed"),
                               ("playwright-test", "browser_navigate", navigation)],
                        extra=[{"type": "event_msg", "payload": {"type": "exec_command_end",
                            "command": ["ls", "specs/plan.md"], "exit_code": shell_code}}])]
            check = self.evaluate(stream(), builds)
            self.assertEqual(check["status"], "fail")
            self.assertEqual(check["criteria"]["child_shell_works"], shell_code == 0)
            self.assertEqual(check["criteria"]["child_mutating_mcp_ok"], navigation == "completed")

    def test_parent_shell_success_does_not_validate_the_child(self):
        shell = {"type": "event_msg", "payload": {"type": "exec_command_end", "command": ["ls", "specs/plan.md"], "exit_code": 0}}
        builds = [lambda d: rollout(d, 0, tokens=(1, 0, 1), extra=[shell]),
                  lambda d: rollout(d, 1, parent=UUIDS[0], tokens=(2, 0, 1), calls=[
                    ("playwright-test", "generator_setup_page", "completed"), ("playwright-test", "browser_navigate", "completed")])]
        self.assertFalse(self.evaluate(stream(), builds)["criteria"]["child_shell_works"])

    def test_native_shell_output_needs_observed_success(self):
        call = {"type":"response_item", "payload":{"type":"function_call", "name":"exec_command", "call_id":"shell", "arguments":'{"cmd":"ls specs/plan.md"}'}}
        for output, success in (("Process exited with code 0\nspecs/plan.md", 1),
                ("Process exited with code 1\nbwrap: No permissions to create a new namespace", 0),
                ('{"exit_code":0,"output":"specs/plan.md"}', 1), ("I listed specs/plan.md successfully", 0)):
            result = {"type":"response_item", "payload":{"type":"function_call_output", "call_id":"shell", "output":output}}
            self.assertEqual(ev.successful_plan_shell([call,result]), success)

    def test_result_is_bound_to_the_freeze_and_only_a_bound_pass_loads(self):
        with tempfile.TemporaryDirectory() as tmp, memory_freeze(Path(tmp) / "freeze.json"), patch.object(m, "BASE", Path(tmp)):
            lock = Path(tmp) / "freeze.json"
            lock.write_text("{}")
            with patch.object(m, "LOCK", lock):
                with self.assertRaisesRegex(ValueError, "no harness live check"):
                    m.load_harness_check()

                def call(tdir):
                    jl(tdir / "t.jsonl", stream())
                    sdir = tdir.parent / "codex-sessions" / "t"
                    self.good[0](sdir), self.good[1](sdir)
                    return arm_rec(transcript_path="/x/t.jsonl", elapsed_ms=5000)
                data = m.run_harness_check("gpt-6-sol", Path(tmp) / "_entry/harness-check", call)
                self.assertEqual((data["status"], data["attempts"], data["freeze_sha256"]), ("pass", 1, m.digest(lock)))
                self.assertEqual(m.load_harness_check()["status"], "pass")
                lock.write_text('{"x":1}')  # a different freeze
                with self.assertRaisesRegex(ValueError, "not a pass bound to this freeze"):
                    m.load_harness_check()
                lock.write_text("{}")
                m.harness_check_path().write_text(json.dumps(dict(data, status="inconclusive")))
                with self.assertRaises(ValueError):
                    m.load_harness_check()

    def test_preflight_runs_the_check_first_and_stops_without_entry_calls_unless_it_passes(self):
        order = []

        def run(status):
            order.clear()
            check = {"status": status, "criteria": {}, "info": {}, "model": "gpt-6-sol", "attempts": 1}
            handle = SimpleNamespace(close=lambda: order.append("unlock"))
            with tempfile.TemporaryDirectory() as tmp, memory_freeze(Path(tmp) / "freeze.json"), patch.object(m, "BASE", Path(tmp)), patch.object(m, "frozen", lambda: {}), \
                    patch.object(m, "campaign_lock", lambda: handle), patch.object(m, "bind_v1", lambda: None), patch.object(m.orig, "output_guard", lambda p: None), \
                    patch.object(m, "configure", lambda *a: order.append("configure")), \
                    patch.object(m, "ensure_harness_check", lambda *a: (order.append("check"), check)[1]), \
                    patch.object(m, "run_entry", lambda *a: (order.append("entry"), ("admitted", {"attempts": [], "aborted_calls": 0}))[1]), \
                    patch.object(m, "LOCK", Path(tmp) / "freeze.json"), contextlib.redirect_stdout(io.StringIO()):
                (Path(tmp) / "freeze.json").write_text("{}")
                return m.preflight(argparse.Namespace(allow_live=True, model="gpt-6-sol"))
        self.assertEqual(run("inconclusive"), 5)
        self.assertEqual(order, ["configure", "check", "unlock"])
        self.assertEqual(run("fail"), 5)
        self.assertNotIn("entry", order)
        self.assertEqual(run("pass"), 0)
        self.assertEqual(order[:3], ["configure", "check", "entry"])

    def test_drive_refuses_without_a_passing_check_before_reading_any_entry_decision(self):
        with patch.object(m, "frozen", lambda: {}), patch.object(m, "load_entries", side_effect=AssertionError("entries read first")), \
                patch.object(m, "load_harness_check", side_effect=ValueError("no harness live check recorded")):
            with self.assertRaisesRegex(ValueError, "harness live check"):
                m.drive(argparse.Namespace(allow_live=True, only=None, descriptive_only=False))

    def test_the_check_prompt_and_command_are_cheap_and_bound(self):
        self.assertIn("browser_navigate", m.HARNESS_CHECK_LINE)
        self.assertIn("Do not create or edit spec files", m.HARNESS_CHECK_LINE)
        self.assertEqual(m.bindings()["harness_check_line"], m.orig.sha(m.HARNESS_CHECK_LINE))
        with patch("subprocess.run", side_effect=AssertionError("executed")), patch("subprocess.Popen", side_effect=AssertionError("executed")):
            with self.assertRaisesRegex(ValueError, "--allow-live"):
                m.harness_check_cmd(argparse.Namespace(allow_live=False, model=None))
        with patch("sys.argv", ["x", "harness-check"]), self.assertRaisesRegex(ValueError, "--allow-live"):
            m.main()


# ------------------------------------------------------------------------------------------------ (d) cost, fidelity, as-treated

class SpawnLineage(unittest.TestCase):
    def observe(self, events, builds):
        with tempfile.TemporaryDirectory() as tmp:
            tdir, _ = make_cell_files(tmp, events, builds)
            rec = arm_rec(compliance={"sessions": {"files": len(builds), "skipped": []}})
            return m.classify_fidelity(rec, tdir), m.tokens_for_record(rec, tdir), m.evaluate_harness_check(rec, tdir)

    def test_root_rollout_does_not_discard_an_unmatched_parent_stream_spawn(self):
        builds = [lambda d: rollout(d, 0, tokens=(10, 0, 1)),
                  lambda d: rollout(d, 1, parent=UUIDS[0], tokens=(20, 0, 2),
                                    calls=[("playwright-test", "test_list", "completed")])]
        # A persisted root and a usable child do not establish that an additional stream spawn is stale.
        fid, tokens, check = self.observe(stream() + [spawn_item(UUIDS[7])], builds)
        self.assertEqual(check["status"], "fail")
        self.assertFalse(check["criteria"]["spawns_have_rollouts"])
        self.assertFalse(fid["evidence"]["primary_signal_complete"])
        self.assertTrue(fid["evidence"]["observation_incomplete"])
        self.assertNotEqual(fid["evidence"]["primary_signal"], "rollout-absence")
        self.assertFalse(tokens["complete"])
        self.assertTrue(any(UUIDS[7] in gap for gap in tokens["observation_gaps"]))

    def test_matching_root_and_stream_spawns_do_not_hide_an_additional_stream_identity(self):
        root_spawn = [{"type": "response_item", "payload": {"type": "function_call", "name": "spawn_agent", "call_id": "root-child"}},
                      {"type": "response_item", "payload": {"type": "function_call_output", "call_id": "root-child",
                                                            "output": json.dumps({"agent_id": UUIDS[1]})}}]
        builds = [lambda d: rollout(d, 0, tokens=(10, 0, 1), extra=root_spawn),
                  lambda d: rollout(d, 1, parent=UUIDS[0], tokens=(20, 0, 2),
                                    calls=[("playwright-test", "test_list", "completed")])]
        events = stream() + [spawn_item(UUIDS[1]), spawn_item(UUIDS[1])]
        fid, tokens, check = self.observe(events, builds)
        self.assertEqual(check["status"], "inconclusive")
        self.assertEqual(fid["evidence"]["primary_signal"], "rollout-absence")
        self.assertTrue(fid["evidence"]["primary_signal_complete"])
        self.assertTrue(tokens["complete"])
        self.assertEqual(tokens["child_output"], 2)
        fid, tokens, check = self.observe(events + [spawn_item(UUIDS[7])], builds)
        self.assertEqual(check["status"], "fail")
        self.assertFalse(check["criteria"]["spawns_have_rollouts"])
        self.assertFalse(fid["evidence"]["primary_signal_complete"])
        self.assertNotEqual(fid["evidence"]["primary_signal"], "rollout-absence")
        self.assertFalse(tokens["complete"])
        self.assertTrue(any(UUIDS[7] in gap for gap in tokens["observation_gaps"]))

    def test_grandchild_cannot_replace_missing_direct_child(self):
        events = stream() + [spawn_item(UUIDS[1]), spawn_item(UUIDS[2])]
        builds = [lambda d: rollout(d, 0, tokens=(10, 0, 1)),
                  lambda d: rollout(d, 1, parent=UUIDS[0], tokens=(20, 0, 2), extra=[spawn_item(UUIDS[3])]),
                  lambda d: rollout(d, 3, parent=UUIDS[1], tokens=(30, 0, 3), calls=[("playwright-test", "test_list", "completed")])]
        fid, tokens, check = self.observe(events, builds)
        self.assertFalse(fid["evidence"]["primary_signal_complete"])
        self.assertTrue(fid["evidence"]["observation_incomplete"])
        self.assertTrue(any(UUIDS[2] in gap for gap in fid["evidence"]["observation_gaps"]))
        self.assertFalse(tokens["complete"])
        self.assertEqual(check["status"], "fail")
        self.assertFalse(check["criteria"]["spawns_have_rollouts"])

    def test_missing_descendant_spawn_in_function_schema_breaks_completeness(self):
        spawn = [{"type": "response_item", "payload": {"type": "function_call", "name": "spawn_agent", "call_id": "child"}},
                 {"type": "response_item", "payload": {"type": "function_call_output", "call_id": "child",
                                                       "output": json.dumps({"agent_id": UUIDS[2]})}}]
        builds = [lambda d: rollout(d, 0, tokens=(10, 0, 1)),
                  lambda d: rollout(d, 1, parent=UUIDS[0], tokens=(20, 0, 2), extra=spawn)]
        fid, tokens, check = self.observe(stream() + [spawn_item(UUIDS[1])], builds)
        self.assertFalse(fid["evidence"]["primary_signal_complete"])
        self.assertFalse(tokens["complete"])
        self.assertEqual(check["status"], "fail")

    def test_spawn_end_events_also_require_the_named_descendant(self):
        end = {"type": "event_msg", "payload": {"type": "collab_agent_spawn_end", "new_thread_id": UUIDS[2]}}
        builds = [lambda d: rollout(d, 0, tokens=(10, 0, 1)),
                  lambda d: rollout(d, 1, parent=UUIDS[0], tokens=(20, 0, 2), extra=[end])]
        fid, tokens, check = self.observe(stream() + [spawn_item(UUIDS[1])], builds)
        self.assertFalse(fid["evidence"]["primary_signal_complete"])
        self.assertFalse(tokens["complete"])
        self.assertEqual(check["status"], "fail")

    def test_matching_unique_identities_at_every_level_are_complete(self):
        events = stream() + [spawn_item(UUIDS[1]), spawn_item(UUIDS[2]), spawn_item(UUIDS[1])]
        builds = [lambda d: rollout(d, 0, tokens=(10, 0, 1), extra=[spawn_item(UUIDS[1]), spawn_item(UUIDS[2])]),
                  lambda d: rollout(d, 1, parent=UUIDS[0], tokens=(20, 0, 2), extra=[spawn_item(UUIDS[3])]),
                  lambda d: rollout(d, 2, parent=UUIDS[0], tokens=(30, 0, 3)),
                  lambda d: rollout(d, 3, parent=UUIDS[1], tokens=(40, 0, 4), calls=[("playwright-test", "test_list", "completed")])]
        fid, tokens, check = self.observe(events, builds)
        self.assertTrue(fid["evidence"]["primary_signal_complete"])
        self.assertTrue(tokens["complete"])
        self.assertEqual(tokens["child_output"], 9)
        self.assertEqual(check["status"], "inconclusive")

    def test_unknown_ids_wrong_parents_and_duplicate_rollouts_are_incomplete(self):
        for failure in ("parent", "duplicate"):
            events = stream() + [spawn_item() if failure == "unknown" else spawn_item(UUIDS[1])]
            builds = [lambda d: rollout(d, 0, tokens=(10, 0, 1)),
                      lambda d: rollout(d, 1, parent=UUIDS[7] if failure == "parent" else UUIDS[0], tokens=(20, 0, 2),
                                        calls=[("playwright-test", "test_list", "completed")])]
            if failure == "duplicate":
                def duplicate(d):
                    source = next(Path(d).rglob("*" + UUIDS[1] + ".jsonl"))
                    (Path(d) / ("rollout-copy-" + UUIDS[1] + ".jsonl")).write_text(source.read_text())
                builds.append(duplicate)
            fid, tokens, check = self.observe(events, builds)
            self.assertFalse(fid["evidence"]["primary_signal_complete"], failure)
            self.assertFalse(tokens["complete"], failure)
            self.assertEqual(check["status"], "fail", failure)
            if failure == "duplicate":
                self.assertEqual(tokens["child_output"], 2)  # duplicate identity is never counted twice

    def test_unknown_spawn_identity_is_resolved_by_child_rollouts_naming_the_parent(self):
        # Codex multi_agent v2 spawn outputs carry only a task name (live check 2026-10-15), so the identity is unknown by design.
        build_child = lambda d: rollout(d, 1, parent=UUIDS[0], tokens=(20, 0, 2), calls=[("playwright-test", "test_list", "completed")])
        fid, tokens, check = self.observe(stream() + [spawn_item()], [lambda d: rollout(d, 0, tokens=(10, 0, 1)), build_child])
        self.assertTrue(fid["evidence"]["primary_signal_complete"])
        self.assertTrue(tokens["complete"])
        self.assertEqual(check["status"], "inconclusive")
        # negative control: a spawn whose child rollout was never persisted stays a gap
        fid, tokens, check = self.observe(stream() + [spawn_item()], [lambda d: rollout(d, 0, tokens=(10, 0, 1))])
        self.assertFalse(fid["evidence"]["primary_signal_complete"])
        self.assertEqual(check["status"], "fail")


class CostAndTreatment(unittest.TestCase):
    def test_codex_tokens_parent_children_and_fallbacks(self):
        sess = {"root_found": True, "child_usage": usage(1000, 600, 100), "children_total": 2, "children_without_usage": 0, "root_rollout_usage": usage(70, 50, 7)}
        rec = {"usage": {"input_tokens": 99, "cached_input_tokens": 1, "output_tokens": 1}, "usage_all_turns": [usage(200, 150, 20, 5), usage(100, 50, 10, 2)]}
        # the parent's own rollout is preferred (correct whether or not the stream folds the children in); the stream is the cross-check
        t = ev.codex_tokens(rec, sess)
        self.assertEqual((t["uncached_input"], t["cached_input"], t["output"], t["parent_source"]), (20, 50, 7, "rollout"))
        self.assertEqual(t["parent_cross_check"], {"stream_total": 330, "rollout_total": 77, "differs": True})
        self.assertEqual((t["child_uncached_input"], t["child_cached_input"], t["child_output"]), (400, 600, 100))
        self.assertEqual((t["processed"], t["total"], t["complete"]), (20 + 7 + 400 + 100, 20 + 7 + 400 + 100 + 50 + 600, True))
        no_root = dict(sess, root_rollout_usage=None)  # fallback usage is reported but cannot be a complete cost endpoint
        t = ev.codex_tokens(rec, no_root)
        self.assertEqual((t["uncached_input"], t["cached_input"], t["output"], t["reasoning_output"], t["parent_turns"]), (100, 200, 30, 7, 2))
        self.assertEqual((t["processed"], t["total"], t["parent_source"], t["parent_cross_check"]), (100 + 30 + 400 + 100, 100 + 30 + 400 + 100 + 200 + 600, "stream.turn.completed", None))
        self.assertFalse(t["complete"])
        single = ev.codex_tokens({"usage": usage(10, 4, 2)}, no_root)
        self.assertEqual((single["parent_source"], single["uncached_input"]), ("stream.usage", 6))
        from_rollout = ev.codex_tokens({}, sess)  # a timeout: no turn.completed; the root rollout carries the parent's usage
        self.assertEqual((from_rollout["parent_source"], from_rollout["uncached_input"], from_rollout["complete"]), ("rollout", 20, True))
        agree = ev.codex_tokens({"usage": usage(70, 50, 7)}, sess)
        self.assertFalse(agree["parent_cross_check"]["differs"])
        none = ev.codex_tokens(rec, None)
        self.assertFalse(none["complete"])
        self.assertIn("unavailable", none["child_status"])
        partial = ev.codex_tokens(rec, dict(sess, children_without_usage=1))
        self.assertFalse(partial["complete"])
        self.assertFalse(ev.codex_tokens({}, dict(no_root))["complete"])
        for incomplete in (dict(sess, malformed_lines=1), dict(sess, children_unlinked=1), dict(sess, extra_root_rollouts=1)):
            self.assertFalse(ev.codex_tokens(rec, incomplete)["complete"])
        self.assertFalse(ev.codex_tokens(dict(rec, compliance={"agent_spawns": 3}), sess)["complete"])
        for census in ({"skipped": ["rollout-x.jsonl (oversize)"]}, {"error": "copy failed"}):
            self.assertFalse(ev.codex_tokens(dict(rec, compliance={"sessions": census}), sess)["complete"])

    def test_claude_tokens_and_cost_from_model_usage(self):
        rec = {"model_usage": {"claude-sonnet-5-5": {"inputTokens": 12, "outputTokens": 3534, "cacheReadInputTokens": 127567, "cacheCreationInputTokens": 33990,
                                                       "thinkingTokens": 347, "costUSD": 0.1840807}},
               "usage": {"input_tokens": 161569, "cached_input_tokens": 127567, "output_tokens": 3534}}
        t = ev.cell_tokens(rec, None)
        self.assertEqual((t["family"], t["uncached_input"], t["cached_input"], t["output"], t["cost_usd"]), ("claude", 12 + 33990, 127567, 3534, 0.184081))
        self.assertEqual((t["processed"], t["total"], t["complete"]), (12 + 33990 + 3534, 12 + 33990 + 3534 + 127567, True))
        two = {"model_usage": {"a": {"inputTokens": 1, "outputTokens": 2, "costUSD": 0.5}, "b": {"inputTokens": 3, "outputTokens": 4, "costUSD": 0.25}}}
        self.assertEqual((ev.cell_tokens(two, None)["cost_usd"], ev.cell_tokens(two, None)["output"]), (0.75, 6))
        self.assertEqual(ev.cell_tokens({"usage": usage(10, 4, 2)}, {"child_usage": usage(0, 0, 0), "children_total": 0, "children_without_usage": 0,
                                                                        "root_rollout_usage": None})["family"], "codex")

    def test_pipeline_totals_for_arm_b_and_cost_endpoint_math(self):
        a = ev.codex_tokens({"usage": usage(1000, 800, 100)}, {"root_found": True, "child_usage": usage(500, 100, 50), "children_total": 1, "children_without_usage": 0, "root_rollout_usage": usage(1000, 800, 100)})
        b = ev.codex_tokens({"usage": usage(300, 100, 30)}, {"root_found": True, "child_usage": usage(0, 0, 0), "children_total": 0, "children_without_usage": 0, "root_rollout_usage": usage(300, 100, 30)})
        pipe = ev.pipeline_tokens([a, b])
        self.assertEqual((pipe["uncached_input"], pipe["output"], pipe["child_uncached_input"], pipe["child_output"]), (200 + 200, 130, 400, 50))
        self.assertEqual(pipe["processed"], a["processed"] + b["processed"])
        self.assertTrue(pipe["complete"])
        self.assertFalse(ev.pipeline_tokens([a, dict(b, complete=False)])["complete"])
        cell = lambda score, tokens, elapsed: {"refactor_score": score, "pipeline": {"tokens": tokens, "elapsed_s": elapsed}}
        t1, t2 = ev.pipeline_tokens([a]), ev.pipeline_tokens([b])
        e = pool.cost_endpoint([cell(1.0, t1, 100.0), cell(0.0, t2, 50.0), cell(1.0, dict(t2, complete=False), 10.0)])
        self.assertEqual((e["cells"], e["cells_with_complete_tokens"], e["survivors"], e["survivors_in_complete_cells"]), (3, 2, 2.0, 1.0))
        self.assertEqual(e["quality_per_100k_processed"], round(100000 * 1.0 / (t1["processed"] + t2["processed"]), 4))  # ratio of sums
        self.assertEqual(e["quality_per_100k_total"], round(100000 * 1.0 / (t1["total"] + t2["total"]), 4))
        self.assertEqual((e["elapsed_s_mean"], e["elapsed_s_per_survivor"]), (53.3, 80.0))
        empty = pool.cost_endpoint([cell(1.0, dict(t1, complete=False), 1.0)])
        self.assertIsNone(empty["quality_per_100k_processed"])

    def synthetic_cells(self):
        cells = []
        for i, task in enumerate(TASKS):
            for rep in range(1, m.protocol()["repetitions"] + 1):
                official = i < 4
                cells.append({"case": task, "repetition": rep, "arm": A, "aborted": False, "fidelity_class": "official-tool" if official else "blocked",
                              "fidelity": {"evidence": {"primary_signal": "rollout" if official else "rollout-absence", "signal_conflict": False}},
                              "rollouts": {"children_total": 1, "playwright_test_completed": 1 if official else 0, "generator_write_test_completed": 2 if official else 0}})
                cells.append({"case": task, "repetition": rep, "arm": B, "aborted": False, "unavailable": None, "treatment": {"treated": rep % 2 == 1, "reviewer_skill_read": True, "scanner": rep % 2 == 1}})
                core = i % 2 == 0
                steps = {s: (s in ("skill_md_read", "reference_read", "scanner") and core) or s == "skill_md_read" for s in ev.C_STEPS}
                cells.append({"case": task, "repetition": rep, "arm": C, "aborted": False, "compliance_raw": {"scanner_runs": int(core), "commands_over_400_chars": 1},
                              "treatment": {"available": True, "steps": steps, "treated_core": core}})
        return cells

    def test_as_treated_flags_view_and_fidelity_table(self):
        cells = self.synthetic_cells()
        m.set_as_treated(cells)
        by = lambda arm: [c for c in cells if c["arm"] == arm]
        self.assertEqual((sum(c["as_treated"] for c in by(A)), sum(c["as_treated"] for c in by(B)), sum(c["as_treated"] for c in by(C))), (16, 8, 12))
        # a B cell is as-treated only if its source A cell is official-tool AND its own reviewer steps ran
        for c in by(B):
            src = next(a for a in by(A) if (a["case"], a["repetition"]) == (c["case"], c["repetition"]))
            self.assertEqual(c["as_treated"], src["fidelity_class"] == "official-tool" and c["treatment"]["treated"])
        sub = [c for c in cells if m.in_view(dict(c, load_flagged=False), "as_treated")]
        self.assertEqual(len(sub), 36)
        self.assertTrue(m.in_view(dict(by(C)[0], aborted=False), "itt"))
        self.assertFalse(m.in_view(dict(by(A)[0], aborted=True), "as_treated"))
        self.assertFalse(m.in_view({"arm": A, "aborted": False}, "as_treated"))  # default: not treated
        ft = m.fidelity_table(cells)
        self.assertEqual((ft["arm_a"]["official_tool"], ft["arm_a"]["with_playwright_test_calls"], ft["arm_a"]["generator_write_test_completed"]), (16, 16, 32))
        self.assertEqual(ft["arm_a"]["primary_signal_counts"], {"rollout": 16, "rollout-absence": 8})
        self.assertEqual((ft["arm_b"]["cells"], ft["arm_b"]["treated"]), (24, 12))
        self.assertEqual((ft["arm_c"]["treated_core"], ft["arm_c"]["steps"]["skill_md_read"], ft["arm_c"]["steps"]["preflight"], ft["arm_c"]["steps"]["scanner"]), (12, 24, 0, 12))
        self.assertEqual(ft["arm_c"]["scanner_runs_engine_definition"], 12)
        self.assertEqual(ft["as_treated_cells"], {A: 16, B: 8, C: 12})

    def test_add_pipeline_links_arm_b_to_its_source_a_cell(self):
        tok = lambda n: dict(ev.pipeline_tokens([ev.codex_tokens({"usage": usage(n, 0, 1)}, {"child_usage": usage(0, 0, 0), "children_total": 0, "children_without_usage": 0, "root_rollout_usage": None})]))
        cells = [{"case": "k", "repetition": 1, "arm": A, "tokens": ev.codex_tokens({"usage": usage(100, 0, 1)}, {"child_usage": usage(0, 0, 0), "children_total": 0, "children_without_usage": 0, "root_rollout_usage": None}), "elapsed_s": 10.0},
                 {"case": "k", "repetition": 1, "arm": B, "tokens": ev.codex_tokens({"usage": usage(7, 0, 1)}, {"child_usage": usage(0, 0, 0), "children_total": 0, "children_without_usage": 0, "root_rollout_usage": None}), "elapsed_s": 2.5},
                 {"case": "k", "repetition": 2, "arm": B, "tokens": ev.codex_tokens({}, None), "elapsed_s": 1.0}]
        m.add_pipeline(cells)
        b1, b2 = cells[1]["pipeline"], cells[2]["pipeline"]
        self.assertEqual((b1["tokens"]["uncached_input"], b1["tokens"]["output"], b1["elapsed_s"], b1["includes_source_a"]), (107, 2, 12.5, True))
        self.assertEqual((b2["includes_source_a"], b2["tokens"]["complete"]), (False, False))
        self.assertEqual(cells[0]["pipeline"]["elapsed_s"], 10.0)


# ------------------------------------------------------------------------------------------------ (e) pooled analysis

def grid_cells(effects, tasks=TASKS):
    """{model: [cells]}: per model and task one X cell and one Y cell whose refactor_score differ by effects[model][task]."""
    out = {}
    for model, per_task in effects.items():
        cells = []
        for task, d in zip(tasks, per_task):
            for rep in range(1, m.protocol()["repetitions"] + 1):
                cells.append({"case": task, "arm": "X", "repetition": rep, "refactor_score": 0.5 + d / 2, "clean": True, "effective_fault_kill": 1.0})
                cells.append({"case": task, "arm": "Y", "repetition": rep, "refactor_score": 0.5 - d / 2, "clean": True, "effective_fault_kill": 1.0})
        out[model] = cells
    return out


class PooledAnalysis(unittest.TestCase):
    def test_sign_flip_is_exact_and_hand_checkable(self):
        self.assertEqual(pool.sign_flip_exact([1, 2, 3]), {"n_models": 3, "p_two_sided": 0.25, "min_attainable_p": 0.25, "patterns": 8})
        six = pool.sign_flip_exact([0.1, 0.2, 0.3, 0.1, 0.2, 0.4])
        self.assertEqual((six["p_two_sided"], six["min_attainable_p"], six["patterns"]), (2 / 64, 2 / 64, 64))
        four = pool.sign_flip_exact([0.3] * 4)
        self.assertEqual((four["p_two_sided"], four["min_attainable_p"]), (0.125, 0.125))  # N <= 4 can never reach 0.05
        self.assertEqual(pool.sign_flip_exact([0.5, -0.5])["p_two_sided"], 1.0)
        self.assertEqual(pool.sign_flip_exact([0, 0, 0])["p_two_sided"], 1.0)
        mixed = pool.sign_flip_exact([1, 1, 1, -0.5])
        self.assertEqual(mixed["p_two_sided"], 0.25)  # |mean| = 0.625; reached only when the three 1s share a sign: 4 of 16 patterns
        self.assertIsNone(pool.sign_flip_exact([])["p_two_sided"])
        with self.assertRaises(ValueError):
            pool.sign_flip_exact([1] * 17)

    def test_estimate_is_unweighted_over_models_and_tasks(self):
        grid = {"m1": {"t1": 1.0, "t2": 0.0, "t3": None}, "m2": {"t1": 0.5, "t2": 0.5, "t3": 0.5}, "m3": {"t1": None, "t2": None, "t3": None}}
        self.assertEqual(pool.model_effect(grid["m1"]), 0.5)
        self.assertIsNone(pool.model_effect(grid["m3"]))
        self.assertEqual(pool.pooled_estimate(grid), 0.5)
        self.assertEqual(pool.leave_one_model_out({"a": {"t": 1.0}, "b": {"t": 0.0}, "c": {"t": 0.5}}), {"a": 0.25, "b": 0.75, "c": 0.5})

    def test_cluster_bootstrap_is_seeded_degenerate_when_constant_and_wider_with_spread(self):
        const = {f"m{i}": {f"t{j}": 0.25 for j in range(6)} for i in range(5)}
        self.assertEqual(pool.cluster_bootstrap(const, reps=300)["ci"], [0.25, 0.25])
        rng_grid = {f"m{i}": {f"t{j}": ((i * 7 + j * 3) % 5 - 2) / 4 for j in range(6)} for i in range(6)}
        one, two = pool.cluster_bootstrap(rng_grid, reps=500), pool.cluster_bootstrap(rng_grid, reps=500)
        self.assertEqual(one, two)
        lo, hi = one["ci"]
        self.assertLess(lo, hi)
        self.assertLessEqual(lo, pool.pooled_estimate(rng_grid) + 0.2)
        self.assertGreaterEqual(hi, pool.pooled_estimate(rng_grid) - 0.2)
        self.assertNotEqual(pool.cluster_bootstrap(rng_grid, reps=500, seed=1)["ci"], one["ci"])
        self.assertIsNone(pool.cluster_bootstrap({}, reps=10)["ci"])
        holes = {"a": {"t1": None, "t2": None}, "b": {"t1": 0.5, "t2": None}}
        self.assertIsNotNone(pool.cluster_bootstrap(holes, reps=200)["ci"])

    def test_pooled_report_is_always_development_evidence_and_matches_the_grid(self):
        effects = {f"m{i}": [0.5] * 6 for i in range(6)}
        lineage = {f"m{i}": "g1" if i < 3 else "g2" for i in range(6)}
        r = pool.pooled_report(grid_cells(effects), lineage, "X", "Y", TASKS, reps=200)
        self.assertEqual((r["n_models"], r["estimate_unweighted_over_models"], r["models_positive"], r["models_negative"]), (6, 0.5, 6, 0))
        self.assertEqual(r["label"], "development evidence")
        self.assertEqual((r["sign_flip"]["p_two_sided"], r["lineage_means"]), (2 / 64, {"g1": 0.5, "g2": 0.5}))
        self.assertEqual(set(r["task_profile"]), set(TASKS))
        approved = pool.pooled_report(grid_cells(effects), lineage, "X", "Y", TASKS, reps=50, inference_approved=True)
        self.assertEqual(approved["label"], "development evidence")
        only = pool.pooled_report(grid_cells(effects), lineage, "X", "Y", TASKS, reps=50, eligible=["m0", "m5"])
        self.assertEqual(only["n_models"], 2)
        empty = pool.pooled_report({"m": []}, {}, "X", "Y", TASKS, reps=10)
        self.assertEqual((empty["n_models"], empty["estimate_unweighted_over_models"], empty["sign_flip"]["p_two_sided"]), (0, None, None))
        other = pool.pooled_report(grid_cells({"a": [0.2] * 6, "b": [-0.2] * 6}), {}, "X", "Y", TASKS, metric="clean", reps=10)
        self.assertEqual(other["estimate_unweighted_over_models"], 0.0)  # clean is 1 in both arms: no difference

    def test_pooled_analysis_uses_the_cross_model_eligibility_and_the_protocol_section(self):
        p = m.protocol()
        cfg = p["pooled_analysis"]
        self.assertIs(cfg["owner_approval"]["inference"], True)
        self.assertIs(cfg["owner_approval"]["pooling_with_v1_claude_family"], False)
        self.assertEqual((cfg["primary_view"], cfg["metrics"][0], cfg["cluster_bootstrap"]["replicates"], cfg["cluster_bootstrap"]["seed"]), ("primary", "refactor_score", 10000, 20261016))
        self.assertEqual(set(cfg["views"]), {"primary", "itt", "as_treated"})
        ids = [x["id"] for x in p["models"]]
        label = lambda eligible: {"C_minus_A": {"eligible": eligible}, "B_minus_A": {"eligible": eligible}, "C_minus_B": {"eligible": eligible}}
        results = {}
        for i, mid in enumerate(ids):
            cells = [dict(c, arm={"X": C, "Y": A}[c["arm"]], aborted=False, as_treated=True, load_flagged=False, fidelity_class="official-tool", deliverable=True)
                     for c in grid_cells({mid: [0.4] * 6})[mid]]
            results[mid] = {"complete": i != 1, "cells": cells, "views": {v: {"labels": label(i != 2)} for v in m.VIEWS}}
        small = json.loads(json.dumps(p))
        small["pooled_analysis"]["cluster_bootstrap"]["replicates"] = 50
        out = m.pooled_analysis(results, small)
        self.assertEqual(out["primary|C_minus_A|refactor_score"]["n_models"], 4)  # one incomplete, one not evaluable
        self.assertEqual(out["primary|C_minus_A|refactor_score"]["estimate_unweighted_over_models"], 0.4)
        self.assertIn("primary|C_minus_A|clean", out)
        self.assertNotIn("itt|C_minus_A|clean", out)  # secondary metrics in the primary view only
        self.assertIn("as_treated|C_minus_B|refactor_score", out)
        self.assertTrue(all(r["label"] == "development evidence" for r in out.values()))
        bad = json.loads(json.dumps(p))
        bad["pooled_analysis"]["owner_approval"]["inference"] = "yes"
        with patch.object(m, "read", lambda path, _real=m.read: bad if Path(path) == m.PROTOCOL else _real(path)), self.assertRaisesRegex(ValueError, "boolean"):
            m.protocol()


# ------------------------------------------------------------------------------------------------ (5) selector hygiene

class SelectorHygiene(unittest.TestCase):
    def test_static_scan_of_string_literals(self):
        r = ev.references_renamed_selector
        self.assertTrue(r(["await page.locator('#bg-total').click();"], ["bg-total"]))
        self.assertTrue(r(["page.locator('article.over')"], ["over"]))
        self.assertTrue(r(['page.locator("[class*=\'over\']")'], ["over"]))
        self.assertTrue(r(["page.locator('[id=\"bg-total\"]')"], ["bg-total"]))
        self.assertFalse(r(["page.getByRole('status', { name: 'bg-total' })", "const n = data.total;"], ["bg-total", "total"]))
        self.assertFalse(r(["page.locator('#bg-total-extra')"], ["bg-total"]))  # a longer id is another id
        self.assertIsNone(r([], ["x"]))
        self.assertIsNone(r(["page.locator('#x')"], []))

    def test_multi_line_template_literals_are_read_and_dynamic_selectors_are_flagged_not_scanned(self):
        r = ev.references_renamed_selector
        self.assertTrue(r(["page.locator(`\n  #bg-total\n`)"], ["bg-total"]))
        self.assertFalse(r(["// don't do this\nconst a = 1;\nconst b = 'it';"], ["bg-total"]))  # a stray apostrophe pairs nothing across lines
        for dynamic in ("page.locator('#' + ID)", "page.locator(`#${ID}`)", "page.locator(`.item-${n}`)", "page.locator(sel)"):
            self.assertFalse(r([dynamic], ["bg-total"]), dynamic)  # still unreadable by the static scan: documented blind spot
            self.assertTrue(ev.dynamic_selector_hint([dynamic]), dynamic)
        for literal in ("page.locator('#bg-total')", "page.getByRole('button', { name: 'Add' })", "const label = `Total ${n}`;"):
            self.assertFalse(ev.dynamic_selector_hint([literal]), literal)
        t = pool.selector_table([{"clean": True, "references_renamed_selector": False, "refactor_score": 1.0, "dynamic_selector_hint": True},
                                 {"clean": True, "references_renamed_selector": False, "refactor_score": 1.0}])
        self.assertEqual(t["clean_not_referencing_with_dynamic_selector_hint"], 1)

    def test_removed_tokens_union_fixes_the_manifest_substring_blind_spot(self):
        edits = [{"find": 'node.className = "deck";', "replace": 'node.className = "deck__item";'},
                 {"find": '<p id="bg-total" class="total-line">', "replace": '<p id="bg-total" class="summary">'}]
        self.assertEqual(ev.removed_selector_tokens(edits), ["deck", "total-line"])
        self.assertEqual(ev.removed_selector_tokens(edits, ["manifest-only"]), ["deck", "manifest-only", "total-line"])
        self.assertEqual(ev.attribute_tokens('x.classList.add("a-b", "c"); el.id = "e1";'), {"a-b", "c", "e1"})

    def test_selector_status_reads_artifacts_and_case_truth(self):
        case = TASKS[0]
        edits = m.engine.load_truth(case)["refactor"]
        app = (m.engine.CASES / case / "app.mjs").read_text()
        tokens = ev.removed_selector_tokens(edits, m.engine.refactor_manifest(app, edits)["renamed_ids_and_classes"])
        self.assertTrue(tokens)
        with tempfile.TemporaryDirectory() as tmp:
            for name, text in (("a", f"page.locator('#{tokens[0]}')"), ("b", "page.getByRole('button', { name: 'Add' })")):
                f = Path(tmp) / "final-artifacts" / name / "tests/x.spec.ts"
                f.parent.mkdir(parents=True)
                f.write_text(text)
            cache = {}
            cell = lambda name: {"case": case, "call_id": name, "spec_files": ["tests/x.spec.ts"]}
            self.assertTrue(m.selector_status(cell("a"), tmp, cache))
            self.assertFalse(m.selector_status(cell("b"), tmp, cache))
            self.assertIsNone(m.selector_status(dict(cell("a"), spec_files=[]), tmp, cache))

    def test_selector_table_reports_the_two_by_two_and_the_clean_conditional_survival(self):
        cells = ([{"clean": True, "references_renamed_selector": True, "refactor_score": 0.0}] * 3
                 + [{"clean": True, "references_renamed_selector": False, "refactor_score": 1.0}] * 5
                 + [{"clean": True, "references_renamed_selector": False, "refactor_score": 0.0}]
                 + [{"clean": False, "references_renamed_selector": None, "refactor_score": 0.0}] * 2)
        t = pool.selector_table(cells)
        self.assertEqual((t["clean_cells"], t["clean_referencing_renamed_selector"], t["clean_referencing_failed_refactor"]), (9, 3, 3))
        self.assertEqual((t["clean_not_referencing"], t["clean_not_referencing_failed_refactor"]), (6, 1))
        self.assertEqual((t["clean_conditional_survival"], t["primary_survival"]), (round(5 / 9, 4), round(5 / 11, 4)))
        self.assertIsNone(pool.selector_table([])["clean_conditional_survival"])

    @unittest.skipUnless((SONNET / "scores.json").is_file() and (SOL / "scores.json").is_file(), "stored cells not present")
    def test_stored_cells_survival_is_selector_hygiene(self):
        """claude-sonnet-5-5 and gpt-6-sol, clean delivered cells: every cell referencing a renamed id/class failed the refactor, none of the others did."""
        ref, noref, cache = [0, 0], [0, 0], {}
        for d in (SONNET, SOL):
            rows = {(r["case"], r["arm"], r["repetition"]): r for r in m.read(d / "scores.json")["scores"]}
            for rec in m.read(d / "final.json")["runs"]:
                row = rows.get((rec["case"], rec["arm"], rec["repetition"]))
                if not (row and row.get("clean") and rec.get("spec_files")):
                    continue
                status = m.selector_status(dict(rec), d, cache)
                slot = ref if status else noref
                slot[0] += 1
                slot[1] += not row["refactor_score"]
        self.assertEqual(ref, [9, 9])
        self.assertEqual(noref, [40, 0])


# ------------------------------------------------------------------------------------------------ docs and files

class DocsAndFiles(unittest.TestCase):
    NEW_FILES = ("scripts/evals/generator_v3_codex_evidence.py", "scripts/evals/generator_v3_codex_pooled.py", "scripts/ci/test-generator-v3-codex-harness-fixes.py",
                 "scripts/evals/generator_codex_official_adapter_compat_v3.py", "scripts/evals/run-generator-multimodel-v3-codex.py",
                 "benchmarks/generator-multimodel-v3-codex/README.md", "benchmarks/generator-multimodel-v3-codex/CHANGES.md",
                 "benchmarks/generator-multimodel-v3-codex/protocol.json")

    def test_no_home_paths_and_english_only(self):
        for rel in self.NEW_FILES:
            text = (ROOT / rel).read_text()
            self.assertNotIn("/Us" + "ers/", text, rel)
            self.assertFalse(any(ord(ch) > 0x2fff and not 0x2000 <= ord(ch) <= 0x2bff for ch in text), rel)  # no CJK or Hangul
            self.assertNotIn("pupp" + "eteer", text.lower(), rel)

    def test_docs_state_the_review_fixes(self):
        readme = (ROOT / "benchmarks/generator-multimodel-v3-codex/README.md").read_text()
        for needle in ("Live check after freeze, before the first preflight", "preserve the frozen files", "`generator_*` or `browser_*`", "`observation_incomplete`",
                       "`aborted` means an infrastructure outcome", "reproduction on the cells the scan was refined against", "parent stream only",
                       "`pooling_with_v1_claude_family = false`"):
            self.assertIn(needle, readme)
        self.assertNotIn("Live check before freeze", readme)
        p = m.protocol()
        self.assertTrue(p["pooled_analysis"]["owner_approval"]["inference"])
        self.assertIn("approved 2026-10-15", p["pooled_analysis"]["owner_approval"]["note"])
        self.assertNotIn("written addendum bound", json.dumps(p["pooled_analysis"]))

    def test_protocol_documents_every_fix_and_the_follow_up(self):
        p = m.protocol()
        self.assertEqual(set(p["harness_fixes"]) - {"status"}, {"H1_port_conflict", "H2_command_truncation", "H3_child_agents", "H4_treatment_fidelity_arm_c",
                                                              "H5_headline_metric", "H6_cost_accounting", "H7_fidelity_tables", "H8_pooled_analysis"})
        self.assertEqual(p["secondary_refactor_classes"]["status"], "SPECIFIED_NOT_BUILT")
        self.assertEqual(set(p["secondary_refactor_classes"]["classes"]), {"R-TEXT", "R-STRUCT"})
        self.assertIn("quality per 100k", p["cost_endpoints"]["co_primary"])
        self.assertIn("pass_requires_all_of", p["harness_fixes"]["H3_child_agents"]["live_check"])
        self.assertEqual(p["status"], "NOT_RUN")
        changes = (ROOT / "benchmarks/generator-multimodel-v3-codex/CHANGES.md").read_text()
        for needle in ("H1", "H2", "H3", "H4", "H5", "H6", "H7", "H8"):
            self.assertIn(needle, changes)

    def test_the_new_modules_are_bound_in_the_freeze(self):
        b = m.bindings()
        self.assertEqual(b["evidence_module"], m.digest(m.EVIDENCE))
        self.assertEqual(b["pooled_module"], m.digest(m.POOLED))
        self.assertEqual(b["generation_config_policy"], m.orig.sha(json.dumps([m.SCORING_REUSE, m.GENERATION_REUSE])))

    def test_modules_have_no_io_side_effects_at_import_and_the_runner_does_not_touch_v1_files(self):
        self.assertTrue(m.v1_unchanged())
        for name in ("subprocess", "socket"):
            self.assertNotIn(f"import {name}", (ROOT / "scripts/evals/generator_v3_codex_evidence.py").read_text())
            self.assertNotIn(f"import {name}", (ROOT / "scripts/evals/generator_v3_codex_pooled.py").read_text())


if __name__ == "__main__":
    unittest.main()
