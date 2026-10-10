#!/usr/bin/env python3
"""Frozen successor for the side-effectful-GET V4 evidence gate. Apache-2.0."""
import importlib.util
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[2]
PARENT = ROOT / "scripts/evals/run-generator-v4-get-pilot-v1.py"
spec = importlib.util.spec_from_file_location("v4_get_pilot_v1", PARENT)
parent = importlib.util.module_from_spec(spec)
spec.loader.exec_module(parent)

BENCH = ROOT / "benchmarks/generator-v4-get-pilot-v2"
ARMS = ("before", "after")
SNAPSHOTS = {arm: BENCH / "arms" / arm / "playwright-test-generator" for arm in ARMS}
PROTOCOL, LOCK = BENCH / "protocol.json", BENCH / "freeze.json"
parent.BENCH, parent.SNAPSHOTS = BENCH, SNAPSHOTS
parent.PROTOCOL, parent.LOCK = PROTOCOL, LOCK
overlap, pilot = parent.overlap, parent.pilot
overlap.BENCH, overlap.SNAPSHOTS = BENCH, SNAPSHOTS
overlap.PROTOCOL, overlap.LOCK = PROTOCOL, LOCK
pilot.BENCH, pilot.PROTOCOL, pilot.LOCK = BENCH, PROTOCOL, LOCK
PARENT_BINDINGS = parent.bindings

SKILL_ADDITION = (
    "Before reporting `Complete`, reconcile each planned V4 write with the two evidence "
    "lines required by `verification-rules.md`: the normal request's method, endpoint, "
    "payload/query, and cardinality with its visible outcome; and the failed-write run's "
    "failure at the unchanged primary assertion or declared settled-state gate. A passing "
    "suite, V6 verdict, or `V4 PASS` label without those lines is not V4 proof; record "
    "`CANNOT_VERIFY` and use `PARTIAL/BLOCKED`.\n\n"
)
OLD_PLAN_FIELD = "- Write proof (V4): <request evidence, or N/A for read-only behavior>"
NEW_PLAN_FIELD = (
    "- Write proof (V4): <effect from source or observed behavior: write, read-only, or unknown; "
    "for a write, planned method, endpoint, relevant payload/query, cardinality, user-visible "
    "outcome, and failed-write assertion/gate; N/A with reason for read-only behavior; "
    "CANNOT_VERIFY for unknown effect>"
)
PLAN_ADDITION = (
    "Classify the action's effect before assigning V4, including a `GET` handler that changes "
    "server-side state the scenario asserts. The HTTP method alone never proves an action "
    "read-only. If its effect remains unknown, keep that uncertainty in the plan instead "
    "of marking V4 `N/A`.\n\n"
)


def snapshot_check():
    before, after = (pilot.engine.tree_digest(SNAPSHOTS[arm]) for arm in ARMS)
    if not before or set(before) != set(after):
        raise ValueError("missing or differently shaped skill snapshots")
    if {name for name in before if before[name] != after[name]} != {"SKILL.md", "scenario-design.md"}:
        raise ValueError("intervention changed files beyond SKILL.md and scenario-design.md")
    old_skill = (SNAPSHOTS["before"] / "SKILL.md").read_text()
    new_skill = (SNAPSHOTS["after"] / "SKILL.md").read_text()
    if old_skill.count(SKILL_ADDITION) or new_skill.count(SKILL_ADDITION) != 1 or new_skill.replace(SKILL_ADDITION, "") != old_skill:
        raise ValueError("completion-gate contrast is not the exact paragraph addition")
    old_plan = (SNAPSHOTS["before"] / "scenario-design.md").read_text()
    new_plan = (SNAPSHOTS["after"] / "scenario-design.md").read_text()
    if (old_plan.count(OLD_PLAN_FIELD) != 1 or new_plan.count(NEW_PLAN_FIELD) != 1
            or old_plan.count(PLAN_ADDITION) or new_plan.count(PLAN_ADDITION) != 1
            or new_plan.replace(NEW_PLAN_FIELD, OLD_PLAN_FIELD).replace(PLAN_ADDITION, "") != old_plan):
        raise ValueError("scenario-plan contrast is not the exact field and paragraph change")
    source = pilot.engine.tree_digest(ROOT / "skills/playwright-test-generator", skip=("evals",))
    if after != source:
        raise ValueError("after snapshot differs from current product skill")
    return {arm: pilot.engine.tree_digest(path) for arm, path in SNAPSHOTS.items()}


def protocol():
    value = pilot.read(PROTOCOL)
    old = pilot.v8.protocol()
    if value["protocol_id"] != "generator-v4-get-pilot-v2" or value["arms"] != list(ARMS):
        raise ValueError("unexpected V4 successor protocol or arms")
    if value["cases"] != ["v3-13"] or value["repetitions"] != 3 or value["workers"] != 1:
        raise ValueError("V4 successor requires one case, three pairs, one worker")
    for key in ("model", "reasoning_effort", "container_image", "docker_context",
                "minimum_free_disk_bytes", "timeout_s"):
        if value[key] != old[key]:
            raise ValueError("V4 execution identity differs from v8: " + key)
    if value["minimum_free_disk_bytes"] != 4294967296:
        raise ValueError("disk safety floor differs")
    if "print its complete source with a read-only command" not in value["common_prompt_appendix"]:
        raise ValueError("conditional probe-source evidence instruction missing")
    snapshot_check()
    pilot.validate_probe(value)
    return value


def bindings():
    data = PARENT_BINDINGS()
    data.update(
        protocol=pilot.digest(PROTOCOL),
        runner=pilot.digest(Path(__file__)),
        parent_runner=pilot.digest(PARENT),
        snapshots=snapshot_check(),
    )
    return data


parent.snapshot_check = snapshot_check
parent.protocol = protocol
parent.bindings = bindings
overlap.snapshot_check = snapshot_check
overlap.protocol = protocol
overlap.bindings = bindings
pilot.protocol = protocol
pilot.bindings = bindings

if __name__ == "__main__":
    try:
        raise SystemExit(pilot.main())
    except (ValueError, KeyError, FileNotFoundError, FileExistsError) as error:
        print(f"refused (INCOMPLETE): {error}", file=sys.stderr)
        raise SystemExit(3)
