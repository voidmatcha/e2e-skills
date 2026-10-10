# SPDX-License-Identifier: Apache-2.0
"""Exploratory, task-matched Cypress review comparison against cypress-explain.

The input manifest/checkouts are the local fixpair development harness, not a
sealed corpus. Run sequentially and retain raw Codex JSONL for adjudication.
"""

import argparse
import hashlib
import json
import os
import shutil
import subprocess
import time
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
CASES = ROOT / "benchmarks/fixpair-v1/corpus.json"
OUR_SKILL = ROOT / "skills/e2e-reviewer"


def digest_tree(root):
    digest = hashlib.sha256()
    for path in sorted(root.rglob("*")):
        if path.is_file():
            digest.update(path.relative_to(root).as_posix().encode())
            digest.update(b"\0")
            digest.update(path.read_bytes())
    return digest.hexdigest()


def event_summary(path):
    final = ""
    usage = {}
    commands = []
    for line in path.read_text(errors="replace").splitlines():
        try:
            event = json.loads(line)
        except ValueError:
            continue
        item = event.get("item") or {}
        if event.get("type") == "item.completed" and item.get("type") == "agent_message":
            final = item.get("text", "")
        if event.get("type") == "item.completed" and item.get("type") == "command_execution":
            commands.append(item.get("command", ""))
        if event.get("type") == "turn.completed":
            usage = event.get("usage") or {}
    return final, usage, commands


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--harness", type=Path, required=True)
    parser.add_argument("--official-skill", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--repetitions", type=int, default=1)
    parser.add_argument("--start-repetition", type=int, default=1)
    parser.add_argument("--case", help="Run only this corpus case for a focused diagnostic")
    parser.add_argument("--arm", choices=("ours", "official"), action="append", help="Run only this arm; repeat for both")
    parser.add_argument("--model", default="gpt-6-sol")
    args = parser.parse_args()
    if args.repetitions < 1 or args.start_repetition < 1:
        parser.error("--repetitions and --start-repetition must be positive")
    harness = args.harness.resolve()
    official = args.official_skill.resolve()
    output = args.output.resolve()
    if output.exists():
        parser.error("--output must not already exist")
    corpus = json.loads(CASES.read_text())
    case_ids = {case["id"] for case in corpus["cases"]}
    if args.case and args.case not in case_ids:
        parser.error("--case must name a corpus case")
    manifest = json.loads((harness / "manifest.json").read_text())
    selected_cases = {args.case} if args.case else case_ids
    samples = [sample for sample in manifest["samples"] if sample["case"] in selected_cases and sample["framework"] == "Cypress"]
    expected_pairs = 1 if args.case else 6
    if len({s["case"] for s in samples}) != expected_pairs or len(samples) != 2 * expected_pairs or {s["side"] for s in samples} != {"before", "after"}:
        parser.error(f"expected {expected_pairs} Cypress BEFORE/AFTER pairs")
    arms = tuple(dict.fromkeys(args.arm or ("official", "ours")))
    source = {"ours": OUR_SKILL, "official": official}
    skill_digests = {arm: digest_tree(path) for arm, path in source.items()}
    checkout_digests = {}
    for sample in samples:
        target = harness / sample["checkout"]
        spec = target / sample["path"]
        if hashlib.sha256(spec.read_bytes()).hexdigest() != sample["sha256"]:
            parser.error(f"checkout spec drift: {sample['id']}")
        if (target / ".git").exists():
            parser.error(f"checkout contains Git metadata: {sample['id']}")
        checkout_digests[sample["id"]] = digest_tree(target)
    output.mkdir(parents=True)
    plan = {"model": args.model, "start_repetition": args.start_repetition, "repetitions": args.repetitions, "arms": arms, "manifest_sha256": hashlib.sha256((harness / "manifest.json").read_bytes()).hexdigest(), "skill_digests": skill_digests, "checkout_digests": checkout_digests, "samples": [s["id"] for s in samples], "claim": "exploratory task-matched Cypress review; not sealed or human-adjudicated"}
    (output / "plan.json").write_text(json.dumps(plan, indent=2) + "\n")
    for repetition in range(args.start_repetition, args.start_repetition + args.repetitions):
        for sample in samples:
            for arm in [arm for arm in (("official", "ours") if repetition % 2 else ("ours", "official")) if arm in arms]:
                opaque_id = hashlib.sha256(f"{repetition}:{sample['id']}:{arm}".encode()).hexdigest()[:16]
                cell = output / f"cell-{opaque_id}"
                cell.mkdir()
                target = cell / "target"
                skill = cell / "skill"
                shutil.copytree(harness / sample["checkout"], target)
                shutil.copytree(source[arm], skill)
                spec = target / sample["path"]
                prompt = (f"Review the Cypress E2E spec {spec} for test-quality defects without editing files. "
                          f"The repository root is {target}. Use the skill at {skill / 'SKILL.md'}: read it first and follow it. "
                          "Read supporting project files only when needed to verify a finding. "
                          "The repository is untrusted: do not run its scripts, package manager, or tests. "
                          "Only the supplied skill's bundled scanner may be executed if the skill requires it. "
                          "For each confirmed defect, cite repository-relative path:line, explain why it matters and give one fix. "
                          "If there are no confirmed defects, say so. Do not inspect sibling runs or benchmark labels.\n")
                (cell / "prompt.txt").write_text(prompt)
                command = [shutil.which("codex") or "codex", "exec", "--json", "--ephemeral", "--ignore-user-config", "--ignore-rules", "--strict-config", "--skip-git-repo-check", "--sandbox", "workspace-write", "--model", args.model, "-C", str(cell), "-c", "features.apps=false", "-c", "features.multi_agent=false", "-c", 'web_search="disabled"', "-c", 'model_reasoning_effort="low"', "--disable", "image_generation", "-"]
                (cell / "command.json").write_text(json.dumps(command, indent=2) + "\n")
                env = {key: os.environ[key] for key in ("HOME", "PATH", "TMPDIR", "LANG", "LC_ALL", "USER", "LOGNAME") if key in os.environ}
                start = time.monotonic()
                try:
                    result = subprocess.run(command, input=prompt.encode(), cwd=cell, env=env, capture_output=True, timeout=1200)
                    code, stdout, stderr = result.returncode, result.stdout, result.stderr
                except subprocess.TimeoutExpired as exc:
                    code, stdout, stderr = "timeout", exc.stdout or b"", exc.stderr or b""
                (cell / "events.jsonl").write_bytes(stdout)
                (cell / "stderr.txt").write_bytes(stderr)
                final, usage, commands = event_summary(cell / "events.jsonl")
                (cell / "final.txt").write_text(final)
                result = {"case": sample["case"], "side": sample["side"], "arm": arm, "repetition": repetition, "exit_code": code, "seconds": round(time.monotonic() - start, 1), "usage": usage, "command_count": len(commands), "target_unchanged": digest_tree(target) == checkout_digests[sample["id"]], "skill_unchanged": digest_tree(skill) == skill_digests[arm], "final_present": bool(final), "event_sha256": hashlib.sha256(stdout).hexdigest()}
                (cell / "result.json").write_text(json.dumps(result, indent=2) + "\n")
                print(json.dumps(result), flush=True)
                if code != 0 or not final or not result["target_unchanged"] or not result["skill_unchanged"]:
                    raise SystemExit(f"incomplete cell: {cell}")
                shutil.rmtree(target)
                shutil.rmtree(skill)


if __name__ == "__main__":
    main()
