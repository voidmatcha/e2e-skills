#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Validate the published fix-pair corpus and its derived score claims."""

import json
import re
from pathlib import Path, PurePosixPath


ROOT = Path(__file__).resolve().parents[2]
BASE = ROOT / "benchmarks/fixpair-v1"
LICENSES = {"MIT", "Apache-2.0"}
REPOS = {"appsmith", "backstage", "cypress-realworld-app", "react-router", "storybook", "payload", "react-admin", "router"}


def require(condition, message):
    if not condition:
        raise AssertionError(message)


def load(path):
    return json.loads((BASE / path).read_text(encoding="utf-8"))


def safe_path(value):
    path = PurePosixPath(value)
    require(isinstance(value, str) and value and not path.is_absolute() and
            all(part not in {"", ".", ".."} for part in path.parts), f"unsafe path: {value!r}")
    return path


def run():
    corpus = load("corpus.json")
    require(corpus["schema_version"] == 1, "corpus schema version")
    require(corpus["labeling"]["human_labels"] is False, "label provenance")
    cases = corpus["cases"]
    require(isinstance(cases, list) and len(cases) == 19, "expected 19 batch B/C/D cases")
    batch_c_ids = {"payloa-1c4eba41", "payloa-bda5d0d3", "payloa-f1b005c4",
                   "react--0a5bb042", "react--6ad48415", "react--d8e38cb9", "router-0b377c2e"}
    batch_d_ids = {"payloa-ee4cd616", "router-db1774b7"}
    require({c["id"] for c in cases[10:17]} == batch_c_ids, "batch C case set")
    require({c["id"] for c in cases[17:]} == batch_d_ids, "batch D case set")
    require(corpus["labeling"]["batch_c"] == {
        "classifier": "codex-gpt-6-sol", "independent_verifier": "codex-gpt-6-astra",
        "human_labels": False, "confirmed_instances": 12}, "batch C labeling summary")
    require(corpus["labeling"]["batch_d"] == {
        "classifier": "codex-gpt-6-sol", "independent_verifier": "codex-gpt-6-astra",
        "human_labels": False, "confirmed_instances": 6, "rejected_instances": 14},
        "batch D labeling summary")
    ids = set()
    expected_samples = set()
    instance_count = 0
    for case in cases:
        require(set(case) == {"id", "upstream_repo", "upstream_url", "license", "commit", "parent",
                              "commit_subject", "spec_paths", "instances", "labeling_provenance"},
                "case schema")
        case_id = case["id"]
        require(re.fullmatch(r"[a-z-]+-[0-9a-f]{8}", case_id) and case_id not in ids,
                f"case id: {case_id}")
        ids.add(case_id)
        require(case["upstream_repo"] in REPOS and case["license"] in LICENSES, f"repo/license: {case_id}")
        require(case["upstream_url"].startswith("https://github.com/"), f"repo URL: {case_id}")
        require(all(re.fullmatch(r"[0-9a-f]{40}", case[k]) for k in ("commit", "parent")),
                f"commit metadata: {case_id}")
        require(isinstance(case["commit_subject"], str) and case["commit_subject"], f"subject: {case_id}")
        provenance = case["labeling_provenance"]
        verifier_key, verifier_name = (("astra_verifier", "codex-gpt-6-astra") if case_id in batch_c_ids | batch_d_ids
                                       else ("claude_verifier", "claude-subagent"))
        require(provenance["codex_model"] == "codex-gpt-6-sol" and
                provenance["codex_verdict"] == "smell_fix" and
                provenance[verifier_key] == verifier_name and
                provenance["human_labels"] is False, f"provenance: {case_id}")
        paths = case["spec_paths"]
        require(isinstance(paths, list) and paths == sorted(set(paths)) and paths, f"spec paths: {case_id}")
        for spec in paths:
            safe_path(spec)
            for side in ("before", "after"):
                file = BASE / "cases" / case_id / side / spec
                require(file.is_file() and not file.is_symlink(), f"missing snapshot: {file}")
                expected_samples.add((case_id, side, spec))
        require(isinstance(case["instances"], list) and case["instances"], f"instances: {case_id}")
        for instance in case["instances"]:
            prefix = "astra" if case_id in batch_c_ids | batch_d_ids else "claude"
            require(set(instance) == {"spec_path", "pattern_id", "severity", "before_line",
                                     "before_source_line", "after_mapped_line", "after_mapping_rule",
                                     "codex_rule", f"{prefix}_verdict", f"{prefix}_contract_quote",
                                     f"{prefix}_reason"}, f"instance schema: {case_id}")
            spec = instance["spec_path"]
            require(spec in paths and re.fullmatch(r"#[0-9]+[a-z]?(?:-[0-9]+[a-z]?)?", instance["pattern_id"]),
                    f"instance identity: {case_id}")
            require(instance["severity"] in {"P0", "P1", "P2"} and
                    instance[f"{prefix}_verdict"] == "confirm" and
                    instance[f"{prefix}_contract_quote"] and instance["codex_rule"],
                    f"instance label: {case_id}")
            line = instance["before_line"]
            raw_lines = (BASE / "cases" / case_id / "before" / spec).read_bytes().splitlines()
            require(type(line) is int and 1 <= line <= len(raw_lines), f"line range: {case_id}")
            require(raw_lines[line - 1] == instance["before_source_line"].encode("utf-8"),
                    f"BEFORE byte mismatch: {case_id}:{spec}:{line}")
            after_lines = (BASE / "cases" / case_id / "after" / spec).read_bytes().splitlines()
            mapped = instance["after_mapped_line"]
            require(type(mapped) is int and 1 <= mapped <= len(after_lines) and
                    instance["after_mapping_rule"] in {"delete", "replace-similar", "replace-offset", "equal", "insert"},
                    f"AFTER mapping: {case_id}")
            instance_count += 1
    require(instance_count == 33 and
            sum(len(c["instances"]) for c in cases if c["id"] in batch_c_ids) == 12 and
            sum(len(c["instances"]) for c in cases if c["id"] in batch_d_ids) == 6,
            "expected 15 batch B, 12 batch C, and 6 batch D instances")

    actual_snapshots = {(p.relative_to(BASE / "cases").parts[0], p.relative_to(BASE / "cases").parts[1],
                         PurePosixPath(*p.relative_to(BASE / "cases").parts[2:]).as_posix())
                        for p in (BASE / "cases").rglob("*") if p.is_file()}
    require(actual_snapshots == expected_samples, "snapshot set differs from corpus")
    for case in cases:
        path = BASE / "licenses" / f"{case['upstream_repo']}-LICENSE.txt"
        require(path.is_file() and len(path.read_bytes()) > 900, f"missing upstream license: {case['upstream_repo']}")
        marker = "Apache License" if case["license"] == "Apache-2.0" else "MIT License"
        require(marker in path.read_text(encoding="utf-8") or "Permission is hereby granted" in path.read_text(encoding="utf-8"),
                f"license text does not match {case['license']}: {path.name}")
    require((BASE / "licenses" / "backstage-NOTICE.txt").is_file(), "missing Backstage NOTICE")

    rows = load("scores/samples.json")
    summary = load("scores/summary.json")
    require(isinstance(rows, list) and len(rows) == 84 and summary["sample_count"] == 84,
            "sample count")
    seen = set()
    by_batch = {batch: {arm: {"samples": 0, "strict_hits": 0, "before_instances": 0,
                              "after_false_alarms": 0, "after_instances": 0, "input_tokens": 0}
                        for arm in ("skill", "no-skill")} for batch in ("B", "C", "D")}
    totals = {arm: {"samples": 0, "strict_hits": 0, "before_instances": 0,
                    "after_false_alarms": 0, "after_instances": 0, "input_tokens": 0}
              for arm in ("skill", "no-skill")}
    for row in rows:
        require(set(row) == {"arm", "case", "side", "sample_id", "spec_path", "instance_hits",
                             "strict_hits", "before_instances", "false_alarms", "after_instances",
                             "input_tokens"}, "result row schema")
        arm, case_id, side, spec = (row[key] for key in ("arm", "case", "side", "spec_path"))
        require(arm in totals and (case_id, side, spec) in expected_samples, "result row scope")
        key = arm, case_id, side, spec
        require(key not in seen, f"duplicate result: {key}")
        seen.add(key)
        require(row["sample_id"].endswith(f"-{side}"), f"sample id: {key}")
        instances = [i for c in cases if c["id"] == case_id for i in c["instances"] if i["spec_path"] == spec]
        require(len(row["instance_hits"]) == len(instances), f"instance score count: {key}")
        expected_locations = sorted((i["pattern_id"], i["before_line"] if side == "before"
                                     else i["after_mapped_line"]) for i in instances)
        actual_locations = sorted((i["pattern_id"], i["line"]) for i in row["instance_hits"])
        require(actual_locations == expected_locations, f"instance score locations: {key}")
        require(all(i["result"] in ({"hit", "miss"} if side == "before" else {"clean", "alarm"})
                    for i in row["instance_hits"]), f"instance score status: {key}")
        expected_hits = sum(i["result"] == "hit" for i in row["instance_hits"])
        expected_alarms = sum(i["result"] == "alarm" for i in row["instance_hits"])
        require(row["strict_hits"] == (expected_hits if side == "before" else 0) and
                row["false_alarms"] == (expected_alarms if side == "after" else 0) and
                row["before_instances"] == (len(instances) if side == "before" else 0) and
                row["after_instances"] == (len(instances) if side == "after" else 0),
                f"score mismatch: {key}")
        require(type(row["input_tokens"]) is int and row["input_tokens"] > 0, f"tokens: {key}")
        batch_total = by_batch["D" if case_id in batch_d_ids else
                               "C" if case_id in batch_c_ids else "B"][arm]
        totals[arm]["samples"] += 1
        batch_total["samples"] += 1
        for field in ("strict_hits", "before_instances", "false_alarms", "after_instances", "input_tokens"):
            target = "after_false_alarms" if field == "false_alarms" else field
            totals[arm][target] += row[field]
            batch_total[target] += row[field]
    require(len(seen) == 2 * len(expected_samples), "missing result rows")
    require(summary["arms"] == totals and summary["case_count"] == len(cases), "summary totals")
    require(summary["batches"] == by_batch, "per-batch totals")
    for batch, expected in (("B", [(24, 10, 15, 0), (24, 5, 15, 0)]),
                            ("C", [(14, 11, 12, 0), (14, 7, 12, 0)]),
                            ("D", [(4, 4, 6, 0), (4, 1, 6, 0)])):
        require([(by_batch[batch][a]["samples"], by_batch[batch][a]["strict_hits"],
                  by_batch[batch][a]["before_instances"], by_batch[batch][a]["after_false_alarms"])
                 for a in ("skill", "no-skill")] == expected, f"frozen batch {batch} totals")
    require([(totals[a]["strict_hits"], totals[a]["before_instances"], totals[a]["after_false_alarms"])
             for a in ("skill", "no-skill")] == [(25, 33, 0), (13, 33, 0)], "frozen B+C+D totals")
    require([(by_batch["D"][a]["input_tokens"], totals[a]["input_tokens"])
             for a in ("skill", "no-skill")] == [(2128166, 20454464), (485924, 5290450)],
            "frozen D and combined token totals")
    gain = round(100 * (totals["skill"]["strict_hits"] - totals["no-skill"]["strict_hits"]) / 33, 1)
    rule = summary["preregistered_rule"]
    require(rule == {"minimum_strict_recall_gain_pp": 20, "maximum_skill_after_false_alarms": 1},
            "preregistered rule")
    require(summary["strict_recall_gain_pp"] == gain and
            summary["preregistered_rule_met"] is (gain >= rule["minimum_strict_recall_gain_pp"] and
            totals["skill"]["after_false_alarms"] <= rule["maximum_skill_after_false_alarms"]),
            "gate outcome")
    aggregate = summary["all_batch_aggregate_including_local_only_unpublished_batch"]
    require([(aggregate[a]["hits"], aggregate[a]["before_instances"], aggregate[a]["after_false_alarms"])
             for a in ("skill", "no-skill")] == [(36, 44, 0), (23, 44, 1)], "frozen aggregate")
    readme = (BASE / "README.md").read_text(encoding="utf-8")
    for claim in ("10/15", "5/15", "11/12", "7/12", "4/6", "1/6", "25/33", "13/33", "0/33", "36.4", "36/44", "23/44", "0 versus 1",
                  f"{totals['skill']['input_tokens']:,}", f"{totals['no-skill']['input_tokens']:,}"):
        require(claim in readme, f"README missing computed claim: {claim}")
    for claim in ("release-ineligible Codex `gpt-6-astra`", "**10/15** without it",
                  "**0/15 AFTER false alarms** in both arms", "11,571,501", "482,145.875 per sample",
                  "2,891,803", "120,491.792 per sample", "independently verified by a Claude subagent, not by Astra",
                  "the only qualifying repository found was refine", "relevant E2E suite uses Cypress"):
        require(claim in readme, f"README missing Astra batch B claim: {claim}")
    astra_rows = (
        ("appsmi-b7510d1b-6b9472", "1/1", "0/1"),
        ("appsmi-ec4ea27d-ca7b28", "0/1", "0/1"),
        ("backst-02a0f0df-27e82e", "0/1", "0/1"),
        ("backst-daaaa72e-38c493", "0/1", "0/1"),
        ("backst-daaaa72e-9b7887", "0/1", "0/1"),
        ("cypres-d081b173-a861fe", "1/1", "0/1"),
        ("react--44f7e565-9a0ac6", "2/2", "0/2"),
        ("storyb-457eeac9-7a2ca3", "1/1", "0/1"),
        ("storyb-457eeac9-d00259", "1/1", "0/1"),
        ("storyb-613551da-06aa67", "0/1", "0/1"),
        ("storyb-8e8a1d31-0f2bfc", "2/2", "0/2"),
        ("storyb-efb5d516-337174", "2/2", "0/2"),
    )
    for sample_id, before, after in astra_rows:
        row = f"| `{sample_id}` | {before} | {after} | {before} | {after} |"
        require(row in readme, f"README missing Astra sample score: {sample_id}")
    sonnet_rows = json.loads((BASE / "scores/sonnet-5-5-b-samples.json").read_text())
    require(len(sonnet_rows) == 48, "Sonnet 5.5 batch B sample count")
    for arm, hits, tokens in (("skill", 9, 7804777), ("no-skill", 9, 954600)):
        rows = [row for row in sonnet_rows if row["arm"] == arm]
        require(len(rows) == 24 and len({row["sample"] for row in rows}) == 24,
                f"Sonnet 5.5 {arm} sample identities")
        require(sum(row["strict_recall"]["hits"] for row in rows) == hits and
                sum(row["strict_recall"]["n"] for row in rows) == 15 and
                sum(row["after_false_alarm"]["alarms"] for row in rows) == 0 and
                sum(row["input_tokens"] for row in rows) == tokens,
                f"Sonnet 5.5 {arm} totals")
    require("**9/15 versus 9/15**" in readme and
            "scores/sonnet-5-5-b-samples.json" in readme,
            "README missing Sonnet 5.5 result")
    for path in BASE.rglob("*"):
        if path.is_file():
            require("cal.com" not in path.relative_to(BASE).as_posix().lower() and
                    b"cal.com" not in path.read_bytes().lower(), f"excluded material: {path}")
    print(f"fixpair-v1: {len(cases)} cases, {instance_count} instances, "
          f"B+C+D skill {totals['skill']['strict_hits']}/33, no-skill {totals['no-skill']['strict_hits']}/33, "
          f"AFTER false alarms 0/33 each, gain {gain} pp")


if __name__ == "__main__":
    run()
