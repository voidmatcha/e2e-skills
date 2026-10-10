#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Re-score archived fixpair Inspect logs without changing frozen score files.

Usage: python3 scripts/evals/audit-fixpair-logs.py arm=path/to/run.eval [...]
The raw logs are local development artifacts and are not part of this repository.
"""

import json
import re
import sys
import zipfile
from pathlib import Path


HEAD = re.compile(r"^#{2,4}\s+\[?(P[012])\]?(.*)$", re.M)
IDS = re.compile(r"#(\d+[a-z]?)")


def base_id(pattern):
    return "3b" if pattern.lower().startswith("3b") else re.match(r"\d+", pattern).group(0)


def findings(text, target_name, include_heading_locations):
    """Mirror the frozen parser, optionally admitting citations in finding headings."""
    out = []
    heads = list(HEAD.finditer(text))
    name = re.escape(target_name)
    full = re.compile(rf"(?:[\w./@-]*/)?{name}`?:(\d+)(?:\s*[-–]\s*:?(\d+))?")
    short = re.compile(r"(?<![\w/.\]])`?:(\d+)(?:\s*[-–]\s*:?(\d+))?")
    words = re.compile(r"\b[Ll]ines?\s+(\d+)(?:\s*(?:[-–]|to)\s*(\d+))?")
    for index, head in enumerate(heads):
        end = heads[index + 1].start() if index + 1 < len(heads) else len(text)
        body = text[head.end():end]
        body = re.split(r"^## (?!\[?P[012])", body, flags=re.M)[0]
        subs = re.split(r"^### ", body, flags=re.M)
        blocks = ["### " + block for block in subs[1:]] or [body]
        head_ids = IDS.findall(head.group(0))
        head_names_target = re.search(name, head.group(0)) is not None
        for block in blocks:
            if block.lower().startswith("### refuted"):
                continue
            ids = head_ids or IDS.findall(block)[:1]
            citation_text = head.group(0) + "\n" + block if include_heading_locations else block
            names_target = head_names_target or re.search(name, block) is not None
            lines = set()
            for regex in ((full, short, words) if names_target else (full,)):
                for match in regex.finditer(citation_text):
                    start = int(match.group(1))
                    stop = int(match.group(2)) if match.group(2) else start
                    if stop < start or stop - start > 60:
                        stop = start
                    lines.update(range(start, stop + 1))
            out.append({"severity": head.group(1), "ids": sorted(set(ids)),
                        "base_ids": {base_id(item) for item in ids}, "lines": lines})
    return out


def score(sample, include_heading_locations):
    metadata = sample["metadata"]
    parsed = findings(sample["output"]["completion"] or "", metadata["target_name"],
                      include_heading_locations)
    side = metadata["side"]
    result = []
    for instance in metadata["instances"]:
        lo, hi = instance["line_range"]
        want = base_id(instance["pattern_id"].lstrip("#"))
        pad = 2 if side == "after" else 0
        hit = any(want in finding["base_ids"] and
                  any(lo - pad <= line <= hi + pad for line in finding["lines"])
                  for finding in parsed)
        result.append({"pattern": instance["pattern_id"], "line": lo, "hit": hit})
    return result


def main(paths):
    if not paths:
        raise SystemExit("usage: audit-fixpair-logs.py arm=run.eval [...]")
    output = []
    for arg in paths:
        arm, path = arg.split("=", 1)
        with zipfile.ZipFile(Path(path)) as archive:
            names = sorted({name for name in archive.namelist() if name.startswith("samples/")
                            and name.endswith(".json")})
            samples = {json.loads(archive.read(name))["id"]: json.loads(archive.read(name))
                       for name in names}
        for sample_id, sample in sorted(samples.items()):
            if sample["metadata"]["arm"] != arm:
                raise ValueError(f"arm mismatch: {sample_id}")
            old = score(sample, False)
            archived = sample["scores"]["strict_recall" if sample["metadata"]["side"] == "before"
                                        else "after_false_alarm"]["value"]
            old_count = sum(item["hit"] for item in old)
            archived_count = archived["hits" if sample["metadata"]["side"] == "before" else "alarms"]
            if old_count != archived_count:
                raise ValueError(f"frozen parser reproduction failed: {sample_id}: {old_count} != {archived_count}")
            new = score(sample, True)
            for prior, corrected in zip(old, new):
                if prior["hit"] != corrected["hit"]:
                    output.append({"arm": arm, "sample": sample_id, "pattern": prior["pattern"],
                                   "line": prior["line"], "frozen_hit": prior["hit"],
                                   "heading_aware_hit": corrected["hit"]})
        print(f"{arm}: verified {len(samples)} frozen sample scores", file=sys.stderr)
    print(json.dumps(output, indent=2))


if __name__ == "__main__":
    main(sys.argv[1:])
