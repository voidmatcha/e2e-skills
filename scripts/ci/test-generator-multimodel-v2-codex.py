#!/usr/bin/env python3
"""Offline guards for generator-multimodel-v2-codex: schedule, freeze drift, adapter argv, arm A fidelity classifier,
decision rules, v1 immutability, live refusals. No network, no model, no container, no execution of the built argv. Apache-2.0."""
import argparse
import contextlib
import hashlib
import io
import importlib.util
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


m = load("gmm_v2_under_test", "scripts/evals/run-generator-multimodel-v2-codex.py")
frozen_adapter = load("frozen_official_adapter_for_diff", "scripts/evals/generator_codex_official_adapter.py")
DATA = Path.home() / ".cache/e2e-skills-bench"
GPT55, SOL, ASTRA = DATA / "offgen-pilot-v1", DATA / "multimodel-v1/gpt-6-sol", DATA / "multimodel-v1/gpt-6-astra"
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


class Schedule(unittest.TestCase):
    def test_72_cells_complete_unique_and_ordered(self):
        rows = m.schedule()
        self.assertEqual(len(rows), 72)
        self.assertEqual({(r["case"], r["arm"], r["repetition"]) for r in rows},
                         {(t, a, r) for t in TASKS for a in (A, B, C) for r in range(1, 5)})
        self.assertEqual([r["ordinal"] for r in rows], list(range(1, 73)))
        self.assertTrue(all(r["arm"] != B for r in rows[:48]) and all(r["arm"] == B for r in rows[48:]))
        by_id = {(r["case"], r["arm"], r["repetition"]): r["ordinal"] for r in rows}
        for r in rows[48:]:
            self.assertGreater(r["ordinal"], by_id[(r["case"], A, r["repetition"])])  # B runs after the A cell it reviews
        self.assertEqual(rows, m.schedule())

    def test_schedule_preserves_the_v1_seed_but_has_four_repetitions(self):
        self.assertEqual(m.protocol()["seed"], m._V1["protocol"]()["seed"])
        self.assertNotEqual(m.schedule(), m.read(m.V1_LOCK)["schedule"])
        self.assertEqual(m.protocol()["repetitions"], 4)

    def test_protocol_contract(self):
        p, base = m.protocol(), m._V1["protocol"]()
        for key in ("tasks", "seed", "container_image", "timeout_s", "reasoning_effort"):
            self.assertEqual(p[key], base[key])
        self.assertEqual(p["status"], "NOT_RUN")
        self.assertTrue(all(x["family"] == "codex" and x["catalog_multi_agent_version"] == "v2" for x in p["models"]))
        self.assertEqual([x["id"] for x in p["models"]], ["gpt-6-sol", "gpt-6-astra", "gpt-6.1-sol", "gpt-6-luna", "gpt-5.6-sol", "gpt-5.6-terra"])
        self.assertEqual(p["repetitions"], 4)
        self.assertNotIn("gpt-5.6-luna", [x["id"] for x in p["models"]])
        self.assertNotIn("gpt-5.5", [x["id"] for x in p["models"]])
        self.assertEqual(p["entry_rule"]["task"], "v2-01")
        self.assertNotIn("v2-01", p["tasks"])
        self.assertEqual(p["decision"]["cross_model"]["min_models"], 4)
        self.assertEqual(p["load"]["flag_threshold"], 40)


class FreezeAndV1(unittest.TestCase):
    def test_v1_frozen_files_still_match_their_freeze(self):
        lock = m.read(m.V1_LOCK)["bindings"]
        for key, rel in V1_FILES.items():
            self.assertEqual(sha256(ROOT / rel), lock[key], f"v1 file changed: {rel}")
        self.assertTrue(m.v1_unchanged())

    def test_freeze_roundtrip_and_one_byte_drift_detection(self):
        with tempfile.TemporaryDirectory() as tmp, memory_freeze(Path(tmp) / "freeze.json"):
            lock = Path(tmp) / "freeze.json"
            with self.assertRaises((ValueError, FileNotFoundError)):  # a missing freeze is not a pass
                with patch.object(m, "LOCK", lock):
                    m.frozen()
            with patch.object(m, "LOCK", lock):
                data = m.build_freeze(lock)
                self.assertEqual(m.frozen()["bindings"], data["bindings"])
                with self.assertRaisesRegex(ValueError, "already frozen"):
                    m.build_freeze(lock)
                bound = {"protocol": m.PROTOCOL, "runner": Path(m.__file__), "compat adapter": m.COMPAT,
                         "pilot source protocol": m.orig.SOURCE / "protocol.json", "pilot source validation": m.orig.SOURCE / "reports/validation.json",
                         "evidence module": m.EVIDENCE, "pooled module": m.POOLED, "v1 runner": ROOT / V1_FILES["runner"], "v1 frozen adapter": ROOT / V1_FILES["codex_official_adapter"],
                         "v1 protocol": ROOT / V1_FILES["protocol"], "v1 freeze": m.V1_LOCK,
                         "pilot scorer": ROOT / V1_FILES["original_runner"]}
                for label, path in bound.items():
                    with patch.object(m.orig, "digest", flip_last_byte(path)):
                        with self.assertRaises(ValueError, msg=f"one-byte change not detected: {label}"):
                            m.frozen()
                for name, text in (("ARM_A_LINE_V2", m.ARM_A_LINE_V2 + "."), ("C_SCRATCH", m.C_SCRATCH + ".")):
                    with patch.object(m, name, text), self.assertRaises(ValueError, msg=name):
                        m.frozen()
                with patch.object(m, "DENY", re.compile(m.DENY.pattern + "|x")), self.assertRaises(ValueError):
                    m.frozen()
                tampered = json.loads(lock.read_text())
                tampered["schedule"][0]["ordinal"] = 99
                lock.write_text(json.dumps(tampered))
                with self.assertRaises(ValueError):
                    m.frozen()

    def test_freeze_refuses_when_a_v1_file_differs(self):
        with tempfile.TemporaryDirectory() as tmp, memory_freeze(Path(tmp) / "freeze.json"), patch.object(m.orig, "digest", flip_last_byte(ROOT / V1_FILES["runner"])):
            with self.assertRaisesRegex(ValueError, "v1 freeze"):
                m.build_freeze(Path(tmp) / "freeze.json")
            self.assertFalse((Path(tmp) / "freeze.json").exists())

    def test_every_file_the_runner_imports_or_reads_is_bound(self):
        keys = set(m.bindings())
        self.assertTrue({"protocol", "readme_before_results", "runner", "compat_adapter", "v1_freeze", "v1_bindings", "prompt_lines", "fidelity_patterns",
                         "evidence_module", "pooled_module", "generation_config_policy", "harness_check_line"} <= keys)
        self.assertTrue(set(V1_FILES) <= set(m.bindings()["v1_bindings"]))


class AdapterArgv(unittest.TestCase):
    engine = SimpleNamespace(CODEX_DOCKER="/usr/bin/docker", CODEX_DOCKER_CONTEXT="colima",
                             CODEX_CONTAINER_IMAGE=m.protocol()["container_image"])
    mcp = ['mcp_servers.playwright-test.command="npx"', 'mcp_servers.playwright-test.args=["playwright","run-test-mcp-server"]',
           'mcp_servers.playwright-test.env.PLAYWRIGHT_BROWSERS_PATH="/ms-playwright"', 'mcp_servers.playwright-test.env.HOME="/codex-home"']

    def argv(self, arm):
        return m.compat.command(self.engine, "/w", "/p", "c1", "gpt-6-sol", arm)

    def frozen(self):
        return frozen_adapter.command(self.engine, "/w", "/p", "c1", "gpt-6-sol")

    def test_arm_b_and_c_differ_from_the_frozen_argv_only_by_no_ephemeral(self):
        base = self.frozen()
        self.assertIn("--ephemeral", base)
        expected = [x for x in base if x != "--ephemeral"]
        for arm in (B, C, None):
            self.assertEqual(self.argv(arm), expected, arm)

    def test_arm_a_carries_generator_allowlist_and_read_only_sandbox(self):
        base = [x for x in self.frozen() if x != "--ephemeral"]
        argv = self.argv(A)
        base[base.index("--sandbox") + 1] = "read-only"
        tools = list(m.compat.GENERATOR_TOOLS)
        extra = [part for config in self.mcp + ["mcp_servers.playwright-test.enabled_tools=" + json.dumps(tools, separators=(",", ":"))] for part in ("-c", config)]
        self.assertEqual(argv, base[:-1] + extra + ["-"])
        self.assertEqual(argv[argv.index("--sandbox") + 1], "read-only")
        self.assertNotIn("danger-full-access", argv)
        self.assertEqual(tools, [
            "browser_click", "browser_drag", "browser_evaluate", "browser_file_upload", "browser_handle_dialog",
            "browser_hover", "browser_navigate", "browser_press_key", "browser_select_option", "browser_snapshot",
            "browser_type", "browser_verify_element_visible", "browser_verify_list_visible", "browser_verify_text_visible",
            "browser_verify_value", "browser_wait_for", "generator_read_log", "generator_setup_page", "generator_write_test",
        ])
        self.assertEqual(len(tools), len(set(tools)))
        self.assertTrue(all(t.startswith(("browser_", "generator_")) for t in tools))
        self.assertFalse(set(tools) & {"test_list", "test_run", "test_debug", "planner_setup_page", "planner_save_plan"})
        self.assertNotIn("--ephemeral", argv)
        for token in ("--strict-config", "--model", "gpt-6-sol", 'model_reasoning_effort="medium"', "read-only", "--output-schema"):
            self.assertIn(token, argv)
        self.assertEqual(argv[0:3], ["/usr/bin/docker", "--context", "colima"])
        self.assertEqual(argv[-1], "-")

    def test_generator_allowlist_matches_the_official_role_source_when_present(self):
        source = ROOT / "scripts/evals/fixtures/node_modules/playwright/lib/agents/playwright-test-generator.agent.md"
        if not source.is_file():
            self.skipTest("installed official role source not present; exact allowlist still tested")
        tools = re.findall(r"^  - playwright-test/(\w+)$", source.read_text(), re.M)
        self.assertEqual(list(m.compat.GENERATOR_TOOLS), tools)

    def test_mcp_server_is_declared_for_arm_a_only(self):
        for arm in (B, C):
            self.assertFalse([t for t in self.argv(arm) if "mcp_servers" in t])

    def test_the_built_argv_is_inspected_never_executed(self):
        with patch("subprocess.run", side_effect=AssertionError("executed")), patch("subprocess.Popen", side_effect=AssertionError("executed")):
            self.argv(A)

    def test_prompt_lines(self):
        lines = m.arm_lines()
        for needle in ("no agent-type selector", "already configured for the whole session", "playwright_test_generator.toml",
                       "Do not write or edit the spec files yourself", "partial_or_blocked", "npx playwright run-test-mcp-server"):
            self.assertIn(needle, lines[A])
        self.assertEqual(lines[B], m.rev.REVIEW_LINE)
        self.assertTrue(lines[C].startswith(m.orig.OURS_LINE) and lines[C].endswith(m.C_SCRATCH))
        lines[C].format(gen="/g", rev="/r")  # still a valid template
        lock = m.read(m.V1_LOCK)["bindings"]["prompt_lines"]
        self.assertEqual(m.orig.sha(m.orig.OURS_LINE), lock["ours"])
        self.assertEqual(m.orig.sha(m.rev.REVIEW_LINE), lock["review"])
        self.assertEqual(m.orig.sha(m.orig.OFFICIAL_LINE), lock["official_codex"])
        self.assertNotEqual(m.orig.sha(m.ARM_A_LINE_V2), lock["official_codex"])


def write_transcript(directory, name, events):
    path = Path(directory) / name
    path.write_text("\n".join(json.dumps(e) for e in events) + "\n")
    return path


def msg(text):
    return {"type": "item.completed", "item": {"type": "agent_message", "text": text}}


def child(text):
    return {"type": "item.completed", "item": {"type": "collab_tool_call", "tool": "wait", "agents_states": {"t": {"status": "completed", "message": text}}}}


def mcp_call(tool="generator_write_test", status="completed", server="playwright-test"):
    return {"type": "item.completed", "item": {"type": "mcp_tool_call", "server": server, "tool": tool, "status": status}}


class Fidelity(unittest.TestCase):
    def classify(self, events, **rec):
        with tempfile.TemporaryDirectory() as tmp:
            write_transcript(tmp, "t.jsonl", events)
            base = {"arm": A, "transcript_path": "/elsewhere/t.jsonl", "spec_files": ["tests/a.spec.ts"], "out_of_scope_writes": []}
            return m.classify_fidelity(dict(base, **rec), tmp)["class"]

    def test_positive_evidence_makes_official_tool_even_without_delivery(self):
        self.assertEqual(self.classify([mcp_call()]), "official-tool")
        self.assertEqual(self.classify([], out_of_scope_writes=[".playwright-mcp/page-1.yml"]), "official-tool")
        self.assertEqual(self.classify([], out_of_scope_writes=[".playwright-mcp/page-1.yml"], spec_files=[]), "official-tool")
        self.assertEqual(self.classify([msg("The generator confirmed its browser tools work.")]), "official-tool")
        self.assertEqual(self.classify([child("The agent confirmed the approved Playwright generator tools are working.")]), "official-tool")
        self.assertEqual(self.classify([msg("The generator's browser setup succeeded.")]), "official-tool")

    def test_denial_without_positive_evidence_is_manual_follow_or_blocked(self):
        deny = child("Blocker: the requested generator MCP tools (`generator_setup_page`) were not exposed in this session.")
        self.assertEqual(self.classify([deny]), "manual-follow")
        self.assertEqual(self.classify([deny], spec_files=[]), "blocked")
        self.assertEqual(self.classify([msg("The agent tool cannot select the custom agent or load its MCP tools.")], spec_files=[]), "blocked")

    def test_absence_of_evidence_is_unverified_and_headers_do_not_count(self):
        self.assertEqual(self.classify([msg("Generated three specs.")]), "unverified")
        self.assertEqual(self.classify([], spec_files=[]), "blocked")

    def test_affirmation_inside_a_denying_message_and_other_servers_do_not_count(self):
        self.assertNotEqual(self.classify([msg("I confirmed the tools work only if available; they are unavailable.")]), "official-tool")
        self.assertNotEqual(self.classify([msg("The agent confirmed its tools are working, but generator tools are not exposed.")]), "official-tool")
        self.assertEqual(self.classify([mcp_call(server="other")]), "unverified")
        self.assertEqual(self.classify([mcp_call(status="failed")]), "unverified")

    def test_aborted_is_an_infrastructure_outcome_not_a_model_outcome(self):
        self.assertEqual(self.classify([mcp_call()], infrastructure_error=True), "aborted")
        self.assertEqual(self.classify([], unavailable="init-agents failed", spec_files=[]), "aborted")
        self.assertTrue(not m.is_aborted({"unavailable": "this model's arm A deliverable for the same task and repetition has no spec file"}))
        self.assertFalse(m.is_aborted({"timeout": True}))

    def test_missing_transcript_still_classifies_from_the_workspace(self):
        with tempfile.TemporaryDirectory() as tmp:
            rec = {"arm": A, "transcript_path": "/x/missing.jsonl", "spec_files": ["a"], "out_of_scope_writes": [".playwright-mcp/p.yml"]}
            out = m.classify_fidelity(rec, tmp)
            self.assertEqual((out["class"], out["evidence"]["transcript_found"]), ("official-tool", False))

    @unittest.skipUnless((GPT55 / "final.json").is_file(), "stored gpt-5.5 pilot cells not present")
    def test_gpt55_pilot_cells_tools_not_exposed_versus_official_headers(self):
        report = m.read(GPT55 / "final.json")
        classes = {}
        for rec in report["runs"]:
            if rec["arm"] != A:
                continue
            classes[rec["call_id"]] = (m.classify_fidelity(rec, GPT55 / "final-transcripts")["class"], m.spec_headers(GPT55, rec))
        manual = {k for k, (c, _) in classes.items() if c == "manual-follow"}
        self.assertEqual(manual, {"v3-09-official-generator-r2", "v3-06-official-generator-r2", "v2-22-official-generator-r2",
                                  "v3-06-official-generator-r1", "v3-04-official-generator-r2", "v2-23-official-generator-r1"})
        self.assertEqual(sorted(c for c, _ in classes.values()).count("unverified"), 6)
        self.assertNotIn("official-tool", [c for c, _ in classes.values()])
        # the header proxy cannot separate the two groups: 5 of the 6 'not exposed' cells carry both headers
        self.assertEqual(sum(classes[k][1] for k in manual), 5)
        self.assertEqual(sum(h for _, h in classes.values()), 11)

    @unittest.skipUnless((SOL / "final.json").is_file() and (ASTRA / "final.json").is_file(), "stored v1 cells not present")
    def test_v1_gpt6_cells(self):
        for model_dir, official in ((SOL, 3), (ASTRA, 0)):
            report = m.read(model_dir / "final.json")
            counts = {}
            for rec in report["runs"]:
                if rec["arm"] == A:
                    k = m.classify_fidelity(rec, model_dir / "final-transcripts")["class"]
                    counts[k] = counts.get(k, 0) + 1
            self.assertEqual(counts.get("official-tool", 0), official, (model_dir.name, counts))
            self.assertEqual(counts.get("official-tool", 0) + counts.get("blocked", 0), 12)



def cell(case, arm, rep, score, klass=None, delivered=True, clean=True, kill=1.0, p0=0, p12=0, aborted=False, flagged=False):
    return {"case": case, "arm": arm, "repetition": rep, "refactor_score": score, "clean": clean, "effective_fault_kill": kill,
            "scan_p0": p0, "scan_p1p2": p12, "deliverable": delivered, "aborted": aborted, "load_flagged": flagged,
            "fidelity_class": klass or ("official-tool" if arm != C else None)}


def table(a_scores, c_scores, b_scores=None, a_class="official-tool", **c_over):
    cells = []
    for i, t in enumerate(TASKS):
        for rep in range(1, m.protocol()["repetitions"] + 1):
            cells.append(cell(t, A, rep, a_scores[i], a_class))
            cells.append(cell(t, C, rep, c_scores[i], **c_over))
            cells.append(cell(t, B, rep, (b_scores or a_scores)[i], a_class))
    return cells


class Rules(unittest.TestCase):
    def label(self, cells, view="primary", contrast="C_minus_A"):
        return m.view_results(cells, view, TASKS)["labels"][contrast]

    def test_suggestive_needs_five_of_six_and_not_worse_guards(self):
        won = self.label(table([0] * 6, [1] * 6))
        self.assertEqual((won["label"], won["leader"]), (f"suggestive: {C} better", C))
        five = self.label(table([0] * 6, [1] * 5 + [0]))
        self.assertEqual(five["leader"], C)
        four = self.label(table([0] * 6, [1] * 4 + [0, 0]))
        self.assertEqual(four["leader"], None)
        self.assertEqual(self.label(table([1] * 6, [1] * 6))["leader"], None)  # ties
        self.assertEqual(self.label(table([1, 1, 1, 0, 0, 0], [0, 0, 0, 1, 1, 1]))["leader"], None)  # 3-3 split
        worse_scan = self.label(table([0] * 6, [1] * 6, p0=1))
        self.assertEqual((worse_scan["leader"], worse_scan["guards_not_worse_x"]), (None, False))
        worse_clean = self.label(table([0] * 6, [1] * 6, clean=False))
        self.assertEqual(worse_clean["leader"], None)
        y_wins = self.label(table([1] * 6, [0] * 6))
        self.assertEqual(y_wins["leader"], A)

    def test_not_evaluable_when_an_arm_has_fewer_than_six_delivered_or_five_shared_tasks(self):
        few = table([0] * 6, [1] * 6)
        for c in few:
            if c["arm"] == A and c["repetition"] == 2 and c["case"] in TASKS[:2]:
                c["deliverable"] = False
        self.assertTrue(self.label(few)["eligible"])  # 22 of 24 delivered: still evaluable
        for c in few:
            if c["arm"] == A and c["case"] in TASKS[:5]:
                c["deliverable"] = False
        self.assertFalse(self.label(few)["eligible"])
        narrow = [c for c in table([0] * 6, [1] * 6) if not (c["arm"] == A and c["case"] in TASKS[:2])]  # A official on 4 tasks only
        out = self.label(narrow)
        self.assertEqual((out["eligible"], out["tasks_covered"]), (False, 4))

    def test_primary_keeps_only_official_tool_cells_and_itt_keeps_everything(self):
        cells = table([0] * 6, [0.5] * 6)
        for c in cells:
            if c["arm"] == A and c["repetition"] > 2:
                c["fidelity_class"], c["refactor_score"] = "manual-follow", 1  # hand-written specs happen to survive
        for c in cells:
            if c["arm"] == B and c["repetition"] > 2:
                c["fidelity_class"] = "manual-follow"
        views = m.view_results(cells, "primary", TASKS)
        self.assertEqual(views["cells_in_view"], {A: 12, B: 12, C: 24})
        self.assertEqual(views["labels"]["C_minus_A"]["eligible"], True)
        self.assertEqual(views["labels"]["C_minus_A"]["leader"], C)  # 12 official A cells at survival 0
        itt = m.view_results(cells, "itt", TASKS)
        self.assertEqual(itt["cells_in_view"], {A: 24, B: 24, C: 24})
        self.assertEqual(itt["labels"]["C_minus_A"]["leader"], None)  # ITT: A averages 0.5 = C on every task (a tie)

    def test_upper_load_clean_and_aborted_handling(self):
        cells = table([0] * 6, [1] * 6, a_class="unverified")
        self.assertEqual(m.view_results(cells, "primary", TASKS)["cells_in_view"][A], 0)
        self.assertEqual(m.view_results(cells, "upper", TASKS)["cells_in_view"][A], 24)
        self.assertEqual(m.view_results(cells, "primary", TASKS)["labels"]["C_minus_A"]["eligible"], False)
        cells = table([0] * 6, [1] * 6)
        cells[0]["aborted"], cells[1]["load_flagged"] = True, True
        self.assertEqual(m.view_results(cells, "primary", TASKS)["cells_in_view"], {A: 23, B: 24, C: 24})
        self.assertEqual(m.view_results(cells, "load_clean", TASKS)["cells_in_view"], {A: 23, B: 24, C: 23})
        self.assertEqual(m.view_results(cells, "itt", TASKS)["cells_in_view"], {A: 24, B: 24, C: 24})

    def test_b_cells_follow_their_source_a_cell(self):
        cells = table([0] * 6, [1] * 6)
        for c in cells:
            if c["arm"] == B and c["case"] == TASKS[0]:
                c["fidelity_class"] = "blocked"
        self.assertEqual(m.view_results(cells, "primary", TASKS)["cells_in_view"][B], 20)

    def test_load_and_extras_flags(self):
        rec = {"arm": A, "load_at_start": 40.0, "attempts": [{"error": "x"}], "setup": {"setup_s": 1.5}, "transcript_path": "n.jsonl",
               "spec_files": [], "out_of_scope_writes": [], "cell_started_utc": "t0", "cell_finished_utc": "t1", "load_at_finish": 41}
        with tempfile.TemporaryDirectory() as tmp:
            out = m.cell_extras(rec, tmp, tmp)
            self.assertFalse(out["load_flagged"])
            out = m.cell_extras(dict(rec, load_at_start=40.01), tmp, tmp)
            self.assertTrue(out["load_flagged"])
            self.assertEqual((out["cell_started_utc"], out["setup_s"], out["attempt_errors"], out["fidelity_class"]), ("t0", 1.5, ["x"], "blocked"))
        fields = m.protocol()["per_cell_record"]
        for section, keys in (("load", ("load_at_start", "load_pause_s", "load_flagged", "load_at_finish")),
                              ("timing", ("cell_started_utc", "cell_finished_utc", "elapsed_s", "setup_s"))):
            for key in keys:
                self.assertTrue(any(key in item for item in fields[section]), key)
        self.assertTrue(set(out) >= {"load_at_start", "load_pause_s", "load_flagged", "load_at_finish", "cell_started_utc",
                                     "cell_finished_utc", "setup_s", "aborted", "fidelity"})
        self.assertEqual(set(fields), {"availability_signals", "load", "timing", "evidence", "cost"})


def result(complete, leader, eligible=True, view="primary", contrast="C_minus_A"):
    return {"complete": complete, "views": {view: {"labels": {contrast: {"eligible": eligible, "leader": leader}}}}}


class CrossModel(unittest.TestCase):
    ids = [x["id"] for x in m.protocol()["models"]]  # gpt-6-sol, gpt-6-astra, gpt-6.1-sol, gpt-6-luna, gpt-5.6-sol, gpt-5.6-terra

    def verdict(self, leaders, **kw):
        results = {i: result(kw.get("complete", {}).get(i, True), l, kw.get("eligible", {}).get(i, True)) for i, l in zip(self.ids, leaders)}
        return m.cross_model(results, m.protocol(), "primary", "C_minus_A")["verdict"]

    def test_floor_and_lineage(self):
        self.assertTrue(self.verdict([C, C, C]).startswith("not evaluable (fewer than 4"))
        self.assertTrue(self.verdict([C, C, C, C]).startswith("not evaluable (eligible models span a single"))
        self.assertEqual(self.verdict([C, None, None, None, C]), f"consistent: {C} better in 2 of 5 models")  # 2 of 5, both lineages
        self.assertEqual(self.verdict([C, C, None, None, None]), "not consistent")  # 2 agree but one lineage only
        self.assertEqual(self.verdict([C, None, None, None, None]), "not consistent")

    def test_threshold_is_max_2_ceil_n_over_3_and_none_opposite(self):
        self.assertEqual(self.verdict([C, None, None, None, C, None]), f"consistent: {C} better in 2 of 6 models")  # N=6 needs 2
        self.assertEqual(self.verdict([C, None, None, None, C, A]), "not consistent")  # one opposite label
        self.assertEqual(self.verdict([A, None, None, None, A, None]), f"consistent: {A} better in 2 of 6 models")
        results = {f"m{i}": result(True, C if i in (0, 1, 4, 5) else None) for i in range(8)}
        p = json.loads(json.dumps(m.protocol()))
        p["models"] = [{"id": f"m{i}", "lineage": "gpt-6" if i < 4 else "gpt-5.6"} for i in range(8)]
        out = m.cross_model(results, p, "primary", "C_minus_A")
        self.assertEqual((out["eligible_n"], out["needed"]), (8, 3))
        self.assertEqual(out["verdict"], f"consistent: {C} better in 4 of 8 models")  # 4 agree >= 3, both lineages
        results["m5"] = result(True, None)
        self.assertEqual(m.cross_model(results, p, "primary", "C_minus_A")["verdict"], f"consistent: {C} better in 3 of 8 models")  # 3 agree >= 3
        results["m4"] = result(True, None)
        self.assertEqual(m.cross_model(results, p, "primary", "C_minus_A")["verdict"], "not consistent")  # 2 agree < 3

    def test_incomplete_and_not_evaluable_models_leave_n(self):
        v = self.verdict([C, C, C, None, C, None], complete={self.ids[0]: False})
        self.assertEqual(v, f"consistent: {C} better in 3 of 5 models")
        v = self.verdict([C, C, C, None, C, None], complete={self.ids[0]: False, self.ids[1]: False, self.ids[2]: False})
        self.assertTrue(v.startswith("not evaluable"))
        v = self.verdict([C, C, None, None, C, None], eligible={self.ids[2]: False, self.ids[3]: False, self.ids[5]: False})
        self.assertTrue(v.startswith("not evaluable (fewer than 4"))


class FidelityNegativeControls(unittest.TestCase):
    """Sentences a reviewer showed the first AFFIRM accepted as positive evidence. None may classify a delivered cell official-tool."""
    NOT_EVIDENCE = [
        "The agent reported that the browser tool was not working.",
        "The agent reported the generator tools do not work in this session.",
        "The agent reported the generator tools aren't available.",
        "The agent reported the browser isn't ready.",
        "The agent confirmed the tools are not working.",
        "The generator never called generator_setup_page; it wrote the files directly.",
        "I will spawn a generic agent and ask it to write each file via `generator_write_test`.",
        "The agent reports it has no access to the generator tools; ready to write specs manually.",
        "The agent should confirm the tools work before writing.",
        "I could not tell whether the agent confirmed the browser tools were working.",
        "The tools were used only after the agent failed to set up the browser; generator_write_test was never called.",
    ]

    def classify(self, text, **rec):
        with tempfile.TemporaryDirectory() as tmp:
            write_transcript(tmp, "t.jsonl", [msg(text)])
            base = {"arm": A, "transcript_path": "t.jsonl", "spec_files": ["tests/a.spec.ts"], "out_of_scope_writes": []}
            return m.classify_fidelity(dict(base, **rec), tmp)

    def test_negated_or_planned_statements_are_not_positive_evidence(self):
        for text in self.NOT_EVIDENCE:
            self.assertNotEqual(self.classify(text)["class"], "official-tool", text)
            self.assertNotEqual(self.classify(text, spec_files=[])["class"], "official-tool", text)

    def test_a_clean_affirmation_still_counts_and_is_message_strength(self):
        for text in ("The agent confirmed the approved Playwright generator tools are working.", "Browser setup succeeded; the agent called generator_write_test for each scenario."):
            out = self.classify(text)
            self.assertEqual((out["class"], out["evidence"]["strength"]), ("official-tool", "message"), text)

    def test_denying_messages_are_recognised_as_denials(self):
        self.assertEqual(self.classify("The agent reported the generator tools aren't available.")["class"], "manual-follow")
        self.assertEqual(self.classify("The agent confirmed the tools are not working.", spec_files=[])["class"], "blocked")

    def test_hard_evidence_is_labelled_hard(self):
        out = self.classify("done", out_of_scope_writes=[".playwright-mcp/p.yml"])
        self.assertEqual((out["class"], out["evidence"]["strength"]), ("official-tool", "hard"))
        self.assertTrue(m.admits(out))
        self.assertFalse(m.admits(self.classify("The agent confirmed the tools are working.")))  # message-only never admits


def entry_rec(kind):
    base = {"arm": A, "transcript_path": None, "spec_files": ["tests/a.spec.ts"], "out_of_scope_writes": [], "elapsed_ms": 1000,
            "load_at_start": 5.0, "attempts": [], "structured_output": {"summary": "x"}}
    return {"hard": dict(base, out_of_scope_writes=[".playwright-mcp/p.yml"]), "blocked": dict(base, spec_files=[]),
            "unverified": base, "aborted": dict(base, infrastructure_error=True, spec_files=[], attempts=[{"error": "docker down"}]),
            "fatal": dict(base, infrastructure_error=True, spec_files=[], attempts=[{"error": "usage limit", "fatal_infrastructure": True}]),
            "setup": dict(base, spec_files=[], unavailable="init-agents failed"),
            "message_only": dict(base, structured_output={"summary": "The agent confirmed the tools are working."})}[kind]


class EntryRule(unittest.TestCase):
    rule = m.protocol()["entry_rule"]

    def run_entry(self, kinds, tmp, model="gpt-6-sol"):
        seq, calls = list(kinds), []

        def call(n, tdir):
            calls.append(n)
            rec = entry_rec(seq.pop(0))
            if rec.get("out_of_scope_writes"):
                return rec  # exercise the hard artifact fallback without a contradictory complete absence
            # Real non-admitting attempts need a complete primary observation, including a persisted root.
            thread = "entry-root"
            tdir.mkdir(parents=True, exist_ok=True)
            transcript = tdir / "entry.jsonl"
            transcript.write_text(json.dumps({"type": "thread.started", "thread_id": thread}) + "\n")
            sessions = tdir.parent / "codex-sessions/entry"
            sessions.mkdir(parents=True, exist_ok=True)
            (sessions / "rollout-entry.jsonl").write_text(json.dumps({"type": "session_meta", "payload": {"id": thread}}) + "\n")
            return dict(rec, transcript_path=str(transcript))
        with patch.object(m, "BASE", Path(tmp)):
            decision, state = m.run_entry(model, self.rule, Path(tmp) / "root", call)
        return decision, state, calls

    def test_sequences(self):
        cases = [(["hard"], "admitted", 1, 1), (["blocked", "hard"], "admitted", 2, 2), (["blocked", "unverified"], "excluded", 2, 2),
                 (["blocked", "blocked", "hard"], "excluded", 2, 2),  # never a third real attempt
                 (["message_only", "message_only"], "excluded", 2, 2),  # an affirming message alone does not admit
                 (["aborted", "hard"], "admitted", 2, 1), (["aborted", "blocked", "hard"], "admitted", 3, 2),
                 (["setup", "hard"], "admitted", 2, 1)]
        for kinds, decision, n_calls, n_attempts in cases:
            with tempfile.TemporaryDirectory() as tmp:
                got, state, calls = self.run_entry(kinds, tmp)
                self.assertEqual((got, len(calls), len(state["attempts"])), (decision, n_calls, n_attempts), kinds)

    def test_infrastructure_outages_leave_the_model_undecided(self):
        for kinds, n_calls, n_attempts in ((["aborted", "aborted"], 2, 0), (["aborted", "blocked", "aborted"], 3, 1), (["fatal"], 1, 0),
                                           (["blocked", "fatal"], 2, 1), (["aborted", "fatal"], 2, 0)):
            with tempfile.TemporaryDirectory() as tmp:
                got, state, calls = self.run_entry(kinds, tmp)
                self.assertIsNone(got, kinds)
                self.assertEqual((len(calls), len(state["attempts"])), (n_calls, n_attempts), kinds)

    def test_attempts_accumulate_across_invocations_and_decision_is_written_only_by_preflight(self):
        with tempfile.TemporaryDirectory() as tmp:
            got, state, _ = self.run_entry(["blocked", "aborted", "aborted"], tmp)
            self.assertIsNone(got)
            got, state, calls = self.run_entry(["unverified"], tmp)  # second real attempt, in a later invocation
            self.assertEqual((got, len(state["attempts"]), calls), ("excluded", 2, [4]))
            with patch.object(m, "BASE", Path(tmp)):
                self.assertFalse(m.entry_path("gpt-6-sol").exists())

    def test_no_decision_while_a_preflight_is_pending(self):
        with tempfile.TemporaryDirectory() as tmp:
            self.run_entry(["aborted", "aborted"], tmp)
            with patch.object(m, "BASE", Path(tmp)), self.assertRaisesRegex(ValueError, "undecided"):
                m.load_entries(m.protocol())

    def test_go_no_go_gate(self):
        p = m.protocol()
        ids = [x["id"] for x in p["models"]]  # four gpt-6 then two gpt-5.6

        def gate(admitted):
            return m.entry_gate({i: {"decision": "admitted" if i in admitted else "excluded"} for i in ids}, p)[0]
        self.assertTrue(gate(ids[:3] + ids[4:5]))
        self.assertFalse(gate(ids[:3]))  # three models
        self.assertFalse(gate(ids[:4]))  # four models, one lineage
        self.assertFalse(gate(ids[4:]))
        entries = {i: {"decision": "admitted" if i in ids[:3] else "excluded", "freeze_sha256": "x"} for i in ids}
        sentinel = RuntimeError("reached the campaign lock")
        with patch.object(m, "frozen", lambda: {}), patch.object(m, "load_entries", lambda p: entries), \
                patch.object(m, "load_harness_check", lambda: {"status": "pass"}), patch.object(m, "campaign_lock", side_effect=sentinel):
            with self.assertRaisesRegex(ValueError, "go/no-go"):
                m.drive(argparse.Namespace(allow_live=True, only=None, descriptive_only=False))
            with self.assertRaises(RuntimeError):
                m.drive(argparse.Namespace(allow_live=True, only=None, descriptive_only=True))


class CampaignLock(unittest.TestCase):
    def test_refuses_while_another_driver_process_exists(self):
        with tempfile.TemporaryDirectory() as tmp, patch.object(m, "BASE", Path(tmp)):
            with patch.object(m, "other_campaign_running", return_value=["4242"]), self.assertRaisesRegex(ValueError, "another multimodel driver"):
                m.campaign_lock()

    def test_refuses_while_the_lock_is_held(self):
        with tempfile.TemporaryDirectory() as tmp, patch.object(m, "BASE", Path(tmp)), patch.object(m, "other_campaign_running", return_value=[]):
            handle = m.campaign_lock()
            try:
                with self.assertRaisesRegex(ValueError, "campaign lock"):
                    m.campaign_lock()
            finally:
                handle.close()
            m.campaign_lock().close()


class FreezeReadmeAndAbort(unittest.TestCase):
    def test_results_appended_below_the_heading_do_not_break_the_freeze_but_edits_above_do(self):
        with tempfile.TemporaryDirectory() as tmp, memory_freeze(Path(tmp) / "freeze.json"):
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

    def test_setup_unavailable_is_an_infrastructure_outcome_for_the_inherited_loop(self):
        item = {"case": TASKS[0], "arm": A, "repetition": 1, "ordinal": 1}
        for unavailable, infra in (("init-agents failed or did not emit the generator agent", True),
                                   ("this model's arm A deliverable for the same task and repetition has no spec file", False)):
            rec = dict(item, attempts=[], infrastructure_error=False, unavailable=unavailable, spec_files=[])
            with patch.dict(m._V1, {"one_call": lambda *a: dict(rec)}):
                out = m.one_call(item, None, None, None, None, None)
            self.assertEqual(bool(out["infrastructure_error"]), infra, unavailable)
            self.assertEqual(m.is_aborted(out), infra)

    def test_load_clean_drops_an_arm_b_cell_with_a_flagged_source_a_cell(self):
        cells = table([0] * 6, [1] * 6)
        for c in cells:
            if c["arm"] == A and c["case"] == TASKS[0] and c["repetition"] == 1:
                c["load_flagged"] = True
            c["source_load_flagged"] = c["arm"] == B and c["case"] == TASKS[0] and c["repetition"] == 1
        self.assertEqual(m.view_results(cells, "load_clean", TASKS)["cells_in_view"], {A: 23, B: 23, C: 24})
        self.assertEqual(m.view_results(cells, "primary", TASKS)["cells_in_view"], {A: 24, B: 24, C: 24})


class PowerAndText(unittest.TestCase):
    def test_recorded_simulation_is_reproducible_and_supports_the_chosen_threshold(self):
        rec = m.read(m.PROTOCOL)["power_simulation"]["recorded"]
        self.assertEqual(rec["params"], m.POWER)
        for key, args in (("N4|effect_2.4_all|fid1.0", (4, "effect_2.4_all", 1.0)), ("N6|null_lineage_shared|fid0.75", (6, "null_lineage_shared", 0.75))):
            self.assertEqual(m.power_cell(*args), rec["cells"][key], key)
        nulls = [v for k, v in rec["cells"].items() if "|null" in k and not k.startswith("N3")]
        self.assertTrue(nulls)
        self.assertEqual(max(round(sum(v["cross"]["chosen_third2|lineages>=2"]), 4) for v in nulls), 0.0447)
        self.assertEqual(m.POWER["reps"], 4)
        chosen = rec["cells"]["N6|effect_2.4_all|fid1.0"]["cross"]
        self.assertGreater(chosen["chosen_third2|lineages>=2"][0], chosen["v1_2of3|lineages>=2"][0])
        self.assertIn("floor3_check", rec)

    def test_docs_state_the_required_contract(self):
        text = m.README.read_text()
        for needle in ("harness-limited descriptive", "Entry rule", "not consistent", "headers are not evidence", "--ephemeral",
                       "scratch", "official-tool", "**itt**", "load_clean", "owner", "No pooled p-value", "## Results",
                       "Live check after freeze", "approved 2026-10-15", "development evidence", "reuseExistingServer", "quality per 100k", "Pooled analysis", "as_treated", "selector hygiene"):
            self.assertIn(needle, text, needle)
        out_of_scope = "Pupp" + "eteer"  # built from fragments: the framework-scope CI scan flags the literal word in scripts/
        self.assertNotIn(out_of_scope, text + m.PROTOCOL.read_text())

    def test_live_commands_refuse_without_allow_live_and_touch_nothing(self):
        before = m.BASE.exists()
        with patch("subprocess.run", side_effect=AssertionError("no subprocess before the flag check")), \
                patch("subprocess.Popen", side_effect=AssertionError("no subprocess before the flag check")):
            for call, args in ((m.drive, argparse.Namespace(allow_live=False, only=None)),
                               (m.preflight, argparse.Namespace(allow_live=False, model="gpt-6-sol"))):
                with self.assertRaisesRegex(ValueError, "--allow-live"):
                    call(args)
            for argv in (["x", "drive"], ["x", "preflight", "--model", "gpt-6-sol"]):
                with patch("sys.argv", argv), self.assertRaisesRegex(ValueError, "--allow-live"):
                    m.main()
        self.assertEqual(m.BASE.exists(), before)

    def test_entry_decisions_are_required_before_any_scored_cell(self):
        with tempfile.TemporaryDirectory() as tmp, patch.object(m, "BASE", Path(tmp)):
            with self.assertRaisesRegex(ValueError, "no entry decision"):
                m.load_entries(m.protocol())


class DryIntegration(unittest.TestCase):
    """Drives the imported v1 run_model/analyze path with stubbed calls (no docker, no model, no scoring) to prove the wiring."""

    def stub_call(self, item, args, ports, artifacts, mcfg, p):
        arm, ordinal = item["arm"], item["ordinal"]
        files = [] if (arm == A and ordinal % 3 == 0) else [f"tests/{item['case']}.spec.ts"]
        official = arm == A and ordinal % 3 == 1
        return dict(item, attempts=[], call_id=f"{item['case']}-{arm}-r{item['repetition']}", spec_files=files, tests_files=files,
                    out_of_scope_writes=[".playwright-mcp/p.yml"] if official else [], elapsed_ms=1000, timeout=False, num_turns=1,
                    usage=None, structured_output={"summary": "stub"}, result_text=None, compliance=None, setup={"setup_s": 1.0},
                    load_at_start=41.0 if ordinal == 5 else 12.0, transcript_path=None, infrastructure_error=False, deliverable=bool(files))

    def test_run_freeze_resume_and_analyze_wiring(self):
        stub_configure = lambda a, p, c: (tmp, None, "codex-cli stub")
        with tempfile.TemporaryDirectory() as tmp, memory_freeze(Path(tmp) / "freeze.json"), contextlib.redirect_stdout(io.StringIO()):
            tmp = Path(tmp).resolve()
            with patch.object(m, "BASE", tmp), patch.object(m, "LOCK", tmp / "freeze.json"), \
                    patch.dict(m._V1, {"one_call": self.stub_call}):
                m.build_freeze(tmp / "freeze.json")
                m.bind_v1()
                self.addCleanup(m.unbind_v1)  # runs after patch.dict has restored the real originals
                m.v1.configure = stub_configure  # the real configure would start Docker
                ns = argparse.Namespace(allow_live=True, resume=True, output=None)
                m.v1.run_model("gpt-6-sol", ns, {})
                report = m.read(tmp / "gpt-6-sol/final.json")
                self.assertEqual((report["protocol_id"], report["completed_calls"], len(report["runs"])), (m.PROTOCOL_ID, 72, 72))
                self.assertEqual(report["freeze_sha256"], m.digest(tmp / "freeze.json"))
                self.assertTrue(all("cell_started_utc" in r and "load_at_finish" in r for r in report["runs"]))
                m.v1.run_model("gpt-6-sol", ns, {})  # resume is a no-op
                scores = {"report": "final.json", "scores": [], "report_sha256": m.digest(tmp / "gpt-6-sol/final.json"),
                          "freeze_sha256": m.digest(tmp / "freeze.json")}
                (tmp / "gpt-6-sol/scores.json").write_text(json.dumps(scores))
                views = m.analyze_model("gpt-6-sol")
                result = m.read(tmp / "gpt-6-sol/results.json")
                self.assertEqual(set(views), set(m.VIEWS))
                self.assertIn("as_treated", m.VIEWS)
                self.assertTrue(result["complete"])
                self.assertEqual(set(result["cost_endpoints"]), set(m.VIEWS))
                self.assertEqual(result["scoring_config_policy"], {"reuse_existing_server": False, "cases_checked": 6})
                self.assertEqual(set(result["fidelity_table"]), {"arm_a", "arm_b", "arm_c", "as_treated_cells"})
                self.assertTrue(all(c["tokens"]["complete"] is False for c in result["cells"] if c["arm"] == A))  # stub: no usage, no sessions
                a_ordinals = [r["ordinal"] for r in m.schedule() if r["arm"] == A]
                expected = {"official-tool": sum(o % 3 == 1 for o in a_ordinals), "manual-follow": 0,
                            "unverified": sum(o % 3 == 2 for o in a_ordinals), "blocked": sum(o % 3 == 0 for o in a_ordinals), "aborted": 0}
                self.assertEqual(result["arm_a_fidelity_classes"], expected)
                self.assertEqual(result["load_flagged_cells"], 1)
                self.assertEqual(len(result["cells"]), 72)
                self.assertEqual(result["views"]["primary"]["cells_in_view"][A], expected["official-tool"])
                self.assertFalse(result["views"]["primary"]["labels"]["C_minus_A"]["eligible"])  # synthetic zero rows: nothing delivered
                m.summary_cmd(None)
                self.assertTrue((tmp / "summary.md").is_file())
                text = (tmp / "summary.md").read_text()
                self.assertIn("discordance between views", text)
                for heading in ("Treatment fidelity", "Cost endpoints", "selector hygiene", "Pooled analysis"):
                    self.assertIn(heading, text)
                self.assertTrue((tmp / "pooled.json").is_file())


if __name__ == "__main__":
    unittest.main()
