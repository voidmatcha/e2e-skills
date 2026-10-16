#!/usr/bin/env python3
"""Synthetic offline checks for generator-oss-eval-v1. Apache-2.0.

No model, container, network, process census, port, or held-out material is used.
All writable fixtures live in a temporary directory, never a campaign cache.
"""
import contextlib
import hashlib
import importlib.util
import io
import json
import sys
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

ROOT = Path(__file__).resolve().parents[2]


def load(name, relative):
    spec = importlib.util.spec_from_file_location(name, ROOT / relative)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


m = load("generator_oss_eval_under_test", "scripts/evals/run-generator-oss-eval-v1.py")
z = load("generator_oss_zeppelin_under_test", "scripts/evals/generator_oss_zeppelin.py")


@contextlib.contextmanager
def memory_freeze(path):
    """Virtual freeze I/O exercises the command without freezing any checkout."""
    path = Path(path)
    state = {"text": None}
    originals = {key: getattr(Path, key) for key in
                 ("open", "exists", "is_file", "read_text", "read_bytes", "write_text")}

    class Buffer(io.StringIO):
        def close(self):
            if not self.closed:
                state["text"] = self.getvalue()
            super().close()

    def virtual_open(candidate, mode="r", *args, **kwargs):
        if candidate != path:
            return originals["open"](candidate, mode, *args, **kwargs)
        if "x" in mode and state["text"] is not None:
            raise FileExistsError(path)
        if any(flag in mode for flag in ("x", "w")):
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
        for key in ("exists", "is_file"):
            stack.enter_context(patch.object(Path, key, lambda candidate, method=key:
                state["text"] is not None if candidate == path else originals[method](candidate)))
        stack.enter_context(patch.object(Path, "read_text", contents))
        stack.enter_context(patch.object(Path, "read_bytes", lambda candidate:
            contents(candidate).encode() if candidate == path else originals["read_bytes"](candidate)))
        stack.enter_context(patch.object(Path, "write_text", write))
        yield state


class OfflineCase(unittest.TestCase):
    def setUp(self):
        self.stack = contextlib.ExitStack()
        self.addCleanup(self.stack.close)
        for target in ("subprocess.run", "subprocess.Popen", "urllib.request.urlopen", "socket.socket"):
            self.stack.enter_context(patch(target, side_effect=AssertionError("offline tripwire: " + target)))
        self.tmp = Path(self.stack.enter_context(tempfile.TemporaryDirectory())).resolve()
        original_open = Path.open
        forbidden = {"sealed-eval", "zep-about-modal", "zep-home-links"}
        def guarded_open(path, *args, **kwargs):
            resolved = Path(path).resolve()
            if forbidden.intersection(resolved.parts) and not resolved.is_relative_to(self.tmp):
                self.fail("held-out material read outside synthetic fixture")
            return original_open(path, *args, **kwargs)
        self.stack.enter_context(patch.object(Path, "open", guarded_open))


class Schedule(OfflineCase):
    def test_all_three_arms_two_tasks_six_repetitions(self):
        p = m.protocol()
        tasks = p["tasks"]
        arms = (m.ARM_A, m.ARM_B, m.ARM_C)
        rows = m.schedule()
        self.assertEqual(tasks, ["zep-sidebar", "zep-note-rename"])
        self.assertEqual(p["repetitions"], 6)
        self.assertEqual(len(rows), 36)
        self.assertEqual({(r["case"], r["arm"], r["repetition"]) for r in rows},
                         {(task, arm, rep) for task in tasks for arm in arms for rep in range(1, 7)})
        self.assertEqual([r["ordinal"] for r in rows], list(range(1, 37)))
        self.assertEqual(rows, m.schedule())
        source = {(r["case"], r["repetition"]): r["ordinal"] for r in rows if r["arm"] == m.ARM_A}
        for row in rows:
            if row["arm"] == m.ARM_B:
                self.assertGreater(row["ordinal"], source[row["case"], row["repetition"]])
        self.assertTrue(all(r["arm"] != m.ARM_B for r in rows[:24]))
        self.assertTrue(all(r["arm"] == m.ARM_B for r in rows[24:]))

    def test_roster_is_six_catalog_v2_models_and_216_cells(self):
        p = m.protocol()
        models = [row["id"] for row in p["models"]]
        self.assertEqual(models, ["gpt-6-sol", "gpt-6-astra", "gpt-6.1-sol", "gpt-6-luna", "gpt-5.6-sol", "gpt-5.6-terra"])
        self.assertEqual(len(models) * len(m.schedule()), 216)
        self.assertNotIn("gpt-5.5", models)

    def test_external_task_schedule_uses_only_names(self):
        rows = m.schedule(tasks=["synthetic-alpha", "synthetic-beta"])
        self.assertEqual(len(rows), 36)
        self.assertEqual({row["case"] for row in rows}, {"synthetic-alpha", "synthetic-beta"})


class Freeze(OfflineCase):
    def test_roundtrip_one_byte_binding_drift_and_schedule_tamper(self):
        lock = self.tmp / "freeze.json"
        bound = self.tmp / "synthetic-bound.txt"
        bound.write_bytes(b"synthetic evidence\n")
        inputs = (self.tmp / "pool", self.tmp / "loop.py", self.tmp / "dists", self.tmp / "source")
        def bindings(*args, **kwargs):
            return {"synthetic": hashlib.sha256(bound.read_bytes()).hexdigest()}
        with memory_freeze(lock), patch.object(m, "bindings", bindings), patch.object(m, "LOCK", lock):
            with self.assertRaises((ValueError, FileNotFoundError)):
                m.frozen(*inputs)
            frozen = m.build_freeze(lock, *inputs)
            self.assertEqual(m.frozen(*inputs)["bindings"], frozen["bindings"])
            with self.assertRaises((ValueError, FileExistsError)):
                m.build_freeze(lock, *inputs)
            original = bound.read_bytes()
            bound.write_bytes(original[:-1] + bytes([original[-1] ^ 1]))
            with self.assertRaises(ValueError):
                m.frozen(*inputs)
            bound.write_bytes(original)
            tampered = json.loads(lock.read_text())
            tampered["schedule"][0]["ordinal"] = 999
            lock.write_text(json.dumps(tampered))
            with self.assertRaises(ValueError):
                m.frozen(*inputs)
        self.assertFalse(lock.exists())

    def test_dev_binding_selection_never_discovers_pool_root(self):
        visited = []
        def synthetic_tree(path):
            path = Path(path)
            visited.append(path)
            self.assertIn(path.name, m.DEV_TASKS)
            return {"scope.md": "synthetic-digest"}
        pool = self.tmp / "pool"
        with patch.object(m, "tree", side_effect=synthetic_tree):
            result = m.task_bindings(pool)
        self.assertEqual(visited, [pool / "tasks" / name for name in m.DEV_TASKS])
        self.assertEqual(set(result), set(m.DEV_TASKS))

    def test_freeze_records_one_canonical_external_campaign_output(self):
        lock = self.tmp / "freeze.json"
        inputs = (self.tmp / "pool", self.tmp / "loop.py", self.tmp / "dists", self.tmp / "source")
        output = self.tmp / "campaign"
        output.mkdir()
        (output / "_scorer-calibration.json").write_text("{}")
        with memory_freeze(lock), patch.object(m, "validate_calibration"), patch.object(m, "bindings", return_value={"synthetic": "digest"}):
            data = m.build_freeze(lock, *inputs, campaign_output=output)
            self.assertEqual(data["campaign_output"], str(output.resolve()))
            self.assertEqual(m.frozen(*inputs, lock=lock)["campaign_output"], str(output.resolve()))
        self.assertFalse(lock.exists())


class SharedZeppelinOwnership(OfflineCase):
    def server_fixture(self):
        dist = self.tmp / "dists/synthetic--D1"
        dist.mkdir(parents=True, exist_ok=True)
        (dist / "index.html").write_text("<html>synthetic</html>")
        loop = SimpleNamespace(ZEP_DISTS=dist.parent, ZEP_SRC=self.tmp / "source", BENCH=self.tmp / "loop")
        return z.OwnedVariantServer(loop, dist.name, z.PORT)

    def test_occupied_port_refuses_before_spawning_without_signalling(self):
        server = self.server_fixture()
        probe = MagicMock()
        probe.__enter__.return_value.bind.side_effect = OSError("synthetic occupied port")
        with patch.object(z.socket, "socket", return_value=probe), \
             patch.object(z.subprocess, "Popen") as spawn, \
             patch.object(z.urllib.request, "urlopen") as request:
            with self.assertRaisesRegex(ValueError, "occupied.*untouched"):
                server.__enter__()
            spawn.assert_not_called()
            request.assert_not_called()

    def test_dead_owned_child_cannot_accept_unrelated_html(self):
        server = self.server_fixture()
        child = MagicMock()
        child.poll.return_value = 1
        with patch.object(z.socket, "socket", return_value=MagicMock()), \
             patch.object(z.subprocess, "Popen", return_value=child), \
             patch.object(z.urllib.request, "urlopen") as request:
            with self.assertRaisesRegex(RuntimeError, "child exited"):
                server.__enter__()
            request.assert_not_called()
            child.terminate.assert_not_called()
            child.kill.assert_not_called()
            child.wait.assert_called_once()

    def test_readiness_requires_fresh_token_and_exact_variant_identity(self):
        for mismatch in ("token", "variant", "dist", "html"):
            with self.subTest(mismatch=mismatch):
                server = self.server_fixture()
                child, response = MagicMock(), MagicMock()
                child.poll.return_value = None
                payload = dict(server.identity, **{mismatch: "wrong"})
                response.__enter__.return_value.status = 200
                response.__enter__.return_value.read.return_value = (
                    b"<html>another server</html>" if mismatch == "html" else json.dumps(payload).encode())
                with patch.object(z.socket, "socket", return_value=MagicMock()), \
                     patch.object(z.subprocess, "Popen", return_value=child), \
                     patch.object(z.urllib.request, "urlopen", return_value=response), \
                     patch.object(z.time, "sleep"):
                    with self.assertRaisesRegex(RuntimeError, "identity was not confirmed"):
                        server.__enter__()
                    child.terminate.assert_called_once()

    def test_correct_identity_accepts_only_living_owned_child_and_cleans_it(self):
        server = self.server_fixture()
        child, response = MagicMock(), MagicMock()
        child.poll.return_value = None
        response.__enter__.return_value.status = 200
        response.__enter__.return_value.read.return_value = json.dumps(server.identity).encode()
        with patch.object(z.socket, "socket", return_value=MagicMock()), \
             patch.object(z.subprocess, "Popen", return_value=child) as spawn, \
             patch.object(z.urllib.request, "urlopen", return_value=response):
            with server:
                child.terminate.assert_not_called()
                self.assertEqual(json.loads(spawn.call_args.kwargs["env"]["E2E_OSS_SERVER_IDENTITY"]), server.identity)
                self.assertIn(str(server.dist), spawn.call_args.args[0])
            child.terminate.assert_called_once()
            child.wait.assert_called_once()

    def test_child_dying_during_identity_request_is_refused(self):
        server = self.server_fixture()
        child, response = MagicMock(), MagicMock()
        child.poll.side_effect = [None, 1, 1]
        response.__enter__.return_value.status = 200
        response.__enter__.return_value.read.return_value = json.dumps(server.identity).encode()
        with patch.object(z.socket, "socket", return_value=MagicMock()), \
             patch.object(z.subprocess, "Popen", return_value=child), \
             patch.object(z.urllib.request, "urlopen", return_value=response):
            with self.assertRaisesRegex(RuntimeError, "child exited during"):
                server.__enter__()
            child.terminate.assert_not_called()

    def test_nested_campaign_refuses_and_does_not_remove_owner_lock(self):
        lock = self.tmp / "zeppelin.lock"
        with z.CampaignLock(lock, process_probe=lambda: [], campaign_id="synthetic"):
            self.assertTrue(lock.exists())
            with self.assertRaisesRegex(ValueError, "lock already exists"):
                with z.CampaignLock(lock, process_probe=lambda: []):
                    self.fail("second campaign acquired lock")
            self.assertTrue(lock.exists())
        self.assertFalse(lock.exists())
        with z.CampaignLock(lock, process_probe=lambda: []):
            self.assertTrue(lock.exists())

    def test_other_driver_probe_refuses_and_cleans_its_own_lock(self):
        lock = self.tmp / "zeppelin.lock"
        with self.assertRaisesRegex(ValueError, "another.*driver process"):
            with z.CampaignLock(lock, process_probe=lambda: [12345]):
                self.fail("driver conflict allowed")
        self.assertFalse(lock.exists())

    def test_stale_lock_refuses_without_querying_or_stealing(self):
        lock = self.tmp / "zeppelin.lock"
        lock.write_text("synthetic stale owner\n")
        def forbidden_probe():
            self.fail("existing lock must refuse before process probe")
        with self.assertRaises(ValueError):
            with z.CampaignLock(lock, process_probe=forbidden_probe):
                self.fail("stale lock acquired")
        self.assertEqual(lock.read_text(), "synthetic stale owner\n")

    def test_namespaces_are_cell_scoped_and_cleanup_is_exact(self):
        folder = z.namespace("synthetic-campaign", "model:arm:task:1")
        self.assertEqual(folder, z.namespace("synthetic-campaign", "model:arm:task:1"))
        self.assertNotEqual(folder, z.namespace("synthetic-campaign", "model:arm:task:2"))
        self.assertNotEqual(folder, z.namespace("other-campaign", "model:arm:task:1"))
        notes = [{"id": "owned", "path": folder + "/note"},
                 {"id": "other", "path": folder + "-other/note"},
                 {"id": "ordinary", "path": "ordinary/note"}]
        deleted = []
        def api(method, endpoint):
            if method == "GET":
                return {"body": list(notes)}
            note_id = endpoint.rsplit("/", 1)[-1]
            deleted.append(note_id)
            notes[:] = [note for note in notes if note["id"] != note_id]
            return {"status": "OK"}
        self.assertEqual(z.clean_namespace(api, folder), 1)
        self.assertEqual(deleted, ["owned"])
        self.assertEqual({note["id"] for note in notes}, {"other", "ordinary"})
        with self.assertRaises(ValueError):
            z.clean_namespace(api, "ordinary")

    def test_failed_cleanup_is_fatal(self):
        folder = z.namespace("synthetic", "cell")
        def api(method, endpoint):
            return {"body": [{"id": "owned", "path": folder + "/note"}]} if method == "GET" else {"status": "ERROR"}
        with self.assertRaises(RuntimeError):
            z.clean_namespace(api, folder)

    def test_phase_guard_and_finally_cleanup_without_server(self):
        notes = []
        deleted = []
        def api(method, endpoint):
            if method == "GET":
                return {"body": list(notes)}
            deleted.append(endpoint.rsplit("/", 1)[-1])
            notes.clear()
            return {"status": "OK"}
        loop = SimpleNamespace(zep_api=api, engine=SimpleNamespace())
        runtime = z.ZeppelinRuntime(self.tmp / "loop.py", self.tmp / "pool", self.tmp / "dists",
            self.tmp / "source", self.tmp / "modules", lock_path=self.tmp / "zeppelin.lock",
            process_probe=lambda: [], loop=loop)
        with self.assertRaisesRegex(ValueError, "campaign lock"):
            with runtime._phase("generation", "cell"):
                self.fail("phase without lock")
        with runtime.campaign():
            with self.assertRaisesRegex(RuntimeError, "synthetic call failure"):
                with runtime._phase("generation", "cell") as (_, folder):
                    notes.append({"id": "generated-note", "path": folder + "/note"})
                    with self.assertRaisesRegex(ValueError, "overlapping"):
                        with runtime._phase("scoring", "other-cell"):
                            self.fail("scoring overlapped generation")
                    raise RuntimeError("synthetic call failure")
            self.assertIsNone(runtime.phase)
            self.assertEqual(deleted, ["generated-note"])
            self.assertFalse(notes)
            with runtime._phase("scoring", "cell"):
                self.assertEqual(runtime.phase, "scoring")
        self.assertFalse(runtime.lock_path.exists())

    def test_new_cell_note_escape_is_recorded_cleaned_and_phase_continues(self):
        notes, deleted = [], []
        def api(method, endpoint):
            if method == "GET":
                return {"body": list(notes)}
            note_id = endpoint.rsplit("/", 1)[-1]
            deleted.append(note_id)
            notes[:] = [note for note in notes if note["id"] != note_id]
            return {"status": "OK"}
        loop = SimpleNamespace(zep_api=api, engine=SimpleNamespace())
        runtime = z.ZeppelinRuntime(self.tmp / "loop.py", self.tmp / "pool", self.tmp / "dists",
            self.tmp / "source", self.tmp / "modules", lock_path=self.tmp / "zeppelin.lock",
            process_probe=lambda: [], loop=loop)
        with runtime.campaign():
            with runtime._phase("generation", "synthetic-cell") as (_, folder):
                notes.extend([{"id": "owned", "path": folder + "/note"},
                              {"id": "foreign", "path": "outside/note"}])
            self.assertIsNone(runtime.phase)
        self.assertEqual(deleted, ["foreign", "owned"])
        self.assertEqual(notes, [])
        self.assertEqual(runtime.note_isolation_violations[0]["kind"], "new_note_outside_namespace")

    def test_preexisting_note_changes_are_isolation_violations(self):
        folder = z.namespace("synthetic", "cell")
        before = {"old": "ordinary/note", "changed": "ordinary/another"}
        after = {"changed": "ordinary/renamed", "owned": folder + "/new-note"}
        violations = z.isolation_violations(before, after, folder)
        self.assertEqual({row["kind"] for row in violations},
                         {"preexisting_note_removed", "preexisting_note_path_changed"})

    def test_late_driver_refuses_next_phase(self):
        drivers = []
        runtime = z.ZeppelinRuntime(self.tmp / "loop.py", self.tmp / "pool", self.tmp / "dists",
            self.tmp / "source", self.tmp / "modules", lock_path=self.tmp / "zeppelin.lock",
            process_probe=lambda: list(drivers), loop=SimpleNamespace())
        with runtime.campaign():
            drivers.append(12345)
            with self.assertRaisesRegex(ValueError, "another.*driver appeared"):
                with runtime._phase("generation", "cell"):
                    self.fail("phase allowed after late driver appeared")

    def test_runtime_inherits_only_its_own_open_campaign_lock(self):
        lock_path = self.tmp / "zeppelin.lock"
        runtime = z.ZeppelinRuntime(self.tmp / "loop.py", self.tmp / "pool", self.tmp / "dists",
            self.tmp / "source", self.tmp / "modules", lock_path=lock_path, process_probe=lambda: [])
        with self.assertRaisesRegex(ValueError, "open owned"):
            runtime.inherit_lock(z.CampaignLock(lock_path, process_probe=lambda: []))
        with z.CampaignLock(self.tmp / "other.lock", process_probe=lambda: []) as other:
            with self.assertRaisesRegex(ValueError, "different.*lock path"):
                runtime.inherit_lock(other)
        with z.CampaignLock(lock_path, process_probe=lambda: []) as owner:
            runtime.inherit_lock(owner)
            self.assertIs(runtime.lock, owner)
            with self.assertRaisesRegex(ValueError, "already has"):
                runtime.inherit_lock(owner)


class SyntheticScoring(OfflineCase):
    def measurements(self):
        return ([{"ok": True, "passed": 1, "failed": 0, "errors": []} for _ in range(3)],
                {f"D{i}": {"ok": False, "passed": 0, "failed": 1, "errors": []} for i in range(1, 6)},
                {"ok": True, "passed": 1, "failed": 0, "errors": []})

    def test_clean_fault_kill_and_refactor_survival(self):
        result = z.scoring_result(*self.measurements())
        self.assertTrue(result["clean"])
        self.assertEqual(result["effective_fault_kill"], 1.0)
        self.assertEqual(result["refactor_score"], 1.0)
        self.assertTrue(all(run["killed"] for run in result["faults"].values()))

    def test_clean_failure_gates_fault_kill_and_refactor(self):
        clean, faults, refactor = self.measurements()
        clean[1]["ok"] = False
        result = z.scoring_result(clean, faults, refactor)
        self.assertFalse(result["clean"])
        self.assertEqual(result["kill_rate"], 1.0)
        self.assertEqual(result["effective_fault_kill"], 0.0)
        self.assertEqual(result["refactor_score"], 0.0)
        self.assertIsNone(result["refactor_pass"])

    def test_error_and_surviving_defect_do_not_count_as_kills(self):
        clean, faults, refactor = self.measurements()
        faults["D1"]["errors"] = ["synthetic setup error"]
        faults["D2"].update(ok=True, failed=0, passed=1)
        refactor["ok"] = False
        result = z.scoring_result(clean, faults, refactor)
        self.assertEqual(result["effective_fault_kill"], 0.6)
        self.assertFalse(result["faults"]["D1"]["killed"])
        self.assertFalse(result["faults"]["D2"]["killed"])
        self.assertEqual(result["refactor_score"], 0.0)

    def test_incomplete_measurements_refuse(self):
        clean, faults, refactor = self.measurements()
        with self.assertRaises(ValueError):
            z.scoring_result(clean[:2], faults, refactor)
        with self.assertRaises(ValueError):
            z.scoring_result(clean, {key: value for key, value in faults.items() if key != "D5"}, refactor)

    def test_attributed_effective_kill_preserves_candidate_rate(self):
        clean, faults, refactor = self.measurements()
        for fault in faults.values():
            fault["valid_detection"] = True
        faults["D1"]["valid_detection"] = False
        result = m.score_measurements(clean, faults, refactor, {"p0": 0, "p1p2": 2})
        self.assertEqual(result["candidate_kill_rate"], 1.0)
        self.assertEqual(result["effective_fault_kill"], 0.8)
        self.assertTrue(result["fault_attribution_complete"])
        self.assertEqual(result["refactor_score"], 1.0)
        self.assertEqual(result["scan"], {"p0": 0, "p1p2": 2})

    def test_unadjudicated_candidate_kills_remain_unknown(self):
        clean, faults, refactor = self.measurements()
        result = m.score_measurements(clean, faults, refactor)
        self.assertEqual(result["candidate_kill_rate"], 1.0)
        self.assertIsNone(result["effective_fault_kill"])
        self.assertIsNone(result["kill_rate"])
        self.assertFalse(result["fault_attribution_complete"])
        self.assertFalse(any(fault["killed"] for fault in result["faults"].values()))
        clean[0]["ok"] = False
        self.assertEqual(m.score_measurements(clean, faults, refactor)["effective_fault_kill"], 0.0)

    def test_non_candidate_faults_do_not_require_attribution(self):
        clean, faults, refactor = self.measurements()
        for fault in faults.values():
            fault.update(ok=True, passed=1, failed=0)
        result = m.score_measurements(clean, faults, refactor)
        self.assertEqual(result["effective_fault_kill"], 0.0)
        self.assertTrue(result["fault_attribution_complete"])

    def test_zero_tests_never_supply_clean_or_refactor_survival(self):
        clean, faults, refactor = self.measurements()
        for fault in faults.values():
            fault["valid_detection"] = True
        clean[0]["passed"] = 0
        result = m.score_measurements(clean, faults, refactor)
        self.assertFalse(result["clean"])
        self.assertEqual(result["effective_fault_kill"], 0.0)
        self.assertEqual(result["refactor_score"], 0.0)
        clean[0]["passed"] = 1
        refactor["passed"] = 0
        result = m.score_measurements(clean, faults, refactor)
        self.assertEqual(result["refactor_score"], 0.0)
        self.assertFalse(result["refactor_pass"])

    def test_imported_runtime_scores_only_fixed_variants_and_cleans_every_run(self):
        case = "zep-sidebar"
        pool = self.tmp / "pool"
        patches = pool / "tasks" / case / "patches"
        patches.mkdir(parents=True)
        for defect in range(1, 6):
            (patches / f"D{defect}-synthetic.patch").write_text("synthetic defect fixture\n")
        (patches / "R1-markup-refactor.patch").write_text("synthetic refactor fixture\n")
        tests_src = self.tmp / "generated-tests"
        tests_src.mkdir()
        generated_spec = "// synthetic generated fixture\nconst base = 'http://host.docker.internal:14210';\n"
        (tests_src / "synthetic.spec.ts").write_text(generated_spec)
        variants, active, notes, deleted = [], [], [], []
        runtime_holder = {}

        @contextlib.contextmanager
        def server(variant, port):
            self.assertFalse(active)
            self.assertEqual(port, 14210)
            variants.append(variant)
            active.append(variant)
            try:
                yield
            finally:
                active.pop()

        def api(method, endpoint):
            if method == "GET":
                return {"body": list(notes)}
            deleted.append(endpoint.rsplit("/", 1)[-1])
            notes.clear()
            return {"status": "OK"}

        def stage(work, base):
            project = work / "project"
            project.mkdir()
            (project / "tests").mkdir()
            (project / "README.md").write_text("Notes must use E2E_LOOP/synthetic.\n")
            return project

        def run_playwright(project, specs, timeout, env_extra):
            self.assertEqual(runtime_holder["runtime"].phase, "scoring")
            self.assertEqual(specs, ["tests/synthetic.spec.ts"])
            self.assertEqual(timeout, 600)
            self.assertEqual((project / "tests/synthetic.spec.ts").read_text(),
                             generated_spec.replace("host.docker.internal:14210", "127.0.0.1:14210"))
            self.assertNotIn("E2E_LOOP/", (project / "README.md").read_text())
            folder = env_extra["E2E_NOTE_FOLDER"]
            notes.append({"id": "run-note", "path": folder + "/note"})
            failure = "--D" in active[-1]
            return {"ok": not failure, "failed": int(failure), "passed": int(not failure), "errors": []}

        engine = SimpleNamespace(wait_for_load=lambda _: None, run_playwright=run_playwright)
        loop = SimpleNamespace(zep_api=api, zep_stage=stage, ZepServer=server, engine=engine)
        runtime = z.ZeppelinRuntime(self.tmp / "loop.py", pool, self.tmp / "dists", self.tmp / "source",
            self.tmp / "modules", lock_path=self.tmp / "zeppelin.lock", process_probe=lambda: [], loop=loop)
        runtime_holder["runtime"] = runtime
        with runtime.campaign(), patch.object(z.os, "getloadavg", return_value=(0.0, 0.0, 0.0)), \
             patch.object(z, "OwnedVariantServer", side_effect=lambda loop, variant, port: server(variant, port)), \
             patch.object(z, "run_playwright_records", side_effect=run_playwright):
            result = runtime.evaluate(case, tests_src, ["tests/synthetic.spec.ts"], "synthetic-cell")
        self.assertEqual(variants, ["clean"] * 3 + [f"{case}--D{i}-synthetic" for i in range(1, 6)] +
            [f"{case}--R1-markup-refactor"])
        self.assertEqual(result["effective_fault_kill"], 1.0)
        self.assertEqual(result["refactor_score"], 1.0)
        self.assertEqual(len(deleted), 9)
        self.assertFalse(notes)
        self.assertFalse(active)
        self.assertEqual((tests_src / "synthetic.spec.ts").read_text(), generated_spec)


class ScoringAttempts(OfflineCase):
    def fixture(self):
        directory = self.tmp / "model"
        directory.mkdir()
        records = [dict(row, call_id="synthetic-" + str(row["ordinal"]), spec_files=[])
                   for row in m.schedule()[:2]]
        (directory / "final.json").write_text(json.dumps({"model": m.compat.MODELS[0], "runs": records}))
        (directory / "scores.json").write_text(json.dumps({"scores": [{"refactor_score": 1}], "status": "COMPLETED"}))
        return directory, records

    def test_cleanup_failure_preserves_partial_scores_errors_and_blocks_stale_analysis(self):
        directory, records = self.fixture()
        records[1]["spec_files"] = ["tests/synthetic.spec.ts"]
        (directory / "final.json").write_text(json.dumps({"model": m.compat.MODELS[0], "runs": records}))
        def fail(*unused):
            try:
                raise RuntimeError("synthetic note isolation failure")
            finally:
                raise RuntimeError("synthetic cleanup failure")
        rt = SimpleNamespace(evaluate=fail, note_isolation_violations=[{"kind": "new_note_outside_namespace"}])
        with patch.object(m, "report_check"), patch.object(m, "digest", return_value="synthetic-digest"):
            with self.assertRaisesRegex(RuntimeError, "cleanup"):
                m.score_directory(directory, rt, m.DEV_TASKS)
            attempt = m.read(directory / "scoring-attempt.json")
            self.assertEqual(attempt["status"], "INCOMPLETE")
            self.assertEqual(len(attempt["scores"]), 1)
            self.assertEqual(attempt["active_cell"]["call_id"], records[1]["call_id"])
            self.assertEqual([e["message"] for e in attempt["errors"]],
                             ["synthetic cleanup failure", "synthetic note isolation failure"])
            self.assertEqual(attempt["note_isolation_violations"], rt.note_isolation_violations)
            self.assertEqual(m.read(directory / "scores.json"), attempt)
            self.assertEqual(m.read(next((directory / "scoring-attempts").glob("*.json"))), attempt)
            with self.assertRaisesRegex(ValueError, "incomplete"):
                m.analyze_directory(directory, m.DEV_TASKS)
            with self.assertRaisesRegex(ValueError, "incomplete"):
                m.adjudicate_directory(directory, {})

    def test_new_failed_attempt_supersedes_success_and_retains_success_history(self):
        directory, _ = self.fixture()
        rt = SimpleNamespace(note_isolation_violations=[])
        with patch.object(m, "report_check"), patch.object(m, "digest", return_value="synthetic-digest"):
            m.score_directory(directory, rt, m.DEV_TASKS)
            previous = m.completed_scores(directory)
        with patch.object(m, "report_check", side_effect=ValueError("synthetic invalid report")), \
             patch.object(m, "digest", return_value="synthetic-digest"):
            with self.assertRaisesRegex(ValueError, "invalid report"):
                m.score_directory(directory, rt, m.DEV_TASKS)
        histories = [m.read(p) for p in (directory / "scoring-attempts").glob("*.json")]
        self.assertEqual({r["status"] for r in histories}, {"COMPLETED"})
        self.assertIn(previous, histories)
        self.assertEqual(m.completed_scores(directory), previous)

    def test_interrupted_attempt_and_started_marker_refuse(self):
        directory, _ = self.fixture()
        rt = SimpleNamespace(note_isolation_violations=[])
        with patch.object(m, "score_rows", side_effect=KeyboardInterrupt()), \
             patch.object(m, "report_check"), patch.object(m, "digest", return_value="synthetic-digest"):
            with self.assertRaises(KeyboardInterrupt):
                m.score_directory(directory, rt, m.DEV_TASKS)
        self.assertEqual(m.read(directory / "scoring-attempt.json")["errors"][0]["type"], "KeyboardInterrupt")
        m.write(directory / "scoring-attempt.json", {"status": "STARTED", "attempt_id": "synthetic-new-attempt"})
        with self.assertRaisesRegex(ValueError, "incomplete"):
            m.completed_scores(directory)

    def test_interruption_before_initial_history_write_invalidates_old_success(self):
        directory, _ = self.fixture()
        rt = SimpleNamespace(note_isolation_violations=[])
        with patch.object(m, "report_check"), patch.object(m, "digest", return_value="synthetic-digest"):
            m.score_directory(directory, rt, m.DEV_TASKS)
        previous = m.completed_scores(directory)
        real_write = m.write
        def interrupt_history(path, data, **kwargs):
            if "scoring-attempts" in Path(path).parts:
                raise KeyboardInterrupt()
            real_write(path, data, **kwargs)
        with patch.object(m, "write", side_effect=interrupt_history), \
             patch.object(m, "score_rows", side_effect=AssertionError("scoring before attempt persistence")):
            with self.assertRaises(KeyboardInterrupt):
                m.score_directory(directory, rt, m.DEV_TASKS)
        self.assertEqual(m.read(directory / "scores.json"), previous)
        self.assertEqual(m.read(directory / "scoring-attempt.json")["status"], "STARTED")
        with self.assertRaisesRegex(ValueError, "incomplete"):
            m.completed_scores(directory)

    def test_summary_rechecks_scores_even_when_success_results_remain(self):
        directory, _ = self.fixture()
        output = self.tmp / "campaign"
        model = m.compat.MODELS[0]
        (output / model).mkdir(parents=True)
        for f in directory.iterdir():
            if f.is_file():
                (output / model / f.name).write_bytes(f.read_bytes())
        (output / model / "results.json").write_text('{"complete": true}')
        for name in m.compat.MODELS:
            m.write(output / "_entry" / (name + ".json"), {"decision": "admitted" if name == model else "excluded",
                    "reason": "synthetic hard evidence" if name == model else "synthetic exclusion", "freeze_sha256": "synthetic-digest"})
        m.write(output / model / "scoring-attempt.json", {"status": "INCOMPLETE"})
        with patch.object(m, "digest", return_value="synthetic-digest"), patch.object(m, "report_check"):
            with self.assertRaisesRegex(ValueError, "incomplete"):
                m.summary(output, m.DEV_TASKS)
        self.assertFalse((output / "summary.json").exists())


class ExternalVault(OfflineCase):
    def fixture(self):
        vault = self.tmp / "synthetic-vault"
        vault.mkdir()
        (vault / "manifest.json").write_text(json.dumps({"schema_version": 1, "tasks": list(m.EVAL_NAMES)}))
        for task_name in m.EVAL_NAMES:
            task = vault / "tasks" / task_name
            patches = task / "patches"
            patches.mkdir(parents=True)
            (task / "scope.md").write_text("Synthetic vault scope; contains no real held-out content.\n")
            for variant in [f"D{i}" for i in range(1, 6)] + ["R1-markup-refactor"]:
                (patches / (variant + ".patch")).write_text("Synthetic patch bytes.\n")
                dist = vault / "dists" / (task_name + "--" + variant)
                dist.mkdir(parents=True)
                (dist / "index.html").write_text("<html>Synthetic variant</html>\n")
        clean = vault / "dists/clean"
        clean.mkdir()
        (clean / "index.html").write_text("<html>Synthetic clean app</html>\n")
        vault.chmod(0o700)
        for item in vault.rglob("*"):
            item.chmod(0o700 if item.is_dir() else 0o600)
        return vault

    def test_current_repository_path_refuses_before_manifest_read(self):
        with self.assertRaisesRegex(ValueError, "repository|outside repo"):
            m.validate_vault(ROOT / "synthetic-no-such-vault")

    def test_other_repository_and_worktree_paths_refuse(self):
        for git_entry in ("directory", "file"):
            repo = self.tmp / git_entry
            repo.mkdir()
            if git_entry == "directory":
                (repo / ".git").mkdir()
            else:
                (repo / ".git").write_text("gitdir: synthetic-worktree-metadata\n")
            with self.assertRaisesRegex(ValueError, "repository"):
                m.validate_vault(repo / "nested/vault", repo_roots=[self.tmp / "unrelated-root"])

    def test_symlink_alias_refuses(self):
        vault = self.fixture()
        alias = self.tmp / "alias"
        alias.symlink_to(vault, target_is_directory=True)
        with self.assertRaisesRegex(ValueError, "symlink"):
            m.validate_vault(alias)

    def test_synthetic_vault_validates_and_byte_change_changes_commitment(self):
        vault = self.fixture()
        first = m.validate_vault(vault)
        self.assertEqual(first["tasks"], list(m.EVAL_NAMES))
        self.assertRegex(first["commitment"], r"^[0-9a-f]{64}$")
        target = vault / "tasks" / m.EVAL_NAMES[0] / "scope.md"
        data = target.read_bytes()
        target.write_bytes(data[:-1] + bytes([data[-1] ^ 1]))
        self.assertNotEqual(first["commitment"], m.validate_vault(vault)["commitment"])

    def test_missing_variant_and_changed_manifest_refuse(self):
        vault = self.fixture()
        (vault / "manifest.json").write_text(json.dumps({"schema_version": 1, "tasks": ["synthetic-unknown"]}))
        with self.assertRaises(ValueError):
            m.validate_vault(vault)
        (vault / "manifest.json").write_text(json.dumps({"schema_version": 1, "tasks": list(m.EVAL_NAMES)}))
        import shutil
        shutil.rmtree(vault / "dists" / (m.EVAL_NAMES[0] + "--D5"))
        with self.assertRaises(ValueError):
            m.validate_vault(vault)

    def test_wrong_defect_identifiers_refuse_before_execution(self):
        vault = self.fixture()
        patches = vault / "tasks" / m.EVAL_NAMES[0] / "patches"
        (patches / "D5.patch").rename(patches / "D9.patch")
        with self.assertRaises(ValueError):
            m.validate_vault(vault)


class CommandRefusals(OfflineCase):
    def args(self, command):
        result = [command, "--pool", str(self.tmp / "pool"), "--loop-runner", str(self.tmp / "loop.py"),
                  "--dists", str(self.tmp / "dists"), "--source", str(self.tmp / "source"),
                  "--output", str(self.tmp / "output")]
        if command == "final-eval":
            result.extend(["--vault", str(self.tmp / "vault")])
        return result

    def test_all_live_commands_require_allow_live_before_freeze_or_setup(self):
        with patch.object(m, "frozen", side_effect=AssertionError("freeze checked before live opt-in")), \
             patch.object(m, "validate_vault", side_effect=AssertionError("vault opened before live opt-in")):
            for command in ("preflight", "drive", "score", "final-eval"):
                with self.subTest(command=command), contextlib.redirect_stderr(io.StringIO()) as err:
                    self.assertEqual(m.main(self.args(command)), 2)
                    self.assertIn("requires --allow-live", err.getvalue())
        self.assertFalse((self.tmp / "output").exists())

    def test_allow_live_alone_cannot_bypass_missing_freeze(self):
        with patch.object(m, "LOCK", self.tmp / "nonexistent-freeze.json"):
            for command in ("preflight", "drive", "score", "final-eval"):
                with self.subTest(command=command), contextlib.redirect_stderr(io.StringIO()) as err:
                    self.assertEqual(m.main(self.args(command) + ["--allow-live"]), 2)
                    self.assertIn("not frozen", err.getvalue())
        self.assertFalse((self.tmp / "output").exists())

    def test_live_commands_refuse_unset_or_different_frozen_campaign_output_before_setup(self):
        for frozen_output in (None, str(self.tmp / "different-campaign")):
            with patch.object(m, "frozen", return_value={"campaign_output": frozen_output}), \
                 patch.object(m, "CampaignLock", side_effect=AssertionError("lock acquisition before campaign-output guard")), \
                 patch.object(m, "validate_vault", side_effect=AssertionError("vault read before campaign-output guard")):
                for command in ("preflight", "drive", "score", "final-eval"):
                    with self.subTest(command=command, frozen_output=frozen_output), \
                         contextlib.redirect_stderr(io.StringIO()) as err:
                        self.assertEqual(m.main(self.args(command) + ["--allow-live"]), 2)
                        self.assertRegex(err.getvalue(), "campaign.*output|output.*campaign")
        self.assertFalse((self.tmp / "output").exists())

    def test_final_eval_spends_marker_before_vault_read_and_refuses_second_attempt(self):
        output = self.tmp / "output"
        output.mkdir()
        (output / "summary.json").write_text("{\"synthetic\":true}\n")
        model = m.compat.MODELS[0]
        entries = {name: {"decision": "admitted" if name == model else "excluded"} for name in m.compat.MODELS}
        vault = self.tmp / "vault"
        vault.mkdir(mode=0o700)
        reads = []
        def reject_vault(path, **kwargs):
            self.assertTrue((output / "FINAL_EVAL_ATTEMPT.json").exists())
            reads.append(str(path))
            raise ValueError("synthetic vault invalid")
        with patch.object(m, "require_live", return_value={"vault_sha256": "a" * 64, "campaign_output": str(output),
                     "eval_results_root": str(self.tmp / "eval-results"), "spent_ledger_root": str(self.tmp / "spent"),
                     "bindings": {"committed_skills": {"skill": {"SKILL.md": "b" * 64}}}}), \
             patch.object(m, "CampaignLock", return_value=contextlib.nullcontext()), \
             patch.object(m, "codex_context", return_value=contextlib.nullcontext()), \
             patch.object(m.v2, "load_harness_check", return_value={"status": "pass"}), \
             patch.object(m.v2, "load_entries", return_value=entries), \
             patch.object(m, "runtime", return_value=SimpleNamespace(inherit_lock=lambda _: None)), \
             patch.object(m, "digest", return_value="a" * 64), \
             patch.object(m, "summary", return_value={"models": {model: {"complete": True}}}), \
             patch.object(m, "validate_vault", side_effect=reject_vault), \
             patch.object(m, "drive_models", side_effect=AssertionError("model call attempted")):
            with contextlib.redirect_stderr(io.StringIO()):
                self.assertEqual(m.main(self.args("final-eval") + ["--allow-live"]), 2)
                self.assertEqual(m.main(self.args("final-eval") + ["--allow-live"]), 2)
        self.assertEqual(len(reads), 1)
        self.assertEqual(json.loads((output / "FINAL_EVAL_ATTEMPT.json").read_text())["status"], "STARTED_ONCE")


class SyntheticAnalysis(OfflineCase):
    def extras(self, rec, *unused):
        tokens = {name: 0 for name in m.evidence.TOKEN_FIELDS}
        tokens.update(complete=True, uncached_input=100, output=20, child_uncached_input=40, child_output=10,
                      processed=120, total=120)
        return dict(aborted=False, load_flagged=False, tokens=tokens, rollouts=None, compliance_raw={},
                    fidelity_class="official-tool", fidelity={"evidence": {"primary_signal": "synthetic"}},
                    treatment={"treated": True, "treated_core": True, "available": True, "steps": {},
                               "reviewer_skill_read": True, "scanner": True},
                    generation_config={"stages": 1, "reuse_existing_server": True,
                        "config_sha256_port_normalized": ["synthetic-config"],
                        "scoring_config_sha256_port_normalized": ["synthetic-config"]})

    def fixture(self):
        records = [dict(row, call_id=f"synthetic-{row['ordinal']}", elapsed_ms=1000,
                        spec_files=["tests/synthetic.spec.ts"]) for row in m.schedule()]
        scores = [dict(row, clean=True, refactor_score=float(row["arm"] == m.ARM_C),
                       effective_fault_kill=0.6, primary=0.6, kill_rate=0.6, scan={"p0": 0, "p1p2": 1},
                       references_renamed_selector=row["arm"] != m.ARM_C, dynamic_selector_hint=False)
                  for row in m.schedule()]
        return records, scores

    def test_never_launched_reviewer_retains_source_cost_and_elapsed(self):
        item = dict(case=m.DEV_TASKS[0], arm=m.ARM_B, repetition=1, ordinal=3)
        with patch.object(m.shutil, "disk_usage", return_value=SimpleNamespace(free=2**50)), \
             patch.object(m.engine, "wait_for_load", side_effect=AssertionError("model setup reached")):
            row = m.generate(item, SimpleNamespace(), SimpleNamespace(), "synthetic-model", self.tmp / "skipped", m.DEV_TASKS)
        self.assertFalse(row["model_call_launched"])
        self.assertTrue(m.evidence.proven_skipped_reviewer(row))
        tokens = m.v2.tokens_for_record(row, self.tmp)
        self.assertTrue(tokens["complete"])
        self.assertEqual(tokens["total"], 0)
        source_tokens = {name: 0 for name in m.evidence.TOKEN_FIELDS}
        source_tokens.update(complete=True, uncached_input=100, processed=100, total=100)
        cells = [dict(case=item["case"], repetition=1, arm=m.ARM_A, tokens=source_tokens, elapsed_s=10),
                 dict(case=item["case"], repetition=1, arm=m.ARM_B, tokens=tokens, elapsed_s=0, refactor_score=0)]
        m.v2.add_pipeline(cells)
        cost = m.pooled.cost_endpoint([cells[1]])
        self.assertTrue(cells[1]["pipeline"]["tokens"]["complete"])
        self.assertEqual(cost["tokens"]["total"], 100)
        self.assertEqual(cost["elapsed_s_mean"], 10)

    def test_metrics_fidelity_child_costs_and_b_pipeline_are_preserved(self):
        records, scores = self.fixture()
        with patch.object(m.v2, "cell_extras", side_effect=self.extras):
            result = m.analyze_cells(records, scores, m.compat.MODELS[0], self.tmp, m.DEV_TASKS)
        self.assertTrue(result["complete"])
        self.assertEqual(result["evidence_label"], "development evidence")
        self.assertTrue(result["no_directional_verdict"])
        self.assertEqual(set(result["views"]), set(m.v2.VIEWS))
        primary = result["views"]["primary"]["arms"]
        self.assertEqual(primary[m.ARM_C]["metrics"]["refactor_score"], 1.0)
        self.assertEqual(primary[m.ARM_A]["metrics"]["effective_fault_kill"], 0.6)
        self.assertEqual(primary[m.ARM_C]["selector_hygiene"]["clean_conditional_survival"], 1.0)
        self.assertEqual(primary[m.ARM_A]["cost"]["tokens"]["child_output"], 120)
        self.assertEqual(primary[m.ARM_B]["cost"]["tokens"]["child_output"], 240)
        self.assertEqual(primary[m.ARM_B]["cost"]["elapsed_s_mean"], 2.0)
        self.assertEqual(result["fidelity_table"]["arm_a"]["official_tool"], 12)
        self.assertEqual(result["fidelity_table"]["arm_b"]["treated"], 12)
        for contrast in result["views"]["primary"]["contrasts"].values():
            self.assertEqual(set(contrast), set(m.DEV_TASKS))

    def test_unpaired_scoring_and_missing_source_a_refuse(self):
        records, scores = self.fixture()
        with patch.object(m.v2, "cell_extras", side_effect=self.extras):
            with self.assertRaisesRegex(ValueError, "incomplete"):
                m.analyze_cells(records, scores[:-1], m.compat.MODELS[0], self.tmp, m.DEV_TASKS)
            remove = next(index for index, row in enumerate(records) if row["arm"] == m.ARM_A)
            records.pop(remove)
            scores.pop(remove)
            with self.assertRaisesRegex(ValueError, "source A"):
                m.analyze_cells(records, scores, m.compat.MODELS[0], self.tmp, m.DEV_TASKS)

    def test_duplicate_record_and_score_identities_refuse(self):
        records, scores = self.fixture()
        with patch.object(m.v2, "cell_extras", side_effect=self.extras):
            with self.assertRaisesRegex(ValueError, "duplicate"):
                m.analyze_cells(records + [dict(records[0])], scores, m.compat.MODELS[0], self.tmp, m.DEV_TASKS)
            with self.assertRaisesRegex(ValueError, "duplicate"):
                m.analyze_cells(records, scores + [dict(scores[0])], m.compat.MODELS[0], self.tmp, m.DEV_TASKS)

    def test_summary_prints_frozen_roster_reasons_pooled_contrasts_and_missing_models(self):
        records, scores = self.fixture()
        model, missing, excluded = m.compat.MODELS[:3]
        with patch.object(m.v2, "cell_extras", side_effect=self.extras):
            result = m.analyze_cells(records, scores, model, self.tmp, m.DEV_TASKS)
        for name in m.compat.MODELS:
            m.write(self.tmp / "_entry" / (name + ".json"), {"decision": "admitted" if name in (model, missing) else "excluded",
                    "reason": "synthetic hard evidence" if name in (model, missing) else "synthetic no official tools",
                    "freeze_sha256": "synthetic-digest"})
        for name in (model, excluded):
            m.write(self.tmp / name / "results.json", {"synthetic": True})
        cfg = m.protocol()
        cfg["pooled_analysis"]["cluster_bootstrap"]["replicates"] = 20
        with patch.object(m, "protocol", return_value=cfg), patch.object(m, "digest", return_value="synthetic-digest"), \
             patch.object(m, "analyze_directory", return_value=result) as analyze, contextlib.redirect_stdout(io.StringIO()):
            summary = m.summary(self.tmp, m.DEV_TASKS)
        analyze.assert_called_once_with(self.tmp / model, m.DEV_TASKS)
        self.assertEqual(summary["missing_or_incomplete_models"], [missing])
        self.assertIn(excluded, summary["excluded_by_admission"])
        text = (self.tmp / "summary.txt").read_text()
        self.assertIn(missing + " roster decision=admitted reason=synthetic hard evidence results=missing results", text)
        self.assertIn(excluded + " roster decision=excluded reason=synthetic no official tools results=excluded by admission", text)
        for key, report in summary["pooled"].items():
            self.assertIn("pooled " + key + "=" + json.dumps(report, sort_keys=True), text)
            for field in ("sign_flip", "cluster_bootstrap", "model_effects", "task_profile", "lineage_means", "leave_one_model_out"):
                self.assertIn(field, report)

    def test_summary_requires_matching_frozen_roster_decisions(self):
        m.write(self.tmp / "_entry" / (m.compat.MODELS[0] + ".json"), {"decision": "admitted", "freeze_sha256": "wrong"})
        with patch.object(m, "digest", return_value="synthetic-digest"):
            with self.assertRaisesRegex(ValueError, "frozen roster"):
                m.summary(self.tmp, m.DEV_TASKS)


class SyntheticGeneration(OfflineCase):
    def test_entry_scores_the_namespace_supplied_by_actual_generation(self):
        model, case = m.compat.MODELS[0], m.DEV_TASKS[1]
        pool = self.tmp / "pool"
        task = pool / "tasks" / case
        task.mkdir(parents=True)
        (task / "scope.md").write_text("Synthetic note rename scope.\n")
        args = SimpleNamespace(campaign_id="synthetic-entry")
        generated, scored = [], []

        @contextlib.contextmanager
        def generation(cell):
            folder = z.namespace(args.campaign_id, cell)
            generated.append((cell, folder))
            yield {"base": "http://synthetic.invalid:14210", "folder": folder}

        def stage(work, base, folder):
            project = work / "project"
            (project / "tests").mkdir(parents=True)
            return project

        def call_model(project, work, arm, frame, actual_model, timeout, budget):
            self.assertIn(generated[-1][1], frame)
            (project / "tests/generated.spec.ts").write_text(generated[-1][1] + "/note")
            return {"infrastructure_error": False, "elapsed_ms": 1}

        def collect(project, target):
            (target / "tests").mkdir(parents=True)
            (target / "tests/generated.spec.ts").write_text((project / "tests/generated.spec.ts").read_text())
            return {"spec_files": ["tests/generated.spec.ts"]}

        def evaluate(actual_case, tests, specs, cell):
            self.assertEqual(actual_case, case)
            self.assertEqual(specs, ["tests/generated.spec.ts"])
            scored.append(cell)
            folder = z.namespace(args.campaign_id, cell)
            notes = {"synthetic-note": (tests / "generated.spec.ts").read_text()}
            escapes = z.isolation_violations({}, notes, folder)
            self.assertEqual(escapes, [], "a compliant generated note must remain inside the scoring namespace")
            return {"clean": not escapes, "clean_runs": [{"errors": []}]}

        runtime = SimpleNamespace(pool=pool, generation=generation, stage=stage, evaluate=evaluate,
            loop=SimpleNamespace(commit_baseline=lambda _: None),
            prompt=lambda scope, base, folder: scope + " " + folder,
            generation_config=lambda _: {"reuse_existing_server": True})
        with patch.object(m.tempfile, "tempdir", str(self.tmp)), \
             patch.object(m, "digest", return_value="synthetic-freeze"), \
             patch.object(m.engine, "wait_for_load", return_value=None), \
             patch.object(m.engine, "call_model", side_effect=call_model) as calls, \
             patch.object(m.engine, "collect_deliverable", side_effect=collect), \
             patch.object(m.v2.v1, "_init_codex", return_value={"status": "ready"}), \
             patch.object(m.os, "getloadavg", return_value=(0.0, 0.0, 0.0)):
            for attempt in (1, 2):
                with self.subTest(attempt=attempt):
                    root = self.tmp / ("entry-" + str(attempt))
                    if attempt == 2:
                        previous = root / "zeppelin-entry/attempt-1"
                        m.write(previous / "started.json", {"attempt_id": "previous", "freeze_sha256": "synthetic-freeze"})
                        m.write(previous / "outcome.json", {"kind": "infrastructure", "decision": None})
                    decision, _ = m.zeppelin_entry(args, runtime, root, model, m.protocol())
                    self.assertEqual(decision, "admitted")
                    self.assertEqual(scored[-1], generated[-1][0])
                    self.assertNotEqual(scored[-1], model + "-zeppelin-entry-" + str(attempt))
                    before = calls.call_count
                    self.assertEqual(m.zeppelin_entry(args, runtime, root, model, m.protocol())[0], "admitted")
                    self.assertEqual(calls.call_count, before)

    def test_three_arms_keep_zeppelin_frame_and_per_cell_namespace(self):
        model, case = m.compat.MODELS[0], m.DEV_TASKS[0]
        pool, directory = self.tmp / "pool", self.tmp / "output" / model
        task = pool / "tasks" / case
        task.mkdir(parents=True)
        (task / "scope.md").write_text("Synthetic Zeppelin task scope.\n")
        active, observed = [], []
        args = SimpleNamespace(campaign_id="synthetic-campaign")
        current = {}

        @contextlib.contextmanager
        def generation(cell):
            self.assertFalse(active)
            active.append(cell)
            folder = z.namespace(args.campaign_id, cell)
            current["folder"] = folder
            try:
                yield {"base": "http://synthetic.invalid:14210", "folder": folder}
            finally:
                active.pop()

        def stage(work, base, folder):
            project = work / "project"
            (project / "tests").mkdir(parents=True)
            (project / "README.md").write_text("Synthetic project " + folder)
            return project

        def call_model(project, work, arm, frame, actual_model, timeout, budget):
            self.assertEqual(m.engine.FRAME, "{task}")
            self.assertEqual(actual_model, model)
            self.assertTrue(frame.startswith("ZEPPELIN_FRAME "))
            self.assertIn("Synthetic Zeppelin task scope.", frame)
            self.assertIn(current["folder"], frame)
            self.assertTrue(active)
            if arm == m.ARM_B:
                self.assertIn(current["folder"], (project / "tests/synthetic.spec.ts").read_text())
            (project / "tests/synthetic.spec.ts").write_text("// " + current["folder"] + "/note\n")
            observed.append((arm, current["folder"]))
            return {"infrastructure_error": False, "elapsed_ms": 1000}

        def collect(project, target):
            (target / "tests").mkdir(parents=True, exist_ok=True)
            (target / "tests/synthetic.spec.ts").write_text((project / "tests/synthetic.spec.ts").read_text())
            return {"spec_files": ["tests/synthetic.spec.ts"]}

        runtime = SimpleNamespace(pool=pool, generation=generation, stage=stage,
            loop=SimpleNamespace(commit_baseline=lambda _: None),
            prompt=lambda scope, base, folder: "ZEPPELIN_FRAME " + scope + " " + base + " " + folder,
            generation_config=lambda _: {"reuse_existing_server": True})
        original_frame = m.engine.FRAME
        with patch.object(m.tempfile, "tempdir", str(self.tmp)), \
             patch.object(m.engine, "wait_for_load", return_value=None), \
             patch.object(m.engine, "call_model", side_effect=call_model), \
             patch.object(m.engine, "collect_deliverable", side_effect=collect), \
             patch.object(m.v2.v1, "_init_codex", return_value={"status": "ready"}), \
             patch.object(m.os, "getloadavg", return_value=(0.0, 0.0, 0.0)):
            for ordinal, arm in enumerate((m.ARM_A, m.ARM_C, m.ARM_B), 1):
                result = m.generate({"case": case, "arm": arm, "repetition": 1, "ordinal": ordinal},
                    args, runtime, model, directory, m.DEV_TASKS)
                self.assertTrue(result["deliverable"])
                self.assertFalse(result["infrastructure_error"])
                self.assertEqual(len(result["attempts"]), 1)
                self.assertEqual(m.engine.FRAME, original_frame)
        self.assertEqual([arm for arm, _ in observed], [m.ARM_A, m.ARM_C, m.ARM_B])
        self.assertEqual(len({folder for _, folder in observed}), 3)
        self.assertFalse(active)
        self.assertFalse(list(self.tmp.glob("oss-cell-*")))


class VaultIntegrityRepairs(OfflineCase):
    def test_external_ledger_refuses_reuse_across_campaign_and_skill_digests(self):
        root = self.tmp / "spent"
        first = m.vault_guard.spend(root, "a" * 64, {"skill": {"SKILL.md": "b" * 64}}, "c" * 64)
        self.assertEqual(first["status"], "SPENT_BEFORE_OPEN")
        self.assertEqual(root.stat().st_mode & 0o777, 0o700)
        self.assertEqual((root / ("a" * 64 + ".json")).stat().st_mode & 0o777, 0o600)
        with self.assertRaisesRegex(ValueError, "already spent"):
            m.vault_guard.spend(root, "a" * 64, {"different": {"SKILL.md": "d" * 64}}, "e" * 64)

    def test_private_results_and_disjoint_roots(self):
        root = m.vault_guard.prepare_results(self.tmp / "results")
        self.assertEqual(root.stat().st_mode & 0o777, 0o700)
        with self.assertRaises(FileExistsError):
            m.vault_guard.prepare_results(root)
        with self.assertRaisesRegex(ValueError, "separate"):
            m.vault_guard.disjoint(root, root / "child")
        root.chmod(0o755)
        with self.assertRaisesRegex(ValueError, "0700"):
            m.vault_guard.owner_only(root)

    def test_vault_rejects_permissions_labels_extra_manifest_and_internal_links(self):
        fixture = ExternalVault.fixture(self)
        fixture.chmod(0o755)
        with self.assertRaisesRegex(ValueError, "0700"):
            m.validate_vault(fixture)
        fixture.chmod(0o700)
        scope = fixture / "tasks" / m.EVAL_NAMES[0] / "scope.md"
        scope.chmod(0o644)
        with self.assertRaisesRegex(ValueError, "owner-only"):
            m.validate_vault(fixture)
        scope.chmod(0o600)
        patch_file = fixture / "tasks" / m.EVAL_NAMES[0] / "patches/D1.patch"
        labelled = patch_file.with_name("D1-curator-label.patch")
        patch_file.rename(labelled)
        with self.assertRaisesRegex(ValueError, "five defects"):
            m.validate_vault(fixture)
        labelled.rename(patch_file)
        manifest = fixture / "manifest.json"
        manifest.write_text(json.dumps({"schema_version": 1, "tasks": list(m.EVAL_NAMES), "note": "private semantics"}))
        with self.assertRaises(ValueError):
            m.validate_vault(fixture)
        manifest.write_text(json.dumps({"schema_version": 1, "tasks": list(m.EVAL_NAMES)}))
        provenance = m.validate_vault(fixture)
        self.assertEqual(set(provenance), {"schema_version", "tasks", "commitment"})
        scope.unlink()
        scope.symlink_to(manifest)
        with self.assertRaisesRegex(ValueError, "symlink"):
            m.validate_vault(fixture)

    def args(self, command, split=None):
        args = CommandRefusals.args(self, command)
        if split:
            args += ["--split", split]
        return args

    def test_dev_drive_score_and_analysis_refuse_after_spend_without_vault_read(self):
        output = self.tmp / "output"
        output.mkdir()
        m.write(output / "FINAL_EVAL_ATTEMPT.json", {"status": "STARTED_ONCE"})
        with patch.object(m, "require_live", return_value={}), patch.object(m, "frozen", return_value={}), \
             patch.object(m, "campaign_output_guard"), patch.object(m, "validate_vault", side_effect=AssertionError("vault reopened")), \
             patch.object(m, "CampaignLock", side_effect=AssertionError("live setup attempted")):
            for command in ("drive", "score", "analyze", "summary"):
                with contextlib.redirect_stderr(io.StringIO()) as err:
                    self.assertEqual(m.main(self.args(command) + ["--allow-live"]), 2)
                    self.assertIn("DEV operations refuse", err.getvalue())

    def test_generated_eval_analysis_and_summary_do_not_reopen_vault(self):
        output = self.tmp / "output"
        output.mkdir()
        results = self.tmp / "final-results"
        results.mkdir(mode=0o700)
        m.write(output / "FINAL_EVAL_ATTEMPT.json", {"status": "GENERATED_ONCE", "freeze_sha256": "f" * 64})
        lock = {"eval_results_root": str(results)}
        with patch.object(m, "frozen", return_value=lock), patch.object(m, "campaign_output_guard"), \
             patch.object(m, "digest", return_value="f" * 64), patch.object(m, "validate_vault", side_effect=AssertionError("vault reopened")), \
             patch.object(m, "summary") as summary_call, patch.object(m, "analyze_directory") as analyze_call:
            self.assertEqual(m.main(self.args("summary", "final-eval")), 0)
            self.assertEqual(m.main(self.args("analyze", "final-eval") + ["--model", m.compat.MODELS[0]]), 0)
        summary_call.assert_called_once_with(results, list(m.EVAL_NAMES))
        analyze_call.assert_called_once_with(results / m.compat.MODELS[0], list(m.EVAL_NAMES))

    def test_eval_task_summary_and_pooling_run_from_generation_records(self):
        records, scores = SyntheticAnalysis.fixture(self)
        names = dict(zip(m.DEV_TASKS, m.EVAL_NAMES))
        for row in records + scores:
            row["case"] = names[row["case"]]
        model = m.compat.MODELS[0]
        with patch.object(m.v2, "cell_extras", side_effect=lambda *args: SyntheticAnalysis.extras(self, *args)):
            result = m.analyze_cells(records, scores, model, self.tmp, m.EVAL_NAMES)
        for name in m.compat.MODELS:
            m.write(self.tmp / "_entry" / (name + ".json"), {"decision": "admitted" if name == model else "excluded",
                    "freeze_sha256": "f" * 64})
        m.write(self.tmp / model / "final.json", {"synthetic": True})
        m.write(self.tmp / "final-eval-integrity.json", {"status": "GENERATED_ONCE", "vault_drift": True})
        cfg = m.protocol()
        cfg["pooled_analysis"]["cluster_bootstrap"]["replicates"] = 20
        with patch.object(m, "protocol", return_value=cfg), patch.object(m, "digest", return_value="f" * 64), \
             patch.object(m, "analyze_directory", return_value=result), \
             patch.object(m, "validate_vault", side_effect=AssertionError("vault reopened")), contextlib.redirect_stdout(io.StringIO()):
            summary = m.summary(self.tmp, m.EVAL_NAMES)
        self.assertTrue(summary["models"][model]["complete"])
        self.assertTrue(summary["final_eval_integrity"]["vault_drift"])
        self.assertTrue(summary["pooled"])
        for report in summary["pooled"].values():
            self.assertEqual(set(report["task_profile"]), set(m.EVAL_NAMES))

    def test_late_summary_failure_preserves_generated_status_and_drift_flag(self):
        output = self.tmp / "output"
        output.mkdir()
        m.write(output / "summary.json", {})
        vault = self.tmp / "vault"
        vault.mkdir(mode=0o700)
        model = m.compat.MODELS[0]
        entries = {name: {"decision": "admitted" if name == model else "excluded"} for name in m.compat.MODELS}
        for name, value in entries.items():
            m.write(output / "_entry" / (name + ".json"), value)
        lock = {"vault_sha256": "a" * 64, "eval_results_root": str(self.tmp / "eval-results"),
                "spent_ledger_root": str(self.tmp / "spent"), "bindings": {"committed_skills": {"skill": "digest"}}}
        summary_results = [{"models": {model: {"complete": True}}}, ValueError("late summary bug")]
        with patch.object(m, "require_live", return_value=lock), patch.object(m, "CampaignLock", return_value=contextlib.nullcontext()), \
             patch.object(m, "codex_context", return_value=contextlib.nullcontext()), \
             patch.object(m.v2, "load_harness_check"), patch.object(m.v2, "load_entries", return_value=entries), \
             patch.object(m, "runtime", return_value=SimpleNamespace(inherit_lock=lambda _: None)), \
             patch.object(m, "digest", return_value="a" * 64), patch.object(m, "summary", side_effect=summary_results), \
             patch.object(m, "validate_vault", side_effect=[{"commitment": "a" * 64}, ValueError("late drift")]), \
             patch.object(m, "drive_models"), contextlib.redirect_stderr(io.StringIO()):
            original_tmp = tempfile.tempdir
            try:
                self.assertEqual(m.main(self.args("final-eval") + ["--allow-live"]), 2)
            finally:
                tempfile.tempdir = original_tmp
        marker = m.read(output / "FINAL_EVAL_ATTEMPT.json")
        self.assertEqual(marker["status"], "GENERATED_ONCE")
        self.assertTrue(marker["vault_drift"])
        self.assertEqual((self.tmp / "eval-results").stat().st_mode & 0o777, 0o700)


class RuntimeAuditRepairs(OfflineCase):
    def test_delete_500_is_accepted_only_after_listing_proves_removal_and_trash_owned(self):
        import urllib.error
        folder = z.namespace("synthetic", "cell")
        notes = [{"id": "note1", "path": "~Trash/" + folder + "/note"}]
        def api(method, endpoint):
            if method == "GET":
                return {"body": list(notes)}
            notes.clear()
            error = urllib.error.HTTPError("synthetic", 500, "error", {}, io.BytesIO())
            try:
                raise error
            finally:
                error.close()
        self.assertEqual(z.clean_namespace(api, folder), 1)
        self.assertFalse(notes)

    def test_cleanup_retries_then_refuses_remaining_note(self):
        folder = z.namespace("synthetic", "cell")
        deletes = []
        def api(method, endpoint):
            if method == "GET":
                return {"body": [{"id": "note1", "path": folder + "/note"}]}
            deletes.append(endpoint)
            return {"status": "error"}
        with self.assertRaisesRegex(RuntimeError, "remain"):
            z.clean_namespace(api, folder)
        self.assertEqual(len(deletes), 2)

    def test_process_probe_ignores_wrappers_editors_and_ancestors(self):
        census = """100 90 python3 scripts/evals/run-generator-oss-eval-v1.py drive
90 1 zsh -c python3 scripts/evals/run-generator-oss-eval-v1.py drive
200 1 rg -n DELETE scripts/evals/run-generator-oss-eval-v1.py drive
201 1 vim scripts/evals/run-generator-oss-eval-v1.py drive
202 1 timeout 60 python3 scripts/evals/run-generator-oss-eval-v1.py drive
203 1 /usr/bin/python3 -B scripts/evals/run-generator-oss-eval-v1.py score
204 1 python3 scripts/evals/run-generator-multimodel-v2-codex.py drive
205 1 python3 scripts/evals/run-generator-oss-eval-v1.py plan
206 1 python3 inspect.py scripts/evals/run-generator-oss-eval-v1.py drive
207 1 python3 -X dev scripts/evals/run-generator-oss-eval-v1.py score
208 1 python3 -c 'print("run-generator-oss-eval-v1.py drive")'
"""
        with patch.object(z.subprocess, "run", return_value=SimpleNamespace(stdout=census)), \
             patch.object(z.os, "getpid", return_value=100), patch.object(z.os, "getppid", return_value=90):
            self.assertEqual(z.driver_processes(), [203, 204, 207])

    def test_scope_scrub_and_fixed_plan_have_no_answer_key_pointers(self):
        scope = """# Scope
Source of scope: apache/zeppelin PR #5181 (Upstream title)
Target src/app/title.ts:123 source line 123
See https://github.com/apache/zeppelin/pull/5181
- Rename persists after reload.
## Out of scope
- Add unrelated functionality.
"""
        scrubbed = m.scrub_scope(scope)
        plan = m.approved_plan("synthetic", scrubbed)
        for pointer in ("5181", "github.com", "title.ts", "source line"):
            self.assertNotIn(pointer, scrubbed + plan)
        self.assertIn("## Test Scenarios", plan)
        self.assertIn("**Seed:** `tests/seed.spec.ts`", plan)
        scenarios = plan.split("## Test Scenarios", 1)[1]
        self.assertIn("Rename persists", scenarios)
        self.assertNotIn("unrelated", scenarios)

    def test_arm_prompts_use_synthetic_suffix_and_b_is_review_only(self):
        frame = "You are adding Playwright end-to-end tests.\nDeliverable: new test file(s).\nTask scope."
        for arm in m.ARMS:
            task = m.arm_task(frame, arm)
            self.assertTrue(task.endswith(m.v2.rev.TASK_LINE if arm == m.ARM_B else m.v2.orig.PLAN_LINE))
        task = m.arm_task(frame, m.ARM_B)
        self.assertIn("Do not generate tests from scratch", task)
        self.assertNotIn("Deliverable: new test", task)
        self.assertNotIn("You are adding", task)
        with patch.object(m.v2.rev.orig, "OURS_SKILLS", m.ROOT / "skills"):
            m.v2.rev.stage_reviewer(self.tmp)
        staged = m.tree(self.tmp / "skill/e2e-reviewer")
        expected = {name: value for name, value in m.tree(m.ROOT / "skills/e2e-reviewer").items()
                    if "evals" not in Path(name).parts and "__pycache__" not in Path(name).parts}
        self.assertEqual(staged, expected)

    def test_saved_completed_scores_do_not_rerun_or_erase_adjudications(self):
        directory = self.tmp / "model"
        directory.mkdir()
        m.write(directory / "final.json", {"runs": []})
        saved = {"attempt_id": "first", "status": "COMPLETED", "scores": [],
                 "report_sha256": "digest", "freeze_sha256": "digest", "adjudications": {"call": {"D1": True}}}
        m.write(directory / "scores.json", saved)
        m.write(directory / "scoring-attempt.json", saved)
        with patch.object(m, "digest", return_value="digest"), patch.object(m, "report_check"), \
             patch.object(m, "score_rows", side_effect=AssertionError("completed score rerun")):
            self.assertEqual(m.score_directory(directory, SimpleNamespace(), m.DEV_TASKS), saved)
        self.assertEqual(m.read(directory / "scores.json")["adjudications"], saved["adjudications"])

    def test_partial_scores_resume_only_unscored_cells(self):
        previous = [{"call_id": "done", "case": "synthetic", "arm": m.ARM_A, "repetition": 1, "clean": False}]
        report = {"runs": [dict(previous[0]), {"call_id": "next", "case": "synthetic", "arm": m.ARM_A,
                  "repetition": 2, "spec_files": []}]}
        rt = SimpleNamespace(evaluate=lambda *args: self.fail("already scored cell rerun"))
        scores = m.score_rows(self.tmp, rt, report, previous=previous)
        self.assertEqual([r["call_id"] for r in scores], ["done", "next"])
        self.assertEqual(scores[0], previous[0])

    def test_minimal_failure_titles_and_calibration_reason_use_exact_json_scoring_path(self):
        data = {"stats": {"expected": 0, "unexpected": 1}, "suites": [{"title": "suite", "specs": [{"title": "behavior",
            "tests": [{"status": "unexpected", "results": [{"status": "failed", "errors": [{"message": "private expected value"}]}]}]}]}]}
        completed = SimpleNamespace(returncode=1, stdout=json.dumps(data), stderr="private stderr")
        with patch.object(z.subprocess, "run", return_value=completed) as run:
            result = z.run_playwright_records(self.tmp, ["tests/reference.spec.ts"], 600, {},
                                             {"failing_test_title": "suite > behavior", "reason_regex": "expected value"})
        self.assertEqual(result["failing_test_titles"], ["suite > behavior"])
        self.assertTrue(result["calibration_reason_matched"])
        self.assertNotIn("private", json.dumps(result))
        self.assertEqual(run.call_args.args[0][-1], "--reporter=json")

    def test_calibration_rejects_swapped_reason_and_nonfailed_matching_result(self):
        def spec(title, status, message):
            return {"title": title, "tests": [{"results": [{"status": status, "errors": [{"message": message}]}]}]}
        expected = {"failing_test_title": "suite > expected", "reason_regex": "declared defect"}
        for specs in ([spec("expected", "timedOut", "unrelated timeout"), spec("other", "failed", "declared defect")],
                      [spec("expected", "passed", "declared defect"), spec("other", "failed", "declared defect")]):
            data = {"stats": {"unexpected": 2}, "suites": [{"title": "suite", "specs": specs}]}
            with patch.object(z.subprocess, "run", return_value=SimpleNamespace(returncode=1, stdout=json.dumps(data))):
                result = z.run_playwright_records(self.tmp, ["tests/reference.spec.ts"], 600, {}, expected)
            self.assertFalse(result["calibration_reason_matched"])
            self.assertNotIn("declared defect", json.dumps(result))

    def test_calibration_requires_titles_reasons_clean_and_refactor_on_exact_runtime(self):
        pool = self.tmp / "pool"
        for case in m.DEV_TASKS:
            task = pool / "tasks" / case
            task.mkdir(parents=True)
            (task / "reference.spec.ts").write_text("const note = 'E2E_POOL/note';")
            m.write(task / "calibration-expectations.json", {f"D{i}": {"failing_test_title": "suite > expected",
                                                   "reason_regex": "expected"} for i in range(1, 6)})
        calls = []
        def evaluate(case, tests, specs, cell, expected_failures):
            calls.append(case)
            self.assertNotIn("E2E_POOL", (tests / "reference.spec.ts").read_text())
            self.assertEqual(specs, ["tests/reference.spec.ts"])
            return {"clean": True, "refactor_pass": True, "faults": {f"D{i}": {"failed": 1, "errors": [],
                "failing_test_titles": ["suite > expected"], "calibration_reason_matched": True} for i in range(1, 6)}}
        args = SimpleNamespace(pool=pool, loop_runner=self.tmp / "loop", dists=self.tmp / "dists", source=self.tmp / "source", campaign_id="synthetic")
        with patch.object(m, "bindings", return_value={"synthetic": "digest"}):
            result = m.calibrate_references(args, SimpleNamespace(pool=pool, evaluate=evaluate), self.tmp / "output")
            self.assertEqual(result["status"], "PASS")
            self.assertEqual(calls, list(m.DEV_TASKS))
            self.assertEqual(m.validate_calibration(args, self.tmp / "output"), result)

    def test_smoke_is_available_without_freeze_and_requires_explicit_live(self):
        args = SimpleNamespace(allow_live=False)
        with patch.object(m, "frozen", side_effect=AssertionError("smoke consulted freeze")):
            with self.assertRaisesRegex(ValueError, "allow-live"):
                m.zeppelin_smoke(args, {}, self.tmp / "smoke")
        marker = self.tmp / "NON_DATA_SMOKE.json"
        m.write(marker, {"not_campaign_data": True})
        with self.assertRaisesRegex(ValueError, "non-data"):
            m.score_directory(self.tmp, SimpleNamespace(), m.DEV_TASKS)
        with self.assertRaisesRegex(ValueError, "non-data"):
            m.analyze_directory(self.tmp, m.DEV_TASKS)



class ZeppelinEntryBudget(OfflineCase):
    def setUp(self):
        super().setUp()
        self.stack.enter_context(patch.object(m, "digest", return_value="synthetic-freeze"))
        self.args = SimpleNamespace()
        self.rt = SimpleNamespace(evaluate=MagicMock(return_value={"clean": True, "clean_runs": [{"errors": []}]}))

    def run_entry(self):
        return m.zeppelin_entry(self.args, self.rt, self.tmp, "synthetic-model", m.protocol())

    @staticmethod
    def row(**kwargs):
        return {"case": m.DEV_TASKS[1], "call_id": "synthetic-call", "spec_files": ["tests/generated.spec.ts"],
                "infrastructure_error": False, **kwargs}

    def test_infrastructure_retry_keeps_unique_history_and_one_call_per_slot(self):
        with patch.object(m, "generate", side_effect=[self.row(infrastructure_error=True), self.row()]) as generate:
            self.assertIsNone(self.run_entry()[0])
            first = self.tmp / "zeppelin-entry/attempt-1/run.json"
            before = first.read_bytes()
            decision, state = self.run_entry()
            self.assertEqual(decision, "admitted")
            self.assertEqual(len(state["attempts"]), 2)
            self.assertEqual(first.read_bytes(), before)
            self.assertEqual(len({a["attempt_id"] for a in state["attempts"]}), 2)
            self.assertTrue(all(call.kwargs["max_attempts"] == 1 for call in generate.call_args_list))
            self.assertEqual(self.run_entry()[0], "admitted")
            self.assertEqual(generate.call_count, 2)

    def test_valid_missing_delivery_or_clean_failure_is_final_exclusion(self):
        for name, row, score in (("delivery", self.row(spec_files=[]), {"clean": True}),
                                 ("clean", self.row(), {"clean": False, "clean_runs": [{"errors": []}]})):
            root = self.tmp / name
            rt = SimpleNamespace(evaluate=MagicMock(return_value=score))
            with patch.object(m, "generate", return_value=row) as generate:
                for _ in range(3):
                    decision, state = m.zeppelin_entry(self.args, rt, root, "synthetic-model", m.protocol())
                    self.assertEqual(decision, "excluded")
                self.assertEqual(generate.call_count, 1)
                self.assertEqual(len(state["attempts"]), 1)
                self.assertEqual(rt.evaluate.call_count, 0 if name == "delivery" else 1)

    def test_interrupted_calls_consume_slots_and_exhausted_budget_never_relaunches(self):
        with patch.object(m, "generate", side_effect=RuntimeError("synthetic interruption")) as generate:
            for _ in range(2):
                with self.assertRaisesRegex(RuntimeError, "interruption"):
                    self.run_entry()
            decision, state = self.run_entry()
            self.assertIsNone(decision)
            self.assertIn("budget exhausted", state["reason"])
            self.assertEqual(len(state["attempts"]), 2)
            self.assertEqual(generate.call_count, 2)

    def test_valid_generation_scoring_interruption_never_relaunches_model(self):
        self.rt.evaluate.side_effect = RuntimeError("score interrupted")
        with patch.object(m, "generate", return_value=self.row()) as generate:
            with self.assertRaisesRegex(RuntimeError, "score interrupted"):
                self.run_entry()
            decision, state = self.run_entry()
            self.assertIsNone(decision)
            self.assertIn("no further model", state["reason"])
            self.assertEqual(generate.call_count, 1)
            self.assertEqual(self.rt.evaluate.call_count, 1)

    def test_fatal_or_scoring_infrastructure_stays_undecided_without_retry(self):
        for name, row, score in (("fatal", self.row(infrastructure_error=True, fatal_infrastructure=True), {"clean": True}),
                                 ("scoring", self.row(), {"clean": False, "clean_runs": [{"errors": ["harness timeout"]}]})):
            root = self.tmp / name
            with patch.object(m, "generate", return_value=row) as generate:
                rt = SimpleNamespace(evaluate=MagicMock(return_value=score))
                for _ in range(2):
                    decision, _ = m.zeppelin_entry(self.args, rt, root, "synthetic-model", m.protocol())
                    self.assertIsNone(decision)
                self.assertEqual(generate.call_count, 1)

    def test_legacy_unbounded_history_refuses(self):
        m.write(self.tmp / "zeppelin-entry/non-data-entry.json", {})
        with patch.object(m, "generate", side_effect=AssertionError("model called")), self.assertRaisesRegex(ValueError, "legacy unbounded"):
            self.run_entry()


class CodexConfigurationAdmission(unittest.TestCase):
    def test_protocol_configuration_and_successor_imports_are_consistent(self):
        p = m.protocol()
        self.assertEqual(p["arm_a_configuration"], {"sandbox_mode": "danger-full-access", "approval_policy": "never",
                         "mcp_default_tools_approval_mode": "approve", "generator_tool_count": 19})
        self.assertTrue(p["imports"]["codex_runner"].endswith("run-generator-multimodel-v4-codex.py"))
        self.assertEqual(Path(m.v2.__file__).name, Path(p["imports"]["codex_runner"]).name)
        self.assertIn("intentionally overrides", p["fidelity"]["role_differences"])
        self.assertIn("danger-full-access", p["fidelity"]["role_differences"])
        p["arm_a_configuration"]["sandbox_mode"] = "read-only"
        with self.assertRaisesRegex(ValueError, "contradicts runtime"):
            m.require_corrected_codex_config(p)

    def test_obsolete_shell_or_mcp_approval_refuses_before_live_setup(self):
        good = ["exec", "--sandbox", "danger-full-access", "-c", 'approval_policy="never"',
                "-c", 'mcp_servers.playwright-test.default_tools_approval_mode="approve"',
                "-c", "mcp_servers.playwright-test.enabled_tools=" + json.dumps(list(m.compat.GENERATOR_TOOLS))]
        with patch.object(m.compat, "command", return_value=good):
            m.require_corrected_codex_config(m.protocol())
        for broken in (good[:2] + ["read-only"] + good[3:], good[:5] + good[7:]):
            with patch.object(m.compat, "command", return_value=broken), \
                    patch.object(m.subprocess, "run", side_effect=AssertionError("live setup called")), \
                    self.assertRaisesRegex(ValueError, "obsolete adapter"):
                with m.codex_context(Path("unused-offline-output"), m.protocol()):
                    self.fail("broken configuration admitted")
        wrong = good[:-1] + ['mcp_servers.playwright-test.enabled_tools=["test_list"]']
        with patch.object(m.compat, "command", return_value=wrong), self.assertRaisesRegex(ValueError, "allowlist"):
            m.require_corrected_codex_config(m.protocol())


class ReadinessOfflineRepairs(OfflineCase):
    CANDIDATES = ROOT / "benchmarks/generator-oss-eval-v1/calibration-candidates"

    def test_expectation_schema_is_strict(self):
        good = {f"D{i}": {"failing_test_title": "a > b", "reason_regex": "x"} for i in range(1, 6)}
        m.validate_expectations(good)
        for bad in ({k: v for k, v in good.items() if k != "D5"}, {**good, "D6": good["D1"]},
                    {**good, "D1": {"failing_test_title": "a"}}, {**good, "D1": {**good["D1"], "extra": "x"}},
                    {**good, "D1": {"failing_test_title": "a", "reason_regex": ""}},
                    {**good, "D1": {"failing_test_title": "a", "reason_regex": "("}}, []):
            with self.assertRaises((ValueError, m.re.error)):
                m.validate_expectations(bad)

    def test_committed_candidates_satisfy_the_runner_schema_and_stay_unverified(self):
        for case in m.DEV_TASKS:
            data = json.loads((self.CANDIDATES / (case + ".calibration-expectations.json")).read_text())
            m.validate_expectations(data)
            titles = [entry["failing_test_title"] for entry in data.values()]
            self.assertTrue(all(title.startswith("reference.spec.ts > ") for title in titles))
        provenance = json.loads((self.CANDIDATES / "PROVENANCE.json").read_text())
        self.assertEqual(provenance["status"], "CANDIDATE_UNVERIFIED_PENDING_LIVE_CALIBRATION")
        self.assertTrue(provenance["pending_live_values"])

    def test_dev_pool_guard_refuses_heldout_names_and_leak_paths_by_existence_only(self):
        clean = self.tmp / "clean"
        for case in m.DEV_TASKS:
            (clean / "tasks" / case).mkdir(parents=True)
        m.assert_dev_only_pool(clean)
        for leak in (["tasks", "zep-about-modal"], ["tasks", "zep-home-links"], ["sealed-eval"],
                     ["harness", "author-patches.py"], ["harness", "defect-meta.json"],
                     ["results", "mutant-results.md"], ["results", "mutant-results.txt"]):
            root = self.tmp / ("leak-" + "-".join(leak))
            for case in m.DEV_TASKS:
                (root / "tasks" / case).mkdir(parents=True)
            target = root.joinpath(*leak)
            target.parent.mkdir(parents=True, exist_ok=True)
            if leak[0] in ("tasks", "sealed-eval"):
                target.mkdir(exist_ok=True)
            else:
                target.touch()
            with self.assertRaisesRegex(ValueError, "not isolated"):
                m.assert_dev_only_pool(root)
            with self.assertRaisesRegex(ValueError, "not isolated"):
                m.bindings(root, self.tmp / "a/b/c/loop.py", self.tmp / "dists", self.tmp / "source")

    def test_smoke_and_calibrate_refuse_exposed_pool_before_output_lock_or_subprocess(self):
        root = self.tmp / "exposed"
        (root / "tasks" / "zep-about-modal").mkdir(parents=True)
        out = self.tmp / "out"
        args = SimpleNamespace(allow_live=True, pool=root, command="calibrate")
        with patch.object(m, "CampaignLock", side_effect=AssertionError("lock taken")), \
                patch.object(m.subprocess, "run", side_effect=AssertionError("subprocess")), \
                self.assertRaisesRegex(ValueError, "not isolated"):
            m.zeppelin_smoke(args, m.protocol(), out)
        self.assertFalse(out.exists())


if __name__ == "__main__":
    unittest.main(verbosity=2)
