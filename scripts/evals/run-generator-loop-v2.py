#!/usr/bin/env python3
"""DEV-only generator restart: Codex proposes; deterministic scripts decide. Apache-2.0.

Imports are lazy. Offline commands never configure Docker, call a model, open an
eval task, inspect processes or create a freeze. Existing machinery is read-only.
"""
import argparse
from collections import defaultdict
import contextlib
import difflib
from fractions import Fraction
import hashlib
import importlib.util
import json
from math import comb, isfinite
import os
from pathlib import Path
import random
import re
import shutil
import subprocess
import sys
import tempfile

sys.dont_write_bytecode = True
ROOT = Path(__file__).resolve().parents[2]
BENCH = ROOT / "benchmarks/generator-loop-v2"
MODEL = "gpt-6-luna"
ARM = "ours-2.0.1"
DEV_SYNTH = ("v2-11", "v3-08", "v2-18")
DEV_OSS = ("zep-sidebar", "zep-note-rename")
DEV = DEV_SYNTH + DEV_OSS
ADOPTIONS = {"ADOPT_QUALITY", "ADOPT_COST"}
MACHINERY = None


def read(path):
    return json.loads(Path(path).read_text())


def write(path, value):
    """Exclusive outputs: interrupted work is evidence, never silently replaced."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("x") as handle:
        json.dump(value, handle, indent=2, allow_nan=False)
        handle.write("\n")


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def tree(path):
    path = Path(path)
    if not path.is_dir() or path.is_symlink():
        raise ValueError("missing or linked input tree")
    result = {}
    for f in sorted(path.rglob("*")):
        if f.is_symlink():
            raise ValueError("linked input refused")
        if f.is_file() and not {"__pycache__", "evals"}.intersection(f.relative_to(path).parts):
            result[f.relative_to(path).as_posix()] = sha(f)
    if not result:
        raise ValueError("empty input tree")
    return result


def tree_id(path):
    return hashlib.sha256(json.dumps(tree(path), sort_keys=True).encode()).hexdigest()


def assert_dev(case):
    if case not in DEV:
        raise ValueError("task outside the DEV allowlist")


def schedule(iteration=0):
    if type(iteration) is not int or not 0 <= iteration <= 8:
        raise ValueError("iteration must be 0 through 8")
    rng = random.Random(20261015 + iteration)
    pairs = [(case, rep) for case in DEV for rep in (1, 2)]
    rng.shuffle(pairs)
    rows = []
    for case, rep in pairs:
        slots = ["aa1", "aa2"] if iteration == 0 else ["incumbent", "candidate"]
        rng.shuffle(slots)
        for slot in slots:
            rows.append(dict(case=case, repetition=rep, slot=slot, arm=ARM, ordinal=len(rows) + 1))
    return rows


def scrub_prompt(text):
    """Conservative line removal of public answer-key pointers, including URLs."""
    pattern = (r"(?i)\b(?:PR|pull\s+request|issue)\s*#?\s*\d+|/pull/\d+|"
               r"https?://|github\.com|\bprovenance\b|source\s*(?:of\s+scope|:)|"
               r"[\w./-]+\.(?:[cm]?[jt]sx?|html|java|py|vue|svelte)(?::\d+|#L\d+|\s+lines?\s+\d+)|"
               r"\b(?:source\s+)?lines?\s+\d+")
    return "\n".join(line for line in text.splitlines() if not re.search(pattern, line)).strip()


def scrub_runtime_prompt(text):
    """Preserve runtime origins and their safety/approval text while scrubbing."""
    origins = {}
    def remember(match):
        key = "__APP_ORIGIN_" + str(len(origins)) + "__"
        origins[key] = match.group(0)
        return key
    text = re.sub(r"http://(?:127\.0\.0\.1|localhost|host\.docker\.internal):\d+", remember, text)
    text = scrub_prompt(text)
    for key, origin in origins.items():
        text = text.replace(key, origin)
    return text


def number(value, name, lower=0, upper=None):
    if type(value) not in (int, float) or not isfinite(value) or value < lower or (upper is not None and value > upper):
        raise ValueError("invalid or missing " + name)
    return value


def summarize(cells):
    expected = {(case, rep) for case in DEV for rep in (1, 2)}
    if len(cells) != 10 or {(c["case"], c["repetition"]) for c in cells} != expected:
        raise ValueError("batch incomplete, duplicate or foreign task")
    if len({c["call_id"] for c in cells}) != 10:
        raise ValueError("duplicate call ID")
    for c in cells:
        assert_dev(c["case"])
        if type(c["repetition"]) is not int or not isinstance(c["call_id"], str) or not c["call_id"]:
            raise ValueError("malformed repetition or call ID")
        if type(c["clean"]) is not bool or c["refactor_score"] not in (0, 1) or type(c["refactor_score"]) is bool:
            raise ValueError("malformed clean or binary survival")
        if c["refactor_score"] and not c["clean"]:
            raise ValueError("unclean cell cannot survive")
        if c.get("infrastructure_error") or c.get("cost_complete") is False:
            raise ValueError("infrastructure or incomplete cost makes batch void")
        number(c["refactor_score"], "survival", upper=1)
        number(c["kill_rate"], "kill rate", upper=1)
        for key in ("tokens", "generation_s", "scan_p0", "scan_p1p2"):
            number(c[key], key)
        if any(type(c[k]) is not int for k in ("scan_p0", "scan_p1p2")):
            raise ValueError("scanner counts must be integers")
    mean = lambda values: sum(values) / len(values)
    clean = [c for c in cells if c["clean"]]
    return dict(dev_refactor_survival=mean([c["refactor_score"] for c in cells]),
                clean_all_three_rate=mean([int(c["clean"]) for c in cells]),
                effective_kill_all_cells=mean([c["kill_rate"] if c["clean"] else 0 for c in cells]),
                effective_kill_clean_cells=mean([c["kill_rate"] for c in clean]) if clean else None,
                scanner_p0_total=sum(c["scan_p0"] for c in cells),
                scanner_p1p2_total=sum(c["scan_p1p2"] for c in cells),
                tokens_mean=mean([c["tokens"] for c in cells]),
                generation_s_mean=mean([c["generation_s"] for c in cells]), cells=10)


def permutation(candidate, incumbent):
    summarize(candidate)
    summarize(incumbent)
    distribution = {Fraction(0): Fraction(1)}
    observed = Fraction(0)
    for task in DEV:
        c = [int(r["refactor_score"]) for r in candidate if r["case"] == task]
        b = [int(r["refactor_score"]) for r in incumbent if r["case"] == task]
        observed += Fraction(sum(c), 2) - Fraction(sum(b), 2)
        k = sum(c + b)
        step = {Fraction(x, 2) - Fraction(k - x, 2): Fraction(comb(k, x) * comb(4 - k, 2 - x), 6)
                for x in range(max(0, k - 2), min(2, k) + 1)}
        new = defaultdict(Fraction)
        for a, pa in distribution.items():
            for b, pb in step.items():
                new[a + b] += pa * pb
        distribution = new
    return dict(p_one_sided=float(sum(p for v, p in distribution.items() if v >= observed)),
                observed_mean_task_difference=float(observed / 5), tasks=5,
                interpretation="descriptive; within-task exchangeability is not established")


def decide(candidate_cells, incumbent_cells, history_batches):
    c, b = summarize(candidate_cells), summarize(incumbent_cells)
    if len(history_batches) < 2:
        raise ValueError("at least two incumbent batches required for A/A spread")
    summaries = [summarize(batch) for batch in history_batches]
    noise = {}
    for key in c:
        if key == "cells":
            continue
        values = [s[key] for s in summaries if s[key] is not None]
        noise[key] = dict(min=min(values), max=max(values), width=max(values) - min(values)) if values else None
    guards = {k: c[k] is not None and b[k] is not None and c[k] >= b[k] - 1e-12
              for k in ("clean_all_three_rate", "effective_kill_all_cells", "effective_kill_clean_cells")}
    guards.update({k: c[k] <= b[k] for k in ("scanner_p0_total", "scanner_p1p2_total")})
    delta = c["dev_refactor_survival"] - b["dev_refactor_survival"]
    relative = lambda key: c[key] / b[key] - 1 if b[key] > 0 else None
    tokens, seconds = relative("tokens_mean"), relative("generation_s_mean")
    verdict = "REJECT"
    if all(guards.values()):
        if delta >= .10 - 1e-12 and tokens is not None and tokens <= .10 + 1e-12:
            verdict = "ADOPT_QUALITY"
        elif delta >= -1e-12 and tokens is not None and seconds is not None and (
                (tokens <= -.15 + 1e-12 and seconds <= .10 + 1e-12) or
                (seconds <= -.15 + 1e-12 and tokens <= .10 + 1e-12)):
            verdict = "ADOPT_COST"
    width = noise["dev_refactor_survival"]["width"]
    return dict(verdict=verdict, guards=guards, candidate=c, incumbent=b, delta=delta,
                tokens_change=tokens, seconds_change=seconds, noise=noise,
                within_batch_width=abs(delta) <= width + 1e-12,
                task_stratified_exact_permutation=permutation(candidate_cells, incumbent_cells),
                evidence_label="development evidence; adoption is not a significance or release claim")


def stop_reason(decisions):
    if len(decisions) >= 8:
        return "iteration cap"
    if len(decisions) >= 3 and all(d["verdict"] not in ADOPTIONS for d in decisions[-3:]):
        return "three consecutive non-adoptions"
    return None


def machinery():
    global MACHINERY
    if MACHINERY is None:
        def load(name, rel):
            spec = importlib.util.spec_from_file_location(name, ROOT / rel)
            module = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(module)
            return module
        # No imported campaign-level bindings, entry, summary or drive are called.
        base = load("loop_v2_codex_core", "scripts/evals/run-generator-multimodel-v2-codex.py")
        oss = load("loop_v2_oss", "scripts/evals/run-generator-oss-eval-v1.py")
        MACHINERY = base, oss
    return MACHINERY


def reject_root_mismatch(evidence, rec, transcripts, events):
    """Do not accept the predecessor's parentless fallback for a conflicting ID."""
    root = evidence.root_thread_of(events or [])
    directory = evidence.sessions_dir_for(rec, transcripts)
    rollouts = evidence.load_sessions(directory) if directory else []
    if root and len([r for r in rollouts if r.get("thread_id") == root and not r.get("parent_thread_id")]) != 1:
        raise ValueError("explicit transcript/rollout root identity mismatch")


def external(path):
    if path is None:
        raise ValueError("--campaign required")
    raw = Path(path).expanduser().absolute()
    for parent in (raw, *raw.parents):
        if parent.is_symlink() or (parent / ".git").exists() or parent.name == "e2e-skills-bench":
            raise ValueError("campaign must be external, unlinked and outside every repository/cache")
    return raw.resolve()


def copy_skill(source, target):
    tree(source)  # Refuse symlinks before copytree can dereference them.
    shutil.copytree(source, target, ignore=shutil.ignore_patterns("evals", "__pycache__"))


def bindings(config, campaign):
    # Script sources only, never recurse a benchmark pool or an inherited schedule.
    names = ["run-generator-loop-v2.py", "run-generator-multimodel-v2-codex.py",
             "run-generator-multimodel-v3-codex.py", "run-generator-multimodel-v1.py",
             "run-generator-official-reviewer-pilot-v1.py", "run-generator-official-pilot-v1.py",
             "run-generator-skill-effect-v3.py", "generator_codex_official_adapter_compat.py",
             "generator_codex_official_adapter_compat_v3.py", "generator_codex_adapter_v2.py",
             "generator_v2_codex_evidence.py", "generator_v3_codex_evidence.py",
             "generator_v2_codex_pooled.py", "generator_v3_codex_pooled.py",
             "run-generator-oss-eval-v1.py", "generator_oss_zeppelin.py", "generator_oss_vault.py",
             "run-reviewer-holdout.py", "eval_security.py"]
    loop = Path(config["loop_runner"])
    pool, dists = Path(config["pool"]), Path(config["dists"])
    scripts = {n: sha(ROOT / "scripts/evals" / n) for n in names}
    scripts["strict_json.py"] = sha(ROOT / "scripts/ci/lib/strict_json.py")
    _, oss = machinery()
    return dict(protocol=sha(BENCH / "protocol.json"), readme=sha(BENCH / "README.md"), scripts=scripts,
                tests=sha(ROOT / "scripts/ci/test-generator-loop-v2.py"), config=config,
                runtime_protocol=sha(oss.PROTOCOL), baseline=tree(campaign / "baseline"),
                reviewer=tree(campaign / "reviewer"), scanner=tree(oss.engine.REV_SKILL),
                loop_runner=sha(loop), loop_adapter=sha(loop.parent / "generator_codex_loop_adapter.py"),
                proxy=sha(loop.parents[2] / "benchmarks/generator-loop-v1/harness/serve.mjs"),
                synthetic={c: dict(case=tree(oss.engine.CASES / c), truth=sha(oss.engine.TRUTH / (c + ".json"))) for c in DEV_SYNTH},
                oss_tasks=oss.task_bindings(pool, DEV_OSS), oss_dists=oss.dist_bindings(dists, DEV_OSS),
                fixture_lock=sha(ROOT / "scripts/evals/fixtures/package-lock.json"),
                source_lock=sha(Path(config["source"]) / "package-lock.json"),
                plans=tree(campaign / "plans"), schedules=[schedule(i) for i in range(9)])


def prepare(args):
    campaign = external(args.campaign)
    if campaign.exists():
        raise ValueError("prepare needs a new campaign root")
    required = ("pool", "loop_runner", "dists", "source")
    if any(getattr(args, key) is None for key in required):
        raise ValueError("prepare requires explicit DEV input locations")
    config = {key: str(Path(getattr(args, key)).resolve()) for key in required}
    config.update(model=MODEL, campaign_root=str(campaign),
                  campaign_id="generator-loop-v2-" + hashlib.sha256(str(campaign).encode()).hexdigest()[:12])
    campaign.mkdir(mode=0o700, parents=True)
    copy_skill(ROOT / "skills/playwright-test-generator", campaign / "baseline")
    copy_skill(ROOT / "skills/e2e-reviewer", campaign / "reviewer")
    base, oss = machinery()
    (campaign / "plans").mkdir()
    for case in DEV:
        if case in DEV_SYNTH:
            scope = base.engine.load_truth(case)["task"]
        else:
            scope = (Path(config["pool"]) / "tasks" / case / "scope.md").read_text()
        scope = scrub_prompt(oss.scrub_scope(scope))
        (campaign / "plans" / (case + ".md")).write_text(oss.approved_plan(case, scope))
    write(campaign / "config.json", config)
    write(campaign / "prepared-bindings.json", bindings(config, campaign))


def require_live(args):
    if not args.allow_live:
        raise ValueError(args.command + " requires --allow-live")
    p = read(BENCH / "protocol.json")
    if p["model"]["id"] != MODEL or p["model"]["selection_status"] != "REPRODUCED":
        raise ValueError("model-selection rule not reproduced; successor preregistration required")
    campaign = external(args.campaign)
    config = read(campaign / "config.json")
    if config.get("campaign_root") != str(campaign):
        raise ValueError("campaign differs from its single canonical root")
    now = bindings(config, campaign)
    if now != read(campaign / "prepared-bindings.json"):
        raise ValueError("prepared inputs drifted; stop this protocol")
    if args.command not in ("freeze", "calibrate") and now != read(campaign / "freeze.json")["bindings"]:
        raise ValueError("freeze drift")
    if args.command != "calibrate":
        validate_calibration(campaign, config)
        if args.command != "freeze" and read(campaign / "freeze.json")["calibration_sha256"] != sha(campaign / "calibration/_scorer-calibration.json"):
            raise ValueError("frozen calibration drift")
    return campaign, config, now


def verify_campaign(campaign):
    config = read(campaign / "config.json")
    if config.get("campaign_root") != str(campaign.resolve()):
        raise ValueError("campaign canonical root drift")
    if bindings(config, campaign) != read(campaign / "freeze.json")["bindings"]:
        raise ValueError("campaign input drift; stop this protocol")
    validate_calibration(campaign, config)
    if read(campaign / "freeze.json")["calibration_sha256"] != sha(campaign / "calibration/_scorer-calibration.json"):
        raise ValueError("calibration drift")


def validate_calibration(campaign, config):
    data = read(campaign / "calibration/_scorer-calibration.json")
    if (data.get("status") != "PASS" or data.get("campaign_id") != config["campaign_id"]
            or data.get("bindings") != {"prepared_sha256": sha(campaign / "prepared-bindings.json")}
            or set(data.get("tasks", {})) != set(DEV_OSS) or data.get("model_calls") != 0):
        raise ValueError("matching DEV reference calibration required")


def calibrate(args, campaign, config):
    """Import exact OSS reference scoring, overriding broad campaign bindings."""
    _, oss = machinery()
    target = campaign / "calibration"
    target.mkdir()
    old_bindings = oss.bindings
    try:
        oss.bindings = lambda *a, **kw: {"prepared_sha256": sha(campaign / "prepared-bindings.json")}
        with live_context(campaign, config, campaign / "baseline"):
            rt = oss.runtime(runtime_args(config))
            with rt.campaign():
                oss.calibrate_references(runtime_args(config), rt, target)
        validate_calibration(campaign, config)
    finally:
        oss.bindings = old_bindings


def iteration_dir(campaign, iteration):
    schedule(iteration)
    return campaign / "iterations" / f"{iteration:02d}"


def batch_dir(directory, slot):
    if slot not in ("aa1", "aa2", "candidate", "incumbent"):
        raise ValueError("unregistered batch slot")
    return directory / "batches" / slot


def artifact_tree(path):
    """Hash all generated bytes, including helpers; never follow links."""
    if not path.exists():
        return {}
    if path.is_symlink():
        raise ValueError("linked generated root")
    result = {}
    for f in sorted(path.rglob("*")):
        if f.is_symlink():
            raise ValueError("linked generated artifact")
        if f.is_file():
            result[f.relative_to(path).as_posix()] = sha(f)
    return result


def generation_inputs(target):
    return {name: artifact_tree(target / name) for name in ("final-artifacts", "final-transcripts", "codex-sessions")}


def verify_report(target):
    report = read(target / "final.json")
    if report["generation_inputs"] != generation_inputs(target):
        raise ValueError("generated spec, transcript or session drift")
    generated = read(target.parents[1] / "generated.json")
    if generated["reports"].get(target.name) != sha(target / "final.json"):
        raise ValueError("generated report changed")
    return report


def verified_result(directory, slot):
    if any((directory / n).exists() for n in ("VOID.json", "SCORE-VOID.json", "POST-VOID.json")):
        raise ValueError("void batch cannot enter a decision or noise estimate")
    target = batch_dir(directory, slot)
    result = read(target / "results.json")
    if read(directory / "analyzed.json")[slot] != sha(target / "results.json"):
        raise ValueError("analyzed result drift")
    report = verify_report(target)
    score_path = target / result["score_file"]
    if (result["report_sha256"] != sha(target / "final.json") or result["scores_sha256"] != sha(score_path)
            or result["skill_sha256"] != report["skill_sha256"] or result["summary"] != summarize(result["cells"])):
        raise ValueError("result provenance mismatch")
    return result


def previous_decisions(campaign):
    decisions = []
    for i in range(1, 9):
        path = iteration_dir(campaign, i) / "decision.json"
        if not path.exists():
            break
        decisions.append(read(path))
    return decisions


def incumbent(campaign, iteration):
    decisions = previous_decisions(campaign)
    if len(decisions) != iteration - 1 or stop_reason(decisions):
        raise ValueError("iteration order or stop rule refuses further work")
    result = campaign / "baseline"
    for i, decision in enumerate(decisions, 1):
        if decision["verdict"] in ADOPTIONS:
            result = iteration_dir(campaign, i) / "candidate"
            if tree_id(result) != decision["candidate_binding"]["candidate"]:
                raise ValueError("adopted incumbent drift")
    return result


def candidate_diff(before, after):
    a, b = tree(before), tree(after)
    chunks = []
    for name in sorted(set(a) | set(b)):
        if a.get(name) != b.get(name):
            if not name.endswith((".md", ".py", ".sh", ".json", ".yaml")):
                raise ValueError("candidate contains unsupported file type")
            old = (Path(before) / name).read_text().splitlines(True) if name in a else []
            new = (Path(after) / name).read_text().splitlines(True) if name in b else []
            chunks.extend(difflib.unified_diff(old, new, fromfile="a/" + name, tofile="b/" + name))
    if not chunks:
        raise ValueError("candidate made no change")
    return "".join(chunks)


def validate_candidate(directory, before):
    directory = Path(directory)
    hypothesis = read(directory / "hypothesis.json")
    packet = read(directory / "packet.json")
    failures = {r["call_id"] for r in packet["failures"]}
    if (set(hypothesis) != {"hypotheses"} or len(hypothesis["hypotheses"]) != 1):
        raise ValueError("exactly one hypothesis required")
    h = hypothesis["hypotheses"][0]
    if (set(h) != {"mechanism", "evidence_call_ids", "expected_effect", "falsification"}
            or not h["evidence_call_ids"] or not set(h["evidence_call_ids"]) <= failures
            or any(not isinstance(h[k], str) or not h[k].strip() for k in ("mechanism", "expected_effect", "falsification"))):
        raise ValueError("hypothesis must cite failing cells and state one falsifiable mechanism")
    diff = candidate_diff(before, directory / "candidate")
    if diff != (directory / "diff").read_text():
        raise ValueError("diff does not match candidate")
    added = "\n".join(line[1:] for line in diff.splitlines() if line.startswith("+") and not line.startswith("+++"))
    if not added.isascii() or any(case.lower() in added.lower() for case in DEV):
        raise ValueError("rule text must be English and contain no DEV identifiers")
    if re.search(r"locator\s*\(\s*['\"]|\.(?:sidebar|note-name)\b|grader|perturbation|R1-markup", added, re.I):
        raise ValueError("task-specific examples or scorer mirroring refused")
    review = read(directory / "wording-review.json")
    if (review.get("diff_sha256") != sha(directory / "diff") or review.get("verdict") != "PASS"
            or not review.get("reviewer") or review.get("reviewer") == "researcher"
            or not review.get("reason")):
        raise ValueError("independent semantic wording review required")
    repo = read(directory / "repository-review.json")
    if repo != {"diff_sha256": sha(directory / "diff"), "command": "/bin/bash -p scripts/ci/review.sh", "exit": 0}:
        raise ValueError("repository review PASS for this diff required")
    return dict(incumbent=tree_id(before), candidate=tree_id(directory / "candidate"),
                hypothesis=sha(directory / "hypothesis.json"), hypothesis_md=sha(directory / "hypothesis.md"),
                packet=sha(directory / "packet.json"), diff=sha(directory / "diff"),
                wording=sha(directory / "wording-review.json"), repository_review=sha(directory / "repository-review.json"))


def review_candidate(campaign, iteration):
    """Run repository rules against a disposable tracked checkout plus candidate."""
    directory = iteration_dir(campaign, iteration)
    diff = directory / "diff"
    if candidate_diff(incumbent(campaign, iteration), directory / "candidate") != diff.read_text():
        raise ValueError("candidate diff drift")
    tracked = subprocess.run(["git", "ls-files", "-z"], cwd=ROOT, capture_output=True, check=True).stdout.decode().split("\0")
    with tempfile.TemporaryDirectory(prefix="loop-v2-review-") as tmp:
        checkout = Path(tmp).resolve()
        for rel in filter(None, tracked):
            src, dst = ROOT / rel, checkout / rel
            if src.is_symlink():
                raise ValueError("tracked symlink refused in review snapshot")
            dst.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(src, dst)
        target = checkout / "skills/playwright-test-generator"
        shutil.rmtree(target)
        copy_skill(directory / "candidate", target)
        for cmd in (["git", "init", "-q"], ["git", "add", "-A"]):
            disposable_git(cmd, checkout, {})
        done = subprocess.run(["/bin/bash", "-p", "scripts/ci/review.sh"], cwd=checkout,
                              capture_output=True, text=True, timeout=300)
        (directory / "repository-review.log").write_text(done.stdout + done.stderr)
        write(directory / "repository-review.json", {"diff_sha256": sha(diff),
              "command": "/bin/bash -p scripts/ci/review.sh", "exit": done.returncode})
        if done.returncode:
            raise ValueError("candidate repository review failed")


def packet(campaign, iteration):
    before = incumbent(campaign, iteration)
    directory = iteration_dir(campaign, iteration)
    previous = iteration_dir(campaign, iteration - 1)
    if iteration == 1:
        slot = "aa2"
    else:
        prior_decision = read(previous / "decision.json")
        slot = "candidate" if prior_decision["verdict"] in ADOPTIONS else "incumbent"
    result = verified_result(previous, slot)
    failures = []
    for row in result["cells"]:
        assert_dev(row["case"])
        if row["clean"] and row["refactor_score"] and row["kill_rate"] == 1:
            continue
        rec = next(r for r in read(batch_dir(previous, slot) / "final.json")["runs"] if r["call_id"] == row["call_id"])
        specs = {}
        for name in rec.get("spec_files", []):
            rel = Path(name)
            if rel.is_absolute() or ".." in rel.parts or rel.parts[0] != "tests":
                raise ValueError("unsafe delivered test path")
            f = batch_dir(previous, slot) / "final-artifacts" / rec["call_id"] / rel
            if f.is_symlink():
                raise ValueError("linked spec refused")
            specs[name] = scrub_prompt(f.read_text())
        raw = next(r for r in read(batch_dir(previous, slot) / "scores.json")["scores"] if r["call_id"] == row["call_id"])
        errors = [scrub_prompt(str(message)) for run in raw.get("clean_runs", []) + [raw.get("refactor") or {}]
                  for message in run.get("errors", [])]
        failures.append(dict(call_id=row["call_id"], case=row["case"], clean=row["clean"],
                             refactor_score=row["refactor_score"], kill_rate=row["kill_rate"], specs=specs,
                             failure_messages=errors, status=(rec.get("structured_output") or {}).get("status"),
                             summary=scrub_prompt((rec.get("structured_output") or {}).get("summary", ""))))
    if not failures:
        raise ValueError("no failing DEV cells support another hypothesis")
    data = dict(incumbent_sha256=tree_id(before), failures=failures,
                rule="Exactly one falsifiable general hypothesis; no task-specific rule text; no eval material or retrieval.")
    write(directory / "packet.json", data)
    return data


@contextlib.contextmanager
def live_context(campaign, config, skill):
    _, oss = machinery()
    p = oss.protocol()
    old_stage, old_prompt = oss.stage_skills, oss.engine.call_model
    old_scrub, old_plan = oss.scrub_scope, oss.approved_plan
    old_frame = oss.engine.FRAME
    def stage(work, arm):
        if arm != ARM:
            raise ValueError("arm C only")
        for source, name in ((skill, "playwright-test-generator"), (campaign / "reviewer", "e2e-reviewer")):
            copy_skill(source, Path(work) / "skill" / name)
        return Path(work) / "skill/playwright-test-generator", Path(work) / "skill/e2e-reviewer"
    try:
        oss.stage_skills = stage
        oss.scrub_scope = scrub_prompt
        def plan(case, scope):
            assert_dev(case)
            return (campaign / "plans" / (case + ".md")).read_text()
        oss.approved_plan = plan
        with oss.codex_context(campaign / "runtime", p):
            real = oss.engine.call_model
            def call(project, work, arm, task, model, timeout, budget):
                if arm not in (ARM, "researcher") or model != MODEL:
                    raise ValueError("unregistered treatment/model")
                prompt = scrub_runtime_prompt(oss.engine.FRAME.format(task=task))
                # Preserve the complete model-visible prompt, including the arm suffix.
                suffix = oss.compat.ARM_LINES[arm]
                if arm == ARM:
                    suffix = suffix.format(gen="/work/skill/playwright-test-generator/SKILL.md", rev="/work/skill/e2e-reviewer/SKILL.md")
                prompts = campaign / "prompts"
                prompts.mkdir(exist_ok=True)
                name = hashlib.sha256((prompt + suffix).encode()).hexdigest() + ".txt"
                if not (prompts / name).exists():
                    (prompts / name).write_text(prompt + suffix)
                frame = oss.engine.FRAME
                oss.engine.FRAME = "{task}"
                try:
                    return real(project, work, arm, prompt, model, timeout, budget)
                finally:
                    oss.engine.FRAME = frame
            oss.engine.call_model = call
            yield oss
    finally:
        oss.stage_skills, oss.engine.call_model, oss.engine.FRAME = old_stage, old_prompt, old_frame
        oss.scrub_scope, oss.approved_plan = old_scrub, old_plan


def synthetic_generate(item, args, campaign, directory, oss):
    case = item["case"]
    if case not in DEV_SYNTH or item["arm"] != ARM:
        raise ValueError("unregistered synthetic cell")
    rec = dict(item, call_id=oss.v2.v1.call_id_of(item), attempts=[])
    oss.engine.wait_for_load(rec)
    for attempt in (1, 2):
        with tempfile.TemporaryDirectory(prefix="loop-v2-cell-") as tmp:
            work = Path(tmp).resolve()
            # Reuse the corrected v2 generation-only staging transformer.
            base, _ = machinery()
            with base.generation_staging() as staged:
                project = base.engine.stage(base.engine.CASES / case, args.ports.take(), work, git=False)
                rec["generation_config"] = base.generation_summary(staged)
            (project / "specs").mkdir(exist_ok=True)
            plan = (campaign / "plans" / (case + ".md")).read_text()
            (project / "specs/plan.md").write_text(plan)
            (project / "tests/seed.spec.ts").write_text(oss.v2.orig.SEED)
            # The OSS helper commits only in this disposable project.
            for cmd in (["git", "init", "-q"], ["git", "add", "-A"], ["git", "commit", "-q", "-m", "baseline"]):
                disposable_git(cmd, project, oss.engine.GIT_ENV)
            oss.engine.CODEX_TRANSCRIPTS = directory / "final-transcripts"
            task = scrub_prompt(oss.engine.load_truth(case)["task"]) + oss.v2.orig.PLAN_LINE
            result = oss.engine.call_model(project, work, ARM, task, MODEL, 1500, None)
            rec["attempts"].append(result)
            rec.update(result)
            if not result.get("infrastructure_error"):
                rec.update(oss.engine.collect_deliverable(project, directory / "final-artifacts" / rec["call_id"]))
        if not result.get("infrastructure_error") or result.get("fatal_infrastructure"):
            break
    rec.update(deliverable=bool(rec.get("spec_files")), infrastructure_error="spec_files" not in rec)
    return rec


def runtime_args(config):
    fields = {k: config[k] for k in ("pool", "dists", "source", "loop_runner", "campaign_id")}
    return argparse.Namespace(**fields, lock_file=machinery()[1].SHARED_LOCK)


def disposable_git(cmd, project, identity):
    """Do not let ambient Git routing/configuration escape disposable staging."""
    env = {k: v for k, v in os.environ.items() if not k.startswith("GIT_")}
    env.update(identity, GIT_CONFIG_NOSYSTEM="1", GIT_CONFIG_GLOBAL=os.devnull)
    subprocess.run([cmd[0], "-c", "core.hooksPath=" + os.devnull, *cmd[1:]],
                   cwd=project, env=env, capture_output=True, check=True)


def run_batch(args, campaign, config):
    directory = iteration_dir(campaign, args.iteration)
    before = campaign / "baseline" if args.iteration == 0 else incumbent(campaign, args.iteration)
    candidate_lock = None if args.iteration == 0 else validate_candidate(directory, before)
    write(directory / "started.json", dict(schedule=schedule(args.iteration),
          freeze_sha256=sha(campaign / "freeze.json"), incumbent=tree_id(before), candidate=candidate_lock))
    reports = {slot: {"model": MODEL, "runs": []} for slot in ("aa1", "aa2") if args.iteration == 0}
    if args.iteration:
        reports = {slot: {"model": MODEL, "runs": []} for slot in ("incumbent", "candidate")}
    _, oss = machinery()
    args.ports = oss.engine.Ports(23000)
    rt = oss.runtime(runtime_args(config))
    try:
        with rt.campaign():
            for row in schedule(args.iteration):
                slot = row["slot"]
                target = batch_dir(directory, slot)
                target.mkdir(parents=True, exist_ok=True)
                skill = directory / "candidate" if slot == "candidate" else before
                with live_context(campaign, config, skill) as active:
                    if row["case"] in DEV_OSS:
                        rec = active.generate(row, runtime_args(config), rt, MODEL, target, list(DEV_OSS))
                    else:
                        rec = synthetic_generate(row, args, campaign, target, active)
                reports[slot]["runs"].append(rec)
                write(target / (rec["call_id"] + ".json"), rec)
                if rec.get("infrastructure_error") or rec.get("fatal_infrastructure"):
                    raise ValueError("infrastructure-invalid batch")
                if rec.get("note_isolation_violations"):
                    raise ValueError("Zeppelin namespace violation makes batch void")
                if bindings(config, campaign) != read(campaign / "freeze.json")["bindings"]:
                    raise ValueError("bound input drift")
                if candidate_lock and validate_candidate(directory, before) != candidate_lock:
                    raise ValueError("candidate changed during run")
        for slot, report in reports.items():
            skill = directory / "candidate" if slot == "candidate" else before
            report.update(skill_sha256=tree_id(skill), skill_bytes=sum((skill / name).stat().st_size for name in tree(skill)),
                          freeze_sha256=sha(campaign / "freeze.json"), generation_inputs=generation_inputs(batch_dir(directory, slot)))
            write(batch_dir(directory, slot) / "final.json", report)
        write(directory / "generated.json", {"status": "COMPLETED", "reports":
              {slot: sha(batch_dir(directory, slot) / "final.json") for slot in reports}})
    except BaseException as exc:
        write(directory / "VOID.json", {"error": type(exc).__name__, "message": str(exc)})
        raise


def score_batch(args, campaign, config):
    directory = iteration_dir(campaign, args.iteration)
    if any((directory / name).exists() for name in ("VOID.json", "POST-VOID.json")) or not (directory / "generated.json").exists():
        raise ValueError("void or incomplete generation")
    _, oss = machinery()
    rt = oss.runtime(runtime_args(config))
    ports = oss.engine.Ports(24000)
    annotations = read(args.adjudications) if args.adjudications else {}
    write(directory / "score-started.json", {"freeze_sha256": sha(campaign / "freeze.json")})
    try:
        with live_context(campaign, config, campaign / "baseline"), rt.campaign():
            machinery()[0].scoring_guard(list(DEV_SYNTH))
            for slot in (("aa1", "aa2") if args.iteration == 0 else ("incumbent", "candidate")):
                target = batch_dir(directory, slot)
                scores = []
                slot_annotations = annotations.get(slot, {})
                for rec in verify_report(target)["runs"]:
                    assert_dev(rec["case"])
                    if rec["case"] in DEV_OSS:
                        result = oss.score_rows(target, rt, {"model": MODEL, "runs": [rec]}, slot_annotations)[0]
                    elif rec.get("spec_files"):
                        tests = target / "final-artifacts" / rec["call_id"] / "tests"
                        result = oss.engine.evaluate_specs(rec["case"], oss.engine.CASES / rec["case"], tests, rec["spec_files"], ports)
                        scan = oss.engine.scan_smells(tests, [f.removeprefix("tests/") for f in rec["tests_files"]])
                        for defect, fault in result["faults"].items():
                            if defect in slot_annotations.get(rec["call_id"], {}):
                                annotation = slot_annotations[rec["call_id"]][defect]
                                if type(annotation) is not bool:
                                    raise ValueError("attribution must be boolean")
                                fault["valid_detection"] = annotation
                        result = oss.score_measurements(result["clean_runs"], result["faults"], result["refactor"], scan)
                    else:
                        result = dict(clean=False, refactor_score=0, kill_rate=0, scan={"p0": 0, "p1p2": 0})
                    result.update({k: rec[k] for k in ("call_id", "case", "repetition")})
                    scores.append(result)
                    write(target / "raw-scores" / (rec["call_id"] + ".json"), result)
                verify_report(target)
                write(target / "scores.json", {"scores": scores, "report_sha256": sha(target / "final.json")})
        write(directory / "scored.json", {"status": "COMPLETED"})
    except BaseException as exc:
        write(directory / "SCORE-VOID.json", {"error": type(exc).__name__, "message": str(exc)})
        raise


def adjudicate_batch(campaign, iteration, annotations):
    """Attribute saved mutant failures offline; never relaunch a browser/model."""
    verify_campaign(campaign)
    directory = iteration_dir(campaign, iteration)
    if not (directory / "scored.json").is_file() or (directory / "SCORE-VOID.json").exists():
        raise ValueError("completed scoring required")
    _, oss = machinery()
    outputs = []
    for slot in (("aa1", "aa2") if iteration == 0 else ("incumbent", "candidate")):
        target = batch_dir(directory, slot)
        verify_report(target)
        data = read(target / "scores.json")
        for row in data["scores"]:
            if not row.get("faults"):
                continue
            for defect, fault in row["faults"].items():
                annotation = annotations.get(slot, {}).get(row["call_id"], {}).get(defect)
                if annotation is not None:
                    if type(annotation) is not bool:
                        raise ValueError("attribution must be boolean for exact slot/call/defect")
                    fault["valid_detection"] = annotation
            row.update(oss.score_measurements(row["clean_runs"], row["faults"], row["refactor"], row.get("scan")))
            if row.get("fault_attribution_complete") is not True:
                raise ValueError("complete positive-failure attribution required before publishing adjudications")
        data["raw_scores_sha256"] = sha(target / "scores.json")
        outputs.append((target, data))
    for target, data in outputs:
        write(target / "adjudicated-scores.json", data)


def analyze_batch(campaign, iteration):
    verify_campaign(campaign)
    directory = iteration_dir(campaign, iteration)
    if any((directory / name).exists() for name in ("SCORE-VOID.json", "VOID.json", "POST-VOID.json")) or not (directory / "scored.json").exists():
        raise ValueError("void or incomplete batch cannot be analyzed for decisions")
    _, oss = machinery()
    analysis_digests = {}
    outputs = []
    for slot in (("aa1", "aa2") if iteration == 0 else ("incumbent", "candidate")):
        target = batch_dir(directory, slot)
        score_path = target / "adjudicated-scores.json" if (target / "adjudicated-scores.json").exists() else target / "scores.json"
        report, scored = verify_report(target), read(score_path)
        if report["freeze_sha256"] != sha(campaign / "freeze.json") or report["model"] != MODEL:
            raise ValueError("report freeze or model differs")
        if "raw_scores_sha256" in scored and scored["raw_scores_sha256"] != sha(target / "scores.json"):
            raise ValueError("raw score provenance drift")
        if scored["report_sha256"] != sha(target / "final.json"):
            raise ValueError("score provenance drift")
        indexed = {r["call_id"]: r for r in scored["scores"]}
        if len(scored["scores"]) != 10 or len(report["runs"]) != 10 or len(indexed) != 10 or set(indexed) != {r["call_id"] for r in report["runs"]}:
            raise ValueError("scores incomplete or duplicated")
        cells = []
        for rec in report["runs"]:
            assert_dev(rec["case"])
            if rec["arm"] != ARM or rec.get("infrastructure_error"):
                raise ValueError("aborted or foreign-arm result")
            raw = indexed[rec["call_id"]]
            if rec.get("spec_files"):
                raw = oss.score_measurements(raw["clean_runs"], raw["faults"], raw["refactor"], raw.get("scan"))
            costs = []
            for attempt in rec["attempts"]:
                events = oss.v2.transcript_events(attempt, target / "final-transcripts")
                sess = oss.v2.rollout_summary(attempt, target / "final-transcripts", events)
                reject_root_mismatch(oss.evidence, attempt, target / "final-transcripts", events)
                costs.append(oss.evidence.cell_tokens(attempt, sess))
            if not costs or not all(c["complete"] for c in costs):
                raise ValueError("all-attempt parent/child cost incomplete")
            scan = raw.get("scan")
            if rec.get("spec_files") and (not scan or scan.get("error") or "p0" not in scan or "p1p2" not in scan):
                raise ValueError("delivered cell scanner evidence missing")
            extra = oss.v2.cell_extras(rec, target / "final-transcripts", target)
            cells.append(dict(case=rec["case"], repetition=rec["repetition"], call_id=rec["call_id"],
                clean=raw["clean"], refactor_score=raw["refactor_score"], kill_rate=raw["kill_rate"],
                scan_p0=(scan or {}).get("p0", 0), scan_p1p2=(scan or {}).get("p1p2", 0),
                tokens=sum(c["processed"] for c in costs), cached_tokens=sum(c["total"] - c["processed"] for c in costs),
                generation_s=sum(a["elapsed_ms"] / 1000 for a in rec["attempts"]), cost_complete=True,
                fidelity=extra.get("treatment"), deliverable=bool(rec.get("spec_files"))))
        result = dict(cells=cells, summary=summarize(cells), skill_sha256=report["skill_sha256"],
                      skill_bytes=report.get("skill_bytes"),
                      report_sha256=sha(target / "final.json"), scores_sha256=sha(score_path), score_file=score_path.name)
        outputs.append((target, result))
    for target, result in outputs:
        write(target / "results.json", result)
        analysis_digests[target.name] = sha(target / "results.json")
    write(directory / "analyzed.json", analysis_digests)


def decide_iteration(campaign, iteration):
    verify_campaign(campaign)
    directory = iteration_dir(campaign, iteration)
    if iteration == 0:
        a, b = [verified_result(directory, slot)["cells"] for slot in ("aa1", "aa2")]
        spread = decide(a, b, [a, b])
        spread.pop("verdict")
        spread["comparison_kind"] = "A/A noise calibration only; no adoption decision"
        write(directory / "aa-spread.json", spread)
        return
    before = incumbent(campaign, iteration)
    if any((directory / name).exists() for name in ("SCORE-VOID.json", "VOID.json", "POST-VOID.json")):
        raise ValueError("void batch cannot decide")
    current = [verified_result(directory, slot) for slot in ("candidate", "incumbent")]
    for slot, result in zip(("candidate", "incumbent"), current):
        target = batch_dir(directory, slot)
        if (result["report_sha256"] != sha(target / "final.json")
                or result["scores_sha256"] != sha(target / result["score_file"])):
            raise ValueError("decision inputs changed after analysis")
    lock = validate_candidate(directory, before)
    if read(directory / "started.json")["candidate"] != lock:
        raise ValueError("candidate provenance changed since generation")
    if [r["skill_sha256"] for r in current] != [lock["candidate"], lock["incumbent"]]:
        raise ValueError("result treatment differs from candidate/incumbent")
    history = []
    for i in range(iteration + 1):
        for slot in (("aa1", "aa2") if i == 0 else ("incumbent", "candidate")):
            if i == iteration and slot == "candidate":
                continue
            result = verified_result(iteration_dir(campaign, i), slot)
            if result["skill_sha256"] == lock["incumbent"]:
                history.append(result["cells"])
    decision = decide(current[0]["cells"], current[1]["cells"], history)
    decision.update(iteration=iteration, candidate_binding=lock,
                    researcher_overhead=read(directory / "researcher-run.json"))
    decision["stop_reason"] = stop_reason(previous_decisions(campaign) + [decision])
    write(directory / "decision.json", decision)
    (directory / "decision.md").write_text("# Iteration decision\n\n" + decision["verdict"] +
        ". Development evidence only. Wording review: PASS.\n\nSee decision.json for both kill guards, costs, exact permutation and incumbent A/A spread.\n")


def researcher(args, campaign, config):
    directory = iteration_dir(campaign, args.iteration)
    before = incumbent(campaign, args.iteration)
    data = read(directory / "packet.json") if (directory / "packet.json").exists() else packet(campaign, args.iteration)
    if data["incumbent_sha256"] != tree_id(before):
        raise ValueError("research packet belongs to another incumbent")
    write(directory / "researcher-started.json", {"model": MODEL, "packet_sha256": sha(directory / "packet.json")})
    with live_context(campaign, config, before) as oss, tempfile.TemporaryDirectory(prefix="loop-v2-research-") as tmp:
        work = Path(tmp).resolve()
        project = work / "project"
        project.mkdir()
        copy_skill(before, project / "candidate")
        (project / "node_modules").symlink_to(oss.engine.FIXTURE_MODULES)
        write(project / "packet.json", data)
        for cmd in (["git", "init", "-q"], ["git", "add", "-A"], ["git", "commit", "-q", "-m", "baseline"]):
            disposable_git(cmd, project, oss.engine.GIT_ENV)
        task = ("Read packet.json and candidate/. From failing DEV cells propose exactly one hypothesis. "
                "Write hypothesis.json with exactly {hypotheses: [{mechanism: string, evidence_call_ids: [string], "
                "expected_effect: string, falsification: string}]}, plus hypothesis.md. "
                "Make one coherent change under candidate/ only. General principles only: no selectors, regexes, "
                "identifiers, control names or examples from DEV applications, no text mirroring grader perturbations. "
                "Do not retrieve anything from the internet, inspect installed benchmark tasks, eval or sealed material, "
                "modify packet.json, install packages, run browsers or change scoring/decisions. "
                "Only candidate/, hypothesis.json and hypothesis.md may be written. Then return status complete.")
        old = oss.compat.ARM_LINES.get("researcher")
        oss.compat.ARM_LINES["researcher"] = ""
        oss.engine.CODEX_TRANSCRIPTS = directory / "researcher-transcripts"
        frame = oss.engine.FRAME
        oss.engine.FRAME = "{task}"
        try:
            rec = oss.engine.call_model(project, work, "researcher", task, MODEL, 1500, None)
        finally:
            oss.engine.FRAME = frame
            if old is None:
                oss.compat.ARM_LINES.pop("researcher", None)
            else:
                oss.compat.ARM_LINES["researcher"] = old
        events = oss.v2.transcript_events(rec, directory / "researcher-transcripts")
        try:
            reject_root_mismatch(oss.evidence, rec, directory / "researcher-transcripts", events)
            sess = oss.v2.rollout_summary(rec, directory / "researcher-transcripts", events)
            rec["overhead_tokens"] = oss.evidence.cell_tokens(rec, sess)
        except ValueError as exc:
            rec["overhead_tokens"] = {"complete": False, "error": str(exc)}
        rec["overhead_generation_s"] = rec.get("elapsed_ms", 0) / 1000
        write(directory / "researcher-run.json", rec)
        if rec.get("infrastructure_error"):
            raise ValueError("researcher infrastructure failure; do not retry this iteration")
        if sha(project / "packet.json") != sha(directory / "packet.json"):
            raise ValueError("researcher altered the evidence packet")
        allowed = {"candidate", "packet.json", "hypothesis.json", "hypothesis.md", ".git", "node_modules"}
        if {f.name for f in project.iterdir()} - allowed or {f.name for f in work.iterdir()} != {"project"}:
            raise ValueError("researcher wrote outside its authorized outputs")
        copy_skill(project / "candidate", directory / "candidate")
        for name in ("hypothesis.json", "hypothesis.md"):
            source = project / name
            if source.is_symlink():
                raise ValueError("linked research output")
            (directory / name).write_text(source.read_text())
        (directory / "diff").write_text(candidate_diff(before, directory / "candidate"))


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=("plan", "prepare", "packet", "review-candidate", "validate-candidate", "calibrate", "freeze", "researcher", "run", "score", "adjudicate", "analyze", "decide"))
    parser.add_argument("--campaign", type=Path)
    parser.add_argument("--iteration", type=int, default=0)
    parser.add_argument("--allow-live", action="store_true")
    for key in ("pool", "loop-runner", "dists", "source", "adjudications"):
        parser.add_argument("--" + key, type=Path)
    args = parser.parse_args(argv)
    schedule(args.iteration)
    if args.command in ("calibrate", "freeze", "researcher", "run", "score"):
        campaign, config, bound = require_live(args)  # Before machinery imports or setup.
        if args.command == "freeze":
            write(campaign / "freeze.json", {"bindings": bound,
                  "calibration_sha256": sha(campaign / "calibration/_scorer-calibration.json")})
        elif args.command == "calibrate":
            calibrate(args, campaign, config)
        elif args.command == "researcher":
            researcher(args, campaign, config)
        elif args.command == "run":
            run_batch(args, campaign, config)
        else:
            score_batch(args, campaign, config)
        if bindings(config, campaign) != bound:
            if args.command in ("run", "score"):
                write(iteration_dir(campaign, args.iteration) / "POST-VOID.json", {"reason": "post-operation binding drift"})
            raise ValueError("post-operation binding drift; output void")
    elif args.command == "plan":
        print(json.dumps(schedule(args.iteration), indent=2))
    elif args.command == "prepare":
        prepare(args)
    else:
        campaign = external(args.campaign)
        if args.command == "packet":
            packet(campaign, args.iteration)
        elif args.command == "review-candidate":
            review_candidate(campaign, args.iteration)
        elif args.command == "validate-candidate":
            print(json.dumps(validate_candidate(iteration_dir(campaign, args.iteration), incumbent(campaign, args.iteration))))
        elif args.command == "analyze":
            analyze_batch(campaign, args.iteration)
        elif args.command == "adjudicate":
            if args.adjudications is None:
                raise ValueError("--adjudications required")
            adjudicate_batch(campaign, args.iteration, read(args.adjudications))
        else:
            decide_iteration(campaign, args.iteration)
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (ValueError, KeyError, OSError) as error:
        print(str(error), file=sys.stderr)
        raise SystemExit(2)
